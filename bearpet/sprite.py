from __future__ import annotations

import os
from collections import OrderedDict

from PIL import Image, ImageDraw

from . import outfit as omod

CELL_W, CELL_H = 192, 208
GRID_COLS, GRID_ROWS = 8, 20

W, H = 300, 340
CELL_X = (W - CELL_W) // 2
CELL_Y = H - 6 - CELL_H
FEET_IN_CELL = 203
GROUND = CELL_Y + FEET_IN_CELL

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SHEET = os.path.join(BASE, "assets", "sprite.png")
PETDEX_V2_SHEET = os.path.join(BASE, "assets", "petdex", "jokebear-codexpet", "spritesheet.webp")
V1_ROWS = 9

# row >= V1_ROWS points into PETDEX_V2_SHEET (row - V1_ROWS).
STATES: dict[str, tuple[int, int, int, tuple[int, ...] | None]] = {
    "idle":              (0, 6, 1100, None),
    "running-right":     (1, 8, 1060, None),
    "running-left":      (2, 8, 1060, None),
    "waving":            (3, 4, 700, None),
    "jumping":           (4, 5, 840, None),
    "failed":            (5, 8, 1220, None),
    "waiting":           (6, 6, 1010, None),
    "running":           (7, 6, 820, None),
    "review":            (8, 6, 1030, None),
    "sleep":             (5, 8, 2600, (6, 7)),
    "sad":               (5, 8, 1400, (0, 1, 2, 3)),
    "typing-calm":       (V1_ROWS + 1, 8, 1060, None),
    "typing-frustrated": (V1_ROWS + 2, 8, 920, None),
    "coffee":            (V1_ROWS + 6, 6, 1010, None),
    "keyboard":          (V1_ROWS + 7, 6, 820, None),
    "burger":            (V1_ROWS + 8, 6, 1030, None),
    **{
        f"look-{i}": (V1_ROWS + 9 + (i // 8), 8, 1000, (i % 8,))
        for i in range(16)
    },
}

LOOK_STATES: tuple[str, ...] = tuple(f"look-{i}" for i in range(16))

FRAME_CACHE = 140


def _load_merged_sheet(path: str, v2_path: str = PETDEX_V2_SHEET) -> Image.Image:
    v1 = Image.open(path).convert("RGBA")
    if os.path.exists(v2_path):
        try:
            v2 = Image.open(v2_path).convert("RGBA")
            w = max(v1.width, v2.width)
            merged = Image.new("RGBA", (w, V1_ROWS * CELL_H + v2.height), (0, 0, 0, 0))
            merged.paste(v1, (0, 0))
            merged.paste(v2, (0, V1_ROWS * CELL_H))
            rgb = Image.new("RGB", merged.size, (0, 0, 0))
            rgb.paste(merged.convert("RGB"), mask=merged.getchannel("A"))
            return rgb, merged.getchannel("A")
        except Exception:
            pass
    rgb = Image.new("RGB", v1.size, (0, 0, 0))
    rgb.paste(v1.convert("RGB"), mask=v1.getchannel("A"))
    return rgb, v1.getchannel("A")


class SpriteSheet:
    def __init__(self, path: str = DEFAULT_SHEET, v2_path: str = PETDEX_V2_SHEET):
        self.path = path
        self.v2_path = v2_path
        rgb, alpha = _load_merged_sheet(path, v2_path)
        self.src_size = rgb.size
        self.has_v2 = rgb.height > V1_ROWS * CELL_H
        self.atlas_p = rgb.quantize(colors=256, method=Image.MEDIANCUT)
        self.alpha = alpha
        self.mapper = omod.PaletteMapper(self.atlas_p)
        ident = bytes(b for i in range(256) for b in (i, i, i))
        self.idx_atlas = self.atlas_p.copy()
        self.idx_atlas.putpalette(ident)
        self.outfit: omod.Outfit = omod.DEFAULT
        self.wear: dict[str, str] = {}
        self._frames: OrderedDict[tuple[str, str, int], Image.Image] = OrderedDict()
        self._anchors: dict[tuple[str, int], object] = {}

    def set_outfit(self, o: omod.Outfit):
        self.outfit = o

    def _resolve_state(self, state: str) -> str:
        if state not in STATES:
            return "idle"
        if not self.has_v2 and STATES[state][0] >= V1_ROWS:
            if state in ("typing-calm", "typing-frustrated", "keyboard"):
                return "running"
            if state in ("coffee", "burger"):
                return "waiting"
            return "idle"
        return state

    def sequence(self, state: str) -> tuple[int, ...]:
        state = self._resolve_state(state)
        row, frames, _ms, use = STATES[state]
        return use if use else tuple(range(frames))

    def frame(self, state: str, idx: int, outfit: omod.Outfit | None = None) -> Image.Image:
        state = self._resolve_state(state)
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
        state = self._resolve_state(state)
        _row, _frames, ms, _use = STATES[state]
        n = len(self.sequence(state))
        return int((t_ms % ms) / ms * n) % n

    def frame_at(self, state: str, t_ms: float, outfit: omod.Outfit | None = None) -> Image.Image:
        state = self._resolve_state(state)
        return self.frame(state, self.index_at(state, t_ms), outfit)

    def anchors(self, state: str, idx: int):
        state = self._resolve_state(state)
        key = (state, idx)
        got = self._anchors.get(key)
        if got is None:
            from . import garment
            got = garment.compute_anchors(self, state, idx)
            self._anchors[key] = got
        return got

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
