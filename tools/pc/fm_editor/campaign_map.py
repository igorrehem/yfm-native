"""The campaign map: where each of its sixteen places is, which way leads
where, and where the Millennium Puzzle marker stands in the town.

The map is the overworld module's table (src/overlays/overworld/
location_table.c, notes/overlays/campaign-map-records.md): sixteen 66-byte
records, 0-9 the world map's sites and 10-15 the town's places, named by the
executable's strings 0x8350 + index. Each record holds

  +0x00 u16  confirm gate: nonzero, Confirm works only while exit 1's
             condition holds
  +0x02 s16  camera pitch    (ViewState field_04)
  +0x04 s16  camera heading  (ViewState angle)
  +0x06 s16  camera distance (ViewState field_00)
  +0x08 s16  camera target x (the reference point; y is 0)
  +0x0A s16  camera target z
  +0x0C s16  marker x, +0x0E s16 marker y: the Puzzle's place on the screen
             (drawn in the town only)
  +0x10 u8   Confirm's destination: 0 enters the place's own scene
  +0x11 u8   kept as the disc has it
  +0x12      four exits of 12 bytes: u16 condition (0 always, else a story
             flag, 0x8000 meaning "while it is clear"), s16 x, s16 y (the
             arrow's place on the screen), u16 the direction held (0x1000 up,
             0x2000 right, 0x4000 down, 0x8000 left), u8 the arrow's picture,
             u8 destination (16: no exit), u8 the move's length in frames,
             u8 kept

The module comes twice on the disc, in the overworld package before
Heishin's coup (WA_MRG.MRG sector 8153) and in the one after it (8311, story
flag 0x47), each with the table 0x11A8 bytes into it. A mod changes both
with "data" patches (notes/modding.md); the PC port reads the table where
the package puts it (location_table.c), as the console does. The module's
second, alternate copy of the table (+0x1E54) has no reader found on the
map's paths and is left alone.

The same package holds the map's pictures: a display resource bank (the
sprites' layout, sector +140), a 256x256 four-bit strip of sprites (+141,
16 sectors, at VRAM 448,256) and its palettes (+157, 256x4 at 256,240).
"""
from __future__ import annotations

import copy
import struct
from dataclasses import dataclass, field

from . import pngio
from .pngio import Image

SECTOR = 2048
ARCHIVE_FILE = "\\DATA\\WA_MRG.MRG;1"
PACKAGES = (("before", 8153), ("after", 8311))
PACKAGE_LABELS = {"before": "before the coup", "after": "after the coup"}
PACKAGE_SECTORS = 158
MODULE_SECTORS = 6
MODULE_IDENTIFIER = 0x14
TABLE_OFFSET = 0x11A8
COUNT = 16
RECORD = 66
EXITS = 4
NO_EXIT = 16
TOWN_FIRST = 10
TOURNAMENT_FLAG = 0x47          # set: the town's Cancel leads back to the world map (place 0)
FLAG_CLEAR = 0x8000
FLAG_ID = 0x7FF
NAME_STRING = 0x350              # global string 0x8350 + index (CampaignMap_CreateLocationLabel)
SCREEN = (320, 240)
PANEL_AT = (96, 24)              # CampaignMap_SetLocation: the name panel's sprite

DIRECTIONS = (("up", 0x1000), ("right", 0x2000), ("down", 0x4000), ("left", 0x8000))
DIRECTION_BITS = 0xF000
# The arrow pictures an exit may use (the resource bank's animation 2).
ARROWS = ("right", "down-left", "down", "down-right", "left", "up-left", "up", "up-right")

_HEAD = struct.Struct("<HhhhhhhhBB")
_EXIT = struct.Struct("<HhhHBBBB")
assert _HEAD.size + EXITS * _EXIT.size == RECORD


@dataclass
class Exit:
    condition: int = 0          # story_flag
    x: int = 0
    y: int = 0
    buttons: int = 0            # input_mask
    arrow: int = 0              # field_08
    destination: int = NO_EXIT
    steps: int = 0              # move_steps
    pad: int = 0

    @property
    def used(self) -> bool:
        return self.destination != NO_EXIT


