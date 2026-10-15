"""The duel board as the game draws it: its 3D model from the user's disc,
textured with a mod's board (board_art.py), for the UI tab's Duel board
page and as the backdrop of other duel previews.

The model is phase 11 of each field's package (board_art.MODEL_SECTOR,
five sectors, the same bytes in all seven): an HMD whose first word is its
size. Duel_InitModelScene (src/game/duel_init_model_scene.c:13) hands it to
func_80056250(2, 0x80100000, ...), which passes it on to func_8004CB0C
(src/game/model_slot_setup.c:99): model slot 2, the stage. Its one block of
primitives is 78 lit, fogged textured triangles (0x0082000D) and 64 quads
(0x00020015), the drivers func_80033DB0 and func_80034830 that the campaign
map's terrain uses too (map_view.py reads both), under an identity
coordinate. Its polygons read the board phase's two VRAM columns
(tpage 0x1A and 0x1B) through the palettes board_art.PARTS names, so each
polygon is a piece of board_art's, found by its palette and texture
rectangle. Duel_DrawFieldCards (src/game/func_800164FC.c) draws it each
frame through func_800540B4(2).

The camera is D_800F2848's orbit (ViewState_ApplyOrbit,
src/game/view_state_orbit.c): `distance` from the target (x, 0, z),
raised by `pitch` and turned by `heading`. The duel's own, from its start
and whenever the hand is shown (func_80017130, Duel_InitScene,
DuelScene_UpdateTurnSwitch), is 600 away, pitch 0x100, heading 0x400 for
the player: CAMERA. Read back from a running duel: viewpoint (0, -229,
-554), target 0. The projection is 300 about 160, 108 (Duel_DrawFieldCards'
SetGeomOffset); against the game's frames at eight cameras (2026-10-07) the
picture fits best a pixel higher, as CENTRE has it (the GTE's screen points
are whole pixels, cut down, and the console fills a pixel by its corner,
this rasterizer by its centre). The light is
slot 2's: ambient one half and Model_InitLightTriplet's three flat lights
(src/game/model_slot_support.c), each corner lit by its normal (NCDS) and
fogged to black from 650 to 800 deep (SetFogNearFar in
Duel_DrawFieldCards). The picture is the game's closely, not exactly:
affine texturing as the console's, a depth buffer for its ordering table.

render_board(project, terrain, camera, size) is the picture alone, without
Tk and without side effects, for any page: camera None is the duel's, and at
320x240 the picture is the game's screen, so things placed at the game's
coordinates line up with it. render() also gives each pixel's piece, which
the Duel board page picks by."""
from __future__ import annotations

import math
import re
from array import array

from . import board_art as ba, map_view, pngio

CAMERA = (600, 0x400, 0x100, 0, 0)     # distance, heading, pitch, target x, target z
PROJECTION = 300
CENTRE = (160, 107)                     # the game's 160, 108, a pixel higher (above)
SCREEN = (320, 240)
FOG = (650, 800)
AMBIENT = 0.5
# Model_InitLightTriplet: (direction, intensity of 255).
LIGHTS = (((3000, 5000, 2000), 128), ((-3000, 5000, -2000), 128), ((0, -5000, 0), 64))
NEAR = 16                               # a corner nearer the eye than this drops its polygon
BACKGROUND = (0, 0, 0)
# Orbit limits: the camera stays above the floor and outside the board.
PITCH_RANGE = (16, 1020)
DISTANCE_RANGE = (150, 2400)
TARGET_RANGE = 400


class Board:
    """The model of a field's board: polygons, each with its piece (a part
    key of board_art, or None), and VRAM as the board phase leaves it."""

    def __init__(self, blob: bytes, phase: bytes = None):
        self.model = map_view.MapModel(blob, scale=1.0, header=False)
        if phase:
            vram = self.model.vram
            for column in range(2):
                for row in range(256):
                    at = column * ba.COLUMN_BYTES + row * ba.ROW_BYTES
                    start = (256 + row) * 1024 + 640 + 64 * column
                    vram[start:start + 64] = array("H", phase[at:at + ba.ROW_BYTES])
        cluts = {clut_word(p.column, p.palette): p for p in ba.PARTS}
        self.parts = [part_of(cluts, polygon) for polygon in self.model.polygons]
        self.shades = [shade(n) for n in self.model.normals]
        self.points = [self.model.world(v) for v in self.model.vertices]


