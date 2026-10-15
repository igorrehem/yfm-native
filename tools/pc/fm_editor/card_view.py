"""The card view's right-hand panel as the game draws it, for the Cards
tab's preview: its stone and frame off the disc, the type line, GUARDIAN
STAR and the stars, and the card text, in the game's letters (glyph_cells:
the port's own accented and drawn letters too) and colors, US or one of
the port's translations (languages/*.txt) with the European spacing.

Where everything comes from (checked against the game's screen):

* the panel: a 43-part sprite frame in the executable (SLUS file offset
  0x19CED2: count, flags 0x50 -- ten-bit offsets and a palette step a
  part), drawn by DisplayObject_RenderSpriteSheet at the panel's place
  (DuelEffect_UpdateCardViewerState: x 0x94, y 0x22 in a duel); its texels
  are the Build Deck package's 4-bit page at WA_MRG 0x10E4800 (VRAM 832, 0)
  and its two palettes, frame and stone, at 0x10E9600 and 0x10E9620 (CLUT
  256 and 272, row 247). Parts listed first are drawn on top.
* the text: string 3 (a monster) or 4 (any other card) of the executable's
  first bank, a box 168 x 192 at the panel's corner (TextBox_Create): F8 00
  puts in the type's icon (00) and name (80), the stars' icons (01, 02) and
  names (81, 82), and the card text (40); F8 01 starts a line further down,
  F8 02 moves right, F8 04/05 the letter size and line height, F8 0A the
  color; names from the name bank's strings 0x8300 + type and 0x8317 +
  star. Letters are 8 apart (the European spacing narrows some), icons 16;
  a line wraps once x reaches 168, and no row starts below 192 - 12.
* the card text is first wrapped as cards.c wraps a mod's (card_text.encode)."""
from __future__ import annotations

import re
import struct
from pathlib import Path

from . import card_text, glyph_cells, pngio

FRAME_AT = 0x19CED2                 # SLUS file offset of the panel's sprite frame
TEXELS_AT, TEXELS_SIZE = 0x10E4800, 8 * 2048
PALETTES_AT = 0x10E9600             # frame's 16 colors; the stone's follow
BOX_W, BOX_H = 0xA8, 0xC0
LEFT, TOP = 8, 8                    # the panel's corner in the picture (the frame reaches 8 past it)
WIDTH, HEIGHT = 180, 200             # to 192 below the corner: the ninth row's letters pass the frame
# The card text's part: its frame's top bar (72) to the ninth row's foot.
TEXT_TOP, TEXT_BOTTOM = TOP + 72, HEIGHT
GLYPH_DOWN = 2                      # func_80035E20: a letter is drawn 2 below its place
ICON_UP = 0                         # an icon at its place's top
SLUS_LOAD = 0x80010000 - 0x800      # the executable's file offset 0 in memory
STRING_TABLE, STRING_BASE = 0x801C0000, 0x801B0000
NAME_TABLE, NAME_BASE = 0x801D5800, 0x801D0000
FLAT_PANEL, FLAT_FRAME = card_text.PANEL, card_text.FRAME
TOKEN = re.compile(r"\{([^{}]*)\}|.", re.S)
SECONDARY = {0x00: 1, 0x01: 1, 0x02: 1, 0x03: 5, 0x04: 1, 0x05: 2, 0x06: 2, 0x07: 2, 0x08: 0, 0x09: 0, 0x0A: 1,
             0x0B: 1, 0x0C: 1, 0x0D: 6, 0x0E: 2, 0x11: 1, 0x12: 0, 0x13: 0, 0x14: 1, 0x15: 1, 0x16: 0, 0x19: 1,
             0x1A: 0, 0x1B: 1, 0x1C: 1, 0x1D: 1, 0x1E: 1, 0x1F: 1, 0x20: 1, 0x21: 2, 0x22: 1, 0x25: 0, 0x27: 2,
             0x28: 2, 0x29: 0, 0x2A: 0}
# Language codes the port has (language.h), the European ones spaced as PAL.
LANGUAGES = {"en-us": "English (US)", "en-eu": "English (Europe)", "de": "Deutsch", "fr": "Français",
             "it": "Italiano", "es": "Español"}


def _rgb15(word):
    return None if word == 0 else ((word & 31) << 3, (word >> 5 & 31) << 3, (word >> 10 & 31) << 3)


def pal_advance(character: str):
    """(the advance's change from 8, the drawing's shift): PalText_Advance."""
    if character == " ":
        return -1, 0
    if character == "'":
        return -6, -3
    if character in "fil":
        return -2, -1
    if character in ".,":
        return -2, 0
    return 0, 0


# --- the panel ---------------------------------------------------------------------

