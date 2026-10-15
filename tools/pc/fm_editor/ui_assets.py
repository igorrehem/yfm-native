"""The title screen's and the duel's pictures off the user's own disc, for the
UI tab's previews (ui_tab.py): nothing of the game's art is kept with the
editor, only where each piece is.

The pictures are VRAM the screens' loaders fill (notes/mrg-files.md,
tools/pc/extract_images.py): each sector of a package's image is a 64 x 16
word tile, sixteen of them one 64-word column of 256 rows, the next column
64 words to the right; the palettes are plain rectangles. A sprite is then
the texels at a page, through a palette, as the GPU reads them.

The sprites' places are the game's: measured from what the game draws (a
log of every primitive the software GPU ran, at the title, at each menu
entry with and without the cursor, and in a duel; 2026-10-07), and
checked against the code that sets them up (frontend.c, Duel_InitScene).
"""
from __future__ import annotations

from pathlib import Path

from . import disc, pngio

SECTOR = 2048
COLUMN = 16 * SECTOR           # one 64-word column of 256 rows
SU = "DATA/SU.MRG"

# --- the title (MainMenu_LoadPackageStage) --------------------------------------------
# SU.MRG sectors 0-63 at VRAM (512, 256), 64-95 at (896, 0); the palettes, 256 x 8
# at (0, 240), from byte 0x30000.
TITLE_SHEETS = ((0, 64, 512, 256), (64 * SECTOR, 32, 896, 0))
TITLE_PALETTE = (0x30000, 0, 240, 256, 8)
# The hieroglyph wall: 4 bits a texel at page (960, 0), palette (0, 244), 256 x 240,
# tiled every 256 across (MainMenu_DrawFrontendBackground).
WALL = (960, 0, 4, 0, 244, 0, 0, 256, 240)
# The three pictures: each part (x, y, w, h, u, v) at page (640, 256), 8 bits,
# through palette row 241, 242 or 243; in the order the game draws them.
LOGO_PARTS = [(0, 0, 128, 128, 0, 0), (128, 0, 128, 128, 128, 0), (128, 128, 128, 40, 0, 168),
              (256, 56, 56, 80, 128, 176), (256, 136, 64, 32, 192, 224), (256, 24, 64, 32, 192, 192),
              (0, 128, 128, 40, 0, 128)]
COPYRIGHT_PARTS = [(27, 200, 128, 16, 0, 208), (155, 200, 128, 16, 0, 224), (283, 200, 16, 16, 0, 240)]
PROMPT_PARTS = [(46, 177, 56, 16, 128, 128), (102, 177, 72, 16, 184, 128), (174, 177, 104, 16, 128, 144)]
LAYERS = {"logo": (LOGO_PARTS, 241), "copyright": (COPYRIGHT_PARTS, 242), "prompt": (PROMPT_PARTS, 243)}
# Where a mod's own picture for each stands (title_screen.c `middles`).
LAYER_MIDDLES = {"logo": (162, 90), "copyright": (163, 207), "prompt": (160, 185)}
# The menu entries, at page (512, 256), 8 bits, palette (0, 240): each part (dx, dy,
# w, h, u, v) from the entry's middle (160, its y), as it is and with the cursor on it.
ENTRY_SPRITES = {
    0: ([(-48, -16, 96, 32, 128, 160)],
        [(-52, -16, 104, 32, 0, 160)]),
    1: ([(-32, -16, 64, 32, 0, 32), (-24, -12, 48, 24, 48, 96)],
        [(-36, -16, 72, 32, 0, 0), (-24, -16, 48, 32, 64, 32)]),
    2: ([(-32, -16, 64, 32, 0, 32), (-28, -12, 32, 24, 96, 96), (4, -12, 8, 24, 120, 8), (12, -12, 16, 24, 112, 32)],
        [(-36, -16, 72, 32, 0, 0), (-28, -16, 56, 32, 0, 64)]),
    3: ([(-32, -16, 64, 32, 0, 32), (-28, -12, 56, 8, 0, 120), (-28, -4, 56, 8, 56, 120), (-20, 4, 16, 8, 112, 56),
         (-4, 4, 16, 8, 112, 120), (12, 4, 8, 8, 120, 0)],
        [(-36, -16, 72, 32, 0, 0), (-32, -16, 64, 32, 56, 64)]),
    4: ([(-44, -16, 56, 32, 0, 32), (12, -16, 32, 32, 160, 0), (-36, -12, 40, 24, 216, 24), (4, -12, 32, 24, 208, 48)],
        [(-44, -16, 64, 32, 0, 0), (20, -16, 24, 32, 136, 0), (-40, -16, 80, 32, 128, 64)]),
    5: ([(-48, -16, 96, 32, 128, 128)],
        [(-52, -16, 104, 32, 0, 128)]),
    6: ([(-56, -16, 112, 32, 128, 192)],
        [(-60, -16, 120, 32, 0, 192)]),
    7: ([(-40, -16, 56, 32, 0, 32), (16, -16, 24, 32, 168, 0), (-36, -12, 64, 24, 192, 0), (28, -12, 8, 24, 208, 24)],
        [(-44, -16, 64, 32, 0, 0), (20, -16, 24, 32, 136, 0), (-40, -16, 80, 32, 128, 32)]),
    8: ([(-48, -16, 96, 32, 128, 224)],
        [(-52, -16, 104, 32, 0, 224)]),
    9: ([(-40, -16, 56, 32, 0, 32), (16, -16, 24, 32, 168, 0), (-36, -12, 16, 24, 240, 48),
         (-20, -12, 48, 24, 208, 72), (28, -12, 8, 24, 208, 96)],
        [(-44, -16, 64, 32, 0, 0), (20, -16, 24, 32, 136, 0), (-40, -16, 80, 32, 128, 96)]),
    10: ([(-32, -16, 64, 32, 0, 32), (-24, -12, 48, 24, 0, 96)],
         [(-36, -16, 72, 32, 0, 0), (-24, -16, 48, 32, 72, 0)]),
}

