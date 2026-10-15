"""The Rituals tab: each ritual card's recipe as the duel reads it, drawn as
cards in a row -- the ritual card, its one to five tributes, and what it
summons -- with where the tributes may be (the field, as on the disc, the
hand, or both) and a sentence saying it all in words.

The list on the left has every ritual card. Choosing one shows its recipe;
a click on a card of the row edits it below (a tribute: a card, or any
monster meeting conditions; the result: a monster). Every change is the
mod's at once, as the Equips tab's are (Undo takes it back). The game's
side: src/pc/cards/tables.c read_rituals, src/game/duel_check_ritual.c."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import art, pngio, text_menu, theme
from .gamedata import FUSION_GROUPS, RITUAL_TRIBUTE_MAX, TYPE_NAMES
from .icon_choice import IconChoice
from .model import same_letters
from .tabs import Tab
from .widgets import CardField, WrapLabel, card_matches, card_named, legend, pick_card, px, scrolled_tree, ui_font

ORIGINS = (("field", "On the field"), ("hand", "In the hand"), ("both", "Both"))
ORIGIN_HINTS = {
    "field": "Monsters on the player's side of the field, as the game's own rituals take them. The result takes the "
             "zone of the middle tribute.",
    "hand": "Monsters in the hand, played with the ritual card. The result goes to the first free monster zone; "
            "with the field full the ritual cannot take place. Played from the hand, the ritual card leaves four "
            "others there (five when it was set face down first).",
    "both": "Monsters in the hand or on the field. A hand card is spent before a field one that would do as well; "
            "the result takes a field tribute's zone, or the first free one.",
}
WHERE = {"field": "on the field", "hand": "in the hand", "both": "in the hand or on the field"}
# A tribute's conditions (tables.c ritual_requirement): what the editor
# calls each, in the order the Add condition menu lists them.
CONDITIONS = (("type", "Monster type"), ("fusion_group", "Fusion group"), ("min_attack", "ATK at least"),
              ("max_attack", "ATK at most"), ("min_defense", "DEF at least"), ("max_defense", "DEF at most"),
              ("min_level", "Level at least"), ("max_level", "Level at most"), ("defense_gt_attack", "DEF above ATK"),
              ("card", "Is this card (or a copy)"))
NUMBERS = {"min_attack": 9999, "max_attack": 9999, "min_defense": 9999, "max_defense": 9999, "min_level": 12,
           "max_level": 12}
NUMBER_DEFAULTS = {"min_attack": 1000, "max_attack": 2000, "min_defense": 1000, "max_defense": 2000,
                   "min_level": 1, "max_level": 12}

# The recipe row's colors: light, dark (theme.py's palettes).
COLORS = {
    "tile": ("#ffffff", "#2a2b2f"),
    "line": ("#b8bcc2", "#55585e"),
    "group": ("#e8ecf2", "#25272b"),
    "ink": ("#202124", "#e8eaed"),
    "hint": ("#5f6368", "#a3a9b0"),
    "pick": ("#1a5fb4", "#8ab4f8"),
    "ritual": ("#2848b0", "#7f9cf0"),     # the game's ritual frame
    "result": ("#b07800", "#e0a838"),     # a monster's gold
    "add": ("#8c9197", "#8c9197"),
    "remove": ("#c01c28", "#ff8f87"),
    "picture": ("#d9dce1", "#383a40"),
}


def color(widget, key: str) -> str:
    light, dark = COLORS[key]
    return dark if theme.is_dark(widget) else light


def article(word: str) -> str:
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def _range(low, high, what: str) -> str:
    if low is not None and high is not None:
        return f"{what} {low}" if low == high else f"{what} {low}\u2013{high}"
    if low is not None:
        return f"{what} {low}+"
    return f"{what} up to {high}"


def condition_lines(project, req: dict) -> list:
    """A tribute's conditions, short, a line each (the tile's caption)."""
    if not req:
        return ["(nothing)"]
    lines = []
    if req.get("card"):
        lines.append(project.cards[req["card"]].name if req["card"] in project.cards else f"#{req['card']}")
    kind = " ".join(x for x in (req.get("fusion_group"), req.get("type")) if x)
    if kind:
        lines.append(kind)
    if req.get("min_attack") is not None or req.get("max_attack") is not None:
        if req.get("min_attack") == 0 and req.get("max_attack") is None:
            if len(req) == 1:
                lines.append("Any monster")
        else:
            lines.append(_range(req.get("min_attack"), req.get("max_attack"), "ATK"))
    if req.get("min_defense") is not None or req.get("max_defense") is not None:
        lines.append(_range(req.get("min_defense"), req.get("max_defense"), "DEF"))
    if req.get("min_level") is not None or req.get("max_level") is not None:
        lines.append(_range(req.get("min_level"), req.get("max_level"), "Level"))
    if req.get("defense_gt_attack"):
        lines.append("DEF > ATK")
    return lines or ["Any monster"]


def describe(project, req: dict) -> str:
    """A tribute in words: "Blue-eyes White Dragon", "a Female Spellcaster
    with DEF 1500+", "any monster"."""
    if set(req) == {"card"}:
        card = project.cards.get(req["card"])
        return card.name if card else f"card {req['card']}"
    noun = " ".join(x for x in (req.get("fusion_group"), req.get("type") or "monster") if x)
    if req.get("card"):
        noun = f"{project.cards[req['card']].name}" if req["card"] in project.cards else f"card {req['card']}"
        text = noun
    else:
        text = article(noun)
    terms = []
    if req.get("min_attack") is not None or req.get("max_attack") is not None:
        if not (req.get("min_attack") == 0 and req.get("max_attack") is None):
            terms.append(_range(req.get("min_attack"), req.get("max_attack"), "ATK"))
    if req.get("min_defense") is not None or req.get("max_defense") is not None:
        terms.append(_range(req.get("min_defense"), req.get("max_defense"), "DEF"))
    if req.get("min_level") is not None or req.get("max_level") is not None:
        terms.append(_range(req.get("min_level"), req.get("max_level"), "level"))
    if req.get("defense_gt_attack"):
        terms.append("more DEF than ATK")
    if text == "a monster" and not terms:
        return "any monster"
    return text + (" with " + " and ".join(terms) if terms else "")


