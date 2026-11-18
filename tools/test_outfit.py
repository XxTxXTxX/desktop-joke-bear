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

from bearpet import app, fx, outfit as omod, sprite, winlayer as W

OUT = os.path.join(BASE, "preview")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "outfit_test.log")
open(LOG, "w", encoding="utf-8").close()


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.perf_counter():8.3f}  {msg}\n")
    print(msg, flush=True)


def lparam(x, y):
    return (y << 16) | (x & 0xFFFF)


def post(hwnd, msg, wp=0, lp=0):
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), msg, wp, lp)


def set_cursor(x, y):
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
            dt = min(0.05, now - self.last)
            self.last = now
            self.pet.update(dt)
            self.pet.draw()
            time.sleep(0.006)
            if time.perf_counter() >= end:
                break

    def shot(self, tag, pad=30):
        p = self.pet
        box = (max(0, int(p.x) - pad), max(0, int(p.y) - pad),
               min(1920, int(p.x) + sprite.W + pad), min(1080, int(p.y) + sprite.H + pad))
        path = os.path.join(OUT, f"w_{self.n:02d}_{tag}.png")
        ImageGrab.grab(bbox=box).save(path)
        self.n += 1
        log(f"shot {os.path.basename(path)}  outfit={p.outfit.id} morph="
            f"{None if p.morph is None else round(p.morph['t'], 2)}")
        return path


def main() -> int:
    h = H()
    pet = h.pet
    hwnd = pet.win.hwnd
    h.step(0.6)
    log(f"start outfit={pet.outfit.id}")
    h.shot("start")

    set_cursor(pet.x + sprite.W / 2, pet.y + sprite.GROUND - 90)
    post(hwnd, W.WM_RBUTTONUP)
    h.step(0.35)
    log(f"menu_open={pet.menu_open} items={len(app.Menu.ITEMS)}")
    h.shot("menu")

    mi = 3
    mx = pet.menu.win.x + pet.menu.W / 2
    my = pet.menu.win.y + pet.menu.PAD + mi * pet.menu.ROW + pet.menu.ROW / 2
    set_cursor(mx, my)
    post(pet.menu.win.hwnd, W.WM_MOUSEMOVE, 1, lparam(80, int(my - pet.menu.win.y)))
    h.step(0.15)
    post(pet.menu.win.hwnd, W.WM_LBUTTONDOWN, 1, lparam(80, int(my - pet.menu.win.y)))
    post(pet.menu.win.hwnd, W.WM_LBUTTONUP, 0, lparam(80, int(my - pet.menu.win.y)))
    h.step(0.4)
    log(f"after click: wardrobe_open={pet.wardrobe_is_open} menu_open={pet.menu_open}")
    h.shot("wardrobe")

    wi = 5
    wx = pet.wardrobe.win.x + pet.wardrobe.W / 2
    wy = pet.wardrobe.win.y + pet.wardrobe.PAD + 12 + wi * pet.wardrobe.ROW + pet.wardrobe.ROW / 2
    set_cursor(wx, wy)
    post(pet.wardrobe.win.hwnd, W.WM_MOUSEMOVE, 1, lparam(60, int(wy - pet.wardrobe.win.y)))
    h.step(0.15)
    h.shot("hover")
    post(pet.wardrobe.win.hwnd, W.WM_LBUTTONDOWN, 1, lparam(60, int(wy - pet.wardrobe.win.y)))
    post(pet.wardrobe.win.hwnd, W.WM_LBUTTONUP, 0, lparam(60, int(wy - pet.wardrobe.win.y)))
    h.step(0.02)
    log(f"morph started: {pet.morph is not None}")

    for tag, at in (("morph_25", 0.22), ("morph_50", 0.45), ("morph_75", 0.70)):
        while pet.morph is not None and pet.morph["t"] < at:
            h.step(0.01)
        h.shot(tag)
    while pet.morph is not None:
        h.step(0.01)
    h.step(0.3)
    log(f"morph finished -> outfit={pet.outfit.id}")
    h.shot("done")

    cfg = os.path.join(BASE, ".bear.json")
    got = json.load(open(cfg, encoding="utf-8")) if os.path.exists(cfg) else None
    log(f"config={got}")

    pet.apply_outfit(omod.BY_ID["sakura"])
    while pet.morph is not None:
        h.step(0.01)
    h.step(0.3)
    h.shot("sakura")
    log(f"now outfit={pet.outfit.id} render_ms_check")
    t0 = time.perf_counter()
    for i in range(30):
        pet.sprites.render("running-right", i * 40)
    log(f"cached render ms/frame={(time.perf_counter()-t0)/30*1000:.2f}")

    pet.shutdown()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
