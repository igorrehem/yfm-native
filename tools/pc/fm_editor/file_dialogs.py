"""Every Open, Save as and folder chooser the editor shows, through one place.

On Windows and macOS Tk shows the system's own dialogs, which size
themselves: the calls go straight to tkinter.filedialog. On Linux (X11, and
XWayland) Tk draws its own dialog (tkfbox.tcl) at the size its contents ask
for, about 470x300 pixels whatever the window or View > Interface size: a
small box in the middle of a big editor. There the dialog is made about two
thirds of the editor's window (never under MIN logical pixels at the
interface size, never over the screen), centered on the window; a size the
user drags it to is remembered (settings "file_dialog_size", in logical
pixels, so it follows the interface size). Its text already follows the
interface size: it uses the named fonts zoom.py resizes.

How: Tk makes the dialog (a toplevel, <parent>.__tk_filedialog or
.__tk_choosedir), then lays it out (::tk::PlaceWindow's update idletasks)
before showing it, centered on its parent by its requested size. An idle
callback queued just before the call runs in that layout: it fixes the
dialog's requested size (pack propagate off, -width/-height), so Tk centers
and shows it at that size, with no jump. Should the dialog not be there by
then (another Tk), a short timer resizes it once it shows."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

from . import settings
from .widgets import ui_scale

FRACTION = 0.65             # of the editor window's width and height
MIN = (900, 600)            # logical pixels (96 dpi, interface size 100%)
LEAST = (400, 300)          # the smallest remembered size kept, logical
MARGIN = 40                 # screen pixels kept free around the dialog
SETTING = "file_dialog_size"
POLL_MS = 15
POLL_TRIES = 200            # 3 s: then the dialog keeps Tk's size
IDLE_TRIES = 50


def askopenfilename(**options):
    return _ask(filedialog.askopenfilename, "__tk_filedialog", options)


def askopenfilenames(**options):
    return _ask(filedialog.askopenfilenames, "__tk_filedialog", options)


def asksaveasfilename(**options):
    return _ask(filedialog.asksaveasfilename, "__tk_filedialog", options)


def askdirectory(**options):
    return _ask(filedialog.askdirectory, "__tk_choosedir", options)


# --- the geometry -------------------------------------------------------------

def dialog_size(window: tuple[int, int], screen: tuple[int, int], scale: float,
                remembered=None) -> tuple[int, int]:
    """The dialog's size in screen pixels: the remembered one (logical pixels
    times scale) or FRACTION of the editor's window, at least MIN at the
    scale; never bigger than the screen less MARGIN on each side."""
    room = (max(1, screen[0] - 2 * MARGIN), max(1, screen[1] - 2 * MARGIN))
    least = parse_remembered(remembered)
    if least is not None:
        wanted = [round(n * scale) for n in least]
    else:
        wanted = [max(round(w * FRACTION), round(m * scale)) for w, m in zip(window, MIN)]
    return min(wanted[0], room[0]), min(wanted[1], room[1])


def centered(size: tuple[int, int], window: tuple[int, int, int, int],
             screen: tuple[int, int]) -> tuple[int, int]:
    """Where a dialog of `size` sits centered on `window` (x, y, width,
    height), kept on the screen."""
    x = window[0] + (window[2] - size[0]) // 2
    y = window[1] + (window[3] - size[1]) // 2
    x = max(0, min(x, screen[0] - size[0]))
    y = max(0, min(y, screen[1] - size[1]))
    return x, y


def parse_remembered(value):
    """A stored size ([width, height], logical pixels) or None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in value):
        return None
    if value[0] < LEAST[0] or value[1] < LEAST[1] or value[0] > 20000 or value[1] > 20000:
        return None
    return int(value[0]), int(value[1])


def to_remember(shown: tuple[int, int], placed: tuple[int, int], scale: float):
    """The logical size to store once the dialog closes: None when the user
    left it at the size it was given (a couple of pixels either way)."""
    if all(abs(s - p) <= 2 for s, p in zip(shown, placed)):
        return None
    size = [max(least, round(n / scale)) for n, least in zip(shown, LEAST)]
    return size


# --- the call -------------------------------------------------------------------

def _x11(widget) -> bool:
    try:
        return widget.tk.call("tk", "windowingsystem") == "x11"
    except tk.TclError:
        return False


def _ask(function, name: str, options: dict):
    parent = options.get("parent") or tk._default_root
    if parent is None or not _x11(parent):
        return function(**options)
    try:
        top = parent.winfo_toplevel()
    except tk.TclError:
        return function(**options)
    # Centered on the editor's window, not the tab that asked: Tk centers
    # the dialog on its parent.
    options = dict(options, parent=top)
    sizer = _Sizer(top, name)
    sizer.start()
    try:
        return function(**options)
    finally:
        sizer.finish()


class _Sizer:
    def __init__(self, top, name):
        self.top = top
        self.path = (".%s" % name) if str(top) == "." else f"{top}.{name}"
        self.job = None
        self.tries = 0
        self.done = False
        self.placed = None
        self.scale = 1.0

    def exists(self) -> bool:
        return bool(int(self.top.tk.call("winfo", "exists", self.path)))

    def start(self):
        self.job = self.top.after_idle(self.idle)

    def idle(self):
        """In Tk's layout before it shows the dialog."""
        self.job = None
        if self.done:
            return
        if self.exists():
            self.apply()
            return
        self.tries += 1
        if self.tries < IDLE_TRIES:
            self.job = self.top.after_idle(self.idle)
        else:
            self.tries = 0
            self.job = self.top.after(POLL_MS, self.poll)

    def poll(self):
        """The fallback: the dialog was not there in the layout."""
        self.job = None
        if self.done:
            return
        if self.exists() and int(self.top.tk.call("winfo", "ismapped", self.path)):
            self.apply()
            return
        self.tries += 1
        if self.tries < POLL_TRIES:
            self.job = self.top.after(POLL_MS, self.poll)

    def window_box(self):
        """The editor's window on the screen; the screen when it is hidden."""
        top = self.top
        if top.winfo_ismapped():
            return (top.winfo_rootx(), top.winfo_rooty(), top.winfo_width(), top.winfo_height())
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        return (0, 0, sw, sh)

    def apply(self):
        top, call, w = self.top, self.top.tk.call, self.path
        try:
            self.scale = ui_scale(top)
            screen = (top.winfo_screenwidth(), top.winfo_screenheight())
            box = self.window_box()
            size = dialog_size(box[2:], screen, self.scale, settings.load().get(SETTING))
            x, y = centered(size, box, screen)
            # The requested size: what ::tk::PlaceWindow centers and shows.
            call("pack", "propagate", w, 0)
            call(w, "configure", "-width", size[0], "-height", size[1])
            call("wm", "minsize", w, *(min(s, round(n * self.scale)) for s, n in zip(size, LEAST)))
            call("wm", "geometry", w, f"{size[0]}x{size[1]}+{x}+{y}")
            self.placed = size
        except tk.TclError:
            self.placed = None

    def finish(self):
        """The dialog closed (Tk withdraws it, keeping it for the next
        time): its size, if the user changed it, for the next time."""
        self.done = True
        if self.job is not None:
            try:
                self.top.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.placed is None:
            return
        try:
            if not self.exists():
                return
            shown = (int(self.top.tk.call("winfo", "width", self.path)),
                     int(self.top.tk.call("winfo", "height", self.path)))
        except tk.TclError:
            return
        size = to_remember(shown, self.placed, self.scale)
        if size is not None:
            settings.save(SETTING, size)