def sentence(project, ritual: int, tributes: list, result: int, origin: str) -> str:
    """The whole recipe in words."""
    counted = []
    for req in tributes:
        text = describe(project, req)
        for row in counted:
            if row[0] == text:
                row[1] += 1
                break
        else:
            counted.append([text, 1])
    parts = [text if n == 1 else f"{n} \u00d7 {text}" for text, n in counted]
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    summoned = project.cards[result].name if result in project.cards else f"card {result}"
    return f"Play {project.cards[ritual].name} with {listed} {WHERE[origin]} to summon {summoned}."


def fit_lines(text: str, font: str, width: int, most: int) -> list:
    """The text wrapped at word breaks to lines of `width` pixels, at most
    `most` of them, the last cut short with an ellipsis when it goes on."""
    measure = tkfont.nametofont(font).measure
    lines, words = [], text.split()
    while words and len(lines) < most:
        line = words.pop(0)
        while words and measure(line + " " + words[0]) <= width:
            line += " " + words.pop(0)
        lines.append(line)
    if words or (lines and measure(lines[-1]) > width):
        last = lines[-1] + (" " + " ".join(words) if words else "")
        while last and measure(last + "\u2026") > width:
            last = last[:-1].rstrip()
        lines[-1] = last + "\u2026"
    return lines


