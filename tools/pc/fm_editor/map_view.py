"""Pictures of the campaign map drawn from the player's disc, for the Map tab.

The map is a 3D model: the overworld package's 134-sector block (WA sector
+6, loaded at 0x80100000) is an HMD (src/pc/sdk/libgs_unit.c reads the same
layout): a header, a primitive header section, a coordinate section and
blocks of primitives. Block 0 uploads the textures and their palettes
(GsU_02000001: image rectangle, offset; palette rectangle, offset); block 1
holds the terrain as fog-shaded textured triangles (type 0x0002000D,
func_80033DB0: twelve halfwords uv0, clut, uv1, tpage, uv2, pad, then
normal and vertex for each corner) and quads (0x00020015, func_80034830:
fourteen halfwords uv0, clut, uv1, tpage, uv2, n0, uv3, v0, n1, v1, n2, v2,
n3, v3). CampaignMap_SetLocation scales the model by 1365/4096 and turns
it by its coordinate's rotation (func_8005922C).

A place's camera is ViewState_ApplyOrbit's: the viewpoint is `distance`
from the target (x, 0, z), raised by `pitch` and turned by `heading`, with
the projection 300 (GsSetProjection) centred at 160, 120. The picture is the
game's closely, not exactly: affine texturing, back faces culled, the light
a fit to the game's frames (a little under two thirds ambient, the rest
from above), the far fog of CampaignMap_UpdateView (2000 to 2400) and, on
the world map, the spotlight mask of CampaignMap_SetLocation (clear within
32 of 160, 144, black from 192 out, 1.25 times wider than tall)."""
from __future__ import annotations

import math
import struct
import sys
from array import array

from . import pngio

SECTOR = 2048
MODEL_SECTOR = 6                # the block's first sector in the package
MODEL_SECTORS = 134
SCALE = 1365 / 4096
PROJECTION = 300
FOG = (2000, 2400)
AMBIENT, DIFFUSE = 0.61, 0.58
LIGHT = (0.10, -0.99, 0.02)     # towards the light, in the model's axes (y down)
SPOTLIGHT = (160, 144, 32, 192, 1.25)


class ModelError(Exception):
    pass


