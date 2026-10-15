"""file_dialogs.py: the Linux Tk file dialog's size, and every dialog going
through it. The window tests are skipped where Tk cannot start."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk: file_dialogs needs it
    raise unittest.SkipTest("this Python has no Tk")

from fm_editor import file_dialogs as fd

EDITOR = Path(fd.__file__).resolve().parent


class GeometryTest(unittest.TestCase):

    def test_two_thirds_of_a_big_window(self):
        self.assertEqual(fd.dialog_size((2400, 1300), (2560, 1440), 1.25), (1560, 845))

    def test_never_under_the_least_at_the_scale(self):
        self.assertEqual(fd.dialog_size((1000, 700), (2560, 1440), 1.0), (900, 600))
        self.assertEqual(fd.dialog_size((1000, 700), (3840, 2160), 2.0), (1800, 1200))

    def test_never_over_the_screen(self):
        self.assertEqual(fd.dialog_size((1280, 720), (1280, 720), 2.0),
                         (1280 - 2 * fd.MARGIN, 720 - 2 * fd.MARGIN))

    def test_remembered_size_follows_the_scale(self):
        self.assertEqual(fd.dialog_size((2400, 1300), (2560, 1440), 1.5, [1000, 700]), (1500, 1050))
        # Clamped to the screen all the same.
        self.assertEqual(fd.dialog_size((2400, 1300), (1920, 1080), 2.0, [1000, 700]),
                         (1920 - 2 * fd.MARGIN, 1080 - 2 * fd.MARGIN))

    def test_bad_remembered_sizes_are_ignored(self):
        for bad in (None, "900x600", [900], [900, "600"], [True, 600], [10, 10], [900, 600, 1], [90000, 600]):
            self.assertIsNone(fd.parse_remembered(bad), bad)
            self.assertEqual(fd.dialog_size((2400, 1300), (2560, 1440), 1.0, bad), (1560, 845))

    def test_centered_on_the_window_and_kept_on_screen(self):
        self.assertEqual(fd.centered((1000, 600), (100, 50, 2000, 1200), (2560, 1440)), (600, 350))
        self.assertEqual(fd.centered((1000, 600), (-500, -400, 600, 400), (2560, 1440)), (0, 0))
        self.assertEqual(fd.centered((1000, 600), (2000, 1200, 600, 400), (2560, 1440)), (1560, 840))

    def test_size_to_remember(self):
        self.assertIsNone(fd.to_remember((1560, 845), (1560, 845), 1.25))
        self.assertIsNone(fd.to_remember((1561, 843), (1560, 845), 1.25))
        self.assertEqual(fd.to_remember((1250, 1000), (1560, 845), 1.25), [1000, 800])
        self.assertEqual(fd.to_remember((100, 100), (1560, 845), 1.0), list(fd.LEAST))


class RoutingTest(unittest.TestCase):

    def test_no_module_calls_tkinter_filedialog_itself(self):
        for path in sorted(EDITOR.glob("*.py")):
            if path.name == "file_dialogs.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\bfiledialog\b", text), f"{path.name} uses tkinter.filedialog")

    def test_native_dialogs_get_the_call_unchanged(self):
        parent = mock.Mock()
        parent.tk.call.return_value = "win32"
        for name in ("askopenfilename", "asksaveasfilename", "askdirectory", "askopenfilenames"):
            options = dict(parent=parent, title="T", filetypes=[("PNG", "*.png")], initialdir="/x",
                           defaultextension=".png", initialfile="a.png")
            with mock.patch("tkinter.filedialog." + name, return_value="chosen") as real:
                self.assertEqual(getattr(fd, name)(**options), "chosen")
            real.assert_called_once_with(**options)
            parent.winfo_toplevel.assert_not_called()


class DialogWindowTest(unittest.TestCase):
    """The real Tk dialog, on a display."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as problem:
            self.skipTest(f"no display for Tk: {problem}")
        self.addCleanup(self.root.destroy)
        if self.root.tk.call("tk", "windowingsystem") != "x11":
            self.skipTest("Tk's own dialog is the X11 one")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = tmp.name
        stored = Path(tmp.name) / "config" / "settings.json"
        patcher = mock.patch("fm_editor.settings.path", lambda: stored)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root.fm_desktop_scale = 1.0
        self.root.geometry("1800x1100+20+20")
        self.frame = tk.Frame(self.root)
        self.frame.pack(side="left", fill="both", expand=True)
        self.root.update()

    def open(self, function, dialog, then=None, **options):
        """`function` from a tab (a frame); its dialog's geometry while shown."""
        seen = {}
        path = "." + dialog

        def look():
            call = self.root.tk.call
            if not int(call("winfo", "ismapped", path)):
                self.root.after(20, look)
                return
            self.root.update_idletasks()
            seen["size"] = (int(call("winfo", "width", path)), int(call("winfo", "height", path)))
            seen["at"] = (int(call("winfo", "rootx", path)), int(call("winfo", "rooty", path)))
            if then:
                then(path)
            call("set", "::tk::Priv(selectFilePath)", "")

        self.root.after(50, look)
        result = function(parent=self.frame, title="Pick", initialdir=self.folder, **options)
        return result, seen

    def test_open_save_and_folder_dialogs_are_sized_and_centered(self):
        width, height = self.root.winfo_width(), self.root.winfo_height()
        want = fd.dialog_size((width, height), (self.root.winfo_screenwidth(), self.root.winfo_screenheight()),
                              1.0)
        cases = ((fd.askopenfilename, "__tk_filedialog", {"filetypes": [("PNG", "*.png")]}),
                 (fd.asksaveasfilename, "__tk_filedialog", {"defaultextension": ".png"}),
                 (fd.askdirectory, "__tk_choosedir", {}))
        for function, dialog, options in cases:
            with self.subTest(function.__name__):
                result, seen = self.open(function, dialog, **options)
                self.assertFalse(result)        # cancelled
                self.assertEqual(seen["size"], want)
                x, y = fd.centered(want, (self.root.winfo_rootx(), self.root.winfo_rooty(), width, height),
                                   (self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
                self.assertLessEqual(abs(seen["at"][0] - x), 2)
                self.assertLessEqual(abs(seen["at"][1] - y), 2)

    def test_a_size_the_user_drags_to_is_remembered(self):
        from fm_editor import settings
        if self.root.winfo_screenwidth() < 1100 or self.root.winfo_screenheight() < 800:
            self.skipTest("the screen is too small to drag the dialog to 1000x700")

        def drag(path):
            self.root.tk.call("wm", "geometry", path, "1000x700")
            self.root.update()

        self.open(fd.askopenfilename, "__tk_filedialog", then=drag)
        self.assertEqual(settings.load().get(fd.SETTING), [1000, 700])
        _, seen = self.open(fd.askopenfilename, "__tk_filedialog")
        self.assertEqual(seen["size"], (1000, 700))
        # Left as it was given: nothing new stored.
        self.assertEqual(settings.load().get(fd.SETTING), [1000, 700])


if __name__ == "__main__":
    unittest.main()
