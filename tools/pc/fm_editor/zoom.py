"""View > Interface size: how big the editor draws its text, lists and
pictures, on top of the desktop's own scale (widgets.desktop_scale).

"Fit to window" (the default) grows everything with the window: the layout
is made for 1600x960 at the desktop's scale, and a window bigger than that
in both directions (maximized on a 4K monitor, say) draws everything that
much bigger, up to 3x. The fixed sizes keep one size whatever the window.

A change is applied live, not at the next start: the named fonts (every
font the editor uses is one, widgets.ui_font) take their sizes times the
factor, so text and everything sized in characters follow by themselves;
then widgets.px (root.fm_zoom) and the theme's pixel sizes, the lists'
column widths and the labels' wrap lengths, and the tabs that draw
pictures (their rescaled()) are told."""
from __future__ import annotations

import _tkinter
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import settings, still
from .widgets import desktop_scale

FIT = "fit"
SIZES = (100, 125, 150, 175, 200, 250, 300)    # the fixed sizes, in percent
DESIGN = (1600, 960)        # the window the layout is made for, at 96 dpi
MOST = 3.0                  # Fit to window grows no further
SETTLE = 80                 # ms without a new size before Fit to window looks again


def parse(value):
    """A stored setting: FIT or one of SIZES."""
    if value == FIT:
        return FIT
    try:
        value = int(value)
    except (TypeError, ValueError):
        return FIT
    return value if value in SIZES else FIT


def fit_factor(width: int, height: int, desktop: float) -> float:
    """The factor for a window this big: its smaller stretch over DESIGN,
    in steps of 1/8 (no jitter while dragging), never below 1."""
    stretch = min(width / (DESIGN[0] * desktop), height / (DESIGN[1] * desktop))
    return min(MOST, max(1.0, int(stretch * 8 + 0.01) / 8))


def font_size(size: int, factor: float) -> int:
    """A font's size times the factor, its sign (points or pixels) kept."""
    sign = -1 if size < 0 else 1
    return sign * max(1, int(abs(size) * factor + 0.5))