class MapModel:
    """The terrain of one overworld package: vertices, normals, polygons,
    and VRAM as its image uploads leave it."""

    def __init__(self, blob: bytes, scale: float = SCALE, header: bool = True):
        self.blob = blob
        self.scale = scale
        self.header = header        # the HMD's own first word (0x50); the duel board's holds its size
        self.vram = array("H", bytes(1024 * 512 * 2))
        self.polygons = []          # (uvs, clut, tpage, vertices, normals)
        self.images = []            # dicts: the image uploads (x, y, words, rows, offset, clut...)
        self.vertices = []
        self.normals = []
        self.matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        self.translation = (0, 0, 0)
        self.parse()

    def word(self, index: int) -> int:
        return struct.unpack_from("<I", self.blob, index * 4)[0]

    def parse(self):
        blob, word = self.blob, self.word
        if len(blob) < 64 or (self.header and word(0) != 0x50):
            raise ModelError("the map block is not an HMD")
        # The primitive header section: a count, then per header its
        # section count and the sections' word offsets (top bit set).
        at = word(2)
        headers = {}
        position = at + 1
        for _ in range(word(at)):
            count = word(position)
            headers[position] = [word(position + 1 + i) & 0x7FFFFFFF for i in range(count)]
            position += 1 + count
        terrain = None
        for b in range(word(3)):
            block = word(4 + b)
            if not block:
                continue
            # A block: the next block (0xFFFFFFFF: none), its header, the
            # number of primitive types, then the types.
            count = word(block + 2) & 0xFFFF
            sections = headers.get(word(block + 1))
            if sections is None:
                raise ModelError("a block names no primitive header")
            cursor = block + 3
            for _ in range(count):
                kind, head = word(cursor), word(cursor + 1)
                size, items = head & 0xFFFF, (head >> 16) & 0x7FFF
                if kind in (0x02000000, 0x02000001):
                    self.upload(cursor + 2, items, kind & 1, sections)
                elif kind & 0xFFFF in (0x000D, 0x0015):
                    self.read_polygons(sections[0] + word(cursor + 2), items, kind & 0xFFFF == 0x0015)
                    terrain = sections
                cursor += 1 + size
        if terrain is None:
            raise ModelError("the map block has no terrain")
        vertices, normals, coordinates = terrain[1], terrain[2], terrain[3]
        count = (normals - vertices) // 2
        self.vertices = [struct.unpack_from("<hhh", blob, (vertices + 2 * i) * 4) for i in range(count)]
        count = (terrain[0] - normals) // 2
        self.normals = [struct.unpack_from("<hhh", blob, (normals + 2 * i) * 4) for i in range(count)]
        unit = coordinates * 4 + 4          # the first GsCOORDUNIT: flg, coord MATRIX, workm, rot, super
        self.translation = struct.unpack_from("<3i", blob, unit + 4 + 20)
        rx, ry, rz = struct.unpack_from("<3h", blob, unit + 68)
        self.matrix = rotation_yxz(rx, ry, rz)

    def upload(self, at: int, items: int, with_clut: int, sections):
        for _ in range(items):
            parts = []
            for k in range(1 + with_clut):
                x, y, w, h = struct.unpack_from("<hhhh", self.blob, at * 4)
                offset = (sections[k] + self.word(at + 2)) * 4
                parts.append((x, y, w, h, offset))
                for row in range(h):
                    line = struct.unpack_from(f"<{w}H", self.blob, offset + row * w * 2)
                    start = ((y + row) & 511) * 1024 + (x & 1023)
                    self.vram[start:start + w] = array("H", line)
                at += 3
            self.images.append(parts)

    def read_polygons(self, at: int, items: int, quad: bool):
        stride = 14 if quad else 12
        for i in range(items):
            r = struct.unpack_from(f"<{stride}H", self.blob, at * 4 + i * stride * 2)
            if quad:
                self.polygons.append(((r[0], r[2], r[4], r[6]), r[1], r[3], (r[7], r[9], r[11], r[13]),
                                      (r[5], r[8], r[10], r[12])))
            else:
                self.polygons.append(((r[0], r[2], r[4]), r[1], r[3], (r[7], r[9], r[11]), (r[6], r[8], r[10])))

    def polygon_blocks(self) -> list:
        """The image upload each polygon's texture lies in (the last one to
        cover it, as VRAM keeps it), or None."""
        if getattr(self, "_blocks", None) is None:
            blocks = []
            for uvs, clut, tpage, _, _ in self.polygons:
                depth = (tpage >> 7) & 3
                per = 4 if depth == 0 else 2 if depth == 1 else 1
                px, py = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
                us, vs = [u & 255 for u in uvs], [u >> 8 for u in uvs]
                left, right = px + min(us) // per, px + max(us) // per
                top, bottom = py + min(vs), py + max(vs)
                found = None
                for index in range(len(self.images) - 1, -1, -1):
                    x, y, w, h, _ = self.images[index][0]
                    if x <= left and right < x + w and y <= top and bottom < y + h:
                        found = index
                        break
                blocks.append(found)
            self._blocks = blocks
        return self._blocks

    def world(self, v):
        m, t = self.matrix, self.translation
        return tuple(sum(m[i][j] * v[j] for j in range(3)) * self.scale + t[i] for i in range(3))

    def shades(self):
        """The light each normal gets, turned with the model (worked out
        once: the model does not change once read)."""
        if getattr(self, "_shades", None) is None:
            m = self.matrix
            out = []
            for n in self.normals:
                turned = [sum(m[i][j] * n[j] for j in range(3)) / 4096 for i in range(3)]
                out.append(AMBIENT + DIFFUSE * max(0.0, sum(turned[i] * LIGHT[i] for i in range(3))))
            self._shades = out
        return self._shades

    def points(self):
        """Each vertex in the world (world()), worked out once."""
        if getattr(self, "_points", None) is None:
            self._points = [self.world(v) for v in self.vertices]
        return self._points


def rotation_yxz(rx, ry, rz):
    """RotMatrixYXZ: Ry * Rx * Rz, angles in 4096ths of a turn."""
    def c(a):
        return math.cos(a * 2 * math.pi / 4096)

    def s(a):
        return math.sin(a * 2 * math.pi / 4096)
    mx = ((1, 0, 0), (0, c(rx), -s(rx)), (0, s(rx), c(rx)))
    my = ((c(ry), 0, s(ry)), (0, 1, 0), (-s(ry), 0, c(ry)))
    mz = ((c(rz), -s(rz), 0), (s(rz), c(rz), 0), (0, 0, 1))

    def mul(a, b):
        return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(mul(my, mx), mz)


