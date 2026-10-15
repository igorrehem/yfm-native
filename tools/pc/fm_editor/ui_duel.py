"""The UI tab's Duel page: the duel's pictures ("ui"."duel", notes/modding.md
"The duel's pictures") on a duel drawn from the disc's own pieces -- the
life-point panel's two halves and their digits, the FIELD box, the card
bar, the hand's and the field's cursors -- over a sketch of the field and
the hand (the 3D field is not drawn here). Drag a picture to move it, the
mouse wheel sizes it about its middle, and the side has the rest: its
colors, its words (the life-point halves), a picture of the mod's own,
hidden, back to the game's. What the game slides off the screen sideways
(the LP halves, the FIELD box) moves up and down only and is sized no
larger than still leaves the screen with the game's; the card bar stays
where it is, at its size (ui_rules.MOVES, as ui_config.c reads them), but
its parts -- the card's name, ATK, DEF, the type's icon, the stars, a
magic card's word -- are listed under it and move about on it, each
colored or hidden, the name's letters spread (ui_rules.PARTS)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import card_text, duel_screen, gamedata, pngio, ui_assets as ua, ui_rules
from .ui_tab import (WARN, ColorButton, Stage, as_int, color_text, ensure, import_image, mod_image, page_layout,
                     section, set_member, sized)
from .widgets import px

ELEMENTS = ["lp_opponent", "lp_player", "field", "card_bar", "hand_cursor", "field_cursor"]
GROUPS = [("life", "Life points", ["lp_opponent", "lp_player"]), ("board", "Field", ["field", "field_cursor"]),
          ("hand", "Hand", ["card_bar", "hand_cursor"])]
NAMES = {"lp_opponent": "Opponent's LP", "lp_player": "Your LP", "field": "FIELD box", "card_bar": "Card bar",
         "hand_cursor": "Hand cursor", "field_cursor": "Field cursor"}
# What ui_config.c lets each take (its `takes`): which ways it moves ("xy",
# "y" or ""), whether it is sized.
MOVES = ui_rules.MOVES
SIZED = set(ui_rules.SIZED)
LABELLED = {"lp_opponent", "lp_player"}
# Below this the field's view has its first row of cards (the game's own LP
# panel and FIELD box end above it, at 56 and 48).
FIELD_TOP = 60
SCALE_MIN, SCALE_MAX = ui_rules.SCALE_MIN, ui_rules.SCALE_MAX
# The hand shown: the five cards the first duel deals (deck 1-40, as the runtime
# tests play), the cursor on the first.
HAND = [9, 20, 27, 31, 28]
# The card bar's parts, listed under it as "card_bar.<part>".
PART_NAMES = {"name": "Name", "atk": "ATK", "def": "DEF", "type": "Type icon", "stars": "Guardian stars",
              "kind": "Magic/trap word"}
PART_WHAT = {
    "name": "The card's name. Its letters can be spread or drawn together; a magic card's name has up to 28 "
            "letters, a monster's 24.",
    "atk": "The sword and the ATK digits.",
    "def": "The shield and the DEF digits.",
    "type": "The icon of the card's type (Dragon, Spellcaster, Magic...).",
    "stars": "A monster's two guardian stars; on the field, the one it has on.",
    "kind": "Magic, Trap, Equip or Ritual, beside a non-monster's icon."}
BAR_SHOWS = ("Monster", "Magic card")


def part_of(key):
    """The part a list key names ("card_bar.name" -> "name"), else None."""
    if isinstance(key, str) and key.startswith("card_bar."):
        part = key[len("card_bar."):]
        return part if part in ui_rules.PARTS else None
    return None


def part_rough_edges(part: str, parts: dict, picture: bool = False) -> list:
    """What the game does not quite do with a part where it is: drawn over
    (or under) the name where a long one reaches -- a monster's has up to 24
    letters (ATK, DEF and the stars are a monster's), another card's 28 (the
    type's icon and the word are a magic card's too); and over a picture of
    the mod's own for the bar, the letters' and digits' dark cells."""
    out = []
    if parts.get(part, {}).get("hide") is True:
        return out
    if picture and part in ("name", "atk", "def"):
        out.append("Its letters' cells are dark: over a lighter bar picture of yours they show as dark boxes.")

    def rect(name, letters=ui_rules.NAME_LETTERS):
        spacing = ui_rules.part_spacing(parts.get(name, {})) if name == "name" else 0
        x, y, w, h = ui_rules.part_home(name, spacing)
        if name == "name":
            w = letters * ui_rules.LETTER + (letters - 1) * spacing
        dx, dy = ui_rules.part_offset(name, parts.get(name, {}))
        return x + dx, y + dy, w, h

    def meet(a, b):
        return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]

    def letters(other):
        return 24 if other in ("atk", "def", "stars") else ui_rules.NAME_LETTERS
    shown = [n for n in ui_rules.PARTS if n != part and parts.get(n, {}).get("hide") is not True]
    if part == "name":
        hit = [PART_NAMES[n] for n in shown if meet(rect("name", letters(n)), rect(n))]
        if hit:
            out.append("A long name runs into " + ", ".join(hit) + " (a monster's has up to 24 letters, another "
                       "card's 28).")
    elif "name" in shown and meet(rect(part), rect("name", letters(part))):
        out.append("A long name runs into it (a monster's has up to 24 letters, another card's 28).")
    return out


