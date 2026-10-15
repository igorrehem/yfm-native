"""The Cards tab's card text box: an icon code ({f8 0B NN}) shown as the
icon off the disc, two letters wide as the game sets it, and a color code
({f8 0A NN}) as a hairline of its color, the letters after it in that
color (darker on a light background, so they read; white as the box's own
ink). The preview beside it (preview.py) draws the card view itself
(notes/more-cards.md, "Card text codes").

Its lines break where the game's do (card_text.wrap_points: twenty
letters a line, an icon two, a word never split), not where Tk's own
word wrapping would (it breaks between any two pictures): the space the game
breaks at shows as the end of the line, a "soft" newline that reads back
as that space.

What it holds is still the text with its codes: get() gives them back for
the pictures and soft newlines, and after every change (typing, a paste,
insert(), delete()) the box is laid out again from that text, so a code
typed or pasted in full becomes its picture. Copy and cut put the codes on
the clipboard. Without the game files the codes stay as written, and the
lines still break as the game's."""
from __future__ import annotations

import base64
import re
import tkinter as tk
from tkinter import font as tkfont

from . import card_text, pngio

SOFT = "soft"           # the tag of the newlines the wrapping puts in
# The codes the box shows as pictures (card_text.CODE, less {g X}).
PICTURED = re.compile(r"\{f8 *(0[AaBb]) *([0-9A-Fa-f]{1,2})\}")