@dataclass
class Location:
    gate: int = 0
    pitch: int = 0
    heading: int = 0
    distance: int = 0
    target_x: int = 0
    target_z: int = 0
    marker_x: int = 0
    marker_y: int = 0
    confirm: int = 0
    pad: int = 0
    exits: list = field(default_factory=lambda: [Exit() for _ in range(EXITS)])

    def copy(self) -> "Location":
        return copy.deepcopy(self)


def unpack(blob: bytes) -> Location:
    head = _HEAD.unpack_from(blob, 0)
    exits = [Exit(*_EXIT.unpack_from(blob, _HEAD.size + i * _EXIT.size)) for i in range(EXITS)]
    return Location(*head, exits=exits)


def pack(location: Location) -> bytes:
    out = _HEAD.pack(location.gate & 0xFFFF, location.pitch, location.heading, location.distance,
                     location.target_x, location.target_z, location.marker_x, location.marker_y,
                     location.confirm & 0xFF, location.pad & 0xFF)
    for e in location.exits:
        out += _EXIT.pack(e.condition & 0xFFFF, e.x, e.y, e.buttons & 0xFFFF, e.arrow & 0xFF,
                          e.destination & 0xFF, e.steps & 0xFF, e.pad & 0xFF)
    return out


def pack_table(locations) -> bytes:
    return b"".join(pack(location) for location in locations)


def unpack_table(blob: bytes) -> list:
    return [unpack(blob[i * RECORD:(i + 1) * RECORD]) for i in range(COUNT)]


def package_offset(sector: int) -> int:
    return sector * SECTOR


def table_offset(sector: int) -> int:
    """The table's first byte in WA_MRG.MRG."""
    return sector * SECTOR + TABLE_OFFSET


# --- conditions ----------------------------------------------------------------------

def condition_parts(value: int) -> tuple:
    """("always", 0) for 0, else ("set" or "clear", flag number)."""
    if value == 0:
        return "always", 0
    return ("clear" if value & FLAG_CLEAR else "set"), value & 0x7FFF


def condition_value(kind: str, flag: int) -> int:
    if kind == "always":
        return 0
    return (flag & 0x7FFF) | (FLAG_CLEAR if kind == "clear" else 0)


def describe_condition(value: int) -> str:
    kind, flag = condition_parts(value)
    if kind == "always":
        return "always"
    return f"while flag {flag} (0x{flag:X}) is {'clear' if kind == 'clear' else 'set'}"


def direction_names(buttons: int) -> list:
    return [name for name, bit in DIRECTIONS if buttons & bit]


def describe_buttons(buttons: int) -> str:
    names = direction_names(buttons)
    other = buttons & ~DIRECTION_BITS & 0xFFFF
    if other:
        names.append(f"0x{other:04X}")
    return "+".join(names) if names else "nothing"


# --- the retail map ------------------------------------------------------------------

@dataclass
class MapData:
    """The map as the player's disc has it."""
    tables: dict            # package name -> the 16 Locations
    raw: dict               # package name -> the table's 1056 bytes
    names: list             # 16 place names
    resource: bytes = b""   # the display resource bank (one sector)
    strip: bytes = b""      # the sprite strip, 256x256 at four bits
    palettes: bytes = b""   # 256x4 colors
    notes: list = field(default_factory=list)
    wa: bytes = field(default=b"", repr=False, compare=False)   # the archive, for the map's model and pictures

    @property
    def locations(self) -> list:
        return self.tables["before"]


def _string_at(image, glyphs: dict, at: int, depth: int = 0) -> str:
    """The text of a global string as the label shows it: 0xF8 codes (the
    label's placement) skipped, a jump (0xFD) followed, and a flag test
    (0xF9 "if") read both ways, "before / after" when they differ."""
    from .gamedata import NAME_BANK
    text = ""
    for _ in range(64):
        code = image.bytes(at, 1)[0]
        if code < 0xF0:
            text += glyphs.get(code, "?")
            at += 1
        elif code <= 0xF5:
            at += 2
        elif code == 0xF8:
            at += 3
        elif code == 0xF9:
            command = image.u16(at + 1)
            if command & 0x4000 or depth > 2:
                at += 3
                continue
            other = _string_at(image, glyphs, NAME_BANK + image.u16(at + 3), depth + 1)
            rest = _string_at(image, glyphs, at + 5, depth + 1)
            return text + (rest if other == rest or not other else f"{rest} / {other}")
        elif code == 0xFD and depth <= 2:
            at = NAME_BANK + image.u16(at + 1)
            depth += 1
        elif code == 0xFE:
            text += " "
            at += 1
        else:
            break
    return text


