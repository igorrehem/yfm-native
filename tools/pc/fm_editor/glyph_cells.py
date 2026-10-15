"""The card view's 8x12 letters as the port draws them, for the card-text
preview (card_text.py): the retail letters, and the letters the port makes
(src/pc/text/glyphs.c) for a translation's accented and other characters.

GlyphCells(retail, face=None, european=False).cell(c) gives a character's
cell: 96 palette indices of the text's colors, 8 across and 12 down, row by
row, 0 transparent; None when the port can make no letter for it (cards.c
then leaves the character out of the text, with a mod note, and the letters
after it close up: it takes no cell).

How the port makes them (Glyphs_Code, Glyphs_Cell; checked against
glyphs.c built on its own, on the retail font, character for character):

* retail: the letters, digits and the punctuation the executable's glyph
  table has (! " # $ % & ' ( ) * + , - . / : < > ? and « » · ♀ ♂ ⊂ ⊃ α ← →,
  ‘ ’ “ ” − – — and a no-break space standing for theirs), from the font
  page as func_80035E20 finds them: « and » are < and >, α its own cell,
  and · ♀ ♂ ⊂ ⊃ ← → the small font's "no glyph" box. ; and = are no retail
  glyphs (the table lacks them) and come from a font as other characters do.
* accented letters (accents.inc and the extra list: ¿ ¡ ı ø Ø ł Ł đ Đ ħ Ħ):
  compose(), exactly: the retail letter, its i/j dot taken off, its mark
  stamped on in the letter's color with the dark outline round it; a
  capital gives up rows for a mark (drop_rows); Vietnamese's two marks side
  by side; dot below, cedilla, ogonek, horn, slash and bar; ¿ ¡ turned.
* the drawn letters (letters.inc: ß æ Æ œ Œ ð Ð þ Þ º ª ° € ẞ): render(),
  exactly: their 8x12 shapes, shaded by row as the retail capitals are,
  outlined.
* with `european` (Game > Language's European text, Glyphs_SetEuropean):
  the PAL's serifs (serif.c) on the retail i and l and on the letters made
  of them with marks over them (their acute a column left), exactly.
* anything else: set in a font (a mod's, then the system's sans-serif bold)
  by render(): FreeType at 10 pixels, hinted (FT_LOAD_TARGET_NORMAL), its
  coverage 96/255 and up as ink, squeezed into 6 columns, baseline row 10.
  Here `face` (a ttf.Font, or a list of them, in the port's order) is set
  with the editor's own TrueType reader (ttf.py), with no hinting but the
  face's baseline, x-height, capitals and descender snapped as FreeType
  snaps them (x-height and capitals rounded up): the shading, outline,
  squeeze and placing are the port's, but a stroke may land a pixel off
  where the hinting moves it. Against FreeType on Noto Sans Bold (the
  Linux port's sans-serif bold), 668 Greek, Cyrillic and symbol letters:
  170 cells exact, 5.6% of pixels differ (11.4% without the snapping).
  Without a face that has the character, None.

Not modelled: the port's limit of 672 made letters (Glyphs_Code then
fails for more) and a mod font loaded over the retail font page.
"""
from __future__ import annotations

import math
import unicodedata

from . import card_text, ttf

W, H = card_text.CELL_W, card_text.CELL_H

# --- marks (glyphs.c) -----------------------------------------------------------

(NONE, GRAVE, ACUTE, CIRCUMFLEX, TILDE, MACRON, BREVE, DOT, DIAERESIS, RING, DOUBLE_ACUTE, CARON, CEDILLA, OGONEK,
 HOOK, DOT_BELOW, HORN) = range(17)
FLIP, DOTLESS, SLASH, BAR = range(17, 21)

SMALL_MARKS = ((), ("#..", ".#."), ("..#", ".#."), (".#.", "#.#"), (".#.#", "#.#."), ("###",), ("#..#", ".##."),
               ("#",), ("#.#",), (".#.", "#.#", ".#."), (".#.#", "#.#."), ("#.#", ".#."), (".#", "#."), ("#.", ".#"),
               ("##", ".#"), ("#",), ())
SIDE_MARKS = ((), ("#.", ".#"), (".#", "#."), (".#.", "#.#"), (".##", "##."), (), ("#.#", ".#."),
              (), (), (), (), (), (), (), ("##", ".#"), (), ())

