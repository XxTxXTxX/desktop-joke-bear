from __future__ import annotations

import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, ".deps"))
sys.path.insert(0, BASE)

from PIL import ImageGrab

from bearpet import app, reminder

OUT = os.path.join(BASE, "preview")
LOG = os.path.join(OUT, "local_reminder.log")
open(LOG, "w", encoding="utf-8").close()


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  {m}\n")
    print(m, flush=True)


def main() -> int:
    pet = app.BearPet()
    pet.store.items = []
    pet.store.quiet_on = False
    pet.store.quiet = ("00:00", "00:00")
    last = time.perf_counter()

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

    pet.open_editor()
    pump(0.4)
    e = pet.editor
    assert e.alive, "编辑器没打开"
    e._set_text(e.edit_msg, "记得喝水")
    e.sel_time = 1
    t0 = time.time()
    e.commit()
    pump(0.2)
    log(f"after commit: items={[(r.text, r.due_str(), r.repeat) for r in pet.store.items]} "
        f"speech={pet.brain.speech!r}")
    assert len(pet.store.items) == 1, "提醒没写进队列"
    due = pet.store.items[0].due
    assert abs((due - t0) - 600) < 5, f"10 分钟档位算错了：{due - t0:.0f}s"
    assert not e.alive, "提交后编辑器应关闭"

    pet.open_editor()
    pump(0.3)
    e._set_text(e.edit_msg, "晚上该睡觉了")
    e._set_text(e.edit_time, "23:59")
    e.commit()
    pump(0.2)
    lastone = pet.store.items[-1]
    lt = time.localtime(lastone.due)
    log(f"custom 23:59 -> {lastone.due_str()} repeat={lastone.repeat}")
    assert lt.tm_hour == 23 and lt.tm_min == 59, "自定义时间没生效"

    pet.open_editor()
    pump(0.3)
    e._set_text(e.edit_msg, "每天喝水")
    e.sel_time = 1
    e.sel_rep = 1
    e.commit()
    pump(0.2)
    daily = [r for r in pet.store.items if r.repeat == "daily"]
    assert daily, "daily 没记上"
    log(f"daily ok: {daily[0].due_str()}")

    pet.open_editor()
    pump(0.3)
    e._set_text(e.edit_msg, "三秒后提醒我")
    e._set_text(e.edit_time, "in:3s")
    e.commit()
    pump(1.0)
    log(f"t+1s speech={pet.brain.speech!r}")
    assert pet.brain.speech != "三秒后提醒我", "提前触发了"
    pump(3.0)
    log(f"t+4s speech={pet.brain.speech!r}")
    assert pet.brain.speech == "三秒后提醒我", "到点没触发"
    assert all(r.text != "三秒后提醒我" for r in pet.store.items), "一次性提醒触发后应出队"

    pet.open_reminders()
    pump(0.3)
    panel = pet.remind_panel
    log(f'panel state: open={pet.reminders_open} panel={panel} '
        f'shown={panel.win._shown} want={panel.win._want_visible} visible={panel.win.visible}')
    assert pet.reminders_open and panel.win.visible
    ImageGrab.grab(bbox=(panel.win.x - 6, panel.win.y - 6,
                         panel.win.x + panel.W + 6, panel.win.y + panel.H + 6)
                   ).save(os.path.join(OUT, "remind_panel.png"))
    before = len(pet.store.items)
    up = pet.store.upcoming(time.time(), 4)
    if up:
        d0 = panel._del_box(0)
        panel._on_up(panel.win.x + (d0[0] + d0[2]) / 2,
                     panel.win.y + (d0[1] + d0[3]) / 2)
        pump(0.2)
        log(f"delete: {before} -> {len(pet.store.items)}")
        assert len(pet.store.items) == before - 1, "删除没生效"

    ax0, ay0, ax1, ay1 = panel._add_box()
    panel._on_up(panel.win.x + (ax0 + ax1) / 2, panel.win.y + (ay0 + ay1) / 2)
    pump(0.3)
    log(f"panel add button -> editor alive={pet.editor.alive}")
    assert pet.editor.alive, "面板上的添加按钮没打开编辑器"
    pet.editor.close()

    pet.shutdown()
    log("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
