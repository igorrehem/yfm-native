"""A synthetic campaign map for the tests: two overworld packages at the
retail sectors of a made-up WA_MRG.MRG, each with a module identifier, a
location table, a display resource bank, a sprite strip, palettes and a
small HMD. No byte of the game is in here."""
from __future__ import annotations

import struct

from fm_editor import campaign_map as cm
from fm_editor.campaign_map import Exit, Location
from fm_editor.tests import fixtures

SECTOR = 2048
NAMES = {0x350 + i: f"Place {chr(65 + i)}" for i in range(16)}
STRIP_COLOR = 0x03E0          # green, the palette entry the strip's texels use
TEXTURE_COLOR = 0x7C00        # blue, the HMD texture's


def locations() -> list:
    out = []
    for i in range(cm.COUNT):
        loc = Location(gate=0, pitch=480, heading=2048, distance=1000 + i, target_x=100 * i - 500,
                       target_z=50 * i, marker_x=40 + 10 * i if i >= cm.TOWN_FIRST else 0,
                       marker_y=60 + 5 * i if i >= cm.TOWN_FIRST else 0, confirm=0, pad=0x80 if i >= 10 else 0)
        nxt, back = (i + 1) % cm.COUNT, (i - 1) % cm.COUNT
        loc.exits = [Exit(0, 300, 120, 0x2000, 0, nxt, 16, 0), Exit(0, 24, 120, 0x8000, 4, back, 16, 0),
                     Exit(), Exit()]
        out.append(loc)
    out[3].exits[2] = Exit(0x8054, 160, 200, 0x4000, 2, 7, 24, 0)
    return out