def model_blob(wa: bytes, package_sector: int) -> bytes:
    start = (package_sector + MODEL_SECTOR) * SECTOR
    return bytes(wa[start:start + MODEL_SECTORS * SECTOR])


_MODELS = {}


def model(wa: bytes, package_sector: int) -> MapModel:
    """The package's map, parsed once per disc."""
    key = (id(wa), len(wa), package_sector)
    if key not in _MODELS:
        _MODELS[key] = MapModel(model_blob(wa, package_sector))
    return _MODELS[key]


def eye(camera):
    """(viewpoint, target) of a place's camera (ViewState_ApplyOrbit)."""
    distance, heading, pitch, tx, tz = camera
    turn = 2 * math.pi / 4096
    level = -distance * math.cos(pitch * turn)
    rise = -distance * math.sin(pitch * turn)
    return (tx + level * math.cos(heading * turn), rise, tz + level * math.sin(heading * turn)), (tx, 0, tz)


# The textures as the rasterizer reads them: per texture (a page and
# palette, or a mod's picture) 256 rows of 256 texels, each (red, green,
# blue, n) or None where clear, so a pixel costs two lookups; n numbers the texture's colors (below 0: not numbered,
# the 16-bit pages') for the rasterizer's shaded colors. Kept across
# renders while the VRAM or picture they come from lives (a model's VRAM
# is not changed once it is built).
_TABLES = {}


class _Texture:
    __slots__ = ("rows", "colors", "never")

    def __init__(self, rows, colors):
        self.rows, self.colors = rows, colors     # colors: how many n's there are
        self.never = [False] * (colors + 1)         # its shaded colors where none is ever the same


def _texture(vram, tpage, clut, override) -> _Texture:
    if override is not None:
        key, holder = ("picture", id(override[0])) + tuple(override[1:]), override[0]
    else:
        key, holder = ("vram", id(vram), tpage, clut), vram
    hit = _TABLES.get(key)
    if hit is not None and hit[0] is holder:
        return hit[1]
    if len(_TABLES) > 160:
        _TABLES.clear()
    if override is not None:
        texture = _picture_texture(*override)
    else:
        rows = []
        rows.extend(_Row(rows, vram, tpage, clut, v) for v in range(256))
        texture = _Texture(rows, 256)
    _TABLES[key] = (holder, texture)        # held: its id stays its own
    return texture


class _Row:
    """A row of VRAM's texels not read yet: read (_vram_row) and put in its
    place at the first look."""
    __slots__ = ("rows", "vram", "tpage", "clut", "v")

    def __init__(self, rows, vram, tpage, clut, v):
        self.rows, self.vram, self.tpage, self.clut, self.v = rows, vram, tpage, clut, v

    def __getitem__(self, u):
        row = self.rows[self.v] = _vram_row(self.vram, self.tpage, self.clut, self.v)
        return row[u]