def clut_word(column: int, palette: int) -> int:
    """The palette word (GPU clut) of a palette at `palette` bytes into the
    board phase, as the phase lies in VRAM from (640, 256)."""
    inner = palette - column * ba.COLUMN_BYTES
    x = 640 + 64 * column + (inner % ba.ROW_BYTES) // 2
    y = 256 + inner // ba.ROW_BYTES
    return (y << 6) | (x >> 4)


def part_of(cluts: dict, polygon):
    """The piece a polygon draws: its palette, page and texture rectangle."""
    uvs, clut, tpage, _, _ = polygon
    part = cluts.get(clut & 0x7FFF)
    if part is None or (tpage & 15) != 10 + part.column or (tpage >> 4) & 1 != 1:
        return None
    us, vs = [u & 255 for u in uvs], [u >> 8 for u in uvs]
    if part.x <= min(us) and max(us) <= part.x + part.w and part.y <= min(vs) and max(vs) <= part.y + part.h:
        return part.key
    return None


def shade(normal) -> float:
    """The light a corner with this normal gets (NCDS: ambient plus each
    flat light along it), 1.0 the texture as it is."""
    out = AMBIENT
    for (lx, ly, lz), intensity in LIGHTS:
        length = math.sqrt(lx * lx + ly * ly + lz * lz)
        out += max(0.0, -(lx * normal[0] + ly * normal[1] + lz * normal[2]) / length / 4096) * intensity / 255
    return out


_BOARDS = {}


def board(data: ba.BoardData, terrain: str) -> Board:
    """A field's board, parsed once per disc."""
    blob, phase = data.models[terrain], data.phases.get(terrain)
    key = (terrain, id(blob), id(phase))
    if key not in _BOARDS:
        if len(_BOARDS) > 16:
            _BOARDS.clear()
        _BOARDS[key] = (Board(blob, phase), blob, phase)      # the bytes kept: their ids stay theirs
    return _BOARDS[key][0]


def available(project) -> bool:
    data = ba.disc(project)
    return data.ok and len(data.models) == len(ba.TERRAINS)


# --- the camera ------------------------------------------------------------------------------

def basis(camera):
    """(viewpoint, forward, right, down) of a camera, as GsSetRefView2
    makes them (map_view.render's)."""
    vp, vr = map_view.eye(camera)
    f = [vr[i] - vp[i] for i in range(3)]
    length = math.sqrt(sum(a * a for a in f)) or 1.0
    f = [a / length for a in f]
    r = [f[2], 0.0, -f[0]]
    length = math.sqrt(r[0] * r[0] + r[2] * r[2])
    r = [a / length for a in r] if length > 1e-9 else [1.0, 0.0, 0.0]
    u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]]
    return vp, f, r, u


def frame(size):
    """(scale, x, y): the game's 320x240 screen within a picture of `size`,
    as large as it fits and centred (a wider picture shows more at the
    sides, a taller one above and below)."""
    width, height = size
    k = min(width / SCREEN[0], height / SCREEN[1])
    return k, width / 2 - SCREEN[0] / 2 * k, height / 2 - SCREEN[1] / 2 * k


def clamp(camera):
    """The camera kept where the board can be seen from: above the floor,
    not inside it, its target on the board."""
    distance, heading, pitch, tx, tz = camera
    return (max(DISTANCE_RANGE[0], min(DISTANCE_RANGE[1], round(distance))), round(heading) % 4096,
            max(PITCH_RANGE[0], min(PITCH_RANGE[1], round(pitch))),
            max(-TARGET_RANGE, min(TARGET_RANGE, round(tx))), max(-TARGET_RANGE, min(TARGET_RANGE, round(tz))))


def orbit(camera, dx: float, dy: float):
    """The camera turned round its target by a drag of dx, dy (the game's
    pixels): across turns it, down raises it."""
    distance, heading, pitch, tx, tz = camera
    return clamp((distance, heading - dx * 8, pitch + dy * 6, tx, tz))


