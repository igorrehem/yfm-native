"""The duel board's textures in a mod: the floor and the platform's walls of
each field, as texture pack entries in the mod's pack (notes/modding.md,
"Texture packs"; art.py keeps the pack's manifest, this module owns the
board's entries in it), and their tints as "data" patches of the palettes.

Where they are (tools/pc/extract_images.py, notes/image-remaster.md "Third:
the duel"): each field is a 235-sector package of WA_MRG.MRG from sector
0x16C6 (Normal, Forest, Wasteland, Mountain, Sogen, Umi, Yami, as
gDuel_bTerrain counts them), and its last phase, 32 sectors from sector
+203, is the board: two 64-word columns of 256 rows uploaded to VRAM
(640, 256), four bits a texel.

* The first column is the floor: five rows of tiles, each read through its
  own 16-color palette, the palettes at +0x7F00 of the column itself (rows
  254 and 255, where the game reads them in VRAM). Seen from the player,
  far to near: the opponent's back row, their front row, the centre strip
  (drawn twice, the near half turned round), your front row, your back
  row; each texture's top is the far side. A field card (Forest ... Yami,
  DuelEffect_ApplyTerrain) loads only this column of the new field's
  package (DUEL_TERRAIN_EFFECT_DATA_SECTOR_COUNT, 16 sectors).
* The second column is the platform's walls and trim, ten pieces through
  ten palettes from +0xF120 of the phase. Where each is drawn was found
  with a pack painting each its own color (2026-10-07). The duel keeps
  the walls of the field it began on.

A replacement is a pack entry per piece: the words of its rectangle read
through its palette, nothing else, so no two entries share a word and each
shows at the console's resolution as well (texture_pack.c draws only the
first reading of shared words there). A tint rewrites the piece's palette on
the disc ("data" patch of WA_MRG.MRG): every color multiplied by the tint,
exact at every resolution, the game's art never in the mod. A replaced
piece draws the mod's colors, so a tint is for the game's own picture.

The floor is also one picture, the five rows in the board's order (far to
near, the centre strip once), split into the rows' textures."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import pngio
from .pngio import Image

SECTOR = 2048
ARCHIVE = "WA_MRG.MRG"
ARCHIVE_FILE = "\\DATA\\WA_MRG.MRG;1"
FIRST_SECTOR, PACKAGE_SECTORS = 0x16C6, 235
PHASE_SECTOR, PHASE_BYTES = 203, 32 * SECTOR
MODEL_SECTOR, MODEL_BYTES = 198, 5 * SECTOR    # phase 11: the board's model (board_model.py)
COLUMN_BYTES = 16 * SECTOR      # 64 words x 256 rows
ROW_BYTES = 128
MAX_SCALE = 4
DIR = "board"
WHITE = 0xFFFFFF

# gDuel_bTerrain's values, named as the field cards are (tables.c).
TERRAINS = ("normal", "forest", "wasteland", "mountain", "sogen", "umi", "yami")
TERRAIN_LABELS = {"normal": "Normal", "forest": "Forest", "wasteland": "Wasteland", "mountain": "Mountain",
                  "sogen": "Sogen", "umi": "Umi", "yami": "Yami"}


@dataclass(frozen=True)
class Part:
    key: str
    label: str
    column: int             # 0 the floor, 1 the walls
    x: int                  # texels within the column (four bits each)
    y: int
    w: int
    h: int
    palette: int            # the palette's first byte from the phase's
    what: str = ""
    warnings: tuple = ()

    @property
    def group(self) -> str:
        return "floor" if self.column == 0 else "walls"


WALLS_STAY = "A field card changes only the floor: the walls stay those of the field the duel began on."
WINGS = "The end walls have the middle block between the wings; the long sides show the wings alone."
PARTS = [
    # The floor's rows: 51x51 tiles side by side, far to near as the board has
    # them. A rectangle reaches the texel its polygons' far corners name (row
    # 51 of a row, 253 of the centre strip's): the pack looks a primitive up
    # by its first corner, and one outside every entry would be the game's.
    Part("opponent_back", "Opponent's back row", 0, 0, 0, 256, 52, 0x7F00,
         "The five zones farthest from you: 51x51 tiles side by side."),
    Part("opponent_front", "Opponent's front row", 0, 0, 52, 256, 52, 0x7F20,
         "The opponent's monster zones."),
    Part("centre", "Centre strip", 0, 0, 208, 256, 46, 0x7F80,
         "The raised strip between the two sides.",
         ("Drawn twice: the near half is this picture turned round.",)),
    Part("your_front", "Your front row", 0, 0, 104, 256, 52, 0x7F40, "Your monster zones."),
    Part("your_back", "Your back row", 0, 0, 156, 256, 52, 0x7F60, "Your magic and trap zones, nearest you."),
    # The walls (the second column).
    Part("wall_left", "Wall, left wing", 1, 0, 0, 128, 64, 0xF120,
         "The left half of the sun disc's wings, on the platform's walls.",
         (WINGS, WALLS_STAY)),
    Part("wall_right", "Wall, right wing", 1, 128, 0, 128, 64, 0xF140,
         "The right half of the wings.",
         (WINGS, WALLS_STAY)),
    Part("wall_middle", "Wall, middle", 1, 0, 64, 64, 64, 0xF160, "The block between the wings.", (WALLS_STAY,)),
    Part("wall_corners", "Wall corners", 1, 64, 64, 64, 64, 0xF180, "The bricks at each end of a wall.",
         (WALLS_STAY,)),
    Part("trim", "Top trim", 1, 96, 192, 128, 16, 0xF280, "The bar along the top of the walls.",
         ("Drawn in thin slices: a plain band along its length looks best.", WALLS_STAY)),
    Part("corner_triangles", "Triangles", 1, 0, 128, 96, 96, 0xF200,
         "The sloping triangles at the platform's corners and at the ends of the centre strip.",
         ("Only triangles of it are drawn.", WALLS_STAY)),
    Part("corner_edges", "Triangle edges", 1, 144, 128, 48, 64, 0xF240, "Thin strips under the triangles.",
         (WALLS_STAY,)),
    Part("centre_step", "Centre step", 1, 192, 128, 64, 48, 0xF260, "The lip where the centre strip rises.",
         (WALLS_STAY,)),
    Part("centre_sides", "Centre sides", 1, 128, 64, 128, 64, 0xF1A0, "The sides of the raised centre strip.",
         (WALLS_STAY,)),
    Part("centre_ends", "Centre side ends", 1, 96, 128, 48, 64, 0xF220, "The ends of the centre strip's sides.",
         (WALLS_STAY,)),
]
BY_KEY = {p.key: p for p in PARTS}
FLOOR = [p for p in PARTS if p.column == 0]          # the board's order, far to near
WALLS = [p for p in PARTS if p.column == 1]
FLOOR_W = 256
FLOOR_H = sum(p.h for p in FLOOR)                    # 254: the floor as one picture


def phase_offset(terrain: str) -> int:
    """The board phase's first byte in WA_MRG.MRG."""
    return (FIRST_SECTOR + TERRAINS.index(terrain) * PACKAGE_SECTORS + PHASE_SECTOR) * SECTOR


