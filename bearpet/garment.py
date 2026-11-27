from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import outfit as omod
from . import sprite as sp

HEAD_R = 48.0
CROWN_MARGIN = 2.0


@dataclass
class Anchors:
    cx: float
    head_top: float
    head_cy: float
    neck_y: float
    shoulder_y: float
    feet_y: float
    half_w: float
    eye_l: float = 0.0
    eye_r: float = 0.0
    eye_y: float = 0.0
    eye_dx: float = 0.0

    @property
    def eye_span(self) -> float:
        return self.eye_r - self.eye_l


def _role_mask(idx_cell: Image.Image, mapper, role: str) -> Image.Image:
    lut = [255 if mapper.roles[i] == role else 0 for i in range(256)]
    m = idx_cell.point(lut)
    return m.filter(ImageFilter.MinFilter(5))


def _crown_mask(idx_cell: Image.Image, mapper) -> Image.Image:
    pal = mapper.base_palette
    lut = [0] * 256
    for i in range(256):
        r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        if 36 <= h * 360 <= 64 and s >= 0.55 and v >= 0.70:
            lut[i] = 255
    return idx_cell.point(lut).filter(ImageFilter.MinFilter(5))


def _dark_lut(mapper) -> list[int]:
    pal = mapper.base_palette
    lut = [0] * 256
    for i in range(256):
        r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
        lut[i] = 255 if max(r, g, b) / 255.0 < 0.34 else 0
    return lut


