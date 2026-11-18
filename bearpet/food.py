from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import art, sprite, winlayer


@dataclass
class Food:
    id: str
    name: str
    satiety: float
    weight: float
    mood: int
    color: tuple[int, int, int]
    line: str


FOODS: list[Food] = [
    Food("fish", "小鱼干", 14, 0.3, 2, (222, 176, 92), "小鱼干，还是咸的"),
    Food("rice", "饭团", 22, 0.6, 2, (250, 249, 244), "饭团，碳水让我安心"),
    Food("cake", "蛋糕", 18, 1.1, 3, (255, 198, 214), "甜一点，就没那么难过了"),
    Food("coffee", "咖啡", 4, 0.1, 1, (122, 84, 56), "喝了也还是困"),
    Food("spicy", "辣条", 10, 0.4, 4, (214, 68, 48), "辣到流泪，正好不用解释"),
]

BY_ID = {f.id: f for f in FOODS}

HUNGRY_LINES = [
    "有点饿，但懒得动",
    "肚子在叫，装作没听见",
    "饿着也挺好，省事",
    "谁能给我点吃的，我连手都懒得伸",
]
EAT_LINES = [
    "吃了，但没觉得活着",
    "吃东西是今天唯一正经事",
    "边吃边觉得没意思",
    "谢了，虽然我不值得",
]
FULL_LINES = [
    "吃不下了，真的",
    "再吃就要变成球了",
    "够了够了，谢谢你还惦记我",
]


def icon(f: Food, size: int = 34) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (74, 46, 28, 255)
    if f.id == "fish":
        d.ellipse([s * 0.10, s * 0.30, s * 0.70, s * 0.72], fill=f.color + (255,),
                  outline=ink, width=2)
        d.polygon([(s * 0.68, s * 0.50), (s * 0.94, s * 0.28), (s * 0.94, s * 0.72)],
                  fill=f.color + (255,), outline=ink, width=2)
        d.ellipse([s * 0.22, s * 0.44, s * 0.29, s * 0.52], fill=ink)
    elif f.id == "rice":
        d.polygon([(s * 0.5, s * 0.14), (s * 0.88, s * 0.80), (s * 0.12, s * 0.80)],
                  fill=f.color + (255,), outline=ink, width=2)
        d.rectangle([s * 0.36, s * 0.52, s * 0.64, s * 0.72], fill=(40, 70, 50, 255))
    elif f.id == "cake":
        d.rounded_rectangle([s * 0.16, s * 0.42, s * 0.84, s * 0.84], radius=4,
                            fill=f.color + (255,), outline=ink, width=2)
        d.rectangle([s * 0.16, s * 0.40, s * 0.84, s * 0.52], fill=(255, 255, 255, 255))
        d.ellipse([s * 0.44, s * 0.20, s * 0.56, s * 0.34], fill=(226, 62, 72, 255))
    elif f.id == "coffee":
        d.rounded_rectangle([s * 0.20, s * 0.34, s * 0.74, s * 0.86], radius=4,
                            fill=f.color + (255,), outline=ink, width=2)
        d.arc([s * 0.66, s * 0.42, s * 0.92, s * 0.70], 270, 90, fill=ink, width=3)
        d.line([s * 0.34, s * 0.16, s * 0.42, s * 0.28], fill=(200, 200, 210, 255), width=2)
    else:
        d.polygon([(s * 0.14, s * 0.62), (s * 0.5, s * 0.24), (s * 0.86, s * 0.62),
                   (s * 0.5, s * 0.84)], fill=f.color + (255,), outline=ink, width=2)
        d.line([s * 0.34, s * 0.58, s * 0.66, s * 0.58], fill=(255, 214, 214, 255), width=2)
    return img


def _heart(d, x, y, r, color, alpha):
    d.polygon([(x, y + r),
               (x - r * 0.98, y - r * 0.18),
               (x - r * 0.86, y - r * 0.82),
               (x - r * 0.34, y - r * 0.96),
               (x, y - r * 0.34),
               (x + r * 0.34, y - r * 0.96),
               (x + r * 0.86, y - r * 0.82),
               (x + r * 0.98, y - r * 0.18)],
              fill=color + (alpha,))


