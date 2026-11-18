from __future__ import annotations

from PIL import Image, ImageDraw

GW, GH = 48, 42
K = 6

CLEAR = (0, 0, 0, 0)
INK = (26, 14, 8, 255)
FUR = (255, 255, 255, 255)
SHADE = (226, 232, 238, 255)
CROWN = (255, 205, 45, 255)
GEM = (96, 190, 240, 255)
CAPE = (232, 52, 56, 255)
CAPE_D = (176, 32, 38, 255)
CURSOR = (250, 250, 252, 255)
PINK = (255, 168, 178, 255)


def _px(d, x, y, c):
    d.point((x, y), fill=c)


def _rect(d, x0, y0, x1, y1, c):
    d.rectangle([x0, y0, x1, y1], fill=c)


def _disc(d, cx, cy, r, c):
    for y in range(-r, r + 1):
        for x in range(-r, r + 1):
            if x * x + y * y <= r * r + r * 0.6:
                d.point((cx + x, cy + y), fill=c)


def build() -> Image.Image:
    img = Image.new("RGBA", (GW, GH), CLEAR)
    d = ImageDraw.Draw(img)

    arrow = [(29, 18), (29, 39), (34, 34), (38, 41), (43, 38), (39, 31), (45, 31)]
    d.polygon(arrow, fill=CURSOR, outline=INK)

    d.polygon([(34, 8), (46, 13), (46, 25), (35, 22)], fill=CAPE, outline=INK)
    for y in range(14, 24, 3):
        _rect(d, 40, y, 45, y, CAPE_D)

    d.ellipse([13, 8, 39, 24], fill=FUR, outline=INK)
    _rect(d, 18, 20, 33, 22, SHADE)

    _rect(d, 15, 22, 17, 28, INK)
    _rect(d, 15, 22, 16, 27, FUR)
    _rect(d, 25, 22, 27, 30, INK)
    _rect(d, 26, 22, 26, 29, FUR)
    _rect(d, 19, 21, 22, 24, INK)
    _rect(d, 20, 21, 21, 23, FUR)

    _disc(d, 11, 13, 9, INK)
    _disc(d, 11, 13, 8, FUR)
    _disc(d, 4, 5, 3, INK)
    _disc(d, 4, 5, 2, FUR)
    _disc(d, 16, 4, 3, INK)
    _disc(d, 16, 4, 2, FUR)

    d.polygon([(5, 4), (7, -1), (9, 2), (11, -2), (13, 2), (15, -1), (17, 4)],
              fill=CROWN, outline=INK)

    _rect(d, 8, 13, 10, 13, INK)
    _rect(d, 14, 13, 16, 13, INK)
    _rect(d, 6, 17, 8, 17, PINK)
    _px(d, 12, 17, INK)
    _px(d, 11, 18, INK)
    _px(d, 13, 18, INK)

    out = Image.new("RGBA", (GW, GH + 3), CLEAR)
    out.alpha_composite(img, (0, 3))
    return out.resize((GW * K, (GH + 3) * K), Image.NEAREST)


_CACHE: Image.Image | None = None


def sprite() -> Image.Image:
    global _CACHE
    if _CACHE is None:
        _CACHE = build()
    return _CACHE


def render(scale: float = 1.0) -> Image.Image:
    img = sprite()
    if abs(scale - 1.0) < 0.01:
        return img
    w, h = img.size
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


if __name__ == "__main__":
    render().save("pixel_bear.png")
    print("pixel_bear.png", render().size)
