"""The editor's two looks: the desktop's own (light, as the editor always
was) and a dark one, switched at run time under View > Dark mode.

The ttk widgets follow a theme: the light one is "vista" on Windows and
"clam" elsewhere, the dark one "fm-dark", a clam made dark (clam's elements
take colors; the native vista ones do not). The few classic Tk widgets (the
text boxes, the menus, a Combobox's drop-down list, the dialogs' Toplevel)
take colors of their own: set on the ones that exist and in the option
database for those made later, and put back to Tk's defaults for light.
The hint and result labels use the named styles in INKS, and the trees'
row tags the colors in TAGS, so they change with the theme too."""
from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

DARK_THEME = "fm-dark"
PORTRAIT_ROW = 38       # the Duelists list's rows: a 32-pixel face and its margin

# The dark palette. Text and every ink below are at least 4.5:1 against the
# backgrounds they are drawn on (WCAG AA); disabled text is dimmer, as
# disabled controls may be.
BG = "#202124"          # windows, frames, labels
FIELD = "#2a2b2f"       # entries, lists, text boxes, trees
RAISED = "#35373c"      # buttons, headings, the unselected tabs
HOVER = "#404349"
PRESSED = "#2a2b2f"
BORDER = "#55585e"
TROUGH = "#18191b"
FG = "#e8eaed"
DISABLED = "#8c9197"
SELECT = "#264266"      # selected rows and text
FOCUS = "#6f9dd6"       # a focused field's border

# Label styles (ttk.Label(..., style="Hint.TLabel")): light, dark.
INKS = {
    "Hint": ("#777", "#a3a9b0"),        # explanations and counts
    "Note": ("#555", "#c4c8cd"),        # the Art tab's captions
    "Error": ("#c01c28", "#ff8f87"),
    "Ok": ("#26a269", "#7fd49b"),
    "Warning": ("#9c6500", "#f2c04c"),
    "Changed": ("#1a5fb4", "#8ab4f8"),  # a field that differs from the disc (TAGS' "changed")
}

# Tree row tags (widgets.scrolled_tree): light, dark.
TAGS = {
    "changed": ("#1a5fb4", "#8ab4f8"),
    "added": ("#26a269", "#7fd49b"),
    "removed": ("#c01c28", "#ff8f87"),
    "glitch": ("#865e3c", "#e0ae78"),
    "error": ("#c01c28", "#ff8f87"),
    "warning": ("#9c6500", "#f2c04c"),
    "note": ("#5e5c64", "#a8a6ae"),
}

# The classic widgets' colors in the dark look, by widget class.
CLASSIC = {
    "Text": {"background": FIELD, "foreground": FG, "insertbackground": FG, "selectbackground": SELECT,
             "selectforeground": FG, "inactiveselectbackground": SELECT, "highlightbackground": BG,
             "highlightcolor": FOCUS},
    "Listbox": {"background": FIELD, "foreground": FG, "selectbackground": SELECT, "selectforeground": FG,
                "disabledforeground": DISABLED, "highlightbackground": BG, "highlightcolor": FOCUS},
    "Menu": {"background": FIELD, "foreground": FG, "activebackground": SELECT, "activeforeground": FG,
             "disabledforeground": DISABLED, "selectcolor": FG},
    "Toplevel": {"background": BG},
}
if sys.platform == "win32":
    # Windows draws a classic widget's sunken border with a white bevel,
    # glaring on the dark fields: a flat one-pixel line instead, in the ttk
    # fields' border color (the focus color when focused). Same width.
    # Not a Combobox's drop-down list (use): its frame is its border.
    for _cls in ("Text", "Listbox"):
        CLASSIC[_cls].update(relief="flat", borderwidth=1, highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=FOCUS)
BORDERS = ("relief", "borderwidth", "highlightthickness")


