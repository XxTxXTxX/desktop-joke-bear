"""变身特效：换装瞬间的"扫光 + 地面法阵 + 星屑"。

全部是逐帧程序化绘制，不占额外素材；扫光用 L 掩膜做 Image.composite，
两个版本的帧在图集里形状完全一致，所以换装看起来是"颜色从脚下漫上头顶"。
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from . import sprite

# 粒子表：角度、半径、延迟、大小（固定种子 → 每次变身同一套轨迹）
_RNG = random.Random(20261117)
PARTICLES = [
    (_RNG.uniform(0, math.tau), _RNG.uniform(0.35, 1.0),
     _RNG.uniform(0.0, 0.55), _RNG.uniform(3.0, 6.2))
    for _ in range(24)
]
DURATION = 0.95          # 变身总时长（秒）


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _star(d: ImageDraw.ImageDraw, x: float, y: float, r: float, fill):
    k = r * 0.34
    d.polygon([(x, y - r), (x + k, y - k), (x + r, y), (x + k, y + k),
               (x, y + r), (x - k, y + k), (x - r, y), (x - k, y - k)], fill=fill)


def render_morph(a: Image.Image, b: Image.Image, t: float,
                 spark: tuple[int, int, int]) -> Image.Image:
    """t∈[0,1]：0 = 旧装，1 = 新装。返回合成好的整窗画布。"""
    t = max(0.0, min(1.0, t))
    e = _smooth(t)
    W, H = a.size
    ground = sprite.GROUND
    cx = W / 2.0
    top = sprite.CELL_Y + 6.0

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ---- 1. 地面法阵：扩张的环 + 旋转刻度
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    fade = int(190 * (1.0 - e) ** 1.4)
    if fade > 3:
        rx = 26.0 + 72.0 * e
        ry = rx * 0.26
        rd.ellipse([cx - rx, ground - ry, cx + rx, ground + ry],
                   outline=spark + (fade,), width=3)
        rx2 = rx * 0.72
        rd.ellipse([cx - rx2, ground - ry * 0.72, cx + rx2, ground + ry * 0.72],
                   outline=spark + (int(fade * 0.6),), width=2)
        ang0 = e * 2.4
        for i in range(10):
            ang = ang0 + i * math.tau / 10
            x1 = cx + math.cos(ang) * rx * 0.86
            y1 = ground + math.sin(ang) * ry * 0.86
            x2 = cx + math.cos(ang) * rx
            y2 = ground + math.sin(ang) * ry
            rd.line([(x1, y1), (x2, y2)], fill=spark + (fade,), width=2)
    out.alpha_composite(ring)

    # ---- 2. 从下往上的扫光换色
    y_sweep = ground - (ground - top) * e
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([0, y_sweep, W, H], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(7))
    out.alpha_composite(Image.composite(b, a, mask))

    # ---- 3. 扫光边缘的一道亮线
    line = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line)
    strength = math.sin(math.pi * min(1.0, t * 1.05))
    if strength > 0.05 and 0 < y_sweep < H:
        w = int(220 * strength)
        ld.rounded_rectangle([cx - 66, y_sweep - 2, cx + 66, y_sweep + 2],
                             radius=2, fill=(255, 255, 255, w))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle(
            [cx - 78, y_sweep - 9, cx + 78, y_sweep + 9], radius=9,
            fill=spark + (int(150 * strength),))
        line.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6)))
    out.alpha_composite(line)

    # ---- 4. 星屑：从脚边升起、边升边淡
    parts = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(parts)
    for ang, rad, delay, size in PARTICLES:
        tt = (t - delay * 0.6) / (1.0 - delay * 0.45)
        if tt <= 0.0 or tt >= 1.0:
            continue
        alpha = int(255 * math.sin(math.pi * tt) ** 0.8)
        if alpha <= 4:
            continue
        px = cx + math.cos(ang) * (24 + 52 * rad) * (0.5 + tt)
        py = ground - 12 - 96 * tt * (0.5 + rad)
        _star(pd, px, py, size * (0.7 + 0.5 * math.sin(math.pi * tt)), spark + (alpha,))
        _star(pd, px, py, size * 0.42, (255, 255, 255, alpha))
    out.alpha_composite(parts)

    return out


def render_flash(img: Image.Image, t: float, spark: tuple[int, int, int]) -> Image.Image:
    """换装完成瞬间的一层柔光（t∈[0.6,1] 用）。"""
    strength = math.sin(math.pi * max(0.0, min(1.0, (t - 0.55) / 0.45)))
    if strength <= 0.03:
        return img
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cx, cy = img.width / 2, sprite.GROUND - 96
    ImageDraw.Draw(halo).ellipse([cx - 78, cy - 78, cx + 78, cy + 78],
                                 fill=spark + (int(70 * strength),))
    halo = halo.filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(halo, img)


def _demo(path: str = "morph.png"):
    from . import outfit as omod
    sh = sprite.SpriteSheet()
    a = sh.render("idle", 0, outfit=omod.BY_ID["classic"])
    b = sh.render("idle", 0, outfit=omod.BY_ID["cyber"])
    frames = []
    for i in range(6):
        t = i / 5.0
        frames.append(render_morph(a, b, t, omod.BY_ID["cyber"].spark))
    out = Image.new("RGBA", (sprite.W * len(frames), sprite.H), (232, 228, 222, 255))
    for i, f in enumerate(frames):
        out.alpha_composite(f, (i * sprite.W, 0))
    out.save(path)
    return path


if __name__ == "__main__":
    print(_demo())
