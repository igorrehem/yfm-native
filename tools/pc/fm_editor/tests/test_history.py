"""Undo across tables and assets, save boundaries and crash-safe recovery."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fm_editor import art, history, manifest, recovery, settings
from fm_editor.model import Project
from fm_editor.pngio import Image
from fm_editor.tests.test_data import fixture


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.project = Project(fixture().game())
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        patch = mock.patch.object(settings, "path", return_value=self.folder / "config" / "settings.json")
        patch.start()
        self.addCleanup(patch.stop)

    def test_undo_redo_branch_and_saved_boundary(self):
        p = self.project
        h = history.History(p, limit=2)
        self.assertFalse(h.record(p))
        p.cards[1].name = "First edit"
        self.assertTrue(h.record(p))
        h.mark_saved(p)
        p.cards[1].name = "Second edit"
        h.record(p)
        p = h.move(-1, p)
        self.assertEqual(p.cards[1].name, "First edit")
        self.assertFalse(h.dirty)
        self.assertFalse(h.record(p), "restoring a snapshot must not create another edit")
        p = h.move(1, p)
        self.assertEqual(p.cards[1].name, "Second edit")
        self.assertTrue(h.dirty)
        p = h.move(-1, p)
        p.info.author = "New branch"
        h.record(p)
        self.assertIsNone(h.move(1, p))
        for i in range(5):
            p.info.version = str(i)
            h.record(p)
        self.assertEqual(len(h.items), 3)
        self.assertEqual(h.position, 2)

    def test_form_reordering_is_not_an_edit(self):
        p = self.project
        p.other = {"limits": {"life_points": 9000}, "custom": [1, 2]}
        h = history.History(p)
        p.other = {"custom": [1, 2], "limits": {"life_points": 9000}}
        self.assertFalse(h.record(p))

    def test_map_history_and_artwork_survive_save(self):
        from fm_editor import campaign_map as cm, map_art
        from fm_editor.tests.map_fixture import map_fixture
        p = Project(map_fixture().game())
        original = cm.state(p).locations[0].marker_x
        h = history.History(p)
        cm.state(p).locations[0].marker_x = original + 10
        picture = Image(256, 256, bytes([60, 70, 80, 255]) * (256 * 256))
        map_art.set_strip(p, 2, picture)
        h.record(p)
        p = h.move(-1, p)
        self.assertEqual(cm.state(p).locations[0].marker_x, original)
        self.assertIsNone(map_art.strip_override(p, 2))
        self.assertFalse(h.record(p))
        p = h.move(1, p)
        self.assertIs(cm.state(p).retail, p.retail.campaign_map)
        self.assertEqual(cm.state(p).locations[0].marker_x, original + 10)
        folder = self.folder / "map-mod"
        manifest.save_mod(p, folder)
        reopened, _ = manifest.open_mod(p.retail, folder)
        self.assertEqual(map_art.strip_override(reopened, 2), picture)
        self.assertEqual(cm.state(reopened).locations[0].marker_x, original + 10)

    def test_multiple_tables_and_unknown_keys_roundtrip(self):
        p = self.project
        h = history.History(p)
        p.cards[1].type = 23
        p.card_extra[1] = {"effect": 301}
        p.equips[1] = {2, 3}
        p.other["limits"] = {"life_points": 9000}
        p.other["custom_unknown"] = {"keep": [1, "two"]}
        p.files["notes.txt"] = b"asset"
        p.notes[1] = "Private note"
        expected = manifest.build(p)
        h.record(p)
        p = h.move(-1, p)
        self.assertNotEqual(p.cards[1].type, 23)
        self.assertNotIn("custom_unknown", p.other)
        p = h.move(1, p)
        self.assertEqual(manifest.build(p), expected)
        self.assertEqual(p.notes[1], "Private note")
        self.assertEqual(p.files["notes.txt"], b"asset")

    def test_artwork_undo_after_overwriting_save(self):
        p = self.project
        old = Image(102, 96, bytes([30, 40, 50, 255]) * (102 * 96))
        new = Image(102, 96, bytes([90, 80, 70, 255]) * (102 * 96))
        art.set_image(p, 1, "art", old)
        folder = self.folder / "mod"
        manifest.save_mod(p, folder)
        p, _ = manifest.open_mod(p.retail, folder)
        h = history.History(p)  # freezes the initially lazy art
        art.set_image(p, 1, "art", new)
        h.record(p)
        manifest.save_mod(p, folder)
        h.mark_saved(p)
        p = h.move(-1, p)
        self.assertEqual(art.replacement_image(p, 1, "art"), old)
        self.assertFalse(h.record(p))
        manifest.save_mod(p, folder)
        reopened, _ = manifest.open_mod(p.retail, folder)
        self.assertEqual(art.replacement_image(reopened, 1, "art"), old)
        self.assertEqual(len(art.entries_now(reopened)), 2)  # art plus derived thumbnail
        p = h.move(1, p)
        self.assertEqual(art.replacement_image(p, 1, "art"), new)

    def test_pack_and_star_images_undo_after_save(self):
        from fm_editor import guardian_stars as gs, pngio
        p = self.project
        stars = gs.read(None)
        star = stars.add_star()
        stars.stars[star].icon = "icons/star.png"
        p.other["guardian_stars"] = stars.build()
        p.packs = [{"id": "pack", "name": "Pack", "image": "packs/pack.png", "cards": [1]}]
        old = pngio.encode(Image(4, 4, bytes([30, 40, 50, 255]) * 16))
        new = pngio.encode(Image(4, 4, bytes([90, 80, 70, 255]) * 16))
        p.files = {"icons/star.png": old, "packs/pack.png": old}
        folder = self.folder / "image-mod"
        manifest.save_mod(p, folder)
        p, _ = manifest.open_mod(p.retail, folder)
        self.assertFalse(p.files)
        h = history.History(p)
        p.files = {"icons/star.png": new, "packs/pack.png": new}
        h.record(p)
        manifest.save_mod(p, folder)
        h.mark_saved(p)
        p = h.move(-1, p)
        self.assertFalse(h.record(p))
        manifest.save_mod(p, folder)
        for name in ("icons/star.png", "packs/pack.png"):
            self.assertEqual((folder / name).read_bytes(), old)
        p = h.move(1, p)
        self.assertEqual(p.files["icons/star.png"], new)

    def test_recovery_preserves_assets_forms_and_original(self):
        p = self.project
        source = self.folder / "mod"
        manifest.save_mod(p, source)
        original = (source / "mod.json").read_bytes()
        p.cards[1].name = "Recovered name"
        p.files["extra/data.bin"] = b"unsaved asset"
        r = recovery.Recovery()
        forms = {"cards": {"current": 1, "vars": {"attack": "invalid but recoverable"}}}
        r.write(p, forms)
        rows = recovery.records()
        self.assertEqual(len(rows), 1)
        _, folder, data = rows[0]
        reopened, _ = manifest.open_mod(p.retail, folder)
        self.assertEqual(reopened.cards[1].name, "Recovered name")
        self.assertEqual((folder / "extra/data.bin").read_bytes(), b"unsaved asset")
        self.assertEqual(data["forms"], forms)
        self.assertEqual((source / "mod.json").read_bytes(), original)
        self.assertEqual(p.source_dir, source)
        r.write(p)
        self.assertFalse(folder.exists())
        self.assertEqual(len(recovery.records()), 1)
        r.clear()
        self.assertEqual(recovery.records(), [])

    def test_failed_recovery_keeps_previous_generation(self):
        r = recovery.Recovery()
        r.write(self.project)
        before = recovery.records()[0]
        with mock.patch.object(manifest, "save_mod", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                r.write(self.project)
        self.assertEqual(recovery.records(), [before])
        self.assertEqual(len(list(r.folder.iterdir())), 2)

    def test_backup_assets_rotation_and_failure(self):
        source = self.folder / "mod"
        manifest.save_mod(self.project, source)
        for i in range(4):
            (source / "art.png").write_bytes(bytes([i]))
            recovery.backup(source, keep=2)
        rows = recovery.records()
        self.assertEqual(len(rows), 2)
        self.assertEqual({(folder / "art.png").read_bytes() for _, folder, _ in rows}, {b"\x02", b"\x03"})
        with mock.patch.object(recovery.shutil, "copy2", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                recovery.backup(source)
        self.assertEqual(len(recovery.records()), 2)
        self.assertEqual((source / "art.png").read_bytes(), b"\x03")

    def test_copies_share_unchanged_files(self):
        """Autosaves and backups link what did not change since the last copy
        and copy the rest, so a large mod's art is not copied every time."""
        source = self.folder / "mod"
        manifest.save_mod(self.project, source)
        (source / "big.bin").write_bytes(b"art" * 1000)
        (source / "edited.bin").write_bytes(b"old")
        old = time.time() - 60      # settled well before the copies
        for name in ("big.bin", "edited.bin"):
            os.utime(source / name, (old, old))
        p, _ = manifest.open_mod(self.project.retail, source)

        r = recovery.Recovery()
        r.write(p)
        first = next(row[1] for row in recovery.records() if row[0].parent == r.folder)
        linked = (first / "big.bin").stat().st_ino
        edited = (first / "edited.bin").stat().st_ino
        (source / "edited.bin").write_bytes(b"new!")
        os.utime(source / "edited.bin", (old + 1, old + 1))
        p.files["extra.bin"] = b"unsaved"
        r.write(p)
        second = next(row[1] for row in recovery.records() if row[0].parent == r.folder)
        self.assertFalse(first.exists())
        self.assertEqual((second / "big.bin").read_bytes(), b"art" * 1000)
        self.assertEqual((second / "edited.bin").read_bytes(), b"new!")
        self.assertEqual((second / "extra.bin").read_bytes(), b"unsaved")
        self.assertFalse((second / "big.bin").samefile(source / "big.bin"))
        if (second / "big.bin").stat().st_ino != linked:
            self.skipTest("no hard links on this file system")
        self.assertNotEqual((second / "edited.bin").stat().st_ino, edited)
        r.clear()
        # Backups: the second shares big.bin with the first; a file changed
        # in between, or written just before the first, is copied.
        recovery.backup(source)
        (source / "edited.bin").write_bytes(b"newer")
        (source / "fresh.bin").write_bytes(b"just written")
        recovery.backup(source)
        rows = sorted(recovery.records(), key=lambda row: row[0].stat().st_mtime_ns)
        a, b = rows[0][1], rows[1][1]
        self.assertTrue((a / "big.bin").samefile(b / "big.bin"))
        self.assertFalse((a / "edited.bin").samefile(b / "edited.bin"))
        self.assertEqual((a / "edited.bin").read_bytes(), b"new!")
        self.assertEqual((b / "edited.bin").read_bytes(), b"newer")
        self.assertFalse((source / "big.bin").samefile(b / "big.bin"))
        self.assertEqual((b / "mod.json").read_bytes(), (source / "mod.json").read_bytes())

    def test_recent_file_is_copied_not_linked(self):
        """A file written right around the previous copy may have changed
        within the clock's step: it is copied."""
        source = self.folder / "mod"
        manifest.save_mod(self.project, source)
        (source / "art.png").write_bytes(b"\x01")
        recovery.backup(source)
        (source / "art.png").write_bytes(b"\x02")
        last = max(recovery.records(), key=lambda row: row[2]["time"])[1]
        stat = (last / "art.png").stat()
        os.utime(source / "art.png", ns=(stat.st_atime_ns, stat.st_mtime_ns))  # same size and time
        recovery.backup(source)
        rows = sorted(recovery.records(), key=lambda row: row[0].stat().st_mtime_ns)
        self.assertEqual((rows[-1][1] / "art.png").read_bytes(), b"\x02")

    def test_broken_previous_index_does_not_delete_other_sessions(self):
        first, second = recovery.Recovery(), recovery.Recovery()
        first.write(self.project)
        second.write(self.project)
        index = first.folder / "recovery.json"
        index.write_text(json.dumps({"generation": ".."}))
        with self.assertRaises(ValueError):
            first.write(self.project)
        self.assertTrue(second.folder.exists())
        self.assertTrue(index.exists())

    def test_invalid_recovery_index_cannot_escape_store(self):
        r = recovery.Recovery()
        r.folder.mkdir(parents=True)
        (r.folder / "recovery.json").write_text(json.dumps({"generation": "../elsewhere"}))
        self.assertEqual(recovery.records(), [])
