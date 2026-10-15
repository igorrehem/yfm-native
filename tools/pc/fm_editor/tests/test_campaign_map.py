"""The campaign map (campaign_map.py, map_view.py) on synthetic files:
reading the table, the "data" patches a mod gets and reading them back,
the checks, the sprites and the drawn map."""
import json
import tempfile
import unittest
from pathlib import Path

from fm_editor import campaign_map as cm, gamedata as g, manifest, map_view as mv, validate
from fm_editor.model import Project
from fm_editor.tests import map_fixture as mf


def project() -> Project:
    return Project(mf.map_fixture().game())


class ReadTest(unittest.TestCase):
    def test_table_and_names(self):
        data = mf.map_fixture().game().campaign_map
        self.assertIsNotNone(data)
        self.assertEqual(data.locations, mf.locations())
        self.assertEqual(data.tables["after"], mf.locations())
        self.assertEqual(data.names[0], "Place A")
        self.assertEqual(data.names[15], "Place P")
        self.assertEqual(data.notes, [])

    def test_without_the_packages(self):
        f = mf.map_fixture()
        self.assertIsNone(cm.read(f.slus, f.wa[:cm.PACKAGES[0][1] * cm.SECTOR]))
        broken = bytearray(f.wa)
        broken[cm.PACKAGES[1][1] * cm.SECTOR] = 0x15       # not the overworld module
        self.assertIsNone(cm.read(f.slus, bytes(broken)))
        p = Project(g.read_game(f.slus, f.wa[:0xFC0000]))
        self.assertFalse(cm.available(p))
        self.assertNotIn("data", manifest.build(p))

    def test_packages_that_differ(self):
        f = mf.map_fixture()
        wa = bytearray(f.wa)
        at = cm.table_offset(cm.PACKAGES[1][1])
        wa[at] = 1
        data = cm.read(f.slus, bytes(wa))
        self.assertEqual(len(data.notes), 1)
        self.assertEqual(data.locations, mf.locations())

    def test_names_follow_codes(self):
        """A label's placement code (0xF8 02 nn) is skipped and a flag test
        (0xF9 flag target) is read both ways."""
        from fm_editor.gamedata import _image, _tl, NAME_BANK, NAME_TABLE, slus_offset
        f = mf.map_fixture()
        slus = bytearray(f.slus)
        image = _image(bytes(slus))
        codes = {v: k for k, v in _tl.glyph_characters(image).items()}
        first = NAME_BANK + image.u16(NAME_TABLE + 0x350 * 2)
        other = NAME_BANK + image.u16(NAME_TABLE + 0x351 * 2)
        free = 0x801DF000
        blob = bytes([0xF8, 0x02, 0x10, 0xF9, 0x47, 0x00]) + (other - NAME_BANK).to_bytes(2, "little") + \
            bytes(codes[c] for c in "Old") + b"\xFF"
        slus[slus_offset(free):slus_offset(free) + len(blob)] = blob
        slus[slus_offset(NAME_TABLE + 0x350 * 2):slus_offset(NAME_TABLE + 0x350 * 2) + 2] = \
            (free - NAME_BANK).to_bytes(2, "little")
        self.assertEqual(cm.place_names(bytes(slus))[0], "Old / Place B")
        self.assertNotEqual(first, free)


class RecordTest(unittest.TestCase):
    def test_pack_round_trip(self):
        for loc in mf.locations():
            blob = cm.pack(loc)
            self.assertEqual(len(blob), cm.RECORD)
            self.assertEqual(cm.unpack(blob), loc)

    def test_conditions(self):
        self.assertEqual(cm.condition_parts(0), ("always", 0))
        self.assertEqual(cm.condition_parts(0x8054), ("clear", 0x54))
        self.assertEqual(cm.condition_parts(0x0047), ("set", 0x47))
        for kind, flag in (("always", 0), ("set", 71), ("clear", 90)):
            self.assertEqual(cm.condition_parts(cm.condition_value(kind, flag)), (kind, flag))
        self.assertEqual(cm.describe_buttons(0x3000), "up+right")

    def test_runs(self):
        old = bytes(20)
        new = bytearray(old)
        new[2] = 1
        new[4] = 2               # within the gap of 4: one run
        new[15] = 3              # far: a run of its own
        self.assertEqual(cm.runs(old, bytes(new), 0x100),
                         [{"at": "0x102", "bytes": "01 00 02"}, {"at": "0x10F", "bytes": "03"}])
        self.assertEqual(cm.runs(old, old, 0), [])