# --- the duel ----------------------------------------------------------------------------
# The boot package (Main_LoadBootPackageStage): 48 sectors from WA 0xB48000 at VRAM
# (640, 0); its palettes 256 x 8 at (512, 248) from 0xB60000, then eight color ramps
# 16 x 8 at (640, 232) from 0xB61000.
BOOT_SHEET = (0xB48000, 48, 640, 0)
BOOT_RECTS = ((0xB60000, 512, 248, 256, 8), (0xB61000, 640, 232, 16, 8))
# A terrain's package (Duel_LoadPackageStage): from sector 0x16C6 + 235 a terrain,
# 64 sectors of image at (768, 256), then a sector of palettes, 256 x 16 at (256, 240).
TERRAIN_FIRST, TERRAIN_SECTORS = 0x16C6, 235
TERRAIN_SHEET = (64, 768, 256)
TERRAIN_PALETTE = (256, 240, 256, 16)
# The life-point panel: 64 x 40 at (248, 16), page (704, 0), 4 bits, palette (736, 252)
# on the player's turn and (752, 252) on the opponent's; its halves are rows 0-19 and
# 20-39. Its digits: 8 x 8 at page (896, 256), 8 bits, palette (256, 241), digit d at
# u = 8 d, v 88; the LP at (277, 19) and (277, 45), the deck counts at (294, 27) and
# (294, 37) (Duel_DrawLifePointsAndDeckCounts, from the panel's place 280, 32).
PANEL = (704, 0, 4, 736, 252, 128, 128, 64, 40)
PANEL_AT = (248, 16)
PANEL_TURN_CLUT = 752
DIGIT = (896, 256, 8, 256, 241, 0, 88, 8, 8)
LP_DIGITS = {"lp_opponent": ((277, 19, 4), (294, 27, 2)), "lp_player": ((277, 45, 4), (294, 37, 2))}
# The FIELD box (variant = the terrain, here the first's): its parts (x, y, w, h, u, v)
# at page (704, 0), 4 bits, palette (720, 252), drawn in this order.
FIELD_PARTS = [(12, 24, 8, 24, 24, 96), (20, 24, 24, 24, 40, 96), (60, 24, 8, 24, 32, 96), (44, 24, 16, 24, 48, 96),
               (20, 24, 40, 8, 24, 88), (32, 32, 16, 16, 112, 64)]
