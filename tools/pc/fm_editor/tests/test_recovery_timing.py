"""Recovery copies on a timer (File > Recovery copy), written on a thread of
their own, and undo snapshots that share pictures instead of storing them."""
import copy
import gc
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter  # noqa: F401
except ImportError:     # a Python built without Tk: editing needs it
    raise unittest.SkipTest("this Python has no Tk")

from fm_editor import art, editing, history, manifest, pngio, recovery, settings
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture
from fm_editor.tests.test_gui import GuiCase


def picture(seed, w=102, h=96):
    return pngio.Image(w, h, bytes((seed + i) & 255 if i % 4 != 3 else 255 for i in range(w * h * 4)))


class IntervalTest(unittest.TestCase):
    def test_setting_values(self):
        self.assertEqual(editing.recovery_minutes(None), editing.RECOVERY_DEFAULT)
        self.assertEqual(editing.RECOVERY_DEFAULT, 5)
        for bad in (7, "5", 5.0, True, -1):
            self.assertEqual(editing.recovery_minutes(bad), 5, bad)
        for good in editing.RECOVERY_CHOICES:
            self.assertEqual(editing.recovery_minutes(good), good)
        self.assertEqual([editing.recovery_label(m) for m in editing.RECOVERY_CHOICES],
                         ["Off", "Every minute", "Every 5 minutes", "Every 10 minutes", "Every 30 minutes"])

    def test_delay(self):
        delay = editing.recovery_delay
        self.assertIsNone(delay(0, 1000.0, None, 900.0))            # off
        self.assertEqual(delay(5, 1000.0, None, None), 300.0)       # from now
        self.assertEqual(delay(5, 1000.0, None, 900.0), 200.0)      # from the first change
        self.assertEqual(delay(5, 1000.0, 950.0, 900.0), 250.0)     # from the last copy
        self.assertEqual(delay(1, 1000.0, 100.0, 990.0), 0.0)       # long overdue: now
        self.assertEqual(delay(30, 0.0, None, 0.0), 1800.0)


class SharedPicturesTest(unittest.TestCase):
    def setUp(self):
        self.project = Project(fixture().game())

    def test_image_copies_are_itself(self):
        image = picture(1)
        self.assertIs(copy.deepcopy(image), image)
        self.assertIs(copy.copy(image), image)
        self.assertEqual(image.digest(), picture(1).digest())
        self.assertNotEqual(image.digest(), picture(2).digest())
        self.assertNotEqual(pngio.Image(2, 1, bytes(8)).digest(), pngio.Image(1, 2, bytes(8)).digest())

    def test_snapshots_share_pictures_and_undo_them(self):
        p = self.project
        first, second = picture(10), picture(20)
        plain = len(history.Snapshot(p).data)
        art.set_image(p, 1, "art", first)
        h = history.History(p)
        stored = art.replacement_image(p, 1, "art")
        self.assertIn(stored, h.items[0].blobs)
        self.assertLess(len(h.items[0].data) - plain, 2000, "the picture is not in the pickle")
        p.cards[1].name = "Text only"
        h.record(p)
        self.assertIs(h.items[1].blobs[h.items[1].blobs.index(stored)], stored, "shared, not copied")
        art.set_image(p, 1, "art", second)
        h.record(p)
        changed = art.replacement_image(p, 1, "art")
        self.assertNotEqual(changed, stored)
        p = h.move(-1, p)
        self.assertEqual(art.replacement_image(p, 1, "art"), stored)
        self.assertFalse(h.record(p), "the same picture is no edit")
        p = h.move(1, p)
        self.assertEqual(art.replacement_image(p, 1, "art"), changed)

    def test_history_counts_pictures_only_old_states_hold(self):
        p = self.project
        art.set_image(p, 1, "art", picture(1, 408, 384))
        h = history.History(p)
        size = sum(history._blob_size(blob) for blob in h.items[0].blobs)    # the picture and its thumbnail
        self.assertGreater(size, 600_000)
        h.max_bytes = size * 2 + 200 * 1024
        base = h.size()
        self.assertLess(base, size, "the picture the project holds now costs the history nothing")
        for seed in range(2, 6):
            art.set_image(p, 1, "art", picture(seed, 408, 384))
            h.record(p)
        # Each older picture is a picture's worth: no more than two kept.
        self.assertLessEqual(h.size(), h.max_bytes)
        self.assertEqual(len(h.items), 3)
        p.cards[1].name = "Many text edits"
        for i in range(10):
            p.cards[2].name = f"Name {i}"
            h.record(p)
        self.assertGreater(len(h.items), 3, "text edits cost no pictures")