def image_offset(terrain: str, part: Part) -> int:
    return phase_offset(terrain) + part.column * COLUMN_BYTES + part.y * ROW_BYTES + part.x // 2


def palette_offset(terrain: str, part: Part) -> int:
    return phase_offset(terrain) + part.palette


def entry(terrain: str, part: Part, file: str) -> dict:
    """The pack entry of a piece (texture_pack.c's keys)."""
    return {"file": file, "alias": f"duel board, {TERRAIN_LABELS[terrain]}: {part.label.lower()}",
            "archive": ARCHIVE, "offset": image_offset(terrain, part), "words": part.w // 4, "rows": part.h,
            "bpp": 4, "clut_offset": palette_offset(terrain, part), "clut_entries": 16, "width": part.w,
            "height": part.h, "crop_left": 0, "stride": 64, "row_offsets": None}


# --- the disc's pictures ---------------------------------------------------------------

@dataclass
class BoardData:
    """The seven boards as the disc has them (the phases' bytes)."""
    phases: dict = field(default_factory=dict, repr=False)     # terrain -> 64 KiB
    models: dict = field(default_factory=dict, repr=False)     # terrain -> the model's 10 KiB

    @property
    def ok(self) -> bool:
        return len(self.phases) == len(TERRAINS)


def read(wa: bytes) -> BoardData:
    data = BoardData()
    for terrain in TERRAINS:
        start = phase_offset(terrain)
        if len(wa) >= start + PHASE_BYTES:
            data.phases[terrain] = bytes(wa[start:start + PHASE_BYTES])
        start = (FIRST_SECTOR + TERRAINS.index(terrain) * PACKAGE_SECTORS + MODEL_SECTOR) * SECTOR
        if len(wa) >= start + MODEL_BYTES:
            data.models[terrain] = bytes(wa[start:start + MODEL_BYTES])
    return data


