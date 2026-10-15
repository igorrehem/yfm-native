"""The duel board's textures (board_art.py), its model (board_model.py) and
the UI tab's Duel board page (ui_board.py) on boards painted here: where
each piece is (checked against the HD recipe's capture), the pack entries
and palette patches a mod gets, tints read back from their patches, saving
and opening again, the model drawn and picked from, and the page's own
controls (the camera on the middle button among them). With the game files
in game/, the disc's own model too.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import random
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fm_editor import board_art as ba, board_model as bm, gamedata, manifest, pngio, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture
from fm_editor.tests.test_gui import GuiCase

ROOT = Path(__file__).resolve().parents[4]
GAME_WA = ROOT / "game" / "DATA" / "WA_MRG.MRG"

# A board for the fixture, laid out as the game's (z far, y down): the floor's
# five rows at y 0 (the centre strip twice, the near half turned round), and
# four walls under its edges. (part, corners v0..v3 as the console's quads
# order them, normal); each quad's texture is its piece's whole rectangle.
HALF_W, DEPTH = 175, 55
ROWS = [("opponent_back", 127, 196), ("opponent_front", 60, 127), ("centre", 0, 60), ("centre", -60, 0),
        ("your_front", -127, -60), ("your_back", -196, -127)]
NORMALS = [(0, -4096, 0), (0, 0, -4096), (0, 0, 4096), (-4096, 0, 0), (4096, 0, 0)]


def board_quads():
    quads = []
    for key, near, far in ROWS:
        turned = key == "centre" and far == 0
        corners = [(-HALF_W, 0, far), (HALF_W, 0, far), (-HALF_W, 0, near), (HALF_W, 0, near)]
        quads.append((key, corners[::-1] if turned else corners, 0))
    w, d, z = HALF_W, DEPTH, 196
    quads.append(("wall_middle", [(-w, 0, -z), (w, 0, -z), (-w, d, -z), (w, d, -z)], 1))     # near, facing you
    quads.append(("wall_corners", [(w, 0, z), (-w, 0, z), (w, d, z), (-w, d, z)], 2))         # far
    quads.append(("wall_left", [(-w, 0, z), (-w, 0, -z), (-w, d, z), (-w, d, -z)], 3))
    quads.append(("wall_right", [(w, 0, -z), (w, 0, z), (w, d, -z), (w, d, z)], 4))
    return quads


def board_hmd() -> bytes:
    """board_quads() as the disc's board model is: an HMD with its size in
    the first word, one block of quads (0x00020015) and an identity
    coordinate."""
    words = [0] * (ba.MODEL_BYTES // 4)

    def put(at, values):
        for i, v in enumerate(values):
            words[at + i] = v & 0xFFFFFFFF
    header_section, coords, vertices, normals, polygons, block = 16, 32, 64, 240, 260, 900
    quads = board_quads()
    put(0, [0x21F4, 0, header_section, 3, 56, block, 0])
    put(56, [0xFFFFFFFF, header_section + 6, 0x80000000])          # block 0: no images
    put(header_section, [2, 4, 0x80000000 | polygons, 0x80000000 | vertices, 0x80000000 | normals,
                         0x80000000 | coords, 0])
    put(coords, [1, 0, 0x1000, 0, 0x1000, 0, 0x1000])
    points = [c for _, corners, _ in quads for c in corners]
    for i, (x, y, z) in enumerate(points):
        put(vertices + i * 2, [(x & 0xFFFF) | ((y & 0xFFFF) << 16), z & 0xFFFF])
    for i, (x, y, z) in enumerate(NORMALS):
        put(normals + i * 2, [(x & 0xFFFF) | ((y & 0xFFFF) << 16), z & 0xFFFF])
    for q, (key, _, normal) in enumerate(quads):
        part = ba.BY_KEY[key]
        u0, v0, u1, v1 = part.x, part.y, part.x + part.w - 1, part.y + part.h - 1
        tpage = 10 + part.column | 1 << 4
        uv = [u0 | v0 << 8, u1 | v0 << 8, u0 | v1 << 8, u1 | v1 << 8]
        n = 4 * q
        halves = [uv[0], bm.clut_word(part.column, part.palette), uv[1], tpage, uv[2], normal, uv[3], n,
                  normal, n + 1, normal, n + 2, normal, n + 3]
        for i in range(0, 14, 2):
            put(polygons + q * 7 + i // 2, [halves[i] | (halves[i + 1] << 16)])
    put(block, [0xFFFFFFFF, header_section + 1, 0x80000001, 0x00020015, 0x80000002 | len(quads) << 16, 0])
    return b"".join(struct.pack("<I", w) for w in words)


def paint_boards(wa: bytes) -> bytes:
    """Each field's board: texel (x, y) of a column is (x + y + field) % 15 + 1,
    every palette's color i a mix of the field, the palette and i; its
    model board_hmd()."""
    data = bytearray(wa)
    for t_index, terrain in enumerate(ba.TERRAINS):
        start = ba.phase_offset(terrain)
        for column in range(2):
            for y in range(256):
                for x in range(0, 256, 2):
                    lo, hi = ((x + y + t_index) % 15 + 1), ((x + 1 + y + t_index) % 15 + 1)
                    data[start + column * ba.COLUMN_BYTES + y * 128 + x // 2] = lo | hi << 4
        for p_index, part in enumerate(ba.PARTS):
            at = start + part.palette
            for i in range(16):
                word = 0 if i == 0 else ((i * 2) & 31) | ((p_index + 3 * t_index) % 32) << 5 | (31 - i) << 10
                if i == 15:
                    word |= 0x8000
                data[at + 2 * i:at + 2 * i + 2] = word.to_bytes(2, "little")
        at = (ba.FIRST_SECTOR + t_index * ba.PACKAGE_SECTORS + ba.MODEL_SECTOR) * ba.SECTOR
        data[at:at + ba.MODEL_BYTES] = board_hmd()
    return bytes(data)


_game = None


def game():
    global _game
    if _game is None:
        f = fixture()
        _game = gamedata.read_game(f.slus, paint_boards(f.wa))
    return _game


def project() -> Project:
    p = Project(game())
    p.info.id = "boardmod"
    return p


def solid(width, height, color=(200, 40, 40, 255)):
    return pngio.Image(width, height, bytes(color) * (width * height))


class WhereTest(unittest.TestCase):
    def test_against_the_hd_recipe(self):
        """The recipe's floor bands and wall readings (captured from a duel)
        are the pieces' rectangles, offsets and palettes on every field."""
        recipe = json.loads((ROOT / "tools/pc/hd_recipes/duel.json").read_text(encoding="utf-8"))
        names = dict(zip(("normal", "forest", "wasteland", "mountain", "meadow", "sea", "dark"), ba.TERRAINS))
        checked = 0
        for sheet in recipe["sheets"]:
            field, _, what = sheet["what"].partition(" field: ")
            if field not in names or not what.startswith(("floor tiles", "the platform's sides")):
                continue
            terrain = names[field]
            palette = int(sheet["palette"], 16) - ba.phase_offset(terrain)
            part = next(p for p in ba.PARTS if p.palette == palette)
            column_start = ba.phase_offset(terrain) + part.column * ba.COLUMN_BYTES
            self.assertEqual(int(sheet["offset"], 16), column_start, sheet["what"])
            for x, y, w, h in sheet["rects"]:
                self.assertTrue(part.x <= x and x + w <= part.x + part.w and part.y <= y and y + h <= part.y + part.h,
                                f"{sheet['what']}: {x, y, w, h} outside {part.label}")
            checked += 1
        self.assertEqual(checked, 7 * 15)

    def test_pieces_share_no_word(self):
        for column in (0, 1):
            cells = set()
            for part in (p for p in ba.PARTS if p.column == column):
                mine = {(x // 4, y) for x in range(part.x, part.x + part.w) for y in range(part.y, part.y + part.h)}
                self.assertFalse(cells & mine, part.label)
                cells |= mine
                self.assertEqual(part.x % 4, 0)
                self.assertEqual(part.w % 4, 0)
            # The palettes are words of the phase no piece covers.
            for part in ba.PARTS:
                at = part.palette - column * ba.COLUMN_BYTES
                if 0 <= at < ba.COLUMN_BYTES:
                    self.assertNotIn(((at % 128) // 2, at // 128), cells)

    def test_entry(self):
        part = ba.BY_KEY["wall_right"]
        entry = ba.entry("forest", part, "board/forest/wall_right.png")
        base = (0x16C6 + 235 + 203) * 2048
        self.assertEqual((entry["offset"], entry["words"], entry["rows"], entry["stride"], entry["clut_offset"]),
                         (base + 0x8000 + 128 // 2, 32, 64, 64, base + 0xF140))


class TintTest(unittest.TestCase):
    def test_word(self):
        self.assertEqual(ba.tint_word(0, 0x000000), 0)                 # clear stays clear
        self.assertEqual(ba.tint_word(0x7FFF, 0xFFFFFF), 0x7FFF)
        self.assertEqual(ba.tint_word(0x801F, 0x000000), 0x8000)       # black, with the bit
        self.assertEqual(ba.tint_word(0x001F, 0x00FFFF), 0x0001)       # black without it
        self.assertEqual(ba.tint_word(0x7FFF, 0xFF8000), 31 | 16 << 5)

    def test_read_back(self):
        rng = random.Random(3)
        for trial in range(300):
            retail = [0] + [rng.randrange(1, 65536) for _ in range(15)]
            if trial % 3 == 0:
                retail = [0] + [rng.randrange(1, 32) | rng.choice((0, 0x8000)) for _ in range(15)]
            words = ba.tinted(retail, rng.randrange(0x1000000))
            found = ba.recover_tint(retail, words)
            self.assertIsNotNone(found)
            self.assertEqual(ba.tinted(retail, found), words)
            self.assertEqual(ba.recover_tint(retail, ba.tinted(retail, found)), found)
        self.assertIsNone(ba.recover_tint([0, 0x0421, 0x0842], [0, 0x0421, 0x0400]))


class ModTest(unittest.TestCase):
    def test_piece_image(self):
        data = game().board
        part = ba.BY_KEY["opponent_front"]
        image = ba.piece_image(data, "normal", part)
        self.assertEqual(image.size, (256, 52))
        index = (0 + 52 + 0) % 15 + 1
        word = ((index * 2) & 31) | 1 << 5 | (31 - index) << 10
        self.assertEqual(image.pixel(0, 0), ba.color(word))

    def test_floor_split_and_joined(self):
        p = project()
        image = pngio.Image(512, 508, bytes(b for y in range(508) for x in range(512)
                                            for b in (y // 2 % 256, x // 2, 90, 255)))
        self.assertEqual(ba.set_floor(p, ["sogen"], image), [])
        rows = {k: v.image for (t, k), v in ba.state(p).pictures.items() if t == "sogen"}
        self.assertEqual(rows["opponent_back"].size, (512, 104))
        self.assertEqual(rows["centre"].size, (512, 92))
        self.assertEqual(rows["centre"].pixel(0, 0)[0], 104)            # the third row of the picture
        self.assertEqual(ba.floor_image(p, "sogen"), image)

    def test_saved_and_opened_again(self):
        p = project()
        ba.set_floor(p, ["normal"], solid(256, 254))
        self.assertEqual(ba.set_piece(p, list(ba.TERRAINS), ba.BY_KEY["trim"], solid(300, 40)),
                         ["300x40 is not 128x16's shape: stretched to fit"])
        ba.set_tint(p, ["forest"], ba.FLOOR, 0x8080FF)
        ba.set_tint(p, list(ba.TERRAINS), [ba.BY_KEY["wall_middle"]], 0xFF4040)
        self.assertIsNotNone(ba.common_tint(p, "forest", ba.FLOOR))
        p.other["data"] = [{"file": ba.ARCHIVE_FILE, "patch": [{"at": "0x10", "bytes": "01 02"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "m"
            manifest.save_mod(p, folder)
            written = json.loads((folder / "mod.json").read_text(encoding="utf-8"))
            entries = json.loads((folder / "textures" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(entries), 5 + 7)
            self.assertEqual({e["file"] for e in entries if e["offset"] in
                              {ba.image_offset(t, ba.BY_KEY["trim"]) for t in ba.TERRAINS}}, {"board/all/trim.png"})
            self.assertTrue((folder / "textures" / "board" / "all" / "trim.png").is_file())
            self.assertEqual(written["data"][0]["patch"], [{"at": "0x10", "bytes": "01 02"}])
            ours = written["data"][1]["patch"]
            self.assertTrue(all(any(ba.palette_offset(t, q) <= int(run["at"], 16) < ba.palette_offset(t, q) + 32
                                    for t in ba.TERRAINS for q in ba.PARTS) for run in ours))
            opened, messages = manifest.open_mod(game(), folder)
            self.assertEqual(messages, [])
            # The same palettes, and the same tints on the page (a piece's own
            # reading of its patch may differ from the one set with others).
            self.assertEqual(ba.patches(opened), ba.patches(p))
            self.assertEqual(set(ba.state(opened).tints), set(ba.state(p).tints))
            for terrain in ba.TERRAINS:
                for parts in [ba.FLOOR] + [[q] for q in ba.PARTS]:
                    self.assertEqual(ba.common_tint(opened, terrain, parts), ba.common_tint(p, terrain, parts))
            self.assertEqual(ba.digest(opened), ba.digest(p))
            self.assertEqual(opened.other["data"],
                             [{"file": ba.ARCHIVE_FILE, "patch": [{"at": "0x10", "bytes": "01 02"}]}])
            self.assertFalse([str(i) for i in validate.validate(opened) if i.area in ("UI", "Art")])
            again = Path(tmp) / "m2"
            manifest.save_mod(opened, again)
            self.assertEqual((again / "mod.json").read_text(encoding="utf-8"),
                             (folder / "mod.json").read_text(encoding="utf-8"))
            self.assertEqual((again / "textures" / "manifest.json").read_text(encoding="utf-8"),
                             (folder / "textures" / "manifest.json").read_text(encoding="utf-8"))

    def test_a_palette_patch_that_is_no_tint_stays(self):
        p = project()
        part = ba.BY_KEY["centre_step"]
        at = ba.palette_offset("umi", part) + 2
        p.other["data"] = [{"file": ba.ARCHIVE_FILE, "patch": [{"at": f"0x{at:X}", "bytes": "FF 7F"}]}]
        messages = ba.read_patches(p)
        self.assertEqual(len(messages), 1)
        self.assertIn("is no tint", messages[0])
        self.assertEqual(ba.state(p).tints, {})
        self.assertEqual(len(p.other["data"][0]["patch"]), 1)

    def test_checks(self):
        p = project()
        ba.set_piece(p, ["yami"], ba.BY_KEY["wall_corners"], solid(64, 64, (0, 0, 0, 0)))
        ba.state(p).tints[("yami", "wall_corners")] = 0x808080
        issues = [i.message for i in validate.validate(p) if i.area == "UI"]
        self.assertTrue(any("tint shows nowhere" in m for m in issues), issues)
        self.assertTrue(any("see-through" in m for m in issues), issues)


def centre_of(key, quads=None):
    """The middle of a fixture quad of the piece (the first one)."""
    corners = next(c for k, c, _ in (quads or board_quads()) if k == key)
    return tuple(sum(c[i] for c in corners) / 4 for i in range(3))


class ModelTest(unittest.TestCase):
    def test_read_from_the_package(self):
        data = game().board
        self.assertEqual(set(data.models), set(ba.TERRAINS))
        board = bm.board(data, "forest")
        self.assertEqual(board.parts, [k for k, _, _ in board_quads()])
        self.assertEqual(board.points[:8], [tuple(map(float, c)) for _, cs, _ in board_quads()[:2] for c in cs])
        self.assertIs(bm.board(data, "forest"), board)            # parsed once
        # Every palette word names its piece's palette in VRAM (640, 256 on).
        self.assertEqual(bm.clut_word(0, 0x7F00), 510 << 6 | 640 >> 4)
        self.assertEqual(bm.clut_word(1, 0xF1A0), 483 << 6 | 720 >> 4)

    def test_render_board(self):
        """The picture alone, no Tk: the game's screen at 320x240, the mod's
        textures in it, kept until they change."""
        p = project()
        image = bm.render_board(p)
        self.assertEqual(image.size, (320, 240))
        self.assertIs(bm.render_board(p, "normal", None, (320, 240)), image)
        self.assertEqual(bm.render_board(p, camera=bm.CAMERA), image)
        # The near wall faces the duel's camera, under the floor's near edge.
        x, y, _ = bm.projector(None)(centre_of("wall_middle"))
        self.assertTrue(0 < x < 320 and 0 < y < 240)
        before = image.pixel(int(x), int(y))
        ba.set_piece(p, ["normal"], ba.BY_KEY["wall_middle"], solid(64, 64, (0, 200, 0, 255)))
        after = bm.render_board(p)
        r, g, b, _ = after.pixel(int(x), int(y))
        self.assertTrue(g > 100 and r < 30 and b < 30, (r, g, b))           # lit from the side
        self.assertNotEqual(before, after.pixel(int(x), int(y)))
        self.assertIs(bm.render_board(p), after)
        pieces = bm.pieces_of(p, "normal")
        self.assertIs(bm.pieces_of(p, "normal"), pieces)
        ba.set_tint(p, ["normal"], [ba.BY_KEY["wall_middle"]], 0x808080)     # an edit: drawn again
        self.assertIsNot(bm.pieces_of(p, "normal"), pieces)
        self.assertEqual(bm.render_board(p, "forest").size, (320, 240))
        self.assertEqual(bm.render_board(p, size=(640, 360)).size, (640, 360))
        self.assertIsNone(bm.render_board(Project(gamedata.GameData())))

    def test_picking_from_several_cameras(self):
        """Each pixel says which piece it shows: the middle of each face the
        camera sees is that face's piece, a face it cannot see is not."""
        board = bm.board(game().board, "normal")
        pieces = bm.pieces_of(project(), "normal")
        cameras = {"game": None, "behind": (600, 0xC00, 0x100, 0, 0), "left": (550, 0x000, 0x180, 0, 0),
                   "above": (500, 0x400, 0x3F0, 0, 0), "right": (700, 0x800, 0x80, 40, -30)}
        seen = {"game": ["wall_middle", "your_back", "your_front", "opponent_front"],
                "behind": ["wall_corners", "opponent_back"],
                "left": ["wall_left", "opponent_back", "your_back"],
                "above": ["opponent_back", "opponent_front", "your_front", "your_back"],
                "right": ["wall_right", "your_back"]}
        hidden = {"game": ["wall_corners"], "behind": ["wall_middle"], "left": ["wall_right"],
                  "above": ["wall_middle", "wall_left"], "right": ["wall_left"]}
        for name, camera in cameras.items():
            for size in ((320, 240), (500, 260)):
                picture = bm.render(board, pieces, camera, size)
                to_screen = bm.projector(camera, size)
                for key in seen[name]:
                    x, y, _ = to_screen(centre_of(key))
                    self.assertEqual(picture.part_at(int(x), int(y)), key, (name, size, key))
                for key in hidden[name]:
                    self.assertNotIn(bm.KEYS.index(key) + 1, picture.ids, (name, key))
                self.assertIsNone(picture.part_at(-1, 0))

    def test_outline(self):
        board = bm.board(game().board, "normal")
        picture = bm.render(board, bm.pieces_of(project(), "normal"))
        drawn = bm.outline(picture, ["wall_middle"])
        changed = [i // 4 for i in range(0, len(drawn.rgba), 4) if drawn.rgba[i:i + 3] != picture.image.rgba[i:i + 3]]
        self.assertTrue(changed)
        index = bm.KEYS.index("wall_middle") + 1
        self.assertTrue(all(picture.ids[at] == index or any(picture.ids[n] == index for n in
                                                            (at - 1, at + 1, at - 320, at + 320) if 0 <= n < 76800)
                            for at in changed))
        self.assertEqual(bm.outline(picture, []).rgba, picture.image.rgba)

    def test_camera_limits(self):
        camera = bm.CAMERA
        down = bm.orbit(camera, 0, 10000)
        self.assertEqual(down[2], bm.PITCH_RANGE[1])
        up = bm.orbit(camera, 0, -10000)
        self.assertEqual(up[2], bm.PITCH_RANGE[0])
        self.assertGreater(up[2], 0)                                 # never under the floor
        self.assertEqual(bm.orbit(camera, 4096 / 8, 0)[1], (camera[1] - 4096) % 4096)
        self.assertEqual(bm.orbit(camera, 64, 0)[1], camera[1] - 512)
        self.assertEqual(bm.zoom(camera, 100)[0], bm.DISTANCE_RANGE[0])
        self.assertEqual(bm.zoom(camera, -100)[0], bm.DISTANCE_RANGE[1])
        far = bm.pan(camera, 100000, 100000)
        self.assertEqual({abs(far[3]), abs(far[4])}, {bm.TARGET_RANGE})
        # A pan across moves the target across the screen: the board's
        # middle follows the mouse.
        moved = bm.pan(camera, -20, 0)
        x0, y0, _ = bm.projector(camera)((0, 0, 0))
        x1, y1, _ = bm.projector(moved)((0, 0, 0))
        self.assertAlmostEqual(x1 - x0, -20, delta=1)
        self.assertAlmostEqual(y1 - y0, 0, delta=1)
        moved = bm.pan(camera, 0, 15)
        x1, y1, _ = bm.projector(moved)((0, 0, 0))
        self.assertAlmostEqual(y1 - y0, 15, delta=2)


@unittest.skipUnless(GAME_WA.is_file(), "needs the game files in game/")
class DiscModelTest(unittest.TestCase):
    def test_the_games_board(self):
        """The disc's model: 78 triangles and 64 quads, the same on every
        field, each a piece of the board's textures, all fifteen drawn; the
        duel's camera sees the floor's rows and the near wall where the
        game's own screen shows them."""
        data = ba.read(GAME_WA.read_bytes())
        self.assertEqual(len({data.models[t] for t in ba.TERRAINS}), 1)
        board = bm.board(data, "normal")
        polygons = board.model.polygons
        self.assertEqual((sum(len(p[3]) == 3 for p in polygons), sum(len(p[3]) == 4 for p in polygons)), (78, 64))
        self.assertNotIn(None, board.parts)
        self.assertEqual(set(board.parts), set(bm.KEYS))
        xs, ys, zs = zip(*board.points)
        self.assertEqual((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)), (-252, 251, 0, 69, -220, 220))
        pieces = {p.key: ba.piece_image(data, "normal", p) for p in ba.PARTS}
        picture = bm.render(board, pieces)
        # Read off the game's own frame (Internal 1x, the hand's camera).
        for (x, y), key in (((160, 82), "opponent_back"), ((160, 91), "opponent_front"),
                            ((160, 98), "centre_step"), ((160, 110), "centre"), ((160, 128), "your_front"),
                            ((160, 148), "your_back"), ((160, 165), "trim"), ((160, 190), "wall_middle"),
                            ((80, 185), "wall_left"), ((240, 185), "wall_right"), ((10, 185), "wall_corners")):
            self.assertEqual(picture.part_at(x, y), key, (x, y))


class BoardPageTest(GuiCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wa = cls.game / "DATA" / "WA_MRG.MRG"
        wa.write_bytes(paint_boards(wa.read_bytes()))

    def setUp(self):
        super().setUp()
        self.tab = self.app.ui
        self.app.notebook.select(self.tab)
        self.tab.page_name.set("board")
        self.tab.show_page()
        self.app.update()
        self.page = self.tab.pages["board"]
        self.folder = Path(tempfile.mkdtemp())

    def png(self, name, w, h, color=(30, 160, 60, 255)):
        path = self.folder / name
        pngio.write(path, solid(w, h, color))
        return path

    def test_edits(self):
        page = self.page
        self.assertIsNotNone(page.picture)
        # The full picture first: a slow machine shows a small one a while, where a wall is a few pixels.
        start = time.perf_counter()
        while (page._work is not None or page.scale != 1) and time.perf_counter() - start < 20:
            self.app.update()
            time.sleep(0.002)
        self.assertEqual(page.scale, 1)
        # Clicking the board's near wall chooses it.
        self.click(centre_of("wall_middle"))
        self.assertEqual(page.chosen, "wall_middle")
        page.all_fields.set(True)
        page.replace(self.png("middle.png", 128, 128))
        st = ba.state(self.app.project)
        self.assertEqual({t for t, k in st.pictures}, set(ba.TERRAINS))
        self.assertEqual(self.tab.pages["board"].tree.set("wall_middle", "state"), "replaced")
        self.assertTrue(self.app.dirty)
        # A tint of the game's floor, on Forest alone.
        page.all_fields.set(False)
        page.field.set("forest")
        page.choose_field()
        page.select("floor")
        page.set_tint(0x80A0FF)
        self.assertEqual(len([k for k in st.tints if k[0] == "forest"]), 5)
        self.assertNotEqual(page.tint.value, ba.WHITE)
        # A replaced piece takes no tint.
        page.select("wall_middle")
        page.set_tint(0x404040)
        self.assertNotIn(("forest", "wall_middle"), st.tints)
        self.pause()
        out = self.folder / "export.png"
        page.export(str(out))
        self.assertEqual(pngio.read(out).size, (64, 64))
        page.revert()
        self.assertNotIn(("forest", "wall_middle"), st.pictures)
        self.assertIn(("normal", "wall_middle"), st.pictures)
        with mock.patch("fm_editor.ui_board.messagebox.askyesno", return_value=True):
            page.revert_all()
        self.assertFalse(st.pictures or st.tints)
        # Undo brings the edits back, pictures and all.
        self.pause()
        self.app.undo()
        self.app.update()
        st = ba.state(self.app.project)
        # Back to just before Revert page (its own undo step): the forest's
        # middle wall reverted before it stays so.
        self.assertEqual(len(st.pictures), 6)
        self.assertEqual(ba.picture(self.app.project, st.pictures[("normal", "wall_middle")]).size, (128, 128))
        self.assertEqual(len([k for k in st.tints if k[0] == "forest"]), 5)

    def click(self, point, button=1):
        page = self.page
        # Projected at the size of the picture shown (the canvas may have been resized since it was drawn).
        width, height = page.picture.image.size
        x, y, _ = bm.projector(page.camera, (width * page.scale, height * page.scale))(point)
        page.clicked(mock.Mock(x=x, y=y))

    def test_camera(self):
        """The middle button turns the board round (Shift: moves it), small
        pictures while it moves and the full one when it is let go; the
        wheel, a double middle click and Game's view."""
        page = self.page
        self.pause()                        # the canvas at its size and drawn so
        self.assertEqual((page.camera, page.scale), (bm.CAMERA, 1))
        full = page.picture
        self.assertEqual(full.image.size, page.canvas_size())
        k = page.game_pixels()
        small = page.drag_scale             # as small as this machine draws quickly (ui_board.adapt)
        from fm_editor import ui_board      # Tk: not imported where the pages are skipped
        self.assertIn(small, ui_board.DRAG_SCALES)
        page.press(mock.Mock(x=100, y=100, state=0))
        drawn = []
        real = page.draw

        def counted(scale=1):
            drawn.append(scale)
            real(scale)
        page.draw = counted
        for step in range(1, 41):           # a quick drag: many motions, few pictures
            page.motion(mock.Mock(x=100 + step * k * 3.2, y=100))
        self.app.update()
        self.assertEqual(page.camera[1], (bm.CAMERA[1] - 1024) % 4096)
        self.assertEqual(drawn, [small])
        self.assertEqual(page.scale, small)
        page.release(mock.Mock(x=0, y=0))
        self.pause()
        self.assertEqual(drawn[-1], 1)
        self.assertEqual(page.scale, 1)
        # Turned a quarter round, the left wall faces the camera.
        self.click(centre_of("wall_left"))
        self.assertEqual(page.chosen, "wall_left")
        # Down as far as it goes: the camera stays above the floor.
        page.press(mock.Mock(x=0, y=0, state=0))
        page.motion(mock.Mock(x=0, y=-5000))
        page.release(mock.Mock(x=0, y=-5000))
        self.assertEqual(page.camera[2], bm.PITCH_RANGE[0])
        # Shift moves the target.
        page.press(mock.Mock(x=0, y=0, state=1))
        page.motion(mock.Mock(x=40, y=0))
        page.release(mock.Mock(x=40, y=0))
        self.assertNotEqual(page.camera[3:], (0, 0))
        distance = page.camera[0]
        page.wheel(mock.Mock(num=4, delta=0))
        self.assertLess(page.camera[0], distance)
        for _ in range(2):
            page.canvas.event_generate("<ButtonPress-2>", x=10, y=10)
            page.canvas.event_generate("<ButtonRelease-2>", x=10, y=10)
        self.pause()
        self.assertEqual(page.camera, bm.CAMERA)
        page.camera = bm.orbit(bm.CAMERA, 100, 0)
        page.game_view.invoke()
        self.assertEqual(page.camera, bm.CAMERA)
        page.draw = real
        self.pause()
        self.assertEqual(page.picture.image.rgba, full.image.rgba)

    def test_saved_and_opened_again(self):
        page = self.page
        page.select("floor")
        page.replace(self.png("floor.png", 1024, 1016))
        page.select("trim")
        page.replace(self.png("trim.png", 512, 64, (250, 200, 40, 255)))
        page.select("corner_triangles")
        page.set_tint(0xFF6060)
        folder = self.folder / "mod"
        manifest.save_mod(self.app.project, folder)
        opened, messages = manifest.open_mod(self.app.retail, folder)
        self.assertEqual(messages, [])
        self.assertEqual(ba.digest(opened), ba.digest(self.app.project))
        self.app.set_project(opened)
        self.tab.refresh()
        self.app.update()
        self.assertEqual(self.page.tree.set("trim", "state"), "replaced")
        self.assertEqual(self.page.tree.set("corner_triangles", "state"), "tinted")


class TabRevertTest(GuiCase):
    def test_the_tabs_revert_to_retail_puts_the_board_back(self):
        tab = self.app.ui
        ba.state(self.app.project).tints[("normal", ba.PARTS[0].key)] = 0x808080
        ba.touched(self.app.project, pictures=False)
        tab.mark_reverts()
        self.assertNotIn("disabled", tab.revert_button.state())
        with mock.patch("fm_editor.ui_tab.messagebox.askyesno", return_value=True) as asked:
            tab.revert_all()
        self.assertIn("duel board", asked.call_args[0][1])
        self.assertFalse(ba.changed(self.app.project))
        self.assertIn("disabled", tab.revert_button.state())