def resource_bank() -> bytes:
    """Levels: [2] -> animations [8, 10, 12] -> variants; animation 0 (the
    panel) and 1 (the marker) one each, animation 2 eight arrows: 0 a
    frame, 4 its mirror (0xFB), the rest the same frame."""
    bank = bytearray(SECTOR)
    struct.pack_into("<H", bank, 0, 2)
    struct.pack_into("<3H", bank, 2, 8, 10, 12)
    streams = 64
    struct.pack_into("<H", bank, 8, streams)          # panel
    struct.pack_into("<H", bank, 10, streams + 3)     # marker
    for variant in range(8):
        struct.pack_into("<H", bank, 12 + variant * 2, streams + (10 if variant == 4 else 6))
    frames = 128
    # streams: (duration, u16 frame)
    bank[streams:streams + 3] = bytes([0]) + struct.pack("<H", frames)
    bank[streams + 3:streams + 6] = bytes([0]) + struct.pack("<H", frames + 10)
    bank[streams + 6:streams + 9] = bytes([4]) + struct.pack("<H", frames + 20)
    bank[streams + 9] = 0xFE                                  # loop
    bank[streams + 10:streams + 13] = bytes([0xFB]) + struct.pack("<H", streams + 6)
    # frames: count, flags, page, palette step; parts dx, dy, cell, size
    def frame(at, dx, dy, u, v, w, h):
        bank[at:at + 4] = bytes([1, 0, 0, 0])
        cell = (u // 8) | ((v // 8) << 5)
        size = ((w // 8 - 1) << 5) | ((h // 8 - 1) << 9)
        struct.pack_into("<bbHH", bank, at + 4, dx, dy, cell, size)
    frame(frames, -64, -8, 0, 0, 128, 16)       # panel
    frame(frames + 10, -16, -16, 0, 32, 32, 32)  # marker
    frame(frames + 20, -4, -8, 64, 64, 16, 16)   # arrow: left 12 columns painted, right 4 clear
    return bytes(bank)


def strip() -> bytes:
    """256x256 texels at four bits: index 1 where the frames are painted
    (the arrow only in its left 12 columns, to see the mirror)."""
    data = bytearray(16 * SECTOR)

    def paint(u0, v0, w, h):
        for v in range(v0, v0 + h):
            for u in range(u0, u0 + w):
                at = v * 128 + u // 2
                data[at] |= (1 << 4) if u & 1 else 1
    paint(0, 0, 128, 16)
    paint(0, 32, 32, 32)
    paint(64, 64, 12, 16)
    return bytes(data)


def palettes() -> bytes:
    data = bytearray(SECTOR)
    struct.pack_into("<H", data, 2, STRIP_COLOR)     # palette 0, entry 1
    return bytes(data)


def hmd() -> bytes:
    """A small map: one texture (32x64 words at VRAM 0,256, all index 1)
    with its palette (0,240), and one quad 800 units square at the origin
    facing up (y down), under an identity coordinate."""
    words = [0] * 8192

    def put(at, values):
        for i, v in enumerate(values):
            words[at + i] = v & 0xFFFFFFFF
    header_section = 16
    coords = 32                  # count, then one GsCOORDUNIT (21 words)
    vertices = 64
    normals = 80
    polygons = 96
    images = 128
    cluts = 128 + 1024
    image_block = 1400
    terrain_block = 1300
    put(0, [0x50, 0, header_section, 2, image_block, terrain_block])
    # primitive header section: 2 headers
    put(header_section, [2, 4, 0x80000000 | polygons, 0x80000000 | vertices, 0x80000000 | normals,
                         0x80000000 | coords, 2, 0x80000000 | images, 0x80000000 | cluts])
    put(coords, [1, 0])          # one unit, flg 0; the rest (matrix, t, rot, super) zero
    s = 400
    corners = [(-s, 0, -s), (-s, 0, s), (s, 0, -s), (s, 0, s)]    # front-facing from above
    for i, (x, y, z) in enumerate(corners):
        put(vertices + i * 2, [(x & 0xFFFF) | ((y & 0xFFFF) << 16), z & 0xFFFF])
    put(normals, [(0 & 0xFFFF) | ((-4096 & 0xFFFF) << 16), 0])
    # the quad: uv0, clut, uv1, tpage, uv2, n0, uv3, v0, n1, v1, n2, v2, n3, v3 (tpage 0x10: 0,256 four bits)
    halves = [0x0000, 240 << 6, 0x007F, 0x0010, 0x3F00, 0, 0x3F7F, 0, 0, 1, 0, 2, 0, 3]
    for i in range(0, 14, 2):
        put(polygons + i // 2, [halves[i] | (halves[i + 1] << 16)])
    for i in range(32 * 64 // 2):
        words[images + i] = 0x11111111      # index 1 everywhere
    words[cluts] = TEXTURE_COLOR << 16     # entry 0 clear, entry 1 blue
    # image block: next, header, count; GsU_02000001 with 1 image and its palette
    put(image_block, [0xFFFFFFFF, header_section + 6, 0x80000001, 0x02000001, 0x80010007,
                      0 | (256 << 16), 32 | (64 << 16), 0, 0 | (240 << 16), 256 | (1 << 16), 0])
    # terrain block: one type of quads, one quad
    put(terrain_block, [0xFFFFFFFF, header_section + 1, 0x80000001, 0x00020015, 0x80010002, 0])
    return b"".join(struct.pack("<I", w) for w in words)


def add_packages(wa: bytes, table=None) -> bytes:
    """`wa` grown to hold both overworld packages, the same in each."""
    table = cm.pack_table(table or locations())
    size = (cm.PACKAGES[-1][1] + cm.PACKAGE_SECTORS) * SECTOR
    data = bytearray(wa) + bytes(max(0, size - len(wa)))
    for _, sector in cm.PACKAGES:
        base = sector * SECTOR
        struct.pack_into("<I", data, base, cm.MODULE_IDENTIFIER)
        data[base + cm.TABLE_OFFSET:base + cm.TABLE_OFFSET + len(table)] = table
        model = hmd()
        data[base + 6 * SECTOR:base + 6 * SECTOR + len(model)] = model
        data[base + 140 * SECTOR:base + 141 * SECTOR] = resource_bank()
        data[base + 141 * SECTOR:base + 157 * SECTOR] = strip()
        data[base + 157 * SECTOR:base + 158 * SECTOR] = palettes()
    return bytes(data)


class MapFixture(fixtures.Fixture):
    """The synthetic game with a campaign map and its place names."""

    def __init__(self):
        super().__init__()
        self.other_names = {**self.other_names, **NAMES}
        self.slus = fixtures.make_slus(self.cards, self.other_names)
        self.wa = add_packages(self.wa)


_FIXTURE = None


def map_fixture() -> MapFixture:
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = MapFixture()
    return _FIXTURE
