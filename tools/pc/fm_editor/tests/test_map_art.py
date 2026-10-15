"""The map's pictures in a mod (map_art.py) on the synthetic map: the
terrain's textures and the sprite strip as texture pack entries, pasting a
sprite's picture into its animation's cells, export and import, reading a
saved mod's entries back, and the previews drawing them."""
import json
import tempfile
import unittest
from pathlib import Path

from fm_editor import art, campaign_map as cm, manifest, map_art as ma, map_view as mv, pngio, validate
from fm_editor.model import Project
from fm_editor.tests import map_fixture as mf

RED = (255, 0, 0, 255)


def project() -> Project:
    return Project(mf.map_fixture().game())


def solid(width, height, color=RED):
    return pngio.Image(width, height, bytes(color) * (width * height))


class TextureTest(unittest.TestCase):
    def test_found(self):
        data = mf.map_fixture().game().campaign_map
        found = ma.package_textures(data, "before")
        self.assertEqual(len(found), 1)
        t = found[0]
        base = (cm.PACKAGES[0][1] + 6) * cm.SECTOR
        self.assertEqual((t.block, t.x, t.y, t.words, t.rows, t.bpp, t.entries), (0, 0, 256, 32, 64, 4, 16))
        self.assertEqual(t.offset, base + 128 * 4)               # the image section's first word
        self.assertEqual(t.clut_offset, base + (128 + 1024) * 4)
        self.assertEqual(t.name, "before/texture00-3c00.png")
        image = ma.texture_image(data.wa, t)
        self.assertEqual(image.size, (128, 64))
        self.assertEqual(image.pixel(5, 5), cm.color(mf.TEXTURE_COLOR))
        after = ma.package_textures(data, "after")[0]
        self.assertNotEqual(after.offset, t.offset)

    def test_pack_entries_and_reading_back(self):
        p = project()
        texture = ma.uses(p)[0]
        notes = ma.set_texture(p, texture, solid(256, 128))      # 2x
        self.assertEqual(notes, [])
        ma.set_strip(p, 2, solid(256, 256, (0, 255, 0, 255)))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "m"
            manifest.save_mod(p, folder)
            data = json.loads((folder / "mod.json").read_text(encoding="utf-8"))
            self.assertEqual(data["textures"], "textures")
            entries = json.loads((folder / "textures" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(entries), 1 + len(cm.PACKAGES))
            by_offset = {e["offset"]: e for e in entries}
            self.assertEqual(by_offset[texture.offset]["clut_offset"], texture.clut_offset)
            self.assertEqual(by_offset[texture.offset]["file"], "map/before/texture00-3c00.png")
            for _, sector in cm.PACKAGES:
                entry = by_offset[ma.strip_offset(sector)]
                self.assertEqual((entry["clut_offset"], entry["words"], entry["rows"]),
                                 (ma.palette_offset(sector, 2), 64, 256))
            self.assertEqual(pngio.read(folder / "textures" / "map" / "before" / "texture00-3c00.png").size,
                             (256, 128))
            self.assertEqual([i for i in validate.validate(p) if i.area == "Art"], [])
            again, messages = manifest.open_mod(p.retail, folder)
            st = ma.state(again)
            self.assertEqual(set(st.textures), {texture})
            self.assertEqual(set(st.strips), {2})
            self.assertEqual(ma.picture(again, st.textures[texture]).size, (256, 128))
            # Written again as it was, no entry twice.
            manifest.save_mod(again, folder)
            self.assertEqual(json.loads((folder / "textures" / "manifest.json").read_text(encoding="utf-8")),
                             entries)

    def test_other_entries_are_kept(self):
        p = project()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "m"
            (folder / "textures").mkdir(parents=True)
            other = {"file": "x.png", "archive": "WA_MRG.MRG", "offset": 4096, "words": 4, "rows": 4, "bpp": 16,
                     "clut_offset": 0, "clut_entries": 0}
            pngio.write(folder / "textures" / "x.png", solid(4, 4))
            (folder / "textures" / "manifest.json").write_text(json.dumps([other]), encoding="utf-8")
            (folder / "mod.json").write_text(json.dumps({"id": "m", "textures": "textures"}), encoding="utf-8")
            again, _ = manifest.open_mod(p.retail, folder)
            ma.set_strip(again, 3, solid(256, 256))
            manifest.save_mod(again, folder)
            entries = json.loads((folder / "textures" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(entries[0], other)
            self.assertEqual(len(entries), 1 + len(cm.PACKAGES))

    def test_export_import_revert(self):
        p = project()
        with tempfile.TemporaryDirectory() as tmp:
            written = ma.export_textures(p, "before", tmp)
            self.assertEqual([w.name for w in written], ["texture00-3c00.png"])
            self.assertEqual(pngio.read(written[0]).pixel(0, 0), cm.color(mf.TEXTURE_COLOR))
            pngio.write(written[0], solid(128, 64))
            notes = ma.import_textures(p, "before", tmp)
            self.assertTrue(notes)
            self.assertEqual(len(ma.state(p).textures), 1)
            sprites = ma.export_sprites(p, tmp)
            self.assertEqual(len(sprites), 4)
            self.assertEqual(pngio.read(sprites[0]).size, (256, 256))
            self.assertTrue(ma.import_sprites(p, tmp))
            self.assertEqual(set(ma.state(p).strips), {0, 1, 2, 3})
        ma.revert_textures(p, "after")
        self.assertEqual(len(ma.state(p).textures), 1)
        ma.revert_textures(p, "before")
        ma.revert_sprites(p)
        self.assertEqual((ma.state(p).textures, ma.state(p).strips), ({}, {}))

    def test_odd_sizes(self):
        p = project()
        texture = ma.uses(p)[0]
        notes = ma.set_texture(p, texture, solid(1000, 1000))
        self.assertEqual(ma.state(p).textures[texture].image.size, (512, 256))
        self.assertTrue(any("shape" in n for n in notes) and any("at most" in n for n in notes))


class SpriteTest(unittest.TestCase):
    def test_arrow_picture_goes_into_its_cells(self):
        p = project()
        data = cm.state(p).retail
        picture = pngio.Image(32, 32, bytes((0, 0, 255, 255)) * (16 * 32) + bytes((255, 255, 0, 255)) * (16 * 32))
        notes = ma.set_sprite(p, 2, 0, picture)          # 2x the 16x16 arrow: blue top half, yellow bottom
        self.assertEqual(notes, [])
        strip = ma.strip_override(p, 0)
        self.assertEqual(strip.size, (512, 512))
        # The arrow's cell is at u 64, v 64 (x2): its top-left is blue, its bottom yellow.
        self.assertEqual(strip.pixel(128, 128), (0, 0, 255, 255))
        self.assertEqual(strip.pixel(128, 128 + 30), (255, 255, 0, 255))
        # The rest of the strip keeps the disc's texels (index 1 is green in palette 0).
        self.assertEqual(strip.pixel(2, 2), cm.color(mf.STRIP_COLOR))
        # Drawn with the mod's strip, the arrow and its mirror show the picture.
        strips = {0: strip}
        image, _, _ = cm.arrow_image(data, 0, strips)
        self.assertEqual(image.pixel(0, 0), (0, 0, 255, 255))
        mirrored, _, _ = cm.arrow_image(data, 4, strips)
        self.assertEqual(mirrored.pixel(15, 15), (255, 255, 0, 255))

    def test_cells_follow_the_stream(self):
        data = mf.map_fixture().game().campaign_map
        # The panel's frame is held for good (duration 0): the marker's stream after it is not the panel's.
        self.assertEqual(len(ma.sprite_cells(data, 0, 0)), 1)
        self.assertEqual(len(ma.sprite_cells(data, 2, 0)), 1)
        mirrored = ma.sprite_cells(data, 2, 4)
        self.assertEqual(len(mirrored), 1)
        self.assertTrue(mirrored[0].mirror)


class PreviewTest(unittest.TestCase):
    def test_render_with_a_texture_of_the_mod(self):
        p = project()
        texture = ma.uses(p)[0]
        ma.set_texture(p, texture, solid(128, 64))
        model = mv.MapModel(mv.model_blob(mf.map_fixture().wa, cm.PACKAGES[0][1]))
        overrides = ma.texture_overrides(p, "before")
        self.assertEqual(set(overrides), {(0, texture.clut)})
        picture = mv.render(model, (1000, 2048, 1024, 0, 0), overrides=overrides)
        r, g, b, a = picture.pixel(160, 120)
        self.assertEqual((g, b, a), (0, 0, 255))
        self.assertGreater(r, 200)
        self.assertEqual(mv.render_top(model, (0, 0), 1000, (50, 50), overrides=overrides).pixel(25, 25)[:3],
                         (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