class RecipeRow(tk.Canvas):
    """The recipe as cards in a row: the ritual card, a panel of its
    tributes (and an empty card to add one), an arrow and what it summons,
    sized to the width the tab gives it. on_pick(key) gets "ritual", a
    tribute's index or "result"; on_add() and on_remove(index) the panel's
    buttons."""

    LABEL, NAME, SMALL = (7, "bold"), (8, "bold"), (8, "normal")

    def __init__(self, master, tab, on_pick, on_add, on_remove):
        # As wide as the tab gives it (its cards are sized to that), not asking for more.
        super().__init__(master, highlightthickness=0, borderwidth=0, width=px(master, 300), height=px(master, 220))
        self.tab, self.on_pick, self.on_add, self.on_remove = tab, on_pick, on_add, on_remove
        self.recipe = None          # (ritual, tributes, result, origin, editable)
        self.picked = None
        self._width = None
        self.bind("<Configure>", self._resized)
        self.bind("<<ThemeChanged>>", lambda e: self.draw(), add="+")

    def _resized(self, event):
        if event.width != self._width:
            self._width = event.width
            self.draw()

    def show(self, recipe, picked):
        self.recipe, self.picked = recipe, picked
        self.draw()

    def draw(self):
        self.delete("all")
        try:
            background = ttk.Style(self).lookup("TFrame", "background")
        except tk.TclError:
            background = ""
        self.configure(background=background or color(self, "group"))
        if not self.recipe:
            self.configure(height=1)
            return
        ritual, tributes, result, origin, editable = self.recipe
        adding = editable and len(tributes) < RITUAL_TRIBUTE_MAX
        gap, pad, plus, arrow, edge = (px(self, n) for n in (8, 10, 26, 40, 4))
        # Every card as wide as the room allows (the empty one to add a
        # tribute 0.6 of one), between a small and a full size.
        room = max(self.winfo_width(), px(self, 300)) - 2 * edge - plus - arrow - 2 * pad - \
            gap * (len(tributes) - 1 + adding)
        w = max(px(self, 58), min(px(self, 112), int(room / (2 + len(tributes) + 0.6 * adding))))
        tall = (w - px(self, 10)) * 96 // 102
        line = tkfont.nametofont(ui_font(*self.NAME)).metrics("linespace")
        small = tkfont.nametofont(ui_font(*self.LABEL)).metrics("linespace")
        h = px(self, 18) + tall + px(self, 4) + 3 * line + small + px(self, 6)
        top = px(self, 22)
        self.tab.images = []        # the pictures of this drawing, kept while it shows
        x = edge
        self._tile(x, top, w, h, tall, "ritual", ritual, "RITUAL", color(self, "ritual"))
        x += w
        self._operator(x, top + h // 2, plus, "+")
        x += plus
        add_w = int(w * 0.6) if adding else 0
        group_w = pad * 2 + len(tributes) * w + gap * (len(tributes) - 1 + adding) + add_w
        self.create_rectangle(x, top - px(self, 6), x + group_w, top + h + px(self, 6),
                              fill=color(self, "group"), outline=color(self, "line"))
        count = f"{len(tributes)} TRIBUTE{'S' if len(tributes) != 1 else ''}"
        self.create_text(x + px(self, 2), top - px(self, 9), anchor="sw", fill=color(self, "hint"),
                         font=ui_font(*self.LABEL), text=f"{count} \u00b7 {WHERE[origin].upper()}")
        tx = x + pad
        for index, req in enumerate(tributes):
            plain = set(req) == {"card"}
            self._tile(tx, top, w, h, tall, index, req["card"] if plain else None, f"TRIBUTE {index + 1}",
                       color(self, "pick"), None if plain else req)
            if editable and len(tributes) > 1:
                self._remove_button(tx + w - px(self, 9), top + px(self, 11), index)
            tx += w + gap
        if adding:
            self._add_tile(tx, top, add_w, h)
        x += group_w
        self._operator(x, top + h // 2, arrow, "\u2192")
        x += arrow
        self._tile(x, top, w, h, tall, "result", result, "SUMMONS", color(self, "result"))
        self.configure(height=top + h + px(self, 10))

    def _operator(self, x, y, width, text):
        self.create_text(x + width // 2, y, text=text, fill=color(self, "hint"), font=ui_font(16))

    def _tile(self, x, y, w, h, tall, key, cid, label, accent, req=None):
        project = self.tab.project
        picked = key == self.picked
        tag = f"tile:{key}"
        self.create_rectangle(x, y, x + w, y + h, fill=color(self, "tile"),
                              outline=color(self, "pick") if picked else color(self, "line"),
                              width=px(self, 3) if picked else 1, tags=(tag,))
        self.create_rectangle(x + 1, y + 1, x + w, y + px(self, 4), fill=accent, outline="", tags=(tag,))
        self.create_text(x + px(self, 5), y + px(self, 11), text=label, fill=color(self, "hint"),
                         font=ui_font(*self.LABEL), anchor="w", tags=(tag,))
        inner = w - px(self, 10)
        py = y + px(self, 18)
        image = self.tab.picture(cid, inner, tall) if cid else None
        if image is not None:
            self.tab.images.append(image)
            self.create_image(x + w // 2, py, image=image, anchor="n", tags=(tag,))
        else:
            self.create_rectangle(x + px(self, 5), py, x + w - px(self, 5), py + tall, fill=color(self, "picture"),
                                  outline="", tags=(tag,))
            icon = self.tab.type_icon(req.get("type"), 3 if w >= px(self, 96) else 2) if req else None
            if icon is not None:
                self.tab.images.append(icon)
                self.create_image(x + w // 2, py + tall // 2, image=icon, tags=(tag,))
            else:
                self.create_text(x + w // 2, py + tall // 2, text="?" if req is not None else "-",
                                 fill=color(self, "hint"), font=ui_font(20), tags=(tag,))
        name_font, small_font = ui_font(*self.NAME), ui_font(*self.SMALL)
        width = w - px(self, 8)
        stats = None
        if req is not None:
            rows = [(text, small_font if n else name_font) for n, text in enumerate(condition_lines(project, req))]
            lines = [(fit_lines(text, font, width, 1)[0], font) for text, font in rows[:3]]
        else:
            card = project.cards.get(cid) if cid else None
            lines = [(text, name_font) for text in fit_lines(card.name if card else "(no card)", name_font, width, 2)]
            if card is not None and card.is_monster():
                stats = f"{card.attack} / {card.defense}"
        ty = py + tall + px(self, 4)
        for n, (text, font) in enumerate(lines):
            self.create_text(x + w // 2, ty, text=text, anchor="n", font=font, tags=(tag,),
                             fill=color(self, "ink") if font == name_font else color(self, "hint"))
            ty += tkfont.nametofont(font).metrics("linespace")
        if stats:   # ATK / DEF at the card's foot, as the game's cards have them
            self.create_text(x + w // 2, y + h - px(self, 4), text=stats, anchor="s", fill=color(self, "hint"),
                             font=ui_font(*self.LABEL), tags=(tag,))
        self.tag_bind(tag, "<Button-1>", lambda e, k=key: self.on_pick(k))
        self._hand(tag)

    def _hand(self, tag):
        self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))

    def _add_tile(self, x, y, w, h):
        tag = "add"
        self.create_rectangle(x, y, x + w, y + h, outline=color(self, "add"), dash=(4, 3),
                              fill=color(self, "group"), width=1, tags=(tag,))
        self.create_text(x + w // 2, y + h // 2 - px(self, 10), text="+", fill=color(self, "add"), font=ui_font(20),
                         tags=(tag,))
        for n, text in enumerate(("Add a", "tribute")):
            self.create_text(x + w // 2, y + h // 2 + px(self, 14 + 13 * n), text=text, fill=color(self, "hint"),
                             font=ui_font(*self.SMALL), tags=(tag,))
        self.tag_bind(tag, "<Button-1>", lambda e: self.on_add())
        self._hand(tag)

    def _remove_button(self, x, y, index):
        tag = f"remove:{index}"
        r = px(self, 7)
        self.create_oval(x - r, y - r, x + r, y + r, fill=color(self, "tile"), outline=color(self, "remove"),
                         tags=(tag,))
        self.create_text(x, y, text="\u00d7", fill=color(self, "remove"), font=ui_font(9), tags=(tag,))
        self.tag_bind(tag, "<Button-1>", lambda e, i=index: self.on_remove(i))
        self._hand(tag)


class PickedCardField(CardField):
    """A CardField whose "..." picker applies the card it gives: picked()
    once the picker has closed (not within a Tk call of a box the change
    draws again)."""

    picked = None

    def pick(self):
        before = self.var.get()
        super().pick()
        if self.picked is not None and self.var.get() != before:
            # On the window, which outlives this box.
            self.winfo_toplevel().after_idle(self.picked)


class RitualsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Rituals")
        self.current = None         # the ritual card shown
        self.picked = 0             # the card of the row being edited: a tribute's index, "result" or "ritual"
        self.images = []
        self._pictures = {}

        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        search = ttk.Frame(left)
        search.pack(fill="x", pady=(0, 4))
        ttk.Label(search, text="Search").pack(side="left")
        self.search = tk.StringVar()
        ttk.Entry(search, textvariable=self.search, width=18).pack(side="left", padx=(6, 8), fill="x", expand=True)
        self.changed_only = tk.IntVar()
        ttk.Checkbutton(search, text="Changed only", variable=self.changed_only,
                        command=self.fill).pack(side="left")
        self.search.trace_add("write", lambda *_: self.fill())
        frame, self.tree = scrolled_tree(left, [("ritual", "Ritual card"), ("tributes", "Tributes"),
                                                ("result", "Summons"), ("state", "Status")],
                                         [212, 70, 168, 66], 24)
        frame.pack(fill="y", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())
        self.tree.bind("<Delete>", lambda e: self.remove())
        legend(left, ("changed", "changed"), ("added", "added"), ("removed", "no recipe")).pack(anchor="w",
                                                                                              pady=(2, 0))

        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        head = ttk.Frame(right)
        head.pack(fill="x")
        actions = ttk.Frame(head)
        actions.pack(side="right")
        self.thumb = ttk.Label(head)
        self.thumb.pack(side="left", padx=(0, 8))
        self.heading = ttk.Label(head, font=ui_font(12))
        self.heading.pack(side="left")
        self.status = WrapLabel(right, style="Hint.TLabel")
        self.status.pack(fill="x", pady=(4, 0))
        self.own_button = ttk.Button(actions, text="Give it its own recipe", command=self.make_own)
        self.revert_button = ttk.Button(actions, text="Revert to the game's", command=self.revert)
        self.remove_button = ttk.Button(actions, text="Remove recipe", command=self.remove)
        for button in (self.own_button, self.revert_button, self.remove_button):
            button.pack(side="left", padx=(4, 0))

        origin = ttk.Frame(right)
        origin.pack(fill="x", pady=(10, 0))
        ttk.Label(origin, text="Tributes come from").pack(side="left", padx=(0, 8))
        self.origin = tk.StringVar(value="field")
        self.origin_buttons = []
        for value, text in ORIGINS:
            button = ttk.Radiobutton(origin, text=text, value=value, variable=self.origin,
                                     style="Segment.Toolbutton", command=self.set_origin)
            button.pack(side="left")
            self.origin_buttons.append(button)
        self.origin_hint = WrapLabel(right, style="Hint.TLabel")
        self.origin_hint.pack(fill="x", pady=(4, 0))

        self.row = RecipeRow(right, self, self.pick, self.add_tribute, self.remove_tribute)
        self.row.pack(fill="x", pady=(10, 0))
        self.words = WrapLabel(right)
        self.words.pack(fill="x", pady=(2, 0))

        self.editor = ttk.LabelFrame(right, padding=(10, 6))
        self.editor.pack(fill="x", pady=(10, 0))
        self.error = ttk.Label(right, style="Error.TLabel")
        self.error.pack(fill="x", pady=(4, 0))
        # The editor's typed fields: a number's key -> (variable, its most,
        # the tribute), read when it is left; a card box's name -> the box.
        self._inputs = {}

    # --- the list ---------------------------------------------------------

    def refresh(self):
        self._pictures = {}     # the Art tab may have changed a picture
        self.fill()

    def fill(self):
        if self.project is None:
            return
        p = self.project
        chosen = self.current
        self.tree.delete(*self.tree.get_children())
        text = self.search.get().strip()
        for ritual in sorted(set(p.ritual_cards()) | set(p.rituals) | set(p.retail.rituals)):
            if ritual not in p.cards:
                continue
            values, state = self.row_values(ritual)
            if self.changed_only.get() and not state:
                continue
            if text and not self.matches(ritual, text):
                continue
            self.tree.insert("", "end", iid=str(ritual), values=values, tags=(state,) if state else ())
        rows = self.tree.get_children()
        if chosen is not None and self.tree.exists(str(chosen)):
            self.tree.selection_set(str(chosen))
            self.tree.see(str(chosen))
            self.show()
        elif rows:
            self.current = None
            self.tree.selection_set(rows[0])
            self.select()
        else:
            self.current = None
            self.show()

    def row_values(self, ritual: int):
        p = self.project
        state = p.ritual_status(ritual)
        if ritual in p.added and ritual not in p.rituals and ritual not in p.ritual_requirements:
            state = state or "as base"
        recipe = p.ritual_recipe(ritual)
        if recipe is None:
            return [p.card_label(ritual), "-", "-", state], state
        tributes, result, origin = recipe
        return [p.card_label(ritual), f"{len(tributes)} · {origin}", p.card_label(result), state], state

    def matches(self, ritual: int, text: str) -> bool:
        p = self.project
        recipe = p.ritual_recipe(ritual)
        cards = [ritual]
        if recipe:
            cards += [req["card"] for req in recipe[0] if req.get("card")] + [recipe[1]]
        return any(c in p.cards and card_matches(p, c, text) for c in cards)

    def selected(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def select(self):
        ritual = self.selected()
        if ritual is not None and ritual != self.current:
            self.read_inputs()
            self.current = ritual
            self.picked = 0
            self.show()

    def show_card(self, cid):
        if not self.tree.exists(str(cid)) and (self.search.get() or self.changed_only.get()):
            self.search.set("")
            self.changed_only.set(0)
            self.fill()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))
            self.select()

    def follow(self, cid):
        if cid != self.current and self.project is not None and cid in self.project.ritual_cards():
            self.show_card(cid)

    # --- the recipe -------------------------------------------------------

    def recipe(self):
        """(tributes, result, origin, own): what the shown ritual card
        summons by, own False for an added copy's base's; None for none."""
        p = self.project
        found = p.ritual_recipe(self.current)
        if found is None:
            return None
        own = self.current in p.rituals
        return found[0], found[1], found[2], own

    def picture(self, cid, width, height):
        """The card's picture as the game draws it, at this size; None
        without the game files."""
        key = (cid, width, height)
        if key in self._pictures:
            return self._pictures[key]
        image = None
        files = getattr(self.app, "files", None)
        if cid in self.project.cards and files is not None and getattr(files, "wa", None):
            try:
                image, _ = art.shown_image(self.project, files.wa, cid, "art")
            except (OSError, ValueError, KeyError, IndexError):
                image = None
        photo = None
        if image is not None:
            photo = tk.PhotoImage(master=self, data=pngio.ppm(pngio.scale_to(image, width, height)), format="PPM")
        self._pictures[key] = photo
        return photo

    def type_icon(self, name, zoom=2):
        if not name:
            return None
        names = getattr(self.project, "type_names", TYPE_NAMES)
        type_ = next((i for i, candidate in enumerate(names)
                      if candidate and same_letters(name, candidate)), -1)
        # Retail names remain valid aliases if a type was renamed.  Custom
        # icon files are mod assets and are not presently decoded by this
        # Tk preview; returning None retains the existing question-mark cue.
        if type_ < 0:
            type_ = next((i for i, candidate in enumerate(TYPE_NAMES) if same_letters(name, candidate)), -1)
        if type_ < 0 or type_ >= len(TYPE_NAMES):
            return None
        shown = text_menu.pictures(self.app, self, zoom)
        return shown.icons.get(type_) if shown else None

    def show(self):
        """The shown ritual card's recipe: the head, the place, the row of
        cards, the words and the editor."""
        p = self.project
        self.error.configure(text="")
        if p is None or self.current is None or self.current not in p.cards:
            self.heading.configure(text="No ritual card")
            self.status.configure(text="")
            self.thumb.configure(image="")
            self.row.show(None, None)
            self.words.configure(text="")
            self._editor(None)
            return
        ritual = self.current
        recipe = self.recipe()
        thumb = self.picture(ritual, px(self, 51), px(self, 48))
        self.thumb.configure(image=thumb or "")
        self.heading.configure(text=p.card_label(ritual))
        state = p.ritual_status(ritual)
        own = ritual in p.rituals and p.rituals[ritual] is not None
        if recipe is None:
            status = "No recipe: playing it does nothing."
        elif not recipe[3]:
            status = f"An added copy: it summons by its base's recipe ({p.card_label(p.base_of(ritual))})."
        elif state == "changed":
            retail = p.retail.rituals.get(ritual)
            status = "Changed by the mod" + (f" (the game's: {len(retail) - 1} from the field → "
                                             f"{p.cards[retail[-1]].name})." if retail else ".")
        elif state == "added":
            status = "A recipe the mod adds."
        else:
            status = "The game's own recipe."
        self.status.configure(text=status, style="Changed.TLabel" if state in ("changed", "added") else "Hint.TLabel")
        self.own_button.pack_forget()
        self.revert_button.pack_forget()
        self.remove_button.pack_forget()
        if recipe is None or not recipe[3]:
            self.own_button.configure(text="Give it a recipe" if recipe is None else "Give it its own recipe")
            self.own_button.pack(side="left", padx=(4, 0))
        if state or (ritual in p.added and own):
            self.revert_button.configure(text="Revert to the game's" if ritual in p.retail.rituals
                                         else "Back to its base's" if ritual in p.added else "Revert")
            self.revert_button.pack(side="left", padx=(4, 0))
        if recipe is not None and recipe[3]:
            self.remove_button.pack(side="left", padx=(4, 0))
        editable = recipe is not None and recipe[3]
        for button in self.origin_buttons:
            button.state(["!disabled"] if editable else ["disabled"])
        if recipe is None:
            self.origin.set("field")
            self.origin_hint.configure(text="")
            self.row.show(None, None)
            self.words.configure(text="Give it a recipe to make it summon a monster.")
            self._editor(None)
            return
        tributes, result, origin, _ = recipe
        self.origin.set(origin)
        self.origin_hint.configure(text=ORIGIN_HINTS[origin])
        if isinstance(self.picked, int) and self.picked >= len(tributes):
            self.picked = len(tributes) - 1
        self.row.show((ritual, tributes, result, origin, editable), self.picked if editable else None)
        self.words.configure(text=sentence(p, ritual, tributes, result, origin))
        self._editor(self.picked if editable else None)

    def store(self, tributes, result, origin, keep_editor=False):
        """The recipe is the mod's from now on. With keep_editor the fields
        below the row stay as they are (a number being typed in one)."""
        self.project.set_ritual(self.current, tributes, result, origin)
        self.app.changed()
        values, state = self.row_values(self.current)
        if self.tree.exists(str(self.current)):
            self.tree.item(str(self.current), values=values, tags=(state,) if state else ())
        if keep_editor:
            recipe = self.recipe()
            self.row.show((self.current, recipe[0], recipe[1], recipe[2], True), self.picked)
            self.words.configure(text=sentence(self.project, self.current, recipe[0], recipe[1], recipe[2]))
            self.error.configure(text="")
            return
        self.show()

    def pick(self, key):
        self.read_inputs()
        self.picked = key
        self.show()

    def set_origin(self):
        recipe = self.recipe()
        if recipe and recipe[3] and self.origin.get() != recipe[2]:
            self.read_inputs()
            self.store(recipe[0], recipe[1], self.origin.get())

    def add_tribute(self):
        recipe = self.recipe()
        if not recipe or not recipe[3] or len(recipe[0]) >= RITUAL_TRIBUTE_MAX:
            return
        self.read_inputs()
        tributes = recipe[0] + [{"min_attack": 0}]
        self.picked = len(tributes) - 1
        self.store(tributes, recipe[1], recipe[2])

    def remove_tribute(self, index=None):
        recipe = self.recipe()
        index = self.picked if index is None else index
        if not recipe or not recipe[3] or len(recipe[0]) <= 1 or not isinstance(index, int):
            return
        self.read_inputs()
        tributes = [t for i, t in enumerate(recipe[0]) if i != index]
        self.picked = min(index, len(tributes) - 1)
        self.store(tributes, recipe[1], recipe[2])

    # --- the editor below the row ----------------------------------------

    def _editor(self, key):
        for child in self.editor.winfo_children():
            child.destroy()
        self._inputs = {}
        recipe = self.recipe()
        if key is None or recipe is None:
            self.editor.configure(text="")
            self.editor.pack_forget()
            return
        if not self.editor.winfo_ismapped():
            self.editor.pack(fill="x", pady=(10, 0), before=self.error)
        tributes, result, origin, _ = recipe
        if key == "ritual":
            self.editor.configure(text="Ritual card")
            WrapLabel(self.editor, style="Hint.TLabel",
                      text="The card the player plays. Its name, picture and type are on the Cards tab; a copy of "
                           "a ritual card (or a card whose effect is one) can have a recipe of its own.").pack(
                fill="x")
            ttk.Button(self.editor, text="Open on the Cards tab",
                       command=lambda: self.app.open_card(self.app.cards, self.current)).pack(anchor="w",
                                                                                              pady=(6, 0))
        elif key == "result":
            self.editor.configure(text="Summons")
            row = ttk.Frame(self.editor)
            row.pack(fill="x")
            ttk.Label(row, text="Monster").pack(side="left", padx=(0, 8))
            field = PickedCardField(row, lambda: self.project, width=34, only=self.is_monster)
            field.pack(side="left", fill="x", expand=True)
            field.set(result)
            self._card_input("result", field, self.set_result)
            WrapLabel(self.editor, style="Hint.TLabel",
                      text="It takes the zone of the middle field tribute, or with every tribute from the hand "
                           "the first free one; the player picks its guardian star.").pack(fill="x", pady=(6, 0))
        else:
            self._tribute_editor(key, tributes, result, origin)

    def set_result(self, cid):
        recipe = self.recipe()
        if recipe:
            self.store(recipe[0], cid, recipe[2])

    def is_monster(self, cid) -> bool:
        card = self.project.cards.get(cid)
        return bool(card and card.is_monster())

    def _tribute_editor(self, index, tributes, result, origin):
        req = tributes[index]
        self.editor.configure(text=f"Tribute {index + 1} of {len(tributes)}")
        top = ttk.Frame(self.editor)
        top.pack(fill="x")
        kind = tk.StringVar(value="card" if set(req) == {"card"} else "rule")
        for value, text in (("card", "A specific card"), ("rule", "Any monster that...")):
            ttk.Radiobutton(top, text=text, value=value, variable=kind, style="Segment.Toolbutton",
                            command=lambda: self.switch_kind(index, kind.get())).pack(side="left")
        remove = ttk.Button(top, text="Remove this tribute", command=lambda: self.remove_tribute(index))
        remove.pack(side="right")
        if len(tributes) <= 1:
            remove.state(["disabled"])

        def put(changes=None, drop=None, whole=None):
            """This tribute changed: keys set, one taken away, or all of it
            new; a number still in its box is taken first."""
            self.read_inputs()
            now = self.recipe()
            new = dict(whole) if whole is not None else dict(now[0][index])
            new.update(changes or {})
            new.pop(drop, None)
            changed = [dict(t) for t in now[0]]
            changed[index] = new
            self.store(changed, now[1], now[2])

        body = ttk.Frame(self.editor)
        body.pack(fill="x", pady=(8, 0))
        if kind.get() == "card":
            row = ttk.Frame(body)
            row.pack(fill="x")
            ttk.Label(row, text="Card").pack(side="left", padx=(0, 8))
            field = PickedCardField(row, lambda: self.project, width=34, only=self.is_monster)
            field.pack(side="left", fill="x", expand=True)
            field.set(req["card"])
            self._card_input("card", field, lambda cid: put(whole={"card": cid}))
            WrapLabel(body, style="Hint.TLabel", text="A copy of it counts too; the card itself is taken first.").pack(
                fill="x", pady=(6, 0))
            return
        grid = ttk.Frame(body)
        grid.pack(fill="x")
        row = 0
        for key, label in CONDITIONS:
            if key not in req:
                continue
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            if key == "type":
                value = tk.StringVar(value=req["type"])
                box = IconChoice(grid, self.app, value, TYPE_NAMES[:20],
                                 lambda label: TYPE_NAMES.index(label) if label in TYPE_NAMES else None, width=18)
                value.set(req["type"])      # its icon on the button
                value.trace_add("write", lambda *_, v=value: v.get() != req["type"] and
                                self.after_idle(lambda: put({"type": v.get()})))
            elif key == "fusion_group":
                value = tk.StringVar(value=req["fusion_group"])
                box = ttk.Combobox(grid, textvariable=value, values=FUSION_GROUPS, state="readonly", width=20)
                box.bind("<<ComboboxSelected>>", lambda e, v=value: put({"fusion_group": v.get()}))
            elif key in NUMBERS:
                value = tk.StringVar(value=str(req[key]))
                box = ttk.Spinbox(grid, textvariable=value, from_=0, to=NUMBERS[key],
                                  increment=100 if NUMBERS[key] > 12 else 1, width=8, command=self.read_later)
                self._inputs[key] = (value, NUMBERS[key], index)
                box.bind("<Return>", lambda e: self.read_inputs())
                box.bind("<FocusOut>", lambda e: self.read_inputs())
            elif key == "card":
                box = PickedCardField(grid, lambda: self.project, width=28, only=self.is_monster)
                box.set(req["card"])
                self._card_input("rule_card", box, lambda cid: put({"card": cid}))
            else:
                box = ttk.Label(grid, text="yes", style="Hint.TLabel")
            box.grid(row=row, column=1, sticky="w", pady=2)
            drop = ttk.Button(grid, text="×", width=2,
                              command=lambda k=key: put(drop=k))
            drop.grid(row=row, column=2, sticky="w", padx=(8, 0))
            if len(req) <= 1:
                drop.state(["disabled"])
            row += 1
        more = ttk.Menubutton(body, text="+ Add a condition")
        menu = tk.Menu(more, tearoff=False)
        for key, label in CONDITIONS:
            menu.add_command(label=label, state="disabled" if key in req else "normal",
                             command=lambda k=key: self.add_condition(index, k))
        more["menu"] = menu
        more.pack(anchor="w", pady=(6, 0))
        WrapLabel(body, style="Hint.TLabel",
                  text="All its conditions must hold. ATK, DEF and level are the card's printed ones; a minimum "
                       "ATK of 0 alone is any monster.").pack(fill="x", pady=(6, 0))

    def _card_input(self, name, field, apply):
        """A card typed or picked is applied once it names a monster: at
        Enter, on leaving the box, or as the picker closes."""
        def done(event=None):
            text = field.var.get().strip()
            cid = card_named(self.project, text)
            if not text or not cid:
                self.error.configure(text=f"No card \"{text}\"." if text else "Name a card.")
                return
            if not self.is_monster(cid):
                self.error.configure(text=f"{self.project.card_label(cid)} is not a monster.")
                return
            if field.var.get() != getattr(field, "applied", None):
                field.applied = self.project.card_label(cid)
                self.error.configure(text="")
                apply(cid)
        field.applied = field.var.get()
        field.entry.bind("<Return>", done)
        field.entry.bind("<FocusOut>", done)
        field.picked = done
        self._inputs[name] = field

    def add_condition(self, index, key):
        recipe = self.recipe()
        if not recipe:
            return
        self.read_inputs()
        tributes, result, origin, _ = recipe
        req = dict(tributes[index])
        if key == "card":
            cid = pick_card(self.winfo_toplevel(), self.project, "The tribute is this card", only=self.is_monster)
            if not cid:
                return
            req["card"] = cid
        elif key == "type":
            req["type"] = TYPE_NAMES[0]
        elif key == "fusion_group":
            req["fusion_group"] = "Elf"
        elif key in NUMBERS:
            req[key] = NUMBER_DEFAULTS[key]
        else:
            req["defense_gt_attack"] = True
        if req.get("min_attack") == 0 and len(req) > 1 and key != "min_attack":
            req.pop("min_attack")       # "any monster" gives way to a real condition
        changed = [dict(t) for t in tributes]
        changed[index] = req
        self.store(changed, result, origin)

    def switch_kind(self, index, kind):
        recipe = self.recipe()
        if not recipe:
            return
        tributes, result, origin, _ = recipe
        req = tributes[index]
        if kind == "card":
            if set(req) == {"card"}:
                return
            cid = req.get("card") or pick_card(self.winfo_toplevel(), self.project, f"Tribute {index + 1}",
                                               only=self.is_monster)
            if not cid:
                self.show()
                return
            new = {"card": cid}
        else:
            if set(req) != {"card"}:
                return
            card = self.project.cards.get(req["card"])
            # A card's own type to start from, for a rule like it.
            names = getattr(self.project, "type_names", TYPE_NAMES)
            if card is not None and card.is_monster():
                value = names[card.type] if 0 <= card.type < len(names) and names[card.type] else card.type
                new = {"type": value}
            else:
                new = {"min_attack": 0}
        changed = [dict(t) for t in tributes]
        changed[index] = new
        self.store(changed, result, origin)

    def read_inputs(self):
        """The typed numbers of the editor, applied when they are whole and
        in range; False (and the reason shown) when one is not."""
        recipe = self.recipe() if self.current is not None and self.project is not None else None
        numbers = {k: v for k, v in self._inputs.items() if isinstance(v, tuple)}
        if not recipe or not numbers:
            return True
        tributes, result, origin, _ = recipe
        index = next(iter(numbers.values()))[2]
        if index >= len(tributes):
            return True
        req = dict(tributes[index])
        for key, (value, limit, _) in numbers.items():
            try:
                number = int(value.get().strip())
            except ValueError:
                self.error.configure(text=f"Tribute {index + 1}: a whole number, 0 to {limit}.")
                return False
            if not 0 <= number <= limit:
                self.error.configure(text=f"Tribute {index + 1}: 0 to {limit}.")
                return False
            req[key] = number
        for low, high, what in (("min_attack", "max_attack", "ATK"), ("min_defense", "max_defense", "DEF"),
                                ("min_level", "max_level", "level")):
            if req.get(low) is not None and req.get(high) is not None and req[low] > req[high]:
                self.error.configure(text=f"Tribute {index + 1}: the least {what} is above the most.")
                return False
        if req != tributes[index]:
            changed = [dict(t) for t in tributes]
            changed[index] = req
            self.store(changed, result, origin, keep_editor=True)
        self.error.configure(text="")
        return True

    def read_later(self):
        """A spin box's arrows: applied once they pause, so the box is not
        drawn again under the pointer at every click."""
        if getattr(self, "_reading", None) is not None:
            self.after_cancel(self._reading)
        self._reading = self.after(600, self._read_now)

    def _read_now(self):
        self._reading = None
        self.read_inputs()

    def commit(self):
        if self.project is None or self.current is None:
            return True
        return self.read_inputs()

    # --- the head's buttons ----------------------------------------------

    def chosen(self):
        """The ritual card the list has selected, shown first when a
        selection made in code has not reached the tab yet."""
        self.select()
        return self.current

    def make_own(self):
        """A recipe for a card without one of its own: its base's (an added
        copy), else the game's, else three of any monster summoning a
        monster chosen now."""
        p = self.project
        ritual = self.chosen()
        if ritual is None:
            return
        found = p.ritual_recipe(ritual) or (
            None if ritual not in p.retail.rituals else
            ([{"card": c} for c in p.retail.rituals[ritual][:-1]], p.retail.rituals[ritual][-1], "field"))
        if found is None:
            result = pick_card(self.winfo_toplevel(), p, "What it summons", only=self.is_monster)
            if not result:
                return
            found = ([{"min_attack": 0}] * 3, result, "field")
        self.picked = 0
        self.store([dict(t) for t in found[0]], found[1], found[2])

    def remove(self):
        ritual = self.chosen()
        if ritual is not None:
            self.project.remove_ritual(ritual)
            self.app.changed()
            self.fill()

    def revert(self):
        ritual = self.chosen()
        if ritual is not None:
            self.project.revert_ritual(ritual)
            self.app.changed()
            self.fill()
