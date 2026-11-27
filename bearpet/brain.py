from __future__ import annotations

import math
import random

from . import lines

SETTLED = ("idle", "walk", "sit", "sigh", "sleep", "coffee", "burger")


class Brain:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

        self.state = "idle"
        self.t = 0.0
        self.dur = 2.4
        self.dir = 1
        self.speed = 0.0
        self.energy = 0.72
        self.paused = False

        self.work_heat = 0.0
        self.work_streak = 0
        self.work_frustrated = False
        self.work_variant = "typing-calm"

        self.blink = 1.0
        self._blink_t = -1.0
        self._blink_next = self.rng.uniform(1.5, 4.0)

        self.speech: str | None = None
        self.speech_age = 0.0
        self.speech_dur = 0.0
        self.speech_priority = False
        self._speech_next = self.rng.uniform(4.0, 9.0)
        self._recent: list[str] = []

        self._praise_next = self.rng.uniform(12.0, 30.0)

        self._enter("idle")

    def say(self, text: str, dur: float | None = None, priority: bool = False):
        self.speech = text
        self.speech_age = 0.0
        self.speech_dur = dur if dur is not None else max(2.6, 1.1 + 0.11 * len(text))
        self.speech_priority = priority

    def say_rand(self, pool: list[str], dur: float | None = None):
        if self.speech and self.speech_priority:
            return
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

    def tick(self, dt: float):
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
        self._work_tick(dt)

        if self.state in SETTLED and self.t >= self.dur:
            self._choose_next()
        elif self.state in ("dizzy", "hop") and self.t >= self.dur:
            self._enter("idle")

    def _work_tick(self, dt: float):
        if self.state == "sit":
            self.work_heat = min(18.0, self.work_heat + dt)
            if not self.work_frustrated and (self.work_heat >= 5.5 or self.work_streak >= 2):
                self.work_frustrated = True
                self.say_rand(lines.WORK_FRUSTRATED_LINES, 2.8)
        else:
            self.work_heat = max(0.0, self.work_heat - dt * 0.45)
            if self.work_heat <= 1.2:
                self.work_frustrated = False
                if self.work_heat <= 0.05:
                    self.work_streak = 0

    def _energy_tick(self, dt: float):
        drain = {"walk": 0.011, "idle": 0.0045, "sit": 0.008, "sigh": 0.02,
                 "coffee": -0.025, "burger": -0.030, "sleep": -0.052}.get(self.state, 0.0)
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
        self._praise_next -= dt
        if self._praise_next > 0.0:
            return
        if self.speech or self.state in ("sleep", "dizzy"):
            self._praise_next = self.rng.uniform(8.0, 15.0)
            return
        self._praise_next = self.rng.uniform(45.0, 95.0)
        self.say_rand(lines.COMPLIMENT_LINES, 5.6)

    def _choose_next(self):
        e = self.energy
        r = self.rng.random()
        if self.state == "walk":
            opts = [("idle", 0.36), ("walk", 0.22), ("sit", 0.16), ("coffee", 0.07),
                    ("burger", 0.05), ("sigh", 0.08), ("hop", 0.06)]
        elif self.state == "sit":
            opts = [("idle", 0.30), ("coffee", 0.14), ("sleep", 0.18), ("walk", 0.26), ("sigh", 0.12)]
        elif self.state in ("coffee", "burger"):
            opts = [("idle", 0.44), ("walk", 0.28), ("sit", 0.18), ("sleep", 0.10)]
        elif self.state == "sleep":
            self.say_rand(lines.WAKE_LINES, 2.2)
            opts = [("idle", 0.46), ("walk", 0.22), ("coffee", 0.12), ("sit", 0.12), ("sigh", 0.08)]
        elif self.state == "sigh":
            opts = [("idle", 0.48), ("walk", 0.22), ("sit", 0.16), ("coffee", 0.08), ("burger", 0.06)]
        else:
            opts = [("walk", 0.38), ("idle", 0.16), ("sit", 0.18), ("coffee", 0.07),
                    ("burger", 0.05), ("sigh", 0.10), ("hop", 0.06)]

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

    def _enter(self, state: str, forced: bool = False):
        prev = self.state
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
            self.dur = r.uniform(3.2, 6.8)
            self.speed = 0.0
            if prev == "sit" or self.work_heat > 1.8:
                self.work_streak += 1
            else:
                self.work_streak = 1
            if forced:
                self.work_heat = min(18.0, self.work_heat + 2.4)
            self.work_frustrated = (self.work_streak >= 2 or self.work_heat >= 5.5)
            self.work_variant = "keyboard" if (not self.work_frustrated and r.random() < 0.25) else "typing-calm"
            if forced:
                pool = lines.WORK_FRUSTRATED_LINES if self.work_frustrated else lines.WORK_CALM_LINES
                self.say_rand(pool, 2.6)
        elif state in ("coffee", "burger"):
            self.dur = r.uniform(2.6, 4.6)
            self.speed = 0.0
            if forced or r.random() < 0.45:
                self.say_rand(lines.SNACK_LINES, 2.4)
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

    def force(self, state: str):
        self._enter(state, forced=True)

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
