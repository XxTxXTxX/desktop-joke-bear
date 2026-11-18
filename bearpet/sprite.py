"""Petdex / Codex 精灵图集读取、换装与播放。

图集规格（来自 petdex 的 src/lib/pet-states.ts 与 assets.petdex.dev）：
    整表 1536×1872，8 列 × 9 行，每格 192×208，行 = 状态，列 = 帧。

行序与帧数：
    row 0 idle(6) 1 running-right(8) 2 running-left(8) 3 waving(4) 4 jumping(5)
    row 5 failed(8) 6 waiting(6) 7 running(6, 抱笔记本) 8 review(6, 托腮)

换装走 PaletteMapper：整表量化成 256 色索引图后，按角色重生成调色板，
所以换一身衣服不需要额外的美术资源。
"""
from __future__ import annotations

import os
from collections import OrderedDict

from PIL import Image, ImageDraw

from . import outfit as omod

CELL_W, CELL_H = 192, 208
GRID_COLS, GRID_ROWS = 8, 9

# 画布（= 窗口）尺寸与摆位
W, H = 300, 340
CELL_X = (W - CELL_W) // 2          # 54
CELL_Y = H - 6 - CELL_H             # 126
FEET_IN_CELL = 203                  # 图集里脚底所在的行号
GROUND = CELL_Y + FEET_IN_CELL      # 329：窗口内的脚底线

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SHEET = os.path.join(BASE, "assets", "sprite.png")

# state -> (row, frames_in_row, loop_ms, frame_subset)
STATES: dict[str, tuple[int, int, int, tuple[int, ...] | None]] = {
    "idle":          (0, 6, 1100, None),
    "running-right": (1, 8, 1060, None),
    "running-left":  (2, 8, 1060, None),
    "waving":        (3, 4, 700, None),
    "jumping":       (4, 5, 840, None),
    "failed":        (5, 8, 1220, None),
    "waiting":       (6, 6, 1010, None),
    "running":       (7, 6, 820, None),
    "review":        (8, 6, 1030, None),
    # 合成状态：图集里没有"睡觉"，用 failed 最后两帧（躺平）慢放
    "sleep":         (5, 8, 2600, (6, 7)),
    # 发呆：只用前 4 帧（还没开始掉眼泪）
    "sad":           (5, 8, 1400, (0, 1, 2, 3)),
}

FRAME_CACHE = 90        # 帧缓存条数（每帧 192×208×4 ≈ 160 KB）


class SpriteSheet:
    def __init__(self, path: str = DEFAULT_SHEET):
        self.path = path
        src = Image.open(path).convert("RGBA")
        self.src_size = src.size
        self.atlas_p = src.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT)
        self.alpha = src.getchannel("A")
        self.mapper = omod.PaletteMapper(self.atlas_p)
        # 恒等灰度调色板副本：转 L 后像素值 == 调色板索引，供换装求锚点用
        ident = bytes(b for i in range(256) for b in (i, i, i))
        self.idx_atlas = self.atlas_p.copy()
        self.idx_atlas.putpalette(ident)
        self.outfit: omod.Outfit = omod.DEFAULT
        self.wear: dict[str, str] = {}
        self._frames: OrderedDict[tuple[str, str, int], Image.Image] = OrderedDict()
        self._anchors: dict[tuple[str, int], object] = {}

    # ------------------------------------------------------------ 换装
    def set_outfit(self, o: omod.Outfit):
        self.outfit = o

    # ------------------------------------------------------------ 帧
    def sequence(self, state: str) -> tuple[int, ...]:
        row, frames, _ms, use = STATES[state]
        return use if use else tuple(range(frames))

    def frame(self, state: str, idx: int, outfit: omod.Outfit | None = None) -> Image.Image:
        o = outfit or self.outfit
        key = (o.id, state, idx)
        got = self._frames.get(key)
        if got is not None:
            self._frames.move_to_end(key)
            return got
        row = STATES[state][0]
        seq = self.sequence(state)
        col = seq[idx % len(seq)]
        box = (col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H)
        atlas = self.mapper.atlas_for(o)
        cell = atlas.crop(box).convert("RGBA")
        cell.putalpha(self.alpha.crop(box))
        self._frames[key] = cell
        if len(self._frames) > FRAME_CACHE:
            self._frames.popitem(last=False)
        return cell

    def index_at(self, state: str, t_ms: float) -> int:
        _row, _frames, ms, _use = STATES[state]
        n = len(self.sequence(state))
        return int((t_ms % ms) / ms * n) % n

    def frame_at(self, state: str, t_ms: float, outfit: omod.Outfit | None = None) -> Image.Image:
        return self.frame(state, self.index_at(state, t_ms), outfit)

    def anchors(self, state: str, idx: int):
        key = (state, idx)
        got = self._anchors.get(key)
        if got is None:
            from . import garment
            got = garment.compute_anchors(self, state, idx)
            self._anchors[key] = got
        return got

    # ------------------------------------------------------------ 合成
    def render(self, state: str, t_ms: float, shadow: float = 1.0,
               outfit: omod.Outfit | None = None, wear: dict[str, str] | None = None,
               scale: float = 1.0) -> Image.Image:
        o = outfit or self.outfit
        w = self.wear if wear is None else wear
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if shadow > 0.02:
            d = ImageDraw.Draw(img)
            a = int(max(0, min(255, 48 * shadow)))
            rx = 44.0 * (0.7 + 0.3 * shadow) * scale
            d.ellipse([W / 2 - rx, GROUND - 4, W / 2 + rx, GROUND + 10], fill=(38, 28, 18, a))
        idx = self.index_at(state, t_ms)
        cell = self.frame(state, idx, o)
        if w:
            from . import garment
            cell = garment.apply_wear(cell, self.anchors(state, idx), w, t_ms / 1000.0)
        if abs(scale - 1.0) > 0.002:
            nw, nh = max(1, int(CELL_W * scale)), max(1, int(CELL_H * scale))
            cell = cell.resize((nw, nh), Image.LANCZOS)
            dx = CELL_X + (CELL_W - nw) // 2
            dy = CELL_Y + (CELL_H - nh)
        else:
            dx, dy = CELL_X, CELL_Y
        img.alpha_composite(cell, (dx, dy))
        return img


# ---------------------------------------------------------------- 预览
def _preview(path: str = "atlas_preview.png"):
    sh = SpriteSheet()
    names = ["idle", "running-right", "running-left", "waving",
             "jumping", "failed", "waiting", "running", "review", "sleep"]
    cols = 5
    rows = (len(names) + cols - 1) // cols
    out = Image.new("RGBA", (W * cols, H * rows), (238, 234, 228, 255))
    for i, n in enumerate(names):
        out.alpha_composite(sh.render(n, 200), ((i % cols) * W, (i // cols) * H))
    out.save(path)
    return path


if __name__ == "__main__":
    print(_preview())