# tools/pc/glyph_accents.py: the combining marks glyphs.c draws, Vietnamese's
# shape marks and tones.
COMBINING = {0x0300: GRAVE, 0x0301: ACUTE, 0x0302: CIRCUMFLEX, 0x0303: TILDE, 0x0304: MACRON, 0x0306: BREVE,
             0x0307: DOT, 0x0308: DIAERESIS, 0x030A: RING, 0x030B: DOUBLE_ACUTE, 0x030C: CARON, 0x0327: CEDILLA,
             0x0328: OGONEK, 0x0309: HOOK, 0x0323: DOT_BELOW, 0x031B: HORN}
SHAPES = (0x0302, 0x0306, 0x031B)
TONES = (0x0300, 0x0301, 0x0309, 0x0303, 0x0323)
EXTRA_ACCENTS = {"¿": ("?", FLIP, NONE), "¡": ("!", FLIP, NONE), "ı": ("i", DOTLESS, NONE),
                 "ø": ("o", SLASH, NONE), "Ø": ("O", SLASH, NONE), "ł": ("l", SLASH, NONE),
                 "Ł": ("L", SLASH, NONE), "đ": ("d", BAR, NONE), "Đ": ("D", BAR, NONE),
                 "ħ": ("h", BAR, NONE), "Ħ": ("H", BAR, NONE)}


def _accents():
    """accents.inc as glyph_accents.py writes it, then the extra ones:
    {character: (retail letter, mark, tone)}."""
    out = {}
    for c in range(0xC0, 0x3000):
        if "LATIN" not in unicodedata.name(chr(c), ""):
            continue
        d = unicodedata.normalize("NFD", chr(c))
        if len(d) < 2 or not ("A" <= d[0] <= "Z" or "a" <= d[0] <= "z"):
            continue
        marks = [ord(m) for m in d[1:]]
        if len(marks) == 1 and marks[0] in COMBINING:
            out[chr(c)] = (d[0], COMBINING[marks[0]], NONE)
        elif len(marks) == 2:
            shape = [m for m in marks if m in SHAPES]
            tone = [m for m in marks if m in TONES]
            if len(shape) == 1 and len(tone) == 1:
                out[chr(c)] = (d[0], COMBINING[shape[0]], COMBINING[tone[0]])
    for c, entry in EXTRA_ACCENTS.items():
        out.setdefault(c, entry)
    return out


ACCENTS = _accents()

# letters.inc's small (8x12) shapes (set in Noto Sans Bold, SIL Open Font
# License 1.1, by the port).
LETTERS = {
    "ß": ("........", "........", "..###...", ".#####..", ".##..#..", ".##.#...", ".##.##..", ".##..##.",
               ".##.###.", ".##.##..", "........", "........"),
    "æ": ("........", "........", "........", "........", "..####..", "..#####.", "..#####.", ".#.##...",
               ".####.#.", "..#..##.", "........", "........"),
    "Æ": ("........", "........", "........", "...####.", "..###...", "..#.###.", "..#.###.", "..###...",
               ".##.###.", ".#..###.", "........", "........"),
    "œ": ("........", "........", "........", "........", "..####..", ".######.", ".#..###.", ".#..#...",
               ".#####..", "..##.##.", "........", "........"),
    "Œ": ("........", "........", "........", "..#####.", ".##.#...", ".#..###.", ".#..###.", ".#..#...",
               ".######.", "..#####.", "........", "........"),
    "ð": ("........", "........", "...#.#..", "...###..", "...###..", "..#####.", ".##..##.", ".##..##.",
               ".#####..", "...##...", "........", "........"),
    "Ð": ("........", "........", "........", "..####..", "..#..##.", ".##..##.", ".###.##.", "..#..##.",
               "..####..", "..###...", "........", "........"),
    "þ": ("........", "........", ".##.....", ".##.....", ".#####..", ".######.", ".##..##.", ".##..##.",
               ".######.", ".#####..", ".##.....", "........"),
    "Þ": ("........", "........", "........", ".##.....", ".####...", ".##.##..", ".##.##..", ".####...",
               ".##.....", ".#......", "........", "........"),
    "º": ("........", "........", "...##...", "..####..", "..#..#..", "..###...", "........", "........",
               "........", "........", "........", "........"),
    "ª": ("........", "........", "...#....", "...##...", "..###...", "..###...", "........", "........",
               "........", "........", "........", "........"),
    "°": ("........", "........", "...##...", "..####..", "..#..#..", "...##...", "........", "........",
               "........", "........", "........", "........"),
    "€": ("........", "........", "........", "...####.", "..##....", ".####...", ".####...", "..##....",
               "..####..", "...###..", "........", "........"),
    "ẞ": ("........", "........", "........", "..####..", ".##.##..", ".#..##..", ".##.###.", ".##..##.",
               ".######.", ".#.###..", "........", "........"),
}

