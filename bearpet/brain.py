"""行为状态机：决定熊此刻在干什么、什么时候叹气、什么时候想睡。"""
from __future__ import annotations

import math
import random

from . import lines

SETTLED = ("idle", "walk", "sit", "sigh", "sleep")


class Brain:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

        self.state = "idle"
        self.t = 0.0                 # 当前状态已持续时间
        self.dur = 2.4               # 当前状态计划时长
        self.dir = 1                 # 行走方向 -1/+1
        self.speed = 0.0             # px/s
        self.energy = 0.72           # 0..1，越低越想躺
        self.paused = False          # 被抓/掉落时暂停自主行为

        # 眨眼
        self.blink = 1.0
        self._blink_t = -1.0
        self._blink_next = self.rng.uniform(1.5, 4.0)

        # 说话
        self.speech: str | None = None
        self.speech_age = 0.0
        self.speech_dur = 0.0
        self.speech_priority = False      # True = 提醒等要紧的话，别被随机台词顶掉
        self._speech_next = self.rng.uniform(4.0, 9.0)
        self._recent: list[str] = []

        # 夸主人：闲下来每隔一两分钟夸一句
        self._praise_next = self.rng.uniform(12.0, 30.0)

        self._enter("idle")

    # ------------------------------------------------------------ 台词
    def say(self, text: str, dur: float | None = None, priority: bool = False):
        self.speech = text
        self.speech_age = 0.0
        self.speech_dur = dur if dur is not None else max(2.6, 1.1 + 0.11 * len(text))
        self.speech_priority = priority

    def say_rand(self, pool: list[str], dur: float | None = None):
        if self.speech and self.speech_priority:
            return                        # 正在说要紧的话，随机台词排队等下次
        if not pool:
            return
        avail = [x for x in pool if x not in self._recent] or pool
        text = self.rng.choice(avail)
        self._recent.append(text)
        del self._recent[:-4]
        self.say(text, dur)

    def speech_alpha(self) -> float:
        if not self.speech:
            return 0.0
        a_in = min(1.0, self.speech_age / 0.22)
        a_out = min(1.0, (self.speech_dur - self.speech_age) / 0.35)
        return max(0.0, min(a_in, a_out))

    # ------------------------------------------------------------ 主循环
    def tick(self, dt: float):
        # 气泡计时始终走
        if self.speech:
            self.speech_age += dt
            if self.speech_age >= self.speech_dur:
                self.speech = None
                self.speech_priority = False

        if self.paused:
            return

        self.t += dt
        self._blink_tick(dt)
        self._speech_tick(dt)
        self._praise_tick(dt)
        self._energy_tick(dt)

        if self.state in SETTLED and self.t >= self.dur:
            self._choose_next()
        elif self.state in ("dizzy", "hop") and self.t >= self.dur:
            self._enter("idle")

    # ------------------------------------------------------------ 内部
    def _energy_tick(self, dt: float):
        drain = {"walk": 0.011, "idle": 0.0045, "sit": -0.052, "sigh": 0.02}.get(self.state, 0.0)
        self.energy = max(0.0, min(1.0, self.energy - drain * dt))

    def _blink_tick(self, dt: float):
        if self._blink_t >= 0.0:
            self._blink_t += dt
            p = self._blink_t / 0.15
            if p >= 1.0:
                self._blink_t = -1.0
                self.blink = 1.0
                self._blink_next = self.rng.uniform(2.0, 6.5)
            else:
                self.blink = 1.0 - math.sin(p * math.pi) * 0.95
        else:
            self._blink_next -= dt
            if self._blink_next <= 0.0 and self.state in ("idle", "walk", "sit"):
                self._blink_t = 0.0

    def _speech_tick(self, dt: float):
        if self.state not in ("idle", "walk", "sit"):
            return
        self._speech_next -= dt
        if self._speech_next <= 0.0 and not self.speech:
            self.say_rand(lines.IDLE_LINES)
            self._speech_next = self.rng.uniform(9.0, 26.0)

    def _praise_tick(self, dt: float):
        """闲下来就夸主人一句（比自言自语稀疏，气泡停留也更久）。"""
        self._praise_next -= dt
        if self._praise_next > 0.0:
            return
        if self.speech or self.state in ("sleep", "dizzy"):
            self._praise_next = self.rng.uniform(8.0, 15.0)   # 正在说/在睡，等会儿再夸
            return
        self._praise_next = self.rng.uniform(45.0, 95.0)
        self.say_rand(lines.COMPLIMENT_LINES, 5.6)

    def _choose_next(self):
        e = self.energy
        r = self.rng.random()
        if self.state == "walk":
            opts = [("idle", 0.42), ("walk", 0.26), ("sit", 0.16), ("sigh", 0.09), ("hop", 0.07)]
        elif self.state == "sit":
            opts = [("idle", 0.36), ("sleep", 0.20), ("walk", 0.32), ("sigh", 0.12)]
        elif self.state == "sleep":
            # 睡醒先站一会儿，然后该干嘛干嘛
            self.say_rand(lines.WAKE_LINES, 2.2)
            opts = [("idle", 0.50), ("walk", 0.24), ("sit", 0.16), ("sigh", 0.10)]
        elif self.state == "sigh":
            opts = [("idle", 0.56), ("walk", 0.26), ("sit", 0.18)]
        else:  # idle
            opts = [("walk", 0.44), ("idle", 0.16), ("sit", 0.18), ("sigh", 0.14), ("hop", 0.08)]

        # 精力越高越不想睡，越困越容易就地睡过去
        if e > 0.60:
            sleep_k = 0.10
        elif e > 0.38:
            sleep_k = 0.45
        else:
            sleep_k = 3.2
        opts = [(s, w * (sleep_k if s == "sleep" else 1.0)) for s, w in opts]
        if e < 0.18:
            opts = [(s, w * (1.0 if s == "sleep" else (0.3 if s == "walk" else 0.7)))
                    for s, w in opts]

        acc = sum(w for _, w in opts)
        pick = r * acc
        for s, w in opts:
            pick -= w
            if pick <= 0:
                return self._enter(s)
        return self._enter("idle")

    def _enter(self, state: str):
        self.state = state
        self.t = 0.0
        r = self.rng
        if state == "idle":
            self.dur = r.uniform(1.8, 4.2)
            self.speed = 0.0
        elif state == "walk":
            self.dur = r.uniform(1.4, 4.6)
            self.dir = r.choice((-1, 1))
            self.speed = r.uniform(58.0, 104.0)
        elif state == "sit":
            self.dur = r.uniform(2.5, 6.0)
            self.speed = 0.0
        elif state == "sleep":
            self.dur = r.uniform(7.0, 16.0)
            self.speed = 0.0
            self.say_rand(lines.SLEEP_LINES, 2.4)
        elif state == "sigh":
            self.dur = 1.7
            self.speed = 0.0
            self.say_rand(lines.SIGH_LINES, 1.9)
        elif state == "hop":
            self.dur = 0.9
            self.speed = 0.0
        return state

    # ------------------------------------------------------------ 外部事件
    def force(self, state: str):
        self._enter(state)

    def notify_pickup(self):
        self.paused = True
        self.say_rand(lines.DRAG_LINES, 2.0)

    def notify_drop(self):
        self.paused = True

    def notify_landed(self, hard: bool):
        self.paused = False
        if hard:
            self._enter("dizzy")
            self.dur = 1.3
            self.say_rand(lines.LAND_LINES, 2.6)
        else:
            self._enter("idle")

    def notify_click(self):
        if self.state == "sleep":
            self._enter("idle")
            self.say_rand(lines.WAKE_LINES, 2.2)
        else:
            self.say_rand(lines.CLICK_LINES, 2.0)

    def notify_wall(self):
        self.dir *= -1
        if self.rng.random() < 0.25:
            self._enter("idle")