class ModTest(unittest.TestCase):
    def test_unchanged_writes_nothing(self):
        p = project()
        self.assertFalse(cm.any_changed(p))
        self.assertNotIn("data", manifest.build(p))

    def test_patch_both_packages(self):
        p = project()
        st = cm.state(p)
        st.locations[13].marker_x, st.locations[13].marker_y = 200, 100
        st.locations[0].exits[0].destination = 9
        built = manifest.build(p)
        entry = built["data"][-1]
        self.assertEqual(entry["file"], cm.ARCHIVE_FILE)
        wa = bytearray(mf.map_fixture().wa)
        for run in entry["patch"]:
            at = int(run["at"], 16)
            blob = bytes.fromhex(run["bytes"])
            wa[at:at + len(blob)] = blob
        for name, sector in cm.PACKAGES:
            start = cm.table_offset(sector)
            self.assertEqual(cm.unpack_table(bytes(wa[start:start + cm.COUNT * cm.RECORD])), st.locations)
        touched = {int(r["at"], 16) // cm.SECTOR for r in entry["patch"]}
        self.assertEqual(touched, {sector + cm.TABLE_OFFSET // cm.SECTOR for _, sector in cm.PACKAGES})

    def test_saved_and_opened_again(self):
        p = project()
        p.other["data"] = [{"file": "\\DATA\\WA_MRG.MRG;1", "patch": [{"at": "0x5D800", "bytes": "26 25"}]},
                           {"file": "\\DATA\\CARD.MRG;1", "replace": "card.mrg"}]
        st = cm.state(p)
        st.locations[5].exits[1].buttons = 0x1000
        st.locations[12].confirm = 3
        with tempfile.TemporaryDirectory() as tmp:
            manifest.save_mod(p, Path(tmp) / "m")
            written = json.loads((Path(tmp) / "m" / "mod.json").read_text(encoding="utf-8"))
            self.assertEqual(len(written["data"]), 3)
            self.assertEqual(written["data"][:2], p.other["data"])
            again, messages = manifest.open_mod(p.retail, Path(tmp) / "m")
        self.assertEqual(messages, [])
        self.assertEqual(cm.state(again).locations, st.locations)
        # The map's patches are the map's again, the rest kept as written.
        self.assertEqual(again.other["data"], p.other["data"])
        self.assertEqual(manifest.build(again)["data"], written["data"])

    def test_a_run_across_the_edge_is_kept(self):
        p = project()
        start = cm.table_offset(cm.PACKAGES[0][1])
        edge = {"at": hex(start - 1), "bytes": "AA BB"}
        inside = {"at": hex(start + 0x0C), "bytes": "10 00"}
        p.other["data"] = [{"file": "\\DATA\\WA_MRG.MRG;1", "patch": [edge, inside]}]
        messages = cm.read_mod(p)
        self.assertEqual(p.other["data"], [{"file": "\\DATA\\WA_MRG.MRG;1", "patch": [edge]}])
        self.assertEqual(cm.state(p).locations[0].marker_x, 0x10)
        self.assertTrue(any("crosses the edge" in m for m in messages))
        self.assertTrue(any("differs between the two" in m for m in messages))   # only one package patched

    def test_reset(self):
        p = project()
        st = cm.state(p)
        st.locations[2].target_x += 50
        st.locations[3].pitch = 1
        self.assertTrue(cm.changed(p, 2))
        cm.reset(p, 2)
        self.assertFalse(cm.changed(p, 2))
        self.assertTrue(cm.changed(p, 3))
        cm.reset_all(p)
        self.assertFalse(cm.any_changed(p))


class CheckTest(unittest.TestCase):
    def issues(self, p):
        return [i for i in validate.validate(p) if i.area == "Map"]

    def test_retail_is_clean(self):
        self.assertEqual(self.issues(project()), [])

    def test_refused_and_warned(self):
        p = project()
        st = cm.state(p)
        e = st.locations[1].exits[0]
        e.steps = 0
        st.locations[1].exits[1].destination = 17
        st.locations[2].confirm = 16
        st.locations[4].exits[1].buttons = 0x2000           # the same way as exit 1, always: never taken
        st.locations[6].exits[0].buttons = 0
        st.locations[7].exits[0].x = 400
        issues = self.issues(p)
        text = "\n".join(str(i) for i in issues)
        errors = [i for i in issues if i.level == "error"]
        self.assertEqual(len(errors), 3, text)
        self.assertIn("takes 0 frames", text)
        self.assertIn("leads to 17", text)
        self.assertIn("Confirm leads to 16", text)
        self.assertIn("never taken while arrow 1 is", text)
        self.assertIn("needs no direction", text)
        self.assertIn("off the screen", text)
        self.assertTrue(all(isinstance(i.target, int) for i in issues))

    def test_unreachable(self):
        p = project()
        st = cm.state(p)
        # Place 8 was reached from 7 (right) and 9 (left): both now lead elsewhere.
        st.locations[7].exits[0].destination = 6
        st.locations[9].exits[1].destination = 10
        issues = self.issues(p)
        self.assertTrue(any(i.target == 8 and "leads here" in i.message for i in issues),
                        "\n".join(map(str, issues)))

    def test_edges(self):
        locs = mf.locations()
        locs[2].confirm = 12
        locs[2].gate = 1
        kinds = {what: (to, cond) for what, to, cond in cm.edges(locs, 2)}
        self.assertEqual(kinds["confirm"], (12, 0))          # exit 1 of place 2 is unconditional
        self.assertIn("cancel", {w for w, _, _ in cm.edges(locs, 12)})


class SpriteTest(unittest.TestCase):
    def test_arrow_and_its_mirror(self):
        data = mf.map_fixture().game().campaign_map
        image, left, top = cm.arrow_image(data, 0)
        self.assertEqual((image.width, image.height, left, top), (16, 16, -4, -8))
        color = cm.color(mf.STRIP_COLOR)
        self.assertEqual(image.pixel(0, 0), color)
        self.assertEqual(image.pixel(15, 0)[3], 0)           # the clear columns on the right
        mirrored, left, top = cm.arrow_image(data, 4)
        self.assertEqual((left, top), (-12, -8))            # -(dx + width)
        self.assertEqual(mirrored.pixel(15, 0), color)
        self.assertEqual(mirrored.pixel(0, 0)[3], 0)

    def test_marker_and_panel(self):
        data = mf.map_fixture().game().campaign_map
        marker = cm.sprite_image(data, *cm.MARKER)
        self.assertEqual((marker[0].size, marker[1], marker[2]), ((32, 32), -16, -16))
        panel = cm.sprite_image(data, *cm.PANEL)
        self.assertEqual(panel[0].size, (128, 16))
        self.assertIsNone(cm.sprite_frame(b"", 0, 0))          # no bank


class ViewTest(unittest.TestCase):
    def model(self):
        return mv.MapModel(mv.model_blob(mf.map_fixture().wa, cm.PACKAGES[0][1]))

    def test_model(self):
        m = self.model()
        self.assertEqual(len(m.polygons), 1)
        self.assertEqual(len(m.images), 1)
        self.assertEqual(m.vram[240 * 1024 + 1], mf.TEXTURE_COLOR)
        self.assertEqual(m.world((300, 0, 0)), (300 * mv.SCALE, 0, 0))

    def test_render(self):
        m = self.model()
        blue = (0, 0, 255, 255)
        for camera in ((1000, 2048, 1024, 0, 0), (1000, 0, 900, 0, 0)):
            picture = mv.render(m, camera)
            self.assertEqual(picture.size, (320, 240))
            self.assertEqual(picture.pixel(160, 120), blue, camera)
            self.assertEqual(picture.pixel(1, 1), (0, 0, 0, 255), camera)
        # From below, the quad's back faces the camera: nothing is drawn.
        self.assertEqual(mv.render(m, (1000, 0, -900, 0, 0)).pixel(160, 120), (0, 0, 0, 255))
        # The world map's spotlight leaves the middle and darkens the edge.
        lit = mv.render(m, (300, 0, 1000, 0, 0), spotlight=True)
        self.assertEqual(lit.pixel(160, 144), blue)
        self.assertEqual(lit.pixel(2, 2), (0, 0, 0, 255))

    def test_top(self):
        m = self.model()
        picture = mv.render_top(m, (0, 0), 1000, (100, 100))
        self.assertEqual(picture.pixel(50, 50), (0, 0, 255, 255))
        self.assertEqual(picture.pixel(2, 2), (0, 0, 0, 255))

    def test_not_a_model(self):
        with self.assertRaises(mv.ModelError):
            mv.MapModel(bytes(4096))


if __name__ == "__main__":
    unittest.main()