def _plain_string(image, glyphs: dict, index: int) -> str:
    from .gamedata import NAME_BANK, NAME_TABLE
    return _string_at(image, glyphs, NAME_BANK + image.u16(NAME_TABLE + index * 2))


def place_names(slus: bytes) -> list:
    """The label each place shows (global strings 0x8350 + index)."""
    from .gamedata import _image, _tl
    names = []
    try:
        image = _image(slus)
        glyphs = _tl.glyph_characters(image)
        for index in range(COUNT):
            names.append(_plain_string(image, glyphs, NAME_STRING + index).strip())
    except Exception:       # a short or odd executable: numbers will do
        names = []
    return [name if name else f"Location {i}" for i, name in enumerate(names + [""] * (COUNT - len(names)))]


def read(slus: bytes, wa: bytes):
    """The map from the game's files, or None when WA_MRG.MRG does not hold
    the overworld packages (a short or foreign file)."""
    tables, raw, notes = {}, {}, []
    for name, sector in PACKAGES:
        start = package_offset(sector)
        if len(wa) < start + PACKAGE_SECTORS * SECTOR:
            return None
        if struct.unpack_from("<I", wa, start)[0] != MODULE_IDENTIFIER:
            return None
        raw[name] = bytes(wa[start + TABLE_OFFSET:start + TABLE_OFFSET + COUNT * RECORD])
        tables[name] = unpack_table(raw[name])
    if raw["before"] != raw["after"]:
        notes.append("the two overworld packages' map tables differ on this disc; the editor shows the one before "
                     "the coup and writes both alike")
    base = package_offset(PACKAGES[0][1])
    return MapData(tables=tables, raw=raw, names=place_names(slus),
                   resource=bytes(wa[base + 140 * SECTOR:base + 141 * SECTOR]),
                   strip=bytes(wa[base + 141 * SECTOR:base + 157 * SECTOR]),
                   palettes=bytes(wa[base + 157 * SECTOR:base + 158 * SECTOR]), notes=notes, wa=wa)


# --- the mod's map -------------------------------------------------------------------

class MapState:
    def __init__(self, retail: MapData):
        self.retail = retail
        self.locations = [loc.copy() for loc in retail.locations] if retail else []
        self.notes = []             # what reading the mod found


def state(project) -> MapState:
    st = getattr(project, "map_state", None)
    if st is None:
        st = project.map_state = MapState(getattr(project.retail, "campaign_map", None))
        adopt(project, st, st.notes)
    return st


def available(project) -> bool:
    return state(project).retail is not None


def name(project, index: int) -> str:
    retail = state(project).retail
    if retail and 0 <= index < COUNT:
        return retail.names[index]
    return f"Location {index}"


def label(project, index: int) -> str:
    return f"{index}: {name(project, index)}"


def changed(project, index: int) -> bool:
    st = state(project)
    return st.retail is not None and st.locations[index] != st.retail.locations[index]


def any_changed(project) -> bool:
    return any(changed(project, i) for i in range(COUNT)) if available(project) else False


def reset(project, index: int):
    st = state(project)
    st.locations[index] = st.retail.locations[index].copy()


def reset_all(project):
    st = state(project)
    st.locations = [loc.copy() for loc in st.retail.locations]


# --- data patches ----------------------------------------------------------------------

def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError:
            return None
    return None


def _hex_bytes(text):
    if not isinstance(text, str):
        return None
    digits = "".join(text.split())
    if len(digits) % 2:
        return None
    try:
        return bytes.fromhex(digits)
    except ValueError:
        return None