def render_overlay(canvas: Image.Image, feed: dict, anchors, cell_origin=(0, 0)) -> Image.Image:
    out = canvas
    phase = feed["phase"]
    t = feed["t"]
    f: Food = feed["food"]
    ox, oy = cell_origin

    if phase == "fall":
        img = icon(f, 34)
        x = feed["x"] - 17
        y = feed["y"] - 17
        out = out.copy()
        out.alpha_composite(img, (int(x), int(y)))
        return out

    if phase == "eat":
        frag = Image.new("RGBA", out.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(frag)
        prog = min(1.0, t / 0.85)
        size = max(6, int(34 * (1.0 - prog)))
        img = icon(f, size)
        frag.alpha_composite(img, (int(feed["x"] - size / 2), int(feed["y"] - size / 2)))
        rng = random.Random(feed.get("seed", 7))
        for i in range(7):
            ang = rng.uniform(-0.4, 3.54)
            spd = rng.uniform(24, 52)
            px = feed["x"] + math.cos(ang) * spd * t * 1.8
            py = feed["y"] + math.sin(ang) * spd * t * 1.8 + 60 * t * t
            r = 2.0 * (1.0 - prog) + 0.6
            d.ellipse([px - r, py - r, px + r, py + r], fill=f.color + (int(220 * (1 - prog)),))
        return Image.alpha_composite(out, frag)

    frag = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(frag)
    rng = random.Random(feed.get("seed", 7) + 1)
    for i in range(max(3, f.mood * 2)):
        side = -1 if i % 2 == 0 else 1
        px = feed["x"] + side * rng.uniform(34, 64)
        py = feed["y"] - 34 - (t / 0.8) * 110 - rng.uniform(0, 22)
        a = int(255 * max(0.0, 1.0 - t / 0.8))
        _heart(d, px, py, 8.0, (240, 96, 120), a)
    return Image.alpha_composite(out, frag)


class FeedPanel:
    CELL = 56
    PAD = 10
    BAR_H = 26

    def __init__(self, pet):
        self.pet = pet
        self.W = self.PAD * 2 + self.CELL * len(FOODS)
        self.H = self.PAD * 2 + self.BAR_H + 52
        self.win = winlayer.LayeredWindow(self.W, self.H, "bearpet-feed", auto_show=False)
        self.win.on_move = self.hover_at
        self.win.on_left_up = self._on_up
        self.hover = -1
        self.font = art._font(12)
        self.small = art._font(10)
        self.icons = {f.id: icon(f, 32) for f in FOODS}
        self.image = None
        self._render()

    def _cell_box(self, i):
        return self.PAD + i * self.CELL, self.PAD + self.BAR_H

    def _render(self):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.W - 1, self.H - 1], radius=13,
                            fill=(253, 251, 246, 243), outline=art.OUTLINE, width=2)
        sat = max(0.0, min(100.0, self.pet.stats["satiety"]))
        bx0, by0 = self.PAD, self.PAD
        bx1, by1 = self.W - self.PAD, self.PAD + 14
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=7, fill=(236, 228, 214, 255),
                            outline=(206, 190, 168, 255), width=1)
        if sat > 1:
            w = (bx1 - bx0) * sat / 100.0
            col = (120, 200, 130) if sat < 70 else (240, 176, 90)
            if sat < 25:
                col = (226, 96, 96)
            d.rounded_rectangle([bx0 + 1, by0 + 1, bx0 + w, by1 - 1], radius=6, fill=col + (255,))
        d.text((bx0 + 4, by0 - 1), f"饱食度 {sat:.0f}", font=self.small, fill=(90, 70, 52, 255))
        wt = self.pet.stats["weight"]
        txt = f"{wt:.1f} kg"
        d.text((bx1 - self.small.getlength(txt) - 4, by0 - 1), txt, font=self.small,
               fill=(90, 70, 52, 255))
        for i, f in enumerate(FOODS):
            x, y = self._cell_box(i)
            if i == self.hover:
                d.rounded_rectangle([x + 1, y, x + self.CELL - 3, y + self.CELL - 8], radius=9,
                                    fill=(238, 226, 206, 255))
            img.alpha_composite(self.icons[f.id], (x + 9, y + 2))
            nw = self.small.getlength(f.name)
            d.text((x + (self.CELL - nw) / 2, y + 36), f.name, font=self.small,
                   fill=(58, 40, 26, 255))
        self.image = img

    def open_at(self, bear_x: float, bear_y: float):
        left, top, right, bottom = winlayer.work_area(self.win.hwnd)
        x = bear_x + sprite.W / 2 - self.W / 2
        y = bear_y + 8 - self.H
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
        i = int((sx - self.win.x - self.PAD) // self.CELL)
        return i if 0 <= i < len(FOODS) else -1

    def hover_at(self, sx, sy):
        i = self._index_at(sx, sy)
        if i != self.hover:
            self.hover = i
            self._render()
            self.win.blit(self.image)

    def _on_up(self, sx, sy):
        i = self._index_at(sx, sy)
        if i < 0:
            self.pet.close_feed()
            return
        started = self.pet.feed(FOODS[i])
        if started:
            return
        self._render()
        self.win.blit(self.image)

    def refresh(self):
        if self.win._shown:
            self._render()
            self.win.blit(self.image)

    def destroy(self):
        self.win.destroy()