class WriterTest(unittest.TestCase):
    def setUp(self):
        self.project = Project(fixture().game())
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(settings, "path", return_value=Path(tmp.name) / "config" / "settings.json")
        patch.start()
        self.addCleanup(patch.stop)

    def test_prepared_job_ignores_later_edits(self):
        r = recovery.Recovery()
        self.project.cards[1].name = "At the copy"
        job = r.prepare(self.project, {"cards": {"current": 1}})
        self.project.cards[1].name = "After it"
        recovery.Writer(r, job).start().wait()
        row = next(row for row in recovery.records() if row[0].parent == r.folder)
        self.assertEqual(manifest.open_mod(self.project.retail, row[1])[0].cards[1].name, "At the copy")
        self.assertEqual(row[2]["forms"], {"cards": {"current": 1}})

    def test_cancelled_writer_removes_its_copy(self):
        r = recovery.Recovery()
        job = r.prepare(self.project)
        gate = threading.Event()
        real = r.write_job

        def slow(j):
            gate.wait(5)
            return real(j)
        with mock.patch.object(r, "write_job", side_effect=slow):
            writer = recovery.Writer(r, job).start()
            self.addCleanup(writer.wait)        # a failure here leaves no writer behind
            self.addCleanup(gate.set)           # (cleanups run last first)
            self.assertFalse(writer.done())
            writer.cancel()
            r.clear()
            gate.set()
            writer.wait()
        self.assertIsNone(writer.error)
        self.assertFalse(r.folder.exists())

    def test_writer_reports_errors(self):
        r = recovery.Recovery()
        with mock.patch.object(r, "write_job", side_effect=OSError("disk full")):
            writer = recovery.Writer(r, r.prepare(self.project)).start()
            writer.wait()
        self.assertIsInstance(writer.error, OSError)

    def test_no_collection_on_the_writers_thread(self):
        """The cycle collector waits while a copy is written: on that thread
        it would finalize Tk objects (tkinter must not call Tcl from there),
        and the window's thread turns it back on, by done() or wait()."""
        self.assertTrue(gc.isenabled())
        r = recovery.Recovery()
        real = r.write_job
        for finish in ("done", "wait"):
            with self.subTest(finish=finish):
                gate, seen = threading.Event(), []

                def slow(job):
                    seen.append(gc.isenabled())
                    gate.wait(5)
                    return real(job)
                with mock.patch.object(r, "write_job", side_effect=slow):
                    writer = recovery.Writer(r, r.prepare(self.project)).start()
                    try:
                        self.assertFalse(gc.isenabled())
                        self.assertFalse(writer.done())
                        self.assertFalse(gc.isenabled(), "still writing")
                        gate.set()
                        if finish == "done":
                            deadline = time.monotonic() + 10
                            while not writer.done() and time.monotonic() < deadline:
                                time.sleep(0.01)
                            self.assertTrue(gc.isenabled())
                    finally:
                        # Whatever failed: no writer left running, nor the
                        # collector off for the next round or test.
                        gate.set()
                        writer.wait()
                self.assertEqual(seen, [False])
                self.assertTrue(gc.isenabled())
                writer.wait()                   # once back on, it stays so
                self.assertTrue(gc.isenabled())
        # A collector turned off by someone else is left off.
        gc.disable()
        try:
            recovery.Writer(r, r.prepare(self.project)).start().wait()
            self.assertFalse(gc.isenabled())
        finally:
            gc.enable()


CARD = 300