FIELD_PAGE = (704, 0, 4, 720, 252)
# The card bar: page (960, 256), 4 bits, palette (256, 240); its right part is its
# left mirrored (x, y, w, h, u, v, mirrored).
CARD_BAR_PARTS = [(0, 174, 128, 64, 0, 0, False), (128, 174, 64, 64, 0, 64, False), (192, 174, 128, 64, 0, 0, True),
                  (0, 238, 128, 8, 128, 56, False), (128, 238, 64, 8, 176, 0, False),
                  (192, 238, 128, 8, 128, 56, True)]
CARD_BAR_PAGE = (960, 256, 4, 256, 240)
# The hand's cursor: 16 x 16 mirrored at page (704, 0), palette (544, 252), u 16, v 144,
# its left at 6 + 60 a slot, its top 186.
HAND_CURSOR = (704, 0, 4, 544, 252, 16, 144, 16, 16)
HAND_CURSOR_AT = (6, 186)
# The field's cursor (func_800234E4) on the first zone: page (960, 256), 4 bits,
# palette (304, 240); its left half its right mirrored (x, y, w, h, u, v, mirrored).
FIELD_CURSOR_PARTS = [(33, 53, 32, 8, 176, 8, False), (33, 109, 32, 8, 208, 8, False),
                      (33, 77, 32, 16, 176, 16, False), (33, 61, 8, 16, 176, 32, False),
                      (33, 93, 8, 16, 176, 32, False), (57, 61, 8, 16, 184, 32, False),
                      (57, 93, 8, 16, 192, 32, False), (2, 53, 32, 8, 176, 8, True), (2, 61, 8, 16, 184, 32, True),
                      (2, 93, 8, 16, 192, 32, True), (2, 109, 32, 8, 208, 8, True), (2, 77, 32, 16, 176, 16, True)]
FIELD_CURSOR_PAGE = (960, 256, 4, 304, 240)
# Each element's place in the game's 320 x 240 (x, y, w, h), its middle the point a
# "scale" sizes it about (duel_ui.c).
DUEL_RECTS = {"lp_opponent": (248, 16, 64, 20), "lp_player": (248, 36, 64, 20), "field": (12, 24, 56, 24),
              "card_bar": (0, 174, 320, 72), "hand_cursor": (6, 186, 16, 16), "field_cursor": (2, 53, 64, 64)}


