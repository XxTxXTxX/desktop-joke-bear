"""提醒引擎：把"什么时候提醒"这件事实实在在地交给这台电脑的本地时钟。

时间规格（由手机端填、本机解析）：
    "20:00"        下一次 20:00（已经过了就明天）
    "in:30m"       30 分钟后（也支持 in:2h / in:90 秒）
    "at:2026-11-19T20:00"  绝对本地时间
    ""             立刻

重复：daily（每天同一时刻）/ weekday（工作日）/ 空。
静音时段：跨午夜也支持，非紧急提醒会被压到静音结束再说，并标注"昨晚的"。
"""
from __future__ import annotations

import calendar
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field

WEEKDAY = "weekday"
DAILY = "daily"


def _parse_hhmm(spec: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*", spec)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h < 24 and 0 <= mi < 60):
        return None
    return h, mi


def parse_when(spec: str | None, now: float) -> float | None:
    """把时间规格解析成 epoch 秒；无法解析返回 None（调用方按"立刻"处理）。"""
    if not spec:
        return now
    s = spec.strip()
    lt = time.localtime(now)

    m = re.fullmatch(r"in\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([smh]?)", s, re.I)
    if m:
        v = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        mult = {"s": 1, "m": 60, "h": 3600}[unit]
        return now + v * mult

    if s.lower().startswith("at:"):
        iso = s[3:].strip().replace(" ", "T")
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return time.mktime(time.strptime(iso, fmt))
            except ValueError:
                continue
        return None

    hm = _parse_hhmm(s)
    if hm is not None:
        h, mi = hm
        cand = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, mi, 0, 0, 0, -1))
        if cand <= now + 1:
            cand += 86400
        return cand
    return None


def next_occurrence(due: float, repeat: str | None, now: float) -> float | None:
    """重复提醒下一次的时间；非重复返回 None。"""
    if not repeat:
        return None
    nxt = due
    guard = 0
    while nxt <= now + 1 and guard < 400:
        nxt += 86400
        guard += 1
    if repeat == WEEKDAY:
        while time.localtime(nxt).tm_wday >= 5:      # 周六日往后挪
            nxt += 86400
    return nxt


@dataclass
class Reminder:
    id: int
    text: str
    due: float
    repeat: str | None = None
    urgent: bool = False
    source: str = "phone"
    created: float = field(default_factory=time.time)
    fired: int = 0

    def due_str(self) -> str:
        return time.strftime("%m-%d %H:%M", time.localtime(self.due))


def format_delta(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} 秒后"
    if sec < 3600:
        return f"{sec // 60} 分钟后"
    if sec < 86400:
        return f"{sec // 3600} 小时后"
    return f"{sec // 86400} 天后"


class ReminderStore:
    """提醒队列 + 本地时钟解析 + 静音时段。"""

    def __init__(self, path: str, quiet: tuple[str, str] = ("23:30", "08:00")):
        self.path = path
        self.quiet = quiet
        self.items: list[Reminder] = []
        self._seq = 1
        self.load()

    # ------------------------------------------------------------ 持久化
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        self._seq = int(data.get("seq", 1))
        self.items = []
        for d in data.get("items", []):
            try:
                self.items.append(Reminder(**d))
            except TypeError:
                continue
        self.items.sort(key=lambda r: r.due)

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": self._seq, "items": [asdict(r) for r in self.items]},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except Exception:
            pass

    # ------------------------------------------------------------ 时间策略
    def in_quiet_hours(self, now: float) -> bool:
        a, b = self.quiet
        pa, pb = _parse_hhmm(a), _parse_hhmm(b)
        if not pa or not pb:
            return False
        lt = time.localtime(now)
        cur = lt.tm_hour * 60 + lt.tm_min
        start, end = pa[0] * 60 + pa[1], pb[0] * 60 + pb[1]
        if start == end:
            return False
        if start < end:
            return start <= cur < end
        return cur >= start or cur < end            # 跨午夜

    def quiet_until(self, now: float) -> float:
        """静音结束的时刻（下一个 end 时间点）。"""
        a, b = self.quiet
        pb = _parse_hhmm(b)
        lt = time.localtime(now)
        if not pb:
            return now
        cand = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, pb[0], pb[1], 0, 0, 0, -1))
        if cand <= now:
            cand += 86400
        return cand

    def resolve(self, now: float, when: str | None, repeat: str | None,
                urgent: bool) -> float:
        """到点时间；静音时段内且不紧急 → 压到静音结束。"""
        due = parse_when(when, now)
        if due is None:
            due = now
        if not urgent and self.in_quiet_hours(due):
            due = max(due, self.quiet_until(due))
        return due

    # ------------------------------------------------------------ 增删查
    def add(self, text: str, due: float, repeat: str | None = None,
            urgent: bool = False, source: str = "phone") -> Reminder:
        r = Reminder(id=self._seq, text=text[:120], due=due, repeat=repeat,
                     urgent=urgent, source=source)
        self._seq += 1
        self.items.append(r)
        self.items.sort(key=lambda x: x.due)
        self.save()
        return r

    def add_from_remote(self, msg: dict, now: float) -> Reminder:
        text = str(msg.get("text", "")).strip() or "（空消息）"
        urgent = bool(msg.get("urgent"))
        repeat = msg.get("repeat") or None
        if repeat not in (DAILY, WEEKDAY, None, ""):
            repeat = None
        when = msg.get("at") or msg.get("when") or msg.get("at_local")
        due = self.resolve(now, when, repeat, urgent)
        return self.add(text, due, repeat or None, urgent)

    def remove(self, rid: int):
        self.items = [r for r in self.items if r.id != rid]
        self.save()

    def upcoming(self, now: float, limit: int = 6) -> list[Reminder]:
        return [r for r in self.items if r.due > now][:limit]

    def pop_due(self, now: float) -> list[Reminder]:
        """取走所有到点的提醒，并把重复的排到下一次。"""
        out, keep = [], []
        for r in self.items:
            if r.due <= now:
                out.append(r)
                nxt = next_occurrence(r.due, r.repeat, now)
                if nxt is not None:
                    r.due = nxt
                    r.fired += 1
                    keep.append(r)
            else:
                keep.append(r)
        self.items = keep
        if out:
            self.save()
        return out

    def summary(self, now: float) -> str:
        up = self.upcoming(now)
        if not up:
            return "没有待办提醒"
        return "；".join(f"{r.due_str()} {r.text}" for r in up[:3])


def tidy_quiet(values) -> tuple[str, str]:
    a, b = values
    if _parse_hhmm(a) and _parse_hhmm(b):
        return a, b
    return "23:30", "08:00"
