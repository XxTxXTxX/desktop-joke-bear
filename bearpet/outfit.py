"""换装系统：按"角色"重映射图集的调色板。

图集是平涂 + 抗锯齿边的插画，直接按色值替换会留下锯齿残影。这里先把整张图集
量化成 256 色索引图（一次，误差 <1/255），再把每个调色板条目按 HSV 归类到
"角色"（描边 / 身体 / 皇冠 / 披风 / 饰件），最后按角色的目标色重新生成调色板。
换装 = 换一张调色板 + 一次 P→RGBA 转换，帧缓存按 (outfit, state, frame) 维度。

重映射公式（保留原图的明暗层次）：
    k = v_src / v_base            # 相对亮度
    k <= 1 → new = target * k     # 暗部（向描边过渡）
    k >  1 → new = lerp(target, 白色, (k-1)/(1/255 - v_base))  # 亮部（向白过渡）
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

from PIL import Image

# ---------------------------------------------------------------- 角色
OUTLINE, BODY, CROWN, CAPE, ACCENT, METAL = "outline", "body", "crown", "cape", "accent", "metal"


def classify(r: int, g: int, b: int) -> str:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue = h * 360.0
    if s < 0.10 and v > 0.55:
        return BODY                      # 白色身体
    if v < 0.28:
        if s < 0.55:
            return OUTLINE               # 纯黑描边
        # 饱和色的暗部：按色相归到对应角色
    if s >= 0.35:
        if hue < 22 or hue >= 338:
            return CAPE
        if 32 <= hue <= 72:
            return CROWN
        if 150 <= hue <= 265:
            return ACCENT
    if v < 0.32:
        return OUTLINE
    return METAL


TARGET_ROLE = {
    BODY: "body", OUTLINE: "outline", CROWN: "crown",
    CAPE: "cape", ACCENT: "accent", METAL: "metal",
}


@dataclass
class Outfit:
    id: str
    name: str
    body: tuple[int, int, int]
    outline: tuple[int, int, int]
    crown: tuple[int, int, int]
    cape: tuple[int, int, int]
    accent: tuple[int, int, int]
    metal: tuple[int, int, int]
    spark: tuple[int, int, int]
    desc: str = ""

    def color(self, role: str) -> tuple[int, int, int]:
        return getattr(self, role)


# ---------------------------------------------------------------- 预设
OUTFITS: list[Outfit] = [
    Outfit("classic", "原版",
           body=(255, 255, 255), outline=(26, 20, 22), crown=(255, 205, 45),
           cape=(232, 52, 56), accent=(96, 190, 240), metal=(70, 74, 82),
           spark=(255, 226, 120), desc="戴金冠、红披风、冰剑的白熊"),
    Outfit("caramel", "焦糖",
           body=(232, 168, 92), outline=(92, 52, 26), crown=(255, 200, 70),
           cape=(255, 235, 205), accent=(122, 214, 255), metal=(120, 90, 60),
           spark=(255, 214, 140), desc="蜂蜜色毛 + 奶油披风"),
    Outfit("sakura", "樱花",
           body=(255, 240, 244), outline=(120, 60, 80), crown=(255, 176, 200),
           cape=(255, 111, 145), accent=(255, 208, 224), metal=(150, 100, 120),
           spark=(255, 170, 200), desc="粉熊 + 樱花披风"),
    Outfit("midnight", "午夜",
           body=(104, 112, 138), outline=(20, 22, 34), crown=(196, 206, 226),
           cape=(46, 58, 92), accent=(120, 232, 255), metal=(60, 66, 84),
           spark=(130, 200, 255), desc="灰蓝熊 + 银冠 + 深蓝披风"),
    Outfit("obsidian", "黑金",
           body=(58, 58, 62), outline=(12, 12, 14), crown=(255, 200, 60),
           cape=(28, 28, 32), accent=(255, 210, 90), metal=(40, 40, 44),
           spark=(255, 190, 70), desc="黑熊 + 金冠 + 金披风"),
    Outfit("cyber", "赛博",
           body=(198, 232, 255), outline=(30, 36, 70), crown=(124, 249, 255),
           cape=(122, 92, 255), accent=(255, 79, 216), metal=(50, 56, 96),
           spark=(180, 120, 255), desc="冷光蓝熊 + 霓虹披风"),
]

BY_ID = {o.id: o for o in OUTFITS}
DEFAULT = OUTFITS[0]


# ---------------------------------------------------------------- 调色板重映射
class PaletteMapper:
    """把量化后的索引图集按角色重新上色，结果按 outfit id 缓存。"""

    def __init__(self, atlas_p: Image.Image):
        self.atlas_p = atlas_p
        self.base_palette = bytes(atlas_p.getpalette()[:768])
        self.roles: dict[int, str] = {}
        self.bases: dict[str, tuple[float, float, float]] = {}
        self._compute_roles()
        self._cache: dict[str, Image.Image] = {}
        self._cache_order: list[str] = []

    def _compute_roles(self):
        pal = self.base_palette
        for i in range(256):
            r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
            self.roles[i] = classify(r, g, b)
        # 每个角色的代表色 = 该角色里出现最多（近似为最亮最饱和）的颜色
        stats: dict[str, list[tuple[int, int, int, float]]] = {}
        hist = self.atlas_p.histogram()[:256]
        for i in range(256):
            r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
            role = self.roles[i]
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            stats.setdefault(role, []).append((i, hist[i], v, s))
        for role, items in stats.items():
            # 用"出现最多的中心色"作为基准亮度
            items.sort(key=lambda t: -t[1])
            _i, _n, v, _s = items[0]
            self.bases[role] = (v, items[0][3])

    def palette_for(self, outfit: Outfit) -> bytes:
        pal = bytearray(self.base_palette)
        for i in range(256):
            role = self.roles[i]
            r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
            _h, _s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            v_base = self.bases.get(role, (v, 0.0))[0]
            if v_base <= 0.004:
                v_base = max(v, 0.004)
            target = outfit.color(role)
            k = v / v_base
            if k <= 1.0:
                nr, ng, nb = target[0] * k, target[1] * k, target[2] * k
            else:
                t = min(1.0, (k - 1.0) / max(0.10, 1.0 - v_base) * 1.4)
                nr = target[0] + (255 - target[0]) * t
                ng = target[1] + (255 - target[1]) * t
                nb = target[2] + (255 - target[2]) * t
            pal[i * 3] = max(0, min(255, int(round(nr))))
            pal[i * 3 + 1] = max(0, min(255, int(round(ng))))
            pal[i * 3 + 2] = max(0, min(255, int(round(nb))))
        return bytes(pal)

    def atlas_for(self, outfit: Outfit) -> Image.Image:
        got = self._cache.get(outfit.id)
        if got is not None:
            return got
        img = self.atlas_p.copy()
        img.putpalette(self.palette_for(outfit))
        if len(self._cache_order) >= 3:
            drop = self._cache_order.pop(0)
            self._cache.pop(drop, None)
        self._cache[outfit.id] = img
        self._cache_order.append(outfit.id)
        return img

    def role_report(self) -> str:
        lines = ["role        base_v  base_s  pixels"]
        hist = self.atlas_p.histogram()[:256]
        for role in (OUTLINE, BODY, CROWN, CAPE, ACCENT, METAL):
            v, s = self.bases.get(role, (0.0, 0.0))
            n = sum(hist[i] for i in range(256) if self.roles[i] == role)
            lines.append(f"{role:10s}  {v:5.2f}   {s:5.2f}   {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------- 自检
def _demo(path: str = "outfits.png"):
    from . import sprite
    base = Image.open(sprite.DEFAULT_SHEET).convert("RGBA")
    atlas_p = base.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT)
    alpha = base.getchannel("A")
    mp = PaletteMapper(atlas_p)
    print(mp.role_report())

    W, H = 240, 260
    out = Image.new("RGBA", (W * len(OUTFITS), H), (232, 228, 222, 255))
    for i, o in enumerate(OUTFITS):
        cell = mp.atlas_for(o).crop((0 * 192, 0, 192, 208)).convert("RGBA")
        cell.putalpha(alpha.crop((0, 0, 192, 208)))
        out.alpha_composite(cell, (i * W + (W - 192) // 2, 20))
    out.save(path)
    return path


if __name__ == "__main__":
    print(_demo())
