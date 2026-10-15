"""A card's text as the card view lays it out and draws it, for the Cards
tab's preview (preview.py).

Layout, in two steps as in the port and the game:

* cards.c encode_description: lines of twenty letters at most, broken at
  spaces, "\\n" breaking where it stands; a word longer than a line is not
  broken but written whole.
* the text box (TextBox_WrapLineIfNeeded, TextBox_BuildStep): every glyph
  8 pixels across, 21 to the box's 168 pixels; a glyph that would start
  past them goes to the next row, in the middle of a word. The card text
  starts 80 pixels down the 192-pixel box, 12 pixels a row, so nine rows
  are drawn (checked in the game: the ninth is over the panel's frame) and
  the box stops before the tenth, which the card view never shows.

Drawing: the retail 8x12 font off the player's disc (font_art.c: the boot
package, WA sector 0x1690, raw VRAM words from 0x280, 0; the text colors
at its 51st sector), or a TrueType face set into each glyph's cell the way
the port's HD text sets it (src/pc/text/hd_text.c render_span): the font's
baseline, x-height, capitals, ascenders and descenders onto the retail
font's lines, as wide as the cell's glyph, its stems made as heavy, the
dark outline round it and the rows' shading, through the text's palette.
Nothing of the game is kept: the font is read from the disc each run.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import pngio, ttf

LINE_LETTERS = 20          # cards.c TEXT_LINE_LETTERS
COLUMNS = 21               # the box: 0xA8 pixels, 8 a glyph
CLEAR_ROWS = 8             # rows the panel shows clear of its frame
SHOWN_ROWS = 9             # the ninth is drawn over the frame; the box stops before the tenth
CELL_W, CELL_H = 8, 12

BOOT_SECTOR = 0x1690
FONT_SECTORS = 16
RAMP_SECTOR = BOOT_SECTOR + 50
# The icons and their palettes: the boot package's second font page
# (notes/more-cards.md, "Card text codes").
ICON_SECTOR, ICON_CLUT_SECTOR = BOOT_SECTOR + 16, BOOT_SECTOR + 48
ICON_NAMES = ("Dragon", "Spellcaster", "Zombie", "Warrior", "Beast-Warrior", "Beast", "Winged Beast", "Fiend",
              "Fairy", "Insect", "Dinosaur", "Reptile", "Fish", "Sea Serpent", "Machine", "Thunder", "Aqua", "Pyro",
              "Rock", "Plant", "Magic", "Trap", "Ritual", "Equip", "Mars", "Jupiter", "Saturn", "Uranus", "Pluto",
              "Neptune", "Mercury", "Sun", "Moon", "Venus", "Cross", "Triangle", "Square", "Circle", "Star",
              "Start (left half)", "Start (right half)")
COLOR_NAMES = ("White", "Yellow", "Blue", "Green", "Grey", "Orange", "Red")
PUNCTUATION = "!\"#$%&'()*+,-./:;<=>?"
ALIASES = {"\u2019": "'", "\u2018": "'", "\u201d": '"', "\u201c": '"', "\u2212": "-", "\u2013": "-", "\u2014": "-",
           "\u00a0": " "}

PANEL = (16, 24, 48)       # the card view's panel, about (it is a stone texture)
FRAME = (92, 84, 70)       # its frame
HIDDEN = (40, 40, 40)      # rows the game never shows
MARK = (230, 40, 40)
GUTTER, GUTTER_COLOR = 3, (200, 200, 200)   # texels right of the box, for the marks


# --- layout -------------------------------------------------------------------

# cards.c text_code: an icon "{f8 0B NN}" (two letters wide), a color
# "{f8 0A NN}" (none) or a glyph by number "{g X}" (a letter).
CODE = re.compile(r"\{f8 *(0[AaBb]) *([0-9A-Fa-f]{1,2})\}|\{g *([0-9A-Fa-f]{1,4})\}")


def code_at(text: str, i: int):
    """(the code's characters, its width in letters), or None."""
    match = CODE.match(text, i)
    if not match or (match.group(3) and int(match.group(3), 16) >= 0x600):
        return None
    kind = (match.group(1) or "").upper()
    return match.group(0), 0 if kind == "0A" else 2 if kind == "0B" else 1


def encode(text: str, colors: bool = False, breaks: list = None) -> list:
    """The glyphs cards.c encode_description writes: characters, " " for
    the space it puts between words, "\\n" for its line breaks (0xFE). An
    icon or numbered glyph is its code as written, in one cell; a color
    code takes none and is left out (kept as written with `colors`).
    `breaks` gets the index in text of each space the wrapping breaks at."""
    out, column, i = [], 0, 0
    while i < len(text):
        c = text[i]
        if c == "\n":
            out.append("\n")
            column = 0
            i += 1
            continue
        if c == " ":
            i += 1
            continue
        word, end = [], i
        while end < len(text) and text[end] not in " \n":
            code = code_at(text, end)
            if code:
                word.append(code)
                end += len(code[0])
            else:
                word.append((text[end], 1))
                end += 1
        letters = sum(width for _, width in word)
        if column and column + 1 + letters > LINE_LETTERS:
            out.append("\n")
            column = 0
            if breaks is not None:
                breaks.append(i - 1)
        elif column:
            out.append(" ")
            column += 1
        for letter, width in word:
            if width and letter >= " ":
                out.append(letter)
                column += width
            elif colors and not width:
                out.append(letter)
        i = end
    return out


def wrap_points(text: str) -> list:
    """The spaces of text (indices) where the game's wrapping starts a new
    line: twenty letters a line, an icon two, a word never split."""
    breaks = []
    encode(text, breaks=breaks)
    return breaks


@dataclass
class Layout:
    glyphs: list = field(default_factory=list)      # (character, column, row)
    colors: list = field(default_factory=list)     # each glyph's color ramp ("{f8 0A NN}", 0 white)
    rows: int = 0                                   # rows the text takes
    cut_rows: list = field(default_factory=list)    # rows the box began mid-word (a word past 21 letters)
    lines: int = 0                                  # the port's own count (its "runs to N lines" note)

    @property
    def hidden(self) -> int:
        """Rows the card view never shows."""
        return max(0, self.rows - SHOWN_ROWS)


def layout(text: str) -> Layout:
    out = Layout()
    glyphs = encode(text, colors=True)
    out.lines = 1 + glyphs.count("\n")
    x = row = color = 0
    for g in glyphs:
        if g.startswith("{") and code_at(g, 0)[1] == 0:
            color = int(CODE.match(g).group(2), 16)
            continue
        if g == "\n":
            x = 0
            row += 1
            continue
        if x >= COLUMNS:
            x = 0
            row += 1
            out.cut_rows.append(row)
        out.glyphs.append((g, x, row))
        out.colors.append(color)
        x += 2 if g.startswith("{") and code_at(g, 0)[1] == 2 else 1
    out.rows = row + 1 if glyphs else 0
    return out


# --- the retail font ----------------------------------------------------------

def retail_character(c: str) -> str:
    """The retail glyph a character is drawn with ("" for none); an
    accented letter is its plain one here (the port draws the mark on)."""
    c = ALIASES.get(c, c)
    if c.isascii() and (c.isalnum() or c in PUNCTUATION):
        return c
    base = unicodedata.normalize("NFD", c)[:1]
    return base if base.isascii() and base.isalnum() else ""


def _rgb15(word: int):
    return (word & 31) << 3, (word >> 5 & 31) << 3, (word >> 10 & 31) << 3


def icon_code(n: int) -> str:
    return "{f8 0B %02X}" % n


def color_code(n: int) -> str:
    return "{f8 0A %02X}" % n


def _cell_uv(c: str):
    if c.isdigit():
        return (15 * 8, 0) if c == "0" else ((ord(c) - ord("1")) * 8, 12)
    if "A" <= c <= "Z":
        sjis = 0x8260 + ord(c) - 65
    elif "a" <= c <= "z":
        sjis = 0x8281 + ord(c) - 97
    else:
        i = PUNCTUATION.index(c)
        return (i * 8, 0) if i < 15 else (i * 8 - 0x30, 12)
    return (sjis & 15) * 8, ((sjis - 0x8240) >> 4) * 12


class RetailFont:
    """The 8x12 font and the white text's colors off the disc."""

    def __init__(self, wa: bytes):
        start, end = BOOT_SECTOR * 2048, (BOOT_SECTOR + FONT_SECTORS) * 2048
        ramp = RAMP_SECTOR * 2048
        if wa is None or len(wa) < ramp + 32:
            raise ValueError("the game files have no font where the retail disc has it")
        page = wa[start:end]
        # 256 x 256 texels, 4 bits each, 4 to a little-endian word.
        self.texels = bytearray(256 * 256)
        for i, byte in enumerate(page):
            self.texels[2 * i] = byte & 15
            self.texels[2 * i + 1] = byte >> 4
        # The text's color ramps (gText_abColorSlots: COLOR_NAMES, then an
        # unused eighth), 16 colors each; white is the one drawn without a code.
        self.ramps = [[_rgb15(wa[ramp + 32 * r + 2 * i] | wa[ramp + 32 * r + 2 * i + 1] << 8) for i in range(16)]
                      for r in range(min(8, (len(wa) - ramp) // 32))]
        self.colors = self.ramps[0]
        self._icon_pages = (wa[ICON_SECTOR * 2048:(ICON_SECTOR + 16) * 2048],
                            wa[ICON_CLUT_SECTOR * 2048:(ICON_CLUT_SECTOR + 2) * 2048])
        self._icons = {}
        if not any(self.cell("A")):
            raise ValueError("the game files have no font where the retail disc has it")

    def icon(self, n: int):
        """Icon `n` of "{f8 0B NN}" as func_80035E20 draws it in card text:
        (16, 16, RGBA bytes), or None past ICON_NAMES or when the disc has
        none there."""
        if n not in self._icons:
            self._icons[n] = self._read_icon(n) if 0 <= n < len(ICON_NAMES) else None
        return self._icons[n]

    def _read_icon(self, n: int):
        page, cluts = self._icon_pages
        if n >= 0x22:
            u, v = (n * 16 - 0x210) & 0xFF, 0x80
            cx, cy = (0x210 if u == 0x50 else 0x200), 0xFC
        else:
            u, v = ((n & 7) * 16 - 0x80) & 0xFF, (n & 0x38) * 2
            r = min(n, 0x18)
            cx, cy = 0x200 + (r & 15) * 16, 0xF9 + (r >> 4)
        width = 16
        index = lambda x, y: page[(v + y) * 128 + (u + x) // 2] >> 4 * ((u + x) & 1) & 15
        clut, at = cluts, (cy - 0xF8) * 512 + (cx - 0x200) * 2
        if len(clut) < at + 512 or not any(clut[at:at + 32]):
            return None
        rgba = bytearray()
        for y in range(16):
            for x in range(width):
                i = index(x, y)
                word = clut[at + 2 * i] | clut[at + 2 * i + 1] << 8
                rgba += bytes((*_rgb15(word), 255 if word else 0))
        return width, 16, bytes(rgba)

    def cell(self, c: str):
        """The glyph's 8 x 12 palette indices, row by row (None for none)."""
        c = retail_character(c)
        if not c:
            return None
        u, v = _cell_uv(c)
        return [self.texels[(v + y) * 256 + u + x] for y in range(CELL_H) for x in range(CELL_W)]


# --- the port's HD text -------------------------------------------------------

CELL = 16          # hd_text.c: an atlas cell's texels a side (the small font's glyph fills 8 x 12)
FONT_SIZE = 64
SATURATE = 0.7
BRIGHT = 0.5
MEASURED_BY = ("ABDEFHIKLMNPRTXZ", "BDEFHIKLMNPRTZ", "uvwxz", "bdhkl", "pq", "HILTUdhilnpqu", "EFHLTZ")


def _median(values):
    if not values:
        return 0.0
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n & 1 else (v[n // 2 - 1] + v[n // 2]) / 2


def _runs(cover, width, height, down):
    out = []
    across, along = (width, height) if down else (height, width)
    for i in range(across):
        run = 0.0
        for j in range(along + 1):
            c = (cover[j * width + i] if down else cover[i * width + j]) if j < along else 0
            if c > 0:
                run += c
            elif run > 0:
                out.append(run)
                run = 0.0
    return out


class Retail:
    """hd_text.c measure_retail: the 8x12 font's lines, stems, outline
    and shading, measured from its letters."""

    def __init__(self, font: RetailFont):
        cells = {c: self._wide(font.cell(c)) for c in
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"}
        self.shade = [0.0] * CELL
        border, alls = [0] * 16, [0] * 16
        rows = [[0] * 16 for _ in range(CELL)]
        for cell in cells.values():
            for y in range(CELL_H):
                for x in range(CELL):
                    v = cell[y * CELL + x]
                    self.shade[y] = max(self.shade[y], v)
                    alls[v] += 1
                    rows[y][v] += 1
                    if v and ((x > 0 and not cell[y * CELL + x - 1]) or (x + 1 < CELL and not cell[y * CELL + x + 1])
                              or (y > 0 and not cell[(y - 1) * CELL + x])
                              or (y + 1 < CELL and not cell[(y + 1) * CELL + x])):
                        border[v] += 1
        self.outline = self.dark = 1
        for i in range(2, 5):
            if border[i] > border[self.outline]:
                self.outline = i
            if border[i] * 2 > alls[i] and self.dark == i - 1:
                self.dark = i
        self.body = []
        for y in range(CELL):
            total = sum(rows[y][i] * i for i in range(self.dark + 1, 16))
            count = sum(rows[y][i] for i in range(self.dark + 1, 16))
            self.body.append(total / count if count else 0.0)
        for y in range(1, CELL):
            if self.shade[y] < 3:
                self.shade[y], self.body[y] = self.shade[y - 1], self.body[y - 1]
        for y in range(CELL - 2, -1, -1):
            if self.shade[y] < 3:
                self.shade[y] = self.shade[y + 1] if self.shade[y + 1] >= 3 else 15
                self.body[y] = self.body[y + 1] if self.body[y + 1] >= 3 else 15
        edges = []
        for k in range(7):
            found = []
            for c in MEASURED_BY[k]:
                cell = cells[c]
                if k >= 5:
                    cover = [self.coverage(cell, x, y) if y < CELL_H else 0.0 for y in range(CELL) for x in range(CELL)]
                    found += _runs(cover, CELL, CELL, k == 6)
                else:
                    box = self.extents(cell)
                    if box:
                        found.append(box[3] if k in (0, 4) else box[1])
            edges.append(_median(found))
        self.base, self.cap, self.x_height, self.ascender, self.descender, self.stem, self.bar = edges
        self.ok = self.cap < self.base and self.x_height < self.base and self.stem > 0

    @staticmethod
    def _wide(cell):
        """An 8 x 12 cell in a 16 x 16 one, as hd_text.c reads it."""
        out = [0] * (CELL * CELL)
        if cell:
            for y in range(CELL_H):
                out[y * CELL:y * CELL + CELL_W] = cell[y * CELL_W:(y + 1) * CELL_W]
        return out

    def coverage(self, cell, x, y):
        index = cell[y * CELL + x]
        if index <= self.dark:
            return 0.0
        c = (index - self.dark) / (SATURATE * (self.shade[y] - self.dark))
        return 1.0 if c > 1 else c

    def extents(self, cell):
        """(left, top, right, bottom) of the cell's letter, to a fraction of
        a texel; None for none."""
        rows, columns = [0.0] * CELL, [0.0] * CELL
        for y in range(CELL_H):
            for x in range(CELL):
                c = self.coverage(cell, x, y)
                rows[y] = max(rows[y], c)
                columns[x] = max(columns[x], c)
        ys = [y for y in range(CELL_H) if rows[y] > 0]
        xs = [x for x in range(CELL) if columns[x] > 0]
        if not ys:
            return None
        top, bottom, left, right = ys[0], ys[-1], xs[0], xs[-1]
        return (left + 1 - columns[left], top + 1 - rows[top], right + columns[right], bottom + rows[bottom])


def _through(src, dst, value):
    i = 0
    while i + 2 < len(src) and value > src[i + 1]:
        i += 1
    return dst[i] + (value - src[i]) * (dst[i + 1] - dst[i]) / (src[i + 1] - src[i])


def _scaled(contours, s):
    return [[(x * s, y * s) for x, y in c] for c in contours]


class FaceLines:
    """hd_text.c measure_font: a face's lines, stems and bars at 64 pixels."""

    def __init__(self, font: ttf.Font):
        self.ok = False
        edges = {}
        for k in range(1, 7):
            found = []
            for c in MEASURED_BY[k]:
                contours = font.outline(ord(c))
                if not contours:
                    continue
                contours = _scaled(contours, FONT_SIZE)
                box = ttf.bbox(contours)
                if k < 5:
                    found.append(box[1] if k == 4 else box[3])
                    continue
                left, bottom = int(box[0]) - 1, int(box[1]) - 1
                width, height = int(box[2] - left) + 2, int(box[3] - bottom) + 2
                pixels = [[(x - left, height - (y - bottom)) for x, y in c] for c in contours]
                cover = [v / 255 for v in ttf.fill(pixels, width, height)]
                found += _runs(cover, width, height, k == 6)
            if not found:
                return
            edges[k] = _median(found)
        self.cap, self.x_height, self.ascender, self.descender, self.stem, self.bar = (edges[k] for k in range(1, 7))
        self.ok = (self.cap > self.x_height > 0 and self.ascender > 0 and self.descender < 0 and self.stem > 0
                   and self.bar > 0)


def _fill_rect(cover, width, height, x0, y0, x1, y1):
    y = int(y0)
    while y < height and y < y1:
        h = min(y + 1, y1) - max(y, y0)
        if y >= 0 and h > 0:
            x = int(x0)
            while x < width and x < x1:
                w = min(x + 1, x1) - max(x, x0)
                if x >= 0 and w > 0:
                    cover[y * width + x] = min(255, int(cover[y * width + x] + w * h * 255))
                x += 1
        y += 1


def hd_cell(font: ttf.Font, lines: FaceLines, r: Retail, cell, character: str, f: int):
    """render_span for one character: the glyph's picture, CELL_W*f x
    CELL_H*f palette indices (0 transparent), or None when the face cannot
    set it (the port then draws the retail cell, made larger)."""
    wide = Retail._wide(cell)
    box = r.extents(wide)
    code = ord(character)
    if not lines.ok or box is None or not font.has(code):
        return None
    contours = font.outline(code)
    if not contours:
        return None
    contours = _scaled(contours, FONT_SIZE)
    ink_left, ink_bottom, ink_right, ink_top = ttf.bbox(contours)
    width_f, centre_f = ink_right - ink_left, (ink_right + ink_left) / 2
    centre_r = (box[0] + box[2]) / 2
    upper = character.isascii() and (character.isupper() or character.isdigit())
    lower = character.isascii() and character.islower()
    src, dst, tops = [], [], []
    main = 0
    if upper or lower:
        top_f, top_r = (lines.x_height, r.x_height) if lower else (lines.cap, r.cap)
        if lines.descender < -1 and r.descender > r.base + 0.25:
            if ink_bottom < -lines.bar and box[3] > r.base + 0.25:
                src.append(ink_bottom), dst.append(box[3]), tops.append(0)
            else:
                src.append(lines.descender), dst.append(r.descender), tops.append(0)
        main = len(src)
        src.append(0.0), dst.append(r.base), tops.append(0)
        src.append(top_f), dst.append(top_r), tops.append(1)
        if lines.ascender > top_f + 1 and r.ascender < top_r - 0.25:
            src.append(lines.ascender), dst.append(r.ascender), tops.append(1)
    else:
        src += [ink_bottom, ink_top]
        dst += [box[3], box[1]]
        tops += [0, 1]
    if src[main + 1] <= src[main] or dst[main + 1] >= dst[main]:
        return None
    ey = 0.0
    for _ in range(2):
        sv = (dst[main] - dst[main + 1] - ey) / (src[main + 1] - src[main])
        ey = r.bar - lines.bar * sv
        if ey < -lines.bar * sv / 2:
            ey = -lines.bar * sv / 2
    dst = [d + (ey / 2 if t else -ey / 2) for d, t in zip(dst, tops)]
    if sv <= 0 or dst[main + 1] >= dst[main]:
        return None
    stem_f = min(lines.stem, width_f)
    room = box[2] - box[0]
    if width_f - stem_f > width_f / 4:
        sx = (room - r.stem) / (width_f - stem_f)
        if sx > sv * 1.25:
            sx = sv * 1.25
        if sx <= 0:
            sx = room / width_f
    else:
        sx = sv
        if width_f * sx + r.stem - stem_f * sx > room:
            sx = room / width_f
    ex = r.stem - stem_f * sx
    if ex < -stem_f * sx / 2:
        ex = -stem_f * sx / 2
    width, height = CELL * f, CELL_H * f
    placed = [[((centre_r + (x - centre_f) * sx) * f, _through(src, dst, y) * f) for x, y in c] for c in contours]
    placed = ttf.embolden(placed, ex * f, ey * f)
    cover = ttf.fill(placed, width, height)
    if character == "I" and width_f < lines.stem * 1.8 and box[2] - box[0] > r.stem * 1.5:
        _fill_rect(cover, width, height, box[0] * f, box[1] * f, box[2] * f, (box[1] + r.bar) * f)
        _fill_rect(cover, width, height, box[0] * f, (box[3] - r.bar) * f, box[2] * f, box[3] * f)
    # The outline: within a texel of the half-covered pixels (chamfer 3/4).
    far = 0xFFFF
    dist = [0 if cover[i] >= 128 else far for i in range(width * height)]
    for y in range(height):
        for x in range(width):
            i = y * width + x
            d = dist[i]
            if x > 0 and dist[i - 1] + 3 < d:
                d = dist[i - 1] + 3
            if y > 0:
                if dist[i - width] + 3 < d:
                    d = dist[i - width] + 3
                if x > 0 and dist[i - width - 1] + 4 < d:
                    d = dist[i - width - 1] + 4
                if x + 1 < width and dist[i - width + 1] + 4 < d:
                    d = dist[i - width + 1] + 4
            dist[i] = d
    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            i = y * width + x
            d = dist[i]
            if x + 1 < width and dist[i + 1] + 3 < d:
                d = dist[i + 1] + 3
            if y + 1 < height:
                if dist[i + width] + 3 < d:
                    d = dist[i + width] + 3
                if x + 1 < width and dist[i + width + 1] + 4 < d:
                    d = dist[i + width + 1] + 4
                if x > 0 and dist[i + width - 1] + 4 < d:
                    d = dist[i + width - 1] + 4
            dist[i] = d
    out_w = CELL_W * f
    out = bytearray(out_w * height)
    for y in range(height):
        at = (y + 0.5) / f - 0.5
        line = 0 if at < 0 else int(at)
        nxt = line + 1 if line + 1 < CELL_H else line
        t = 0.0 if at < 0 else at - line
        shade = r.shade[line] + (r.shade[nxt] - r.shade[line]) * t
        shade = shade * BRIGHT + (1 - BRIGHT) * (r.body[line] + (r.body[nxt] - r.body[line]) * t)
        for x in range(out_w):
            i = y * width + x
            index = r.dark + int(cover[i] * (shade - r.dark) / 255 + 0.5)
            if index > r.dark:
                out[y * out_w + x] = index
            elif dist[i] <= 3 * f:
                out[y * out_w + x] = r.outline
    return out


# --- faces --------------------------------------------------------------------

def port_face_path():
    """The face the port's HD text sets the card text in when no mod gives
    one (glyphs.c open_system_face): on Windows the first of Segoe UI,
    Arial and Tahoma in the Fonts folder (win32.c Win32_FontPath); elsewhere
    fontconfig's match for "sans-serif:bold". None when there is none."""
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("segoeui.ttf", "arial.ttf", "tahoma.ttf"):
            if (fonts / name).is_file():
                return str(fonts / name)
        return None
    match = shutil.which("fc-match")
    if not match:
        return None
    try:
        path = subprocess.run([match, "-f", "%{file}", "sans-serif:bold"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return path if path and Path(path).is_file() else None


def fonts_folder():
    if os.name == "nt":
        return str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
    for folder in ("~/.local/share/fonts", "~/.fonts", "/usr/share/fonts", "~/Library/Fonts", "/Library/Fonts"):
        if Path(folder).expanduser().is_dir():
            return str(Path(folder).expanduser())
    return None


# --- the picture ----------------------------------------------------------------

class Renderer:
    """The card view's text panel as a picture, at `scale` pixels a texel
    (the box's 21 columns, then a gutter for the marks):
    the retail font (face None), or `face` set as the port's HD text sets
    it (scale 2 and up; at 1x the port draws the retail font)."""

    def __init__(self, retail: RetailFont, face: ttf.Font = None):
        self.retail, self.face = retail, face
        self._measured = None
        self._lines = None
        self._cells = {}

    def _hd(self, c, f):
        key = (c, f)
        if key not in self._cells:
            cell = self.retail.cell(c)
            picture = None
            if cell is not None and self.face is not None:
                if self._measured is None:
                    self._measured = Retail(self.retail)
                    self._lines = FaceLines(self.face)
                if self._measured.ok:
                    picture = hd_cell(self.face, self._lines, self._measured, cell, retail_character(c) if
                                      not self.face.has(ord(c)) else c, f)
            self._cells[key] = picture
        return self._cells[key]

    @property
    def face_ok(self) -> bool:
        """Whether the face's lines could be measured (the port sets
        nothing in a face without them, and draws the retail font)."""
        if self.face is None:
            return False
        if self._lines is None:
            self._measured = Retail(self.retail)
            self._lines = FaceLines(self.face)
        return self._lines.ok

    def render(self, text: str, scale: int):
        """(picture, layout)."""
        lay = layout(text)
        f = max(1, int(scale))
        rows = max(SHOWN_ROWS, lay.rows)
        box = COLUMNS * CELL_W * f
        w, h = box + GUTTER * f, rows * CELL_H * f
        rgb = bytearray(w * h * 3)
        for row in range(rows):
            color = PANEL if row < CLEAR_ROWS else FRAME if row < SHOWN_ROWS else HIDDEN
            line = bytes(color) * box + bytes(GUTTER_COLOR) * (w - box)
            for y in range(row * CELL_H * f, (row + 1) * CELL_H * f):
                rgb[y * w * 3:(y + 1) * w * 3] = line
        for (c, column, row), ramp in zip(lay.glyphs, lay.colors):
            colors = self.retail.ramps[ramp] if ramp < len(self.retail.ramps) else self.retail.colors
            x0, y0 = column * CELL_W * f, row * CELL_H * f
            dim = row >= SHOWN_ROWS
            match = CODE.match(c) if c.startswith("{") else None
            if match and match.group(1):        # an icon: 16 texels a side, a letter's width apart as the game sets it
                self._icon(rgb, w, h, int(match.group(2), 16), x0, y0, f, dim)
                continue
            if c == " " or c.startswith("{"):      # a numbered glyph: left empty here
                continue
            picture = self._hd(c, f) if self.face is not None and f > 1 else None
            if picture is not None:
                pw = CELL_W * f
                for i, index in enumerate(picture):
                    if index:
                        self._put(rgb, w, x0 + i % pw, y0 + i // pw, colors[index], dim)
                continue
            cell = self.retail.cell(c)
            if cell is None:        # no glyph: the port may make one (glyphs.c); a red box stands in
                for y in range(CELL_H * f):
                    for x in range(CELL_W * f):
                        if x in (0, CELL_W * f - 1) or y in (0, CELL_H * f - 1):
                            self._put(rgb, w, x0 + x, y0 + y, MARK, dim)
                continue
            for i, index in enumerate(cell):
                if index:
                    for dy in range(f):
                        for dx in range(f):
                            self._put(rgb, w, x0 + (i % CELL_W) * f + dx, y0 + (i // CELL_W) * f + dy,
                                      colors[index], dim)
        # A red tick past the box's right edge where it cut a word.
        for row in lay.cut_rows:
            y0 = (row - 1) * CELL_H * f
            for y in range(CELL_H * f):
                for x in range(box + f, w):
                    self._put(rgb, w, x, y0 + y, MARK, False)
        rgba = bytearray(w * h * 4)
        rgba[0::4], rgba[1::4], rgba[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
        rgba[3::4] = b"\xff" * (w * h)
        return pngio.Image(w, h, bytes(rgba)), lay

    def _icon(self, rgb, w, h, n, x0, y0, f, dim):
        """The card view draws an icon from its cell's top left, 16 texels
        high (12 a row): it overlaps the cell after it and the row below."""
        icon = self.retail.icon(n)
        if icon is None:
            return
        width, height, rgba = icon
        for y in range(height * f):
            for x in range(width * f):
                at = ((y // f) * width + x // f) * 4
                if rgba[at + 3] and x0 + x < w and y0 + y - 2 * f < h and y0 + y - 2 * f >= 0:
                    self._put(rgb, w, x0 + x, y0 + y - 2 * f, tuple(rgba[at:at + 3]), dim)

    @staticmethod
    def _put(rgb, w, x, y, color, dim):
        at = (y * w + x) * 3
        if dim:
            color = tuple(v // 2 for v in color)
        rgb[at:at + 3] = bytes(color)
