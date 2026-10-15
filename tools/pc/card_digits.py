"""The anime frame's ATK/DFD digits, drawn from a font.

One PNG for the engine (src/pc/cards/card_layout_art.h's digit strip):
5 x 4 cells of 40 x 48 texels (200 x 192, one texture page), digit d in
column d % 5, row d / 5, the same ten greyed (the stat the attack screen
dims) two rows further down: 4 texels a card unit, one a screen pixel at
Internal 4x, saved stretched to 256 x 256 (OUT_SIZE: OpenGL draws a bank
picture at Internal 2x and up only with power-of-two sides), anti-aliased against the stat box's own color, in the
same 10 x 12 unit proportion the layout draws a digit at ("digits" in
card_layout). The font is the maker's own file (a Yu-Gi-Oh. Matrix Regular
Small Caps .ttf, the card game's ATK/DEF font): it is read from --digit-font
and never committed.
"""
from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 5, 4   # the ten digits (two rows), then the same ten greyed (two rows)
DIM = 0.55           # how far the greyed digits' ink is mixed into the box color
CELL_W, CELL_H = 40, 48
GLYPH_H = 40          # the digits' height in texels: 10 of the box's 17 units (4 texels a unit)
LIFT = 3              # texels the digits sit above the cell's middle: the stat boxes' cream is about half a unit above their studs' centre
INK = (22, 14, 6)
PAPER = (242, 226, 169)   # what the stat box is, for the edge pixels
SUPER = 16
OUT_SIZE = (256, 256)  # the saved PNG: power-of-two sides; the engine reads the cells in proportion
STRETCH = 1.25        # the game draws these digits wide: a zero is about as wide as it is tall


def paper_of(frame_png):
    """The stat box's own color (its middle, between the digits' rows), where the PNG is the monster frame."""
    import numpy as np
    import card_frame_window as W
    centres = W.stat_box_centres(frame_png)
    if not centres:
        return PAPER
    im = np.array(Image.open(frame_png).convert("RGB")).astype(float)
    kx, ky = im.shape[1] / W.CARD_SIZE[0], im.shape[0] / W.CARD_SIZE[1]
    c = centres["atk"]
    box = im[int((c["y"] - 3) * ky):int((c["y"] + 3) * ky), int((c["x"] - 18) * kx):int((c["x"] + 18) * kx)]
    return tuple(int(v) for v in box.reshape(-1, 3).mean(axis=0))


def render(font_path, out_path, stretch=STRETCH, paper=None):
    probe = ImageFont.truetype(font_path, 200)
    top, bottom = probe.getbbox("0", anchor="ls")[1::2]   # the zero's height: all the digits are centred on it
    size = 200 * GLYPH_H * SUPER / (bottom - top)
    font = ImageFont.truetype(font_path, round(size))
    paper = paper or PAPER
    sheet = Image.new("RGBA", (COLS * CELL_W, ROWS * CELL_H), (0, 0, 0, 0))
    for d in range(10):
        mask = Image.new("L", (CELL_W * SUPER, CELL_H * SUPER), 0)
        draw = ImageDraw.Draw(mask)
        box = font.getbbox(str(d), anchor="ls")
        x = (CELL_W * SUPER - (box[2] - box[0])) // 2 - box[0]
        base = (CELL_H * SUPER - GLYPH_H * SUPER) // 2 - LIFT * SUPER - round(top * size / 200)
        draw.text((x, base), str(d), font=font, fill=255, anchor="ls")
        wide = mask.resize((round(mask.width * stretch), mask.height), Image.LANCZOS)
        left = (wide.width - mask.width) // 2
        alpha = wide.crop((left, 0, left + mask.width, mask.height)).resize((CELL_W, CELL_H), Image.BOX)
        for dim in (0, 1):
            ink = tuple(INK[i] * (1 - DIM * dim) + paper[i] * DIM * dim for i in range(3))
            cell = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
            px, src = cell.load(), alpha.load()
            for yy in range(CELL_H):
                for xx in range(CELL_W):
                    a = src[xx, yy] / 255
                    if a >= 0.04:   # the game's texture has one transparent index, no partial alpha: the edge is
                        # blended into the box's own color instead
                        px[xx, yy] = tuple(round(ink[i] * a + paper[i] * (1 - a)) for i in range(3)) + (255,)
            sheet.paste(cell, (d % COLS * CELL_W, (d // COLS + 2 * dim) * CELL_H))
    sheet = sheet.resize(OUT_SIZE, Image.LANCZOS)
    sheet.save(out_path)
    return sheet


if __name__ == "__main__":
    import os
    import sys
    frame = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hd_recipes", "anime_frame_monster.png")
    render(sys.argv[1], sys.argv[2], paper=paper_of(frame) if os.path.isfile(frame) else None)