def _is_wa(entry) -> bool:
    file = entry.get("file") if isinstance(entry, dict) else None
    if not isinstance(file, str):
        return False
    return file.replace("/", "\\").upper().lstrip("\\") in ("DATA\\WA_MRG.MRG;1", "DATA\\WA_MRG.MRG")


def _ranges():
    return [(name, table_offset(sector), table_offset(sector) + COUNT * RECORD) for name, sector in PACKAGES]


def adopt(project, st: MapState, messages: list):
    """Take the mod's patches of the two tables out of its "data" (kept as
    written otherwise) into the map, so that saving writes them again from
    the map. A run that straddles a table's edge, and any "replace" of
    WA_MRG.MRG, stay as they were written."""
    if st.retail is None:
        return
    data = project.other.get("data")
    if not isinstance(data, list):
        return
    tables = {name: bytearray(st.retail.raw[name]) for name, _ in PACKAGES}
    touched = set()
    kept = []
    for entry in data:
        if not _is_wa(entry) or not isinstance(entry.get("patch"), list):
            if _is_wa(entry) and "replace" in entry:
                messages.append("the mod replaces WA_MRG.MRG as a whole: the Map tab shows the disc's map under it")
            kept.append(entry)
            continue
        rest = []
        for run in entry["patch"]:
            at = _number(run.get("at")) if isinstance(run, dict) else None
            blob = _hex_bytes(run.get("bytes")) if isinstance(run, dict) else None
            home = None
            if at is not None and blob:
                home = next((r for r in _ranges() if r[1] <= at and at + len(blob) <= r[2]), None)
            if home is None:
                if at is not None and blob and any(at < r[2] and at + len(blob) > r[1] for r in _ranges()):
                    messages.append(f"a patch at 0x{at:X} crosses the edge of the map's table: kept as written")
                rest.append(run)
                continue
            name, start, _ = home
            tables[name][at - start:at - start + len(blob)] = blob
            touched.add(name)
        if rest:
            kept.append(dict(entry, patch=rest))
        elif set(entry) - {"file", "patch"}:
            kept.append(dict(entry, patch=[]))
    if not touched:
        return
    if tables["before"] != tables["after"]:
        messages.append("the mod's map differs between the two overworld packages (before and after the coup); "
                        "the Map tab shows the one before the coup and will write both alike")
    source = "before" if "before" in touched else "after"
    st.locations = unpack_table(bytes(tables[source]))
    if kept:
        project.other["data"] = kept
    else:
        project.other.pop("data", None)


def read_mod(project, messages: list = None):
    """A freshly opened mod's map (manifest.open_mod)."""
    messages = [] if messages is None else messages
    project.map_state = MapState(getattr(project.retail, "campaign_map", None))
    adopt(project, project.map_state, messages)
    return messages


def runs(old: bytes, new: bytes, base: int, gap: int = 4) -> list:
    """The patch runs that turn old into new, as {"at", "bytes"} with the
    offset in hexadecimal; changes closer than `gap` bytes share a run."""
    out, i, n = [], 0, len(new)
    while i < n:
        if old[i] == new[i]:
            i += 1
            continue
        j = i + 1
        while j < n:
            if old[j] != new[j]:
                j += 1
                continue
            k = j
            while k < n and k - j < gap and old[k] == new[k]:
                k += 1
            if k < n and k - j < gap:
                j = k
                continue
            break
        out.append({"at": f"0x{base + i:X}", "bytes": new[i:j].hex(" ").upper()})
        i = j
    return out


def patch_entry(project):
    """The "data" entry the map writes, or None when it is the disc's."""
    st = state(project)
    if st.retail is None:
        return None
    table = pack_table(st.locations)
    patches = []
    for name, sector in PACKAGES:
        patches += runs(st.retail.raw[name], table, table_offset(sector))
    return {"file": ARCHIVE_FILE, "patch": patches} if patches else None


def build_into(project, manifest: dict):
    """Add the map's patches to the manifest's "data" (after what the mod
    keeps as written)."""
    entry = patch_entry(project)
    if entry is None:
        return
    data = manifest.get("data")
    data = list(data) if isinstance(data, list) else []
    data.append(entry)
    manifest["data"] = data