class TimerGuiTest(GuiCase):
    def session(self):
        return [row for row in recovery.records() if row[0].parent == self.app.recovery.folder]

    def edit(self, name):
        self.app.project.cards[CARD].name = name      # not the card the Cards form shows
        self.app.changed()
        self.pause()

    def wait_writer(self):
        deadline = time.monotonic() + 20
        while self.app._recovery_writer is not None and time.monotonic() < deadline:
            self.app.update()
            self.app.after(20)
        self.assertIsNone(self.app._recovery_writer)

    def test_an_edit_waits_for_the_interval(self):
        app = self.app
        self.assertEqual(app.recovery_choice.get(), 5)
        self.edit("First")
        self.app.after(2200)        # the old copy came two seconds after an edit
        app.update()
        self.assertEqual(self.session(), [])
        self.assertIsNotNone(app._recovery_job)
        due = app.tk.call("after", "info", app._recovery_job)
        self.assertTrue(due)
        self.assertTrue(app._recovery_stale)
        # When it is due: written on another thread, the window going on.
        with mock.patch.object(editing.time, "monotonic", return_value=time.monotonic() + 301):
            app._autosave_due()
        self.assertIsNotNone(app._recovery_writer)
        self.wait_writer()
        rows = self.session()
        self.assertEqual(len(rows), 1)
        self.assertEqual(manifest.open_mod(app.retail, rows[0][1])[0].cards[CARD].name, "First")
        self.assertFalse(app._recovery_stale)
        self.assertIsNone(app._recovery_job, "nothing new to copy")
        # The next change: due five minutes after that copy, not sooner.
        self.edit("Second")
        self.assertIsNotNone(app._recovery_job)
        self.assertGreater(editing.recovery_delay(5, time.monotonic(), app._recovery_copied, app._recovery_since), 290)

    def test_off_and_remembered(self):
        app = self.app
        app.recovery_choice.set(0)
        app.choose_recovery()
        self.assertEqual(json.loads(self.settings.read_text())["recovery_minutes"], 0)
        self.edit("No copies")
        self.assertIsNone(app._recovery_job)
        app.apply_edits()
        self.assertIsNone(app._recovery_writer)
        self.assertEqual(self.session(), [])
        app.recovery_choice.set(10)
        app.choose_recovery()
        self.assertIsNotNone(app._recovery_job, "still unsaved: counting down now")
        self.assertEqual(json.loads(self.settings.read_text())["recovery_minutes"], 10)
        app.dirty = False
        app.destroy()
        from fm_editor.app import App
        self.app = App(ask=False, autostart=False)
        self.app.withdraw()
        self.assertEqual(self.app.recovery_choice.get(), 10)

    def test_apply_writes_only_when_the_copy_is_old(self):
        app = self.app
        self.edit("Applied")
        app.apply_edits()               # no copy yet
        self.assertIsNotNone(app._recovery_writer)
        self.wait_writer()
        self.assertEqual(len(self.session()), 1)
        self.edit("Applied again")
        app.apply_edits()               # the copy is seconds old
        self.assertIsNone(app._recovery_writer)
        self.assertTrue(app._recovery_stale)
        app._recovery_copied -= editing.RECOVERY_ON_APPLY + 1
        app.apply_edits()
        self.assertIsNotNone(app._recovery_writer)
        self.wait_writer()
        self.assertEqual(manifest.open_mod(app.retail, self.session()[0][1])[0].cards[CARD].name, "Applied again")

    def test_one_copy_at_a_time_and_save_cancels(self):
        app = self.app
        self.edit("Busy")
        gate = threading.Event()
        real = app.recovery.write_job

        def slow(job):
            gate.wait(10)
            return real(job)
        with mock.patch.object(app.recovery, "write_job", side_effect=slow) as write:
            app.autosave(wait=False)
            first = app._recovery_writer
            self.edit("While busy")
            app.autosave(wait=False)        # not a second writer
            self.assertIs(app._recovery_writer, first)
            self.assertEqual(write.call_count, 1)
            folder = Path(self.tmp.name) / "timer-save"
            with mock.patch("fm_editor.file_dialogs.askdirectory", return_value=str(folder)):
                self.assertTrue(app.save())
            gate.set()
            self.wait_writer()
        self.assertFalse(app.recovery.folder.exists(), "saved: the copy written meanwhile is gone")
        self.assertIsNone(app._recovery_job)

    def test_failed_save_writes_a_copy(self):
        app = self.app
        self.edit("Unsaved")
        with mock.patch.object(recovery, "backup", side_effect=OSError("no space")), \
                mock.patch("fm_editor.app.messagebox.showerror"), \
                mock.patch("fm_editor.file_dialogs.askdirectory",
                           return_value=str(Path(self.tmp.name) / "failing-save")):
            self.assertFalse(app.save())
        self.assertIsNotNone(app._recovery_writer)
        self.wait_writer()
        self.assertEqual(len(self.session()), 1)


if __name__ == "__main__":
    unittest.main()
