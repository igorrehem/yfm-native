"""A drop-down list whose choices have the game's icons beside them (the
card types', the guardian stars'), for the Cards tab's Type and Guardian
star lists: a ttk.Combobox cannot show pictures, a menu can. It takes the
place of a read-only Combobox: the same variable, values= to configure and
cget, the chosen value's icon on the button."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import text_menu

ZOOM = 1
ROWS = 12           # a column of the menu at most, so a long list stays on the screen


class IconChoice(ttk.Menubutton):
    def __init__(self, master, app, variable: tk.StringVar, values, icon_of, width=18):
        """icon_of(value) is the icon number ("{f8 0B NN}") beside a value, a
        Tk image of its own, or None."""
        super().__init__(master, textvariable=variable, width=width, direction="below", compound="left")
        self.app, self.variable, self.icon_of = app, variable, icon_of
        self._values = list(values)
        self.menu = tk.Menu(self, tearoff=False, postcommand=self._fill)
        self["menu"] = self.menu
        variable.trace_add("write", lambda *_: self._show())

    def _icons(self):
        shown = text_menu.pictures(self.app, self, ZOOM)
        return shown.icons if shown else {}

    def _image(self, value):
        n = self.icon_of(value)
        return self._icons().get(n) if isinstance(n, int) else n

    def _show(self):
        if not self.winfo_exists():
            return
        image = self._image(self.variable.get())
        super().configure(image=image or "")

    def _fill(self):
        self.menu.delete(0, "end")
        for i, value in enumerate(self._values):
            image = self._image(value)
            self.menu.add_radiobutton(label=value, variable=self.variable, value=value, image=image or "",
                                      compound="left" if image else "none", columnbreak=i and i % ROWS == 0,
                                      command=self._picked)

    def _picked(self):
        """As a Combobox says a choice was made: the window counts it as an
        edit of the form (editing.py)."""
        self.event_generate("<<ComboboxSelected>>")

    def get(self):
        return self.variable.get()

    def configure(self, cnf=None, **options):
        if "values" in options:
            self._values = list(options.pop("values"))
        if cnf or options:
            return super().configure(cnf, **options)
        return None

    config = configure

    def cget(self, key):
        return tuple(self._values) if key == "values" else super().cget(key)

    __getitem__ = cget
