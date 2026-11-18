from __future__ import annotations

import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".deps"))
sys.path.insert(0, BASE)

from PIL import ImageGrab

from bearpet import app, winlayer

OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "ride_test.log")
open(LOG, "w", encoding="utf-8").close()

FAKE = {"x": 900, "y": 500}


def fake_cursor():
    return FAKE["x"], FAKE["y"]


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  {m}\n")
    print(m, flush=True)


def main() -> int:
    winlayer.cursor_pos = fake_cursor
    app.winlayer.cursor_pos = fake_cursor
    pet = app.BearPet()
    pet.store.items = []
    pet.brain.speech = None

    def tick(n, dt=1 / 60):
        for _ in range(n):
            pet.win.pump()
            pet.update(dt)
            pet.draw()

    def shot(tag):
        path = os.path.join(OUT, f"ride_{tag}.png")
        x = max(0, int(pet.x) - 20)
        y = max(0, int(pet.y) - 20)
        ImageGrab.grab(bbox=(x, y, min(1920, x + 340), min(1080, y + 360))).save(path)
        return path

    tick(30)
    log(f"start riding={pet.riding} climb={pet.climb is not None} pos=({pet.x:.0f},{pet.y:.0f})")

    tick(int(9 * 60))
    log(f"t=9s riding={pet.riding} climb={pet.climb is not None} idle={pet._cursor_idle:.1f}")
    assert not pet.riding and pet.climb is None, "9 秒就爬上去了"

    tick(int(2 * 60))
    log(f"t=11s riding={pet.riding} climb={pet.climb is not None}")
    assert pet.riding or pet.climb is not None, "超过 10 秒没反应"

    tick(int(1.5 * 60))
    log(f"after climb riding={pet.riding} pos=({pet.x:.0f},{pet.y:.0f}) speech={pet.brain.speech!r}")
    assert pet.riding, "没进入骑乘状态"
    shot("on_cursor")

    for _ in range(10):
        FAKE["x"] += 8
        tick(1)
    log(f"follow pos=({pet.x:.0f},{pet.y:.0f}) cursor=({FAKE['x']},{FAKE['y']})")
    assert pet.riding, "正常移动就掉下来了"

    FAKE["x"] += 200
    tick(2)
    log(f"after flick riding={pet.riding} on_ground={pet.on_ground} vy={pet.vy:.0f}")
    assert not pet.riding, "甩不下来"
    tick(int(2 * 60))
    log(f"landed on_ground={pet.on_ground} y={pet.y:.0f} ground={pet.y_ground:.0f}")
    assert pet.on_ground, "没落地"

    FAKE["x"] += 5
    tick(5)
    tick(int(12 * 60))
    log(f"second ride riding={pet.riding} climb={pet.climb is not None}")
    assert pet.riding or pet.climb is not None, "第二次没爬上去"

    tick(int(1.5 * 60))
    pet._on_down(FAKE["x"], FAKE["y"])
    tick(2)
    log(f"after click riding={pet.riding}")
    assert not pet.riding, "点击没下来"

    log(f"default size = {pet.size_scale}")
    assert abs(pet.size_scale - 0.5) < 1e-6, "默认大小不是 50%"

    pet.shutdown()
    log("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
