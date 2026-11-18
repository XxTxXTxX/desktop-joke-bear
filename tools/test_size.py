from __future__ import annotations

import ctypes
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".deps"))
sys.path.insert(0, BASE)

from PIL import ImageGrab

from bearpet import app, size as sizemod, sprite, winlayer as W

OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "size_test.log")
open(LOG, "w", encoding="utf-8").close()


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.perf_counter():8.3f}  {m}\n")
    print(m, flush=True)


def lp(x, y):
    return (y << 16) | (x & 0xFFFF)


def post(h, msg, wp=0, l=0):
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(h), msg, wp, l)


def cur(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


class H:
    def __init__(self):
        self.pet = app.BearPet()
        self.last = time.perf_counter()
        self.n = 0

    def step(self, sec=0.0):
        end = time.perf_counter() + sec
        while True:
            self.pet.win.pump()
            now = time.perf_counter()
            self.pet.update(min(0.05, now - self.last))
            self.last = now
            self.pet.draw()
            time.sleep(0.006)
            if time.perf_counter() >= end:
                break

    def shot(self, tag, pad=30):
        p = self.pet
        box = (max(0, int(p.x) - pad), max(0, int(p.y) - pad),
               min(1920, int(p.x) + sprite.W + pad), min(1080, int(p.y) + sprite.H + pad))
        path = os.path.join(OUT, f"s_{self.n:02d}_{tag}.png")
        ImageGrab.grab(bbox=box).save(path)
        self.n += 1
        log(f"shot {os.path.basename(path)} size={p.size_scale:.2f} "
            f"draw={p._draw_scale():.3f} bubble_bottom={p._bubble_bottom():.1f}")
        return path

    def click(self, hwnd, wx, wy):
        cur(wx, wy)
        post(hwnd, W.WM_MOUSEMOVE, 1, lp(8, 8))
        self.step(0.12)
        post(hwnd, W.WM_LBUTTONDOWN, 1, lp(8, 8))
        post(hwnd, W.WM_LBUTTONUP, 0, lp(8, 8))
        self.step(0.12)


def main() -> int:
    h = H()
    pet = h.pet
    h.step(0.6)
    log(f"start size={pet.size_scale}")

    ui = [i for i, (_, a) in enumerate(app.Menu.ITEMS) if a == "size"][0]
    cur(pet.x + sprite.W / 2, pet.y + sprite.GROUND - 90)
    post(pet.win.hwnd, W.WM_RBUTTONUP)
    h.step(0.35)
    mx = pet.menu.win.x + pet.menu.W / 2
    my = pet.menu.win.y + pet.menu.PAD + ui * pet.menu.ROW + pet.menu.ROW / 2
    h.click(pet.menu.win.hwnd, mx, my)
    h.step(0.3)
    log(f"size panel open={pet.size_is_open} size={pet.size_panel.W}x{pet.size_panel.H}")
    h.shot("panel")

    panel = pet.size_panel
    for idx, want in ((4, 1.30), (0, 0.70), (2, 1.00)):
        if not pet.size_is_open:
            pet.brain.force("idle")
            pet.brain.speed = 0.0
            pet.open_size()
            h.step(0.2)
        cx = panel.win.x + panel.PAD + idx * panel.CELL_W + panel.CELL_W / 2
        cy = panel.win.y + panel.PAD + panel.HEADER + panel.CELL_H / 2
        h.click(panel.win.hwnd, cx, cy)
        h.step(0.25)
        log(f"click {sizemod.LABELS[idx]}: size_scale={pet.size_scale:.2f} "
            f"open={pet.size_is_open} speech={pet.brain.speech!r}")
        assert abs(pet.size_scale - want) < 0.01, f"档位不匹配 {pet.size_scale} != {want}"
        assert pet.size_is_open is False, "选完档位面板应关闭"
        h.shot(f"size_{int(want*100)}")

    pet.set_size(1.30)
    h.step(0.2)
    mx_, my_ = pet._mouth_point()
    idx = pet.sprites.index_at(pet.spr_state, pet.spr_ms)
    a = pet.sprites.anchors(pet.spr_state, idx)
    s = pet._draw_scale()
    dx = sprite.CELL_X + (sprite.CELL_W - sprite.CELL_W * s) // 2
    dy = sprite.CELL_Y + (sprite.CELL_H - sprite.CELL_H * s)
    log(f"mouth at 130%: ({mx_:.1f},{my_:.1f}) expect "
        f"({dx + a.cx*s:.1f},{dy + (a.eye_y+30)*s:.1f})")
    pet.stats["satiety"] = 40.0
    pet.feed(app.food.BY_ID["rice"])
    h.step(0.45)
    h.shot("feed_at_130")
    while pet.feeding is not None:
        h.step(0.01)
    h.step(0.2)
    h.shot("fed_at_130")

    pet.set_size(1.00)
    h.step(0.2)

    cfg = os.path.join(BASE, ".bear.json")
    data = json.load(open(cfg, encoding="utf-8"))
    log("config=" + json.dumps(data, ensure_ascii=False))

    pet.shutdown()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