def pan(camera, dx: float, dy: float):
    """The target moved along the floor by a drag of dx, dy (the game's
    pixels), so the board follows the mouse at the target's depth."""
    distance, heading, pitch, tx, tz = camera
    _, f, r, _ = basis(camera)
    per = distance / PROJECTION                     # world units a pixel at the target's depth
    level = math.hypot(f[0], f[2]) or 1.0
    ahead = (f[0] / level, f[2] / level)
    sin = math.sin(pitch * 2 * math.pi / 4096) or 1e-3
    tx -= (dx * r[0] - dy * ahead[0] / sin) * per
    tz -= (dx * r[2] - dy * ahead[1] / sin) * per
    return clamp((distance, heading, pitch, tx, tz))


def zoom(camera, steps: float):
    """Nearer by a tenth a step (fewer than 0: farther)."""
    distance, heading, pitch, tx, tz = camera
    return clamp((distance * 0.9 ** steps, heading, pitch, tx, tz))


def projector(camera, size=SCREEN):
    """A function from a point of the board to where `camera` (None: the
    duel's) shows it in a picture of `size`: (x, y, depth), or None nearer
    than NEAR (or behind)."""
    camera = CAMERA if camera is None else camera
    vp, f, r, u = basis(camera)
    k, ox, oy = frame(size)
    cx, cy, scale = ox + CENTRE[0] * k, oy + CENTRE[1] * k, PROJECTION * k

    def to_screen(w):
        p = (w[0] - vp[0], w[1] - vp[1], w[2] - vp[2])
        z = p[0] * f[0] + p[1] * f[1] + p[2] * f[2]
        if z <= NEAR:
            return None
        return (cx + scale * (p[0] * r[0] + p[1] * r[1] + p[2] * r[2]) / z,
                cy + scale * (p[0] * u[0] + p[1] * u[1] + p[2] * u[2]) / z, z)
    return to_screen


# --- the picture -------------------------------------------------------------------------------

class Picture:
    """A render: the image and, per pixel, the index in `keys` of the piece
    drawn there (0: none)."""

    def __init__(self, image, ids, keys):
        self.image, self.ids, self.keys = image, ids, keys

    def part_at(self, x: int, y: int):
        if not (0 <= x < self.image.width and 0 <= y < self.image.height):
            return None
        index = self.ids[y * self.image.width + x]
        return self.keys[index - 1] if index else None


KEYS = [p.key for p in ba.PARTS]


def render(mdl: Board, pieces: dict, camera=None, size=SCREEN) -> Picture:
    """The board as `camera` (None: the duel's) sees it, `pieces` (part
    key -> picture, any scale) its textures; a part missing is the disc's
    own texels."""
    steps = render_steps(mdl, pieces, camera, size)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def render_steps(mdl: Board, pieces: dict, camera=None, size=SCREEN, step: int = map_view.STEP):
    """render() a little at a time (map_view.raster_steps): a generator
    pausing every `step` pixels or so, its value (StopIteration's) the
    Picture."""
    to_screen = projector(camera, size)
    near, far = FOG
    projected = []
    for w in mdl.points:
        p = to_screen(w)
        if p is None:
            projected.append(None)
            continue
        x, y, z = p
        fog = 0.0 if z <= near else min(1.0, far * (z - near) / (z * (far - near)))
        projected.append((x, y, z, 1.0 - fog))
    width, height = size
    overrides = {}
    for key, image in pieces.items():
        if image is not None:
            part = ba.BY_KEY[key]
            overrides[key] = (image.rgba, image.width, image.height, part.x, part.y, part.w, part.h)
    shades = mdl.shades
    faces = []
    for (uvs, clut, tpage, vertices, normals), key in zip(mdl.model.polygons, mdl.parts):
        points = [projected[i] if i < len(projected) else None for i in vertices]
        if any(p is None for p in points):
            continue
        tag = KEYS.index(key) + 1 if key else 0
        for tri in ((0, 1, 2),) if len(vertices) == 3 else ((0, 1, 2), (1, 3, 2)):
            corners = []
            for i in tri:
                x, y, z, clear = points[i]
                light = shades[normals[i]] if normals[i] < len(shades) else 1.0
                corners.append((x, y, z, uvs[i] & 255, uvs[i] >> 8, light * clear))
            (xa, ya, _, _, _, _), (xb, yb, _, _, _, _), (xc, yc, _, _, _, _) = corners
            if (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya) <= 0:
                continue            # a back face (NCLIP)
            faces.append((corners, tpage, clut, overrides.get(key), tag))
    ids = bytearray(width * height)
    pixels = [bytes((*BACKGROUND, 255))] * (width * height)
    yield from map_view.raster_steps(size, faces, mdl.model.vram, pixels, ids, step)
    return Picture(pngio.Image(width, height, b"".join(pixels)), ids, KEYS)