class Vram:
    """The console's 1024 x 512 words, filled as the loaders fill them."""

    def __init__(self):
        self.words = [0] * (1024 * 512)

    def columns(self, data: bytes, offset: int, sectors: int, x: int, y: int):
        """An image phase: `sectors` 64 x 16-word tiles, sixteen to a column."""
        for sector in range(sectors):
            column, tile = divmod(sector, 16)
            at = offset + sector * SECTOR
            for row in range(16):
                line = data[at + row * 128:at + row * 128 + 128]
                if len(line) < 128:
                    return
                base = (y + tile * 16 + row) * 1024 + x + column * 64
                for i in range(64):
                    self.words[base + i] = line[2 * i] | line[2 * i + 1] << 8

    def rect(self, data: bytes, offset: int, x: int, y: int, w: int, h: int):
        for row in range(h):
            line = data[offset + row * w * 2:offset + (row + 1) * w * 2]
            if len(line) < w * 2:
                return
            base = (y + row) * 1024 + x
            for i in range(w):
                self.words[base + i] = line[2 * i] | line[2 * i + 1] << 8

    def texel(self, page_x: int, page_y: int, bits: int, u: int, v: int) -> int:
        row = ((page_y + v) & 511) * 1024
        if bits == 4:
            return self.words[row + ((page_x + u // 4) & 1023)] >> (u & 3) * 4 & 15
        if bits == 8:
            return self.words[row + ((page_x + u // 2) & 1023)] >> (u & 1) * 8 & 255
        return self.words[row + ((page_x + u) & 1023)]

    def sprite(self, page_x, page_y, bits, clut_x, clut_y, u, v, w, h, mirrored=False) -> pngio.Image:
        """The texels as RGBA: 0x0000 clear, as the GPU leaves it."""
        out = bytearray(w * h * 4)
        clut = clut_y * 1024 + clut_x
        for y in range(h):
            for x in range(w):
                index = self.texel(page_x, page_y, bits, u + (w - 1 - x if mirrored else x), v + y)
                word = self.words[clut + index] if bits != 16 else index
                if word:
                    r, g, b = word & 31, word >> 5 & 31, word >> 10 & 31
                    at = (y * w + x) * 4
                    out[at:at + 4] = bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255))
        return pngio.Image(w, h, bytes(out))


def read_su(files) -> bytes | None:
    """SU.MRG beside the files the editor read (a folder or the disc image);
    None when they came another way."""
    source = Path(getattr(files, "source", "") or "")
    try:
        if source.is_dir():
            path = source / SU
            return path.read_bytes() if path.is_file() else None
        if source.is_file() and source.name.upper() == disc.EXECUTABLE:
            path = source.parent / SU
            return path.read_bytes() if path.is_file() else None
        if source.is_file():
            with disc.DiscImage(source) as image:
                found = image.find(SU)
                return image.read(*found) if found else None
    except (OSError, disc.GameFilesError):
        return None
    return None


def paste(canvas: pngio.Image, piece: pngio.Image, x: int, y: int) -> pngio.Image:
    """`piece` over `canvas` at x, y: its clear pixels show what is under."""
    out = bytearray(canvas.rgba)
    for row in range(piece.height):
        ty = y + row
        if not 0 <= ty < canvas.height:
            continue
        for col in range(piece.width):
            tx = x + col
            at = (row * piece.width + col) * 4
            if not 0 <= tx < canvas.width or not piece.rgba[at + 3]:
                continue
            o = (ty * canvas.width + tx) * 4
            a = piece.rgba[at + 3]
            if a == 255:
                out[o:o + 4] = piece.rgba[at:at + 4]
            else:
                for c in range(3):
                    out[o + c] = (piece.rgba[at + c] * a + out[o + c] * (255 - a)) // 255
                out[o + 3] = max(out[o + 3], a)
    return pngio.Image(canvas.width, canvas.height, bytes(out))


def blank(w: int, h: int, color=(0, 0, 0, 0)) -> pngio.Image:
    return pngio.Image(w, h, bytes(color) * (w * h))


def tint(image: pngio.Image, color: int, level: int = 255) -> pngio.Image:
    """Colors multiplied by 0xRRGGBB (as the game's 0x80 grey is), and by
    level/255 (the menu's dimming, PUSH START BUTTON's pulse)."""
    if color == 0xFFFFFF and level == 255:
        return image
    factors = [(color >> 16 & 255) * level, (color >> 8 & 255) * level, (color & 255) * level]
    out = bytearray(image.rgba)
    for c in range(3):
        f = factors[c]
        table = bytes(v * f // (255 * 255) for v in range(256))
        out[c::4] = image.rgba[c::4].translate(table)
    return pngio.Image(image.width, image.height, bytes(out))


def subtract(image: pngio.Image, level: int) -> pngio.Image:
    """What the menu's dimming does (a grey `level` taken away, GPU blend 2)."""
    if level <= 0:
        return image
    table = bytes(max(0, v - level) for v in range(256))
    out = bytearray(image.rgba.translate(table))
    out[3::4] = image.rgba[3::4]
    return pngio.Image(image.width, image.height, bytes(out))


def parse_color(text, default: int = 0xFFFFFF) -> int:
    """"#RRGGBB", "RRGGBB" or a number, as the game reads a color."""
    if isinstance(text, bool):
        return default
    if isinstance(text, int):
        return text if 0 <= text <= 0xFFFFFF else default
    if isinstance(text, str):
        value = text[1:] if text.startswith("#") else text
        if len(value) == 6:
            try:
                return int(value, 16)
            except ValueError:
                return default
    return default


class TitleArt:
    """The title's pictures from SU.MRG; `ok` False without it."""

    def __init__(self, su: bytes | None):
        self.ok = bool(su) and len(su) >= TITLE_PALETTE[0] + 256 * 8 * 2
        self.cache = {}
        if not self.ok:
            return
        self.vram = Vram()
        for offset, sectors, x, y in TITLE_SHEETS:
            self.vram.columns(su, offset, sectors, x, y)
        self.vram.rect(su, *TITLE_PALETTE)

    def wall(self) -> pngio.Image:
        """The background as the game tiles it over 320 x 240, unshaded."""
        if "wall" not in self.cache:
            tile = self.vram.sprite(*WALL)
            out = blank(320, 240, (0, 0, 0, 255))
            for x in range(0, 320, 64):
                out = paste(out, pngio.crop(tile, x % 256, 0, 64, 240), x, 0)
            self.cache["wall"] = out
        return self.cache["wall"]

    def layer(self, name: str) -> tuple:
        """(picture, left, top) of the logo, copyright or prompt."""
        if name not in self.cache:
            parts, row = LAYERS[name]
            left = min(p[0] for p in parts)
            top = min(p[1] for p in parts)
            right = max(p[0] + p[2] for p in parts)
            bottom = max(p[1] + p[3] for p in parts)
            out = blank(right - left, bottom - top)
            for x, y, w, h, u, v in parts:
                out = paste(out, self.vram.sprite(640, 256, 8, 0, row, u, v, w, h), x - left, y - top)
            self.cache[name] = (out, left, top)
        return self.cache[name]

    def entry(self, index: int, selected: bool) -> tuple:
        """(picture, dx, dy) of an entry from its middle."""
        key = ("entry", index, selected)
        if key not in self.cache:
            parts = ENTRY_SPRITES[index][1 if selected else 0]
            left = min(p[0] for p in parts)
            top = min(p[1] for p in parts)
            right = max(p[0] + p[2] for p in parts)
            bottom = max(p[1] + p[3] for p in parts)
            out = blank(right - left, bottom - top)
            for dx, dy, w, h, u, v in parts:
                out = paste(out, self.vram.sprite(512, 256, 8, 0, 240, u, v, w, h), dx - left, dy - top)
            self.cache[key] = (out, left, top)
        return self.cache[key]


class DuelArt:
    """The duel's pictures from WA_MRG.MRG (the boot package and a terrain's)."""

    def __init__(self, wa: bytes | None, terrain: int = 0):
        self.ok = bool(wa) and len(wa) > (TERRAIN_FIRST + terrain * TERRAIN_SECTORS + 65) * SECTOR
        self.cache = {}
        if not self.ok:
            return
        self.vram = Vram()
        self.vram.columns(wa, BOOT_SHEET[0], *BOOT_SHEET[1:])
        for rect in BOOT_RECTS:
            self.vram.rect(wa, *rect)
        first = (TERRAIN_FIRST + terrain * TERRAIN_SECTORS) * SECTOR
        self.vram.columns(wa, first, *TERRAIN_SHEET)
        self.vram.rect(wa, first + TERRAIN_SHEET[0] * SECTOR, *TERRAIN_PALETTE)

    def _cached(self, key, make):
        if key not in self.cache:
            self.cache[key] = make()
        return self.cache[key]

    def panel_half(self, half: int, opponent_turn: bool = False) -> pngio.Image:
        page_x, page_y, bits, clut_x, clut_y, u, v, w, h = PANEL
        clut_x = PANEL_TURN_CLUT if opponent_turn else clut_x
        return self._cached(("half", half, opponent_turn),
                            lambda: self.vram.sprite(page_x, page_y, bits, clut_x, clut_y, u, v + 20 * half, w, 20))

    def digit(self, d: int) -> pngio.Image:
        page_x, page_y, bits, clut_x, clut_y, u, v, w, h = DIGIT
        return self._cached(("digit", d), lambda: self.vram.sprite(page_x, page_y, bits, clut_x, clut_y, 8 * d, v, w, h))

    def field(self) -> pngio.Image:
        def make():
            out = blank(56, 24)
            for x, y, w, h, u, v in FIELD_PARTS:
                out = paste(out, self.vram.sprite(*FIELD_PAGE, u, v, w, h), x - 12, y - 24)
            return out
        return self._cached("field", make)

    def card_bar(self) -> pngio.Image:
        def make():
            out = blank(320, 72)
            for x, y, w, h, u, v, mirrored in CARD_BAR_PARTS:
                out = paste(out, self.vram.sprite(*CARD_BAR_PAGE, u, v, w, h, mirrored), x, y - 174)
            return out
        return self._cached("bar", make)

    def field_cursor(self) -> pngio.Image:
        def make():
            out = blank(64, 64)
            for x, y, w, h, u, v, mirrored in FIELD_CURSOR_PARTS:
                out = paste(out, self.vram.sprite(*FIELD_CURSOR_PAGE, u, v, w, h, mirrored), x - 2, y - 53)
            return out
        return self._cached("field_cursor", make)

    def hand_cursor(self) -> pngio.Image:
        return self._cached("cursor", lambda: self.vram.sprite(*HAND_CURSOR, mirrored=True))