def dpi_awareness():
    """Windows stretches the window of a program that does not say it
    knows the screen's dpi: blurry at 125% or 150%. Said before the first
    window: per-monitor (v2, Windows 10 1703 on), else per-monitor (8.1),
    else system-wide (Vista). Tk then sizes the fonts, in points, for the
    real dpi (tk scaling), and widgets.px the rest. Elsewhere nothing."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def windows_fonts(root):
    """Windows 11's own UI face where there is one (Segoe UI Variable, the
    Text cut; Tk's default Segoe UI before), at Tk's sizes; the fixed font
    as the editor's text boxes (Consolas). Elsewhere nothing."""
    if sys.platform != "win32":
        return
    if "Segoe UI Variable Text" in tkfont.families(root):
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkCaptionFont",
                     "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            tkfont.nametofont(name, root=root).configure(family="Segoe UI Variable Text")
    tkfont.nametofont("TkFixedFont", root=root).configure(family="Consolas", size=10)


def is_dark(widget) -> bool:
    return ttk.Style(widget).theme_use() == DARK_THEME


def tag_color(widget, tag: str) -> str:
    light, dark = TAGS[tag]
    return dark if is_dark(widget) else light


class Theme:
    """Switches a window (and the dialogs it opens) between the two looks."""

    def __init__(self, root: tk.Tk):
        self.root = root
        windows_fonts(root)       # before the row height is measured
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        self.light = self.style.theme_use()
        self.dark = False
        if self.light == "clam":
            # clam shows a pressed toolbutton by its relief alone, barely: tinted.
            self.style.map("Segment.Toolbutton", background=[("selected", "#bcd0ea"), ("active", "#ececec")])
        self.rescale()
        for name, (light, _) in INKS.items():
            self.style.configure(f"{name}.TLabel", foreground=light)
        for tag, (light, _) in TAGS.items():       # a legend's words in its rows' colors (widgets.legend)
            self.style.configure(f"{tag}.Tag.TLabel", foreground=light)
        # Tk's own defaults for the classic widgets, to go back to, and each
        # option's name in the option database (highlightBackground for
        # -highlightbackground: the database is case sensitive).
        self.defaults = {}
        self.dbnames = {}
        for cls, options in CLASSIC.items():
            sample = root if cls == "Toplevel" else getattr(tk, cls)(root)
            self.defaults[cls] = {option: str(sample.configure(option)[3]) for option in options}
            self.dbnames[cls] = {option: sample.configure(option)[1] for option in options}
            if sample is not root:
                sample.destroy()
        root.bind_class("Toplevel", "<Map>", lambda e: self.title_bar(e.widget), add="+")
        self.menubar = None     # the window's own menu bar, while the strip stands in for it
        self.strip = None
        root.bind("<Alt-KeyPress>", self.alt_key, add="+")
        root.bind("<F10>", self.alt_key, add="+")

    @property
    def scale(self):
        """The desktop's scale times View > Interface size's (widgets.ui_scale)."""
        from .widgets import ui_scale
        return ui_scale(self.root)

    def px(self, *pixels):
        """Pixel sizes at 96 dpi, at the desktop's and the interface size
        (self.scale): one, or a tuple of them. Unchanged where the scale is 1."""
        sized = tuple(round(value * self.scale) for value in pixels)
        return sized[0] if len(sized) == 1 else sized

    def rescale(self):
        """The sizes that follow the fonts and the scale, in both themes: a
        row as tall as a line of text, and the pixel sizes (sized())."""
        self.row_height = tkfont.nametofont("TkDefaultFont", root=self.root).metrics("linespace") + 4
        self.style.theme_settings(self.light, self.sized(False))
        if DARK_THEME in self.style.theme_names():
            self.style.theme_settings(DARK_THEME, self.sized(True))

    def sized(self, dark):
        """theme_settings for the sizes in pixels: the row height; clam's
        own sizes (its check boxes 10, scrollbar and drop-down arrows 14,
        spin arrows 10, sashes 6) at the scale, in the light clam and
        fm-dark (vista's are Windows' own); fm-dark's paddings."""
        settings = {"Treeview": {"configure": {"rowheight": self.row_height}},
                    # The Duelists tab's list: a row as tall as the small
                    # portrait beside each name.
                    "Portrait.Treeview": {"configure": {"rowheight": max(self.row_height, self.px(PORTRAIT_ROW))}},
                    # A switch of a few toggles (the Art tab's View): each
                    # one a button, the chosen one pressed in.
                    "Segment.Toolbutton": {"configure": {"padding": self.px(10, 3), "relief": "raised"},
                                           "map": {"relief": [("selected", "sunken"), ("!selected", "raised")]}}}
        if not dark and self.light != "clam":
            return settings
        for toggle in ("TCheckbutton", "TRadiobutton"):
            settings[toggle] = {"configure": {"indicatorsize": self.px(10)}}
        settings["TScrollbar"] = {"configure": {"arrowsize": self.px(14)}}
        settings["TCombobox"] = {"configure": {"arrowsize": self.px(14)}}
        settings["TSpinbox"] = {"configure": {"arrowsize": self.px(10)}}
        settings["Sash"] = {"configure": {"sashthickness": self.px(6)}}
        if dark:
            settings["TButton"] = {"configure": {"padding": self.px(5)}}
            settings["TNotebook"] = {"configure": {"tabmargins": self.px(2, 2, 2, 0)}}
            settings["TNotebook.Tab"] = {"configure": {"padding": self.px(6, 2, 6, 2)},
                                         "map": {"padding": [("selected", self.px(6, 4, 6, 2))]}}
            settings["TLabelframe"] = {"configure": {"labelmargins": self.px(6, 0, 6, 2)}}
            settings["Toolbutton"] = {"configure": {"padding": self.px(2)}}
            for toggle in ("TCheckbutton", "TRadiobutton"):
                settings[toggle]["configure"].update(indicatormargin=self.px(1, 1, 4, 1), padding=self.px(2))
        return settings

    def use(self, dark: bool):
        if dark and DARK_THEME not in self.style.theme_names():
            self.make_dark()
        self.style.theme_use(DARK_THEME if dark else self.light)
        self.root.update_idletasks()      # the widgets take the theme (and ask their sizes again) now
        self.dark = dark
        for cls, options in CLASSIC.items():
            values = options if dark else self.defaults[cls]
            for option, value in values.items():
                self.root.option_add(f"*{cls}.{self.dbnames[cls][option]}", value)
        if "relief" in CLASSIC["Listbox"]:
            # ttk's own for a Combobox's list (combobox.tcl), after the above
            # to come first for the lists made from now on.
            self.root.option_add("*TCombobox*Listbox.relief", "flat")
            self.root.option_add("*TCombobox*Listbox.highlightThickness", 0)
        # The widgets that exist, Tcl's own included (tkinter's
        # winfo_children skips the Combobox's drop-down list).
        call = self.root.tk.call
        for path in self.walk("."):
            cls = call("winfo", "class", path)
            cls = "Toplevel" if cls == "Tk" else cls
            if cls in CLASSIC:
                values = CLASSIC[cls] if dark else self.defaults[cls]
                if ".popdown." in path:     # a Combobox's list keeps the borders ttk gave it
                    values = {option: value for option, value in values.items() if option not in BORDERS}
                call(path, "configure", *[item for option, value in values.items()
                                          for item in (f"-{option}", value)])
                recolor = getattr(self.widget(path), "recolor", None)
                if recolor:        # the card text box's colors follow the background (card_text_box.py)
                    recolor()
            elif cls == "Treeview":
                for tag, (light, dark_ink) in TAGS.items():
                    call(path, "tag", "configure", tag, "-foreground", dark_ink if dark else light)
                # The theme change had the tree ask for its columns' widths,
                # stretched by now, squeezing the form beside it: back to the
                # widths it was made with, and ask again.
                widths = getattr(self.widget(path), "widths", None)
                if widths:
                    for key, width in widths.items():
                        call(path, "column", key, "-width", width)
                    call(path, "configure", "-height", call(path, "cget", "-height"))
            if cls == "Toplevel" and call("winfo", "ismapped", path):
                self.title_bar(self.widget(path))
        self.menu_bar(dark)

    def widget(self, path):
        """The tkinter object of a path, or None for a widget Tcl made."""
        try:
            return self.root.nametowidget(path)
        except KeyError:
            return None

    def walk(self, path):
        yield path
        for child in self.root.tk.splitlist(self.root.tk.call("winfo", "children", path)):
            yield from self.walk(child)

    def title_bar(self, window):
        """Windows 10 (1809 on) and 11 draw a window's title bar dark when
        asked; elsewhere the window manager's own is kept."""
        if sys.platform != "win32" or (not self.dark and not getattr(window, "dark_title", False)):
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            value = ctypes.c_int(1 if self.dark else 0)
            # DWMWA_USE_IMMERSIVE_DARK_MODE, then its number before 20H1.
            for attribute in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                              ctypes.sizeof(value)) == 0:
                    break
            # Redraw the frame now, not at the next activation.
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)   # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
            window.dark_title = self.dark
        except (AttributeError, OSError, KeyError):
            pass

    def menu_bar(self, dark):
        """Windows draws a window's menu bar itself, light whatever Tk asks
        (uxtheme's undocumented dark mode calls leave it light too). In the
        dark look the bar is a strip of Tk menubuttons instead, each posting
        a clone of the bar's menu: a clone keeps its menu's entries, added
        ones (an importer's) included. The menus themselves Tk draws, dark,
        but for the thin frame Windows puts around them. X11 draws Tk's own
        bar, colored with the other menus."""
        if sys.platform != "win32" or (not dark and self.strip is None):
            return
        root = self.root
        if dark:
            if self.strip is None:
                self.menubar = root.nametowidget(root.cget("menu"))
                self.strip = self.make_strip(self.menubar)
            if self.strip.winfo_manager():
                return
            root.configure(menu="")
            self.strip.pack(side="top", fill="x", before=root.pack_slaves()[0])
            grow = self.strip.winfo_reqheight()
        elif self.strip.winfo_manager():
            self.strip.pack_forget()
            root.configure(menu=self.menubar)
            grow = -self.strip.winfo_reqheight()
        else:
            return
        # Tk keeps the size inside the frame, which the bar is not: keep the
        # window's own size instead, the strip taking the bar's room.
        if root.winfo_ismapped() and root.state() == "normal":
            root.geometry(f"{root.winfo_width()}x{root.winfo_height() + grow}")

    def make_strip(self, bar):
        strip = ttk.Frame(self.root)
        for index in range(bar.index("end") + 1):
            if bar.type(index) != "cascade":
                continue
            button = tk.Menubutton(strip, text=bar.entrycget(index, "label"), underline=0, background=BG,
                                   foreground=FG, activebackground=HOVER, activeforeground=FG, borderwidth=0,
                                   highlightthickness=0, padx=self.px(7), pady=self.px(2))
            clone = f"{button}.menu"
            self.root.tk.call(bar.entrycget(index, "menu"), "clone", clone, "normal")
            button.configure(menu=clone)
            button.pack(side="left")
        return strip

    def alt_key(self, event):
        """Alt+letter and F10 open the strip's menus, as they do the bar's."""
        if self.strip is None or not self.strip.winfo_manager():
            return None
        call = self.root.tk.call
        if event.keysym == "F10":
            call("tk::FirstMenu", ".")
            return "break"
        if event.char and call("tk::MenuFind", ".", event.char):
            call("tk::TraverseToMenu", ".", event.char)
            return "break"
        return None

    def make_dark(self):
        """fm-dark: clam's elements and layouts, clam's settings in dark colors."""
        style = self.style
        style.theme_create(DARK_THEME, parent="clam")
        current = style.theme_use()
        style.theme_use(DARK_THEME)       # configure and map set the theme in use
        style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=BORDER,
                        lightcolor=RAISED, darkcolor=BG, troughcolor=TROUGH, selectbackground=SELECT,
                        selectforeground=FG, selectborderwidth=0, insertcolor=FG, arrowcolor=FG,
                        focuscolor=FOCUS, font="TkDefaultFont")
        style.map(".", background=[("disabled", BG), ("active", HOVER)], foreground=[("disabled", DISABLED)],
                  arrowcolor=[("disabled", DISABLED)])
        style.configure("TButton", background=RAISED, lightcolor=HOVER, darkcolor=RAISED, anchor="center",
                        width=-11, padding=self.px(5), relief="raised")
        style.map("TButton", background=[("disabled", BG), ("pressed", PRESSED), ("active", HOVER)],
                  lightcolor=[("pressed", PRESSED)], darkcolor=[("pressed", PRESSED)],
                  bordercolor=[("focus", FOCUS)])
        for field in ("TEntry", "TSpinbox", "TCombobox"):
            style.configure(field, fieldbackground=FIELD, foreground=FG, background=RAISED, lightcolor=FIELD,
                            darkcolor=FIELD, insertwidth=1, padding=1)
            style.map(field, fieldbackground=[("disabled", BG), ("readonly", FIELD)],
                      foreground=[("disabled", DISABLED)], bordercolor=[("focus", FOCUS)],
                      lightcolor=[("focus", FIELD)], darkcolor=[("focus", FIELD)],
                      background=[("disabled", BG), ("pressed", HOVER), ("active", HOVER)],
                      arrowcolor=[("disabled", DISABLED)])
        style.configure("TCombobox", padding=(1, 1, 1, 1))
        style.configure("ComboboxPopdownFrame", background=FIELD, bordercolor=BORDER, relief="solid")
        style.configure("TNotebook", background=BG, bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                        tabmargins=self.px(2, 2, 2, 0))
        style.configure("TNotebook.Tab", background=RAISED, foreground=FG, lightcolor=RAISED, darkcolor=BG,
                        bordercolor=BORDER, padding=self.px(6, 2, 6, 2))
        style.map("TNotebook.Tab", background=[("selected", BG), ("active", HOVER)],
                  padding=[("selected", self.px(6, 4, 6, 2))], lightcolor=[("selected", BG)])
        style.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, bordercolor=BORDER,
                        lightcolor=FIELD, darkcolor=FIELD, rowheight=self.row_height)
        style.map("Treeview", background=[("disabled", BG), ("selected", SELECT)],
                  foreground=[("disabled", DISABLED), ("selected", FG)])
        style.configure("Heading", background=RAISED, foreground=FG, lightcolor=RAISED, darkcolor=RAISED,
                        bordercolor=BORDER, relief="raised", font="TkHeadingFont")
        style.map("Heading", background=[("active", HOVER)])
        style.configure("TScrollbar", background=RAISED, troughcolor=TROUGH, bordercolor=TROUGH,
                        lightcolor=RAISED, darkcolor=RAISED, arrowcolor=FG, gripcount=0)
        style.map("TScrollbar", background=[("pressed", BORDER), ("active", HOVER)])
        style.configure("TLabelframe", background=BG, bordercolor=BORDER, lightcolor=BG, darkcolor=BG, relief="solid",
                        borderwidth=1, labelmargins=self.px(6, 0, 6, 2))
        style.configure("TLabelframe.Label", background=BG, foreground=FG)
        style.configure("TSeparator", background=BORDER)
        for toggle in ("TCheckbutton", "TRadiobutton"):
            style.configure(toggle, indicatorbackground=FIELD, indicatorforeground=FG, upperbordercolor=BORDER,
                            lowerbordercolor=BORDER, indicatormargin=self.px(1, 1, 4, 1), padding=self.px(2))
            # Half ticked ("alternate": some of a set, the Equips tab's types)
            # filled, as clam's light look does: it showed as empty here.
            style.map(toggle, indicatorbackground=[("pressed", BG), ("disabled", BG), ("alternate", FOCUS)],
                      background=[("active", BG)])
        # A toggle drawn as a button (the Map tab's D-pad): pressed shows.
        style.configure("Toolbutton", background=BG, lightcolor=BG, darkcolor=BG, bordercolor=BORDER,
                        padding=self.px(2), relief="flat")
        style.map("Toolbutton", background=[("disabled", BG), ("selected", SELECT), ("active", HOVER)],
                  relief=[("selected", "sunken")], foreground=[("disabled", DISABLED)])
        style.configure("Segment.Toolbutton", background=RAISED, lightcolor=HOVER, darkcolor=RAISED)
        style.map("Segment.Toolbutton", background=[("selected", SELECT), ("active", HOVER)],
                  lightcolor=[("selected", SELECT)], darkcolor=[("selected", SELECT)])
        for name, (_, dark) in INKS.items():
            style.configure(f"{name}.TLabel", foreground=dark)
        for tag, (_, dark) in TAGS.items():
            style.configure(f"{tag}.Tag.TLabel", foreground=dark)
        style.theme_use(current)
        style.theme_settings(DARK_THEME, self.sized(True))
