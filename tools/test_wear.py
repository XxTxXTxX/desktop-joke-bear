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

from bearpet import app, garment, outfit as omod, sprite, winlayer as W

OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "wear_test.log")
open(LOG, "w", encoding="utf-8").close()


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.perf_counter():8.3f}  {m}\n")
    print(m, flush=True)


def lparam(x, y):
    return (y << 16) | (x & 0xFFFF)


def post(h, msg, wp=0, lp=0):
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(h), msg, wp, lp)


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

    def shot(self, tag, pad=26):
        p = self.pet
        box = (max(0, int(p.x) - pad), max(0, int(p.y) - pad),
               min(1920, int(p.x) + sprite.W + pad), min(1080, int(p.y) + sprite.H + pad))
        path = os.path.join(OUT, f"v_{self.n:02d}_{tag}.png")
        ImageGrab.grab(bbox=box).save(path)
        self.n += 1
        log(f"shot {os.path.basename(path)} wear={p.wear} morph="
            f"{None if p.morph is None else round(p.morph['t'], 2)}")
        return path

    def click(self, hwnd, wx, wy):
        cur(wx, wy)
        post(hwnd, W.WM_MOUSEMOVE, 1, lparam(10, 10))
        self.step(0.12)
        post(hwnd, W.WM_LBUTTONDOWN, 1, lparam(10, 10))
        post(hwnd, W.WM_LBUTTONUP, 0, lparam(10, 10))
        self.step(0.12)

    def settle(self):
        while self.pet.morph is not None:
            self.step(0.01)
        self.step(0.25)


def main() -> int:
    h = H()
    pet = h.pet
    hwnd = pet.win.hwnd
    h.step(0.6)
    log(f"start outfit={pet.outfit.id} wear={pet.wear}")

    cur(pet.x + sprite.W / 2, pet.y + sprite.GROUND - 90)
    post(hwnd, W.WM_RBUTTONUP)
    h.step(0.35)
    mi = [i for i, (_, act) in enumerate(app.Menu.ITEMS) if act == "dress"][0]
    mx = pet.menu.win.x + pet.menu.W / 2
    my = pet.menu.win.y + pet.menu.PAD + mi * pet.menu.ROW + pet.menu.ROW / 2
    h.click(pet.menu.win.hwnd, mx, my)
    h.step(0.3)
    log(f"wardrobe open={pet.wardrobe_is_open} size={pet.wardrobe.W}x{pet.wardrobe.H}")
    h.shot("wardrobe")

    w = pet.wardrobe

    def cell_center(row, col):
        x, y = w._cell_box(row, col)
        return w.win.x + x + w.CELL_W / 2, w.win.y + y + w.CELL_H / 2

    cx, cy = cell_center(1, 0)
    h.click(w.win.hwnd, cx, cy)
    h.shot("morph_hat")
    h.settle()
    log(f"after hat: wear={pet.wear}")
    h.shot("hat")

    cx, cy = cell_center(1, 2)
    h.click(w.win.hwnd, cx, cy)
    h.settle()
    log(f"after scarf: wear={pet.wear}")

    cx, cy = cell_center(1, 3)
    h.click(w.win.hwnd, cx, cy)
    h.settle()
    log(f"after hoodie: wear={pet.wear}")
    w.open_at(pet.x, pet.y)
    h.step(0.2)
    h.shot("dressed")

    sx, sy = w._swatch_box(5)
    h.click(w.win.hwnd, w.win.x + sx + 13, w.win.y + sy + 13)
    h.settle()
    log(f"after palette: outfit={pet.outfit.id} wear={pet.wear}")
    h.shot("cyber_dressed")

    cx, cy = cell_center(1, 0)
    h.click(w.win.hwnd, cx, cy)
    h.settle()
    log(f"after toggle off: wear={pet.wear}")

    cfg = os.path.join(BASE, ".bear.json")
    log("config=" + (open(cfg, encoding="utf-8").read() if os.path.exists(cfg) else "MISSING"))

    pet.brain.force("walk")
    pet.brain.dir = 1
    for i in range(6):
        h.step(0.09)
        h.shot(f"walk{i}")

    t0 = time.perf_counter()
    for i in range(30):
        pet.sprites.render("running-right", i * 40)
    log(f"render+wear ms/frame={(time.perf_counter()-t0)/30*1000:.2f}")

    pet.shutdown()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