# --- the retail glyphs ----------------------------------------------------------

# The US executable's glyph table (0x801D9000) past its letters and digits:
# the characters it has, and where func_80035E20 draws those card_text's
# _cell_uv does not know in the small font.
RETAIL_PUNCTUATION = "!\"#$%&'()*+,-./:<>?"
RETAIL_OTHER = {"«": "<", "»": ">", "α": (0x68, 0x3C), "·": (0, 0x30), "♀": (0, 0x30),
                "♂": (0, 0x30), "⊂": (0, 0x30), "⊃": (0, 0x30), "←": (0, 0x30),
                "→": (0, 0x30)}
ALIASES = {"’": "'", "‘": "'", "”": '"', "“": '"', "−": "-", "–": "-", "—": "-",
           "《": "«", "》": "»", "・": "·", " ": " "}


def _cdiv(a, b):
    """C's integer division (toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class _Cell:
    """glyphs.c Cell for the small font: 8 x 12 indices."""

    __slots__ = ("p",)

    def __init__(self, pixels=None):
        self.p = [row[:] for row in pixels] if pixels else [[0] * W for _ in range(H)]

    def copy(self):
        return _Cell(self.p)

    def ink(self):
        """(any, top, bottom, left, right), as ink() leaves them."""
        top, bottom, left, right, any_ = H, -1, W, -1, False
        for y in range(H):
            for x in range(W):
                if self.p[y][x]:
                    any_ = True
                    top, bottom = min(top, y), max(bottom, y)
                    left, right = min(left, x), max(right, x)
        return any_, top, bottom, left, right

    def flat(self):
        return [v for row in self.p for v in row]


# --- serif.c ----------------------------------------------------------------------

SERIF_BODY = 6


def _row_has_body(cell, frm, to, y):
    return any(cell.p[y][x] >= SERIF_BODY for x in range(frm, to + 1))


def serif_stem(cell):
    """Serif_Stem: (left, right, top, bottom) or None."""
    bottom = -1
    y = H - 1
    while y >= 0 and bottom < 0:
        if _row_has_body(cell, 0, W - 1, y):
            bottom = y
        y -= 1
    if bottom < 0:
        return None
    measure = bottom - 1 if bottom > 0 and _row_has_body(cell, 0, W - 1, bottom - 1) else bottom
    left = right = -1
    for x in range(W):
        if cell.p[measure][x] >= SERIF_BODY:
            if left < 0:
                left = x
            right = x
        elif left >= 0:
            break
    y = bottom
    while y > 0 and _row_has_body(cell, left, right, y - 1):
        y -= 1
    return left, right, y, bottom


def serif_add(cell, reach=1, outline=1):
    """Serif_Add on the small cell."""
    stem = serif_stem(cell)
    if not stem or reach < 1 or reach > 4:
        return False
    left, right, top, bottom = stem
    if left - reach - 1 < 0 or right + reach + 1 >= W or bottom + 1 >= H or top < 1:
        return False
    foot = max(cell.p[bottom][left:right + 1], default=0)
    head = max(cell.p[top][left:right + 1], default=0)
    added = []
    for k in range(1, reach + 1):
        cell.p[bottom][left - k] = foot
        added.append((left - k, bottom))
        cell.p[bottom][right + k] = foot
        added.append((right + k, bottom))
        cell.p[top][left - k] = head
        added.append((left - k, top))
    for ax, ay in added:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x, y = ax + dx, ay + dy
                if 0 <= x < W and 0 <= y < H and not cell.p[y][x]:
                    cell.p[y][x] = outline
    return True


# --- glyphs.c's helpers -------------------------------------------------------------

def _bright(cell):
    count = [0] * 16
    for row in cell.p:
        for v in row:
            count[v] += 1
    best = 14
    for x in range(8, 16):
        if count[x] > count[best] or (count[best] == 0 and count[x]):
            best = x
    return best


def _kind(cell, x, y, outline):
    index = cell.p[y][x]
    return 0 if not index else 1 if index == outline else 2


def _rows_differ(cell, a, b, outline):
    return sum(_kind(cell, x, a, outline) != _kind(cell, x, b, outline) for x in range(W))


def _drop_rows(cell, top, bottom, count, outline):
    while count > 0:
        count -= 1
        best, best_score = -1, 0
        for y in range(top + 2, bottom - 1):
            above, below = _rows_differ(cell, y, y - 1, outline), _rows_differ(cell, y, y + 1, outline)
            middle = 2 * y - top - bottom
            score = min(above, below) * 4 + abs(middle)
            if best < 0 or score < best_score:
                best, best_score = y, score
        if best < 0:
            return
        for y in range(best, 0, -1):
            cell.p[y] = cell.p[y - 1][:]
        cell.p[0] = [0] * W
        top += 1


def _stamp(cell, points, fill, outline):
    for x, y in points:
        if 0 <= x < W and 0 <= y < H:
            cell.p[y][x] = fill
    for px, py in points:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x, y = px + dx, py + dy
                if 0 <= x < W and 0 <= y < H and not cell.p[y][x]:
                    cell.p[y][x] = outline


def _mark_width(rows):
    return max((len(r) for r in rows[:3]), default=0)


def _mark_rows(grid, at, column, rows):
    y = 0
    while y < 3 and y < len(rows) and at + y < 8:
        x = 0
        while x < column + len(rows[y]) and x < 15:
            if not grid[at + y][x]:
                grid[at + y][x] = "."
            x += 1
        for x, ch in enumerate(rows[y]):
            if column + x >= 15:
                break
            if ch == "#":
                grid[at + y][column + x] = "#"
        y += 1
    return at + y


def _strlen(row):
    for i, ch in enumerate(row):
        if not ch:
            return i
    return len(row)


def serifed(letter, mark, tone, european):
    if not european or letter not in ("i", "l"):
        return False
    return not any(m in (CEDILLA, OGONEK, DOT_BELOW, HORN, FLIP, SLASH, BAR) for m in (mark, tone))


# --- GlyphCells ---------------------------------------------------------------------

class GlyphCells:
    """The port's small (8x12) letters for any character (see the module's
    notes). `face`: a ttf.Font or a list of them, the fonts the port would
    set other characters in (a mod's, then port_face_path()'s)."""

    def __init__(self, retail: card_text.RetailFont, face=None, european: bool = False):
        self.retail = retail
        self.faces = [] if face is None else list(face) if isinstance(face, (list, tuple)) else [face]
        self.european = bool(european)
        self._cells = {}
        self._shade = None
        self._zone_cache = {}

    def cell(self, character: str):
        """96 indices (8 across, 12 down, row by row; 0 transparent), or None
        when the port has no letter for it (it leaves it out of the text)."""
        if character not in self._cells:
            out = self._make(character)
            self._cells[character] = out.flat() if isinstance(out, _Cell) else out
        out = self._cells[character]
        return list(out) if out is not None else None

    def kind(self, character: str) -> str:
        """How the port makes it: "retail", "composed", "drawn", "font" or
        "none"."""
        c = ALIASES.get(character, character)
        if self._retail_uv(c) is not None or c == " ":
            return "retail"
        if character in LETTERS:
            return "drawn"
        if character in ACCENTS and self._retail_uv(ACCENTS[character][0]) is not None:
            return "composed"
        return "font" if self._face_for(character) is not None else "none"

    # -- the retail font

    @staticmethod
    def _retail_uv(c):
        if len(c) != 1:
            return None
        if c.isascii() and (c.isalnum() or c in RETAIL_PUNCTUATION):
            return card_text._cell_uv(c)
        other = RETAIL_OTHER.get(c)
        if isinstance(other, str):
            return card_text._cell_uv(other)
        return other

    def _read(self, letter):
        """read_cell for the small font: the retail letter's cell (blank for
        none)."""
        cell = _Cell()
        if letter and letter.isascii() and (letter.isalnum() or letter in card_text.PUNCTUATION):
            u, v = card_text._cell_uv(letter)
            t = self.retail.texels
            cell.p = [[t[(v + y) * 256 + u + x] for x in range(W)] for y in range(H)]
        return cell

    def _make(self, character):
        kind = self.kind(character)
        if kind == "retail":
            c = ALIASES.get(character, character)
            if c == " ":
                return [0] * (W * H)
            u, v = self._retail_uv(c)
            t = self.retail.texels
            cell = _Cell([[t[(v + y) * 256 + u + x] for x in range(W)] for y in range(H)])
            if self.european and c in ("i", "l"):
                serif_add(cell)        # serif_cell
            return cell
        if kind == "composed":
            return self._compose(*ACCENTS[character])
        if kind == "drawn":
            return self._render(LETTERS[character])
        if kind == "font":
            return self._render(self._set(character))
        return None

    # -- compose()

    def _compose(self, letter, mark, tone):
        outline = 1
        serifs = serifed(letter, mark, tone, self.european)
        cell = self._read(letter)
        any_, top, bottom, left, right = cell.ink()
        if not any_:
            return cell
        fill = _bright(cell)
        if letter in ("i", "j") and mark not in (CEDILLA, OGONEK, DOT_BELOW):
            n = self._read("n")
            n_any, n_top = n.ink()[:2]
            if n_any:
                for y in range(n_top):
                    cell.p[y] = [0] * W
                _, top, bottom, left, right = cell.ink()
        if serifs:
            stem = serif_stem(cell)
            if stem:
                for y in range(stem[2] - 1):
                    cell.p[y] = [0] * W
                _, top, bottom, left, right = cell.ink()
        if mark == DOTLESS:
            if serifs:
                serif_add(cell)
            return cell
        if mark == FLIP:
            source = cell.copy()
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    cell.p[y][x] = source.p[top + bottom - y][left + right - x]
            return cell
        points = []
        if mark in (SLASH, BAR):
            height = bottom - top
            if mark == BAR:
                y = top + _cdiv(height, 4) + 1
                for x in range(left - 1 if left > 0 else 0, right + 1):
                    points.append((x, y))
            else:
                ell = letter in ("l", "L")
                frm = top + _cdiv(height, 3) if ell else top + 1
                to = top + _cdiv(2 * height, 3) if ell else bottom - 1
                for y in range(frm, to + 1):
                    points.append((right - 1 - _cdiv((y - frm) * (right - left - 2), to - frm if to - frm > 0 else 1),
                                   y))
            _stamp(cell, points[:64], fill, outline)
            return cell
        above, below, horn = [], NONE, False
        for m in (mark, tone):
            if m == NONE:
                continue
            if m == HORN:
                horn = True
            elif m in (CEDILLA, OGONEK, DOT_BELOW):
                below = m
            else:
                above.append(m)
        grid = [[""] * 16 for _ in range(8)]
        height = width = 0
        if len(above) == 2:
            shape, tone_rows = SIDE_MARKS[above[0]], SIDE_MARKS[above[1]]
            height = _mark_rows(grid, 0, 0, shape)
            if _mark_width(shape) + 1 + _mark_width(tone_rows) <= W:
                height = max(height, _mark_rows(grid, 0, _mark_width(shape) + 1, tone_rows))
        elif len(above) == 1:
            height = _mark_rows(grid, 0, 0, SMALL_MARKS[above[0]])
        for y in range(height):
            width = max(width, _strlen(grid[y]))
        y0 = 0
        if not height:
            pass
        elif top < height:
            target = height - 1 if height > 2 else 1
            if top < target:
                _drop_rows(cell, top, bottom, target - top, outline)
                _, top, bottom, left, right = cell.ink()
        elif top == height:
            pass
        else:
            y0 = top - 1 - height
        x0 = _cdiv(left + right + 1, 2) - _cdiv(width, 2)
        if serifs and len(above) == 1 and above[0] == ACUTE:
            x0 -= 1
        if len(above) == 2:
            x0 = _cdiv(left + right + 1, 2) - _cdiv(_mark_width(SIDE_MARKS[above[0]]), 2)
            if x0 + width > W:
                x0 = W - width
            if x0 < 0:
                x0 = 0
        letter_top, letter_right = top, right
        for y in range(height):
            for x in range(_strlen(grid[y])):
                if grid[y][x] == "#":
                    points.append((x0 + x, y0 + y))
        if below == DOT_BELOW:
            cx = _cdiv(left + right + 1, 2)
            y0 = bottom + 1
            if y0 + 1 > H:
                n_any, _, n_bottom = self._read("n").ink()[:3]
                y0 = H - 1
                if n_any and n_bottom < bottom and n_bottom + 1 <= H:
                    y0, cx = n_bottom, right - 1
            points.append((cx, y0))
            if y0 > 0 and 0 <= cx < W and cell.p[y0 - 1][cx] and cell.p[y0 - 1][cx] != outline:
                cell.p[y0 - 1][cx] = outline
        elif below:
            rows = SMALL_MARKS[below]
            high, wide = min(3, len(rows)), _mark_width(rows)
            y0 = bottom if bottom < H - high else H - high
            x0 = right - wide + 1 if below == OGONEK else _cdiv(left + right + 1, 2) - _cdiv(wide, 2)
            for y in range(high):
                for x, ch in enumerate(rows[y]):
                    if ch == "#":
                        points.append((x0 + x, y0 + y))
        if horn:
            for i in range(2):
                points.append((letter_right - 1 + (i + 1) // 2, letter_top + 1 - i))
        _stamp(cell, points[:64], fill, outline)
        if serifs:
            serif_add(cell)
        return cell

    # -- render()

    def _row_shades(self):
        if self._shade is None:
            count = [[0] * 16 for _ in range(H)]
            for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                letter = self._read(c)
                for y in range(H):
                    for v in letter.p[y]:
                        if v >= 2:
                            count[y][v] += 1
            shade = []
            for y in range(H):
                best = 0
                for x in range(2, 16):
                    if count[y][x] > count[y][best]:
                        best = x
                shade.append(best if best else shade[y - 1] if y else 12)
            self._shade = shade
        return self._shade

    def _render(self, mask_rows):
        """render(): `mask_rows` 12 strings of '#' ink (or None: a blank cell,
        the port's when FreeType cannot load the glyph)."""
        cell = _Cell()
        if mask_rows is None:
            return cell
        shade = self._row_shades()
        mask = [[mask_rows[y][x] == "#" if x < len(mask_rows[y]) else False for x in range(W)] for y in range(H)]
        for y in range(H):
            for x in range(W):
                if mask[y][x]:
                    cell.p[y][x] = shade[y]
                elif any(mask[ny][nx] for ny in range(max(0, y - 1), min(H, y + 2))
                         for nx in range(max(0, x - 1), min(W, x + 2))):
                    cell.p[y][x] = 1
        return cell

    # -- the fonts

    def _face_for(self, character):
        code = ord(character) if len(character) == 1 else -1
        for face in self.faces:
            if face.has(code):
                return face
        return None

    def _zones(self, face, size):
        """The face's lines at `size` pixels, as FreeType's hinting moves
        them in the port's faces (measured on Noto Sans Bold at 10 pixels:
        its x-height and capitals rounded up a pixel, its descender to the
        nearest): (lines unhinted, lines hinted), bottom up."""
        key = (id(face), size)
        if key not in self._zone_cache:
            found = {0.0}
            for ch, top in (("p", False), ("x", True), ("H", True), ("d", True)):
                contours = face.outline(ord(ch))
                if contours:
                    box = ttf.bbox(contours)
                    found.add((box[3] if top else box[1]) * size)
            src = sorted(found)
            self._zone_cache[key] = (src, [math.ceil(v) if v > 0 else round(v) for v in src])
        return self._zone_cache[key]

    def _set(self, character):
        """render()'s FreeType path: the glyph at 10 pixels as 12 mask rows,
        its lines snapped as the hinting snaps them (see _zones; the
        hinting's other moves are not made)."""
        face = self._face_for(character)
        contours = face.outline(ord(character)) if face else None
        rows = [["."] * W for _ in range(H)]
        if not contours:
            return ["".join(r) for r in rows]     # a blank glyph (a space's): no ink
        size, baseline, room = 10, 10, 6
        src, dst = self._zones(face, size)

        def snap(y):
            if y <= src[0]:
                return y - src[0] + dst[0]
            if y >= src[-1]:
                return y - src[-1] + dst[-1]
            for i in range(len(src) - 1):
                if src[i] <= y <= src[i + 1]:
                    return dst[i] + (y - src[i]) * (dst[i + 1] - dst[i]) / (src[i + 1] - src[i])
            return y

        contours = [[(x * size, snap(y * size)) for x, y in c] for c in contours]
        x_min, y_min, x_max, y_max = ttf.bbox(contours)
        left_px, top_px = math.floor(x_min), math.ceil(y_max - 1e-6)
        width, height = math.ceil(x_max) - left_px, top_px - math.floor(y_min + 1e-6)
        if width <= 0 or height <= 0:
            return ["".join(r) for r in rows]
        bitmap = ttf.fill([[(x - left_px, top_px - y) for x, y in c] for c in contours], width, height)
        top = baseline - top_px
        squeezed = min(width, room)
        left = 1 + (room - squeezed) // 2
        for y in range(height):
            cy = top + y
            if cy < 1 or cy > H - 2:
                continue
            for x in range(squeezed):
                frm = x * width // room if width > room else x
                if bitmap[y * width + frm] >= 96:
                    rows[cy][left + x] = "#"
        return ["".join(r) for r in rows]