def _blobs(mask: Image.Image, box, min_area=12, max_area=260):
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(mask.width, x1), min(mask.height, y1)
    px = mask.load()
    seen = set()
    out = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            if px[x, y] != 255 or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            pts = []
            while stack:
                a, b = stack.pop()
                pts.append((a, b))
                for p, q in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if x0 <= p < x1 and y0 <= q < y1 and (p, q) not in seen and px[p, q] == 255:
                        seen.add((p, q))
                        stack.append((p, q))
            n = len(pts)
            if min_area <= n <= max_area:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                out.append((sum(xs) / n, sum(ys) / n, n,
                            max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
    return out


def _find_eyes(idx_cell: Image.Image, mapper, cx: float, head_cy: float, head_w: float,
               wide: bool = False):
    radius_x = head_w * (0.62 if wide else 0.55)
    radius_y = head_w * (0.78 if wide else 0.42)
    box = (cx - radius_x, head_cy - radius_y * 0.65, cx + radius_x, head_cy + radius_y)
    cands = []
    for bx, by, area, w, h in _blobs(idx_cell.point(_dark_lut(mapper)), box):
        if w > 13 or h > 13:
            continue
        if abs(bx - cx) > radius_x * (0.95 if wide else 0.85):
            continue
        if not (box[1] <= by <= box[3]):
            continue
        cands.append((bx, by, area))
    if len(cands) < 2:
        return None
    span_min, span_max = head_w * (0.07 if wide else 0.10), head_w * 0.26
    span_ideal = head_w * 0.19
    best = None
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            x1, y1, a1 = cands[i]
            x2, y2, a2 = cands[j]
            if x1 > x2:
                x1, y1, a1, x2, y2, a2 = x2, y2, a2, x1, y1, a1
            if abs(y1 - y2) > (13.0 if wide else 4.0):
                continue
            span = x2 - x1
            if not (span_min <= span <= span_max):
                continue
            area_pen = 0.0 if (20 <= a1 <= 200 and 20 <= a2 <= 200) else 240.0
            mid = (x1 + x2) / 2.0
            cx_w = 0.12 if wide else 0.4
            score = (abs(y1 - y2) * 4.0
                     + abs(span - span_ideal) * 3.0
                     + abs(a1 - a2) * 0.3
                     + abs(mid - cx) * cx_w
                     + area_pen)
            if best is None or score < best[0]:
                best = (score, x1, x2, (y1 + y2) / 2.0)
    if best is None:
        return None
    return best[1], best[2], best[3]


def compute_anchors(sheet: "sp.SpriteSheet", state: str, idx: int) -> Anchors:
    row = sp.STATES[state][0]
    seq = sheet.sequence(state)
    col = seq[idx % len(seq)]
    box = (col * sp.CELL_W, row * sp.CELL_H, (col + 1) * sp.CELL_W, (row + 1) * sp.CELL_H)

    idx_cell = sheet.idx_atlas.crop(box).convert("L")
    alpha_bb = sheet.alpha.crop(box).getbbox()
    feet_y = float(alpha_bb[3]) if alpha_bb else 203.0

    cb = _crown_mask(idx_cell, sheet.mapper).getbbox()
    head_top = (cb[3] - CROWN_MARGIN) if cb is not None else (alpha_bb[1] if alpha_bb else 20.0) + 12.0
    head_cy = head_top + HEAD_R

    body = _role_mask(idx_cell, sheet.mapper, omod.BODY)
    y = int(max(0, min(sp.CELL_H - 1, head_cy)))
    rb = body.crop((0, y, sp.CELL_W, y + 1)).getbbox()
    if rb is not None and (rb[2] - rb[0]) > 20:
        cx = (rb[0] + rb[2]) / 2.0
        head_w = float(rb[2] - rb[0])
    else:
        cx = ((alpha_bb[0] + alpha_bb[2]) / 2.0) if alpha_bb else sp.CELL_W / 2.0
        head_w = HEAD_R * 2.0
    body_cx = cx

    is_look = state.startswith("look-")
    eyes = _find_eyes(idx_cell, sheet.mapper, cx, head_cy, head_w, wide=is_look)
    if eyes is not None:
        ex_l, ex_r, ey = eyes
        eye_cx = (ex_l + ex_r) / 2.0
        # Look-direction frames shift the eyes horizontally while the head crown stays centered.
        cx = eye_cx if cb is not None else (body_cx * 0.65 + eye_cx * 0.35)
        eye_dx = (ex_r - ex_l) / 2.0
        if is_look:
            neck_y = head_cy + head_w * 0.42
        else:
            head_cy = ey + head_w * 0.07
            neck_y = head_cy + head_w * 0.34
    else:
        eye_dx = head_w * 0.165
        ex_l, ex_r = cx - eye_dx, cx + eye_dx
        ey = head_cy - 2.0
        neck_y = head_cy + head_w * 0.34
        if state.startswith("look-"):
            idx_num = int(state.split("-", 1)[1])
            ang = math.radians(idx_num * 22.5)
            ex_off = math.sin(ang) * head_w * 0.24
            ey_off = -math.cos(ang) * head_w * 0.14
            ex_l += ex_off
            ex_r += ex_off
            ey += ey_off

    return Anchors(cx=cx, head_top=head_top, head_cy=head_cy, neck_y=neck_y,
                   shoulder_y=neck_y + head_w * 0.10, feet_y=feet_y,
                   half_w=head_w * 0.45,
                   eye_l=ex_l, eye_r=ex_r, eye_y=ey, eye_dx=eye_dx)


@dataclass
class Item:
    id: str
    name: str
    slot: str
    layer: str = "front"
    tint: tuple[int, int, int] = (90, 90, 96)


SLOTS = [("head", "头饰"), ("face", "脸"), ("neck", "脖子"), ("body", "身上")]


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (255,)


def _draw_straw(d, a: Anchors, t: float):
    col, dark = (226, 190, 108), (176, 138, 64)
    by = a.head_top + 4
    d.ellipse([a.cx - 46, by - 9, a.cx + 46, by + 11], fill=col, outline=(96, 62, 26), width=3)
    d.ellipse([a.cx - 26, by - 24, a.cx + 26, by + 6], fill=col, outline=(96, 62, 26), width=3)
    d.rectangle([a.cx - 26, by - 6, a.cx + 26, by + 3], fill=dark)
    d.line([a.cx - 26, by - 2, a.cx + 26, by - 2], fill=(250, 235, 200), width=2)


def _draw_santa(d, a: Anchors, t: float):
    red, white = (214, 58, 58), (255, 255, 255)
    by = a.head_top + 5
    tipx = a.cx + 14 + math.sin(t * 2.0) * 4
    d.polygon([(a.cx - 30, by), (a.cx + 30, by), (tipx, by - 62)], fill=red,
              outline=(120, 26, 26), width=3)
    d.ellipse([tipx - 11, by - 74, tipx + 11, by - 52], fill=white, outline=(120, 26, 26), width=3)
    d.rounded_rectangle([a.cx - 34, by - 8, a.cx + 34, by + 8], radius=8,
                        fill=white, outline=(150, 120, 110), width=2)


def _draw_cap(d, a: Anchors, t: float):
    blue, brim = (64, 118, 196), (232, 88, 74)
    by = a.head_top + 8
    d.ellipse([a.cx - 42, by - 8, a.cx + 42, by + 14], fill=brim,
              outline=(30, 56, 108), width=3)
    d.pieslice([a.cx - 31, by - 44, a.cx + 31, by + 16], 180, 360, fill=blue,
               outline=(30, 56, 108), width=3)
    d.ellipse([a.cx - 6, by - 38, a.cx + 6, by - 26], fill=(250, 220, 120),
              outline=(30, 56, 108), width=2)


def _draw_round_glasses(d, a: Anchors, t: float):
    r = max(6.0, min(a.eye_dx * 0.95, a.half_w * 0.36))
    for ex in (a.eye_l, a.eye_r):
        box = [ex - r, a.eye_y - r, ex + r, a.eye_y + r]
        d.ellipse(box, fill=(214, 232, 244, 90))
        d.ellipse(box, outline=(70, 54, 44), width=4)
    d.line([a.eye_l + r, a.eye_y, a.eye_r - r, a.eye_y], fill=(70, 54, 44), width=4)


def _draw_sunglasses(d, a: Anchors, t: float):
    hw = max(6.0, a.eye_dx * 0.88)
    hh = max(5.0, a.eye_dx * 0.62)
    for ex in (a.eye_l, a.eye_r):
        d.rounded_rectangle([ex - hw, a.eye_y - hh, ex + hw, a.eye_y + hh], radius=max(3, hh * 0.7),
                            fill=(34, 30, 40), outline=(12, 10, 14), width=3)
        d.line([ex - hw * 0.5, a.eye_y - hh * 0.35, ex + hw * 0.25, a.eye_y - hh * 0.55],
               fill=(120, 190, 255), width=2)
    d.line([a.eye_l + hw, a.eye_y - 1, a.eye_r - hw, a.eye_y - 1], fill=(12, 10, 14), width=4)


def _draw_blush(d, a: Anchors, t: float):
    rx = max(6.0, a.eye_dx * 1.0)
    ry = max(4.0, a.eye_dx * 0.6)
    y = a.eye_y + a.eye_dx * 1.5
    ex_mid = (a.eye_l + a.eye_r) / 2.0
    for sx in (-1, 1):
        x = ex_mid + sx * a.eye_dx * 2.2
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(255, 150, 160, 130))


def _draw_scarf(d, a: Anchors, t: float):
    col, dark = (206, 62, 62), (160, 40, 40)
    y = a.neck_y
    d.rounded_rectangle([a.cx - 34, y - 10, a.cx + 34, y + 12], radius=10,
                        fill=col, outline=(110, 26, 26), width=3)
    sway = math.sin(t * 2.4) * 5
    d.polygon([(a.cx + 10, y + 8), (a.cx + 26, y + 8),
               (a.cx + 24 + sway, y + 52), (a.cx + 8 + sway, y + 48)],
              fill=dark, outline=(110, 26, 26), width=3)
    for i in range(3):
        d.line([a.cx - 30 + i * 20, y - 6, a.cx - 26 + i * 20, y + 8],
               fill=(255, 235, 230), width=2)


def _draw_bowtie(d, a: Anchors, t: float):
    y = a.neck_y + 2
    col = (196, 60, 88)
    for sx in (-1, 1):
        d.polygon([(a.cx + sx * 6, y), (a.cx + sx * 28, y - 13),
                   (a.cx + sx * 28, y + 13)], fill=col, outline=(110, 26, 50), width=3)
    d.ellipse([a.cx - 7, y - 7, a.cx + 7, y + 7], fill=(230, 120, 150),
              outline=(110, 26, 50), width=2)


def _torso_mask(cell: Image.Image, a: Anchors) -> Image.Image:
    inner = cell.getchannel("A").filter(ImageFilter.MinFilter(7))
    band = Image.new("L", cell.size, 0)
    ImageDraw.Draw(band).rectangle([0, a.neck_y + 2, cell.width, a.feet_y - 2], fill=255)
    return ImageChops.multiply(inner, band)


def _draw_hoodie(cell: Image.Image, a: Anchors, t: float):
    col = (86, 108, 180)
    mask = _torso_mask(cell, a)
    paint = Image.new("RGBA", cell.size, col + (232,))
    cell.alpha_composite(Image.composite(paint, Image.new("RGBA", cell.size, (0, 0, 0, 0)), mask))
    d = ImageDraw.Draw(cell)
    d.arc([a.cx - 30, a.neck_y - 16, a.cx + 30, a.neck_y + 26], 200, 340,
          fill=(46, 60, 116), width=6)
    for sx in (-1, 1):
        d.line([a.cx + sx * 9, a.neck_y + 8, a.cx + sx * 11, a.neck_y + 34],
               fill=(244, 244, 250), width=3)
        d.ellipse([a.cx + sx * 11 - 3, a.neck_y + 32, a.cx + sx * 11 + 3, a.neck_y + 38],
                  fill=(244, 244, 250))
    d.arc([a.cx - 26, a.feet_y - 44, a.cx + 26, a.feet_y - 8], 200, 340,
          fill=(60, 78, 140), width=4)


def _draw_vest(cell: Image.Image, a: Anchors, t: float):
    col = (58, 58, 66)
    mask = ImageChops.multiply(_torso_mask(cell, a),
                               Image.new("L", cell.size, 255))
    paint = Image.new("RGBA", cell.size, col + (238,))
    cell.alpha_composite(Image.composite(paint, Image.new("RGBA", cell.size, (0, 0, 0, 0)), mask))
    d = ImageDraw.Draw(cell)
    d.polygon([(a.cx, a.neck_y + 6), (a.cx - 13, a.neck_y + 24), (a.cx, a.neck_y + 40),
               (a.cx + 13, a.neck_y + 24)], fill=(238, 236, 232))
    for i in range(2):
        d.ellipse([a.cx - 3, a.neck_y + 54 + i * 16, a.cx + 3, a.neck_y + 60 + i * 16],
                  fill=(240, 220, 120))


def _draw_backpack(cell: Image.Image, a: Anchors, t: float):
    pass


def _draw_wings(d, a: Anchors, t: float):
    flap = math.sin(t * 3.2) * 7
    for sx in (-1, 1):
        x = a.cx + sx * 24
        y = a.shoulder_y + 10
        d.polygon([(x, y - 34 - flap), (x + sx * 54, y - 46 - flap),
                   (x + sx * 46, y + 4), (x + sx * 14, y + 20)],
                  fill=(223, 234, 250, 245), outline=(120, 140, 172), width=3)
        d.polygon([(x + sx * 8, y - 14), (x + sx * 42, y - 24),
                   (x + sx * 34, y + 10)],
                  fill=(198, 214, 240, 245), outline=(120, 140, 172), width=2)


def _draw_pack(d, a: Anchors, t: float):
    col = (72, 96, 128)
    d.rounded_rectangle([a.cx - 30, a.shoulder_y - 4, a.cx + 30, a.feet_y - 16],
                        radius=14, fill=col, outline=(34, 48, 68), width=3)
    d.rounded_rectangle([a.cx - 20, a.shoulder_y + 10, a.cx + 20, a.feet_y - 30],
                        radius=10, fill=(92, 120, 158), outline=(34, 48, 68), width=2)


def _draw_pack_straps(d, a: Anchors, t: float):
    for sx in (-1, 1):
        d.line([a.cx + sx * 20, a.neck_y + 6, a.cx + sx * 26, a.feet_y - 22],
               fill=(46, 62, 88), width=6)


ITEMS: list[Item] = [
    Item("none", "不戴", "head"),
    Item("straw", "草帽", "head", tint=(226, 190, 108)),
    Item("santa", "圣诞帽", "head", tint=(214, 58, 58)),
    Item("cap", "棒球帽", "head", tint=(64, 118, 196)),

    Item("none", "不戴", "face"),
    Item("glasses", "圆眼镜", "face", tint=(70, 54, 44)),
    Item("shades", "墨镜", "face", tint=(34, 30, 40)),
    Item("blush", "腮红", "face", tint=(255, 150, 160)),

    Item("none", "不戴", "neck"),
    Item("scarf", "围巾", "neck", tint=(206, 62, 62)),
    Item("bowtie", "领结", "neck", tint=(196, 60, 88)),

    Item("none", "不穿", "body"),
    Item("hoodie", "连帽衫", "body", tint=(86, 108, 180)),
    Item("vest", "马甲", "body", tint=(58, 58, 66)),
    Item("pack", "背包", "body", tint=(72, 96, 128)),
    Item("wings", "天使翼", "body", layer="behind", tint=(240, 244, 252)),
]

FRONT_DRAW = {
    "straw": _draw_straw, "santa": _draw_santa, "cap": _draw_cap,
    "glasses": _draw_round_glasses, "shades": _draw_sunglasses, "blush": _draw_blush,
    "scarf": _draw_scarf, "bowtie": _draw_bowtie,
}
BEHIND_DRAW = {"wings": _draw_wings, "pack": _draw_pack}
PAINT = {"hoodie": _draw_hoodie, "vest": _draw_vest}


def apply_wear(cell: Image.Image, a: Anchors, wear: dict[str, str], t: float) -> Image.Image:
    ids = {i for i in wear.values() if i and i != "none"}
    if not ids:
        return cell
    out = cell.copy()

    behind = [i for i in ids if i in BEHIND_DRAW]
    if behind:
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i in behind:
            BEHIND_DRAW[i](d, a, t)
        out = Image.alpha_composite(layer, out)

    for i in ids:
        if i in PAINT:
            PAINT[i](out, a, t)

    front = [i for i in ids if i in FRONT_DRAW]
    if front:
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i in front:
            FRONT_DRAW[i](d, a, t)
        if "pack" in ids:
            straps = Image.new("RGBA", out.size, (0, 0, 0, 0))
            _draw_pack_straps(ImageDraw.Draw(straps), a, t)
            out = Image.alpha_composite(out, straps)
        out = Image.alpha_composite(out, layer)
    elif "pack" in ids:
        straps = Image.new("RGBA", out.size, (0, 0, 0, 0))
        _draw_pack_straps(ImageDraw.Draw(straps), a, t)
        out = Image.alpha_composite(out, straps)
    return out


def _demo(path: str = "wear.png"):
    sh = sp.SpriteSheet()
    demo_sets = [
        {},
        {"head": "straw", "neck": "scarf"},
        {"face": "glasses", "body": "vest"},
        {"head": "santa", "neck": "scarf", "body": "hoodie"},
        {"face": "shades", "body": "pack"},
        {"body": "wings", "head": "cap"},
    ]
    out = Image.new("RGBA", (sp.W * len(demo_sets), sp.H), (238, 234, 228, 255))
    for i, wear in enumerate(demo_sets):
        idx = 0
        cell = sh.frame("idle", idx)
        a = compute_anchors(sh, "idle", idx)
        cell = apply_wear(cell, a, wear, 0.0)
        out.alpha_composite(cell, (i * sp.W + sp.CELL_X, sp.CELL_Y))
    out.save(path)
    return path


if __name__ == "__main__":
    print(_demo())
