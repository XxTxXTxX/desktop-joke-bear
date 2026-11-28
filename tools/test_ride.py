from __future__ import annotations

import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".deps"))
sys.path.insert(0, BASE)

from bearpet import app, sprite, winlayer

OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "ride_test.log")
open(LOG, "w", encoding="utf-8").close()

FAKE = {"x": 900, "y": 500}
FAKE_WIN = {"visible": True, "l": 500, "t": 420, "r": 1220, "b": 900}


def fake_cursor():
    return FAKE["x"], FAKE["y"]


def fake_ledge(bear_hwnd=None):
    if not FAKE_WIN["visible"]:
        return None
    return 99999, FAKE_WIN["l"], FAKE_WIN["t"], FAKE_WIN["r"], FAKE_WIN["b"]


def fake_bounds(hwnd):
    if not FAKE_WIN["visible"] or hwnd != 99999:
        return None
    return FAKE_WIN["l"], FAKE_WIN["t"], FAKE_WIN["r"], FAKE_WIN["b"]


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  {m}\n")
    print(m, flush=True)


def main() -> int:
    winlayer.cursor_pos = fake_cursor
    app.winlayer.cursor_pos = fake_cursor
    winlayer.foreground_window_ledge = fake_ledge
    app.winlayer.foreground_window_ledge = fake_ledge
    winlayer.window_bounds = fake_bounds
    app.winlayer.window_bounds = fake_bounds

    pet = app.BearPet()
    pet.store.items = []
    pet.brain.speech = None

    def tick(n, dt=1 / 60):
        for _ in range(n):
            pet.win.pump()
            pet.update(dt)
            pet.draw()

    tick(30)
    # 1. Idle cursor for 15 seconds must NOT trigger cursor riding
    pet._parkour_next = 999.0
    tick(int(15 * 60))
    log(f"after 15s cursor idle: riding={pet.riding} climb={pet.climb}")
    assert not pet.riding and pet.climb is None, "cursor riding should be removed"

    # 2. Trigger desktop parkour onto windowed foreground window top edge
    pet.brain._enter("idle")
    pet._parkour_next = 0.05
    tick(10)
    assert pet.perch is not None, "should start parkour jump onto foreground window"
    log(f"parkour started: vy={pet.vy:.0f} vx={pet.vx:.0f} target_y={pet.perch['y_ground']:.0f}")

    # Wait until it lands on the window top edge
    tick(int(2.2 * 60))
    expected_y = float(FAKE_WIN["t"] - sprite.GROUND)
    log(f"on window ledge: on_ground={pet.on_ground} y={pet.y:.0f} expected_y={expected_y:.0f} state={pet.brain.state}")
    assert pet.on_ground and abs(pet.y - expected_y) < 2.0, "should land on window top edge"

    # Walk along the window top edge and verify it stays clamped to [left, right]
    pet.brain.force("walk")
    tick(int(3.0 * 60))
    half_foot = 28.0 * pet._draw_scale()
    xmin = FAKE_WIN["l"] - sprite.W / 2.0 + half_foot
    xmax = FAKE_WIN["r"] - sprite.W / 2.0 - half_foot
    log(f"walking on ledge: x={pet.x:.1f} bounds=({xmin:.1f},{xmax:.1f})")
    assert xmin - 1.0 <= pet.x <= xmax + 1.0, "bear walked off the window edge"

    # Closing/minimizing the window drops the bear back to the desktop floor
    FAKE_WIN["visible"] = False
    tick(int(2.0 * 60))
    floor_y = float(winlayer.ground_bottom() - 1 - sprite.GROUND)
    log(f"after window closed: perch={pet.perch} on_ground={pet.on_ground} y={pet.y:.0f} floor={floor_y:.0f}")
    assert pet.perch is None and pet.on_ground and abs(pet.y - floor_y) < 2.0, "should fall back to desktop floor"

    pet.shutdown()
    log("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
