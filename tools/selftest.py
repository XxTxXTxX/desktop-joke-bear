"""交互自测：走真实的 Win32 消息通路（PostMessage + SetCursorPos），
验证 右键菜单 / 拖拽 / 抛掷 / 重力落地 / 点击小跳 是否正常。

用法：  python tools/selftest.py
输出：  preview/t_*.png 截图 + preview/selftest.log 事件日志
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".deps"))
sys.path.insert(0, BASE)

from PIL import ImageGrab

from bearpet import app, art, sprite, winlayer
from bearpet import winlayer as W

OUT = os.path.join(BASE, "preview")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "selftest.log")
open(LOG, "w", encoding="utf-8").close()


def log(msg: str):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.perf_counter():8.3f}  {msg}\n")
    print(msg, flush=True)


def lparam(x: int, y: int) -> int:
    return (y << 16) | (x & 0xFFFF)


def post(hwnd, msg, wp=0, lp=0):
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), msg, wp, lp)


def set_cursor(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


class Harness:
    def __init__(self):
        self.pet = app.BearPet()
        self.t0 = time.perf_counter()
        self.last = self.t0
        self.shots = 0

    def step(self, n: int = 1):
        for _ in range(n):
            self.pet.win.pump()
            now = time.perf_counter()
            dt = min(0.05, now - self.last)
            self.last = now
            self.pet.update(dt)
            self.pet.draw()
            time.sleep(0.008)

    def run_for(self, seconds: float):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.step()
            time.sleep(0.004)

    def until(self, cond, timeout=6.0):
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            self.step()
            if cond():
                return True
            time.sleep(0.004)
        return False

    def shot(self, tag: str, pad: int = 40):
        pet = self.pet
        x0 = max(0, int(pet.x) - pad)
        y0 = max(0, int(pet.y) - pad)
        x1 = min(1920, int(pet.x) + sprite.W + pad)
        y1 = min(1080, int(pet.y) + sprite.H + pad)
        img = ImageGrab.grab(bbox=(x0, y0, x1, y1))
        path = os.path.join(OUT, f"t_{self.shots:02d}_{tag}.png")
        img.save(path)
        self.shots += 1
        log(f"shot {path} bear=({pet.x:.0f},{pet.y:.0f}) state={pet.brain.state} "
            f"drag={pet.dragging} ground={pet.on_ground}")
        return path


def main() -> int:
    h = Harness()
    pet = h.pet
    hwnd = pet.win.hwnd
    h.run_for(0.8)
    h.shot("idle")

    # ---------- 1. 右键菜单 ----------
    log("--- test: right-click menu ---")
    set_cursor(pet.x + sprite.W / 2, pet.y + sprite.GROUND - 90)
    post(hwnd, W.WM_RBUTTONUP)
    h.run_for(0.5)
    ok_menu = pet.menu_open and pet.menu is not None
    log(f"menu_open={ok_menu}")
    if ok_menu:
        set_cursor(pet.menu.win.x + 40, pet.menu.win.y + pet.menu.PAD + pet.menu.ROW + 10)
        post(pet.menu.win.hwnd, W.WM_MOUSEMOVE, 1, lparam(40, 46))
        h.run_for(0.2)
        log(f"menu hover index={pet.menu.hover}")
    h.shot("menu")

    # 点菜单第一项「说句话」
    if ok_menu:
        mx = pet.menu.win.x + pet.menu.W / 2
        my = pet.menu.win.y + pet.menu.PAD + pet.menu.ROW / 2
        set_cursor(mx, my)
        post(pet.menu.win.hwnd, W.WM_MOUSEMOVE, 1, lparam(60, 20))
        h.run_for(0.15)
        post(pet.menu.win.hwnd, W.WM_LBUTTONDOWN, 1, lparam(60, 20))
        post(pet.menu.win.hwnd, W.WM_LBUTTONUP, 1, lparam(60, 20))
        h.run_for(0.4)
        log(f"after menu click: open={pet.menu_open} speech={pet.brain.speech!r}")
        h.shot("after_menu")

    # ---------- 2. 拖拽 + 抛掷 ----------
    log("--- test: drag & throw ---")
    bx = pet.x + sprite.W / 2
    by = pet.y + sprite.GROUND - 80
    set_cursor(bx, by)
    post(hwnd, W.WM_LBUTTONDOWN, 1, lparam(150, 200))
    h.step(2)
    for i in range(6):
        set_cursor(bx - i * 40, by - i * 70)
        post(hwnd, W.WM_MOUSEMOVE, 1, lparam(150, 200))
        h.step(2)
        time.sleep(0.02)
    log(f"dragging={pet.dragging} pos=({pet.x:.0f},{pet.y:.0f})")
    h.shot("dragging")
    post(hwnd, W.WM_LBUTTONUP, 0, lparam(150, 200))
    log("released")

    # 飞行中
    h.until(lambda: not pet.on_ground, 1.0)
    h.run_for(0.10)
    h.shot("airborne")
    landed_ok = h.until(lambda: pet.on_ground, 5.0)
    log(f"landed={landed_ok} impact_state={pet.brain.state} y={pet.y:.0f} ground={pet.y_ground:.0f}")
    h.run_for(0.25)
    h.shot("landed")

    # ---------- 3. 点击（小跳 + 台词） ----------
    log("--- test: click reaction ---")
    h.run_for(1.6)
    before = pet.brain.speech
    set_cursor(pet.x + sprite.W / 2, pet.y + sprite.GROUND - 80)
    post(hwnd, W.WM_LBUTTONDOWN, 1, lparam(150, 200))
    h.step(1)
    post(hwnd, W.WM_LBUTTONUP, 0, lparam(150, 200))
    h.step(3)
    log(f"click speech={pet.brain.speech!r} airborne={not pet.on_ground}")
    h.shot("click")

    # ---------- 4. 自由活动 20 秒，记录行为分布 ----------
    log("--- test: autonomous 20s ---")
    states = {}
    end = time.perf_counter() + 20
    while time.perf_counter() < end:
        h.step()
        states[pet.brain.state] = states.get(pet.brain.state, 0) + 1
        time.sleep(0.004)
    log(f"state histogram (frames): {states}")
    h.shot("autonomous")

    pet.shutdown()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
