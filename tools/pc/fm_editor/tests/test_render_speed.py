"""The 3D renders' speed-ups keep their pictures: the rasterizer
(map_view.raster_steps), the board's outline (board_model.outline) and its
pieces' pictures (board_art.piece_image) against the plain code they
replaced, kept here as it was, on random triangles, the board and the
campaign map at many cameras and sizes, pixel for pixel; and the UI tab's
Duel board page drawing a field soon after the click, the full picture
after, without holding the window.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import contextlib
import random
import time
import unittest
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fm_editor import board_art as ba, board_model as bm, campaign_map as cm, map_view as mv, pngio
from fm_editor.model import Project
from fm_editor.pngio import Image
from fm_editor.tests import map_fixture as mf, test_board_art as tba
from fm_editor.tests.test_gui import GuiCase

ROOT = Path(__file__).resolve().parents[4]
GAME_WA = ROOT / "game" / "DATA" / "WA_MRG.MRG"


# --- the code replaced, as it was (2026-10-07) ----------------------------------------------

def reference_texel(vram, tpage, clut, u, v):
    """The color word a polygon's texture has at u, v; None where clear."""
    px, py, depth = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256, (tpage >> 7) & 3
    if depth == 0:
        index = (vram[(py + v) * 1024 + px + (u >> 2)] >> ((u & 3) * 4)) & 15
    elif depth == 1:
        index = (vram[(py + v) * 1024 + px + (u >> 1)] >> ((u & 1) * 8)) & 255
    else:
        word = vram[((py + v) & 511) * 1024 + ((px + u) & 1023)]
        return None if word == 0 else word
    word = vram[(clut >> 6) * 1024 + (clut & 63) * 16 + index]
    # The game uploads every palette entry but the first with the
    # semi-transparency bit set: only a zero first entry is clear.
    return None if index == 0 and word == 0 else word