# --- checks ------------------------------------------------------------------------------

def edges(locations, index: int) -> list:
    """(kind, destination, condition) for every way out of a place: its used
    exits, Confirm when it leads to another place, and the town's Cancel
    back to the world map once the tournament is over."""
    loc = locations[index]
    out = []
    for n, e in enumerate(loc.exits):
        if e.used and 0 <= e.destination < COUNT:
            out.append((f"arrow {n + 1}", e.destination, e.condition))
    if 0 < loc.confirm < COUNT:
        out.append(("confirm", loc.confirm, loc.exits[0].condition if loc.gate else 0))
    if index >= TOWN_FIRST:
        out.append(("cancel", 0, TOURNAMENT_FLAG))
    return out


def unreachable(locations) -> list:
    """The places no way out of another place leads to (the story may still
    put the player there)."""
    reached = set()
    for index in range(COUNT):
        for _, destination, _ in edges(locations, index):
            if destination != index:
                reached.add(destination)
    return [i for i in range(COUNT) if i not in reached]


def check(project, out: list):
    from .validate import Issue
    st = state(project)
    if st.retail is None or not any_changed(project):
        return
    locations = st.locations

    def add(level, index, message):
        out.append(Issue(level, "Map", label(project, index), message, index))
    for index, loc in enumerate(locations):
        if not changed(project, index):
            continue
        if loc.confirm >= COUNT:
            add("error", index, f"Confirm leads to {loc.confirm}: there are only places 0-15")
        seen = []
        for n, e in enumerate(loc.exits):
            if not e.used:
                continue
            what = f"arrow {n + 1}"   # an exit, as the Map tab names it
            if e.destination > NO_EXIT:
                add("error", index, f"{what} leads to {e.destination}: there are only places 0-15 (16 is none)")
                continue
            if e.steps == 0:
                add("error", index, f"{what} takes 0 frames: the move divides by its length, so it must be 1 or more")
            if e.destination == index:
                add("warning", index, f"{what} leads back to this place")
            if not e.buttons & DIRECTION_BITS:
                add("warning", index, f"{what} needs no direction: it is never taken")
            elif e.buttons & ~DIRECTION_BITS & 0xFFFF:
                add("warning", index, f"{what} also answers buttons that are not directions "
                                      f"({describe_buttons(e.buttons)})")
            if e.condition & 0x7800:
                add("warning", index, f"{what}'s flag {e.condition & 0x7FFF} is past 0x7FF: the game reads "
                                      f"flag {e.condition & FLAG_ID}")
            if not (0 <= e.x < SCREEN[0] and 0 <= e.y < SCREEN[1]):
                add("warning", index, f"{what}'s arrow at {e.x},{e.y} is off the screen")
            if e.arrow >= len(ARROWS):
                add("warning", index, f"{what}'s arrow picture {e.arrow} is not one of the eight the map has")
            for m, other in seen:
                if other.buttons & e.buttons & DIRECTION_BITS and (other.condition == 0 or other.condition == e.condition):
                    add("warning", index, f"{what} is never taken while arrow {m + 1} is: the game takes the first "
                                          "arrow whose direction is held")
                    break
            seen.append((n, e))
        if index >= TOWN_FIRST and not (0 <= loc.marker_x < SCREEN[0] and 0 <= loc.marker_y < SCREEN[1]):
            add("warning", index, f"the marker at {loc.marker_x},{loc.marker_y} is off the screen")
    lost = [i for i in unreachable(locations) if i not in unreachable(st.retail.locations)]
    for index in lost:
        add("warning", index, "no arrow, Confirm or Cancel of another place leads here any more")


# --- sprites -------------------------------------------------------------------------------

def _u16(blob: bytes, at: int) -> int:
    return blob[at] | (blob[at + 1] << 8)


