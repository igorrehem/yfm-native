"""The Map tab, driven as a user would, on the synthetic campaign map.
Skipped where there is no Tk or no display."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
except ImportError:
    tk = None

from fm_editor import campaign_map as cm
from fm_editor.tests import map_fixture as mf


class MapGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name) / "game"
        (folder / "DATA").mkdir(parents=True)
        f = mf.map_fixture()
        (folder / "SLUS_014.11").write_bytes(f.slus)
        (folder / "DATA" / "WA_MRG.MRG").write_bytes(f.wa)
        cls.game = folder

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        from fm_editor import settings
        from fm_editor.app import App
        self.settings = Path(self.tmp.name) / "config" / "settings.json"
        patcher = mock.patch.object(settings, "path", lambda: self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = App(ask=False, autostart=False)
        self.app.withdraw()
        self.app.start(str(self.game), None, False)
        self.app.notebook.select(self.app.map)
        self.app.update()

    def tearDown(self):
        self.app.dirty = False
        self.app.destroy()

    def test_a_field_that_does_not_read_is_said(self):
        """Out of range or not a number: nothing of the place is stored, and
        the tab says which field (it was kept as it was without a word)."""
        app, tab = self.app, self.app.map
        tab.select(13)
        before = cm.state(app.project).locations[13]
        tab.vars["distance"].set(40000)
        self.assertIn("Distance", tab.problems.cget("text"))
        self.assertEqual(str(tab.problems.cget("style")), "Error.TLabel")
        self.assertEqual(cm.state(app.project).locations[13].distance, before.distance)
        tab.vars["distance"].set(before.distance)
        self.assertNotIn("Not stored", tab.problems.cget("text"))
        # The arrow's flag past what can be kept is refused; past the 11
        # bits the game reads, kept and warned about.
        self.assertEqual(tab.exit, 0)
        tab.vars["kind"].set("set")
        tab.vars["flag"].set(0x8000)
        self.assertIn("flag", tab.problems.cget("text"))
        self.assertIn("Not stored", tab.problems.cget("text"))
        tab.vars["flag"].set(0x800)
        self.assertNotIn("Not stored", tab.problems.cget("text"))
        self.assertIn("0x7FF", tab.problems.cget("text"))
        tab.vars["flag"].set(5)
        self.assertNotIn("Not stored", tab.problems.cget("text"))
        self.assertEqual(cm.state(app.project).locations[13].exits[0].condition, 5)

    def test_typing_draws_and_records_once_it_pauses(self):
        """A camera field applies at each key: the 3D screen is drawn, and
        the undo step taken, once the typing stops, not at every key."""
        from unittest import mock
        from fm_editor.app import HISTORY_PAUSE
        app, tab = self.app, self.app.map
        tab.select(0)
        app.update()
        start = int(tab.vars["distance"].get())
        with mock.patch.object(tab, "draw_screen") as drawn, \
                mock.patch.object(app.history, "record", wraps=app.history.record) as recorded:
            for n in range(1, 6):
                tab.vars["distance"].set(start + n)
                app.update()
            self.assertEqual((drawn.call_count, recorded.call_count), (0, 0))
            app.after(HISTORY_PAUSE + 100)
            app.update()
            self.assertEqual((drawn.call_count, recorded.call_count), (1, 1))
        self.assertEqual(cm.state(app.project).locations[0].distance, start + 5)
        app.undo()
        self.assertEqual(cm.state(app.project).locations[0].distance, start)   # one step for the five keys

    def test_simple_until_advanced(self):
        """The numbers are under Show advanced; the marker's only in a town."""
        app, tab = self.app, self.app.map
        tab.select(13)
        app.update()
        self.assertFalse(tab.camera_frame.winfo_ismapped())
        self.assertFalse(tab.marker_frame.winfo_ismapped())
        tab.advanced_shown.set(True)
        tab.show_advanced()
        app.update()
        self.assertTrue(tab.camera_frame.winfo_ismapped())
        self.assertTrue(tab.marker_frame.winfo_ismapped())
        self.assertTrue(tab.arrow_frame.winfo_ismapped())
        tab.select(0)                   # a world place: no marker
        app.update()
        self.assertFalse(tab.marker_frame.winfo_ismapped())
        tab.advanced_shown.set(False)
        tab.show_advanced()

    def test_arrows(self):
        """The arrow list: one row an arrow used; one picked on the screen or
        in the list is the panel's; added, edited, removed, reverted."""
        app, tab = self.app, self.app.map
        tab.select(3)
        self.assertEqual(tab.exits.get_children(), ("0", "1", "2"))
        self.assertEqual(tab.exits.item("2", "values")[2], "before flag 84")
        # Picked by a click on its arrow.
        tab.view.set("screen")
        tab.draw()
        e = cm.state(app.project).locations[3].exits[2]
        tab.press(mock.Mock(x=e.x * 2, y=e.y * 2))
        tab.release(mock.Mock(x=e.x * 2, y=e.y * 2))
        self.assertEqual(tab.exit, 2)
        self.assertEqual(tab.exits.selection(), ("2",))
        self.assertTrue(tab.canvas.find_withtag("ring"))
        # Edited: where it leads, the direction, when it is open, its picture.
        tab.vars["destination"].set(cm.label(app.project, 9))
        tab.vars["up"].set(True)
        tab.vars["kind"].set("always")
        tab.vars["arrow"].set(6)
        e = cm.state(app.project).locations[3].exits[2]
        self.assertEqual((e.destination, e.buttons, e.condition, e.arrow), (9, 0x5000, 0, 6))
        self.assertEqual(list(tab.exits.item("2", "tags")), ["changed"])
        self.assertIn("Arrow 3", [w.cget("text").split(" ", 1)[-1] for w in tab.changes.winfo_children()])
        # Added: the free slot, a direction none takes, a place none leads to.
        tab.add_exit()
        e = cm.state(app.project).locations[3].exits[3]
        self.assertEqual(tab.exit, 3)
        self.assertTrue(e.used)
        self.assertEqual(e.steps, 16)
        self.assertNotIn(e.destination, (3, 4, 2, 9))
        self.assertTrue(tab.add_button.instate(["disabled"]))       # four is all a place has
        # Removed: the slot's "no exit", nothing else of it touched.
        tab.remove_exit()
        self.assertEqual(cm.state(app.project).locations[3].exits[3].destination, cm.NO_EXIT)
        self.assertNotIn("3", tab.exits.get_children())
        # Reverted, one part of the place at a time.
        tab.vars["distance"].set(1234)
        app.update()
        names = [w.cget("text") for w in tab.changes.winfo_children()]
        self.assertIn("\u21ba Camera", names)
        button = next(w for w in tab.changes.winfo_children() if w.cget("text") == "\u21ba Arrow 3")
        button.invoke()
        self.assertEqual(cm.state(app.project).locations[3].exits[2], mf.locations()[3].exits[2])
        self.assertEqual(cm.state(app.project).locations[3].distance, 1234)
        next(w for w in tab.changes.winfo_children() if w.cget("text") == "\u21ba Arrow 4").invoke()
        next(w for w in tab.changes.winfo_children() if w.cget("text") == "\u21ba Camera").invoke()
        self.assertFalse(cm.changed(app.project, 3))
        self.assertEqual(tab.changes.winfo_children()[0].cget("text"), "As in the game")

    def test_camera_by_the_mouse(self):
        """The map dragged moves the camera so the ground under the mouse
        stays under it; a right drag turns it; the wheel zooms. One undo
        step each."""
        app, tab = self.app, self.app.map
        tab.select(0)
        tab.view.set("screen")
        tab.draw()
        start = tab.camera(0)
        ground = tab.ground(start, 100, 150)
        tab.press(mock.Mock(x=200, y=300))      # nothing of the screen's there: the map
        tab.motion(mock.Mock(x=260, y=320))
        tab.release(mock.Mock(x=260, y=320))
        moved = tab.camera(0)
        self.assertEqual(moved[:3], start[:3])
        after = tab.ground(moved, 130, 160)
        self.assertAlmostEqual(after[0], ground[0], delta=2)
        self.assertAlmostEqual(after[1], ground[1], delta=2)
        tab.press(mock.Mock(x=200, y=300), turn=True)
        tab.motion(mock.Mock(x=240, y=300))
        tab.release(mock.Mock(x=240, y=300))
        self.assertNotEqual(tab.camera(0)[1], moved[1])
        distance = tab.camera(0)[0]
        tab.wheel(mock.Mock(num=4, delta=0))
        self.assertLess(tab.camera(0)[0], distance)
        self.assertEqual(int(tab.vars["distance"].get()), tab.camera(0)[0])
        tab.wheel(mock.Mock(num=5, delta=0))
        self.assertTrue(cm.changed(app.project, 0))
        app.update()

    def test_edit_drag_save(self):
        app, tab = self.app, self.app.map
        self.assertEqual(tab.tree.item("0", "text"), "Place A")
        self.assertEqual(tab.tree.parent("13"), "town")
        tab.select(13)
        self.assertEqual(tab.vars["marker_x"].get(), mf.locations()[13].marker_x)
        # A field of the panel, then the direction and destination of arrow 2.
        tab.vars["marker_x"].set(250)
        self.assertEqual(cm.state(app.project).locations[13].marker_x, 250)
        self.assertTrue(app.dirty)
        tab.exits.selection_set("1")
        app.update()
        self.assertEqual(tab.exit, 1)
        tab.vars["up"].set(True)
        tab.vars["destination"].set(cm.label(app.project, 2))
        e = cm.state(app.project).locations[13].exits[1]
        self.assertEqual((e.buttons, e.destination), (0x9000, 2))
        self.assertEqual(list(tab.tree.item("13", "tags")), ["changed"])
        # Drag the marker 20 screen pixels right and 10 down (40 and 20 on the 2x canvas).
        loc = cm.state(app.project).locations[13]
        x, y = loc.marker_x * 2, loc.marker_y * 2
        before = (loc.marker_x, loc.marker_y)
        tab.press(mock.Mock(x=x, y=y))
        tab.motion(mock.Mock(x=x + 40, y=y + 20))
        tab.release(mock.Mock(x=x + 40, y=y + 20))
        loc = cm.state(app.project).locations[13]
        self.assertEqual((loc.marker_x, loc.marker_y), (before[0] + 20, before[1] + 10))
        # The overview draws, and a world site dragged moves its camera.
        tab.view.set("overview")
        tab.draw()
        sx, sy = tab.node(4)
        target = (cm.state(app.project).locations[4].target_x, cm.state(app.project).locations[4].target_z)
        tab.press(mock.Mock(x=round(sx), y=round(sy)))
        tab.motion(mock.Mock(x=round(sx) + 10, y=round(sy)))
        tab.release(mock.Mock(x=round(sx) + 10, y=round(sy)))
        self.assertEqual(tab.index, 4)
        loc = cm.state(app.project).locations[4]
        self.assertEqual(loc.target_x, target[0])
        self.assertNotEqual(loc.target_z, target[1])
        # A problem goes to its place.
        cm.state(app.project).locations[6].exits[0].steps = 0
        issue = next(i for i in app.conflicts.run() if i.area == "Map")
        app.go_to(issue)
        self.assertEqual(tab.index, 6)
        cm.state(app.project).locations[6].exits[0].steps = 16
        tab.reset_place()
        self.assertFalse(cm.changed(app.project, 6))
        # Saved: the patches of both packages, the bytes of the places as edited.
        out = Path(self.tmp.name) / "saved-map"
        app.project.info.id = "map-test"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        runs = data["data"][-1]["patch"]
        sectors = {int(r["at"], 16) // cm.SECTOR for r in runs}
        self.assertEqual(sectors, {s + cm.TABLE_OFFSET // cm.SECTOR for _, s in cm.PACKAGES})
        expected = mf.locations()
        expected[13].marker_x, expected[13].marker_y = before[0] + 20, before[1] + 10
        expected[13].exits[1].buttons, expected[13].exits[1].destination = 0x9000, 2
        expected[4] = cm.state(app.project).locations[4]
        retail = cm.state(app.project).retail
        self.assertEqual(runs, [r for name, sector in cm.PACKAGES
                                for r in cm.runs(retail.raw[name], cm.pack_table(expected), cm.table_offset(sector))])
        app.load_mod(out)
        self.assertEqual(cm.state(app.project).locations[13].marker_x, before[0] + 20)

    def test_bigger_interface(self):
        """At a bigger View > Interface size the screen grows with it, and a
        drag still lands where it is dropped."""
        app, tab = self.app, self.app.map
        with mock.patch.object(tab, "wanted_zoom", return_value=3):
            tab.rescaled()
        self.assertEqual(int(tab.canvas.cget("width")), 960)
        tab.select(13)
        tab.view.set("screen")
        tab.draw()
        loc = cm.state(app.project).locations[13]
        x, y = loc.marker_x * 3, loc.marker_y * 3
        tab.press(mock.Mock(x=x, y=y))
        tab.motion(mock.Mock(x=x + 30, y=y))
        tab.release(mock.Mock(x=x + 30, y=y))
        self.assertEqual(cm.state(app.project).locations[13].marker_x, loc.marker_x + 10)
        tab.view.set("overview")
        tab.draw()
        with mock.patch.object(tab, "wanted_zoom", return_value=2):
            tab.rescaled()
        self.assertEqual(int(tab.canvas.cget("width")), 640)

    def test_screen_picture(self):
        tab = self.app.map
        tab.select(0)
        tab.view.set("screen")
        tab.draw()
        self.assertTrue(tab.canvas.find_withtag("exit0"))
        self.assertIn("Drag an arrow", tab.caption.cget("text"))
        tab.select(12)
        self.assertTrue(tab.canvas.find_withtag("marker"))

    def test_pictures(self):
        from fm_editor import map_art, pngio
        tab = self.app.map
        tab.select(12)
        tab.show_pictures()
        dialog = tab.pictures
        self.app.update()
        self.assertIn("1 textures, 0 replaced", dialog.count.cget("text"))
        picture = Path(self.tmp.name) / "marker.png"
        pngio.write(picture, pngio.Image(64, 64, bytes((255, 0, 255, 255)) * 4096))
        dialog.sprite.set(map_art.SPRITES[0][0])
        dialog.import_sprite(str(picture))
        self.assertEqual(set(map_art.state(self.app.project).strips), {0})
        self.assertTrue(self.app.dirty)
        folder = Path(self.tmp.name) / "textures-out"
        dialog.export_textures(str(folder))
        dialog.import_textures(str(folder))
        self.assertIn("1 replaced", dialog.count.cget("text"))
        tab.draw()
        self.assertTrue(tab.canvas.find_withtag("marker"))
        dialog.revert_textures()
        dialog.revert_sprites()
        self.assertEqual(map_art.state(self.app.project).strips, {})
        dialog.destroy()
        # A new project after the dialog was closed: the tab fills again.
        from fm_editor.model import Project
        self.app.dirty = False
        self.app.set_project(Project(self.app.retail))
        self.assertEqual(sum(len(tab.tree.get_children(g)) for g in tab.tree.get_children()), cm.COUNT)
        self.assertEqual(tab.heading.cget("text"), cm.name(self.app.project, tab.index))

    def test_dark(self):
        self.app.theme.use(True)
        self.app.map.draw()
        self.app.update()
        self.app.theme.use(False)


if __name__ == "__main__":
    unittest.main()