def reference_rasterize(size, faces, vram, out, depth, ids=None):
    """Draw faces: ((x, y, z, u, v, shade) * 3, tpage, clut, override[, id]),
    nearest z first kept; shade multiplies the texel. `ids` (a byte per
    pixel) takes the drawn face's id."""
    width, height = size
    for face in faces:
        corners, tpage, clut, override = face[:4]
        tag = face[4] if ids is not None else 0
        (x0, y0, z0, u0, v0, s0), (x1, y1, z1, u1, v1, s1), (x2, y2, z2, u2, v2, s2) = corners
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if area == 0:
            continue
        inv = 1.0 / area
        left, right = max(int(min(x0, x1, x2)), 0), min(int(max(x0, x1, x2)) + 1, width - 1)
        top, bottom = max(int(min(y0, y1, y2)), 0), min(int(max(y0, y1, y2)) + 1, height - 1)
        for y in range(top, bottom + 1):
            yy = y + 0.5
            for x in range(left, right + 1):
                xx = x + 0.5
                a = ((x1 - xx) * (y2 - yy) - (x2 - xx) * (y1 - yy)) * inv
                b = ((x2 - xx) * (y0 - yy) - (x0 - xx) * (y2 - yy)) * inv
                c = 1.0 - a - b
                if a < 0 or b < 0 or c < 0:
                    continue
                z = a * z0 + b * z1 + c * z2
                at = y * width + x
                if z >= depth[at]:
                    continue
                tu, tv = int(a * u0 + b * u1 + c * u2) & 255, int(a * v0 + b * v1 + c * v2) & 255
                if override is not None:
                    rgba, iw, ih, ox, oy, tw, th = override
                    ix = min(iw - 1, max(0, (tu - ox) * iw // tw))
                    iy = min(ih - 1, max(0, (tv - oy) * ih // th))
                    p = (iy * iw + ix) * 4
                    if rgba[p + 3] < 128:
                        continue
                    red, green, blue = rgba[p], rgba[p + 1], rgba[p + 2]
                else:
                    word = reference_texel(vram, tpage, clut, tu, tv)
                    if word is None:
                        continue
                    red, green, blue = (word & 31) * 8, ((word >> 5) & 31) * 8, ((word >> 10) & 31) * 8
                depth[at] = z
                if ids is not None:
                    ids[at] = tag
                shade = a * s0 + b * s1 + c * s2
                o = at * 4
                out[o] = min(255, int(red * shade))
                out[o + 1] = min(255, int(green * shade))
                out[o + 2] = min(255, int(blue * shade))
                out[o + 3] = 255


def reference_outline(picture: bm.Picture, keys, thickness: int = 1, color=(0x40, 0xE0, 0xFF), dark=(0, 0, 0)) -> pngio.Image:
    """The picture with the edge of what `keys` cover drawn round: a line
    of `color` `thickness` pixels wide inside it and one of `dark`
    outside."""
    image = picture.image
    width, height = image.width, image.height
    wanted = {picture.keys.index(k) + 1 for k in keys if k in picture.keys}
    mask = picture.ids.translate(bytes(1 if i in wanted else 0 for i in range(256)))
    out = bytearray(image.rgba)
    if not wanted or 1 not in mask:
        return Image(width, height, bytes(out))
    # A row at a time, a byte a pixel as one number: a pixel of the mask is
    # on its edge when a neighbour (or the picture's edge) is not.
    ones = int.from_bytes(b"\1" * width, "big")
    rows = [int.from_bytes(mask[y * width:(y + 1) * width], "big") for y in range(height)]
    edges = []
    for y, row in enumerate(rows):
        if not row:
            continue
        above = rows[y - 1] if y > 0 else 0
        below = rows[y + 1] if y + 1 < height else 0
        outside = (ones ^ (row >> 8)) | (ones ^ (row << 8 & (ones * 255))) | (ones ^ above) | (ones ^ below) | 1 | 1 << 8 * (width - 1)
        line = (row & outside).to_bytes(width, "big")
        x = line.find(1)
        while x >= 0:
            edges.append((x, y))
            x = line.find(1, x + 1)
    inner, outer = bytes(color), bytes(dark)
    reach = range(-thickness, thickness + 1)
    for x, y in edges:
        for dy in reach:
            ny = y + dy
            if not 0 <= ny < height:
                continue
            for dx in reach:
                nx = x + dx
                if 0 <= nx < width:
                    at = ny * width + nx
                    if mask[at]:
                        if abs(dx) < thickness and abs(dy) < thickness:
                            out[at * 4:at * 4 + 3] = inner
                    else:
                        out[at * 4:at * 4 + 3] = outer
    return Image(width, height, bytes(out))


def reference_piece_image(data, terrain: str, part, tint: int = ba.WHITE) -> Image:
    """A piece as the game draws it at the console's resolution, through
    its palette (tinted): a color word of 0 is clear."""
    blob = data.phases[terrain]
    palette = [ba.color(w) for w in ba.tinted(ba.palette_words(data, terrain, part), tint)]
    base = part.column * ba.COLUMN_BYTES
    out = bytearray(part.w * part.h * 4)
    for y in range(part.h):
        row = base + (part.y + y) * ba.ROW_BYTES
        for x in range(part.w):
            byte = blob[row + (part.x + x) // 2]
            index = byte >> 4 if (part.x + x) & 1 else byte & 15
            at = (y * part.w + x) * 4
            out[at:at + 4] = bytes(palette[index])
    return Image(part.w, part.h, bytes(out))


def reference_steps(size, faces, vram, pixels, ids=None, step=None):
    """map_view.raster_steps as the plain loop drew (at once)."""
    out = bytearray(b"".join(pixels))
    reference_rasterize(size, faces, vram, out, [1e30] * (size[0] * size[1]), ids)
    pixels[:] = [bytes(out[i:i + 4]) for i in range(0, len(out), 4)]
    return
    yield


@contextlib.contextmanager
def plain():
    """The renders as the replaced code drew them."""
    with mock.patch.object(mv, "raster_steps", reference_steps):
        yield


def both(make):
    """make()'s picture by the rasterizer and by the plain loop."""
    with plain():
        old = make()
    return make(), old


# --- the rasterizer ---------------------------------------------------------------------------

def random_vram(rng) -> array:
    vram = array("H", bytes(1024 * 512 * 2))
    for i in range(0, len(vram), 7):
        vram[i] = rng.randrange(65536)
    for i in range(0, len(vram), 3):
        vram[i] = 0                         # clear texels and palette entries among the rest
    return vram


def random_picture(rng, w, h) -> Image:
    out = bytearray()
    for _ in range(w * h):
        out += bytes((rng.randrange(256), rng.randrange(256), rng.randrange(256), rng.choice((0, 127, 128, 255))))
    return Image(w, h, bytes(out))


def random_faces(rng, size, count, pictures):
    """Triangles of every kind the rasterizer meets: big and small, slivers,
    off the picture, edges along a row or a column and corners on pixels'
    centres, overlapping, shades alike and not, the three texel depths and
    a mod's pictures."""
    width, height = size
    faces = []
    for i in range(count):
        kind = i % 6
        corners = []
        for _ in range(3):
            if kind == 0:
                x, y = rng.uniform(-40, width + 40), rng.uniform(-40, height + 40)
            elif kind == 1:
                x, y = rng.randrange(width) + 0.5, rng.randrange(height) + 0.5
            else:
                x, y = rng.uniform(0, width), rng.uniform(0, height)
            corners.append([x, y, rng.uniform(20, 900), rng.randrange(256), rng.randrange(256),
                            rng.uniform(0.0, 1.6)])
        if kind == 2:                               # an edge along a row
            corners[1][1] = corners[0][1]
        elif kind == 3:                             # a sliver
            corners[2][0], corners[2][1] = corners[0][0] + 0.01, corners[0][1] + rng.uniform(-30, 30)
        elif kind == 4:                             # lit alike
            for c in corners:
                c[5] = corners[0][5]
        elif kind == 5:                             # an edge along a column
            corners[1][0] = corners[0][0]
        if rng.random() < 0.5:
            corners.reverse()
        tpage = rng.randrange(16) | rng.randrange(2) << 4 | rng.randrange(3) << 7
        clut = rng.randrange(512) << 6 | rng.randrange(64)
        override = None
        if pictures and rng.random() < 0.4:
            image = rng.choice(pictures)
            ox, oy = rng.randrange(200), rng.randrange(200)
            override = (image.rgba, image.width, image.height, ox, oy, rng.randrange(8, 56), rng.randrange(8, 56))
        faces.append((tuple(tuple(c) for c in corners), tpage, clut, override, rng.randrange(1, 16)))
    return faces


class RasterTest(unittest.TestCase):
    def test_random_triangles(self):
        rng = random.Random(7)
        vram = random_vram(rng)
        pictures = [random_picture(rng, 16, 16), random_picture(rng, 64, 24), random_picture(rng, 3, 50)]
        for size, count in (((64, 48), 120), ((197, 131), 80), ((320, 240), 40)):
            faces = random_faces(rng, size, count, pictures)
            ids_new, ids_old = bytearray(size[0] * size[1]), bytearray(size[0] * size[1])
            new = mv._rasterize(size, faces, vram, (9, 8, 7), ids_new)
            out = bytearray(bytes((9, 8, 7, 255)) * (size[0] * size[1]))
            reference_rasterize(size, faces, vram, out, [1e30] * (size[0] * size[1]), ids_old)
            self.assertEqual(new, bytes(out), size)
            self.assertEqual(ids_new, ids_old, size)

    def test_texels(self):
        """The texture tables read what _texel read, VRAM and pictures."""
        rng = random.Random(11)
        vram = random_vram(rng)
        for _ in range(60):
            tpage = rng.randrange(16) | rng.randrange(2) << 4 | rng.randrange(3) << 7
            clut = rng.randrange(512) << 6 | rng.randrange(64)
            rows = mv._texture(vram, tpage, clut, None).rows
            for _ in range(40):
                u, v = rng.randrange(256), rng.randrange(256)
                word = reference_texel(vram, tpage, clut, u, v)
                texel = rows[v][u]
                if word is None:
                    self.assertIsNone(texel)
                else:
                    self.assertEqual(texel[:3], ((word & 31) * 8, ((word >> 5) & 31) * 8, ((word >> 10) & 31) * 8))

    def test_steps(self):
        """raster_steps pauses as it goes and draws what _rasterize does."""
        rng = random.Random(5)
        vram = random_vram(rng)
        size = (160, 120)
        faces = random_faces(rng, size, 30, [])
        pixels = [bytes((0, 0, 0, 255))] * (160 * 120)
        pauses = sum(1 for _ in mv.raster_steps(size, faces, vram, pixels, None, step=500))
        self.assertGreater(pauses, 5)
        self.assertEqual(b"".join(pixels), mv._rasterize(size, faces, vram))


# --- the board and the map, rendered ---------------------------------------------------------------

CAMERAS = [bm.CAMERA, (900, 1500, 500, 100, 50), (2000, 300, 900, 0, 0), (150, 0x400, 16, 0, 0),
           (600, 3000, 200, -400, 400), (1200, 0x400, 0x100, 0, 0)]


class BoardRenderTest(unittest.TestCase):
    """The fixture's board (test_board_art.paint_boards), its pictures the
    game's, tinted and replaced."""

    def test_renders(self):
        project = Project(tba.game())
        data = ba.disc(project)
        ba.set_tint(project, ["forest"], ba.FLOOR, 0x80A0FF)
        ba.set_piece(project, ["forest"], ba.BY_KEY["wall_middle"], random_picture(random.Random(2), 128, 128))
        for terrain in ("normal", "forest"):
            board, pieces = bm.board(data, terrain), bm.pieces_of(project, terrain)
            for camera in CAMERAS:
                for size in ((320, 240), (151, 77)):
                    new, old = both(lambda: bm.render(board, pieces, camera, size))
                    self.assertEqual(new.image.rgba, old.image.rgba, (terrain, camera, size))
                    self.assertEqual(new.ids, old.ids, (terrain, camera, size))

    def test_map(self):
        model = mv.MapModel(mv.model_blob(mf.map_fixture().wa, cm.PACKAGES[0][1]))
        for camera in ((1000, 0, 900, 0, 0), (300, 0, 1000, 0, 0), (800, 700, 300, 50, -80)):
            for spotlight in (False, True):
                new, old = both(lambda: mv.render(model, camera, spotlight))
                self.assertEqual(new.rgba, old.rgba, camera)
        new, old = both(lambda: mv.render_top(model, (0, 0), 1000, (100, 100)))
        self.assertEqual(new.rgba, old.rgba)


@unittest.skipUnless(GAME_WA.is_file(), "needs the game files in game/")
class DiscRenderTest(unittest.TestCase):
    """The disc's own board, every field, and its campaign map."""

    @classmethod
    def setUpClass(cls):
        cls.wa = GAME_WA.read_bytes()
        cls.data = ba.read(cls.wa)
        cls.project = SimpleNamespace(retail=SimpleNamespace(board=cls.data))

    def test_board(self):
        for index, terrain in enumerate(ba.TERRAINS):
            board, pieces = bm.board(self.data, terrain), bm.pieces_of(self.project, terrain)
            for camera in CAMERAS[index % 3::3] + [bm.CAMERA]:
                for size in ((320, 240), (533, 320)):
                    new, old = both(lambda: bm.render(board, pieces, camera, size))
                    self.assertEqual(new.image.rgba, old.image.rgba, (terrain, camera, size))
                    self.assertEqual(new.ids, old.ids, (terrain, camera, size))

    def test_board_full_size(self):
        """The page's full picture, as large as a big window makes it."""
        board, pieces = bm.board(self.data, "normal"), bm.pieces_of(self.project, "normal")
        new, old = both(lambda: bm.render(board, pieces, bm.CAMERA, (1600, 960)))
        self.assertEqual(new.image.rgba, old.image.rgba)
        self.assertEqual(new.ids, old.ids)

    def test_map(self):
        for sector in (cm.PACKAGES[0][1], cm.PACKAGES[1][1]):
            model = mv.model(self.wa, sector)
            for camera in ((1500, 0x400, 0x200, 0, 0), (900, 100, 300, 200, -100)):
                new, old = both(lambda: mv.render(model, camera, True))
                self.assertEqual(new.rgba, old.rgba, (sector, camera))
            new, old = both(lambda: mv.render_top(model, (0, 0), 4000, (320, 200)))
            self.assertEqual(new.rgba, old.rgba, sector)


class PictureTest(unittest.TestCase):
    def test_outline(self):
        """The chosen parts' outline, on the board and on random masks."""
        project = Project(tba.game())
        data = ba.disc(project)
        board, pieces = bm.board(data, "normal"), bm.pieces_of(project, "normal")
        pictures = [bm.render(board, pieces, camera, (320, 240)) for camera in CAMERAS[:3]]
        rng = random.Random(4)
        for size in ((40, 30), (7, 5), (1, 1), (90, 3)):
            ids = bytearray(rng.choice((0, 1, 1, 2)) for _ in range(size[0] * size[1]))
            image = Image(size[0], size[1], bytes(rng.randrange(256) for _ in range(size[0] * size[1] * 4)))
            pictures.append(bm.Picture(image, ids, bm.KEYS))
        for picture in pictures:
            for keys in ([p.key for p in ba.FLOOR], ["wall_middle"], ["opponent_back"], ["trim", "centre"], ["none"],
                         bm.KEYS):
                for thickness in (1, 2, 3, 5):
                    self.assertEqual(bm.outline(picture, keys, thickness).rgba,
                                     reference_outline(picture, keys, thickness).rgba, (keys, thickness))

    def test_piece_image(self):
        data = tba.game().board
        for terrain in ("normal", "umi"):
            for part in ba.PARTS:
                for tint in (ba.WHITE, 0x80A0FF, 0x000000):
                    self.assertEqual(ba.piece_image(data, terrain, part, tint).rgba,
                                     reference_piece_image(data, terrain, part, tint).rgba, (terrain, part.key))


# --- the Duel board page ------------------------------------------------------------------------

class PageTest(GuiCase):
    """The page on the fixture's boards: a field chosen shows a small
    picture at once and the full one after, drawn a little at a time;
    the other fields drawn ahead once the page is left alone."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wa = cls.game / "DATA" / "WA_MRG.MRG"
        wa.write_bytes(tba.paint_boards(wa.read_bytes()))

    def setUp(self):
        super().setUp()
        tab = self.app.ui
        self.app.notebook.select(tab)
        tab.page_name.set("board")
        tab.show_page()
        self.page = tab.pages["board"]
        self.settle()

    def settle(self, limit=20.0):
        """Tk's loop run until the page has nothing left to draw."""
        start = time.perf_counter()
        while (self.page._work is not None or self.page._job is not None) and time.perf_counter() - start < limit:
            self.app.update()
            time.sleep(0.002)
        self.app.update()

    def full(self, terrain):
        """The full picture as board_model draws it, for comparing."""
        page = self.page
        return bm.render(bm.board(ba.disc(page.project), terrain), bm.pieces_of(page.project, terrain), page.camera,
                         page.canvas_size())

    def test_field_switch(self):
        page = self.page
        self.assertEqual(page.scale, 1)
        page.field.set("umi")
        small_scale = page.drag_scale       # adapt may change it after the small picture is drawn
        page.choose_field()
        # At once: a small picture of the new field, the full one under way.
        self.assertEqual((page.terrain, page.scale), ("umi", small_scale))
        self.assertIsNotNone(page._work)
        small = page.picture.image.size
        self.assertEqual(small, tuple(max(1, n // page.scale) for n in page.canvas_size()))
        self.settle()
        self.assertEqual(page.scale, 1)
        self.assertEqual(page.picture.image.rgba, self.full("umi").image.rgba)
        # Seen once, a field comes back without being drawn again.
        page.field.set("normal")
        with mock.patch.object(bm, "render", side_effect=AssertionError("drawn again")), \
                mock.patch.object(bm, "render_steps", side_effect=AssertionError("drawn again")):
            page.choose_field()
        self.assertEqual((page.terrain, page.scale), ("normal", 1))

    def test_slices(self):
        """The full picture comes in many short steps, the window's events
        handled between them."""
        page = self.page
        steps = []
        real = page._step

        def step():
            steps.append(page._work is not None)
            real()
        with mock.patch.object(ui_board_module(), "SLICE", 0.0), mock.patch.object(page, "_step", step):
            page.field.set("forest")
            page.choose_field()
            self.settle()
        # More than one step at any canvas size (a small window has few rows to draw).
        self.assertGreater(len(steps), 1)
        self.assertEqual(page.picture.image.rgba, self.full("forest").image.rgba)

    def test_drawn_ahead(self):
        page = self.page
        with mock.patch.object(ui_board_module(), "AHEAD", 1):
            page.ahead_later(1)
            start = time.perf_counter()
            while time.perf_counter() - start < 30:
                self.app.update()
                if all(page.view_key(t) + (page.canvas_size(),) in page.pictures for t in ba.TERRAINS):
                    break
                time.sleep(0.002)
        self.assertEqual(len(page.pictures), len(ba.TERRAINS))
        page.field.set("yami")
        with mock.patch.object(bm, "render", side_effect=AssertionError("drawn again")):
            page.choose_field()
        self.assertEqual((page.terrain, page.scale), ("yami", 1))
        self.assertEqual(page.picture.image.rgba, self.full("yami").image.rgba)
        # An edit: the pictures before it are let go, the new one drawn.
        before = page.picture.image.rgba
        page.select("floor")
        page.set_tint(0x4080FF)
        self.settle()
        self.assertNotEqual(page.picture.image.rgba, before)
        self.assertEqual(page.picture.image.rgba, self.full("yami").image.rgba)
        self.assertEqual(len(page.pictures), 1)

    def test_adapt(self):
        """A machine slow to draw gets smaller pictures while the camera
        moves, a fast one larger; one slow picture does not decide it."""
        page = self.page
        scales = ui_board_module().DRAG_SCALES
        width, height = page.canvas_size()
        frame = ui_board_module().FRAME
        # Only the timings below: the page's own pictures on opening were
        # timed on this machine, as busy as it happened to be.
        page.rate = None

        def took(scale, rate):
            return rate * (width // scale) * (height // scale)
        quick = frame / (width * height)            # a full picture within a moving one's time
        page.adapt(3, took(3, quick))
        self.assertEqual(page.drag_scale, scales[0])
        page.adapt(2, took(2, quick * 1000))        # a slow one: smaller...
        self.assertGreater(page.drag_scale, scales[0])
        for _ in range(12):
            page.adapt(page.drag_scale, took(page.drag_scale, quick * 1000))
        self.assertEqual(page.drag_scale, scales[-1])
        for _ in range(12):                         # ...and back as it speeds up
            page.adapt(page.drag_scale, took(page.drag_scale, quick * 2))
        self.assertEqual(page.drag_scale, 2)
        self.assertLessEqual(took(2, page.rate), frame)


def ui_board_module():
    from fm_editor import ui_board
    return ui_board
