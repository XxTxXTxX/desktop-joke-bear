from __future__ import annotations

from PIL import Image, ImageDraw

from . import art, garment, outfit as omod, sprite, winlayer

ICON = 30


def _icon(item: garment.Item) -> Image.Image:
    img = Image.new("RGBA", (ICON, ICON), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = ICON / 2.0
    i = item.id
    ink = (74, 46, 28, 255)

    if i == "none":
        d.line([(9, 21), (21, 9)], fill=(190, 180, 168, 255), width=2)
        return img
    if i == "straw":
        d.ellipse([2, 15, 28, 24], fill=(226, 190, 108), outline=ink, width=2)
        d.ellipse([7, 4, 23, 20], fill=(226, 190, 108), outline=ink, width=2)
        d.rectangle([7, 14, 23, 17], fill=(176, 138, 64))
    elif i == "santa":
        d.polygon([(5, 20), (25, 20), (20, 3)], fill=(214, 58, 58), outline=ink, width=2)
        d.ellipse([16, 1, 24, 9], fill=(255, 255, 255), outline=ink, width=1)
        d.rectangle([4, 19, 26, 24], fill=(255, 255, 255), outline=(150, 120, 110), width=1)
    elif i == "cap":
        d.ellipse([2, 14, 28, 22], fill=(232, 88, 74), outline=ink, width=2)
        d.pieslice([6, 3, 24, 20], 180, 360, fill=(64, 118, 196), outline=ink, width=2)
    elif i == "glasses":
        d.ellipse([2, 10, 13, 21], fill=(214, 232, 244, 160), outline=ink, width=2)
        d.ellipse([17, 10, 28, 21], fill=(214, 232, 244, 160), outline=ink, width=2)
        d.line([(13, 15), (17, 15)], fill=ink, width=2)
    elif i == "shades":
        d.rounded_rectangle([2, 10, 13, 21], radius=4, fill=(34, 30, 40), outline=ink, width=2)
        d.rounded_rectangle([17, 10, 28, 21], radius=4, fill=(34, 30, 40), outline=ink, width=2)
        d.line([(13, 14), (17, 14)], fill=ink, width=2)
    elif i == "blush":
        d.ellipse([3, 12, 12, 19], fill=(255, 150, 160, 200))
        d.ellipse([18, 12, 27, 19], fill=(255, 150, 160, 200))
    elif i == "scarf":
        d.rounded_rectangle([3, 8, 27, 17], radius=5, fill=(206, 62, 62), outline=ink, width=2)
        d.polygon([(17, 15), (25, 15), (23, 28), (15, 28)], fill=(160, 40, 40),
                  outline=ink, width=2)
    elif i == "bowtie":
        d.polygon([(14, 15), (4, 8), (4, 22)], fill=(196, 60, 88), outline=ink, width=2)
        d.polygon([(16, 15), (26, 8), (26, 22)], fill=(196, 60, 88), outline=ink, width=2)
        d.ellipse([11, 12, 19, 20], fill=(230, 120, 150), outline=ink, width=1)
    elif i == "hoodie":
        d.rounded_rectangle([4, 8, 26, 26], radius=7, fill=(86, 108, 180), outline=ink, width=2)
        d.arc([8, 4, 22, 16], 200, 340, fill=(46, 60, 116), width=2)
    elif i == "vest":
        d.polygon([(6, 8), (24, 8), (26, 26), (4, 26)], fill=(58, 58, 66), outline=ink, width=2)
        d.polygon([(15, 9), (10, 15), (15, 21), (20, 15)], fill=(238, 236, 232))
    elif i == "pack":
        d.rounded_rectangle([7, 8, 23, 26], radius=5, fill=(72, 96, 128), outline=ink, width=2)
        d.rounded_rectangle([10, 12, 20, 21], radius=3, fill=(92, 120, 158), outline=ink, width=1)
    elif i == "wings":
        d.polygon([(14, 14), (2, 5), (5, 22)], fill=(223, 234, 250), outline=(120, 140, 172), width=2)
        d.polygon([(16, 14), (28, 5), (25, 22)], fill=(223, 234, 250), outline=(120, 140, 172), width=2)
    return img


def _swatch(o: omod.Outfit, size: int = 26) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=7, fill=o.body + (255,),
                        outline=o.outline + (255,), width=2)
    d.rounded_rectangle([1, size * 0.56, size - 2, size - 2], radius=6, fill=o.cape + (255,))
    r = size * 0.17
    cx, cy = size * 0.70, size * 0.30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=o.crown + (255,),
              outline=o.outline + (255,), width=1)
    return img


