"""The campaign's scenes and large characters off the player's disc, as the
Tower tab's pickers show them (src/pc/tower/tower.h; notes/tower-mode.md,
Story). Made from WA_MRG.MRG when the tab asks, kept in memory only: no
picture of the disc's is written anywhere.

A scene (ScriptImage_RequestTransfer): records from WA sector 0x21D5 of 33
sectors (mode 0, ids 0x000-0x049), 81 (mode 1, 0x100-) and 113 (mode 2,
0x200-), the last sector the palette (256 x 4 colors), the others 64-word
columns of 256 rows at 8 bits. A mode-0 picture is 320 x 160: its left 256
texels in rows 0-159, its right 64 in words 64-95 (rows 0-79) and 96-127
(rows 80-159) of rows 160-239. Modes 1 and 2 are wider stills with their
own overlays; their thumbnail is the first 320 x 160 of the base picture.

A character (func_8003A560): 50 sectors from WA sector 15182 + id * 50, a
384 x 256 sheet at 8 bits (48 sectors, three 64-word columns), two rows of 256 colors and the parts
bank (DisplayEffect_BuildResourceObjects): expression -> piece -> frame ->
a stream whose first command names a sprite sheet of parts
(DisplayObject_RenderSpriteSheet). The thumbnail is expression 0 with its
three pieces (body, eyes, mouth), as it first comes in."""
from __future__ import annotations

from . import pngio

SECTOR = 2048
SCENE_BASE = 0x21D5
SCENE_MODES = ((0x21, 0, 50), (0x51, 0x672, 42), (0x71, 0x13BC, 13))   # stride, first, count
SCENE_COUNTS = (42, 42, 13)          # the ones with a picture
CHARACTER_BASE = 15182
EMPTY_CHARACTERS = (0x00, 0x05, 0x0B, 0x27, 0x28, 0x29)


def _color(word: int, index: int):
    return ((word & 31) << 3, (word >> 5 & 31) << 3, (word >> 10 & 31) << 3, 0 if index == 0 or word == 0 else 255)


def scene_ids():
    """Every scene of the disc's, as the tower names them (BCD ids)."""
    return [mode << 8 | (index // 10) << 4 | index % 10 for mode, count in enumerate(SCENE_COUNTS)
            for index in range(count)]


def scene_image(wa: bytes, scene: int):
    """Scene `scene`'s picture, 320 x 160 (None off the disc's end)."""
    mode, index = scene >> 8, ((scene >> 4) & 15) * 10 + (scene & 15)
    if mode > 2:
        return None
    stride, first, count = SCENE_MODES[mode]
    if index >= count:
        return None
    base = (SCENE_BASE + first + index * stride) * SECTOR
    palette = base + (stride - 1) * SECTOR
    if len(wa) < palette + 512:
        return None
    colors = [_color(wa[palette + 2 * i] | wa[palette + 2 * i + 1] << 8, i) for i in range(256)]

    def texel(column_x: int, row: int) -> int:
        column, x = divmod(column_x, 128)
        return wa[base + column * 16 * SECTOR + row * 128 + x]

    rgba = bytearray()
    for y in range(160):
        for x in range(320):
            if mode or x < 256:
                value = texel(x, y)
            else:
                value = texel(128 + (x - 256) + (64 if y >= 80 else 0), 160 + y % 80)
            rgba += bytes(colors[value])
    return pngio.Image(320, 160, bytes(rgba))


def _u16(bank: bytes, at: int) -> int:
    return bank[at] | bank[at + 1] << 8 if 0 <= at < len(bank) - 1 else 0


def character_image(wa: bytes, character: int):
    """Character `character`'s picture as it comes in (expression 0, its
    body, eyes and mouth), cut to what it covers; None for an empty one."""
    if character in EMPTY_CHARACTERS or not 0 < character <= 0x40:
        return None
    base = (CHARACTER_BASE + character * 50) * SECTOR
    if len(wa) < base + 50 * SECTOR:
        return None
    sheet, palette, bank = wa[base:base + 48 * SECTOR], base + 48 * SECTOR, wa[base + 49 * SECTOR:base + 50 * SECTOR]
    colors = [_color(wa[palette + 2 * i] | wa[palette + 2 * i + 1] << 8, i) for i in range(256)]
    parts = []
    level2 = _u16(bank, 0)
    for piece in range(3):
        level3 = _u16(bank, level2 + piece * 2) if level2 else 0
        stream = _u16(bank, level3) if level3 else 0
        if not stream or stream + 3 > len(bank):
            continue
        at = _u16(bank, stream + 1)
        if at + 4 > len(bank):
            continue
        count, flags = bank[at], bank[at + 1]
        for k in range(count):
            p = at + 4 + 6 * k
            if p + 6 > len(bank):
                break
            dx, dy, cell, size = bank[p], bank[p + 1], _u16(bank, p + 2), _u16(bank, p + 4)
            if flags & 0x10:
                dx |= (cell & 0xC000) >> 6
                dy |= (size & 0xC000) >> 6
                dx, dy = dx - 0x400 if dx & 0x200 else dx, dy - 0x400 if dy & 0x200 else dy
            else:
                dx, dy = dx - 256 if dx & 0x80 else dx, dy - 256 if dy & 0x80 else dy
            u, v = (cell & 31) * 8 + (((cell >> 10) & 7) * 256 if flags & 0xE0 else 0), ((cell >> 5) & 31) * 8
            parts.append((dx, dy, u, v, ((size >> 5) & 15) * 8 + 8, ((size >> 9) & 15) * 8 + 8))
    if not parts:
        return None
    left, top = min(p[0] for p in parts), min(p[1] for p in parts)
    width, height = max(p[0] + p[4] for p in parts) - left, max(p[1] + p[5] for p in parts) - top
    canvas = bytearray(width * height * 4)
    for dx, dy, u, v, w, h in parts:
        for y in range(h):
            for x in range(w):
                if u + x >= 384 or v + y >= 256:
                    continue
                column, tx = divmod(u + x, 128)       # 64-word columns of 256 rows, as they stream
                value = sheet[column * 16 * SECTOR + (v + y) * 128 + tx]
                if not value:
                    continue
                at = ((dy - top + y) * width + dx - left + x) * 4
                canvas[at:at + 4] = bytes(colors[value])
    return pngio.Image(width, height, bytes(canvas))
