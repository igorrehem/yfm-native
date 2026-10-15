"""Tools > Card text preview: the selected card's text as the card view
lays it out, drawn in the retail font or set as the port's HD text sets it
(card_text.py). A window of its own that follows the Cards tab, so the tab
itself is as it was."""
from __future__ import annotations

import struct
import tkinter as tk
from tkinter import ttk

from . import card_text, file_dialogs, pngio, ttf
from .widgets import px

# A font file cut short or damaged: ttf reads it with struct.
BAD_FONT = (ttf.FontError, OSError, ValueError, IndexError, KeyError, struct.error)

RETAIL = "Retail font (the disc's 8x12)"
PORT = "HD text: the port's face"
FILE = "HD text: a font file"
MODES = [RETAIL, PORT, FILE]


class CardTextPreview(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Card text preview")
        self.resizable(False, False)
        self.mode = tk.StringVar(value=RETAIL)
        self.scale = tk.StringVar(value="2")
        self.font_path = None
        self.faces = {}             # path -> ttf.Font, or the FontError's text
        self.renderers = {}
        self.retail = {}            # the game files' source -> card_text.RetailFont
        self.pending = None
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Font").pack(side="left")
        ttk.Combobox(top, textvariable=self.mode, values=MODES, state="readonly", width=30).pack(side="left", padx=4)
        ttk.Label(top, text="Scale").pack(side="left", padx=(8, 0))
        ttk.Combobox(top, textvariable=self.scale, values=["1", "2", "3", "4"], state="readonly", width=3).pack(
            side="left", padx=4)
        ttk.Button(top, text="Font file...", command=self.choose_font).pack(side="left", padx=(8, 0))
        self.face_label = ttk.Label(self, padding=(6, 0), style="Note.TLabel", justify="left",
                                    wraplength=px(self, 420))
        self.face_label.pack(fill="x")
        self.picture = ttk.Label(self, padding=6)
        self.picture.pack()
        self.notes = ttk.Label(self, padding=(6, 0, 6, 6), justify="left", wraplength=px(self, 420))
        self.notes.pack(fill="x")
        self.mode.trace_add("write", lambda *_: self.refresh())
        self.scale.trace_add("write", lambda *_: self.refresh())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.image = None
        self.refresh()

    def close(self):
        self.destroy()

    def destroy(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        self.app.text_preview = None
        super().destroy()

    def choose_font(self):
        path = file_dialogs.askopenfilename(parent=self, title="A TrueType font file (your own copy; never saved in the mod)",
                                            initialdir=card_text.fonts_folder(),
                                            filetypes=[("TrueType fonts", "*.ttf *.ttc *.otf"), ("All files", "*.*")])
        if path:
            self.font_path = path
            if self.mode.get() != FILE:
                self.mode.set(FILE)         # refreshes
            else:
                self.refresh()

    def face(self, path):
        if path not in self.faces:
            try:
                self.faces[path] = ttf.Font(path)
            except BAD_FONT as problem:
                self.faces[path] = str(problem) or f"{path} could not be read"
        return self.faces[path]

    def later(self):
        """Refresh once typing stops for a moment."""
        if self.pending is not None:
            self.after_cancel(self.pending)
        self.pending = self.after(150, self.refresh)

    def text(self):
        cards = self.app.cards
        if cards.current is None:
            return None
        return cards.text.get("1.0", "end-1c")

    def refresh(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
        self.pending = None
        files = self.app.files
        text = self.text()
        mode, scale = self.mode.get(), int(self.scale.get() or 1)
        if files is None or text is None:
            self.show(None, "Choose a card in the Cards tab." if files is not None else "Choose the game files first.")
            return
        try:
            retail = self.retail.get(files.source)
            if retail is None:
                retail = self.retail[files.source] = card_text.RetailFont(files.wa)
        except ValueError as problem:
            self.show(None, str(problem))
            return
        face, about = None, ""
        if mode != RETAIL:
            path = card_text.port_face_path() if mode == PORT else self.font_path
            if path is None:
                about = ("No system font found where the port looks (Segoe UI, Arial or Tahoma; "
                         "fontconfig's sans-serif elsewhere)." if mode == PORT else "Choose a font file.")
            else:
                face = self.face(path)
                if isinstance(face, str):
                    about, face = face, None
                else:
                    about = f"{face.name}  ({path})"
            if mode == PORT:
                about += ("\nA mod's own \"font\" comes first in the game: the port sets its text in the first "
                          "font of the enabled mods that has the letter.")
        key = (files.source, id(face))
        renderer = self.renderers.get(key)
        if renderer is None:
            renderer = self.renderers[key] = card_text.Renderer(retail, face)
        notes = []
        try:
            if face is not None and scale > 1:
                self.config(cursor="watch")
                self.update_idletasks()
                if not renderer.face_ok:
                    notes.append("The port cannot measure this face's lines (a baseline, x-height, capitals, "
                                 "ascenders and descenders), so it keeps the retail letters, as below.")
            if face is not None and scale == 1:
                notes.append("HD text starts at Internal 2x; at 1x the game draws the retail font.")
            image, lay = renderer.render(text, scale)
        except BAD_FONT as problem:
            # A face whose tables read but whose glyphs do not.
            self.face_label.configure(text=about)
            self.show(None, f"This font could not be drawn: {problem or type(problem).__name__}")
            return
        finally:
            self.config(cursor="")
        notes += describe(lay)
        self.face_label.configure(text=about)
        self.show(image, "\n".join(notes))

    def show(self, image, notes):
        if image is None:
            self.picture.configure(image="", text="")
            self.image = None
        else:
            self.image = tk.PhotoImage(master=self, data=pngio.ppm(image), format="PPM")
            self.picture.configure(image=self.image)
        # Wrap the words to the picture, so a long note does not widen the window.
        wrap = max(px(self, 420), self.image.width() if self.image else 0)
        self.face_label.configure(wraplength=wrap)
        self.notes.configure(text=notes, wraplength=wrap)


def describe(lay: card_text.Layout) -> list:
    """What the picture's marks say, in words."""
    out = [f"{lay.rows} rows. The card view shows {card_text.CLEAR_ROWS} clear of its frame; the "
           f"{card_text.SHOWN_ROWS}th row is drawn over the frame (the brown row), and the rows past it "
           "(dimmed, grey) are never shown."]
    if lay.rows > card_text.SHOWN_ROWS:
        out.append(f"{lay.hidden} row{'s' if lay.hidden != 1 else ''} of this text will not show in the game.")
    elif lay.rows == card_text.SHOWN_ROWS:
        out.append("The last row is over the frame.")
    if lay.cut_rows:
        rows = ", ".join(str(r + 1) for r in lay.cut_rows)
        many = len(lay.cut_rows) > 1
        out.append(f"A word longer than the box's 21 letters is cut where the red tick is (row{'s' if many else ''} "
                   f"{rows} start{'' if many else 's'} mid-word), and the rest of its line takes a row of its own.")
    codes = sorted({c for c, _, _ in lay.glyphs if c.startswith("{")})
    if codes:
        out.append("Left empty here: " + " ".join(codes) + " (the game draws the icon or glyph).")
    missing = sorted({c for c, _, _ in lay.glyphs if c != " " and not c.startswith("{")
                      and not card_text.retail_character(c)})
    if missing:
        out.append("Red boxes: " + " ".join(missing) + " (no retail letter; the port sets one from a font).")
    accented = sorted({c for c, _, _ in lay.glyphs if card_text.retail_character(c) and not c.isascii()})
    if accented:
        out.append("Drawn plain here: " + " ".join(accented) + " (the port draws the mark on).")
    return out
