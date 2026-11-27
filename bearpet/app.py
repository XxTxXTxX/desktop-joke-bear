from __future__ import annotations

import math
import os
import threading
import time

from PIL import Image, ImageDraw, ImageFont

from . import (art, chat, chat_ui, editor, food, fx, garment, lines, outfit as omod,
               pixelfig, remind_ui, reminder, remote, size as sizemod, sprite, wardrobe,
               winlayer)
from .brain import Brain
from . import paths

GRAVITY = 2300.0
MAX_FALL = 3000.0
HARD_LAND = 720.0
FPS = 45
BUBBLE_BOTTOM = 116.0
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = paths.data_dir()
CONFIG_PATH = os.path.join(_DATA_DIR, ".bear.json")
REMINDER_PATH = os.path.join(_DATA_DIR, ".reminders.json")
REMOTE_STATE_PATH = os.path.join(_DATA_DIR, ".remote_state.json")

_DEBUG = os.environ.get("BEAR_DEBUG") == "1"
_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "preview", "debug.log")


def _log(msg: str):
    if not _DEBUG:
        return
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.perf_counter():8.3f}  {msg}\n")
    except Exception:
        pass


class BearPet:
    def __init__(self, seed: int | None = None):
        try:
            self.sprites: sprite.SpriteSheet | None = sprite.SpriteSheet()
        except Exception as exc:
            print(f"[bearpet] 图集不可用，回退程序化绘制: {exc}")
            self.sprites = None

        self.win = winlayer.LayeredWindow(sprite.W, sprite.H, "自嘲熊")
        self.brain = Brain(seed)
        self.running = True

        self.outfit: omod.Outfit = self._load_outfit()
        self.wear: dict = self._load_wear()
        if self.sprites is not None:
            self.sprites.set_outfit(self.outfit)
            self.sprites.wear = dict(self.wear)
        self.morph = None
        self.wardrobe = None

        self.size_scale: float = sizemod.clamp(self._load_config().get("size", 0.5))
        self.size_panel = None
        self.size_is_open = False

        cfg = self._load_config()
        q = cfg.get("quiet") or ["23:30", "08:00"]
        self.quiet = reminder.tidy_quiet(q[:2] if len(q) >= 2 else ["23:30", "08:00"])
        self.quiet_on = bool(cfg.get("quiet_on", True))
        self.store = reminder.ReminderStore(
            REMINDER_PATH, self.quiet if self.quiet_on else ("00:00", "00:00"))
        rem = cfg.get("remote") or {}
        self.remote_url = str(rem.get("url", "") or "").strip()
        self.remote_token = str(rem.get("token", "") or "").strip()
        self.remote = None
        if self.remote_url and self.remote_token:
            self.remote = remote.RemoteClient(self.remote_url, self.remote_token,
                                              REMOTE_STATE_PATH)
            self.remote.start()
            _log(f"remote client started: {self.remote_url}")
        self.remind_panel = None
        self.reminders_open = False
        self.editor = None
        self.editor_open = False
        self.riding = False
        self.climb = None
        self._cursor_last = None
        self._cursor_idle = 0.0
        self._cursor_speed = 0.0

        self.chat = chat.ChatClient(self)
        self.chat_window = None
        self.chat_open = False

        self.stats: dict = self._load_stats()
        self.feed_panel = None
        self.feed_is_open = False
        self.feeding = None
        self._hungry_next = 40.0

        left, top, right, bottom = self.win.work_area()
        self.y_ground = float(winlayer.ground_bottom() - 1 - sprite.GROUND)
        self.x = float(right - 520)
        self.y = self.y_ground
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = True

        self.spr_state = "idle"
        self.spr_ms = 0.0
        self.wave_t = 0.0
        self._look_dir: int | None = None
        self._look_active = False

        self.dragging = False
        self.pressed = False
        self.press_at = 0.0
        self.press_pos = (0, 0)
        self.grab = (0.0, 0.0)
        self.samples: list[tuple[float, float, float]] = []

        self.menu: Menu | None = None
        self.menu_open = False
        self.wardrobe: "Wardrobe | None" = None
        self.wardrobe_is_open = False
        self._prev_lbtn = False

        self._last_raise = 0.0
        self._frame = 0
        self._t0 = time.perf_counter()

        self.win.on_left_down = self._on_down
        self.win.on_left_up = self._on_up
        self.win.on_move = self._on_move
        self.win.on_right_up = self._on_right
        self.win.on_double_click = self._on_dbl

        self.brain.say("又见到你了，我没什么变化", 3.2)

    def _on_down(self, sx, sy):
        if (self.menu_open or self.wardrobe_is_open or self.feed_is_open
                or self.size_is_open or self.reminders_open or self.editor_open):
            return
        if self.riding:
            self.stop_riding(thrown=False)
            return
        self.pressed = True
        self.dragging = False
        self.press_at = time.perf_counter()
        self.press_pos = (sx, sy)
        self.grab = (self.x - sx, self.y - sy)
        self.samples = [(time.perf_counter(), self.x, self.y)]

    def _on_move(self, sx, sy):
        if not self.pressed:
            return
        if not self.dragging:
            dx = sx - self.press_pos[0]
            dy = sy - self.press_pos[1]
            if dx * dx + dy * dy < 16:
                return
            self.dragging = True
            self.brain.notify_pickup()
            _log(f"drag start at ({sx},{sy})")
        self.x = sx + self.grab[0]
        self.y = sy + self.grab[1]
        self._clamp_drag()
        now = time.perf_counter()
        self.samples.append((now, self.x, self.y))
        del self.samples[:-8]

    def _on_up(self, sx, sy):
        if (self.menu_open or self.wardrobe_is_open or self.feed_is_open
                or self.size_is_open or self.reminders_open):
            return
        was_drag = self.dragging
        self.pressed = False
        self.dragging = False
        if was_drag:
            self.vx, self.vy = self._throw_velocity()
            _log(f"drop vx={self.vx:.0f} vy={self.vy:.0f} pos=({self.x:.0f},{self.y:.0f})")
            self.brain.notify_drop()
            self.on_ground = False
        else:
            _log("click -> hop")
            self.brain.notify_click()
            self.wave_t = 0.9
            self.vy = -300.0
            self.on_ground = False
        self.samples = []

    def _on_dbl(self, sx, sy):
        if (self.menu_open or self.wardrobe_is_open or self.feed_is_open
                or self.size_is_open or self.reminders_open):
            return
        self.wave_t = 0.9
        self.brain.say_rand(lines.IDLE_LINES, 3.4)

    def _on_right(self, sx, sy):
        if self.wardrobe is not None and self.wardrobe_is_open:
            self.close_wardrobe()
            return
        self._open_menu()

    def _throw_velocity(self) -> tuple[float, float]:
        if len(self.samples) < 2:
            return 0.0, 0.0
        t0, x0, y0 = self.samples[0]
        t1, x1, y1 = self.samples[-1]
        dt = max(1e-3, t1 - t0)
        vx = (x1 - x0) / dt
        vy = (y1 - y0) / dt
        return max(-2600.0, min(2600.0, vx)), max(-2600.0, min(2600.0, vy))

    def _clamp_drag(self):
        left, top, right, bottom = self.win.work_area()
        bear_l = left - 60
        bear_r = right - sprite.W + 60
        self.x = max(bear_l, min(bear_r, self.x))
        bottom_limit = winlayer.ground_bottom() - sprite.GROUND - 10.0
        min_y = getattr(winlayer, "MIN_Y", None)
        if min_y is not None:
            self.y = max(float(min_y), min(bottom_limit, self.y))
        else:
            self.y = max(top - 40.0, min(bottom_limit, self.y))

    def _open_menu(self):
        self.close_reminders()
        self.close_size()
        self.close_feed()
        self.close_wardrobe()
        self.close_chat()
        if self.menu is None:
            self.menu = Menu(self)
        self.menu_open = True
        self.brain.speech = None
        self.menu.open_at(self.x, self.y)

    def close_menu(self):
        self.menu_open = False
        if self.menu:
            self.menu.hide()

    def open_wardrobe(self):
        self.close_menu()
        self.close_size()
        self.close_reminders()
        if self.wardrobe is None:
            self.wardrobe = wardrobe.Wardrobe(self)
        self.wardrobe_is_open = True
        self.brain.speech = None
        self.wardrobe.open_at(self.x, self.y)

    def close_wardrobe(self):
        self.wardrobe_is_open = False
        if self.wardrobe:
            self.wardrobe.hide()

    def open_feed(self):
        self.close_menu()
        self.close_wardrobe()
        self.close_size()
        self.close_reminders()
        if self.feed_panel is None:
            self.feed_panel = food.FeedPanel(self)
        self.feed_is_open = True
        self.brain.speech = None
        self.feed_panel.open_at(self.x, self.y)

    def close_feed(self):
        self.feed_is_open = False
        if self.feed_panel:
            self.feed_panel.hide()

    def _mouth_point(self) -> tuple[float, float]:
        s = self._draw_scale()
        dx = sprite.CELL_X + (sprite.CELL_W - sprite.CELL_W * s) // 2
        dy = sprite.CELL_Y + (sprite.CELL_H - sprite.CELL_H * s)
        try:
            idx = self.sprites.index_at(self.spr_state, self.spr_ms)
            a = self.sprites.anchors(self.spr_state, idx)
            return dx + a.cx * s, dy + (a.eye_y + 30.0) * s
        except Exception:
            return sprite.W / 2.0, dy + 150.0 * s

    def feed(self, f: "food.Food") -> bool:
        if self.feeding is not None:
            return False
        if self.stats["satiety"] >= 92.0:
            self.brain.say_rand(food.FULL_LINES, 2.4)
            return False
        mx, my = self._mouth_point()
        import random as _r
        self.close_feed()
        self.brain.speech = None
        self.wave_t = 0.9
        self.feeding = {"food": f, "phase": "fall", "t": 0.0,
                        "x": mx, "y": 16.0, "vy": 90.0, "ty": my,
                        "seed": _r.randint(1, 9999)}
        return True

    def _apply_food(self, f: "food.Food"):
        self.stats["satiety"] = min(100.0, self.stats["satiety"] + f.satiety)
        self.stats["weight"] = round(min(120.0, self.stats["weight"] + f.weight), 2)
        self.stats["fed"] = int(self.stats.get("fed", 0)) + 1
        self.brain.say(f.line, 2.6)
        self._save_config()
        if self.feed_panel:
            self.feed_panel.refresh()

    def apply_outfit(self, o: omod.Outfit):
        self.close_menu()
        self._begin_morph(o, dict(self.wear))

    def apply_wear(self, slot: str, item_id: str):
        self.close_menu()
        wear = dict(self.wear)
        if wear.get(slot) == item_id or item_id == "none":
            wear.pop(slot, None)
        else:
            wear[slot] = item_id
        self._begin_morph(self.outfit, wear)

    def _begin_morph(self, new_outfit: omod.Outfit, new_wear: dict):
        if self.morph is not None:
            return
        if new_outfit.id == self.outfit.id and new_wear == self.wear:
            self.brain.say("还是这身", 1.8)
            return
        self.morph = {"from": (self.outfit, dict(self.wear)),
                      "to": (new_outfit, dict(new_wear)), "t": 0.0}
        self.brain.say_rand(lines.OUTFIT_LINES, 2.4)
        self.wave_t = 0.9

    def _finish_morph(self):
        to_outfit, to_wear = self.morph["to"]
        self.morph = None
        self.outfit = to_outfit
        self.wear = dict(to_wear)
        if self.sprites is not None:
            self.sprites.set_outfit(to_outfit)
            self.sprites.wear = dict(to_wear)
        self._save_outfit()

    def _load_outfit(self) -> omod.Outfit:
        cfg = self._load_config()
        got = omod.BY_ID.get(cfg.get("outfit", ""))
        return got if got is not None else omod.DEFAULT

    def _load_wear(self) -> dict:
        cfg = self._load_config()
        wear = cfg.get("wear") or {}
        if not isinstance(wear, dict):
            return {}
        valid = {i.id for i in garment.ITEMS}
        return {k: v for k, v in wear.items() if v in valid and v != "none"}

    def _load_config(self) -> dict:
        try:
            import json
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_stats(self) -> dict:
        cfg = self._load_config().get("stats")
        base = {"satiety": 62.0, "weight": 50.0, "fed": 0}
        if isinstance(cfg, dict):
            for k in base:
                if isinstance(cfg.get(k), (int, float)):
                    base[k] = float(cfg[k])
        return base

    def _save_config(self):
        try:
            import json
            tmp = CONFIG_PATH + ".tmp"
            data = self._load_config()
            data.update({"outfit": self.outfit.id, "wear": self.wear,
                         "stats": self.stats, "size": self.size_scale,
                         "quiet": list(self.quiet), "quiet_on": self.quiet_on,
                         "remote": {"url": self.remote_url, "token": self.remote_token}})
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, CONFIG_PATH)
        except Exception as exc:
            _log(f"save config failed: {exc}")

    def _save_outfit(self):
        self._save_config()

    def set_llm_config(self, cfg: dict):
        try:
            import json
            data = self._load_config()
            data["llm"] = cfg
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, CONFIG_PATH)
        except Exception as exc:
            _log(f"save llm config failed: {exc}")

    def reload_remote(self):
        cfg = self._load_config().get("remote") or {}
        url = str(cfg.get("url", "") or "").strip()
        tok = str(cfg.get("token", "") or "").strip()
        if url == self.remote_url and tok == self.remote_token:
            return
        if self.remote is not None:
            self.remote.stop()
        self.remote_url, self.remote_token = url, tok
        self.remote = None
        if url and tok:
            self.remote = remote.RemoteClient(url, tok, REMOTE_STATE_PATH)
            self.remote.start()
        self._save_config()

    def _tick_feed(self, dt: float):
        self.stats["satiety"] = max(0.0, self.stats["satiety"] - 0.09 * dt)

        self._hungry_next -= dt
        if self._hungry_next <= 0.0:
            self._hungry_next = 55.0
            if self.stats["satiety"] < 25.0 and self.feeding is None and not self.brain.speech:
                self.brain.say_rand(food.HUNGRY_LINES, 2.8)

        fd = self.feeding
        if fd is None:
            return
        fd["t"] += dt
        if fd["phase"] == "fall":
            fd["vy"] += 2200.0 * dt
            fd["y"] += fd["vy"] * dt
            if fd["y"] >= fd["ty"]:
                fd["y"] = fd["ty"]
                fd["phase"] = "eat"
                fd["t"] = 0.0
        elif fd["phase"] == "eat":
            if fd["t"] >= 0.85:
                fd["phase"] = "happy"
                fd["t"] = 0.0
                self._apply_food(fd["food"])
                if fd["food"].id in ("coffee", "burger"):
                    self.brain.force(fd["food"].id)
        elif fd["t"] >= 0.8:
            self.feeding = None

    def _ride_scale(self) -> float:
        return max(0.6, self.size_scale)

    def _ride_offset(self):
        fig = pixelfig.render(self._ride_scale())
        dx = (sprite.W - fig.width) // 2
        dy = 112
        return fig, dx + int(fig.width * 0.60), dy + int(fig.height * 0.86)

    def _start_climb(self):
        self.climb = {"t": 0.0, "x": self.x, "y": self.y}
        self.brain.say_rand(lines.CLIMB_LINES, 2.2)

    def start_riding(self):
        self.riding = True
        self.climb = None
        self.pressed = False
        self.dragging = False
        self.brain.say_rand(lines.RIDE_LINES, 2.4)

    def stop_riding(self, thrown: bool):
        if not self.riding:
            return
        self.riding = False
        self.on_ground = False
        self.vy = -240.0 if thrown else -120.0
        self.vx = max(-900.0, min(900.0, self._cursor_speed * 0.25))
        self.brain.say_rand(lines.THROWN_LINES, 2.0)

    def _tick_cursor(self, dt: float):
        cx, cy = winlayer.cursor_pos()
        if self._cursor_last is None:
            self._cursor_last = (cx, cy)
            return
        dx, dy = cx - self._cursor_last[0], cy - self._cursor_last[1]
        self._cursor_last = (cx, cy)
        moved = (dx * dx + dy * dy) ** 0.5
        self._cursor_speed = moved / max(dt, 1e-3)
        self._cursor_idle = self._cursor_idle + dt if moved < 0.6 else 0.0

        if self.riding:
            fig, ox, oy = self._ride_offset()
            self.x = cx - ox
            self.y = cy - oy
            self._clamp_drag()
            if self._cursor_speed > 1500.0 or moved > 45.0:
                self.stop_riding(thrown=True)
            return

        if self.climb is not None:
            c = self.climb
            c["t"] += dt / 0.9
            k = min(1.0, c["t"])
            ease = k * k * (3 - 2 * k)
            fig, ox, oy = self._ride_offset()
            self.x = c["x"] + (cx - ox - c["x"]) * ease
            self.y = c["y"] + (cy - oy - c["y"]) * ease
            if k >= 1.0:
                self.start_riding()
            return

        busy = (self.dragging or self.morph is not None or self.menu_open
                or self.wardrobe_is_open or self.feed_is_open or self.size_is_open
                or self.reminders_open or self.editor_open)
        if self._cursor_idle >= 10.0 and self.on_ground and not busy:
            self._start_climb()

    def open_reminders(self):
        self.close_menu()
        self.close_wardrobe()
        self.close_feed()
        self.close_size()
        if self.remind_panel is None:
            self.remind_panel = remind_ui.ReminderPanel(self)
        self.reminders_open = True
        self.brain.speech = None
        self.remind_panel.open_at(self.x, self.y)

    def close_reminders(self):
        self.reminders_open = False
        if self.remind_panel:
            self.remind_panel.hide()

    def open_editor(self):
        if self.editor is None:
            self.editor = editor.ReminderEditor(self)
        self.editor_open = True
        self.editor.open(self.x + sprite.W / 2 - 196, self.y - 262)
        self.close_reminders()

    def close_editor(self):
        self.editor_open = False
        if self.editor:
            self.editor.close()

    def open_chat(self):
        self.close_menu()
        self.close_wardrobe()
        self.close_feed()
        self.close_size()
        self.close_reminders()
        if self.chat_window is None:
            self.chat_window = chat_ui.ChatWindow(self)
        self.chat_open = True
        self.brain.speech = None
        self.chat_window.open(self.x + sprite.W / 2 - 200, self.y - 300)

    def close_chat(self):
        self.chat_open = False
        if self.chat_window:
            self.chat_window.close()

    def toggle_quiet(self):
        self.quiet_on = not self.quiet_on
        self.store.quiet = self.quiet if self.quiet_on else ("00:00", "00:00")
        self._save_config()
        self.brain.say("静音开着，等你醒了再说" if self.quiet_on else "不静音了，随时喊你", 2.4)

    def deliver_reminder(self, r: "reminder.Reminder"):
        text = r.text
        late = time.time() - r.due
        if late > 900:
            text = f"（补一句）{text}"
        self.brain.say(text, 9.0, priority=True)
        self.wave_t = 1.2
        self._chime()
        self.win.raise_topmost()
        _log(f"deliver reminder #{r.id} {r.text!r}")
        if self.remind_panel is not None:
            self.remind_panel.refresh()

    def test_reminder(self):
        r = reminder.Reminder(id=-1, text="测试提醒：该喝水了", due=time.time(), source="local")
        self.deliver_reminder(r)

    def _chime(self):
        def go():
            try:
                if os.name == "nt":
                    import winsound
                    for f, d in ((988, 90), (1319, 130)):
                        winsound.Beep(f, d)
                    return
                import struct
                import subprocess
                import tempfile
                import wave
                path = os.path.join(tempfile.gettempdir(), "bearpet_chime.wav")
                if not os.path.exists(path):
                    rate = 22050
                    with wave.open(path, "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(rate)
                        frames = bytearray()
                        for freq, dur in ((988, 0.09), (0, 0.02), (1319, 0.13)):
                            for i in range(int(rate * dur)):
                                v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
                                frames.extend(struct.pack("<h", v))
                        w.writeframes(bytes(frames))
                subprocess.run(["afplay", path], check=False, timeout=3)
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()

    def _tick_reminders(self, dt: float):
        now = time.time()
        if self.remote is not None:
            for msg in self.remote.drain():
                r = self.store.add_from_remote(msg, now)
                _log(f"remote in #{msg.get('id')} -> due {time.strftime('%m-%d %H:%M', time.localtime(r.due))}")
                if self.remind_panel is not None:
                    self.remind_panel.refresh()
        for r in self.store.pop_due(now):
            self.deliver_reminder(r)

    def update(self, dt: float):
        self.brain.tick(dt)
        self.advance_animation(dt)
        now = time.perf_counter()
        if getattr(self, "_last_state", None) != self.brain.state:
            self._last_state = self.brain.state
            _log(f"state={self.brain.state} pos=({self.x:.0f},{self.y:.0f}) "
                 f"ground={self.y_ground:.0f} vy={self.vy:.0f} energy={self.brain.energy:.2f}")

        self._tick_feed(dt)
        self._tick_reminders(dt)
        self._tick_cursor(dt)

        lbtn = winlayer.left_button_down()
        if lbtn and not self._prev_lbtn:
            cx, cy = winlayer.cursor_pos()
            if self.reminders_open:
                if not (self.remind_panel and self.remind_panel.hit(cx, cy)):
                    self.close_reminders()
            elif self.size_is_open:
                if not (self.size_panel and self.size_panel.hit(cx, cy)):
                    self.close_size()
            elif self.feed_is_open:
                if not (self.feed_panel and self.feed_panel.hit(cx, cy)):
                    self.close_feed()
            elif self.wardrobe_is_open:
                if not (self.wardrobe and self.wardrobe.hit(cx, cy)):
                    self.close_wardrobe()
            elif self.menu_open:
                if not (self.menu and self.menu.hit(cx, cy)):
                    self.close_menu()
        self._prev_lbtn = lbtn

        if self.morph is not None:
            self.morph["t"] += dt / fx.DURATION
            if self.morph["t"] >= 1.0:
                self._finish_morph()

        if now - self._last_raise > 4.0 and not self.editor_open:
            self.win.raise_topmost()
            self._last_raise = now

        if getattr(winlayer, "NO_TOP_LIMIT", False) and self.y < -sprite.H:
            if getattr(self, "_offscreen_since", None) is None:
                self._offscreen_since = now
            elif now - self._offscreen_since > 1.5:
                self.y = -40.0
                self.vy = 0.0
                self.on_ground = False
                self.dragging = False
                self.pressed = False
                self._offscreen_since = None
        else:
            self._offscreen_since = None

        if self.dragging:
            return

        if not self.on_ground:
            self._physics(dt)
        else:
            if self.brain.state == "walk":
                self.x += self.brain.dir * self.brain.speed * dt
                self._check_walls()
            elif self.brain.state == "hop" and self.brain.t < 0.05:
                _log(f"hop start y={self.y:.0f} ground={self.y_ground:.0f}")
                self.vy = -560.0
                self.on_ground = False

    def _physics(self, dt: float):
        self.vy = min(MAX_FALL, self.vy + GRAVITY * dt)
        self.y += self.vy * dt
        self.x += self.vx * dt
        self.vx *= max(0.0, 1.0 - 1.4 * dt)
        if self.y < -10000.0:
            self.y = -10000.0
            self.vy = 0.0
        self._recheck_ground()
        if self.y >= self.y_ground:
            impact = self.vy
            _log(f"land impact={impact:.0f} y={self.y:.0f} ground={self.y_ground:.0f} hard={impact > HARD_LAND}")
            self.y = self.y_ground
            self.vx = self.vy = 0.0
            self.on_ground = True
            self.brain.notify_landed(hard=impact > HARD_LAND)
        self._check_walls()

    def _recheck_ground(self):
        self.y_ground = float(winlayer.ground_bottom() - 1 - sprite.GROUND)

    def _check_walls(self):
        left, top, right, bottom = self.win.work_area()
        margin = sprite.W / 2.0 - 56.0
        xmin = left - margin
        xmax = right - sprite.W + margin
        if self.x < xmin:
            self.x = xmin
            if self.brain.state == "walk" and self.brain.dir < 0:
                self.brain.notify_wall()
        elif self.x > xmax:
            self.x = xmax
            if self.brain.state == "walk" and self.brain.dir > 0:
                self.brain.notify_wall()

    def _cursor_look_state(self) -> str | None:
        if self.sprites is None or not getattr(self.sprites, "has_v2", False):
            return None
        if self.brain.blink < 0.72:
            return None
        try:
            cx, cy = winlayer.cursor_pos()
        except Exception:
            return None
        bx = self.x + sprite.W / 2.0
        by = self.y + sprite.GROUND - 110.0
        dx = cx - bx
        dy = cy - by
        dist = (dx * dx + dy * dy) ** 0.5
        enter_r = 46.0 if self._look_active else 62.0
        if dist < enter_r or dist > 980.0:
            self._look_active = False
            self._look_dir = None
            return None
        self._look_active = True
        ang = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0
        step = 22.5
        cand = int((ang + step / 2.0) // step) % 16
        prev = self._look_dir
        if prev is not None and prev != cand:
            prev_ang = prev * step
            diff = abs((ang - prev_ang + 180.0) % 360.0 - 180.0)
            if diff < 14.5:
                cand = prev
        self._look_dir = cand
        return f"look-{cand}"

    def sprite_state(self) -> str:
        b = self.brain
        if self.dragging:
            return "jumping"
        if not self.on_ground:
            return "jumping"
        if self.wave_t > 0.0:
            return "waving"
        if self.feeding is not None and self.feeding.get("phase") == "eat":
            fid = self.feeding["food"].id
            if fid in ("coffee", "burger"):
                return fid
        st = b.state
        if st == "walk":
            return "running-right" if b.dir > 0 else "running-left"
        if st == "sit":
            if getattr(b, "work_frustrated", False):
                return "typing-frustrated"
            return getattr(b, "work_variant", "typing-calm")
        if st in ("coffee", "burger"):
            return st
        if st == "sleep":
            return "sleep"
        if st in ("sigh", "dizzy"):
            return "failed"
        if st == "hop":
            return "jumping"
        if st == "wave":
            return "waving"
        if st == "think":
            return "review"
        look = self._cursor_look_state()
        if look is not None:
            return look
        return "idle"

    def advance_animation(self, dt: float):
        st = self.sprite_state()
        if st != self.spr_state:
            self.spr_state = st
            self.spr_ms = 0.0
        else:
            self.spr_ms += dt * 1000.0
        if self.wave_t > 0.0:
            self.wave_t = max(0.0, self.wave_t - dt)

    def pose(self) -> art.Pose:
        b = self.brain
        st = b.state
        t = b.t
        p = art.Pose()
        p.blink = b.blink
        p.tuft = (time.perf_counter() - self._t0) * 1.9

        if self.dragging:
            n = time.perf_counter()
            p.eye = "wide"
            p.arm_spread = 0.92
            p.mouth = "open"
            p.mouth_open = 0.95
            p.sweat = 1.0
            p.shadow = 0.0
            p.tilt = math.sin(n * 11.0) * 7.0
            p.head_tilt = -6.0 + math.sin(n * 9.0) * 5.0
            p.leg_phase = n * 7.0
            p.walking = True
            return p

        if not self.on_ground:
            dramatic = abs(self.vy) > 240.0
            p.eye = "wide" if dramatic else "open"
            p.arm_spread = 1.0 if dramatic else 0.45
            p.mouth = "open" if dramatic else "flat"
            p.mouth_open = 1.0 if dramatic else 0.2
            p.leg_phase = t * 9.0
            p.walking = True
            p.tilt = max(-12.0, min(12.0, -self.vx * 0.006))
            p.shadow = max(0.0, 1.0 - (self.y_ground - self.y) / 220.0)
            p.sweat = 0.0
            return p

        if st == "walk":
            p.walking = True
            p.leg_phase = t * 8.8
            p.bob = -abs(math.sin(t * 8.8)) * 2.4
            p.arm_swing = 1.0
            p.eye = "open"
            p.mouth = "flat"
            p.head_tilt = -3.0 + math.sin(t * 4.4) * 1.5
            p.tilt = b.dir * 2.2
        elif st == "sit":
            p.sit = True
            p.squash = 1.04
            p.head_bob = 1.6 + math.sin(t * 1.6) * 0.9
            p.eye = "half"
            p.mouth = "flat"
            p.head_tilt = -4.0
            p.bob = 1.0
        elif st == "sleep":
            p.eye = "closed"
            p.mouth = "wave"
            p.squash = 1.0 + 0.035 * math.sin(t * 1.45)
            p.head_bob = 3.0 + math.sin(t * 1.45) * 1.6
            p.head_tilt = -9.0
            p.zzz = (t * 0.30) % 1.0
            p.bob = 2.0
        elif st == "sigh":
            p.eye = "half"
            p.mouth = "open"
            p.mouth_open = 0.35 + 0.35 * abs(math.sin(t * 7.0))
            p.sweat = 0.85
            p.head_bob = 2.2
            p.bob = 1.6
            p.head_tilt = -7.0
        elif st == "dizzy":
            p.eye = "x"
            p.mouth = "frown"
            p.tilt = math.sin(t * 13.0) * 8.0
            p.head_tilt = -10.0 + math.sin(t * 10.0) * 6.0
            p.sweat = 0.7
        elif st == "hop":
            p.eye = "open"
            p.mouth = "open"
            p.mouth_open = 0.6
            p.leg_phase = t * 6.0
        else:
            p.bob = math.sin(t * 2.1) * 1.1
            p.squash = 1.0 + 0.014 * math.sin(t * 2.1 - 0.5)
            p.head_tilt = -1.5 + math.sin(t * 0.8) * 1.5
            p.eye = "open"
            p.mouth = "flat"
            self._look_at_cursor(p)

        return p

    def _look_at_cursor(self, p: art.Pose):
        cx, cy = winlayer.cursor_pos()
        bx = self.x + sprite.W / 2.0
        by = self.y + sprite.GROUND - 120.0
        dx = (cx - bx) / 280.0
        dy = (cy - by) / 240.0
        if abs(dx) < 1.0 and abs(dy) < 1.2:
            p.eye_dx = max(-1.0, min(1.0, dx))
            p.eye_dy = max(-1.0, min(1.0, dy)) * 0.7

    def draw(self):
        if self.riding or self.climb is not None:
            img = Image.new("RGBA", (sprite.W, sprite.H), (0, 0, 0, 0))
            fig, ox, oy = self._ride_offset()
            img.alpha_composite(fig, (ox - int(fig.width * 0.60), oy - int(fig.height * 0.86)))
            if self.brain.speech:
                img = art.draw_bubble(img, self.brain.speech, self.brain.speech_alpha(),
                                      bottom=58)
            self.win.blit(img, int(round(self.x)), int(round(self.y)))
            return
        shadow = self._shadow_factor()
        scale = self._draw_scale()
        if self.sprites is not None:
            if self.morph is not None:
                (fo, fw), (to_o, tw) = self.morph["from"], self.morph["to"]
                a = self.sprites.render(self.spr_state, self.spr_ms, shadow,
                                        outfit=fo, wear=fw, scale=scale)
                b = self.sprites.render(self.spr_state, self.spr_ms, shadow,
                                        outfit=to_o, wear=tw, scale=scale)
                img = fx.render_morph(a, b, self.morph["t"], to_o.spark)
            else:
                img = self.sprites.render(self.spr_state, self.spr_ms, shadow, scale=scale)
        else:
            img = art.render_bear(self.pose())
        if self.feeding is not None:
            img = food.render_overlay(img, self.feeding, None)
        if self.brain.speech:
            img = art.draw_bubble(img, self.brain.speech, self.brain.speech_alpha(),
                                  bottom=self._bubble_bottom())
        self.win.blit(img, int(round(self.x)), int(round(self.y)))

    def _body_scale(self) -> float:
        return max(0.94, min(1.10, 1.0 + (self.stats.get("weight", 50.0) - 50.0) * 0.0012))

    def _draw_scale(self) -> float:
        return self._body_scale() * self.size_scale

    def _bubble_bottom(self) -> float:
        s = self._draw_scale()
        return BUBBLE_BOTTOM + (1.0 - s) * (sprite.CELL_H - 5.0)

    def open_size(self):
        self.close_menu()
        self.close_wardrobe()
        self.close_feed()
        self.close_reminders()
        if self.size_panel is None:
            self.size_panel = sizemod.SizePanel(self)
        self.size_is_open = True
        self.brain.speech = None
        self.size_panel.open_at(self.x, self.y)

    def close_size(self):
        self.size_is_open = False
        if self.size_panel:
            self.size_panel.hide()

    def set_size(self, v: float):
        self.size_scale = sizemod.clamp(v)
        self.close_size()
        self._save_config()
        if self.on_ground and not self.dragging:
            self.y = float(winlayer.ground_bottom() - 1 - sprite.GROUND)
        self.brain.say(f"{int(round(self.size_scale * 100))}% 的我，也还是我", 2.4)

    def _shadow_factor(self) -> float:
        if self.dragging:
            return 0.0
        if self.on_ground:
            return 1.0
        return max(0.25, 1.0 - (self.y_ground - self.y) / 260.0)

    def run(self):
        if getattr(winlayer, "NATIVE_RUN_LOOP", False):
            winlayer.run_forever(self)
            return
        last = time.perf_counter()
        budget = 1.0 / FPS
        while self.running and self.win.alive:
            t_start = time.perf_counter()
            if not self.win.pump():
                break
            now = time.perf_counter()
            dt = min(0.05, now - last)
            last = now
            self.update(dt)
            self.draw()
            self._frame += 1
            spent = time.perf_counter() - t_start
            if spent < budget:
                time.sleep(budget - spent)
        self.shutdown()

    def shutdown(self):
        if self.menu:
            self.menu.destroy()
        if self.wardrobe:
            self.wardrobe.destroy()
        if self.feed_panel:
            self.feed_panel.destroy()
        if self.size_panel:
            self.size_panel.destroy()
        if self.remind_panel:
            self.remind_panel.destroy()
        if self.editor:
            self.editor.destroy()
        if self.chat_window:
            self.chat_window.destroy()
        if self.remote is not None:
            self.remote.stop()
        self.win.destroy()
        self.running = False


class Menu:

    ITEMS = (("说句话", "say"), ("聊聊", "chat"), ("敲会儿键盘", "work"),
             ("躺一会儿", "sleep"), ("投喂", "feed"), ("换装", "dress"),
             ("大小", "size"), ("提醒", "remind"), ("退出", "quit"))
    W = 150
    ROW = 36
    PAD = 8

    def __init__(self, pet: BearPet):
        self.pet = pet
        self.h = self.PAD * 2 + self.ROW * len(self.ITEMS)
        self.win = winlayer.LayeredWindow(self.W, self.h, "bearpet-menu", auto_show=False)
        self.win.on_move = self.hover_at
        self.win.on_left_up = self._on_up
        self.hover = -1
        self.font = art._font(15)
        self.small = art._font(13)
        self._render()

    def _render(self):
        img = Image.new("RGBA", (self.W, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.W - 1, self.h - 1], radius=13,
                            fill=(253, 251, 246, 240), outline=art.OUTLINE, width=2)
        for i, (label, _) in enumerate(self.ITEMS):
            y0 = self.PAD + i * self.ROW
            if i == self.hover:
                d.rounded_rectangle([5, y0 + 2, self.W - 6, y0 + self.ROW - 2], radius=9,
                                    fill=(238, 226, 206, 255))
            color = (58, 40, 26, 255) if i != self.hover else (36, 22, 12, 255)
            d.text((18, y0 + self.ROW / 2 - 11), label, font=self.font, fill=color)
        self.image = img

    def open_at(self, bear_x: float, bear_y: float):
        left, top, right, bottom = winlayer.work_area(self.win.hwnd)
        x = bear_x + sprite.W / 2 - self.W / 2
        y = bear_y + 122 - self.h
        x = max(left + 8, min(right - self.W - 8, x))
        y = max(top + 8, min(bottom - self.h - 8, y))
        self.win.show()
        self.win.blit(self.image, int(x), int(y))
        self.win.raise_topmost()
        self.hover = -1

    def hide(self):
        self.win.hide()

    def hit(self, sx: int, sy: int) -> bool:
        return (self.win.x <= sx < self.win.x + self.W and
                self.win.y <= sy < self.win.y + self.h)

    def _index_at(self, sx: int, sy: int) -> int:
        if not self.hit(sx, sy):
            return -1
        i = int((sy - self.win.y - self.PAD) // self.ROW)
        return i if 0 <= i < len(self.ITEMS) else -1

    def hover_at(self, sx, sy):
        i = self._index_at(sx, sy)
        if i != self.hover:
            self.hover = i
            self._render()
            self.win.blit(self.image)

    def _on_up(self, sx, sy):
        i = self._index_at(sx, sy)
        self.pet.close_menu()
        if i < 0:
            return
        action = self.ITEMS[i][1]
        pet = self.pet
        if action == "say":
            pet.brain.say_rand(lines.IDLE_LINES, 3.6)
        elif action == "chat":
            pet.open_chat()
            return
        elif action == "sleep":
            pet.brain.force("sleep")
        elif action == "work":
            pet.brain.force("sit")
        elif action == "dress":
            pet.open_wardrobe()
            return
        elif action == "feed":
            pet.open_feed()
            return
        elif action == "size":
            pet.open_size()
            return
        elif action == "remind":
            pet.open_reminders()
            return
        elif action == "quit":
            pet.running = False

    def destroy(self):
        self.win.destroy()


def main():
    pet = BearPet()
    try:
        pet.run()
    except KeyboardInterrupt:
        pet.shutdown()


if __name__ == "__main__":
    main()