def _picture_texture(rgba, iw, ih, ox, oy, tw, th) -> _Texture:
    """A mod's picture as texels: u, v scaled onto it from the texture's
    rectangle (clamped at its edges), clear under half alpha. Its pixels
    are read as 32-bit numbers (red the low byte), a row a slice."""
    words = array(_WORD, rgba)
    if sys.byteorder == "big":
        words.byteswap()
    xs = [min(iw - 1, max(0, (tu - ox) * iw // tw)) for tu in range(256)]
    seen, lines, rows = {}, {}, []
    for tv in range(256):
        iy = min(ih - 1, max(0, (tv - oy) * ih // th))
        line = lines.get(iy)
        if line is None:
            pixels = words[iy * iw:(iy + 1) * iw]
            for word in set(pixels).difference(seen):
                seen[word] = None if word >> 24 < 128 else (word & 255, word >> 8 & 255, word >> 16 & 255, len(seen))
            line = lines[iy] = list(map(seen.__getitem__, map(pixels.__getitem__, xs)))
        rows.append(line)
    return _Texture(rows, len(seen))


_WORD = next(code for code in "IL" if array(code).itemsize == 4)


def _vram_row(vram, tpage, clut, v) -> list:
    """Row v of a page's texture: 4 or 8 bits a texel through the palette
    at `clut` (an entry clear only when it is the first and 0: the game
    uploads every other with the semi-transparency bit), or 16-bit color
    words (0 clear)."""
    px, py, depth = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256, (tpage >> 7) & 3
    if depth >= 2:
        start = ((py + v) & 511) * 1024
        words = [vram[start + ((px + u) & 1023)] for u in range(256)]
        return [None if w == 0 else ((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8, -1) for w in words]
    start = (py + v) * 1024 + px
    if depth == 0:
        indices = [(vram[start + (u >> 2)] >> ((u & 3) * 4)) & 15 for u in range(256)]
    else:
        indices = [(vram[start + (u >> 1)] >> ((u & 1) * 8)) & 255 for u in range(256)]
    base = (clut >> 6) * 1024 + (clut & 63) * 16
    palette = {}
    for index in set(indices):
        word = vram[base + index]
        palette[index] = None if index == 0 and word == 0 else \
            ((word & 31) * 8, ((word >> 5) & 31) * 8, ((word >> 10) & 31) * 8, index)
    return [palette[i] for i in indices]


def _shaded(texel, low: float, high: float):
    """A texel's pixel (red, green, blue, 255) under any shade from low to
    high, as the rasterizer's int(channel * shade) gives it, when that is
    the same all through (a margin far wider than the sums' rounding
    either side); else False."""
    out = []
    for channel in texel[:3]:
        if channel == 0:
            out.append(0)
            continue
        first = math.floor(channel * low - 1e-9)
        if first < 0 or first != math.floor(channel * high + 1e-9):
            return False
        out.append(min(255, first))
    return bytes(out + [255])


def _span(a0, ax, b0, bx, flats, left, right):
    """The pixels (first, last) of a row to try: where the weights
    a = a0 + ax * (x + 0.5), b (as a) and 1 - a - b are all at least 0,
    two pixels wider each side than these sums say. The exact test is the
    rasterizer's, per pixel; this only spares it the bounding box's empty
    corners. An edge nearly along the row (its `flats`) bounds nothing
    here: its weight is too near the same all along it to place."""
    lo, hi = left + 0.5, right + 0.5
    for k0, kx, flat in ((a0, ax, flats[0]), (b0, bx, flats[1]), (1.0 - a0 - b0, -ax - bx, flats[2])):
        if flat:
            continue
        if kx > 0:
            lo = max(lo, -k0 / kx)
        elif kx < 0:
            hi = min(hi, -k0 / kx)
    if lo > hi + 2:
        return 0, -1
    return max(left, int(math.floor(lo - 0.5)) - 2), min(right, int(math.floor(hi - 0.5)) + 2)


def _rasterize(size, faces, vram, background=(0, 0, 0), ids=None) -> bytes:
    """The faces drawn over `background`: ((x, y, z, u, v, shade) * 3,
    tpage, clut, override[, id]), nearest z first kept; shade multiplies the
    texel. `ids` (a byte per pixel) takes the drawn face's id. The pixels,
    RGBA."""
    pixels = [bytes((*background, 255))] * (size[0] * size[1])
    for _ in raster_steps(size, faces, vram, pixels, ids):
        pass
    return b"".join(pixels)


STEP = 20000                    # pixels tried between two of raster_steps' pauses (some 10 ms)


def raster_steps(size, faces, vram, pixels, ids=None, step: int = STEP):
    """_rasterize a little at a time, into `pixels` (a list, each pixel's
    RGBA as bytes, joined when done): a generator pausing (yielding) every
    `step` pixels or so, for a picture drawn while the window stays live.

    A pixel's sums are those of the plain loop this replaced, in the same
    order (the picture is the same to the bit: tests/test_render_speed.py
    keeps that loop and compares); the work round them is less:
    * a row is tried from where the triangle starts to where it ends
      (_span), not across its bounding box, and a column's and a row's own
      terms are worked out once;
    * the texels come from tables (_texture), and a texel's color under a
      face's shades once per face, where the face's lightest and darkest
      shade give it the same (_shaded): most of the board's faces are lit
      alike all over;
    * a pixel's depth is worked out only where a face has been drawn there
      before (the buffer holds which face that was, and its depth there is
      worked out again as it was);
    * a pixel is one store of its four bytes, the picture joined once.
    u and v need no & 255: a sum of the corners' (0 to 255) by weights of
    at least 0 is in their range, give or take a hair."""
    width, height = size
    if ids is None:
        ids = bytearray(width * height)
    owner = [0] * (width * height)                      # 1 + the face drawn at each pixel, 0: none yet
    drawn = []                                          # the faces drawn, for their depths
    colors = {}                                        # (texture, shades) -> its colors shaded (_shaded)
    budget = step
    for face in faces:
        corners, tpage, clut, override = face[:4]
        tag = face[4] if len(face) > 4 else 0
        (x0, y0, z0, u0, v0, s0), (x1, y1, z1, u1, v1, s1), (x2, y2, z2, u2, v2, s2) = corners
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if area == 0:
            continue
        inv = 1.0 / area
        left, right = max(int(min(x0, x1, x2)), 0), min(int(max(x0, x1, x2)) + 1, width - 1)
        top, bottom = max(int(min(y0, y1, y2)), 0), min(int(max(y0, y1, y2)) + 1, height - 1)
        if left > right or top > bottom:
            continue
        texture = _texture(vram, tpage, clut, override)
        rows = texture.rows
        low, high = min(s0, s1, s2), max(s0, s1, s2)
        if (high - low) * 255 >= 1:
            lut = texture.never         # shades too far apart: a bright texel's color changes across the face
        else:
            lut = colors.get((texture, low, high))
            if lut is None:
                lut = colors[texture, low, high] = [None] * texture.colors + [False]     # n -1: never shaded once
        drawn.append((x0, y0, z0, x1, y1, z1, x2, y2, z2, inv))
        mark = len(drawn)
        ax, bx = (y1 - y2) * inv, (y2 - y0) * inv
        flats = (abs(y1 - y2) < 1e-3, abs(y2 - y0) < 1e-3, abs(y0 - y1) < 1e-3)
        # Each column's x terms (a corner's x less the pixel's centre's).
        centres = [x + 0.5 for x in range(left, right + 1)]
        cx0, cx1, cx2 = [x0 - xx for xx in centres], [x1 - xx for xx in centres], [x2 - xx for xx in centres]
        for y in range(top, bottom + 1):
            yy = y + 0.5
            e0, e1, e2 = y0 - yy, y1 - yy, y2 - yy
            start, end = _span((x1 * e2 - x2 * e1) * inv, ax, (x2 * e0 - x0 * e2) * inv, bx, flats, left, right)
            row = y * width
            first, last = start - left, end - left + 1
            for at, dx0, dx1, dx2 in zip(range(row + start, row + end + 1), cx0[first:last], cx1[first:last],
                                         cx2[first:last]):
                a = (dx1 * e2 - dx2 * e1) * inv
                if a < 0:
                    continue
                b = (dx2 * e0 - dx0 * e2) * inv
                if b < 0:
                    continue
                c = 1.0 - a - b
                if c < 0:
                    continue
                before = owner[at]
                if before and a * z0 + b * z1 + c * z2 >= _depth(drawn[before - 1], at - row + 0.5, yy):
                    continue
                texel = rows[int(a * v0 + b * v1 + c * v2)][int(a * u0 + b * u1 + c * u2)]
                if texel is None:
                    continue
                owner[at] = mark
                ids[at] = tag
                shaded = lut[texel[3]]
                if shaded:
                    pixels[at] = shaded
                    continue
                if shaded is None:
                    shaded = lut[texel[3]] = _shaded(texel, low, high)
                    if shaded:
                        pixels[at] = shaded
                        continue
                shade = a * s0 + b * s1 + c * s2
                red, green, blue = int(texel[0] * shade), int(texel[1] * shade), int(texel[2] * shade)
                pixels[at] = bytes((red if red < 255 else 255, green if green < 255 else 255,
                                    blue if blue < 255 else 255, 255))
            budget -= end - start + 1
            if budget <= 0:
                yield
                budget = step


def _depth(face, xx, yy) -> float:
    """A drawn face's depth at a pixel's centre, as the rasterizer worked
    it out drawing it."""
    x0, y0, z0, x1, y1, z1, x2, y2, z2, inv = face
    a = ((x1 - xx) * (y2 - yy) - (x2 - xx) * (y1 - yy)) * inv
    b = ((x2 - xx) * (y0 - yy) - (x0 - xx) * (y2 - yy)) * inv
    return a * z0 + b * z1 + (1.0 - a - b) * z2


def _override(mdl: MapModel, index: int, overrides):
    """The rasterizer's view of a mod's picture for a polygon's texture:
    (pixels, width, height, texture origin u, v in its page, texture size)."""
    if not overrides:
        return None
    block = mdl.polygon_blocks()[index]
    uvs, clut, tpage, _, _ = mdl.polygons[index]
    image = overrides.get((block, clut)) if block is not None else None
    if image is None:
        return None
    x, y, w, h, _ = mdl.images[block][0]
    depth = (tpage >> 7) & 3
    per = 4 if depth == 0 else 2 if depth == 1 else 1
    px, py = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    return image.rgba, image.width, image.height, (x - px) * per, y - py, w * per, h


def render(mdl: MapModel, camera, spotlight: bool = False, size=(320, 240), overrides=None) -> pngio.Image:
    """The place's screen as its camera sees the map (320x240); overrides:
    {(image upload, palette word): picture} drawn in place of those
    textures (a mod's texture pack)."""
    vp, vr = eye(camera)
    f = [vr[i] - vp[i] for i in range(3)]
    length = math.sqrt(sum(a * a for a in f)) or 1.0
    f = [a / length for a in f]
    r = [f[2], 0.0, -f[0]]          # (down x forward): y down, as the PS1's axes
    length = math.sqrt(r[0] * r[0] + r[2] * r[2])
    # Straight down, GsSetRefView2 skips the turn about y: x stays across.
    r = [a / length for a in r] if length > 1e-9 else [1.0, 0.0, 0.0]
    u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]]
    width, height = size
    k = width / 320
    near, far = FOG
    projected = []
    for w in mdl.points():
        p = (w[0] - vp[0], w[1] - vp[1], w[2] - vp[2])
        z = p[0] * f[0] + p[1] * f[1] + p[2] * f[2]
        if z <= 16:
            projected.append(None)
            continue
        fog = 0.0 if z <= near else min(1.0, far * (z - near) / (z * (far - near)))
        projected.append((width / 2 + PROJECTION * k * (p[0] * r[0] + p[1] * r[1] + p[2] * r[2]) / z,
                          height / 2 + PROJECTION * k * (p[0] * u[0] + p[1] * u[1] + p[2] * u[2]) / z, z, 1.0 - fog))
    shades = mdl.shades()
    faces = []
    for index, (uvs, clut, tpage, vertices, normals) in enumerate(mdl.polygons):
        points = [projected[i] if i < len(projected) else None for i in vertices]
        if any(p is None for p in points):
            continue
        for tri in ((0, 1, 2),) if len(vertices) == 3 else ((0, 1, 2), (1, 3, 2)):
            corners = []
            for i in tri:
                x, y, z, clear = points[i]
                light = shades[normals[i]] if normals[i] < len(shades) else 1.0
                corners.append((x, y, z, uvs[i] & 255, uvs[i] >> 8, light * clear))
            (xa, ya, _, _, _, _), (xb, yb, _, _, _, _), (xc, yc, _, _, _, _) = corners
            if (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya) <= 0:
                continue            # a back face (NCLIP)
            faces.append((corners, tpage, clut, _override(mdl, index, overrides)))
    out = bytearray(_rasterize(size, faces, mdl.vram))
    if spotlight:
        cx, cy, inner, outer, wide = SPOTLIGHT
        across = [(x / k + 0.5 - cx) / wide for x in range(width)]
        for y in range(height):
            down = y / k + 0.5 - cy
            for x in range(width):
                t = math.hypot(across[x], down)
                if t <= inner:
                    continue
                cut = 255 * min(1.0, (t - inner) / (outer - inner))
                o = (y * width + x) * 4
                for c in range(3):
                    out[o + c] = max(0, int(out[o + c] - cut))
    return pngio.Image(width, height, bytes(out))


def render_top(mdl: MapModel, centre, span: float, size, overrides=None) -> pngio.Image:
    """The map from straight above, turned as the world's cameras mostly
    look: +z to the right, -x up; `span` world units across the picture's
    shorter side, `centre` its middle (x, z)."""
    width, height = size
    scale = min(width, height) / span
    cx, cz = centre
    shades = mdl.shades()
    points = []
    for w in mdl.points():
        points.append((width / 2 + (w[2] - cz) * scale, height / 2 + (w[0] - cx) * scale, w[1]))
    faces = []
    for index, (uvs, clut, tpage, vertices, normals) in enumerate(mdl.polygons):
        if any(i >= len(points) for i in vertices):
            continue
        for tri in ((0, 1, 2),) if len(vertices) == 3 else ((0, 1, 2), (1, 3, 2)):
            corners = [(points[vertices[i]][0], points[vertices[i]][1], points[vertices[i]][2], uvs[i] & 255,
                        uvs[i] >> 8, shades[normals[i]] if normals[i] < len(shades) else 1.0) for i in tri]
            faces.append((corners, tpage, clut, _override(mdl, index, overrides)))
    return pngio.Image(width, height, _rasterize(size, faces, mdl.vram))
