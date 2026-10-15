"""The first window size: the monitor under the mouse, not Tk's whole screen."""
import sys
import unittest
from unittest import mock

from fm_editor import screen

try:
    import tkinter as tk
except ImportError:         # pragma: no cover
    tk = None

# A 1920x1440 monitor at 125% (2304x1728 to X) left of a 4K one, lower down.
LEFT = (0, 360, 2304, 1728, False)
RIGHT = (2304, 0, 3840, 2160, True)


class PickTest(unittest.TestCase):
    def test_monitor_under_the_pointer(self):
        self.assertEqual(screen.pick([LEFT, RIGHT], (1000, 1000)), LEFT[:4])
        self.assertEqual(screen.pick([LEFT, RIGHT], (4000, 100)), RIGHT[:4])
        self.assertEqual(screen.pick([LEFT, RIGHT], (2304, 0)), RIGHT[:4])

    def test_pointer_nowhere_takes_primary_then_first(self):
        self.assertEqual(screen.pick([LEFT, RIGHT], (100, 100)), RIGHT[:4])    # above LEFT
        self.assertEqual(screen.pick([LEFT], (-5, -5)), LEFT[:4])
        self.assertIsNone(screen.pick([], (0, 0)))


class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
        try:
            cls.root = tk.Tk()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_geometry_fits_the_monitor_it_opens_on(self):
        from fm_editor.app import initial_geometry
        with mock.patch("fm_editor.app.px", lambda w, n: n * 3 // 2):    # 144 dpi
            self.assertEqual(initial_geometry(self.root, LEFT[:4]), "2073x1440+115+504")
            self.assertEqual(initial_geometry(self.root, RIGHT[:4]), "2400x1440+3024+360")
            self.assertEqual(initial_geometry(self.root, (0, 0, 1920, 1040)), "1728x936+96+52")
            # A monitor left of the primary one (Windows: negative x).
            self.assertEqual(initial_geometry(self.root, (-1920, 0, 1920, 1040)), "1728x936+-1824+52")

    def test_failure_falls_back_to_the_screen(self):
        whole = (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        target = "_windows_work_area" if sys.platform == "win32" else "_x11_monitors"
        with mock.patch.object(screen, target, side_effect=OSError("no library")):
            self.assertEqual(screen.work_area(self.root), whole)

    def test_real_lookup_works_here(self):
        """The platform's own call runs (Windows CI: GetMonitorInfoW; Linux:
        XRandR under Xvfb) instead of quietly falling back."""
        if sys.platform == "win32":
            found = screen._windows_work_area()
        elif self.root.tk.call("tk", "windowingsystem") == "x11":
            try:
                found = screen.pick(screen._x11_monitors(), self.root.winfo_pointerxy())
            except OSError as problem:
                self.skipTest(f"no XRandR here: {problem}")
        else:
            self.skipTest("Tk's screen is used here")
        self.assertIsNotNone(found)
        x, y, w, h = found
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertEqual(screen.work_area(self.root), found)


if __name__ == "__main__":
    unittest.main()
