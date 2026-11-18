from __future__ import annotations

import math
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

W, H = 300, 320
SS = 2
CX = W // 2
FY = H - 14

FUR       = (206, 126, 5, 255)
FUR_DARK  = (176, 104, 4, 255)
EAR_IN    = (255, 198, 26, 255)
WHITE     = (255, 255, 255, 255)
CREAM     = (255, 252, 245, 255)
OUTLINE   = (51, 18, 8, 255)
NOSE      = (51, 18, 8, 255)
MOUTH_BG  = (255, 255, 255, 255)
BUBBLE_BG = (255, 253, 248, 255)

_OW = 3.4
HEAD_R = 49.0
BUBBLE_BOTTOM = 126.0


@dataclass
class Pose:
    bob: float = 0.0
    squash: float = 1.0
    tilt: float = 0.0
    head_tilt: float = 0.0
    head_bob: float = 0.0
    leg_phase: float = 0.0
    walking: bool = False
    sit: bool = False
    eye: str = "open"
    eye_dx: float = 0.0
    eye_dy: float = 0.0
    blink: float = 1.0
    mouth: str = "flat"
    mouth_open: float = 0.0
    arm_swing: float = 0.0
    arm_spread: float = 0.0
    sweat: float = 0.0
    shadow: float = 1.0
    tuft: float = 0.0
    zzz: float = 0.0
    alpha: float = 1.0


class Pen:

    def __init__(self, w: int, h: int, ss: int = SS):
        self.ss = ss
        self.img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        s = self.ss
        return [(x * s, y * s) for x, y in pts]

    def blob(self, cx, cy, rx, ry, fill, outline=None, w=_OW,
             wobble=0.0, phase=0.0, n=84):
        pts = []
        for i in range(n):
            a = 2.0 * math.pi * i / n
            k = 1.0 + wobble * math.sin(3.0 * a + phase) + 0.5 * wobble * math.sin(5.0 * a - phase)
            pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
        sp = self._p(pts)
        self.d.polygon(sp, fill=fill)
        if outline is not None:
            self.d.line(sp + [sp[0]], fill=outline,
                        width=max(1, int(round(w * self.ss))), joint="curve")
        return pts

    def capsule(self, p0, p1, width, fill, outline=None, ow=_OW):
        ss = self.ss

        def stroke(color, wpx):
            self.d.line(self._p([p0, p1]), fill=color,
                        width=max(1, int(round(wpx * ss))), joint="curve")
            rr = wpx * ss * 0.5
            for p in (p0, p1):
                x, y = p[0] * ss, p[1] * ss
                self.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=color)

        if outline is not None:
            stroke(outline, width + 2.0 * ow)
        stroke(fill, width)

    def line(self, p0, p1, color, w=2.4):
        self.d.line(self._p([p0, p1]), fill=color,
                    width=max(1, int(round(w * self.ss))), joint="curve")

    def arc(self, cx, cy, rx, ry, a0, a1, color, w=2.4):
        ss = self.ss
        self.d.arc([(cx - rx) * ss, (cy - ry) * ss, (cx + rx) * ss, (cy + ry) * ss],
                   a0, a1, fill=color, width=max(1, int(round(w * ss))))

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, w=_OW):
        ss = self.ss
        box = [(cx - rx) * ss, (cy - ry) * ss, (cx + rx) * ss, (cy + ry) * ss]
        self.d.ellipse(box, fill=fill, outline=outline,
                       width=max(1, int(round(w * ss))) if outline else 0)

    def paste(self, layer: "Pen", dx: float, dy: float, angle: float = 0.0,
              cx: float | None = None, cy: float | None = None):
        img = layer.img
        if abs(angle) > 0.01:
            c = ((cx if cx is not None else layer.img.width / self.ss / 2) * self.ss,
                 (cy if cy is not None else layer.img.height / self.ss / 2) * self.ss)
            img = img.rotate(-angle, resample=Image.BICUBIC, center=c)
        self.img.paste(img, (int(dx * self.ss), int(dy * self.ss)), img)


EAR_R = 18.5
EAR_OFF = (40.0, 36.5)


def _head_layer(pose: Pose) -> Pen:
    B = 156
    c = B / 2.0
    pen = Pen(B, B)

    for sx in (-1, 1):
        ex, ey = c + sx * EAR_OFF[0], c - EAR_OFF[1]
        pen.blob(ex, ey, EAR_R, EAR_R, FUR, OUTLINE, _OW)
        pen.blob(ex + sx * 3.2, ey + 2.6, 12.0, 11.0, EAR_IN, OUTLINE, 2.6)

    pen.blob(c, c, HEAD_R, HEAD_R * 0.99, FUR, OUTLINE, _OW)

    pen.blob(c, c + 16.5, 23.5, 17.0, WHITE)
    pen.blob(c, c + 5.5, 9.6, 6.8, NOSE)

    for sx in (-1, 1):
        _eye(pen, c + sx * 20.0, c - 5.5, pose)

    _mouth(pen, c, c + 15.5, pose)
    return pen