def panel_picture(slus: bytes, wa: bytes):
    """The stone and the frame, WIDTH x HEIGHT RGBA (the panel's corner at
    LEFT, TOP), or None when the game files have not got them."""
    if len(slus) < FRAME_AT + 4 or len(wa) < PALETTES_AT + 64:
        return None
    count, flags = slus[FRAME_AT], slus[FRAME_AT + 1]
    if not 0 < count <= 64 or len(slus) < FRAME_AT + 4 + 6 * count:
        return None
    texels = wa[TEXELS_AT:TEXELS_AT + TEXELS_SIZE]
    palettes = [[_rgb15(wa[PALETTES_AT + 32 * step + 2 * i] | wa[PALETTES_AT + 32 * step + 2 * i + 1] << 8)
                 for i in range(16)] for step in range(2)]
    rgba = bytearray(WIDTH * HEIGHT * 4)
    parts = []
    for k in range(count):
        dx, dy, cell, size = struct.unpack_from("<BBHH", slus, FRAME_AT + 4 + 6 * k)
        if flags & 0x10:        # ten-bit offsets: their top bits in the cell and size words
            dx |= (cell & 0xC000) >> 6
            dy |= (size & 0xC000) >> 6
            dx -= 0x400 if dx & 0x200 else 0
            dy -= 0x400 if dy & 0x200 else 0
        else:
            dx -= 256 if dx > 127 else 0
            dy -= 256 if dy > 127 else 0
        step = size & 0xF if flags & 0xE0 else 0
        parts.append((dx, dy, (cell & 0x1F) << 3, (cell & 0x3E0) >> 2, ((size >> 2) & 0x78) + 8,
                      ((size >> 6) & 0x78) + 8, step, bool(cell & 0x2000)))
    for dx, dy, u, v, w, h, step, flip in reversed(parts):      # the first is drawn last, on top
        colors = palettes[min(step, 1)]
        for y in range(h):
            row = (v + y) * 128
            for x in range(w):
                tu = u + (w - 1 - x if flip else x)
                if row + tu // 2 >= len(texels):
                    continue
                color = colors[texels[row + tu // 2] >> 4 * (tu & 1) & 15]
                X, Y = LEFT + dx + x, TOP + dy + y
                if color and 0 <= X < WIDTH and 0 <= Y < HEIGHT:
                    rgba[(Y * WIDTH + X) * 4:(Y * WIDTH + X) * 4 + 4] = bytes((*color, 255))
    return rgba


def flat_panel():
    """Without the panel's pictures: its colors, as the old preview drew it."""
    rgba = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            inside = LEFT <= x < LEFT + 164 and TOP <= y < TOP + BOX_H - 8
            rgba += bytes((*(FLAT_PANEL if inside else FLAT_FRAME), 255))
    return rgba


# --- the text ----------------------------------------------------------------------

def bytes_tokens(data: bytes, glyphs: dict):
    """The game's text bytes as tokens: ("char", c), ("nl",), ("code", words)."""
    out, at = [], 0
    while at < len(data):
        b = data[at]
        if b == 0xFF:
            break
        if b == 0xFE:
            out.append(("nl",))
            at += 1
        elif b == 0xF8 and at + 1 < len(data) and data[at + 1] in SECONDARY:
            n = SECONDARY[data[at + 1]]
            out.append(("code", ["f8"] + ["%02X" % x for x in data[at + 1:at + 2 + n]]))
            at += 2 + n
        elif 0xF0 <= b <= 0xF5 and at + 1 < len(data):
            out.append(("char", glyphs.get(((b - 0xF0) << 8) | data[at + 1], "")))
            at += 2
        elif b >= 0xF0:
            at += 1         # another code the panel has none of
        else:
            out.append(("char", glyphs.get(b, "")))
            at += 1
    return out


def text_tokens(text: str):
    """A text with the listing's codes (a card text, a translation's string)
    as tokens; a newline is a line break."""
    out = []
    for match in TOKEN.finditer(text):
        if match.group(1) is not None:
            words = match.group(1).split()
            if not words:
                continue
            if words[0] == "sp":
                out.append(("char", " "))
            elif words[0] == "f8":
                out.append(("code", [w.upper() if i else w for i, w in enumerate(words)]))
            else:
                out.append(("code", words))
        elif match.group(0) == "\n":
            out.append(("nl",))
        elif match.group(0) != "\r":
            out.append(("char", match.group(0)))
    return out


class Listing:
    """A translation's text listing (notes/translation.md), its strings as
    tokens, following {cont} into the next item and {jump} to a label."""

    def __init__(self, text: str):
        self.items, self.by_id, self.by_label = [], {}, {}
        current = None
        for raw in text.split("\n"):
            line = raw.rstrip("\r")
            starts = line.startswith("[") or line.startswith("{:")
            if starts or line.startswith("@bank") or (current is None and not starts):
                current = None
            if starts:
                head, ids = line, []
                if head.startswith("["):
                    close = head.index("]")
                    ids = [int(w, 16) for w in head[1:close].split()]
                    head = head[close + 1:]
                current = {"lines": []}
                self.items.append(current)
                for i in ids:
                    self.by_id.setdefault(i, len(self.items) - 1)
                for label in re.findall(r"\{:(L[0-9A-Fa-f]{4})\}", head.split("#")[0]):
                    self.by_label[label.upper()] = len(self.items) - 1
                rest = re.sub(r"^(\{:L[0-9A-Fa-f]{4}\} *)+", "", line) if not line.startswith("[") else ""
                if rest:
                    current["lines"].append(rest)
                continue
            if current is not None:
                current["lines"].append(line)

    def tokens(self, string_id: int):
        if string_id not in self.by_id:
            return None
        out, item, seen = [], self.by_id[string_id], set()
        while item is not None and item < len(self.items) and item not in seen:
            seen.add(item)
            following = None
            lines = self.items[item]["lines"]
            for n, line in enumerate(lines):
                stop = False
                for token in text_tokens(line):
                    if token[0] == "code" and token[1][0] == "end":
                        stop = True
                        break
                    if token[0] == "code" and token[1][0] == "cont":
                        following = item + 1
                        stop = True
                        break
                    if token[0] == "code" and token[1][0] == "jump":
                        following = self.by_label.get(token[1][1].upper())
                        stop = True
                        break
                    out.append(token)
                if stop:
                    break
                if n + 1 < len(lines):
                    out.append(("nl",))
            item = following
        return out

    def text(self, string_id: int) -> str | None:
        tokens = self.tokens(string_id)
        if tokens is None:
            return None
        return "".join(t[1] if t[0] == "char" else "\n" if t[0] == "nl" else "" for t in tokens)


def language_folders():
    """Where the translations may be: beside the repository's tools, and
    beside a game the editor ships with."""
    here = Path(__file__).resolve()
    folders = [here.parent / "languages"]
    if len(here.parents) > 3:       # in the repository; the packed program's folder is shallower
        folders.insert(0, here.parents[3] / "languages")
    return folders


def load_listing(code: str, folders=None):
    for folder in folders or language_folders():
        path = folder / f"{code}.txt"
        if path.is_file():
            return Listing(path.read_text(encoding="utf-8", errors="replace"))
    return None


class CardView:
    """What the card view's panel needs off one disc: the panel, the fonts,
    the layouts and names."""

    def __init__(self, slus: bytes, wa: bytes):
        self.retail = card_text.RetailFont(wa)
        self.panel = panel_picture(slus, wa) or flat_panel()
        self.slus = slus
        self._glyphs = {}           # european -> GlyphCells
        self._listings = {}
        self.folders = None         # where translations are looked for (language_folders())
        try:
            import text_listing
            from . import gamedata
            image = gamedata._image(slus)
            self.characters = text_listing.glyph_characters(image)
            self.image = image
        except Exception:           # an executable this cannot read: no names, no layout
            self.image, self.characters = None, {}

    def glyphs(self, european: bool):
        if european not in self._glyphs:
            self._glyphs[european] = glyph_cells.GlyphCells(self.retail, european=european)
        return self._glyphs[european]

    def listing(self, language: str):
        if language not in self._listings:
            self._listings[language] = load_listing(language, self.folders) if language != "en-us" else None
        return self._listings[language]

    def _game_string(self, table, base, index):
        if self.image is None:
            return []
        try:
            at = base + self.image.u16(table + 2 * index)
            return bytes_tokens(self.image.bytes(at, 256), self.characters)
        except Exception:
            return []

    def layout(self, monster: bool, language: str):
        listing = self.listing(language)
        if listing is not None:
            tokens = listing.tokens(3 if monster else 4)
            if tokens is not None:
                return tokens
        return self._game_string(STRING_TABLE, STRING_BASE, 3 if monster else 4)

    def name(self, index: int, language: str):
        """String 0x8300 + index of the name bank (a type's, a star's)."""
        listing = self.listing(language)
        if listing is not None:
            tokens = listing.tokens(0x8300 + index)
            if tokens is not None:
                return tokens
        return self._game_string(NAME_TABLE, NAME_BASE, 0x300 + index)

    def render(self, card_type: int, star1: int, star2: int, text: str, language: str = "en-us",
               colors: dict | None = None, scale: int = 1, star_names: dict | None = None,
               text_only: bool = False):
        """The panel with the card's lines, as pngio.Image at `scale`.
        colors: a card_text_colors rule's {"description", "guardian_star"} ramps;
        star_names: a mod's names for its stars (past the disc's ten: no icon);
        text_only: just the card text's box (its frame, stone and letters)."""
        european = language != "en-us"
        picture = Drawing(bytearray(self.panel), self.retail, self.glyphs(european), european)
        monster = card_type < 20
        colors = colors or {}
        description = text_tokens("".join(card_text.encode(text, colors=True)))
        inserts = {0x00: [("icon", card_type)], 0x80: self.name(card_type, language),
                   0x40: [("color", colors.get("description", 0))] + description}
        for n, star in ((1, star1), (2, star2)):
            if star:
                named = (star_names or {}).get(star)
                inserts[n] = [("icon", star + 0x17)] if star <= 10 else [("char", " "), ("char", " ")]
                inserts[0x80 + n] = [("color", colors.get("guardian_star", 0))] + (
                    text_tokens(named) if named is not None else self.name(star + 0x17, language))
            else:
                inserts[n], inserts[0x80 + n] = [], []
        picture.run(self.layout(monster, language), inserts)
        picture.finish()
        image = pngio.Image(WIDTH, HEIGHT, bytes(picture.rgba))
        if text_only:
            image = pngio.crop(image, 0, TEXT_TOP, WIDTH, TEXT_BOTTOM - TEXT_TOP)
        return pngio.scale_nearest(image, scale) if scale > 1 else image


class Drawing:
    """The text box's cursor over the panel (TextBox and func_80035E20).
    What the text puts down first stays on top, as the game sorts it (an
    icon's foot stays over the top of the next line's letters)."""

    def __init__(self, rgba, retail, glyphs, european):
        self.rgba, self.retail, self.glyphs, self.european = rgba, retail, glyphs, european
        self.letters = {}       # (x, y) -> the text's color there, the first put down
        self.x = self.y = 0
        self.line = 12
        self.color = 0
        self.done = False

    def put(self, X, Y, color):
        if 0 <= X < WIDTH and 0 <= Y < HEIGHT:
            self.rgba[(Y * WIDTH + X) * 4:(Y * WIDTH + X) * 4 + 4] = bytes((*color, 255))

    def finish(self):
        for (X, Y), color in self.letters.items():
            self.put(X, Y, color)

    def newline(self, down=None):
        self.x = 0
        self.y += self.line if down is None else down
        if self.y + 12 > BOX_H:
            self.done = True

    def char(self, c):
        if self.x >= BOX_W:
            self.newline()
        if self.done:
            return
        change, shift = pal_advance(c) if self.european else (0, 0)
        if c != " ":
            cell = self.glyphs.cell(c)
            if cell is None:
                return      # the port has no letter for it: it takes no room
            ramp = self.retail.ramps[self.color] if self.color < len(self.retail.ramps) else self.retail.ramps[0]
            for i, index in enumerate(cell):
                if index:
                    self.letters.setdefault((LEFT + self.x + shift + i % 8, TOP + self.y + GLYPH_DOWN + i // 8),
                                            ramp[index])
        self.x += 8 + change

    def icon(self, n, up=ICON_UP):
        if self.x >= BOX_W:
            self.newline()
        if self.done:
            return
        icon = self.retail.icon(n)
        if icon is not None:
            width, height, rgba = icon
            for y in range(height):
                for x in range(width):
                    at = (y * width + x) * 4
                    if rgba[at + 3]:
                        self.letters.setdefault((LEFT + self.x + x, TOP + self.y - up + y), tuple(rgba[at:at + 3]))
        self.x += 16

    def run(self, tokens, inserts=None):
        for token in tokens:
            if self.done:
                return
            kind = token[0]
            if kind == "char":
                for c in token[1]:
                    self.char(c)
            elif kind == "nl":
                self.newline()
            elif kind == "icon":
                self.icon(token[1], 0)       # a type's or a star's, put in by F8 00
            elif kind == "color":
                self.color = token[1]
            elif kind == "code" and token[1][0] == "f8" and len(token[1]) >= 2:
                op = int(token[1][1], 16)
                args = [int(w, 16) for w in token[1][2:]]
                if op == 0x00 and args and inserts is not None:
                    self.run(inserts.get(args[0], []))
                elif op == 0x01 and args:
                    self.newline(args[0] - 256 if args[0] > 127 else args[0])
                elif op == 0x02 and args:
                    self.x += args[0] - 256 if args[0] > 127 else args[0]
                elif op == 0x05 and len(args) >= 2:
                    # The PAL's 13-pixel lines are the US's 12 here (pal_text.c).
                    self.line = 12 if args[1] == 0x0D else args[1]
                elif op == 0x0A and args:
                    self.color = args[0]
                elif op == 0x0B and args:
                    self.icon(args[0])
            elif kind == "code" and token[1][0] == "g" and len(token[1]) > 1:
                pass        # a numbered glyph: none in the panel's own strings
