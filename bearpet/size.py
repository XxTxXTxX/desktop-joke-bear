"""大小面板：右键 → 大小，五档缩放。

缩放只作用在画布内（窗口尺寸固定 300×340），精灵按底部对齐缩放，
所以脚永远踩在同一条地平线上，影子也跟着缩。
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import art, sprite, winlayer

STEPS = (0.70, 0.85, 1.00, 1.15, 1.30)
LABELS = ("70%", "85%", "100%", "115%", "130%")

MIN_SCALE = STEPS[0]
MAX_SCALE = STEPS[-1]


def clamp(v: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, float(v)))


class SizePanel:
    CELL_W = 54
    CELL_H = 34
    PAD = 10
    HEADER = 20

    def __init__(self, pet):
        self.pet = pet
        self.W = self.PAD * 2 + self.CELL_W * len(STEPS)
        self.H = self.PAD * 2 + self.HEADER + self.CELL_H
        self.win = winlayer.LayeredWindow(self.W, self.H, "bearpet-size", auto_show=False)
        self.win.on_move = self.hover_at
        self.win.on_left_up = self._on_up
        self.hover = -1
        self.small = art._font(11)
        self.font = art._font(13)
        self.image = None
        self._render()

    def _cell_box(self, i: int):
        return self.PAD + i * self.CELL_W, self.PAD + self.HEADER

    def _render(self):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.W - 1, self.H - 1], radius=13,
                            fill=(253, 251, 246, 243), outline=art.OUTLINE, width=2)
        d.text((self.PAD + 2, self.PAD - 3), "大小", font=self.small, fill=(150, 120, 96, 255))
        cur = self.pet.size_scale
        for i, (v, lab) in enumerate(zip(STEPS, LABELS)):
            x, y = self._cell_box(i)
            box = [x + 1, y, x + self.CELL_W - 5, y + self.CELL_H - 2]
            on = abs(v - cur) < 0.005
            if on:
                d.rounded_rectangle(box, radius=9, fill=(246, 236, 214, 255),
                                    outline=(222, 190, 140, 255), width=1)
            elif i == self.hover:
                d.rounded_rectangle(box, radius=9, fill=(238, 226, 206, 255))
            # 用大小不一的圆点直观表示档位
            r = 3.0 + v * 5.0
            cx = (box[0] + box[2]) / 2
            cy = y + 11
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      fill=(206, 126, 5, 255) if not on else (232, 150, 30, 255),
                      outline=art.OUTLINE, width=1)
            tw = self.small.getlength(lab)
            d.text(((box[0] + box[2]) / 2 - tw / 2, y + 20), lab, font=self.small,
                   fill=(58, 40, 26, 255) if on else (120, 96, 74, 255))
        self.image = img

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

    def hide(self):
        self.win.hide()

    def hit(self, sx, sy) -> bool:
        return (self.win.x <= sx < self.win.x + self.W and
                self.win.y <= sy < self.win.y + self.H)

    def _index_at(self, sx, sy) -> int:
        if not self.hit(sx, sy):
            return -1
        i = int((sx - self.win.x - self.PAD) // self.CELL_W)
        return i if 0 <= i < len(STEPS) else -1

    def hover_at(self, sx, sy):
        i = self._index_at(sx, sy)
        if i != self.hover:
            self.hover = i
            self._render()
            self.win.blit(self.image)

    def _on_up(self, sx, sy):
        i = self._index_at(sx, sy)
        if i < 0:
            self.pet.close_size()
            return
        self.pet.set_size(STEPS[i])

    def destroy(self):
        self.win.destroy()
