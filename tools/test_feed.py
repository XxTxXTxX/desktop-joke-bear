"""投喂系统自测：右键 → 投喂 → 选食物 → 下落/咀嚼/爱心 → 数值与持久化。

用法： python tools/test_feed.py
"""
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

from bearpet import app, food, sprite, winlayer as W

OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "feed_test.log")
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
        path = os.path.join(OUT, f"f_{self.n:02d}_{tag}.png")
        ImageGrab.grab(bbox=box).save(path)
        self.n += 1
        fd = p.feeding
        log(f"shot {os.path.basename(path)} satiety={p.stats['satiety']:.1f} "
            f"weight={p.stats['weight']:.2f} feed={None if fd is None else fd['phase']}")
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
    log(f"start satiety={pet.stats['satiety']:.1f} weight={pet.stats['weight']:.2f} "
        f"fed={pet.stats['fed']}")

    # 右键 → 投喂（第 4 项，index 3）
    cur(pet.x + sprite.W / 2, pet.y + sprite.GROUND - 90)
    post(pet.win.hwnd, W.WM_RBUTTONUP)
    h.step(0.35)
    ui = 3
    mx = pet.menu.win.x + pet.menu.W / 2
    my = pet.menu.win.y + pet.menu.PAD + ui * pet.menu.ROW + pet.menu.ROW / 2
    h.click(pet.menu.win.hwnd, mx, my)
    h.step(0.35)
    log(f"feed panel open={pet.feed_is_open} size={pet.feed_panel.W}x{pet.feed_panel.H} "
        f"menu_open={pet.menu_open}")
    h.shot("panel")

    panel = pet.feed_panel
    px = panel.win.x + panel.PAD + 2 * panel.CELL + panel.CELL / 2      # 蛋糕
    py = panel.win.y + panel.PAD + panel.BAR_H + 20
    before = dict(pet.stats)
    h.click(panel.win.hwnd, px, py)
    h.step(0.02)
    log(f"feeding started: {pet.feeding is not None} phase={pet.feeding and pet.feeding['phase']} "
        f"panel_open={pet.feed_is_open}")
    assert pet.feeding is not None, "投喂没启动"
    assert pet.feed_is_open is False, "投喂后面板没关闭"
    h.shot("fall")

    # 落到嘴边
    while pet.feeding and pet.feeding["phase"] == "fall":
        h.step(0.01)
    h.shot("eat")
    while pet.feeding and pet.feeding["phase"] == "eat":
        h.step(0.01)
    h.shot("happy")
    while pet.feeding is not None:
        h.step(0.01)
    h.step(0.3)
    after = dict(pet.stats)
    log(f"stats before={before} after={after}")
    assert after["satiety"] > before["satiety"], "satiety 没涨"
    assert after["fed"] == before["fed"] + 1, "fed 没加"
    h.shot("after")

    # 吃饱了会拒绝，且面板要留着
    pet.stats["satiety"] = 95.0
    pet.open_feed()
    h.step(0.25)
    px = panel.win.x + panel.PAD + 2 * panel.CELL + panel.CELL / 2
    py = panel.win.y + panel.PAD + panel.BAR_H + 20
    h.click(panel.win.hwnd, px, py)
    h.step(0.3)
    log(f"full-refuse: feeding={pet.feeding} panel_open={pet.feed_is_open} "
        f"speech={pet.brain.speech!r}")
    assert pet.feeding is None, "吃饱了还在掉食物"
    assert pet.feed_is_open is True, "拒绝后不应该关面板"
    h.shot("refuse")
    pet.close_feed()

    # 投喂面板刷新（饱食度条）
    pet.open_feed()
    h.step(0.25)
    h.shot("panel_after")
    pet.close_feed()

    # 体重影响体型
    pet.stats["weight"] = 78.0
    h.step(0.2)
    log(f"scale at weight 78 = {pet._body_scale():.3f}")
    h.shot("fat")
    pet.stats["weight"] = 50.0
    pet._save_config()

    cfg = os.path.join(BASE, ".bear.json")
    log("config=" + json.dumps(json.load(open(cfg, encoding="utf-8")), ensure_ascii=False))

    t0 = time.perf_counter()
    for i in range(30):
        pet.sprites.render("running-right", i * 40, scale=pet._body_scale())
    log(f"render ms/frame={(time.perf_counter()-t0)/30*1000:.2f}")

    pet.shutdown()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