# The words' boxes in a half (hd_text.c name_boxes): their rows from the half's
# top, and where they meet the panel.
LABEL_TOP = {"lp_opponent": 9, "lp_player": 1}
LABEL_JOIN = 25
LABEL_COLOR = {"lp_opponent": ("#2c3c98", "#b0b8ff"), "lp_player": ("#b81818", "#ffd8d8")}


def scale_of(name: str, element: dict) -> int:
    """The size the game draws it at: its "scale" (100 when out of range or
    not taken), no more than ui_rules.element_scale_max."""
    scale = as_int(element.get("scale"), 100)
    if name not in SIZED or not SCALE_MIN <= scale <= SCALE_MAX:
        return 100
    return min(scale, ui_rules.element_scale_max(name, element))


def place(rect, element: dict, name: str = None):
    """The function that moves a point of an element as the game does: by
    the "x" and "y" it takes, sized about its middle."""
    x, y, w, h = rect
    px_, py_ = x + w // 2, y + h // 2
    moves = MOVES.get(name, "xy")
    dx = as_int(element.get("x")) if "x" in moves else 0
    dy = as_int(element.get("y")) if "y" in moves else 0
    scale = scale_of(name, element) if name else as_int(element.get("scale"), 100)

    def at(gx, gy):
        def one(v, p, d):
            t = (v - p) * scale
            return p + d + ((t + 50) // 100 if t >= 0 else -((-t + 50) // 100))
        return one(gx, px_, dx), one(gy, py_, dy)
    return at


def rough_edges(name: str, element: dict) -> list:
    """What the game does not quite do with these settings (duel_ui.c,
    hd_text.c make_name): a short line each."""
    out = []
    if MOVES[name] == "y" and as_int(element.get("x")):
        out.append("Moved across in the mod: the game leaves that out, as it slides this off the side.")
    if name in SIZED and SCALE_MIN <= as_int(element.get("scale"), 100) <= SCALE_MAX and \
            as_int(element.get("scale"), 100) > scale_of(name, element):
        out.append(f"Larger than {scale_of(name, element)}% would not leave the screen with the game's: "
                   f"drawn at {scale_of(name, element)}%.")
    if MOVES[name] == "y":
        x, y, w, h = ua.DUEL_RECTS[name]
        bottom = place(ua.DUEL_RECTS[name], element, name)(x, y + h)[1]
        if bottom > FIELD_TOP:
            out.append("Down over the field: the cards there are drawn over or under it, in the game's order.")
    label = element.get("label")
    if name in LABELLED and isinstance(label, str) and label:
        if any(not " " <= c <= "~" for c in label):
            out.append("Only plain A-Z, 0-9 and signs: another letter brings back COM or YOU.")
        if element.get("image"):
            out.append("The words are not drawn over a picture of yours.")
    return out


class DuelPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.chosen = "lp_player"
        self.loading = False
        page_layout(self, self.draw, on_select=self.select, on_move=self.moved, on_wheel=self.wheel,
                    on_drag=self.dragging)
        self.opponent_turn = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.view.tools, text="Opponent's turn", variable=self.opponent_turn,
                        command=self.draw).pack(side="left")
        ttk.Label(self.view.tools, text="Bar shows").pack(side="left", padx=(px(self, 12), 4))
        self.bar_shows = tk.StringVar(value=BAR_SHOWS[0])
        ttk.Combobox(self.view.tools, textvariable=self.bar_shows, values=BAR_SHOWS, state="readonly",
                     width=12).pack(side="left")
        self.bar_shows.trace_add("write", lambda *a: self.draw())
        side = self.side
        self.title = self.heading
        form = ttk.Frame(side)
        form.grid(row=4, column=0, sticky="new", pady=(6, 0))
        form.columnconfigure(0, minsize=px(self, 110))
        self.vars = {key: tk.StringVar() for key in ("x", "y", "scale", "label", "width", "height", "spacing")}
        row = 0

        def line(text, widget):
            nonlocal row
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
            widget.grid(row=row, column=1, sticky="w", pady=2)
            row += 1
            return widget

        places = ttk.Frame(form)
        self.x_part = ttk.Frame(places)
        ttk.Label(self.x_part, text="x").pack(side="left", padx=(0, 4))
        self.x_box = ttk.Spinbox(self.x_part, from_=-400, to=400, width=5, textvariable=self.vars["x"],
                                 command=lambda: self.typed("x"))
        self.x_box.pack(side="left", padx=(0, 8))
        self.x_part.pack(side="left")
        ttk.Label(places, text="y").pack(side="left", padx=(0, 4))
        self.y_box = ttk.Spinbox(places, from_=-300, to=300, width=5, textvariable=self.vars["y"],
                                 command=lambda: self.typed("y"))
        self.y_box.pack(side="left")
        self.place_row = line("Moved by", places)
        self.place_caption = form.grid_slaves(row=row - 1, column=0)[0]
        sizes = ttk.Frame(form)
        self.scale_slider = ttk.Scale(sizes, from_=SCALE_MIN, to=SCALE_MAX, length=px(self, 180),
                                      command=self.slid)
        self.scale_slider.pack(side="left")
        self.scale_box = ttk.Spinbox(sizes, from_=SCALE_MIN, to=SCALE_MAX, increment=5, width=4,
                                     textvariable=self.vars["scale"], command=lambda: self.typed("scale"))
        self.scale_box.pack(side="left", padx=(6, 0))
        ttk.Label(sizes, text="%").pack(side="left")
        self.size_row = line("Size", sizes)
        self.size_caption = form.grid_slaves(row=row - 1, column=0)[0]
        self.tint = line("Color", ColorButton(form, lambda v: self.set_color("tint", v), multiplies=True))
        self.tint_caption = form.grid_slaves(row=row - 1, column=0)[0]
        self.digits = line("Digits", ColorButton(form, lambda v: self.set_color("digits", v), multiplies=True))
        self.digits_label = form.grid_slaves(row=row - 1, column=0)[0]
        self.label_entry = line("Words", ttk.Entry(form, textvariable=self.vars["label"], width=16))
        self.label_caption = form.grid_slaves(row=row - 1, column=0)[0]
        self.spacing_box = line("Letter spacing", ttk.Spinbox(form, from_=ui_rules.SPACING_MIN, to=ui_rules.SPACING_MAX,
                                                              width=4, textvariable=self.vars["spacing"],
                                                              command=lambda: self.typed("spacing")))
        self.spacing_caption = form.grid_slaves(row=row - 1, column=0)[0]
        for key in ("x", "y", "scale", "label", "width", "height", "spacing"):
            entry = {"x": self.x_box, "y": self.y_box, "scale": self.scale_box, "label": self.label_entry,
                     "spacing": self.spacing_box}.get(key)
            if entry is not None:
                entry.bind("<Return>", lambda e, k=key: self.typed(k))
                entry.bind("<FocusOut>", lambda e, k=key: self.typed(k))
        pictures = ttk.Frame(form)
        ttk.Button(pictures, text="Choose PNG...", command=self.choose_image).pack(side="left")
        self.remove_image = ttk.Button(pictures, text="Game's", command=self.clear_image)
        self.remove_image.pack(side="left", padx=(4, 0))
        self.picture_row = line("Picture", pictures)
        self.picture_caption = form.grid_slaves(row=row - 1, column=0)[0]
        self.image_name = ttk.Label(form, style="Hint.TLabel")
        self.image_name.grid(row=row, column=1, sticky="w")
        row += 1
        self.hidden = tk.BooleanVar()
        hide = ttk.Checkbutton(form, text="Hidden", variable=self.hidden, command=self.set_hidden)
        hide.grid(row=row, column=1, sticky="w", pady=(6, 0))
        row += 1
        ttk.Button(form, text="Back to the game's", command=self.reset).grid(row=row, column=1, sticky="w",
                                                                          pady=(10, 0))
        # The game's rough edges with what is set (rough_edges()).
        self.warning = ttk.Label(side, style="Warning.TLabel", wraplength=px(self, 440), justify="left")
        self.warning.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.status = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 440), justify="left")
        self.status.grid(row=6, column=0, sticky="w", pady=(6, 0))

    # --- the mod -------------------------------------------------------------------

    @property
    def project(self):
        return self.tab.project

    def element(self, name: str) -> dict:
        """An element's object in the mod, or a card bar part's
        ("card_bar.name"); {} for none."""
        part = part_of(name)
        value = section(self.project, "ui").get("duel", {})
        value = value.get("card_bar" if part else name) if isinstance(value, dict) else None
        if part and isinstance(value, dict):
            value = value.get(part)
        return value if isinstance(value, dict) else {}

    def edit(self, name: str) -> dict:
        part = part_of(name)
        if part:
            return ensure(self.project, "ui", "duel", "card_bar", part)
        return ensure(self.project, "ui", "duel", name)

    def done(self):
        self.tab.changed("ui")
        self.draw()
        self.fill_form()

    # --- the picture -------------------------------------------------------------------

    def fill(self):
        if self.project is None:
            return
        self.draw()
        self.fill_form()

    def reset_choice(self):
        self.chosen = "lp_player"

    def pick(self, iid, group=None):
        self.select(iid)

    def board(self, stage: Stage):
        """The board as the duel opens on it (duel_screen.board_backdrop):
        under everything, at the game's coordinates."""
        stage.create_rectangle(0, 0, 320 * stage.zoom, 240 * stage.zoom, fill="#000", outline="")
        if self.project is not None:
            stage.picture("board", duel_screen.board_backdrop(self.project), 0, 0, drag=False)

    def font(self):
        files = getattr(self.tab.app, "files", None)
        key = ("font", id(files))
        if key not in self.tab.assets:
            try:
                self.tab.assets[key] = card_text.RetailFont(getattr(files, "wa", None))
            except ValueError:
                self.tab.assets[key] = None
        return self.tab.assets[key]

    def hand(self, stage: Stage, duel):
        """The hand's five cards as the game draws them (duel_screen.hand_card)."""
        wa = getattr(getattr(self.tab.app, "files", None), "wa", None)
        for i, (x, y) in enumerate(duel_screen.HAND_AT):
            stage.picture(("hand", i), duel_screen.hand_card(self.project, wa, duel, HAND[i]), x, y, drag=False)

    def bar_card(self) -> int:
        """The card the bar shows: the hand's first, or (Bar shows: Magic
        card) the first magic card there is."""
        if self.bar_shows.get() == BAR_SHOWS[1]:
            cards = getattr(self.project, "cards", None) or {}
            magic = next((cid for cid in sorted(cards) if cards[cid].type == gamedata.TYPE_MAGIC), None)
            if magic is not None:
                return magic
        return HAND[0]

    def bar_words(self, stage: Stage, duel):
        """The card bar's words, numbers and icons for the card the cursor is
        on, each part where the mod puts it (duel_screen.bar_words): a part
        is dragged by any of its pieces; a hidden one is a dashed box where
        it would be."""
        wa = getattr(getattr(self.tab.app, "files", None), "wa", None)
        card_bar = self.element("card_bar")
        cid = self.bar_card()
        shown = duel_screen.bar_words(self.project, wa, duel, self.font(), cid, card_bar)
        # Where each part is, hidden or not: the same pieces with none hidden.
        unhidden = {name: dict(value, hide=False) for name, value in ui_rules.bar_parts(card_bar).items()}
        boxes = {}
        for picture, x, y, part in duel_screen.bar_words(self.project, wa, duel, self.font(), cid,
                                                         dict(card_bar, **unhidden)):
            x0, y0, x1, y1 = boxes.get(part, (x, y, x + picture.width, y + picture.height))
            boxes[part] = (min(x0, x), min(y0, y), max(x1, x + picture.width), max(y1, y + picture.height))
        for part, (x0, y0, x1, y1) in boxes.items():
            key = f"card_bar.{part}"
            stage.axes[key] = "xy"
            box = (x0, y0, x1 - x0, y1 - y0)
            if self.element(key).get("hide") is True:
                stage.rectangle(key, *box, outline="#9a9a9a", width=1, drag=True, dash=(3, 3))
            stage.boxes[key] = box
        for picture, x, y, part in shown:
            stage.picture(f"card_bar.{part}", picture, x, y, box=stage.boxes.get(f"card_bar.{part}"))

    def fill_list(self):
        """The pictures in groups, a dot on each the mod changes."""
        rows = []
        for group, text, names in GROUPS:
            rows.append((group, "", text, (), False, ("group",)))
            for name in names:
                own = {k: v for k, v in self.element(name).items() if name != "card_bar" or k not in ui_rules.PARTS}
                rows.append((name, group, NAMES[name], (), bool(own), ()))
                if name == "card_bar":
                    rows += [(f"card_bar.{part}", name, PART_NAMES[part], (), bool(self.element(f"card_bar.{part}")),
                              ()) for part in ui_rules.PARTS]
        self.list.fill(rows, self.chosen)

    def draw(self):
        if self.project is None:
            self.paint()
            return
        self.tab.draw_compared(self, self.paint)
        self.fill_list()

    def paint(self):
        stage = self.stage
        stage.clear()
        duel = self.tab.duel_art()
        self.board(stage)
        if not duel.ok:
            stage.create_text(160 * stage.zoom, 120 * stage.zoom, fill="#ccc",
                              text="The duel's pictures come from the game files (File > Game files...).")
            return
        turn = self.opponent_turn.get()
        pieces = {"card_bar": duel.card_bar(), "field": duel.field(), "hand_cursor": duel.hand_cursor(),
                  "field_cursor": duel.field_cursor(), "lp_opponent": duel.panel_half(0, turn),
                  "lp_player": duel.panel_half(1, turn)}
        # In the order the game draws them: the bar and its words, the field's
        # cursor, the FIELD box, the panel, the hand, the hand's cursor.
        self.draw_element(stage, "card_bar", pieces["card_bar"], duel, turn)
        self.bar_words(stage, duel)
        for name in ("field_cursor", "field", "lp_opponent", "lp_player"):
            self.draw_element(stage, name, pieces[name], duel, turn)
        self.hand(stage, duel)
        self.draw_element(stage, "hand_cursor", pieces["hand_cursor"], duel, turn)
        stage.outline(self.chosen)

    def draw_element(self, stage, name, piece, duel, turn):
        rect = ua.DUEL_RECTS[name]
        element = self.element(name)
        at = place(rect, element, name)
        stage.axes[name] = MOVES[name]
        x0, y0 = at(rect[0], rect[1])
        x1, y1 = at(rect[0] + rect[2], rect[1] + rect[3])
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        if element.get("hide") is True:
            stage.rectangle(name, x0, y0, w, h, outline="#9a9a9a", width=1, drag=True, dash=(3, 3))
            return
        tint = ua.parse_color(element.get("tint"))
        picture = mod_image(self.project, element.get("image")) if element.get("image") else None
        if picture is not None:
            iw, ih = as_int(element.get("width")), as_int(element.get("height"))
            if iw or ih:
                iw = iw or rect[2] * ih // rect[3]
                ih = ih or rect[3] * iw // rect[2]
                mx, my = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
                x0, y0 = at(mx - iw // 2, my - ih // 2)
                x1, y1 = at(mx - iw // 2 + iw, my - ih // 2 + ih)
                w, h = max(1, x1 - x0), max(1, y1 - y0)
            image = ua.tint(sized(picture, w, h), tint)
            stage.picture(name, image, x0, y0)
        else:
            image = piece if (w, h) == (piece.width, piece.height) else pngio.scale_to(piece, w, h)
            stage.picture(name, ua.tint(image, tint), x0, y0)
        if name in LABELLED:
            self.draw_digits(stage, name, element, at, duel, turn)
            label = element.get("label")
            if isinstance(label, str) and label and picture is None:
                self.draw_label(stage, name, label, rect, at, tint)

    def draw_digits(self, stage, name, element, at, duel, turn):
        tint = ua.parse_color(element.get("digits"))
        # The side whose turn it is lit, the other dimmed (0x80 and 0x40, Duel_DrawLifePointsAndDeckCounts).
        lit = (name == "lp_opponent") == turn
        values = {"lp_opponent": ("8000", "40"), "lp_player": ("8000", "35")}[name]
        for (x, y, count), text in zip(ua.LP_DIGITS[name], values):
            text = text.rjust(count)
            for i, ch in enumerate(text):
                if ch == " ":
                    continue
                gx0, gy0 = at(x + 8 * i, y)
                gx1, gy1 = at(x + 8 * i + 8, y + 8)
                digit = duel.digit(int(ch))
                if (gx1 - gx0, gy1 - gy0) != (8, 8):
                    digit = pngio.scale_to(digit, max(1, gx1 - gx0), max(1, gy1 - gy0))
                stage.picture((name, "digit"), ua.tint(digit, tint, 255 if lit else 128), gx0, gy0, drag=False)

    def draw_label(self, stage, name, label, rect, at, tint):
        """The words in the COM or YOU box, colored as the panel is (the
        game draws them through its palette and color)."""
        top = rect[1] + LABEL_TOP[name]

        def tinted(color):
            value = int(color[1:], 16)
            parts = [(value >> s & 255) * (tint >> s & 255) // 255 for s in (16, 8, 0)]
            return "#%02x%02x%02x" % tuple(parts)
        fill, ink = (tinted(c) for c in LABEL_COLOR[name])
        z = stage.zoom
        x1, y0 = at(rect[0] + LABEL_JOIN, top)
        _, y1 = at(rect[0] + LABEL_JOIN, top + 10)
        size = max(4, (y1 - y0) - 2)
        text = stage.create_text(0, 0, text=label, font=("Times", -max(6, size * z), "bold"), anchor="e")
        bx0, _, bx1, _ = stage.bbox(text)
        stage.delete(text)
        width = (bx1 - bx0) / z + 4
        stage.create_rectangle((x1 - width) * z, y0 * z, x1 * z, y1 * z, fill=fill, outline=tinted("#ffffff"))
        stage.create_text((x1 - 2) * z, (y0 + y1) / 2 * z, text=label, fill=ink,
                          font=("Times", -max(6, size * z), "bold"), anchor="e")

    # --- choosing and moving ------------------------------------------------------------

    def select(self, key):
        if isinstance(key, tuple) or key is None:
            return
        self.chosen = key
        self.list.show(key)
        self.stage.outline(key)
        self.fill_form()

    def dragging(self, key, dx, dy):
        part = part_of(key)
        if key == self.chosen and part:
            x, y = self.part_moved(key, dx, dy)
            self.vars["x"].set(str(x))
            self.vars["y"].set(str(y))
            return
        if key == self.chosen and MOVES.get(key):
            element = self.element(key)
            if "x" in MOVES[key]:
                self.vars["x"].set(str(max(-400, min(400, as_int(element.get("x")) + dx))))
            self.vars["y"].set(str(max(-300, min(300, as_int(element.get("y")) + dy))))

    def part_moved(self, key, dx, dy):
        """A part's place moved by dx, dy, kept on the bar (ui_rules.part_range)."""
        part = part_of(key)
        element = self.element(key)
        x, y = ui_rules.part_offset(part, element)
        x0, x1, y0, y1 = ui_rules.part_range(part, ui_rules.part_spacing(element) if part == "name" else 0)
        return max(x0, min(x1, x + dx)), max(y0, min(y1, y + dy))

    def moved(self, key, dx, dy):
        """A drag or the arrow keys: only the ways it moves (the stage keeps
        to them too); one that moves up and down only loses an "x" a
        hand-written mod gave it, which the game leaves out. A card bar part
        stays on the bar."""
        if part_of(key):
            x, y = self.part_moved(key, dx, dy)
            element = self.edit(key)
            set_member(element, "x", x, 0)
            set_member(element, "y", y, 0)
            self.select(key)
            self.done()
            return
        moves = MOVES.get(key, "")
        if not moves:
            return
        element = self.edit(key)
        if "x" in moves:
            set_member(element, "x", max(-400, min(400, as_int(element.get("x")) + dx)), 0)
        else:
            element.pop("x", None)
        set_member(element, "y", max(-300, min(300, as_int(element.get("y")) + dy)), 0)
        self.select(key)
        self.done()

    def most(self, key) -> int:
        return ui_rules.element_scale_max(key, self.element(key))

    def wheel(self, key, step):
        if key not in SIZED:
            return
        self.select(key)
        element = self.edit(key)
        scale = scale_of(key, element) + 10 * step
        set_member(element, "scale", max(SCALE_MIN, min(self.most(key), scale)), 100)
        self.done()

    # --- the form ------------------------------------------------------------------

    def fill_form(self):
        if self.project is None:
            return
        self.loading = True
        name = self.chosen
        element = self.element(name)
        if part_of(name):
            self.fill_part(name, element)
            self.loading = False
            return
        for widget in (self.picture_row, self.picture_caption, self.image_name, self.tint, self.tint_caption):
            widget.grid()
        for widget in (self.spacing_box, self.spacing_caption):
            widget.grid_remove()
        self.title.configure(text=NAMES[name])
        self.what.configure(text={
            "lp_opponent": "The panel's top half: the opponent's LP, COM and their deck count. It moves up and "
                           "down: the game slides it off the side for battles, and it slides with it.",
            "lp_player": "The panel's bottom half: YOU, your LP and your deck count. It moves up and down: the "
                         "game slides it off the side for battles, and it slides with it.",
            "field": "The terrain's name, top left. It moves up and down: the game slides it off the side for "
                     "battles, and it slides with it.",
            "card_bar": "The strip under the hand. It stays put, at its size: the hand's cards slide in and out with "
                        "it. Its colors and picture are yours, and its parts, listed under it, move about on it.",
            "hand_cursor": "The arrow under the card you are on.",
            "field_cursor": "The frame on the zone you are choosing."}[name])
        moves = MOVES[name]
        self.vars["x"].set(str(as_int(element.get("x")) if "x" in moves else 0))
        self.vars["y"].set(str(as_int(element.get("y"))))
        scale = scale_of(name, element)
        self.scale_slider.configure(to=self.most(name) if name in SIZED else SCALE_MAX)
        self.scale_box.configure(to=self.most(name) if name in SIZED else SCALE_MAX)
        self.vars["scale"].set(str(scale))
        self.scale_slider.set(scale)
        self.tint.set(ua.parse_color(element.get("tint")))
        self.digits.set(ua.parse_color(element.get("digits")))
        label = element.get("label")
        self.vars["label"].set(label if isinstance(label, str) else "")
        image = element.get("image")
        self.image_name.configure(text=image if isinstance(image, str) and image else "the game's own")
        self.remove_image.state(["!disabled"] if image else ["disabled"])
        self.hidden.set(element.get("hide") is True)
        # Only what it takes: no place for the card bar, no x for what moves
        # up and down only, no size for the card bar.
        for widget in (self.place_row, self.place_caption):
            if moves:
                widget.grid()
            else:
                widget.grid_remove()
        if "x" in moves:
            self.x_part.pack(side="left", before=self.x_part.master.winfo_children()[1])
        else:
            self.x_part.pack_forget()
        for widget in (self.size_row, self.size_caption):
            if name in SIZED:
                widget.grid()
            else:
                widget.grid_remove()
        labelled = name in LABELLED
        for widget in (self.digits, self.digits_label, self.label_entry, self.label_caption):
            if labelled:
                widget.grid()
            else:
                widget.grid_remove()
        self.warning.configure(text="\n".join(WARN + line for line in rough_edges(name, element)))
        self.status.configure(text="")
        self.loading = False

    def typed(self, key):
        if self.loading or self.project is None:
            return
        name = self.chosen
        if part_of(name):
            self.typed_part(name, key)
            return
        if (key == "x" and "x" not in MOVES[name]) or (key == "y" and not MOVES[name]) or \
                (key == "scale" and name not in SIZED):
            return
        text = self.vars[key].get().strip()
        element = self.edit(name)
        if key == "label":
            if len(text) > 15:
                self.status.configure(text="At most 15 letters.")
                text = text[:15]
            set_member(element, "label", text or None)
        else:
            try:
                value = int(text or 0)
            except ValueError:
                self.status.configure(text="A whole number.")
                return
            low, high, default = {"x": (-400, 400, 0), "y": (-300, 300, 0),
                                  "scale": (SCALE_MIN, self.most(name), 100)}[key]
            set_member(element, key, max(low, min(high, value)), default)
        self.done()

    def slid(self, value):
        if self.loading or self.project is None or self.chosen not in SIZED:
            return
        scale = min(int(round(float(value) / 5) * 5), self.most(self.chosen))
        if scale == as_int(self.element(self.chosen).get("scale"), 100):
            return
        set_member(self.edit(self.chosen), "scale", scale, 100)
        self.vars["scale"].set(str(scale))
        self.tab.changed("ui")
        self.draw()

    def set_color(self, key, value):
        if self.loading or self.project is None:
            return
        set_member(self.edit(self.chosen), key, color_text(value) if value is not None else None, "#FFFFFF")
        self.done()

    def choose_image(self):
        if self.project is None:
            return
        name = import_image(self, self.project, f"duel-{self.chosen.replace('_', '-')}")
        if name:
            self.edit(self.chosen)["image"] = name
            self.done()

    def clear_image(self):
        element = self.edit(self.chosen)
        for key in ("image", "width", "height"):
            element.pop(key, None)
        self.done()

    def set_hidden(self):
        if self.loading:
            return
        set_member(self.edit(self.chosen), "hide", True if self.hidden.get() else None)
        self.done()

    def reset(self):
        duel = ensure(self.project, "ui", "duel")
        part = part_of(self.chosen)
        if part:
            bar = duel.get("card_bar")
            if isinstance(bar, dict):
                bar.pop(part, None)
                if not bar:
                    duel.pop("card_bar", None)
        else:
            duel.pop(self.chosen, None)
        self.done()

    # --- the card bar's parts ----------------------------------------------------------

    def fill_part(self, name, element):
        """The form for a card bar part: its place, color, hidden, the
        name's letter spacing; no size or picture of its own."""
        part = part_of(name)
        self.title.configure(text=f"Card bar: {PART_NAMES[part]}")
        self.what.configure(text=PART_WHAT[part] + " It moves about on the bar's dark panel, under the hand "
                                                   "and on the bar's higher look over it.")
        x, y = ui_rules.part_offset(part, element)
        self.vars["x"].set(str(x))
        self.vars["y"].set(str(y))
        self.vars["spacing"].set(str(ui_rules.part_spacing(element)))
        for widget in (self.place_row, self.place_caption, self.tint, self.tint_caption):
            widget.grid()
        self.x_part.pack(side="left", before=self.x_part.master.winfo_children()[1])
        for widget in (self.size_row, self.size_caption, self.digits, self.digits_label, self.label_entry,
                       self.label_caption, self.picture_row, self.picture_caption, self.image_name):
            widget.grid_remove()
        for widget in (self.spacing_box, self.spacing_caption):
            if part == "name":
                widget.grid()
            else:
                widget.grid_remove()
        self.tint.set(ua.parse_color(element.get("tint")))
        self.hidden.set(element.get("hide") is True)
        bar = self.element("card_bar")
        picture = isinstance(bar.get("image"), str) and bool(bar.get("image"))
        self.warning.configure(text="\n".join(WARN + line for line in
                                               part_rough_edges(part, ui_rules.bar_parts(bar), picture)))
        self.status.configure(text="")

    def typed_part(self, name, key):
        part = part_of(name)
        if key not in ("x", "y", "spacing") or (key == "spacing" and part != "name"):
            return
        try:
            value = int(self.vars[key].get().strip() or 0)
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        element = self.edit(name)
        if key == "spacing":
            set_member(element, "spacing", max(ui_rules.SPACING_MIN, min(ui_rules.SPACING_MAX, value)), 0)
            # Spread, the name may reach off the bar: brought back on it.
            x, y = ui_rules.part_offset(part, element)
            set_member(element, "x", x, 0)
        else:
            x0, x1, y0, y1 = ui_rules.part_range(part, ui_rules.part_spacing(element) if part == "name" else 0)
            low, high = (x0, x1) if key == "x" else (y0, y1)
            set_member(element, key, max(low, min(high, value)), 0)
        self.done()