class CardTextBox(tk.Text):
    def __init__(self, master, app, **options):
        # The lines are broken here, as the game breaks them; Tk only cuts a
        # word too long for the box at its edge (21 letters), as the card
        # view does.
        options["wrap"] = "char"
        super().__init__(master, **options)
        self.app = app
        self.codes = {}         # embedded image name -> its code
        self._source = None     # the game files the pictures are of
        self._icons, self._bars, self._inks = {}, {}, {}
        self._laying = False
        for event, handler in (("<<Copy>>", self._copy), ("<<Cut>>", self._cut), ("<<Paste>>", self._paste)):
            self.bind(event, handler)
        # Any change (a key, a drop, the middle button's paste): laid out again.
        self.bind("<<Modified>>", self._modified, add=True)

    # --- the pictures -----------------------------------------------------------

    def _pictures(self) -> bool:
        """Made for the game files the window has now; False without them."""
        files = getattr(self.app, "files", None)
        source = getattr(files, "source", None) if files is not None else None
        if files is None or getattr(files, "wa", None) is None:
            return False
        if source == self._source and self._inks:
            return True
        try:
            font = card_text.RetailFont(files.wa)
        except (ValueError, TypeError):
            return False
        self._source, self._icons, self._bars, self._inks = source, {}, {}, {}
        measure = tkfont.Font(font=self.cget("font"))
        letter, line = measure.measure("0"), measure.metrics("linespace")
        # An icon is two letters wide in the game: as near that here as whole
        # zooms come (16 texels a side, the font's letters about 8 across).
        zoom = max(1, round(2 * letter / 16))
        for n in range(len(card_text.ICON_NAMES)):
            icon = font.icon(n)
            if icon is not None:
                image = pngio.scale_nearest(pngio.Image(*icon), zoom)
                self._icons[n] = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(image)),
                                               format="png")
        for n, ramp in enumerate(font.ramps[:len(card_text.COLOR_NAMES)]):
            rgb = ramp[15]
            self._inks[n] = rgb
            # A color takes no room in the game: a hairline here.
            bar = pngio.Image(2, line, bytes((*rgb, 255)) * (2 * line))
            self._bars[n] = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(bar)), format="png")
        return True

    def _picture(self, code: str):
        match = PICTURED.fullmatch(code)
        if not match:
            return None
        n = int(match.group(2), 16)
        return (self._icons if match.group(1).upper() == "0B" else self._bars).get(n)

    # --- what it holds ----------------------------------------------------------

    def _pieces(self, index1="1.0", index2="end-1c"):
        """(box index, the text it stands for) of each piece between the
        two: runs of letters, pictures (their codes), soft newlines (a space)."""
        soft = SOFT in self.tag_names(index1)
        for key, value, index in self.dump(index1, index2, text=True, image=True, tag=True):
            if key == "tagon" and value == SOFT:
                soft = True
            elif key == "tagoff" and value == SOFT:
                soft = False
            elif key == "text":
                yield index, value.replace("\n", " ") if soft else value
            elif key == "image":
                yield index, self.codes.get(value, "")

    def get(self, index1, index2=None):
        """The text with its codes: a picture gives back the code it shows,
        a soft newline the space it stands for."""
        return "".join(text for _, text in self._pieces(index1, index2 or f"{index1}+1c"))

    def _index_of(self, offset: int) -> str:
        """The box index of character `offset` of get()'s text (after a
        picture whose code it falls inside)."""
        seen = 0
        for index, text in self._pieces():
            if offset < seen + len(text):
                if self._is_image(index):
                    return index if offset == seen else f"{index}+1c"
                return f"{index}+{offset - seen}c"
            seen += len(text)
        return "end-1c"

    def _is_image(self, index) -> bool:
        try:
            self.image_cget(index, "image")
            return True
        except tk.TclError:
            return False

    def insert(self, index, chars, *args):
        """As Text.insert, then laid out again: the codes in chars as their
        pictures, the lines broken as the game's."""
        super().insert(index, chars, *args)
        self.layout()

    def delete(self, index1, index2=None):
        super().delete(index1, index2)
        self.layout()

    def _modified(self, event=None):
        # The flag going back to false is an event too: only a change counts.
        if self._laying or not self.edit_modified():
            return
        self.edit_modified(False)
        self.app.after_idle(self.layout)     # the window's, which it cancels on close

    def layout(self):
        """The box again from its text: pictures for the codes, the game's
        line breaks, the colors; the cursor and a selection where they were
        in the text."""
        if self._laying or not self.winfo_exists() or str(self.cget("state")) != "normal":
            return
        text = self.get("1.0", "end-1c")
        cursor = len(self.get("1.0", "insert"))
        selection = (len(self.get("1.0", "sel.first")), len(self.get("1.0", "sel.last"))) \
            if self.tag_ranges("sel") else None
        breaks = set(card_text.wrap_points(text))
        pictures = self._pictures()
        self._laying = True
        try:
            super().delete("1.0", "end")
            self.codes.clear()
            at = 0
            for match in (PICTURED.finditer(text) if pictures else ()):
                image = self._picture(match.group(0))
                if image is None:
                    continue
                self._put_text(text, at, match.start(), breaks)
                name = self.image_create("end", image=image)
                self.codes[name] = "{f8 %s %s}" % (match.group(1).upper(), match.group(2).upper().zfill(2))
                at = match.end()
            self._put_text(text, at, len(text), breaks)
            self.mark_set("insert", self._index_of(cursor))
            if selection:
                self.tag_add("sel", self._index_of(selection[0]), self._index_of(selection[1]))
            self.recolor()
            self.see("insert")
        finally:
            self.edit_modified(False)
            self._laying = False

    def _put_text(self, text, start, end, breaks):
        """text[start:end] at the end, a soft newline in place of each space
        the game breaks at."""
        run = start
        for i in range(start, end):
            if i in breaks:
                if i > run:
                    super().insert("end", text[run:i])
                super().insert("end", "\n", SOFT)
                run = i + 1
        if end > run:
            super().insert("end", text[run:end])

    def _ink(self, n: int):
        """Color n as the box shows it: on a light background (the theme's
        light look) a darker one that reads; white, the box's own ink."""
        r, g, b = (v >> 8 for v in self.winfo_rgb(self.cget("background")))
        if (r * 299 + g * 587 + b * 114) // 1000 < 128:
            return "#%02x%02x%02x" % self._inks[n]
        return "#%02x%02x%02x" % tuple(v * 55 // 100 for v in self._inks[n])

    def recolor(self):
        """The letters after a color code in its color, as the game draws
        them; the box's own ink again after {f8 0A 00}."""
        for n in self._inks:
            self.tag_remove(f"color{n}", "1.0", "end")
        if not self._inks:
            return
        for n in self._inks:
            if n:
                self.tag_configure(f"color{n}", foreground=self._ink(n))
        color = 0
        for key, value, index in self.dump("1.0", "end-1c", text=True, image=True):
            if key == "image":
                match = PICTURED.fullmatch(self.codes.get(value, ""))
                if match and match.group(1).upper() == "0A":
                    color = int(match.group(2), 16)
            elif color in self._inks and color:
                self.tag_add(f"color{color}", index, f"{index}+{len(value)}c")

    # --- the clipboard: the codes, not the pictures --------------------------------

    def _copy(self, event=None):
        if self.tag_ranges("sel"):
            self.clipboard_clear()
            self.clipboard_append(self.get("sel.first", "sel.last"))
        return "break"

    def _cut(self, event=None):
        if self.tag_ranges("sel") and str(self.cget("state")) == "normal":
            self._copy()
            self.delete("sel.first", "sel.last")
            self.event_generate("<KeyRelease>")
        return "break"

    def _paste(self, event=None):
        if str(self.cget("state")) != "normal":
            return "break"
        try:
            chars = self.clipboard_get()
        except tk.TclError:
            return "break"
        if self.tag_ranges("sel"):
            super().delete("sel.first", "sel.last")
        self.insert("insert", chars)
        self.event_generate("<KeyRelease>")
        return "break"