class Wardrobe:
    COLS = 4
    CELL_W = 68
    CELL_H = 46
    PAD = 10
    HEADER = 24
    SWATCH_ROW = 34

    def __init__(self, pet):
        self.pet = pet
        self.rows = max(len([i for i in garment.ITEMS if i.slot == s[0]])
                        for s in garment.SLOTS)
        self.W = self.PAD * 2 + self.CELL_W * self.COLS
        self.H = (self.PAD * 2 + self.HEADER + self.SWATCH_ROW
                  + self.HEADER + self.rows * self.CELL_H)
        self.win = winlayer.LayeredWindow(self.W, self.H, "bearpet-wardrobe", auto_show=False)
        self.win.on_move = self.hover_at
        self.win.on_left_up = self._on_up
        self.hover = (-1, -1)
        self.font = art._font(13)
        self.small = art._font(11)
        self.icons = {i.id: _icon(i) for i in garment.ITEMS}
        self.swatches = {o.id: _swatch(o) for o in omod.OUTFITS}
        self._slot_items = [[i for i in garment.ITEMS if i.slot == s[0]] for s in garment.SLOTS]
        self.image = None
        self._render()

    def _cell_box(self, r: int, c: int):
        x = self.PAD + c * self.CELL_W
        y = self.PAD + self.HEADER + self.SWATCH_ROW + self.HEADER + r * self.CELL_H
        return x, y

    def _swatch_box(self, i: int):
        return self.PAD + 6 + i * 38, self.PAD + self.HEADER

    def _pick(self, sx: int, sy: int):
        lx, ly = sx - self.win.x, sy - self.win.y
        if not (0 <= lx < self.W and 0 <= ly < self.H):
            return None
        sy0 = self.PAD + self.HEADER
        if sy0 - 4 <= ly < sy0 + self.SWATCH_ROW:
            for i in range(len(omod.OUTFITS)):
                x, _y = self._swatch_box(i)
                if x - 4 <= lx < x + 30:
                    return ("outfit", i)
        for r in range(self.rows):
            for c in range(self.COLS):
                if r >= len(self._slot_items[c]):
                    continue
                x, y = self._cell_box(r, c)
                if x <= lx < x + self.CELL_W and y <= ly < y + self.CELL_H:
                    return ("item", r, c)
        return None

    def _render(self):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.W - 1, self.H - 1], radius=13,
                            fill=(253, 251, 246, 243), outline=art.OUTLINE, width=2)
        d.text((self.PAD + 2, self.PAD - 2), "换装", font=self.small, fill=(150, 120, 96, 255))
        d.text((self.W - 104, self.PAD - 2), "点=穿上 再点=脱掉", font=self.small,
               fill=(176, 158, 138, 255))

        sy = self.PAD + self.HEADER
        for i, o in enumerate(omod.OUTFITS):
            x, y = self._swatch_box(i)
            if self.hover == (-1, i):
                d.rounded_rectangle([x - 5, y - 4, x + 31, y + 30], radius=9,
                                    fill=(238, 226, 206, 255))
            img.alpha_composite(self.swatches[o.id], (x, y + 1))
            if o.id == self.pet.outfit.id:
                d.ellipse([x + 20, y + 20, x + 30, y + 30], fill=o.crown + (255,),
                          outline=art.OUTLINE, width=1)

        hy = sy + self.SWATCH_ROW
        for c, (slot, label) in enumerate(garment.SLOTS):
            cx = self.PAD + c * self.CELL_W + self.CELL_W / 2
            d.text((cx - len(label) * 6, hy + 4), label, font=self.small,
                   fill=(120, 96, 74, 255))
            d.line([(self.PAD + c * self.CELL_W + 8, hy + self.HEADER - 4),
                    (self.PAD + (c + 1) * self.CELL_W - 8, hy + self.HEADER - 4)],
                   fill=(226, 214, 198, 255), width=1)

        for c, (slot, _label) in enumerate(garment.SLOTS):
            for r, item in enumerate(self._slot_items[c]):
                x, y = self._cell_box(r, c)
                on = self.pet.wear.get(slot) == item.id
                if self.hover == (r, c):
                    d.rounded_rectangle([x + 2, y + 1, x + self.CELL_W - 2, y + self.CELL_H - 2],
                                        radius=9, fill=(238, 226, 206, 255))
                elif on:
                    d.rounded_rectangle([x + 2, y + 1, x + self.CELL_W - 2, y + self.CELL_H - 2],
                                        radius=9, fill=(246, 236, 214, 255),
                                        outline=(222, 190, 140, 255), width=1)
                ix = x + (self.CELL_W - ICON) // 2
                img.alpha_composite(self.icons[item.id], (ix, y + 1))
                nw = self.small.getlength(item.name)
                d.text((x + (self.CELL_W - nw) / 2, y + ICON + 1), item.name,
                       font=self.small, fill=(58, 40, 26, 255) if on else (110, 92, 74, 255))
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
        self.hover = (-1, -1)

    def hide(self):
        self.win.hide()

    def hit(self, sx: int, sy: int) -> bool:
        return (self.win.x <= sx < self.win.x + self.W and
                self.win.y <= sy < self.win.y + self.H)

    def hover_at(self, sx, sy):
        pick = self._pick(sx, sy)
        hov = (-1, pick[1]) if pick and pick[0] == "outfit" else \
              ((pick[1], pick[2]) if pick else (-1, -1))
        if hov != self.hover:
            self.hover = hov
            self._render()
            self.win.blit(self.image)

    def _on_up(self, sx, sy):
        pick = self._pick(sx, sy)
        if pick is None:
            self.pet.close_wardrobe()
            return
        if pick[0] == "outfit":
            self.pet.apply_outfit(omod.OUTFITS[pick[1]])
            self._render()
        else:
            item = self._slot_items[pick[2]][pick[1]]
            self.pet.apply_wear(item.slot, item.id)
            self.close_and_reopen()

    def close_and_reopen(self):
        self._render()
        self.win.blit(self.image)

    def destroy(self):
        self.win.destroy()
