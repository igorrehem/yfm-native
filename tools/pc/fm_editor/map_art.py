"""The campaign map's pictures in a mod: its sprites (the name panel, the
Millennium Puzzle marker, the exits' arrows) and its terrain's textures,
as texture pack entries (notes/modding.md, "Texture packs") in the mod's
pack, next to the Art tab's (art.py keeps the pack's manifest; this module
owns the map's entries in it).

* The sprites are one 256x256 four-bit strip in each overworld package
  (sector +141, uploaded to VRAM 448,256), drawn through four 16-color
  palettes of the package's sector +157: 0 the name panel, 2 the marker, 3
  the arrows (campaign_map.sprite_parts); a texture dump of the map shows
  the strip read through palette 1 as well. The mod replaces the
  strip as the game reads it through one palette: an entry per palette
  and package, both packages' entries naming one PNG (the strips are the
  same). A picture for one sprite is pasted into every cell of its
  animation (the marker's 16 frames, an arrow's 10), so the sprite keeps
  its motion but not its frames' differences; an arrow and its mirror
  (right and left, and the diagonals) share their cells.
* The terrain's textures are the HMD's image uploads (map_view.MapModel),
  4 or 8 bits through the palettes their polygons name. An entry per
  texture and palette it is drawn with, per package (the two models
  differ). Most texels are tiles the terrain repeats (86 in 100 of the
  upward faces' texels are drawn more than once, one up to 51 times), so
  the map has no single picture to paint: its textures are replaced one
  by one, as files named after the texture.

A pack image may be bigger than the texture: the console's resolution
averages it down, Internal 2x and 4x draw it at its own. The editor keeps
the map's pictures at most 4x."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from . import campaign_map as cm
from . import map_view, pngio
from .pngio import Image

SECTOR = 2048
ARCHIVE = "WA_MRG.MRG"
STRIP_SECTOR = 141
PALETTE_SECTOR = 157
STRIP_SIZE = 256
STRIP_WORDS = 64
STRIP_PALETTES = (0, 1, 2, 3)
PALETTE_LABELS = {0: "name panel", 1: "a second reading the map draws", 2: "marker", 3: "arrows"}
MAX_SCALE = 4
DIR = "map"

# The sprites a picture can be imported for: (label, animation, variant).
SPRITES = [("Millennium Puzzle marker", 1, 0), ("Name panel", 0, 0)] + \
    [(f"Arrow {name}" + {"right": " (and left)", "left": " (and right)", "down-left": " (and down-right)",
                         "down-right": " (and down-left)", "up-left": " (and up-right)",
                         "up-right": " (and up-left)"}.get(name, ""), 2, i) for i, name in enumerate(cm.ARROWS)]


@dataclass
class Picture:
    file: str               # relative to the pack's directory
    image: Image = None     # None until read
    pending: bool = False   # to be written on save


@dataclass(frozen=True)
class Texture:
    """One texture of a package's terrain as a polygon draws it."""
    package: str
    block: int              # the image upload's index in the model
    x: int                  # VRAM position and size in words
    y: int
    words: int
    rows: int
    bpp: int
    offset: int             # the image's first byte in WA_MRG.MRG
    clut: int               # the palette word polygons name
    clut_offset: int        # the palette's first byte in WA_MRG.MRG
    entries: int

    @property
    def width(self) -> int:
        return self.words * (16 // self.bpp)

    @property
    def name(self) -> str:
        return f"{self.package}/texture{self.block:02d}-{self.clut:04x}.png"


class MapArt:
    def __init__(self):
        self.strips = {}        # palette -> Picture
        self.textures = {}      # Texture -> Picture
        self.version = 0        # changes with every edit (the tab's pictures follow it)


def state(project) -> MapArt:
    st = getattr(project, "map_art", None)
    if st is None:
        st = project.map_art = MapArt()
    return st


def _art():
    from . import art
    return art


def _data(project):
    """The disc's map (campaign_map.MapData), or None."""
    return getattr(project.retail, "campaign_map", None)


def touched(project):
    st = state(project)
    st.version += 1
    _art().state(project).changed = True


# --- where the pictures are on the disc -------------------------------------------------

def strip_offset(sector: int) -> int:
    return (sector + STRIP_SECTOR) * SECTOR


def palette_offset(sector: int, palette: int) -> int:
    return (sector + PALETTE_SECTOR) * SECTOR + palette * 32


def strip_entry(sector: int, palette: int, file: str) -> dict:
    return {"file": file, "alias": f"campaign map sprites, palette {palette} ({PALETTE_LABELS[palette]})",
            "archive": ARCHIVE, "offset": strip_offset(sector), "words": STRIP_WORDS, "rows": STRIP_SIZE, "bpp": 4,
            "clut_offset": palette_offset(sector, palette), "clut_entries": 16, "width": STRIP_SIZE,
            "height": STRIP_SIZE, "crop_left": 0, "stride": STRIP_WORDS, "row_offsets": None}


def texture_entry(texture: Texture, file: str) -> dict:
    return {"file": file, "alias": f"campaign map terrain texture {texture.block} "
                                   f"({cm.PACKAGE_LABELS[texture.package]}), palette {texture.clut:04x}",
            "archive": ARCHIVE, "offset": texture.offset, "words": texture.words, "rows": texture.rows,
            "bpp": texture.bpp, "clut_offset": texture.clut_offset, "clut_entries": texture.entries,
            "width": texture.width, "height": texture.rows, "crop_left": 0, "stride": texture.words,
            "row_offsets": None}


def textures(wa: bytes, package: str) -> list:
    """The package's terrain textures as its polygons draw them: each image
    upload with each palette a polygon inside it names (the last upload to
    a place is the one drawn, as in VRAM)."""
    sector = dict(cm.PACKAGES)[package]
    model = map_view.model(wa, sector)
    base = (sector + map_view.MODEL_SECTOR) * SECTOR
    uploads = [parts for parts in model.images]
    found = {}
    for uvs, clut, tpage, _, _ in model.polygons:
        depth = (tpage >> 7) & 3
        if depth > 1:
            continue
        per = 4 if depth == 0 else 2
        px, py = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
        us, vs = [u & 255 for u in uvs], [u >> 8 for u in uvs]
        left, right, top, bottom = px + min(us) // per, px + max(us) // per, py + min(vs), py + max(vs)
        block = None
        for index in range(len(uploads) - 1, -1, -1):
            x, y, w, h, _ = uploads[index][0]
            if x <= left and right < x + w and y <= top and bottom < y + h:
                block = index
                break
        if block is None:
            continue
        entries = 16 if depth == 0 else 256
        cx, cy = (clut & 63) * 16, clut >> 6
        clut_offset = None
        for parts in reversed(uploads):
            if len(parts) < 2:
                continue
            x, y, w, h, offset = parts[1]
            if x <= cx and cx + entries <= x + w and y <= cy < y + h:
                clut_offset = base + offset + ((cy - y) * w + (cx - x)) * 2
                break
        if clut_offset is None:
            continue
        x, y, w, h, offset = uploads[block][0]
        key = (block, clut)
        if key not in found:
            found[key] = Texture(package, block, x, y, w, h, 16 // per, base + offset, clut, clut_offset, entries)
    return [found[k] for k in sorted(found)]


def texture_image(wa: bytes, texture: Texture) -> Image:
    """A texture as the disc has it, through its palette."""
    blob = wa[texture.offset:texture.offset + texture.words * 2 * texture.rows]
    palette = [cm.color(wa[texture.clut_offset + 2 * i] | (wa[texture.clut_offset + 2 * i + 1] << 8))
               for i in range(texture.entries)]
    # Every entry but the first is drawn opaque (the game sets its STP bit).
    palette = [palette[0]] + [c if c[3] else (0, 0, 0, 255) for c in palette[1:]]
    width = texture.width
    out = bytearray(width * texture.rows * 4)
    for y in range(texture.rows):
        for x in range(width):
            if texture.bpp == 4:
                byte = blob[y * texture.words * 2 + x // 2]
                index = byte >> 4 if x & 1 else byte & 15
            else:
                index = blob[y * texture.words * 2 + x]
            at = (y * width + x) * 4
            out[at:at + 4] = bytes(palette[index])
    return Image(width, texture.rows, bytes(out))


def strip_image(data: cm.MapData, palette: int) -> Image:
    """The disc's sprite strip through one palette, 256x256."""
    colors = cm.palette_colors(data.palettes, palette)
    out = bytearray(STRIP_SIZE * STRIP_SIZE * 4)
    for v in range(STRIP_SIZE):
        for u in range(STRIP_SIZE):
            at = (v * STRIP_SIZE + u) * 4
            out[at:at + 4] = bytes(colors[cm.strip_index(data.strip, u, v)])
    return Image(STRIP_SIZE, STRIP_SIZE, bytes(out))


# --- the mod's pictures -----------------------------------------------------------------

def _folder(project):
    art = _art()
    st = art.state(project)
    folder = st.folder or project.source_dir
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


def strip_override(project, palette: int):
    pic = state(project).strips.get(palette)
    return None if pic is None else picture(project, pic)


def texture_overrides(project, package: str) -> dict:
    """{(block, clut): image} of the package's replaced textures."""
    out = {}
    for texture, pic in state(project).textures.items():
        if texture.package == package:
            image = picture(project, pic)
            if image is not None:
                out[(texture.block, texture.clut)] = image
    return out


def _normalize(image: Image, width: int, height: int):
    """At most 4x the texture, in its shape (stretched when it is not);
    notes on what was done."""
    notes = []
    if image.width * height != image.height * width:
        notes.append(f"{image.width}x{image.height} is not the texture's shape ({width}x{height}): stretched")
    scale = max(1, min(MAX_SCALE, round(image.width / width), round(image.height / height)))
    if image.size != (width * scale, height * scale):
        if image.width > width * MAX_SCALE or image.height > height * MAX_SCALE:
            notes.append(f"made {width * scale}x{height * scale} (the editor keeps at most {MAX_SCALE}x)")
        image = pngio.resample(image, width * scale, height * scale)
    return image, notes


def set_strip(project, palette: int, image: Image) -> list:
    image, notes = _normalize(image, STRIP_SIZE, STRIP_SIZE)
    state(project).strips[palette] = Picture(f"{DIR}/sprites-p{palette}.png", image, pending=True)
    touched(project)
    return notes


def set_texture(project, texture: Texture, image: Image) -> list:
    image, notes = _normalize(image, texture.width, texture.rows)
    state(project).textures[texture] = Picture(f"{DIR}/{texture.name}", image, pending=True)
    touched(project)
    return notes


def sprite_cells(data: cm.MapData, animation: int, variant: int) -> list:
    """Every part of every frame of a sprite's animation, with the frame's
    offset from the object's place, until the stream loops or stops, or
    holds a frame for good (duration 0: DisplayObject_UpdateCommandStream
    counts a nonzero duration down, so the next entry is never read)."""
    res = data.resource
    try:
        level1 = cm._u16(res, 0)
        level2 = cm._u16(res, level1 + animation * 2)
        at = cm._u16(res, level2 + variant * 2)
    except IndexError:
        return []
    parts, mirror, seen = [], False, set()
    for _ in range(64):
        if at >= len(res):
            break
        op = res[at]
        if op < 0xF0:
            parts.extend(cm.sprite_parts(res, cm._u16(res, at + 1), mirror))
            if op == 0:
                break       # a frame held for good: the stream is never read on (the name panel)
            at += 3
            continue
        if op in (0xFB, 0xFC) and at not in seen:
            seen.add(at)
            mirror ^= op == 0xFB
            at = cm._u16(res, at + 1)
            continue
        break
    return parts


def set_sprite(project, animation: int, variant: int, image: Image) -> list:
    """Paste a picture of one sprite (its first frame's box,
    campaign_map.sprite_image) into every cell of its animation, in the
    strip of each palette it uses."""
    data = _data(project)
    first = cm.sprite_image(data, animation, variant)
    if first is None:
        raise ValueError("the map's resource bank has no such sprite")
    box, left, top = first
    notes = []
    scale = max(1, min(MAX_SCALE, round(image.width / box.width), round(image.height / box.height)))
    if image.size != (box.width * scale, box.height * scale):
        notes.append(f"made {box.width * scale}x{box.height * scale} (the sprite is {box.width}x{box.height})")
        image = pngio.resample(image, box.width * scale, box.height * scale)
    cells = sprite_cells(data, animation, variant)
    by_palette = {}
    for part in cells:
        by_palette.setdefault(part.palette, []).append(part)
    for palette, parts in by_palette.items():
        base = strip_override(project, palette) or strip_image(data, palette)
        current = max(1, base.width // STRIP_SIZE)
        strip_scale = max(scale, current)
        if base.size != (STRIP_SIZE * strip_scale,) * 2:
            if base.size == (STRIP_SIZE * current,) * 2 and strip_scale % current == 0:
                base = pngio.scale_nearest(base, strip_scale // current)
            else:
                base = pngio.resample(base, STRIP_SIZE * strip_scale, STRIP_SIZE * strip_scale)
        pixels = bytearray(base.rgba)
        s = strip_scale
        source = image if scale == s else pngio.resample(image, box.width * s, box.height * s)
        for part in parts:
            for j in range(part.height * s):
                for i in range(part.width * s):
                    # The cell's texel (u, v) shows the sprite at (dx, dy) + (i, j),
                    # the other way round when the part is mirrored.
                    sx = (part.dx - left) * s + i
                    sy = (part.dy - top) * s + j
                    tu = part.u * s + (part.width * s - 1 - i if part.mirror else i)
                    tv = part.v * s + j
                    if 0 <= sx < source.width and 0 <= sy < source.height:
                        color = source.rgba[(sy * source.width + sx) * 4:(sy * source.width + sx) * 4 + 4]
                    else:
                        color = b"\x00\x00\x00\x00"
                    at = (tv * base.width + tu) * 4
                    pixels[at:at + 4] = color
        state(project).strips[palette] = Picture(f"{DIR}/sprites-p{palette}.png",
                                                 Image(base.width, base.height, bytes(pixels)), pending=True)
    touched(project)
    return notes


def revert_sprites(project):
    if state(project).strips:
        state(project).strips.clear()
        touched(project)


def revert_textures(project, package: str = None):
    st = state(project)
    keys = [t for t in st.textures if package is None or t.package == package]
    for key in keys:
        del st.textures[key]
    if keys:
        touched(project)


# --- the pack -----------------------------------------------------------------------------

def _match(entry, wa_uses):
    """(kind, key) when a pack entry is one of the map's, else None."""
    if not isinstance(entry, dict) or str(entry.get("archive", "")).upper() != ARCHIVE:
        return None
    if entry.get("setting") or not isinstance(entry.get("file"), str):
        return None
    offset, clut = entry.get("offset"), entry.get("clut_offset")
    for _, sector in cm.PACKAGES:
        if offset == strip_offset(sector) and entry.get("words") == STRIP_WORDS and entry.get("rows") == STRIP_SIZE \
                and entry.get("bpp") == 4 and entry.get("clut_entries") == 16:
            for palette in STRIP_PALETTES:
                if clut == palette_offset(sector, palette):
                    return "strip", palette
    for texture in wa_uses:
        if offset == texture.offset and clut == texture.clut_offset and entry.get("words") == texture.words \
                and entry.get("rows") == texture.rows and entry.get("bpp") == texture.bpp:
            return "texture", texture
    return None


def package_textures(data: cm.MapData, package: str) -> list:
    """textures(), once per disc; none when the package's model cannot be
    read."""
    cache = data.__dict__.setdefault("_textures", {})
    if package not in cache:
        try:
            cache[package] = textures(data.wa, package)
        except (map_view.ModelError, struct.error, IndexError):
            cache[package] = []
    return cache[package]


def uses(project) -> list:
    """Every terrain texture of both packages."""
    data = _data(project)
    if data is None or not data.wa:
        return []
    return [t for name, _ in cm.PACKAGES for t in package_textures(data, name)]


def adopt(project, art_state):
    """Take the map's entries out of the pack as read (art.ArtState.entries)
    into the map's pictures; the Art tab's pack keeps the others."""
    if not art_state.entries or _data(project) is None:
        return
    st = state(project)
    wa_uses = uses(project)
    kept = []
    for entry in art_state.entries:
        found = _match(entry, wa_uses)
        if found is None:
            kept.append(entry)
            continue
        kind, key = found
        if kind == "strip":
            st.strips.setdefault(key, Picture(entry["file"]))
        else:
            st.textures.setdefault(key, Picture(entry["file"]))
    art_state.entries[:] = kept


def entries(project) -> list:
    """The map's entries for the pack's manifest."""
    st = state(project)
    out = []
    for palette in sorted(st.strips):
        for _, sector in cm.PACKAGES:
            out.append(strip_entry(sector, palette, st.strips[palette].file))
    for texture in sorted(st.textures, key=lambda t: (t.package, t.block, t.clut)):
        out.append(texture_entry(texture, st.textures[texture].file))
    return out


def pending_files(project) -> set:
    st = state(project)
    return {pic.file for pic in list(st.strips.values()) + list(st.textures.values()) if pic.pending}


def write(project, folder):
    """Write the pending pictures under the pack's directory in `folder`."""
    art = _art()
    root = Path(folder) / art.pack_dir(project)
    st = state(project)
    for pic in list(st.strips.values()) + list(st.textures.values()):
        if pic.pending and pic.image is not None:
            path = root / pic.file
            path.parent.mkdir(parents=True, exist_ok=True)
            pngio.write(path, pic.image)
            pic.pending = False


# --- export -------------------------------------------------------------------------------

def export_sprites(project, folder) -> list:
    """The strip through each palette as the mod has it (the disc's where
    it has none), as sprites-p0.png ... sprites-p3.png."""
    data = _data(project)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for palette in STRIP_PALETTES:
        image = strip_override(project, palette) or strip_image(data, palette)
        path = folder / f"sprites-p{palette}.png"
        pngio.write(path, image)
        written.append(path)
    return written


def export_textures(project, package: str, folder) -> list:
    """The package's textures as the mod has them (the disc's where it has
    none), texture<upload>-<palette>.png."""
    data = _data(project)
    wa = data.wa
    folder = Path(folder)
    written = []
    overrides = {t: p for t, p in state(project).textures.items() if t.package == package}
    for texture in package_textures(data, package):
        image = picture(project, overrides[texture]) if texture in overrides else None
        path = folder / Path(texture.name).name
        path.parent.mkdir(parents=True, exist_ok=True)
        pngio.write(path, image or texture_image(wa, texture))
        written.append(path)
    return written


def import_sprites(project, folder) -> list:
    """sprites-p0.png ... sprites-p3.png from a folder, those that are there."""
    notes = []
    for palette in STRIP_PALETTES:
        path = Path(folder) / f"sprites-p{palette}.png"
        if path.is_file():
            notes += [f"{path.name}: {n}" for n in set_strip(project, palette, pngio.read(path))]
            notes.append(f"{path.name}: the sprites through palette {palette}")
    return notes


def import_textures(project, package: str, folder) -> list:
    """The textures of a package from a folder, named as export_textures
    names them; those that are not there stay as they are."""
    notes = []
    for texture in package_textures(_data(project), package):
        path = Path(folder) / Path(texture.name).name
        if path.is_file():
            notes += [f"{path.name}: {n}" for n in set_texture(project, texture, pngio.read(path))]
            notes.append(f"{path.name}: texture {texture.block}")
    return notes
