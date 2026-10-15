"""A still of the window, shown over it while View > Interface size
(zoom.py) lays it out again: Tk draws as it lays out, so without a cover
the window changed a piece at a time, and under a plain one it went blank.

The still is a window of its own over the editor's (override-redirect, no
frame): with a compositing window manager the editor draws all of its new
look behind it, so taking it away shows that at once (a frame inside the
window hid the drawing, which then came in pieces once it was gone).

X11 only (the X server copies the window into a pixmap that becomes the
cover's background, so no picture passes through Python and it takes no
time); elsewhere, or when anything is missing, None and the caller covers
the window plainly."""
from __future__ import annotations

import ctypes
import ctypes.util
import tkinter as tk

INCLUDE_INFERIORS = 1       # the copy takes the child windows' pixels too

_xlib = None


def _lib():
    """libX11 with the calls used declared, or None."""
    global _xlib
    if _xlib is None:
        _xlib = False
        name = ctypes.util.find_library("X11")
        if name:
            try:
                x = ctypes.CDLL(name)
            except OSError:
                return None
            vp, ul, ui, i = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_int
            x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [ctypes.c_char_p], vp
            x.XCloseDisplay.argtypes = [vp]
            x.XCreatePixmap.argtypes, x.XCreatePixmap.restype = [vp, ul, ui, ui, ui], ul
            x.XFreePixmap.argtypes = [vp, ul]
            x.XCreateGC.argtypes, x.XCreateGC.restype = [vp, ul, ul, vp], vp
            x.XFreeGC.argtypes = [vp, vp]
            x.XSetSubwindowMode.argtypes = [vp, vp, i]
            x.XSetForeground.argtypes = [vp, vp, ul]
            x.XFillRectangle.argtypes = [vp, ul, vp, i, i, ui, ui]
            x.XCopyArea.argtypes = [vp, ul, ul, vp, i, i, ui, ui, i, i]
            x.XSetWindowBackgroundPixmap.argtypes = [vp, ul, ul]
            x.XClearWindow.argtypes = [vp, ul]
            x.XSync.argtypes = [vp, i]
            _xlib = x
    return _xlib or None


def cover(app):
    """A window over the editor's showing what it shows now, mapped; None
    where that cannot be done. destroy() it once the editor is drawn."""
    try:
        if app.tk.call("tk", "windowingsystem") != "x11":
            return None
    except tk.TclError:
        return None
    x = _lib()
    if x is None:
        return None
    width, height = app.winfo_width(), app.winfo_height()
    if width <= 1 or height <= 1:
        return None
    display = x.XOpenDisplay(app.winfo_screen().encode())
    if not display:
        return None
    top = None
    try:
        # No background of Tk's own (an empty one): the X server paints the
        # still there instead, the moment the window maps.
        top = tk.Toplevel(app, background="", borderwidth=0, highlightthickness=0)
        top.withdraw()
        top.overrideredirect(True)
        top.geometry(f"{width}x{height}+{app.winfo_rootx()}+{app.winfo_rooty()}")
        window = top.winfo_id()
        app.winfo_pointerxy()       # a round trip: Tk's requests (the window) are at the server
        source = app.winfo_id()
        pixmap = x.XCreatePixmap(display, source, width, height, app.winfo_depth())
        gc = x.XCreateGC(display, source, 0, None)
        # What the window grew by (maximized) in its background color, not
        # black: the copy holds only what was drawn.
        red, green, blue = (value >> 8 for value in app.winfo_rgb(app.cget("background")))
        x.XSetForeground(display, gc, red << 16 | green << 8 | blue)
        x.XFillRectangle(display, pixmap, gc, 0, 0, width, height)
        x.XSetSubwindowMode(display, gc, INCLUDE_INFERIORS)
        x.XCopyArea(display, source, pixmap, gc, 0, 0, width, height, 0, 0)
        x.XSetWindowBackgroundPixmap(display, window, pixmap)
        x.XFreeGC(display, gc)
        x.XFreePixmap(display, pixmap)      # the window keeps it while it is its background
        x.XSync(display, 0)
    except (tk.TclError, OSError, ValueError):
        if top is not None:
            top.destroy()
        return None
    finally:
        x.XCloseDisplay(display)
    top.deiconify()
    top.lift()
    return top