def _eye(pen: Pen, x: float, y: float, pose: Pose):
    m = pose.eye
    dx = pose.eye_dx * 2.4
    dy = pose.eye_dy * 1.8
    ex, ey = x + dx, y + dy
    if m == "closed":
        pen.arc(ex, ey + 0.6, 6.6, 4.4, 200, 340, OUTLINE, 2.8)
    elif m == "x":
        pen.line((ex - 5.4, ey - 5.4), (ex + 5.4, ey + 5.4), OUTLINE, 2.9)
        pen.line((ex - 5.4, ey + 5.4), (ex + 5.4, ey - 5.4), OUTLINE, 2.9)
    elif m == "wide":
        pen.ellipse(ex, ey, 7.2, 7.6, WHITE, OUTLINE, 2.2)
        pen.ellipse(ex, ey + 0.4, 3.4, 3.6, OUTLINE)
    else:
        ry = 5.4 * max(0.10, pose.blink)
        pen.ellipse(ex, ey, 5.4, ry, OUTLINE)
        if m == "half" and pose.blink > 0.5:
            pen.ellipse(ex, ey - ry * 0.44, 5.9, ry * 0.46, FUR)


def _mouth(pen: Pen, cx: float, y: float, pose: Pose):
    m = pose.mouth
    if m == "open":
        o = max(0.35, pose.mouth_open)
        pen.ellipse(cx, y + 1.6 * o, 6.2 * (0.7 + 0.3 * o), 5.2 * o,
                    (96, 44, 40, 255), OUTLINE, 1.8)
    elif m == "frown":
        pen.arc(cx, y + 3.2, 6.4, 4.0, 200, 340, OUTLINE, 2.6)
    elif m == "wave":
        pts = [(cx - 6.2, y), (cx - 3.1, y + 1.8), (cx, y - 0.2),
               (cx + 3.1, y + 1.8), (cx + 6.2, y)]
        pen.d.line(pen._p(pts), fill=OUTLINE,
                   width=max(1, int(round(2.4 * pen.ss))), joint="curve")
    else:
        pen.arc(cx - 5.0, y, 5.0, 4.2, 12, 168, OUTLINE, 2.7)
        pen.arc(cx + 5.0, y, 5.0, 4.2, 12, 168, OUTLINE, 2.7)


def render_bear(pose: Pose) -> Image.Image:
    pen = Pen(W, H)
    fy = FY + pose.bob

    if pose.shadow > 0.02:
        a = int(max(0, min(255, 52 * pose.shadow)))
        pen.ellipse(CX, FY + 3.0, 42.0, 7.0, (40, 20, 8, a))

    torso_ry = 33.0 * pose.squash
    torso_rx = 41.0 * (1.0 + (1.0 - pose.squash) * 0.26)
    torso_cy = (fy - 13.0) - torso_ry
    torso_top = torso_cy - torso_ry

    if pose.sit:
        for sx in (-1, 1):
            hip = (CX + sx * 17.0, fy - 22.0)
            foot = (CX + sx * 32.0, fy - 10.0)
            pen.capsule(hip, foot, 17.0, FUR, OUTLINE, _OW)
    else:
        for i, sx in enumerate((-1, 1)):
            ph = pose.leg_phase + (0.0 if i == 0 else math.pi)
            lift = max(0.0, math.sin(ph)) * (10.0 if pose.walking else 0.0)
            swing = math.sin(ph) * (9.0 if pose.walking else 0.0)
            hip = (CX + sx * 17.0, fy - 34.0)
            foot = (CX + sx * 18.0 + swing, fy - 9.0 - lift)
            pen.capsule(hip, foot, 17.0, FUR, OUTLINE, _OW)

    pen.blob(CX, torso_cy, torso_rx, torso_ry, FUR, OUTLINE, _OW, wobble=0.012, phase=0.4)
    pen.blob(CX, torso_cy + 4.0, torso_rx * 0.60, torso_ry * 0.66, WHITE)

    for i, sx in enumerate((-1, 1)):
        sh = (CX + sx * 30.0, torso_cy - torso_ry * 0.30)
        swing = math.sin(pose.leg_phase + (0.0 if i == 0 else math.pi)) * pose.arm_swing
        theta = 0.30 + pose.arm_spread * 1.20 + swing * 0.40
        L = 30.0
        paw = (sh[0] + sx * math.sin(theta) * L, sh[1] + math.cos(theta) * L)
        pen.capsule(sh, paw, 18.0, FUR, OUTLINE, _OW)

    head_cx = CX
    head_cy = fy - 104.0 + pose.head_bob
    hl = _head_layer(pose)
    c = 78.0
    pen.paste(hl, head_cx - c, head_cy - c, angle=pose.head_tilt, cx=c, cy=c)

    if pose.sweat > 0.02:
        a = int(max(0, min(255, 225 * pose.sweat)))
        hx, hy = head_cx + 36.0, head_cy - 30.0
        pen.blob(hx, hy, 5.4, 6.6, (150, 205, 235, a), None)
        pen.blob(hx - 1.4, hy - 2.2, 1.7, 2.1, (255, 255, 255, a))

    img = pen.img
    if abs(pose.tilt) > 0.01:
        img = img.rotate(-pose.tilt, resample=Image.BICUBIC, center=(CX * SS, FY * SS))
    img = img.resize((W, H), Image.LANCZOS)

    if pose.zzz > 0:
        img = _draw_zzz(img, head_cx, head_cy, pose.zzz)
    if pose.alpha < 0.999:
        img = _apply_alpha(img, pose.alpha)
    return img


