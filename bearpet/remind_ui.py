"""提醒面板：看排队中的提醒、切换静音时段、看一眼手机端地址。

手机上发消息是主入口，这个面板是"给她也能看见"的那一层：排了哪些提醒、
静音时段是什么、现在连没连上，都摆在明面上。
"""
from __future__ import annotations

import time

from PIL import Image, ImageDraw

from . import art, sprite, winlayer

PAD = 12


class ReminderPanel:
    W = 340
    ROW = 30
    ROWS = 4

    def __init__(self, pet):
        self.pet = pet
        self.H = PAD * 2 + 26 + 26 + self.ROWS * self.ROW + 24 + 30
        self.win = winlayer.LayeredWindow(self.W, self.H, "bearpet-remind", auto_show=False)
        self.win.on_move = self.hover_at
        self.win.on_left_up = self._on_up
        self.hover = -1
        self.font = art._font(13)
        self.small = art._font(11)
        self.image = None
        self._render()

    # ------------------------------------------------------------ 布局
    def _quiet_box(self):
        return (PAD, PAD + 26, self.W - PAD, PAD + 48)

    def _add_box(self):
        return (PAD, self.H - PAD - 26, self.W * 0.62, self.H - PAD)

    def _test_box(self):
        return (self.W * 0.62 + 6, self.H - PAD - 26, self.W - PAD, self.H - PAD)

    def _del_box(self, i):
        y = self._quiet_box()[3] + 6 + i * self.ROW
        return (self.W - PAD - 18, y, self.W - PAD - 2, y + self.ROW - 8)

    # ------------------------------------------------------------ 绘制
    def _render(self):
        pet = self.pet
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.W - 1, self.H - 1], radius=13,
                            fill=(253, 251, 246, 243), outline=art.OUTLINE, width=2)

        # 标题 + 连接状态
        d.text((PAD, PAD - 3), "提醒", font=self.small, fill=(150, 120, 96, 255))
        online = pet.remote is not None and pet.remote.status == "online"
        dot = (110, 200, 120, 255) if online else (214, 120, 110, 255)
        state = "手机端已连接" if online else ("未配置手机端" if pet.remote is None else "等待连接")
        d.ellipse([self.W - PAD - 92, PAD + 1, self.W - PAD - 84, PAD + 9], fill=dot)
        d.text((self.W - PAD - 78, PAD - 3), state, font=self.small, fill=(120, 96, 74, 255))

        # 静音时段开关
        x0, y0, x1, y1 = self._quiet_box()
        on = pet.quiet_on
        d.rounded_rectangle([x0, y0, x1, y1], radius=8,
                            fill=(240, 232, 218, 255) if not on else (255, 233, 201, 255),
                            outline=(214, 200, 182, 255), width=1)
        label = f"静音时段 {'开' if on else '关'}   {pet.quiet[0]} – {pet.quiet[1]}"
        d.text((x0 + 8, y0 + 5), label, font=self.small, fill=(90, 70, 52, 255))
        d.text((x1 - 46, y0 + 5), "点我切换", font=self.small, fill=(150, 130, 110, 255))

        # 待办列表
        now = time.time()
        up = pet.store.upcoming(now, self.ROWS)
        ly = y1 + 6
        if not up:
            d.text((PAD + 2, ly + 4), "现在没有排队的提醒", font=self.small,
                   fill=(150, 130, 110, 255))
        for i, r in enumerate(up):
            y = ly + i * self.ROW
            if i == self.hover:
                d.rounded_rectangle([PAD - 4, y, self.W - PAD + 4, y + self.ROW - 4],
                                    radius=7, fill=(238, 226, 206, 255))
            tag = {"daily": "每天 ", "weekday": "工作日 "}.get(r.repeat or "", "")
            d.text((PAD + 2, y + 4), r.due_str(), font=self.small, fill=(150, 120, 96, 255))
            d.text((PAD + 76, y + 3), tag + r.text[:16], font=self.font, fill=(58, 40, 26, 255))
            dx0, dy0, dx1, dy1 = self._del_box(i)
            d.text((dx0 + 3, dy0 - 2), "×", font=self.font, fill=(190, 120, 110, 255))

        # 地址提示
        hint_y = ly + self.ROWS * self.ROW + 2
        if pet.remote is not None:
            hint = pet.remote.base
        else:
            hint = "在 .bear.json 里填 remote.url / remote.token"
        d.text((PAD + 2, hint_y), hint[:46], font=self.small, fill=(176, 158, 138, 255))

        # 底部按钮：添加 / 试一下
        ax0, ay0, ax1, ay1 = self._add_box()
        d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=9, fill=(255, 233, 201, 255),
                            outline=(224, 151, 46, 255), width=2)
        label = "＋ 添加提醒"
        tw = self.small.getlength(label)
        d.text(((ax0 + ax1) / 2 - tw / 2, ay0 + 6), label, font=self.small,
               fill=(138, 90, 18, 255))
        bx0, by0, bx1, by1 = self._test_box()
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=9,
                            fill=(238, 226, 206, 255) if self.hover != -4 else (226, 210, 184, 255),
                            outline=(214, 200, 182, 255), width=1)
        tw = self.small.getlength("试一下")
        d.text(((bx0 + bx1) / 2 - tw / 2, by0 + 6), "试一下",
               font=self.small, fill=(120, 96, 74, 255))
        self.image = img

    # ------------------------------------------------------------ 交互
    def open_at(self, bear_x: float, bear_y: float):
        left, top, right, bottom = winlayer.work_area(self.win.hwnd)
        x = bear_x + sprite.W / 2 - self.W / 2
        y = bear_y + 122 - self.H
        x = max(left + 8, min(right - self.W - 8, x))
        y = max(top + 8, min(bottom - self.H - 8, y))
        self._render()
        self.win.show()
        self.win.blit(self.image, int(x), int(y))
        self.win.raise_topmost()
        self.hover = -1

    def refresh(self):
        self._render()
        if self.win.visible:
            self.win.blit(self.image)

    def hide(self):
        self.win.hide()

    def hit(self, sx, sy) -> bool:
        return (self.win.x <= sx < self.win.x + self.W and
                self.win.y <= sy < self.win.y + self.H)

    def _local(self, sx, sy):
        return sx - self.win.x, sy - self.win.y

    def hover_at(self, sx, sy):
        lx, ly = self._local(sx, sy)
        h = -1
        if not self.hit(sx, sy):
            h = -1
        elif self._quiet_box()[1] <= ly <= self._quiet_box()[3]:
            h = -3
        else:
            ax0, ay0, ax1, ay1 = self._add_box()
            x0, y0, x1, y1 = self._test_box()
            ly0 = self._quiet_box()[3] + 6
            if ay0 <= ly <= ay1 and lx <= ax1:
                h = -2
            elif y0 <= ly <= y1:
                h = -4
            else:
                idx = int((ly - ly0) // self.ROW)
                if 0 <= idx < self.ROWS:
                    d0 = self._del_box(idx)
                    h = -10 - idx if (d0[0] <= lx <= d0[2] and d0[1] <= ly <= d0[3]) else idx
        if h != self.hover:
            self.hover = h
            self._render()
            self.win.blit(self.image)

    def _on_up(self, sx, sy):
        lx, ly = self._local(sx, sy)
        if not self.hit(sx, sy):
            self.pet.close_reminders()
            return
        if self._quiet_box()[1] <= ly <= self._quiet_box()[3]:
            self.pet.toggle_quiet()
            self._render()
            self.win.blit(self.image)
            return
        ax0, ay0, ax1, ay1 = self._add_box()
        if ay0 <= ly <= ay1 and lx <= ax1:
            self.pet.open_editor()
            return
        x0, y0, x1, y1 = self._test_box()
        if y0 <= ly <= y1:
            self.pet.test_reminder()
            return
        ly0 = self._quiet_box()[3] + 6
        idx = int((ly - ly0) // self.ROW)
        if 0 <= idx < self.ROWS:
            d0 = self._del_box(idx)
            if d0[0] <= lx <= d0[2] and d0[1] <= ly <= d0[3]:
                up = self.pet.store.upcoming(time.time(), self.ROWS)
                if idx < len(up):
                    self.pet.store.remove(up[idx].id)
                    self._render()
                    self.win.blit(self.image)

    def destroy(self):
        self.win.destroy()
