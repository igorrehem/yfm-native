"""The card text box's right-click menu: cut, copy and paste, an icon
("{f8 0B NN}", from a picker window that scrolls, as the forty-one do not
fit a menu on a short screen) or a color ("{f8 0A NN}") inserted where the
cursor is, each shown as the game draws it (notes/more-cards.md, "Card text
codes"), so the codes need not be looked up."""
from __future__ import annotations

import base64
import sys
import tkinter as tk

from tkinter import ttk

from . import card_links, card_text, pngio
from .widgets import ScrolledForm, px

ICON_GROUPS = (("Monster types", range(0x00, 0x14)), ("Card kinds", range(0x14, 0x18)),
               ("Guardian stars", range(0x18, 0x22)), ("Buttons", range(0x22, 0x29)))
PICKER_COLUMNS = 4
ZOOM = 2


class Pictures:
    """The icons and color swatches of one set of game files, made once."""

    def __init__(self, master, wa, zoom=ZOOM):
        self.icons, self.swatches = {}, {}
        try:
            font = card_text.RetailFont(wa)
        except (ValueError, TypeError):
            return
        for n in range(len(card_text.ICON_NAMES)):
            icon = font.icon(n)
            if icon is not None:
                image = pngio.scale_nearest(pngio.Image(*icon), zoom)
                self.icons[n] = tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")
        for n in range(len(card_text.COLOR_NAMES)):
            rgb = font.ramps[n][15]
            image = pngio.Image(16 * zoom, 12 * zoom, bytes((*rgb, 255)) * (16 * 12 * zoom * zoom))
            self.swatches[n] = tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")




def pictures(app, widget, zoom=ZOOM):
    files = getattr(app, "files", None)
    if files is None or getattr(files, "wa", None) is None:
        return None
    # Kept by the window: its images are its Tk's, as another window's are not.
    cache = app.__dict__.setdefault("_text_pictures", {})
    key = (getattr(files, "source", id(files)), zoom)
    if key not in cache:
        cache[key] = Pictures(widget.winfo_toplevel(), files.wa, zoom)
    return cache[key]


def insert_code(text: tk.Text, code: str):
    """At the cursor, in place of a selection."""
    if text.tag_ranges("sel"):
        text.delete("sel.first", "sel.last")
    text.insert("insert", code)


def color(text: tk.Text, n: int):
    """A selection is colored and the text after it goes back to white;
    without one, the color starts at the cursor."""
    if text.tag_ranges("sel") and n:
        first, last = text.index("sel.first"), text.index("sel.last")
        text.insert(last, card_text.color_code(0))
        text.insert(first, card_text.color_code(n))
        text.tag_remove("sel", "1.0", "end")
    else:
        insert_code(text, card_text.color_code(n))


class IconPicker(tk.Toplevel):
    """Every icon with its name, by group, in a window no taller than the
    screen leaves room for (it scrolls, wheel too); a click puts the icon in
    the text where the cursor was, and closes it, as Escape does."""

    def __init__(self, app, text: tk.Text, after, x=None, y=None):
        super().__init__(text)
        self.title("Insert icon")
        self.transient(text.winfo_toplevel())
        self.text, self.after_insert = text, after
        self.at = text.index("insert")
        self.bind("<Escape>", lambda e: self.destroy())
        shown = pictures(app, text)
        scroll = ScrolledForm(self)
        scroll.pack(fill="both", expand=True)
        body = ttk.Frame(scroll.body, padding=6)
        body.pack(fill="both", expand=True)
        self.buttons = {}
        row = 0
        for title, codes in ICON_GROUPS:
            ttk.Label(body, text=title, style="Hint.TLabel").grid(row=row, column=0, columnspan=PICKER_COLUMNS,
                                                                  sticky="w", pady=(6 if row else 0, 2))
            row += 1
            for i, n in enumerate(codes):
                image = shown.icons.get(n) if shown else None
                button = ttk.Button(body, text=card_text.ICON_NAMES[n], image=image or "",
                                    compound="left" if image else "none", command=lambda n=n: self.pick(n))
                button.grid(row=row + i // PICKER_COLUMNS, column=i % PICKER_COLUMNS, sticky="we", padx=1, pady=1)
                self.buttons[n] = button
            row += (len(codes) + PICKER_COLUMNS - 1) // PICKER_COLUMNS
        self.update_idletasks()
        # As tall as the icons need, or the screen allows; at the click, kept on the screen.
        width = body.winfo_reqwidth()
        height = min(body.winfo_reqheight(), self.winfo_screenheight() - px(self, 120))
        scroll.canvas.configure(width=width, height=height)
        self.update_idletasks()
        x = self.winfo_pointerx() if x is None else x
        y = self.winfo_pointery() if y is None else y
        x = max(0, min(x, self.winfo_screenwidth() - self.winfo_reqwidth() - px(self, 10)))
        y = max(0, min(y, self.winfo_screenheight() - self.winfo_reqheight() - px(self, 60)))
        self.geometry(f"+{x}+{y}")
        self.focus_set()

    def pick(self, n: int):
        text = self.text
        text.mark_set("insert", self.at)
        insert_code(text, card_text.icon_code(n))
        self.destroy()
        text.focus_set()
        self.after_insert()


def fill(menu: tk.Menu, app, text: tk.Text, after):
    def run(action):
        def command():
            action()
            text.focus_set()
            after()
        return command

    editable = str(text.cget("state")) == "normal"
    state = "normal" if editable else "disabled"
    has_selection = bool(text.tag_ranges("sel"))
    menu.add_command(label="Cut", state=state if has_selection else "disabled",
                     command=run(lambda: text.event_generate("<<Cut>>")))
    menu.add_command(label="Copy", state="normal" if has_selection else "disabled",
                     command=lambda: text.event_generate("<<Copy>>"))
    menu.add_command(label="Paste", state=state, command=run(lambda: text.event_generate("<<Paste>>")))
    menu.add_separator()
    shown = pictures(app, text)
    menu.add_command(label="Insert icon...", state=state, command=lambda: IconPicker(app, text, after))
    colors = tk.Menu(menu, tearoff=False)
    for n, name in enumerate(card_text.COLOR_NAMES):
        image = shown.swatches.get(n) if shown else None
        label = f"{name}{' (back to normal)' if n == 0 else ''}   {card_text.color_code(n)}"
        colors.add_command(label=label, image=image or "", compound="left" if image else "none",
                            command=run(lambda n=n: color(text, n)))
    menu.add_cascade(label="Text color" + (" (of the selection)" if has_selection else ""), menu=colors,
                     state=state)


def install(app, text: tk.Text, after=lambda: None):
    """Give the text box the menu; `after` runs once the text is changed
    (the tab's line count and marks)."""
    def popup(event):
        card_links.close_menu()
        # The cursor goes where the click is, as a text editor's does,
        # unless the click is inside the selection (which then stays).
        at = text.index(f"@{event.x},{event.y}")
        inside = text.tag_ranges("sel") and text.compare("sel.first", "<=", at) and text.compare(at, "<", "sel.last")
        if not inside:
            text.tag_remove("sel", "1.0", "end")
            text.mark_set("insert", at)
        menu = tk.Menu(text, tearoff=False)
        card_links._open_menu = menu
        fill(menu, app, text, after)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    text.bind("<Button-3>", popup)
    if sys.platform == "darwin":
        text.bind("<Button-2>", popup)