def _draw_zzz(img: Image.Image, hx: float, hy: float, phase: float) -> Image.Image:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = _font(17)
    for i in range(3):
        t = (phase + i * 0.34) % 1.0
        x = hx + 30.0 + 20.0 * t
        y = hy - 44.0 - 34.0 * t
        a = int(255 * (1.0 - t) * 0.9)
        d.text((x, y), "z", font=font, fill=(51, 18, 8, a))
    return Image.alpha_composite(img, layer)


def _apply_alpha(img: Image.Image, a: float) -> Image.Image:
    a = max(0.0, min(1.0, a))
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}
_FONT_PATHS = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
]


def _font(size: int):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for p in _FONT_PATHS:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _FONT_CACHE[size] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def _wrap(text: str, font, max_w: float) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if font.getlength(trial) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_bubble(img: Image.Image, text: str, alpha: float = 1.0,
                tail_x: float | None = None, bottom: float | None = None) -> Image.Image:
    if not text or alpha <= 0.01:
        return img
    font = _font(16)
    pad_x, pad_y, lh = 11, 8, 22
    max_w = W - 2 * pad_x - 12
    lines = _wrap(text, font, max_w)
    tw = max(font.getlength(l) for l in lines)
    bw = min(W - 8, tw + 2 * pad_x)
    bh = len(lines) * lh + 2 * pad_y
    bx = (W - bw) / 2.0
    by = max(4.0, (BUBBLE_BOTTOM if bottom is None else bottom) - bh)

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=13,
                        fill=BUBBLE_BG, outline=OUTLINE, width=2)
    tx = tail_x if tail_x is not None else W / 2.0
    tx = max(bx + 18, min(bx + bw - 18, tx))
    d.polygon([(tx - 8, by + bh), (tx + 8, by + bh), (tx, by + bh + 13)],
              fill=BUBBLE_BG, outline=OUTLINE, width=2)
    d.rectangle([tx - 7, by + bh - 5, tx + 7, by + bh + 1], fill=BUBBLE_BG)

    for i, l in enumerate(lines):
        lw = font.getlength(l)
        d.text(((W - lw) / 2.0, by + pad_y + i * lh), l, font=font, fill=(58, 30, 12, 255))

    if alpha < 0.999:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    return Image.alpha_composite(img, layer)


def _preview(path: str = "preview.png"):
    poses = [
        ("idle", Pose()),
        ("walk", Pose(walking=True, leg_phase=0.9, arm_swing=1.0, eye="open")),
        ("sit", Pose(sit=True, eye="half", head_bob=1.5)),
        ("sleep", Pose(eye="closed", mouth="wave", squash=1.05, zzz=0.2, head_bob=3)),
        ("fall", Pose(eye="wide", arm_spread=0.9, mouth="open", mouth_open=1.0, sweat=1.0)),
        ("dizzy", Pose(eye="x", mouth="frown", tilt=7)),
    ]
    tiles = []
    for name, p in poses:
        im = render_bear(p)
        if name == "idle":
            im = draw_bubble(im, "今天也是没什么用的一天")
        tiles.append(im)
    gw = 3
    rows = (len(tiles) + gw - 1) // gw
    sheet = Image.new("RGBA", (W * gw, H * rows), (240, 236, 230, 255))
    for i, im in enumerate(tiles):
        sheet.alpha_composite(im, ((i % gw) * W, (i // gw) * H))
    sheet.save(path)
    return path


if __name__ == "__main__":
    print(_preview())