def color(word: int):
    """RGBA of a VRAM color word; 0 is transparent."""
    if word == 0:
        return 0, 0, 0, 0
    r, g, b = word & 31, (word >> 5) & 31, (word >> 10) & 31
    return (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255


def sprite_frame(resource: bytes, animation: int, variant: int = 0):
    """(frame offset, mirrored) of the first frame an object of the bank
    shows (DisplayObject_UpdateCommandStream: three levels of u16 offsets;
    DisplayObjectStream_ReadNextCommand: duration, u16 frame, or an opcode
    0xF0-0xFF; 0xFB toggles the mirror and jumps, 0xFC jumps), or None."""
    try:
        level1 = _u16(resource, 0)
        level2 = _u16(resource, level1 + animation * 2)
        at = _u16(resource, level2 + variant * 2)
        mirror = False
        for _ in range(16):
            op = resource[at]
            if op < 0xF0:
                return _u16(resource, at + 1), mirror
            if op in (0xFB, 0xFC):
                mirror ^= op == 0xFB
                at = _u16(resource, at + 1)
                continue
            return None
    except IndexError:
        return None
    return None


@dataclass
class SpritePart:
    dx: int
    dy: int
    u: int
    v: int
    width: int
    height: int
    palette: int        # 16-color palette index in the 256x4 block (x / 16 + y * 16)
    mirror: bool


def sprite_parts(resource: bytes, frame: int, mirror: bool) -> list:
    """The frame's parts (DisplayObject_RenderSpriteSheet): a four-byte
    header (count, flags, page, palette step) and six-byte parts."""
    count, flags, _page, step = resource[frame:frame + 4]
    parts = []
    for k in range(count):
        dx, dy, cell, size = struct.unpack_from("<bbHH", resource, frame + 4 + 6 * k)
        width, height = ((size >> 5) & 0xF) * 8 + 8, ((size >> 9) & 0xF) * 8 + 8
        if mirror:
            dx = -(dx + width)
        parts.append(SpritePart(dx, dy, (cell & 0x1F) * 8, ((cell >> 5) & 0x1F) * 8, width, height,
                                (step & 0xF) + (step >> 4) * 16, mirror ^ bool(cell & 0x2000)))
    return parts


def strip_index(strip: bytes, u: int, v: int) -> int:
    byte = strip[v * 128 + u // 2]
    return byte >> 4 if u & 1 else byte & 15


def palette_colors(palettes: bytes, palette: int) -> list:
    base = palette * 16
    return [color(_u16(palettes, (base + i) * 2)) for i in range(16)]


def sprite_image(data: MapData, animation: int, variant: int = 0, strips=None):
    """(image, left, top): the sprite as the game draws its first frame,
    and where its top-left corner is from the object's position; None when
    the bank has no such sprite. strips: {palette: picture} a mod draws in
    place of the strip through that palette (map_art)."""
    found = sprite_frame(data.resource, animation, variant)
    if not found or not data.strip:
        return None
    parts = sprite_parts(data.resource, *found)
    if not parts:
        return None
    left = min(p.dx for p in parts)
    top = min(p.dy for p in parts)
    width = max(p.dx + p.width for p in parts) - left
    height = max(p.dy + p.height for p in parts) - top
    out = bytearray(width * height * 4)
    for p in parts:
        colors = palette_colors(data.palettes, p.palette)
        own = (strips or {}).get(p.palette)
        scale = own.width // 256 if own is not None and own.width >= 256 else 0
        for j in range(p.height):
            for i in range(p.width):
                u, v = p.u + (p.width - 1 - i if p.mirror else i), p.v + j
                if scale:
                    at = ((v * scale + scale // 2) * own.width + u * scale + scale // 2) * 4
                    c = tuple(own.rgba[at:at + 4])
                    c = c if c[3] >= 128 else (0, 0, 0, 0)
                else:
                    c = colors[strip_index(data.strip, u, v)]
                if c[3]:
                    at = ((p.dy - top + j) * width + (p.dx - left + i)) * 4
                    out[at:at + 4] = bytes(c)
    return Image(width, height, bytes(out)), left, top


MARKER = (1, 0)
PANEL = (0, 0)


def arrow_image(data: MapData, arrow: int, strips=None):
    return sprite_image(data, 2, arrow, strips)
