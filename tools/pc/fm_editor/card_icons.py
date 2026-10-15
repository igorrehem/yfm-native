"""The card's own small pictures off the disc, for the Cards tab's form: the
attribute balls (Light ... Wind, then Magic and Trap) and the level star of
the big card (func_80028B08: the card view package's sheet, here the
Library's in WA_MRG.MRG), and the sword and shield the duel's info bar puts
before ATK and DEF (its 8x8 letters ♂ and ♀, func_80035E20).

Each sheet is 4 bits a texel, 128 bytes a row; a palette entry is 15-bit
color, 0 transparent."""
from __future__ import annotations

import base64
import tkinter as tk

from . import pngio

CARD_SHEET, CARD_PALETTES = 0xEFE800, 0xF06800     # the Library's sheet (VRAM 960, 256) and palettes (256, 240)
BALL_PALETTE, STAR_PALETTE = 0x1E00, 0x1180
SMALL_FONT, SMALL_PALETTE = 0xB50000, 0xB60520     # the boot package's 8x8 letters and their white


def _picture(wa: bytes, base: int, u: int, v: int, width: int, height: int, palette: int):
    if len(wa) < max(base + (v + height) * 128, palette + 32):
        return None
    rgba = bytearray()
    for y in range(height):
        for x in range(width):
            tu = u + x
            index = wa[base + (v + y) * 128 + tu // 2] >> 4 * (tu & 1) & 15
            word = wa[palette + 2 * index] | wa[palette + 2 * index + 1] << 8
            rgba += bytes(((word & 31) << 3, (word >> 5 & 31) << 3, (word >> 10 & 31) << 3,
                           0 if index == 0 or word == 0 else 255))
    return pngio.Image(width, height, bytes(rgba)) if any(rgba[3::4]) else None


def attribute(wa: bytes, n: int):
    """Attribute n's ball (0 Light ... 5 Wind, 6 Magic, 7 Trap), 16 x 16."""
    return _picture(wa, CARD_SHEET, 16 * n, 128, 16, 16, CARD_PALETTES + BALL_PALETTE + 0x20 * n) \
        if 0 <= n < 8 else None


def level_star(wa: bytes):
    return _picture(wa, CARD_SHEET, 0, 144, 9, 9, CARD_PALETTES + STAR_PALETTE)


def sword(wa: bytes):
    return _picture(wa, SMALL_FONT, 208, 88, 8, 8, SMALL_PALETTE)


def shield(wa: bytes):
    return _picture(wa, SMALL_FONT, 216, 88, 8, 8, SMALL_PALETTE)


def photos(app, widget, zoom: int = 1) -> dict:
    """The pictures as Tk images, kept by the window (its Tk's): "attribute"
    (by number), "level", "attack", "defense"; empty without game files."""
    files = getattr(app, "files", None)
    if files is None or getattr(files, "wa", None) is None:
        return {}
    cache = app.__dict__.setdefault("_card_icons", {})
    key = (getattr(files, "source", id(files)), zoom)
    if key not in cache:
        master = widget.winfo_toplevel()

        def photo(image):
            if image is None:
                return None
            image = pngio.scale_nearest(image, zoom)
            return tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")
        cache[key] = {"attribute": {n: photo(attribute(files.wa, n)) for n in range(8)},
                      "level": photo(level_star(files.wa)), "attack": photo(sword(files.wa)),
                      "defense": photo(shield(files.wa))}
    return cache[key]