class Zoom:
    def __init__(self, app):
        self.app = app
        self.desktop = desktop_scale(app)       # measured before any font grows
        self.factor = 1.0
        app.fm_zoom = 1.0
        # Every named font as Tk made it (the Windows faces set): what the
        # factor multiplies. widgets.ui_font's own add themselves.
        self.base = {name: int(tkfont.nametofont(name, root=app).cget("size"))
                     for name in tkfont.names(app)}
        app.fm_font_base = self.base
        self.mode = parse(settings.load().get("ui_size"))
        self.choice = tk.StringVar(app, value=str(self.mode))
        self.job = None
        self.menu = None
        self.seen = None        # the window's size Fit to window last looked at
        # The window's own size only: bound on the window, <Configure>
        # would run for each of its widgets too (they all carry its tag).
        tag = f"Zoom:{app}"
        app.bindtags((tag,) + app.bindtags())
        app.bind_class(tag, "<Configure>", self.resized)

    # --- the menu ------------------------------------------------------------------

    def build_menu(self, view):
        """Interface size's entries, in View."""
        menu = self.menu = tk.Menu(view, tearoff=False)
        menu.add_radiobutton(label=self.fit_label(), variable=self.choice, value=FIT,
                             command=lambda: self.choose(FIT))
        menu.add_separator()
        for size in SIZES:
            menu.add_radiobutton(label=f"{size}%", variable=self.choice, value=str(size),
                                 command=lambda s=size: self.choose(s))
        view.add_cascade(label="Interface size", menu=menu)
        view.add_command(label="Larger", accelerator="Ctrl++", command=lambda: self.step(1))
        view.add_command(label="Smaller", accelerator="Ctrl+-", command=lambda: self.step(-1))
        view.add_command(label="Fit to window", accelerator="Ctrl+0", command=lambda: self.choose(FIT))
        app = self.app
        for keys, delta in ((("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"), 1),
                            (("<Control-minus>", "<Control-KP_Subtract>"), -1)):
            for key in keys:
                app.bind(key, lambda e, d=delta: app.shortcut(lambda: self.step(d)))
        for key in ("<Control-0>", "<Control-KP_0>"):
            app.bind(key, lambda e: app.shortcut(lambda: self.choose(FIT)))

    def fit_label(self):
        return f"Fit to window ({round(self.factor * 100)}%)" if self.mode == FIT else "Fit to window"

    # --- choosing ----------------------------------------------------------------------

    def choose(self, mode):
        """A size from the menu or the keys, remembered for the next start."""
        self.mode = mode
        self.seen = None        # look at the window afresh
        self.choice.set(str(mode))
        self.update()
        problem = settings.save("ui_size", mode)
        if problem:
            self.app.say(f"Could not remember the interface size: {problem}")
        else:
            self.app.say(f"Interface size: {self.fit_label() if mode == FIT else f'{mode}%'}")

    def step(self, delta):
        """The next fixed size up or down from the size drawn now."""
        now = round(self.factor * 100)
        if delta > 0:
            bigger = [s for s in SIZES if s > now]
            self.choose(bigger[0] if bigger else SIZES[-1])
        else:
            smaller = [s for s in SIZES if s < now]
            self.choose(smaller[-1] if smaller else SIZES[0])

    def wanted(self) -> float:
        if self.mode != FIT:
            return self.mode / 100
        app = self.app
        if not app.winfo_ismapped():
            return self.factor      # its <Configure> on showing says
        size = (app.winfo_width(), app.winfo_height())
        # A new size makes the menu bar taller or shorter, which takes from
        # the window's height and asked again, at an edge between two sizes
        # going back and forth: a change smaller than a few menu bars keeps
        # the size it has.
        near = round(48 * self.desktop * self.factor)
        if self.seen is not None and all(abs(now - then) <= near for now, then in zip(size, self.seen)):
            return self.factor
        self.seen = size
        return fit_factor(*size, self.desktop)

    def resized(self, event):
        """The window's size changed. A jump (maximized, restored) is
        followed at once, before Tk lays the window out at the old size
        first, which took as long again; a drag once it settles."""
        if self.mode != FIT:
            return
        if self.job is not None:
            self.app.after_cancel(self.job)
            self.job = None
        if self.seen is not None and (abs(event.width - self.seen[0]) > self.seen[0] // 4 or
                                      abs(event.height - self.seen[1]) > self.seen[1] // 4):
            self.update()
            return
        self.job = self.app.after(SETTLE, self.settled)

    def settled(self):
        self.job = None
        self.update()

    # --- applying -----------------------------------------------------------------------

    def update(self):
        factor = self.wanted()
        if abs(factor - self.factor) > 1e-6:
            self.apply(factor)
        if self.menu is not None:
            self.menu.entryconfigure(0, label=self.fit_label())

    def apply(self, factor):
        """Everything at the factor, laid out under a cover: Tk draws as it
        lays out, which showed the window changing a piece at a time. The
        cover shows the window as it was (still.py), or, where it cannot,
        its background."""
        app = self.app
        cover = None
        if app.winfo_ismapped():
            cover = still.cover(app)
            if cover is None:
                # A classic frame: the X server paints its background the
                # moment it maps, before Tk draws anything under it.
                cover = tk.Frame(app, background=ttk.Style(app).lookup("TFrame", "background") or "#d9d9d9",
                                 borderwidth=0, highlightthickness=0)
                cover.place(x=0, y=0, relwidth=1, relheight=1)
                cover.lift()
            app.update_idletasks()
        try:
            self.resize(factor)
            if cover is not None:
                self.settle()
            for tab in getattr(app, "tabs", ()):
                rescaled = getattr(tab, "rescaled", None)
                if rescaled is not None:
                    rescaled()
            if cover is not None:
                self.settle()
                app.winfo_pointerxy()   # a round trip: all of it drawn at the server first
        finally:
            if cover is not None:
                cover.destroy()

    def settle(self):
        """Lay out now: the geometry (idle) and the <Configure> events it
        makes (the wrap lengths that follow a width), not timers or input
        from elsewhere."""
        flags = _tkinter.WINDOW_EVENTS | _tkinter.IDLE_EVENTS | _tkinter.DONT_WAIT
        for _ in range(10000):
            if not self.app.tk.dooneevent(flags):
                break

    def resize(self, factor):
        app = self.app
        ratio = factor / self.factor
        self.factor = app.fm_zoom = factor
        for name, size in self.base.items():
            try:
                tkfont.nametofont(name, root=app).configure(size=font_size(size, factor))
            except tk.TclError:
                pass        # deleted since
        app.theme.rescale()
        call = app.tk.call
        for path in app.theme.walk("."):
            widget = app.theme.widget(path)
            if widget is None:
                continue
            widths = getattr(widget, "widths", None)
            if isinstance(widget, ttk.Treeview) and widths:
                widget.widths = {key: max(1, round(width * ratio)) for key, width in widths.items()}
                for key, width in widget.widths.items():
                    call(path, "column", key, "-width", width)
            elif isinstance(widget, (ttk.Label, tk.Label, tk.Message)):
                wrap = widget.cget("wraplength")
                if wrap and str(wrap) not in ("0", "-1"):
                    widget.configure(wraplength=max(1, round(float(str(wrap)) * ratio)))
