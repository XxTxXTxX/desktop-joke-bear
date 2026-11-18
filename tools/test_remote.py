from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".deps"))
sys.path.insert(0, BASE)

from bearpet import app, reminder

PORT = 8799
TOKEN = "test-token-123"
URL = f"http://127.0.0.1:{PORT}"
OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "remote_test.log")
open(LOG, "w", encoding="utf-8").close()


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  {m}\n")
    print(m, flush=True)


def http(path, data=None, token=TOKEN, timeout=30):
    req = urllib.request.Request(f"{URL}{path}", method="POST" if data else "GET")
    if token:
        req.add_header("X-Pet-Token", token)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def phone_send(text, at="", repeat=""):
    st, js = http("/api/send", {"text": text, "at": at, "repeat": repeat})
    log(f"phone → {text!r} at={at!r} repeat={repeat!r} => {st} {js}")
    return st, js


def main() -> int:
    now = time.mktime((2026, 11, 19, 21, 0, 0, 0, 0, -1))
    cases = [("20:00", 86400 - 3600), ("in:30m", 1800), ("in:2h", 7200),
             ("at:2026-11-19T22:00", 3600), ("", 0)]
    for spec, want in cases:
        got = reminder.parse_when(spec, now) - now
        assert abs(got - want) < 2, f"parse {spec!r} 期望 {want} 得到 {got}"
    store = reminder.ReminderStore(os.path.join(OUT, "_t_rem.json"), ("23:30", "08:00"))
    t_late = time.mktime((2026, 11, 19, 23, 50, 0, 0, 0, -1))
    assert store.in_quiet_hours(t_late), "23:50 应在静音时段"
    assert not store.in_quiet_hours(now), "21:00 不应在静音时段"
    due = store.resolve(t_late, "in:5m", None, urgent=False)
    log(f"quiet resolve: 23:50 + 5m → {time.strftime('%m-%d %H:%M', time.localtime(due))}")
    assert time.localtime(due).tm_mday == 20 and time.localtime(due).tm_hour == 8, "静音应压到次日 08:00"
    assert store.resolve(t_late, "in:5m", None, urgent=True) < t_late + 400, "紧急应直接送达"
    log("unit ok: parse_when / quiet hours / urgent bypass")

    env = dict(os.environ, PET_PORT=str(PORT), PET_TOKEN=TOKEN, PET_BIND="127.0.0.1")
    data_file = os.path.join(BASE, "relay", "messages.jsonl")
    if os.path.exists(data_file):
        os.remove(data_file)
    relay = subprocess.Popen([sys.executable, os.path.join(BASE, "relay", "relay.py")],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(40):
            try:
                st, js = http("/api/health", token=None)
                if st == 200:
                    log(f"relay up: {js}")
                    break
            except Exception:
                time.sleep(0.15)
        else:
            raise SystemExit("中继没起来")

        st, _ = http("/api/send", {"text": "x"}, token="wrong")
        assert st == 401, f"错误令牌应 401，实际 {st}"
        log("auth ok: 错误令牌 401")

        cfg_path = os.path.join(BASE, ".bear.json")
        cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
        cfg.update({"remote": {"url": URL, "token": TOKEN}, "quiet": ["23:30", "08:00"], "quiet_on": True})
        json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False)
        for p in (os.path.join(BASE, ".reminders.json"), os.path.join(BASE, ".remote_state.json")):
            if os.path.exists(p):
                os.remove(p)

        pet = app.BearPet()
        pet.store.quiet = ("00:00", "00:00")
        last = time.perf_counter()
        t0 = time.time()

        def pump(sec):
            nonlocal last
            end = time.perf_counter() + sec
            while time.perf_counter() < end:
                pet.win.pump()
                n = time.perf_counter()
                pet.update(min(0.05, n - last))
                last = n
                pet.draw()
                time.sleep(0.006)

        pump(1.0)
        log(f"client status={pet.remote.status if pet.remote else None}")

        phone_send("现在就喝水", "")
        pump(3.0)
        log(f"speech after immediate = {pet.brain.speech!r}")
        assert pet.brain.speech == "现在就喝水", "立即提醒没有送达"

        phone_send("三秒后再提醒一次", "in:3s")
        pump(1.5)
        log(f"t+1.5s speech={pet.brain.speech!r} 待办={len(pet.store.items)}")
        assert pet.brain.speech != "三秒后再提醒一次", "定时提醒提前触发了"
        pump(3.5)
        log(f"t+5.0s speech={pet.brain.speech!r}")
        assert pet.brain.speech == "三秒后再提醒一次", "定时提醒没有按点触发"

        phone_send("每天喝水", "in:1s", "daily")
        pump(2.5)
        up = pet.store.upcoming(time.time(), 5)
        log(f"repeat 待办: {[(r.text, r.due_str(), r.repeat) for r in up]}")
        assert any(r.repeat == "daily" for r in up), "daily 没有排到下一次"

        pet.shutdown()
        phone_send("关机期间发的 1")
        phone_send("关机期间发的 2")
        pet = app.BearPet()
        pet.store.quiet = ("00:00", "00:00")
        pump(3.0)
        log(f"replay speech={pet.brain.speech!r}")
        assert pet.brain.speech in ("关机期间发的 1", "关机期间发的 2"), "离线消息没有补发"
        pump(2.0)
        log(f"after replay speech={pet.brain.speech!r} 待办={len(pet.store.items)}")

        t = time.time()
        st, js = http("/api/poll?since=99999&timeout=2")
        log(f"long-poll empty => {st} {js['messages']} 用时 {time.time()-t:.1f}s")
        assert st == 200 and js["messages"] == []

        pet.shutdown()
        log("ALL OK")
    finally:
        relay.terminate()
        try:
            relay.wait(timeout=5)
        except subprocess.TimeoutExpired:
            relay.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