_PIECES = {}
_PICTURES = {}


def _cached(cache: dict, key, project, make):
    """What make() gives, kept while the project's board is unchanged: its
    state and version (board_art.touched counts every edit), or for no edit
    at all the disc's own."""
    st = ba.state(project)
    plain = not st.pictures and not st.tints
    key = (id(ba.disc(project)), plain) + key
    hit = cache.get(key)
    if hit is not None and hit[0] is ba.disc(project) and (plain or (hit[1] is st and hit[2] == st.version)):
        return hit[3]
    if len(cache) > 16:
        cache.clear()
    value = make()
    cache[key] = (ba.disc(project), st, st.version, value)      # held: their ids stay theirs
    return value


def pieces_of(project, terrain: str) -> dict:
    """Each piece as the mod draws it (board_art.shown)."""
    return _cached(_PIECES, (terrain,), project,
                   lambda: {part.key: ba.shown(project, terrain, part) for part in ba.PARTS})


def render_board(project, terrain: str = "normal", camera=None, size=SCREEN) -> pngio.Image:
    """The field's board with the project's textures (its pictures and
    tints), as `camera` sees it (None: the duel's at its start, the game's
    own framing at 320x240). None without the disc's board."""
    if not available(project):
        return None
    camera = CAMERA if camera is None else tuple(camera)
    return _cached(_PICTURES, (terrain, camera, tuple(size)), project,
                   lambda: render(board(ba.disc(project), terrain), pieces_of(project, terrain), camera,
                                  tuple(size)).image)


def outline(picture: Picture, keys, thickness: int = 1, color=(0x40, 0xE0, 0xFF), dark=(0, 0, 0)) -> pngio.Image:
    """The picture with the edge of what `keys` cover drawn round: a line
    of `color` `thickness` pixels wide inside it and one of `dark`
    outside.

    A row at a time, a byte a pixel as one number: a pixel of the mask is
    on its edge when a neighbour (or the picture's edge) is not. The line
    inside is the mask's pixels within thickness - 1 (across, down or
    diagonally) of an edge pixel; outside, those not in the mask within
    thickness of one, which are those within thickness of the mask (the
    nearest of it is an edge). Both are the rows widened by shifts and
    or-ed with their neighbours, painted a run at a time."""
    image = picture.image
    width, height = image.width, image.height
    wanted = {picture.keys.index(k) + 1 for k in keys if k in picture.keys}
    mask = picture.ids.translate(bytes(1 if i in wanted else 0 for i in range(256)))
    out = bytearray(image.rgba)
    if not wanted or 1 not in mask:
        return pngio.Image(width, height, bytes(out))
    ones = int.from_bytes(b"\1" * width, "big")
    rows = [int.from_bytes(mask[y * width:(y + 1) * width], "big") for y in range(height)]
    edges = []
    for y, row in enumerate(rows):
        if not row:
            edges.append(0)
            continue
        above = rows[y - 1] if y > 0 else 0
        below = rows[y + 1] if y + 1 < height else 0
        outside = (ones ^ (row >> 8)) | (ones ^ (row << 8 & (ones * 255))) | (ones ^ above) | (ones ^ below) | 1 | 1 << 8 * (width - 1)
        edges.append(row & outside)
    for lines, reach, paint, inside in ((edges, thickness - 1, bytes(color), True),
                                        (rows, thickness, bytes(dark), False)):
        if reach < 0:
            continue
        across = []
        for line in lines:
            wide = line
            for k in range(1, reach + 1):
                wide |= line >> 8 * k | line << 8 * k
            across.append(wide & ones)
        for y in range(height):
            near = 0
            for ny in range(max(0, y - reach), min(height, y + reach + 1)):
                near |= across[ny]
            near = near & rows[y] if inside else near & ~rows[y]
            if not near:
                continue
            base = y * width * 4
            for run in _RUN.finditer(near.to_bytes(width, "big")):
                first, last = run.span()
                for c in range(3):
                    out[base + first * 4 + c:base + last * 4:4] = paint[c:c + 1] * (last - first)
    return pngio.Image(width, height, bytes(out))


_RUN = re.compile(b"\1+")