def disc(project) -> BoardData:
    data = getattr(project.retail, "board", None)
    return data if data is not None else BoardData()


def palette_words(data: BoardData, terrain: str, part: Part) -> list:
    blob = data.phases[terrain]
    return [blob[part.palette + 2 * i] | blob[part.palette + 2 * i + 1] << 8 for i in range(16)]


def color(word: int):
    """RGBA of a VRAM color word; 0 is transparent."""
    if word == 0:
        return 0, 0, 0, 0
    r, g, b = word & 31, (word >> 5) & 31, (word >> 10) & 31
    return (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255


def tint_word(word: int, tint: int) -> int:
    """A palette color multiplied by the tint (0xRRGGBB, 255 a channel as
    it is), its semi-transparency bit kept. The clear color stays clear,
    and a color the tint takes to black becomes the opaque black the
    texture packs use (0x8000 with the bit, 0x0001 without; 0 is clear)."""
    if word == 0 or tint == WHITE:
        return word
    parts = [(word >> s & 31) for s in (0, 5, 10)]
    factors = [tint >> 16 & 255, tint >> 8 & 255, tint & 255]
    r, g, b = ((c * f + 127) // 255 for c, f in zip(parts, factors))
    out = r | g << 5 | b << 10
    if out == 0:
        return 0x8000 if word & 0x8000 else 0x0001
    return out | (word & 0x8000)


def tinted(words: list, tint: int) -> list:
    return [tint_word(w, tint) for w in words]


def tint_choices(retail: list, words: list):
    """Each channel's values (0-255) a tint turning the retail palette into
    `words` could have: a set per channel, red first. A word the tint took
    to black (tint_word) holds each channel at 0, but 0x0001 is black and
    the darkest red alike: its red may be 0 or 1."""
    def allowed(a, b, bits):
        if b == 0x8000 and a & 0x8000:
            return (0,)
        if b == 0x0001 and not a & 0x8000:
            return (0, 1) if bits == 0 else (0,)
        return (b >> bits & 31,)
    pairs = [(a, b) for a, b in zip(retail, words) if a]
    return [{t for t in range(256)
             if all(((a >> bits & 31) * t + 127) // 255 in allowed(a, b, bits) for a, b in pairs)}
            for bits in (0, 5, 10)]


def pick_tint(retail_and_words: list):
    """The tint that turns each retail palette into its words, or None:
    of the values every palette allows a channel, the highest, so a tint
    reads back as itself (set_tint stores it so)."""
    channels = None
    for retail, words in retail_and_words:
        choices = tint_choices(retail, words)
        channels = choices if channels is None else [a & b for a, b in zip(channels, choices)]
    if not channels or not all(channels):
        return None
    tint = max(channels[0]) << 16 | max(channels[1]) << 8 | max(channels[2])
    return tint if all(tinted(r, tint) == list(w) for r, w in retail_and_words) else None


def recover_tint(retail: list, words: list):
    return pick_tint([(retail, words)])


def common_tint(project, terrain: str, parts) -> int:
    """The one tint the pieces show (each piece's own reading may differ
    and still be its patch), white for none, None when they differ."""
    st = state(project)
    data = disc(project)
    tints = [st.tints.get((terrain, p.key)) for p in parts]
    if all(t is None for t in tints):
        return WHITE
    if any(t is None for t in tints) or not data.ok:
        return None if len(set(tints)) > 1 else tints[0]
    retail = [palette_words(data, terrain, p) for p in parts]
    pairs = [(words, tinted(words, t)) for words, t in zip(retail, tints)]
    return pick_tint(pairs)


def piece_image(data: BoardData, terrain: str, part: Part, tint: int = WHITE) -> Image:
    """A piece as the game draws it at the console's resolution, through
    its palette (tinted): a color word of 0 is clear. A byte holds two
    texels, the low four bits first; the pieces start and end on a whole
    byte, so a row is its bytes each turned into two pixels."""
    blob = data.phases[terrain]
    palette = [bytes(color(w)) for w in tinted(palette_words(data, terrain, part), tint)]
    pairs = [palette[byte & 15] + palette[byte >> 4] for byte in range(256)]
    base = part.column * COLUMN_BYTES + part.x // 2
    out = b"".join(b"".join(map(pairs.__getitem__, blob[row:row + part.w // 2]))
                   for row in range(base + part.y * ROW_BYTES, base + (part.y + part.h) * ROW_BYTES, ROW_BYTES))
    return Image(part.w, part.h, out)


# --- the mod's state -----------------------------------------------------------------------

@dataclass
class Picture:
    file: str               # relative to the pack's directory
    image: Image = None     # None until read
    pending: bool = False   # to be written on save


class BoardArt:
    def __init__(self):
        self.pictures = {}      # (terrain, part key) -> Picture (one Picture for all seven fields' copies)
        self.tints = {}         # (terrain, part key) -> 0xRRGGBB, never white
        self.version = 0        # changes with every edit (the page's pictures follow it)


def state(project) -> BoardArt:
    st = getattr(project, "board_art", None)
    if st is None:
        st = project.board_art = BoardArt()
    return st


def _art():
    from . import art
    return art


def touched(project, pictures: bool = True):
    st = state(project)
    st.version += 1
    if pictures:
        _art().state(project).changed = True


def _folder(project):
    art = _art()
    folder = art.state(project).folder or project.source_dir
    return None if folder is None else Path(folder) / art.pack_dir(project)


def picture(project, pic: Picture):
    """The mod's image of a Picture (read from the mod folder the first
    time), or None."""
    if pic.image is None:
        folder = _folder(project)
        if folder is None:
            return None
        try:
            pic.image = pngio.read(folder / pic.file)
        except (OSError, pngio.PngError):
            return None
    return pic.image


def override(project, terrain: str, part: Part):
    pic = state(project).pictures.get((terrain, part.key))
    return None if pic is None else picture(project, pic)


def tint_of(project, terrain: str, part: Part) -> int:
    return state(project).tints.get((terrain, part.key), WHITE)


def shown(project, terrain: str, part: Part):
    """A piece as the mod draws it: its picture, else the game's through
    the tint. None without the disc."""
    image = override(project, terrain, part)
    if image is not None:
        return image
    data = disc(project)
    return piece_image(data, terrain, part, tint_of(project, terrain, part)) if data.ok else None


def floor_image(project, terrain: str, retail: bool = False):
    """The floor as one picture, its rows in the board's order, at the
    largest scale a row has (the game's rows are enlarged to it)."""
    data = disc(project)
    rows = []
    for part in FLOOR:
        image = None if retail else override(project, terrain, part)
        if image is None:
            if not data.ok:
                return None
            image = piece_image(data, terrain, part, WHITE if retail else tint_of(project, terrain, part))
        rows.append(image)
    scale = max(max(1, round(image.width / FLOOR_W)) for image in rows)
    out = bytearray()
    for part, image in zip(FLOOR, rows):
        if image.size != (part.w * scale, part.h * scale):
            image = pngio.scale_to(image, part.w * scale, part.h * scale) if image.width == part.w else \
                pngio.resample(image, part.w * scale, part.h * scale)
        out += image.rgba
    return Image(FLOOR_W * scale, FLOOR_H * scale, bytes(out))


def fit(image: Image, width: int, height: int):
    """At most 4x the texture, in its shape (stretched when it is not);
    notes on what was done."""
    notes = []
    if image.width * height != image.height * width:
        notes.append(f"{image.width}x{image.height} is not {width}x{height}'s shape: stretched to fit")
    scale = max(1, min(MAX_SCALE, round(image.width / width), round(image.height / height)))
    if image.size != (width * scale, height * scale):
        if image.width > width * MAX_SCALE or image.height > height * MAX_SCALE:
            notes.append(f"made {width * scale}x{height * scale} (the editor keeps at most {MAX_SCALE}x)")
        image = pngio.resample(image, width * scale, height * scale)
    return image, notes


def _file(terrains, part: Part) -> str:
    where = "all" if len(terrains) > 1 else terrains[0]
    return f"{DIR}/{where}/{part.key}.png"


def set_piece(project, terrains, part: Part, image: Image) -> list:
    """The picture for a piece of the fields named (one file for them all);
    their tints go, the picture having its own colors."""
    image, notes = fit(image, part.w, part.h)
    st = state(project)
    pic = Picture(_file(list(terrains), part), image, pending=True)
    for terrain in terrains:
        st.pictures[(terrain, part.key)] = pic
        st.tints.pop((terrain, part.key), None)
    touched(project)
    return notes


def set_floor(project, terrains, image: Image) -> list:
    """The floor as one picture (floor_image's layout), split into its rows."""
    image, notes = fit(image, FLOOR_W, FLOOR_H)
    scale = image.width // FLOOR_W
    top = 0
    for part in FLOOR:
        set_piece(project, terrains, part, pngio.crop(image, 0, top * scale, part.w * scale, part.h * scale))
        top += part.h
    return notes


def set_tint(project, terrains, parts, tint: int):
    """The tint of the pieces of the fields named; white takes it away. It
    is stored as it reads back from the patches it makes (pick_tint), one
    value for them all."""
    st = state(project)
    data = disc(project)
    keys = [(t, p) for t in terrains for p in parts]
    if tint != WHITE and data.ok:
        pairs = [(palette_words(data, t, p), tinted(palette_words(data, t, p), tint)) for t, p in keys]
        tint = pick_tint(pairs) or tint
    for terrain, part in keys:
        if tint == WHITE or not data.ok:
            st.tints.pop((terrain, part.key), None)
        else:
            st.tints[(terrain, part.key)] = tint
    touched(project, pictures=False)


def revert(project, terrains, parts):
    st = state(project)
    keys = [(t, p.key) for t in terrains for p in parts]
    pictures = any(st.pictures.pop(k, None) is not None for k in keys)
    if any(st.tints.pop(k, None) is not None for k in keys) or pictures:
        touched(project, pictures)


def revert_all(project):
    st = state(project)
    pictures = bool(st.pictures)
    if st.pictures or st.tints:
        st.pictures.clear()
        st.tints.clear()
        touched(project, pictures)


def changed(project, terrain: str = None) -> bool:
    st = state(project)
    return any(terrain is None or t == terrain for t, _ in list(st.pictures) + list(st.tints))


# --- the pack ------------------------------------------------------------------------------

def _match(item):
    """(terrain, part) when a pack entry is one of the board's, else None."""
    if not isinstance(item, dict) or str(item.get("archive", "")).upper() != ARCHIVE:
        return None
    if item.get("setting") or not isinstance(item.get("file"), str):
        return None
    if item.get("row_offsets") is not None or item.get("bpp") != 4 or item.get("clut_entries") != 16 or \
            item.get("stride", item.get("words")) != 64 or item.get("crop_left", 0) != 0:
        return None
    offset = item.get("offset")
    if not isinstance(offset, int):
        return None
    for terrain in TERRAINS:
        if not phase_offset(terrain) <= offset < phase_offset(terrain) + PHASE_BYTES:
            continue
        for part in PARTS:
            if offset == image_offset(terrain, part) and item.get("words") == part.w // 4 and \
                    item.get("rows") == part.h and item.get("clut_offset") == palette_offset(terrain, part) and \
                    item.get("width", part.w) == part.w:
                return terrain, part
    return None


def adopt(project, art_state):
    """Take the board's entries out of the pack as read (art.ArtState.entries)
    into the board's pictures; the pack keeps the others. Entries naming one
    file share one Picture."""
    if not art_state.entries:
        return
    st = state(project)
    files = {}
    kept = []
    for item in art_state.entries:
        found = _match(item)
        if found is None:
            kept.append(item)
            continue
        terrain, part = found
        if (terrain, part.key) not in st.pictures:
            st.pictures[(terrain, part.key)] = files.setdefault(item["file"], Picture(item["file"]))
    art_state.entries[:] = kept


def entries(project) -> list:
    """The board's entries for the pack's manifest."""
    st = state(project)
    out = []
    for terrain in TERRAINS:
        for part in PARTS:
            pic = st.pictures.get((terrain, part.key))
            if pic is not None:
                out.append(entry(terrain, part, pic.file))
    return out


def pending_files(project) -> set:
    return {pic.file for pic in state(project).pictures.values() if pic.pending}


def write(project, folder):
    """Write the pending pictures under the pack's directory in `folder`
    (once for a picture the fields share)."""
    root = Path(folder) / _art().pack_dir(project)
    done = set()
    for pic in state(project).pictures.values():
        if pic.pending and pic.image is not None and id(pic) not in done:
            path = root / pic.file
            path.parent.mkdir(parents=True, exist_ok=True)
            pngio.write(path, pic.image)
            pic.pending = False
            done.add(id(pic))


def freeze(project):
    """Every picture read from the mod folder (history.py, before a save
    can overwrite the files)."""
    for pic in state(project).pictures.values():
        picture(project, pic)


# --- the tints: "data" patches of the palettes ----------------------------------------------

def _runs(old: bytes, new: bytes, base: int) -> list:
    from . import campaign_map
    return campaign_map.runs(old, new, base)


def patches(project) -> list:
    """The patch runs of the tinted palettes, one palette at a time."""
    st = state(project)
    data = disc(project)
    if not data.ok:
        return []
    out = []
    for terrain in TERRAINS:
        for part in PARTS:
            tint = st.tints.get((terrain, part.key))
            if tint is None:
                continue
            retail = palette_words(data, terrain, part)
            old = b"".join(w.to_bytes(2, "little") for w in retail)
            new = b"".join(w.to_bytes(2, "little") for w in tinted(retail, tint))
            out += _runs(old, new, palette_offset(terrain, part))
    return out


def build_into(project, manifest: dict):
    """Add the tints' patches to the manifest's "data" (after what the mod
    keeps as written, and the map's)."""
    runs = patches(project)
    if not runs:
        return
    data = manifest.get("data")
    data = list(data) if isinstance(data, list) else []
    data.append({"file": ARCHIVE_FILE, "patch": runs})
    manifest["data"] = data


def _palettes():
    """{palette's first byte: (terrain, part)} of every piece."""
    return {palette_offset(t, p): (t, p) for t in TERRAINS for p in PARTS}


def read_patches(project, messages: list = None):
    """Take the mod's patches of the board's palettes out of its "data"
    into tints (manifest.apply, after the map's). A palette whose patched
    colors are no tint of the disc's, and every run that also writes
    outside the palettes, stay as they were written."""
    from .campaign_map import _hex_bytes, _is_wa, _number
    messages = [] if messages is None else messages
    state(project).tints.clear()
    data = disc(project)
    listed = project.other.get("data")
    if not data.ok or not isinstance(listed, list):
        return messages
    palettes = _palettes()

    def home(at):
        for offset in palettes:
            if offset <= at < offset + 32:
                return offset
        return None
    # A run is the board's when every byte it writes lies in a piece's palette.
    patched, runs_of = {}, {}
    for e_index, item in enumerate(listed):
        if not _is_wa(item) or not isinstance(item.get("patch"), list):
            continue
        for r_index, run in enumerate(item["patch"]):
            at = _number(run.get("at")) if isinstance(run, dict) else None
            blob = _hex_bytes(run.get("bytes")) if isinstance(run, dict) else None
            if at is None or not blob or any(home(at + i) is None for i in range(len(blob))):
                continue
            touched_here = set()
            for i, byte in enumerate(blob):
                offset = home(at + i)
                if offset not in patched:
                    terrain, part = palettes[offset]
                    patched[offset] = bytearray(b"".join(w.to_bytes(2, "little")
                                                         for w in palette_words(data, terrain, part)))
                patched[offset][at + i - offset] = byte
                touched_here.add(offset)
            runs_of[(e_index, r_index)] = touched_here
    tints, bad = {}, set()
    for offset, blob in patched.items():
        terrain, part = palettes[offset]
        tint = recover_tint(palette_words(data, terrain, part), [blob[2 * i] | blob[2 * i + 1] << 8 for i in range(16)])
        if tint is None:
            messages.append(f"a patch of the duel board's palette at 0x{offset:X} ({TERRAIN_LABELS[terrain]}, "
                            f"{part.label.lower()}) is no tint: kept as written")
            bad.add(offset)
        else:
            tints[offset] = tint
    # A run that also writes a palette that is no tint stays, and so do the
    # palettes it writes.
    grew = True
    while grew:
        grew = False
        for offsets in runs_of.values():
            if offsets & bad and not offsets <= bad:
                bad |= offsets
                grew = True
    st = state(project)
    for offset, tint in tints.items():
        if offset not in bad and tint != WHITE:
            terrain, part = palettes[offset]
            st.tints[(terrain, part.key)] = tint
    dropped = {key for key, offsets in runs_of.items() if not offsets & bad}
    if not dropped:
        return messages
    out = []
    for e_index, item in enumerate(listed):
        if not _is_wa(item) or not isinstance(item.get("patch"), list):
            out.append(item)
            continue
        rest = [run for r_index, run in enumerate(item["patch"]) if (e_index, r_index) not in dropped]
        if rest or set(item) - {"file", "patch"}:
            out.append(dict(item, patch=rest))
    if out:
        project.other["data"] = out
    else:
        project.other.pop("data", None)
    return messages


# --- checks --------------------------------------------------------------------------------

def check(project, out: list):
    """What the game would make of the board's pictures and tints."""
    from .validate import Issue
    st = state(project)
    folder = _folder(project)
    seen = set()
    for (terrain, key), pic in sorted(st.pictures.items()):
        part = BY_KEY[key]
        where = f"{pic.file}"
        if (terrain, key) in st.tints:
            out.append(Issue("warning", "UI", f"duel board {TERRAIN_LABELS[terrain]}",
                             f"{part.label}: tinted and replaced; the picture is drawn, the tint shows nowhere"))
        if id(pic) in seen:
            continue
        seen.add(id(pic))
        image = pic.image
        if image is None and not pic.pending and folder is not None:
            try:
                image = pngio.read(folder / pic.file)
            except OSError:
                continue            # art.check: the file is not there
            except pngio.PngError as problem:
                out.append(Issue("error", "UI", where, f"is not a PNG the game can read ({problem}): "
                                                       "the game's texture stays"))
                continue
        if image is not None and image.width * part.h != image.height * part.w:
            out.append(Issue("warning", "UI", where, f"{image.width}x{image.height} is not {part.w}x{part.h}'s "
                                                     "shape: the game stretches it"))
        if image is not None and any(a < 128 for a in image.rgba[3::4]):
            out.append(Issue("warning", "UI", where, "has see-through pixels: the board shows black there"))


def digest(project) -> str:
    """A short hash of the board's edits (tests and the page's redraws)."""
    st = state(project)
    h = hashlib.sha1()
    for key in sorted(st.pictures):
        image = picture(project, st.pictures[key])
        h.update(repr(key).encode() + (image.rgba if image else b""))
    # The tints by the palettes they make: two readings of one patch are one tint.
    h.update(repr(patches(project) if disc(project).ok else sorted(st.tints.items())).encode())
    return h.hexdigest()[:12]
