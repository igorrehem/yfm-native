"""The Packs tab: card packs the mod sells on the Password screen ("packs"
and "pack_shop", notes/card-packs.md).

A simple view (name, description, price, cards a pack, the picture on the big
card, and the cards with their tier, weight and chance) and an "Advanced"
part, closed at first, for everything else a pack may say. "Shop settings..."
edits "pack_shop"; "Simulate..." opens packs with the game's own dealer
(packs.py) and shows what came out.

Each pack is kept as the object the mod writes, so what the editor has no
field for stays as written; what the tab stores into it is written back with
the defaults left out (packs.minimize)."""
from __future__ import annotations

import copy
import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import art, duelist_rules, file_dialogs, packs as packmath, pngio, roster, validate
from .bulk_dialog import FilterPanel
from .gamedata import DUELIST_NAMES
from .tabs import Tab
from .widgets import CardField, FormDialog, WrapLabel, pick_card, px, scrolled_tree, show_text, ui_font

ZOOMS = (1, 2, 4)
LISTED = ("(default)", "yes", "no")
SHOPS_RULE = "(shop's)"                  # "when_nothing_left" left to "pack_shop"
SIMULATE_MAX = 1000000                   # packs Simulate opens at most
SIMULATE_CARDS = 5000000                 # ...and cards in all: about a minute of dealing
SIMULATE_SLICE = 0.05                    # seconds of dealing between two looks at the window
_FONT = {}


def photo(master, image: pngio.Image, zoom: int = 1):
    return tk.PhotoImage(master=master, data=pngio.ppm(pngio.scale_nearest(image, zoom)), format="PPM")


def pairs_text(value) -> str:
    """{name: n} as "name=n, name=n" for a one-line field."""
    return ", ".join(f"{k}={v}" for k, v in value.items()) if isinstance(value, dict) else ""


def parse_pairs(text: str, what: str) -> dict:
    """"name=n, ..." back; ValueError saying what is wrong."""
    out = {}
    for part in [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]:
        if "=" not in part:
            raise ValueError(f"{what}: \"{part}\" is not name=number")
        name, n = [x.strip() for x in part.rsplit("=", 1)]
        if not name or not n.lstrip("-").isdigit():
            raise ValueError(f"{what}: \"{part}\" is not name=number")
        out[name] = int(n)
    return out


def whole(text: str, what: str, low: int, high: int, blank=None):
    text = text.strip()
    if not text:
        return blank
    if not text.lstrip("-").isdigit() or not low <= int(text) <= high:
        raise ValueError(f"{what} is a whole number, {low} to {high}")
    return int(text)


def plate_inks(name: str):
    """The game's plate for a name, or None without a serif face."""
    if "font" not in _FONT:
        from . import ttf
        path = packmath.serif_path()
        try:
            _FONT["font"] = ttf.Font(path) if path else None
        except ttf.FontError:
            _FONT["font"] = None
    if _FONT["font"] is None:
        return None
    return packmath.name_plate_inks(name, _FONT["font"])


def card_picture(art_image: pngio.Image, inks, zoom: int) -> pngio.Image:
    """The picture over the card's gold and the name plate under it, as the
    big card shows them, `zoom` times (a picture bigger than the console's
    keeps its own detail at 2x and 4x, as the game's HD path draws it)."""
    w, h = 102 * zoom, (96 + 2 + 14) * zoom
    out = bytearray(bytes(art.GOLD) + b"\xff") * (w * h)
    if art_image is not None:
        picture = pngio.resample(art_image, 102 * zoom, 96 * zoom, pngio.middle(art_image, 102, 96))
        for y in range(picture.height):
            start = (y * w) * 4
            out[start:start + picture.width * 4] = picture.rgba[y * picture.width * 4:(y + 1) * picture.width * 4]
    if inks is not None:
        plate = pngio.scale_nearest(art.plate_image(inks, background=art.GOLD), zoom)
        top, left = 98 * zoom, 3 * zoom
        for y in range(plate.height):
            start = ((top + y) * w + left) * 4
            out[start:start + plate.width * 4] = plate.rgba[y * plate.width * 4:(y + 1) * plate.width * 4]
    return pngio.Image(w, h, bytes(out))


def full_picture(image: pngio.Image, zoom: int) -> pngio.Image:
    """"image_style": "full": the picture fitted inside the card's 140x196,
    its shape kept and centred, as the big card shows it (pack_shop.c), over
    the Password screen's black, `zoom` times. At 1x as the console's
    texture has it (art.c CardArt_IndexedImage): a texel under half opaque
    is clear, the rest opaque; at 2x and 4x with the PNG's own alpha, as
    the game draws the PNG itself there."""
    w, h = packmath.fit_full(image.width, image.height)
    picture = pngio.resample(image, w * zoom, h * zoom)
    width, height = packmath.CARD_VIEW[0] * zoom, packmath.CARD_VIEW[1] * zoom
    out = bytearray(b"\x00\x00\x00\xff") * (width * height)
    left, top = (packmath.CARD_VIEW[0] - w) // 2 * zoom, (packmath.CARD_VIEW[1] - h) // 2 * zoom
    for y in range(picture.height):
        row = picture.rgba[y * picture.width * 4:(y + 1) * picture.width * 4]
        start = ((top + y) * width + left) * 4
        for x in range(picture.width):   # its clear parts show the black, as the game's do
            r, g, b, a = row[x * 4:x * 4 + 4]
            if zoom == 1:
                if a * 2 >= 255:
                    out[start + x * 4:start + x * 4 + 4] = bytes((r, g, b, 255))
            elif a:
                out[start + x * 4:start + x * 4 + 4] = bytes((r * a // 255, g * a // 255, b * a // 255, 255))
    return pngio.Image(width, height, bytes(out))


class PacksTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Packs")
        self.index = 0
        self.photos = {}
        self.filling = False
        self.cover = 0
        self.baseline = {}
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        frame, self.list = scrolled_tree(left, [("n", "#"), ("name", "Pack"), ("price", "Price"), ("cards", "Cards"),
                                                ("stock", "Stock")], [30, 150, 50, 45, 50], 22)
        frame.pack(fill="y", expand=True)
        self.list.bind("<<TreeviewSelect>>", lambda e: self.select())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(4, 0))
        for text, command in (("Add pack", self.add_pack), ("Duplicate", self.duplicate), ("Remove", self.remove),
                              ("Up", lambda: self.move(-1)), ("Down", lambda: self.move(1))):
            button = ttk.Button(buttons, text=text, command=command, width=len(text) + 1)
            button.pack(side="left", padx=(0, 2))
            if command == self.add_pack:
                self.add_button = button
        more = ttk.Frame(left)
        more.pack(fill="x", pady=(4, 0))
        self.shop_button = ttk.Button(more, text="Shop settings...", command=self.shop_settings)
        self.shop_button.pack(side="left")
        ttk.Button(more, text="Simulate...", command=self.simulate).pack(side="left", padx=4)
        self.list_buttons = left
        self.file_note = ttk.Label(left, style="Hint.TLabel", wraplength=px(self, 330), justify="left")
        self.file_note.pack(anchor="w", pady=(4, 0))

        self.right = right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        top = ttk.Frame(right)
        top.pack(fill="x")
        form = ttk.Frame(top)
        form.pack(side="left", fill="x", expand=True)
        self.vars = {k: tk.StringVar() for k in ("name", "description", "price", "count", "image_style")}
        ttk.Label(form, text="Name").grid(row=0, column=0, sticky="w", pady=1)
        named = ttk.Frame(form)
        named.grid(row=0, column=1, sticky="w", pady=1)
        ttk.Entry(named, textvariable=self.vars["name"], width=26).pack(side="left")
        # The shop shows NAME_LETTERS letters of a name: the count as it is typed.
        self.name_count = ttk.Label(named, style="Hint.TLabel", width=6)
        self.name_count.pack(side="left", padx=(4, 0))
        self.vars["name"].trace_add("write", lambda *_: self.count_name())
        self.identity = ttk.Label(form, style="Hint.TLabel")
        self.identity.grid(row=0, column=2, sticky="w", padx=6)
        ttk.Label(form, text="Description").grid(row=1, column=0, sticky="w", pady=1)
        ttk.Entry(form, textvariable=self.vars["description"], width=52).grid(row=1, column=1, columnspan=2,
                                                                             sticky="we", pady=1)
        ttk.Label(form, text="Price").grid(row=2, column=0, sticky="w", pady=1)
        line = ttk.Frame(form)
        line.grid(row=2, column=1, columnspan=2, sticky="w", pady=1)
        ttk.Spinbox(line, textvariable=self.vars["price"], from_=0, to=packmath.PRICE_MAX, width=8).pack(side="left")
        ttk.Label(line, text="starchips      Cards a pack").pack(side="left", padx=4)
        ttk.Spinbox(line, textvariable=self.vars["count"], from_=1, to=packmath.COUNT_MAX, width=4).pack(side="left")
        ttk.Button(line, text="Apply", command=self.apply).pack(side="left", padx=(10, 0))
        self.problem = ttk.Label(form, style="Error.TLabel", wraplength=px(self, 460), justify="left")
        self.problem.grid(row=3, column=0, columnspan=3, sticky="w")
        form.columnconfigure(2, weight=1)
        picture = ttk.Frame(top)
        picture.pack(side="right")
        self.picture = ttk.Label(picture)
        self.picture.pack()
        line = ttk.Frame(picture)
        line.pack()
        self.zoom = tk.IntVar(value=1)
        for z in ZOOMS:
            ttk.Radiobutton(line, text=f"{z}x", value=z, variable=self.zoom, command=self.show_picture).pack(side="left")
        line = ttk.Frame(picture)
        line.pack()
        ttk.Button(line, text="Import PNG...", command=self.import_png).pack(side="left")
        self.export_button = ttk.Button(line, text="Export...", command=self.export_png)
        self.export_button.pack(side="left", padx=2)
        self.revert_button = ttk.Button(line, text="Revert", command=self.revert_png)
        self.revert_button.pack(side="left")
        line = ttk.Frame(picture)
        line.pack()
        ttk.Label(line, text="Shown as").pack(side="left")
        style = ttk.Combobox(line, textvariable=self.vars["image_style"], values=packmath.IMAGE_STYLES,
                             state="readonly", width=6)
        style.pack(side="left", padx=4)
        style.bind("<<ComboboxSelected>>", lambda e: self.show_picture())
        # Under the list, not beside it: beside, it made the tab wider than a 1280 window.
        ttk.Label(picture, text="card: in the card's frame; full: the whole picture", style="Hint.TLabel",
                  wraplength=px(self, 240), justify="left").pack()
        self.picture_note = ttk.Label(picture, style="Hint.TLabel", wraplength=px(self, 240), justify="left")
        self.picture_note.pack()

        # Advanced goes in before the cards, from the bottom, so the tree is
        # what gives way when the window is short.
        self.advanced_open = tk.BooleanVar(value=False)
        bottom = ttk.Frame(right)
        bottom.pack(side="bottom", fill="x")
        # As Guardian Stars has it: a box, not a button.
        self.advanced_shown = tk.BooleanVar(self, value=False)
        self.advanced_button = ttk.Checkbutton(bottom, text="Show advanced", variable=self.advanced_shown,
                                               command=self.show_advanced)
        self.advanced_button.pack(anchor="w", pady=(4, 0))
        self.advanced = ttk.LabelFrame(bottom, text="Advanced", padding=4)
        self.build_advanced(self.advanced)

        edit = ttk.Frame(right)
        edit.pack(side="bottom", fill="x")
        ttk.Button(edit, text="Add a card...", command=self.add_card).pack(side="left")
        ttk.Button(edit, text="Add filtered...", command=self.add_filtered).pack(side="left", padx=2)
        ttk.Label(edit, text="Tier").pack(side="left", padx=(8, 2))
        self.tier = ttk.Combobox(edit, width=10, state="readonly")
        self.tier.pack(side="left")
        ttk.Button(edit, text="Set", command=self.set_tier, width=4).pack(side="left", padx=2)
        ttk.Label(edit, text="Weight").pack(side="left", padx=(8, 2))
        self.weight = tk.StringVar(value="1")
        entry = ttk.Entry(edit, textvariable=self.weight, width=7)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.set_weight())
        ttk.Button(edit, text="Set", command=self.set_weight, width=4).pack(side="left", padx=2)
        ttk.Button(edit, text="Remove selected", command=self.remove_cards).pack(side="left", padx=(8, 0))
        frame, self.tree = scrolled_tree(right, [("id", "#"), ("name", "Card"), ("tier", "Tier"), ("weight", "Weight"),
                                                 ("chance", "Chance")], [50, 240, 90, 60, 80], 12,
                                         selectmode="extended")
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        self.tree.bind("<Delete>", lambda e: self.remove_cards())
        # No pack: what packs are, and ways to start one.
        self.empty = ttk.Frame(frame, padding=20)
        WrapLabel(self.empty, 420, font=ui_font(10),
                  text="This mod sells no card packs. A pack is bought in the shop for starchips and deals its "
                       "cards by their weights (in tiers, slots and guarantees under Advanced).").pack(fill="x")
        ttk.Button(self.empty, text="Empty pack", command=self.add_pack).pack(anchor="w", pady=(8, 0))
        ttk.Button(self.empty, text="A pack of an opponent's drops...", command=self.add_from_drops).pack(
            anchor="w", pady=(6, 0))

    # --- the advanced part ------------------------------------------------------

    def build_advanced(self, box):
        book = ttk.Notebook(box)
        book.pack(fill="both", expand=True)
        self.adv = {}
        v = self.adv

        page = ttk.Frame(book, padding=4)
        book.add(page, text="Tiers")
        frame, self.tiers = scrolled_tree(page, [("name", "Tier"), ("odds", "Odds"), ("share", "Share"),
                                                 ("label", "Label"), ("color", "Color"), ("sound", "Sound"),
                                                 ("reveal", "Reveal"), ("cards", "Cards")],
                                          [80, 60, 60, 110, 45, 50, 55, 45], 5)
        frame.pack(fill="both", expand=True)
        self.tiers.bind("<Double-1>", lambda e: self.edit_tier())
        line = ttk.Frame(page)
        line.pack(fill="x", pady=(2, 0))
        for text, command in (("Add tier", self.add_tier), ("Edit...", self.edit_tier), ("Remove", self.remove_tier),
                              ("Up", lambda: self.move_tier(-1)), ("Down", lambda: self.move_tier(1))):
            ttk.Button(line, text=text, command=command).pack(side="left", padx=(0, 2))
        ttk.Label(line, text="written in order of rarity, commonest first", style="Hint.TLabel").pack(side="left", padx=6)

        page = ttk.Frame(book, padding=4)
        book.add(page, text="Slots")
        v["use_slots"] = tk.BooleanVar()
        ttk.Checkbutton(page, text="A rule for each slot (else every slot is dealt by the tiers' odds)",
                        variable=v["use_slots"], command=self.toggle_slots).pack(anchor="w")
        frame, self.slots = scrolled_tree(page, [("n", "#"), ("rule", "Rule")], [30, 420], 5)
        frame.pack(fill="both", expand=True)
        self.slots.bind("<Double-1>", lambda e: self.edit_slot())
        line = ttk.Frame(page)
        line.pack(fill="x", pady=(2, 0))
        for text, command in (("Add slot", self.add_slot), ("Edit...", self.edit_slot), ("Remove", self.remove_slot),
                              ("Up", lambda: self.move_slot(-1)), ("Down", lambda: self.move_slot(1))):
            ttk.Button(line, text=text, command=command).pack(side="left", padx=(0, 2))

        page = ttk.Frame(book, padding=4)
        book.add(page, text="Dealing")
        rows = (("guarantee", "Guarantee", "tier=n: at least n of that tier or rarer in every pack"),
                ("pity", "Pity", "tier=n: the n-th pack in a row without it has one"),
                ("max_copies", "Max copies", "not dealt once the player holds this many (chest and deck)"),
                ("stock", "Stock", "purchases a save may make; empty for no limit"),
                ("cost_cards", "Cost in cards", "card=copies taken from the chest: names or numbers"),
                ("order", "Order", "place in the list; empty for as declared"),
                ("shop", "Shops", "shop ids, comma between; empty for every shop"),
                ("cover", "Cover", "the card whose art stands in without a picture"))
        for r, (key, label, hint) in enumerate(rows):
            v[key] = tk.StringVar()
            ttk.Label(page, text=label).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Entry(page, textvariable=v[key], width=28).grid(row=r, column=1, sticky="w", pady=1)
            ttk.Label(page, text=hint, style="Hint.TLabel").grid(row=r, column=2, sticky="w", padx=6)
        r = len(rows)
        v["duplicates"] = tk.StringVar()
        ttk.Label(page, text="Duplicates").grid(row=r, column=0, sticky="w")
        ttk.Combobox(page, textvariable=v["duplicates"], values=("allow", "unique_in_pack"), state="readonly",
                     width=16).grid(row=r, column=1, sticky="w")
        v["reveal"] = tk.StringVar()
        ttk.Label(page, text="Reveal").grid(row=r + 1, column=0, sticky="w")
        ttk.Combobox(page, textvariable=v["reveal"], values=packmath.REVEALS, state="readonly",
                     width=16).grid(row=r + 1, column=1, sticky="w")
        v["include_added"] = tk.BooleanVar()
        ttk.Checkbutton(page, text="Include cards mods add", variable=v["include_added"]).grid(row=r + 2, column=1,
                                                                                               sticky="w")
        v["when_nothing_left"] = tk.StringVar()
        ttk.Label(page, text="All owned").grid(row=r + 3, column=0, sticky="w")
        ttk.Combobox(page, textvariable=v["when_nothing_left"], values=(SHOPS_RULE,) + packmath.NOTHING_LEFT,
                     state="readonly", width=16).grid(row=r + 3, column=1, sticky="w")
        ttk.Label(page, text="with Max copies, when the player holds that many of every card: refuse (BUY is\n"
                             "refused, ALL OWNED) or sell anyway (empty slots); (shop's): Shop settings' rule",
                  style="Hint.TLabel").grid(row=r + 3, column=2, sticky="w", padx=6)

        page = ttk.Frame(book, padding=4)
        book.add(page, text="Unlock")
        v["beat"] = tk.StringVar()
        ttk.Label(page, text="Beat").grid(row=0, column=0, sticky="w")
        # The disc's and the mod's own, as the game finds them (Duelists_Named),
        # listed afresh as it opens: the roster changes on another tab.
        self.beat_box = ttk.Combobox(page, textvariable=v["beat"], values=[""] + DUELIST_NAMES[1:], width=24,
                                     postcommand=self.beat_choices)
        self.beat_box.grid(row=0, column=1, sticky="w")
        for r, (key, label, hint) in enumerate((("wins", "Wins", "against Beat, or in all without it"),
                                                ("story", "Story flag", "a campaign story flag: 0x6E0 + n is the n-th "
                                                                        "duelist beaten in the campaign"),
                                                ("copies", "Copies", "of the card below (1 by default)"),
                                                ("starchips_spent", "Starchips spent", "on packs, by this save"),
                                                ("packs_opened", "Packs opened", "in all, by this save"),
                                                ("opened", "Opened", "pack=n: that pack opened n times")), start=1):
            v[key] = tk.StringVar()
            ttk.Label(page, text=label).grid(row=r, column=0, sticky="w", pady=1)
            if key == "story":
                ttk.Spinbox(page, textvariable=v[key], from_=0, to=0xFFFF, width=8).grid(row=r, column=1, sticky="w")
            else:
                ttk.Entry(page, textvariable=v[key], width=26).grid(row=r, column=1, sticky="w", pady=1)
            ttk.Label(page, text=hint, style="Hint.TLabel").grid(row=r, column=2, sticky="w", padx=6)
        ttk.Label(page, text="Card").grid(row=7, column=0, sticky="w")
        self.unlock_card = CardField(page, lambda: self.project, width=24)
        self.unlock_card.grid(row=7, column=1, sticky="w")
        v["locked"] = tk.StringVar()
        ttk.Label(page, text="While locked").grid(row=8, column=0, sticky="w")
        ttk.Combobox(page, textvariable=v["locked"], values=("hidden", "shown"), state="readonly",
                     width=10).grid(row=8, column=1, sticky="w")

        page = ttk.Frame(book, padding=4)
        book.add(page, text="Password and sounds")
        v["password"] = tk.StringVar()
        ttk.Label(page, text="Password").grid(row=0, column=0, sticky="w")
        ttk.Entry(page, textvariable=v["password"], width=10).grid(row=0, column=1, sticky="w")
        self.password_note = ttk.Label(page, style="Hint.TLabel")
        self.password_note.grid(row=0, column=2, columnspan=4, sticky="w", padx=6)
        v["once"] = tk.BooleanVar()
        ttk.Checkbutton(page, text="Once a save", variable=v["once"]).grid(row=1, column=1, sticky="w")
        v["listed"] = tk.StringVar()
        ttk.Label(page, text="In the list").grid(row=2, column=0, sticky="w")
        ttk.Combobox(page, textvariable=v["listed"], values=LISTED, state="readonly", width=10).grid(row=2, column=1,
                                                                                                 sticky="w")
        ttk.Label(page, text="Sound ids (empty: the Password screen's)").grid(row=3, column=0, columnspan=3,
                                                                              sticky="w", pady=(6, 0))
        for i, key in enumerate(packmath.SOUND_KEYS):
            v["sound_" + key] = tk.StringVar()
            ttk.Label(page, text=f"{key} ({packmath.DEFAULT_SOUNDS[key]})").grid(row=4 + i // 3, column=(i % 3) * 2,
                                                                                sticky="w")
            ttk.Entry(page, textvariable=v["sound_" + key], width=7).grid(row=4 + i // 3, column=(i % 3) * 2 + 1,
                                                                          sticky="w", padx=(2, 10))
        line = ttk.Frame(box)
        line.pack(fill="x")
        ttk.Button(line, text="Apply", command=self.apply).pack(side="left", pady=(4, 0))
        ttk.Label(line, text="Unknown keys of a pack stay as written.", style="Hint.TLabel").pack(side="left", padx=8)

    def toggle_advanced(self):
        self.advanced_shown.set(not self.advanced_shown.get())
        self.show_advanced()

    def show_advanced(self):
        if self.advanced_shown.get():
            self.advanced.pack(fill="x")
        else:
            self.advanced.pack_forget()

    # --- the list -------------------------------------------------------------

    def entries(self):
        return self.project.packs if self.project else []

    def current(self):
        entries = self.entries()
        return entries[self.index] if 0 <= self.index < len(entries) and isinstance(entries[self.index], dict) else None

    def parsed(self, entry=None):
        """(Pack or None, notes) of the current pack, as the game reads it."""
        entry = self.current() if entry is None else entry
        if entry is None or self.project is None:
            return None, []
        return packmath.read_pack(entry, validate.pack_resolver(self.project), self.project.info.id, self.index)

    def refresh(self):
        self.fill_list()
        self.fill()

    def beat_choices(self):
        if self.project is not None:
            self.beat_box.configure(values=[""] + duelist_rules.references(self.project))

    def fill_list(self):
        if self.project is None:
            return
        self.list.delete(*self.list.get_children())
        resolve = validate.pack_resolver(self.project)
        taken = set()
        for i, entry in enumerate(self.entries()):
            pack, notes = packmath.read_pack(entry, resolve, self.project.info.id, i, taken)
            if pack:
                taken.add(pack.id)
            name = entry.get("name", packmath.pack_id(entry)) if isinstance(entry, dict) else "?"
            tags = ("error",) if pack is None else ("warning",) if notes else ()
            self.list.insert("", "end", iid=str(i), tags=tags, values=(
                i + 1, name, pack.price if pack else "", pack.count if pack else "",
                (pack.stock if pack.stock >= 0 else "") if pack else ""))
        if self.entries():
            self.index = min(self.index, len(self.entries()) - 1)
            if self.list.exists(str(self.index)):
                self.list.selection_set(str(self.index))
        in_file = self.project.packs_file is not None
        self.file_note.configure(text=f"\"packs\" names the file {self.project.packs_file}: the editor keeps it as "
                                      "written and does not edit it." if in_file else "")
        self.set_editable(not in_file)
        for button in self.empty.winfo_children():     # the empty tab's ways to start a pack
            if isinstance(button, ttk.Button):
                button.state(["disabled"] if in_file else ["!disabled"])

    # What does nothing while "packs" names a file: every field and button of
    # a pack, and the list's own but Shop settings ("pack_shop" stays the
    # manifest's).
    EDITABLE = (ttk.Button, ttk.Entry, ttk.Spinbox, ttk.Combobox, ttk.Checkbutton, ttk.Radiobutton)

    def set_editable(self, editable: bool, keep=()):
        """Every control greyed, or back; `keep`: those left as they are."""
        def walk(widget):
            for child in widget.winfo_children():
                if child is self.empty:
                    continue
                if isinstance(child, self.EDITABLE) and child not in keep:
                    if not editable:
                        child.state(["disabled"])
                    elif child not in (self.export_button, self.revert_button):   # show_picture's to set
                        child.state(["!disabled"])
                walk(child)
        keep = {self.shop_button, *keep}
        walk(self.right)
        walk(self.list_buttons)

    def select(self):
        selection = self.list.selection()
        if selection and int(selection[0]) != self.index:
            if not self.commit():
                self.list.selection_set(str(self.index))
                return
            self.index = int(selection[0])
            self.fill()

    def fill(self):
        if self.project is None or self.filling:
            return
        self.filling = True
        try:
            self._fill()
        finally:
            self.filling = False
            # What the form says of the pack as written: a field still saying
            # it keeps the pack's value as the mod wrote it (store).
            self.baseline = self.form_state()

    def form_state(self) -> dict:
        state = {key: var.get() for key, var in self.vars.items()}
        state.update({key: var.get() for key, var in self.adv.items() if key != "use_slots"})
        state["unlock_card"] = self.unlock_card.var.get()
        return state

    def _fill(self):
        entry = self.current()
        self.problem.configure(text="")
        self.tree.delete(*self.tree.get_children())
        for tree in (self.tiers, self.slots):
            tree.delete(*tree.get_children())
        if entry is None:
            for var in self.vars.values():
                var.set("")
            self.identity.configure(text="No pack: Add pack makes one")
            self.picture.configure(image="")
            self.picture_note.configure(text="")
            if self.project.packs_file is None:
                self.empty.place(relx=0.5, rely=0.4, anchor="center", relwidth=0.7)
                # No pack: nothing but Add pack does anything.
                self.set_editable(False, keep={self.add_button})
            else:
                self.empty.place_forget()       # the packs are in a file: there are some
            return
        if self.empty.winfo_manager():
            self.empty.place_forget()
            if self.project.packs_file is None:
                self.set_editable(True)
        pack, notes = self.parsed(entry)
        pid = packmath.pack_id(entry)
        self.identity.configure(text=f"{self.project.info.id}:{pid}")
        self.vars["name"].set(entry.get("name", "") if isinstance(entry.get("name"), str) else "")
        self.vars["description"].set(entry.get("description", "") if isinstance(entry.get("description"), str) else "")
        price = entry.get("price", packmath.DEFAULT_PRICE)
        if isinstance(entry.get("cost"), dict) and "starchips" in entry["cost"]:
            price = entry["cost"]["starchips"]
        self.vars["price"].set(str(price))
        self.vars["count"].set(str(entry.get("count", packmath.default_count(entry))))
        style = entry.get("image_style", "card")
        self.vars["image_style"].set(style if style in packmath.IMAGE_STYLES else "card")
        errors = [m for level, m in notes if level == "error"]
        self.problem.configure(style="Error.TLabel")
        if errors:
            empty = not any(packmath.tier_pool(entry, name) for name, _ in packmath.tiers_of(entry))
            if empty and "none of its cards are here" in errors[0]:
                # A pack just made: not a mistake, a next step.
                self.problem.configure(text="Add cards: a pack with none is not sold.", style="Hint.TLabel")
            else:
                self.problem.configure(text=errors[0])
        chances = packmath.card_chances(pack) if pack else {}
        resolve = validate.pack_resolver(self.project)
        names = []
        for t, (tname, tier) in enumerate(packmath.tiers_of(entry)):
            names.append(tname)
            for k, (ref, weight) in enumerate(packmath.pool_items(tier.get("cards", []))):
                cid = resolve(ref)
                card = self.project.cards.get(cid) if cid > 0 else None
                chance = chances.get((t, cid)) if pack and cid > 0 else None
                self.tree.insert("", "end", iid=f"{t}:{k}", tags=() if card else ("removed",), values=(
                    cid if card else "", card.name if card else f"{ref} (no such card)", tname, weight,
                    f"{chance * 100:.2f}%" if chance else ""))
        self.tier.configure(values=names)
        if self.tier.get() not in names:
            self.tier.set(names[0] if names else "")
        # Advanced.
        total = sum(t.odds for t in pack.tiers) if pack else 0
        for t, (tname, tier) in enumerate(packmath.tiers_of(entry)):
            odds = tier.get("odds", 1)
            self.tiers.insert("", "end", iid=str(t), values=(
                tname, odds, f"{odds / total * 100:.1f}%" if total and isinstance(odds, int) else "",
                tier.get("label", ""), tier.get("color", ""), tier.get("sound", ""), tier.get("reveal", ""),
                len(packmath.pool_items(tier.get("cards", [])))))
        slots = entry.get("slots")
        self.adv["use_slots"].set(isinstance(slots, list))
        for s, rule in enumerate(slots if isinstance(slots, list) else []):
            self.slots.insert("", "end", iid=str(s), values=(s + 1, json.dumps(rule, ensure_ascii=False)))
        v = self.adv
        v["guarantee"].set(pairs_text(entry.get("guarantee")))
        v["pity"].set(pairs_text(entry.get("pity")))
        v["max_copies"].set(str(entry.get("max_copies", "")))
        v["stock"].set(str(entry.get("stock", "")))
        cost = entry.get("cost") if isinstance(entry.get("cost"), dict) else {}
        v["cost_cards"].set(pairs_text(cost.get("cards")))
        v["order"].set(str(entry.get("order", "")))
        shop = entry.get("shop")
        v["shop"].set(", ".join(shop) if isinstance(shop, list) else shop if isinstance(shop, str) else "")
        v["cover"].set(str(entry.get("cover", "")))
        v["duplicates"].set(entry.get("duplicates", "allow"))
        v["reveal"].set(entry.get("reveal", "flip"))
        v["include_added"].set(packmath.json_bool(entry.get("include_added_cards"), True))
        rule = entry.get("when_nothing_left", SHOPS_RULE)
        v["when_nothing_left"].set(rule if isinstance(rule, str) else json.dumps(rule))
        unlock = entry.get("unlock") if isinstance(entry.get("unlock"), dict) else {}
        v["beat"].set(str(unlock.get("beat", "")))
        for key in ("wins", "story", "copies", "starchips_spent", "packs_opened"):
            v[key].set(str(unlock.get(key, "")))
        v["opened"].set(pairs_text(unlock.get("opened")))
        card = resolve(unlock["card"]) if "card" in unlock else 0
        self.unlock_card.set(card if card > 0 else 0)
        if "card" in unlock and card <= 0:
            self.unlock_card.var.set(str(unlock["card"]))
        v["locked"].set(entry.get("locked", "hidden"))
        password = packmath.password_bits(entry.get("password")) if "password" in entry else None
        v["password"].set(f"{password:08X}" if password is not None else str(entry.get("password", "")))
        v["once"].set(packmath.json_bool(entry.get("once"), False))
        listed = entry.get("listed")
        v["listed"].set(LISTED[0] if listed is None else LISTED[1] if listed else LISTED[2])
        sounds = entry.get("sounds") if isinstance(entry.get("sounds"), dict) else {}
        for key in packmath.SOUND_KEYS:
            v["sound_" + key].set(str(sounds.get(key, "")))
        self.password_note.configure(text=self.password_clash(password))
        self.cover = pack.cover if pack else 0
        self.show_picture()

    def password_clash(self, password) -> str:
        if password is None:
            return "A pack with a password is sold by it, and is not in the list unless it says."
        for cid in sorted(self.project.cards):
            text = self.project.password(cid)
            if text and text.isdigit() and int(text, 16) == password:
                return f"{self.project.card_label(cid)} has this password: the card comes first."
        return "Typed on the Password screen, it sells this pack."

    # --- storing the form ---------------------------------------------------------

    def commit(self):
        if self.project is None or self.current() is None or self.filling:
            return True
        if self.project.packs_file is not None:
            return True                  # the file's packs are kept as written
        try:
            self.store(self.current())
        except ValueError as problem:
            self.problem.configure(text=str(problem))
            return False
        return True

    def apply(self):
        if self.commit():
            self.edited()

    def store(self, entry):
        """The form into the pack; ValueError (and nothing stored) when a field
        is not what the game reads. A field that still says what the form
        showed of the pack leaves its key as the mod wrote it (`"cover": 2`
        stays a number, a value the form cannot show stays), so opening a mod
        and moving between packs changes nothing of it."""
        now = self.form_state()
        base = self.baseline
        if now == base:
            self.applied()
            return
        new = copy.deepcopy(entry)
        v = self.adv

        def changed(*keys):
            return any(now.get(key) != base.get(key) for key in keys)

        def put(key, value, container=new):
            if value in (None, "", {}, []):
                container.pop(key, None)
            else:
                container[key] = value

        if changed("name"):
            name = self.vars["name"].get().strip()
            if not name:
                raise ValueError("a pack has a name")
            old_id = packmath.pack_id(entry)
            new["name"] = name
            if "id" not in entry and packmath.slug(name) != old_id:
                new["id"] = old_id           # its identity stays: a save's progress is kept by it
        if changed("description"):
            put("description", self.vars["description"].get().strip())
        if changed("price"):
            price = whole(self.vars["price"].get(), "Price", 0, packmath.PRICE_MAX, packmath.DEFAULT_PRICE)
            if isinstance(new.get("cost"), dict) and "starchips" in new["cost"]:
                new["cost"]["starchips"] = price
            else:
                new["price"] = price
        if changed("image_style"):
            new["image_style"] = self.vars["image_style"].get() or "card"
        if changed("count"):
            new["count"] = whole(self.vars["count"].get(), "Cards a pack", 1, packmath.COUNT_MAX,
                                 packmath.default_count(new))
        if changed("guarantee"):
            put("guarantee", parse_pairs(v["guarantee"].get(), "Guarantee"))
        if changed("pity"):
            put("pity", parse_pairs(v["pity"].get(), "Pity"))
        if changed("max_copies"):
            put("max_copies", whole(v["max_copies"].get(), "Max copies", 1, 250))
        if changed("stock"):
            put("stock", whole(v["stock"].get(), "Stock", 1, 999999))
        if changed("order"):
            put("order", whole(v["order"].get(), "Order", -1000000, 1000000))
        if changed("cost_cards"):
            cost = new.get("cost") if isinstance(new.get("cost"), dict) else {}
            put("cards", parse_pairs(v["cost_cards"].get(), "Cost in cards"), cost)
            put("cost", cost)
        if changed("shop"):
            shops = [s.strip() for s in v["shop"].get().split(",") if s.strip()]
            put("shop", shops[0] if len(shops) == 1 and isinstance(entry.get("shop"), str) else shops)
        if changed("cover"):
            cover = v["cover"].get().strip()
            if cover:
                cid = self.project.resolve(cover) or (int(cover.split(" ", 1)[0]) if cover.split(" ", 1)[0].isdigit()
                                                      else 0)
                put("cover", self.project.ref(cid) if cid in self.project.cards else cover)
            else:
                new.pop("cover", None)
        if changed("duplicates"):
            new["duplicates"] = v["duplicates"].get() or "allow"
        if changed("reveal"):
            new["reveal"] = v["reveal"].get() or "flip"
        if changed("include_added"):
            new["include_added_cards"] = bool(v["include_added"].get())
        if changed("when_nothing_left"):
            rule = v["when_nothing_left"].get()
            put("when_nothing_left", rule if rule in packmath.NOTHING_LEFT else None)
        unlock_keys = ("beat", "wins", "story", "copies", "starchips_spent", "packs_opened", "opened", "unlock_card")
        if changed(*unlock_keys):
            unlock = copy.deepcopy(entry.get("unlock")) if isinstance(entry.get("unlock"), dict) else {}

            def as_written(key, text, container):
                """The text, or the value as the mod wrote it when it reads the same."""
                if key in container and str(container[key]) == text:
                    return container[key]
                return text

            if changed("beat"):
                put("beat", as_written("beat", v["beat"].get().strip(), unlock), unlock)
            for key, low, high in (("wins", 0, 65535), ("story", 0, 0xFFFF), ("copies", 0, 250),
                                   ("starchips_spent", 0, 999999999), ("packs_opened", 0, 999999999)):
                if not changed(key):
                    continue
                text = v[key].get().strip()
                number = int(text, 16) if text.lower().startswith("0x") and key == "story" else None
                put(key, number if number is not None else whole(text, key.replace("_", " ").capitalize(), low, high),
                    unlock)
            if changed("opened"):
                put("opened", parse_pairs(v["opened"].get(), "Opened"), unlock)
            if changed("unlock_card"):
                card = self.unlock_card.get()
                typed = self.unlock_card.var.get().strip()
                if card and "card" in unlock and self.project.resolve(unlock["card"]) == card:
                    put("card", unlock["card"], unlock)
                else:
                    put("card", self.project.ref(card) if card else typed, unlock)
            put("unlock", unlock)
        if changed("locked"):
            new["locked"] = v["locked"].get() or "hidden"
        if changed("password"):
            password = v["password"].get().strip()
            if password and (not password.isdigit() or len(password) > 8):
                raise ValueError("a password is up to 8 digits")
            if password and "password" in entry and packmath.password_bits(entry["password"]) == int(password.zfill(8),
                                                                                                    16):
                put("password", entry["password"])
            else:
                put("password", password.zfill(8) if password else "")
        if changed("once"):
            new["once"] = bool(v["once"].get())
        if changed("listed"):
            listed = v["listed"].get()
            if listed == LISTED[0]:
                new.pop("listed", None)
            else:
                new["listed"] = listed == LISTED[1]
        sound_keys = ["sound_" + key for key in packmath.SOUND_KEYS]
        if changed(*sound_keys):
            sounds = copy.deepcopy(entry.get("sounds")) if isinstance(entry.get("sounds"), dict) else {}
            for key in packmath.SOUND_KEYS:
                if changed("sound_" + key):
                    put(key, whole(v["sound_" + key].get(), f"Sound {key}", 0, 0xFFFF), sounds)
            put("sounds", sounds)
        # Stored only when it says something else.
        if packmath.minimize(new) != packmath.minimize(entry):
            entry.clear()
            entry.update(packmath.minimize(new))
            self.app.changed()
        self.baseline = now
        self.applied()

    def count_name(self):
        n = len(self.vars["name"].get())
        self.name_count.configure(text=f"{n}/{packmath.NAME_LETTERS}" if n else "",
                                  style="Error.TLabel" if n > packmath.NAME_LETTERS else "Hint.TLabel")

    def edited(self):
        self.app.changed()
        self.fill_list()
        self.fill()

    # --- packs ------------------------------------------------------------------

    def ids(self):
        return {packmath.pack_id(e) for e in self.entries()}

    def add_pack(self):
        if self.project is None or self.project.packs_file is not None or not self.commit():
            return
        name = f"Pack {len(self.entries()) + 1}"
        self.project.packs.append(packmath.new_pack(name, self.ids()))
        self.index = len(self.entries()) - 1
        self.edited()

    def add_from_drops(self):
        """A pack of the cards an opponent drops, at their drop weights: the
        start of a "Seto's rare cards" pack."""
        if self.project is None or self.project.packs_file is not None or not self.commit():
            return None
        who = dict(roster.opponents(self.project))      # the disc's and the mod's own
        names = list(who)
        pools = {"S/A-POW drops": "pow", "B/C/D drops": "bcd", "S/A-TEC drops": "tec", "Deck": "deck"}
        fields = {}

        def build(dialog, body):
            for row, (key, label, values) in enumerate((("who", "Opponent", names), ("pool", "Pool", list(pools)))):
                ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
                fields[key] = tk.StringVar(value=values[0])
                ttk.Combobox(body, textvariable=fields[key], values=values, state="readonly", width=30).grid(
                    row=row, column=1, sticky="w", padx=(6, 0), pady=2)
            ttk.Label(body, text="Each card at its weight in that pool: the pack deals them as the duel drops them.",
                      style="Hint.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok(dialog):
            d = who[fields["who"].get()]
            pool = pools[fields["pool"].get()]
            items = [(self.project.ref(c), w) for c, w in sorted(roster.pools_of(self.project, d)[pool].items())
                     if w > 0]
            if not items:
                return "that pool has no card"
            name = f"{roster.shown_name(self.project, d)} {pool.upper()}"[:packmath.NAME_LETTERS]
            entry = packmath.new_pack(name, self.ids())
            packmath.set_tier_pool(entry, "cards", items)
            self.project.packs.append(entry)
            self.index = len(self.entries()) - 1
            self.edited()
            return None

        return FormDialog(self, "A pack of an opponent's drops", build, ok)

    def duplicate(self):
        entry = self.current()
        if entry is None or not self.commit():
            return
        copied = copy.deepcopy(entry)
        name = f"{entry.get('name', packmath.pack_id(entry))} copy"[:packmath.NAME_LETTERS]
        copied["name"] = name
        pid, n, taken = packmath.slug(name), 2, self.ids()
        base = pid
        while pid in taken:
            pid, n = f"{base}-{n}", n + 1
        copied.pop("id", None)
        if pid != packmath.slug(name):
            copied = {"id": pid, **copied}
        # A picture of its own, so importing one for either pack, or taking
        # one's away, leaves the other's as it is.
        blob = self.image_bytes(entry)
        if blob is not None:
            picture = self.free_image_name(pid)
            self.project.files[picture] = blob
            copied["image"] = picture
        self.project.packs.insert(self.index + 1, copied)
        self.index += 1
        self.edited()

    def remove(self):
        entry = self.current()
        if entry is None:
            return
        if not messagebox.askyesno("Remove pack", f"Remove {entry.get('name', packmath.pack_id(entry))}?", parent=self):
            return
        image = entry.get("image")
        self.project.packs.pop(self.index)
        if isinstance(image, str) and not self.image_shared(image, entry):
            self.project.files.pop(image, None)     # else saved as a file nothing names
        self.index = max(0, self.index - 1)
        self.edited()

    def move(self, step):
        entries = self.entries()
        other = self.index + step
        if self.current() is None or not 0 <= other < len(entries) or not self.commit():
            return
        entries[self.index], entries[other] = entries[other], entries[self.index]
        self.index = other
        self.edited()

    def goto(self, target):
        self.index = target if isinstance(target, int) else 0
        self.fill_list()
        if self.list.exists(str(self.index)):
            self.list.see(str(self.index))
        self.fill()

    # --- cards ------------------------------------------------------------------

    def rows(self):
        return [tuple(int(x) for x in iid.split(":")) for iid in self.tree.selection()]

    def pick_row(self):
        entry = self.current()
        rows = self.rows()
        if entry is None or len(rows) != 1:
            return
        t, k = rows[0]
        tiers = packmath.tiers_of(entry)
        if t < len(tiers):
            items = packmath.pool_items(tiers[t][1].get("cards", []))
            if k < len(items):
                self.weight.set(str(items[k][1]))
                self.tier.set(tiers[t][0])

    def add_cards(self, cids):
        entry = self.current()
        if entry is None or not cids:
            return
        tier = self.tier.get() or packmath.tiers_of(entry)[0][0]
        try:
            weight = whole(self.weight.get(), "Weight", 1, packmath.WEIGHT_TOTAL_MAX, 1)
        except ValueError:
            weight = 1
        items = packmath.tier_pool(entry, tier)
        present = {self.project.resolve(ref): i for i, (ref, _) in enumerate(items)}
        for cid in cids:
            if cid in present:
                items[present[cid]] = (items[present[cid]][0], weight)
            else:
                items.append((self.project.ref(cid), weight))
        packmath.set_tier_pool(entry, tier, items)
        self.edited()

    def add_card(self):
        if self.current() is None or not self.commit():
            if self.current() is None:
                messagebox.showinfo("Packs", "Add a pack first.", parent=self)
            return
        cid = pick_card(self, self.project, "Card to add to the pack")
        if cid:
            self.add_cards([cid])

    def add_filtered(self):
        if self.current() is None or not self.commit():
            return
        dialog = tk.Toplevel(self)
        dialog.title("Add filtered cards")
        dialog.transient(self)
        chosen = {"cards": []}

        def changed():
            try:
                cards, _ = panel.read().select(self.project)
            except ValueError as problem:
                panel.count.configure(text=str(problem))
                return
            chosen["cards"] = cards
            panel.show_count(self.project, cards)

        panel = FilterPanel(dialog, "Cards to add", changed)
        panel.pack(fill="both", expand=True, padx=8, pady=8)
        changed()

        def ok():
            dialog.destroy()
            self.add_cards(chosen["cards"])

        line = ttk.Frame(dialog)
        line.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(line, text="Add", command=ok).pack(side="right")
        ttk.Button(line, text="Cancel", command=dialog.destroy).pack(side="right", padx=4)
        dialog.grab_set()

    def change_rows(self, change):
        entry = self.current()
        if entry is None or not self.commit():
            return
        tiers = packmath.tiers_of(entry)
        pools = {name: packmath.pool_items(tier.get("cards", [])) for name, tier in tiers}
        chosen = {}
        for t, k in self.rows():
            if t < len(tiers):
                chosen.setdefault(tiers[t][0], set()).add(k)
        change(pools, chosen)
        for name, items in pools.items():
            packmath.set_tier_pool(entry, name, items)
        self.edited()

    def set_weight(self):
        try:
            weight = whole(self.weight.get(), "Weight", 0, packmath.WEIGHT_TOTAL_MAX)
        except ValueError as problem:
            messagebox.showerror("Weight", str(problem), parent=self)
            return
        if weight is None:
            return

        def change(pools, chosen):
            for name, rows in chosen.items():
                pools[name] = [(ref, weight if k in rows else w) for k, (ref, w) in enumerate(pools[name])]
        self.change_rows(change)

    def set_tier(self):
        target = self.tier.get()

        def change(pools, chosen):
            moving = []
            for name, rows in chosen.items():
                if name == target:
                    continue
                moving += [item for k, item in enumerate(pools[name]) if k in rows]
                pools[name] = [item for k, item in enumerate(pools[name]) if k not in rows]
            pools.setdefault(target, [])
            pools[target] += moving
        if target:
            self.change_rows(change)

    def remove_cards(self):
        def change(pools, chosen):
            for name, rows in chosen.items():
                pools[name] = [item for k, item in enumerate(pools[name]) if k not in rows]
        self.change_rows(change)

    # --- tiers ------------------------------------------------------------------

    def tier_dialog(self, title, name, tier, on_ok):
        fields = {}

        def build(dialog, body):
            rows = (("name", "Name", name), ("odds", "Odds", tier.get("odds", 1)), ("label", "Label", tier.get("label", "")),
                    ("color", "Color", tier.get("color", "")), ("sound", "Sound", tier.get("sound", "")))
            for r, (key, label, value) in enumerate(rows):
                ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=2)
                fields[key] = tk.StringVar(value=str(value))
                ttk.Entry(body, textvariable=fields[key], width=24).grid(row=r, column=1, sticky="w", pady=2)
            fields["reveal"] = tk.StringVar(value=tier.get("reveal", ""))
            ttk.Label(body, text="Reveal").grid(row=5, column=0, sticky="w")
            ttk.Combobox(body, textvariable=fields["reveal"], values=("",) + packmath.REVEALS, state="readonly",
                         width=10).grid(row=5, column=1, sticky="w")
            ttk.Label(body, text="Odds: its weight when a slot deals by the tiers' odds (0: only slots and guarantees\n"
                                 "reach it). Label: what a card of it says when it turns over (\"ULTRA RARE!\").\n"
                                 "Color: the game's text color, 0-15. Sound: a sound effect id of the game's.",
                      style="Hint.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok(dialog):
            new_name = fields["name"].get().strip()
            if not packmath.KEY_RE.match(new_name):
                return "a tier's name is 1-63 letters, digits, '_' or '-'"
            try:
                odds = whole(fields["odds"].get(), "Odds", 0, packmath.WEIGHT_TOTAL_MAX, 1)
                color = whole(fields["color"].get(), "Color", 0, 15)
                sound = whole(fields["sound"].get(), "Sound", 0, 0xFFFF)
            except ValueError as problem:
                return str(problem)
            values = {"odds": odds, "label": fields["label"].get().strip(), "color": color, "sound": sound,
                      "reveal": fields["reveal"].get()}
            return on_ok(new_name, values)

        FormDialog(self, title, build, ok)

    def write_tier(self, tier: dict, values: dict):
        for key, value in values.items():
            if value in (None, "") or (key == "odds" and value == 1):
                tier.pop(key, None)
            else:
                tier[key] = value

    def add_tier(self):
        entry = self.current()
        if entry is None or not self.commit():
            return

        def done(name, values):
            if name in dict(packmath.tiers_of(entry)):
                return f"the pack has a tier \"{name}\""
            packmath.ensure_tiers(entry)
            tier = {"cards": []}
            self.write_tier(tier, values)
            entry["tiers"][name] = tier
            self.edited()
            return None

        self.tier_dialog("Add tier", "rare", {}, done)

    def selected_tier(self):
        selection = self.tiers.selection()
        return int(selection[0]) if selection else None

    def edit_tier(self):
        entry, t = self.current(), self.selected_tier()
        if entry is None or t is None or not self.commit():
            return
        name, tier = packmath.tiers_of(entry)[t]

        def done(new_name, values):
            if new_name != name and new_name in dict(packmath.tiers_of(entry)):
                return f"the pack has a tier \"{new_name}\""
            packmath.ensure_tiers(entry)
            body = entry["tiers"][name]
            self.write_tier(body, values)
            if new_name != name:
                entry["tiers"] = {new_name if k == name else k: v for k, v in entry["tiers"].items()}
                self.rename_tier(entry, name, new_name)
            self.edited()
            return None

        self.tier_dialog("Tier", name, tier, done)

    @staticmethod
    def rename_tier(entry, old, new):
        """A tier renamed: the slots, guarantee and pity that name it too."""
        for key in ("guarantee", "pity"):
            if isinstance(entry.get(key), dict) and old in entry[key]:
                entry[key] = {new if k == old else k: v for k, v in entry[key].items()}
        for s, slot in enumerate(entry.get("slots") or []):
            if slot == old:
                entry["slots"][s] = new
            elif isinstance(slot, dict) and isinstance(slot.get("tiers"), dict) and old in slot["tiers"]:
                slot["tiers"] = {new if k == old else k: v for k, v in slot["tiers"].items()}

    def remove_tier(self):
        entry, t = self.current(), self.selected_tier()
        if entry is None or t is None or not isinstance(entry.get("tiers"), dict):
            return
        tiers = packmath.tiers_of(entry)
        name = tiers[t][0]
        if len(tiers) < 2:
            messagebox.showinfo("Remove tier", "A pack deals from one tier at least: add another before "
                                "removing this one.", parent=self)
            return
        if not self.commit() or not messagebox.askyesno("Remove tier", f"Remove the tier {name} and its cards?",
                                                        parent=self):
            return
        del entry["tiers"][name]
        self.forget_tier(entry, name, packmath.tiers_of(entry)[0][0])
        self.edited()

    @staticmethod
    def forget_tier(entry, gone, first):
        """A tier removed: the guarantee and pity name it no more, and a slot
        that dealt from it alone deals from the first tier left."""
        for key in ("guarantee", "pity"):
            if isinstance(entry.get(key), dict):
                entry[key].pop(gone, None)
                if not entry[key]:
                    del entry[key]
        for s, slot in enumerate(entry.get("slots") or []):
            if slot == gone:
                entry["slots"][s] = first
            elif isinstance(slot, dict) and isinstance(slot.get("tiers"), dict):
                slot["tiers"].pop(gone, None)
                weights = [w for w in slot["tiers"].values() if isinstance(w, (int, float))]
                if not slot["tiers"] or not sum(weights):       # nothing it could deal any more
                    entry["slots"][s] = first

    def move_tier(self, step):
        entry, t = self.current(), self.selected_tier()
        if entry is None or t is None or not isinstance(entry.get("tiers"), dict):
            return
        items = list(entry["tiers"].items())
        other = t + step
        if not 0 <= other < len(items) or not self.commit():
            return
        items[t], items[other] = items[other], items[t]
        entry["tiers"] = dict(items)
        self.edited()
        self.tiers.selection_set(str(other))

    # --- slots ------------------------------------------------------------------

    def toggle_slots(self):
        entry = self.current()
        if entry is None:
            return
        if not self.commit():           # the count typed, not the one stored
            self.adv["use_slots"].set(not self.adv["use_slots"].get())
            return
        if self.adv["use_slots"].get():
            first = packmath.tiers_of(entry)[0][0]
            count = entry.get("count", packmath.DEFAULT_COUNT)
            entry["slots"] = [first] * (count if isinstance(count, int) and count > 0 else packmath.DEFAULT_COUNT)
            entry.pop("count", None)
        else:
            slots = entry.pop("slots", None)
            if isinstance(slots, list) and len(slots) != packmath.DEFAULT_COUNT:
                entry["count"] = len(slots)
        self.edited()

    def slot_dialog(self, title, rule, on_ok):
        entry = self.current()
        fields = {}
        tiers = [name for name, _ in packmath.tiers_of(entry)]

        def build(dialog, body):
            fields["kind"] = tk.StringVar()
            kind = ("card" if isinstance(rule, dict) and "card" in rule else "pool" if isinstance(rule, dict) and
                    "cards" in rule else "mix" if isinstance(rule, dict) else "tier")
            fields["kind"].set(kind)
            fields["tier"] = tk.StringVar(value=rule if isinstance(rule, str) else tiers[0])
            fields["mix"] = tk.StringVar(value=pairs_text(rule.get("tiers")) if kind == "mix" else "")
            pool = packmath.pool_items(rule.get("cards")) if kind == "pool" else []
            fields["pool"] = tk.StringVar(value=", ".join(f"{r}={w}" for r, w in pool))
            ttk.Radiobutton(body, text="A tier", value="tier", variable=fields["kind"]).grid(row=0, column=0, sticky="w")
            ttk.Combobox(body, textvariable=fields["tier"], values=tiers, state="readonly", width=14).grid(
                row=0, column=1, sticky="w")
            ttk.Radiobutton(body, text="Tiers by weight", value="mix", variable=fields["kind"]).grid(row=1, column=0,
                                                                                                   sticky="w")
            ttk.Entry(body, textvariable=fields["mix"], width=34).grid(row=1, column=1, sticky="w")
            ttk.Radiobutton(body, text="Its own cards", value="pool", variable=fields["kind"]).grid(row=2, column=0,
                                                                                                   sticky="w")
            ttk.Entry(body, textvariable=fields["pool"], width=34).grid(row=2, column=1, sticky="w")
            ttk.Radiobutton(body, text="Always a card", value="card", variable=fields["kind"]).grid(row=3, column=0,
                                                                                                   sticky="w")
            fields["card"] = CardField(body, lambda: self.project, width=28)
            fields["card"].grid(row=3, column=1, sticky="w")
            if kind == "card":
                cid = self.project.resolve(rule["card"])
                if cid:
                    fields["card"].set(cid)
                else:
                    fields["card"].var.set(str(rule["card"]))
            ttk.Label(body, text="Tiers by weight: tier=weight, comma between. Its own cards: card=weight\n"
                                 "(names or numbers). A slot of its own cards or a fixed card is never dealt\n"
                                 "again for a guarantee or the pity.", style="Hint.TLabel").grid(
                row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok(dialog):
            kind = fields["kind"].get()
            try:
                if kind == "tier":
                    value = fields["tier"].get()
                elif kind == "mix":
                    value = {"tiers": parse_pairs(fields["mix"].get(), "Tiers by weight")}
                elif kind == "pool":
                    items = []
                    for ref, w in parse_pairs(fields["pool"].get(), "Its own cards").items():
                        cid = self.project.resolve(ref)
                        items.append((self.project.ref(cid) if cid else ref, w))
                    value = {"cards": packmath.pool_value(items)}
                else:
                    cid = fields["card"].get()
                    if not cid:
                        return "choose the card"
                    value = {"card": self.project.ref(cid)}
            except ValueError as problem:
                return str(problem)
            on_ok(value)
            return None

        FormDialog(self, title, build, ok)

    def selected_slot(self):
        selection = self.slots.selection()
        return int(selection[0]) if selection else None

    def add_slot(self):
        entry = self.current()
        if entry is None or not self.commit():
            return

        def done(value):
            if not isinstance(entry.get("slots"), list):
                entry["slots"] = []
            entry["slots"].append(value)
            entry.pop("count", None)
            self.edited()
        self.slot_dialog("Add slot", packmath.tiers_of(entry)[0][0], done)

    def edit_slot(self):
        entry, s = self.current(), self.selected_slot()
        if entry is None or s is None or not isinstance(entry.get("slots"), list) or not self.commit():
            return

        def done(value):
            entry["slots"][s] = value
            self.edited()
        self.slot_dialog("Slot", entry["slots"][s], done)

    def remove_slot(self):
        entry, s = self.current(), self.selected_slot()
        if entry is None or s is None or not isinstance(entry.get("slots"), list) or not self.commit():
            return
        entry["slots"].pop(s)
        if not entry["slots"]:
            del entry["slots"]
        entry.pop("count", None)
        self.edited()

    def move_slot(self, step):
        entry, s = self.current(), self.selected_slot()
        if entry is None or s is None or not isinstance(entry.get("slots"), list):
            return
        other = s + step
        if 0 <= other < len(entry["slots"]) and self.commit():
            entry["slots"][s], entry["slots"][other] = entry["slots"][other], entry["slots"][s]
            self.edited()
            self.slots.selection_set(str(other))

    # --- the picture ---------------------------------------------------------------

    @property
    def wa(self):
        files = self.app.files
        return files.wa if files is not None else None

    def image_bytes(self, entry):
        image = entry.get("image") if entry else None
        if not isinstance(image, str) or not image:
            return None
        if image in self.project.files:
            return self.project.files[image]
        if self.project.source_dir:
            path = Path(self.project.source_dir) / image
            if path.is_file():
                return path.read_bytes()
        return None

    def show_picture(self):
        entry = self.current()
        self.photos = {}
        if entry is None:
            self.picture.configure(image="")
            return
        zoom = self.zoom.get()
        art_image, note = None, ""
        blob = self.image_bytes(entry)
        own = blob is not None
        full = self.vars["image_style"].get() == "full"
        if own:
            try:
                art_image = pngio.decode(blob)
                if full:
                    note = (f"The pack's whole picture, {art_image.width}x{art_image.height}, where the card is drawn: "
                            "fitted inside the card's 140x196 at 1x, its shape kept, a pixel under half opaque "
                            "clear; Internal 2x and 4x draw the PNG itself, with its own transparency.")
                else:
                    note = (f"The pack's picture, {art_image.width}x{art_image.height}: made into the console's "
                            "102x96 at 1x; Internal 2x and 4x draw it at its own size.")
            except pngio.PngError as problem:
                note = f"{entry.get('image')}: {problem}"
        elif isinstance(entry.get("image"), str):
            note = f"{entry['image']} is not in the mod folder: the game shows the cover."
        if art_image is None and self.cover and self.wa is not None:
            try:
                art_image = art.in_game(self.project, self.wa, self.cover, "art", 1)
                note = note or (f"No picture of its own: the cover, {self.project.card_label(self.cover)}, stands in. "
                                "Import a PNG for the pack's own.")
            except (OSError, ValueError, pngio.PngError):
                art_image = None
        inks = plate_inks(self.vars["name"].get().strip() or entry.get("name", ""))
        if inks is None:
            note += " (No Times font here to preview the name plate the game sets.)"
        try:
            if full and own and art_image is not None:
                self.photos["card"] = photo(self, full_picture(art_image, zoom))
            else:
                self.photos["card"] = photo(self, card_picture(art_image, inks, zoom if own or zoom == 1 else 1),
                                            1 if own or zoom == 1 else zoom)
            self.picture.configure(image=self.photos["card"])
        except (ValueError, pngio.PngError):
            self.picture.configure(image="")
        self.picture_note.configure(text=note)
        self.export_button.state(["!disabled"] if own else ["disabled"])
        self.revert_button.state(["!disabled"] if isinstance(entry.get("image"), str) else ["disabled"])

    def import_png(self):
        entry = self.current()
        if entry is None or not self.commit():
            return
        path = file_dialogs.askopenfilename(parent=self, title="Picture for the pack",
                                            filetypes=[("PNG", "*.png"), ("All files", "*")])
        if path:
            self.use_file(path)

    def use_file(self, path):
        entry = self.current()
        try:
            image, notes = art.normalize(pngio.read(path), "art")
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Picture", f"{Path(path).name}: {problem}", parent=self)
            return
        old = entry.get("image")
        name = old if isinstance(old, str) and old in self.project.files and not self.image_shared(old, entry) \
            else self.free_image_name(packmath.pack_id(entry), entry)
        if isinstance(old, str) and old != name and not self.image_shared(old, entry):
            self.project.files.pop(old, None)
        self.project.files[name] = pngio.encode(image)
        entry["image"] = name
        self.app.say(f"Pack picture from {Path(path).name}" + (": " + "; ".join(notes) if notes else ""))
        self.edited()

    def export_png(self):
        entry = self.current()
        blob = self.image_bytes(entry)
        if blob is None:
            return
        path = file_dialogs.asksaveasfilename(parent=self, title="Export the pack's picture", defaultextension=".png",
                                              initialfile=f"{packmath.pack_id(entry)}.png", filetypes=[("PNG", "*.png")])
        if path:
            Path(path).write_bytes(blob)

    def revert_png(self):
        entry = self.current()
        if entry is None or not isinstance(entry.get("image"), str) or not self.commit():
            return
        image = entry.pop("image")
        if not self.image_shared(image, entry):
            self.project.files.pop(image, None)
        self.edited()

    def image_shared(self, image, entry) -> bool:
        """Whether a pack other than `entry` names this picture too."""
        return any(isinstance(other, dict) and other is not entry and other.get("image") == image
                   for other in self.entries())

    def free_image_name(self, pid, entry=None) -> str:
        """packs/<id>.png, or -2, -3... when another pack names that already."""
        name, n = f"packs/{pid}.png", 2
        while self.image_shared(name, entry):
            name, n = f"packs/{pid}-{n}.png", n + 1
        return name

    # --- the shop and Simulate ---------------------------------------------------------

    def shop_settings(self):
        if self.project is None or not self.commit():
            return
        rules = copy.deepcopy(self.project.pack_shop) if isinstance(self.project.pack_shop, dict) else {}
        fields = {}

        shown = {}

        def build(dialog, body):
            fields["password"] = tk.StringVar(value=str(rules.get("password", "both")))
            fields["rng"] = tk.StringVar(value=str(rules.get("rng", "game")))
            fields["music"] = tk.StringVar(value=str(rules.get("music", packmath.DEFAULT_MUSIC)))
            fields["when_nothing_left"] = tk.StringVar(value=str(rules.get("when_nothing_left", "refuse")))
            ttk.Label(body, text="All owned").grid(row=8, column=0, sticky="w", pady=2)
            ttk.Combobox(body, textvariable=fields["when_nothing_left"], values=packmath.NOTHING_LEFT,
                         state="readonly", width=14).grid(row=8, column=1, sticky="w")
            ttk.Label(body, text="for a pack of Max copies that says nothing: refuse it (ALL OWNED) or sell it with "
                                 "empty slots\nwhen the player holds that many of every card",
                      style="Hint.TLabel").grid(row=9, column=0, columnspan=2, sticky="w")
            ttk.Label(body, text="Password screen").grid(row=0, column=0, sticky="w", pady=2)
            ttk.Combobox(body, textvariable=fields["password"], values=packmath.SHOP_PASSWORD, state="readonly",
                         width=14).grid(row=0, column=1, sticky="w")
            ttk.Label(body, text="both: passwords and packs (triangle); packs_only: the screen opens on the packs;\n"
                                 "password_only: no triangle (a pack's own password still sells it)",
                      style="Hint.TLabel").grid(row=1, column=0, columnspan=2, sticky="w")
            ttk.Label(body, text="Random numbers").grid(row=2, column=0, sticky="w", pady=2)
            ttk.Combobox(body, textvariable=fields["rng"], values=("game", "save"), state="readonly", width=14).grid(
                row=2, column=1, sticky="w")
            ttk.Label(body, text="save: a pack dealt from the save, so reloading it deals the same cards",
                      style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")
            ttk.Label(body, text="Music").grid(row=4, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=fields["music"], width=8).grid(row=4, column=1, sticky="w")
            ttk.Label(body, text="Shops: one a line, id | name | unlock as JSON (optional)").grid(
                row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
            fields["shops"] = tk.Text(body, width=64, height=6)
            fields["shops"].grid(row=6, column=0, columnspan=2, sticky="we")
            for shop in rules.get("shops", []) if isinstance(rules.get("shops"), list) else []:
                if isinstance(shop, dict):
                    line = f"{shop.get('id', '')} | {shop.get('name', '')}"
                    if "unlock" in shop:
                        line += " | " + json.dumps(shop["unlock"], ensure_ascii=False)
                    fields["shops"].insert("end", line + "\n")
            ttk.Label(body, text="Needs a restart of the game. Not yet in the game (the keys are kept for them): "
                                 + ", ".join(packmath.NOT_YET) + ". A shop's other keys (\"where\" and any the "
                                 "editor has no field for) stay as written.", style="Hint.TLabel",
                      wraplength=px(self, 460), justify="left").grid(row=7, column=0, columnspan=2, sticky="w",
                                                                     pady=(6, 0))
            shown.update({key: var.get() for key, var in fields.items() if key != "shops"})
            shown["shops"] = fields["shops"].get("1.0", "end")

        def ok(dialog):
            new = dict(rules)
            # A field still showing what was written leaves the key as it was.
            for key in ("password", "rng", "when_nothing_left"):
                if fields[key].get() != shown[key]:
                    new[key] = fields[key].get()
            if fields["music"].get() != shown["music"]:
                try:
                    new["music"] = whole(fields["music"].get(), "Music", 0, 0xFFFF, packmath.DEFAULT_MUSIC)
                except ValueError as problem:
                    return str(problem)
            if fields["shops"].get("1.0", "end") != shown["shops"]:
                written = {}
                for shop in rules.get("shops") if isinstance(rules.get("shops"), list) else []:
                    if isinstance(shop, dict) and isinstance(shop.get("id"), str):
                        written.setdefault(shop["id"], shop)
                shops = []
                for n, line in enumerate(fields["shops"].get("1.0", "end").splitlines(), start=1):
                    if not line.strip():
                        continue
                    parts = [p.strip() for p in line.split("|", 2)]
                    if not packmath.KEY_RE.match(parts[0]):
                        return f"shop line {n}: an id is 1-63 letters, digits, '_' or '-'"
                    # The shop as written, its "where" and unknown keys kept.
                    shop = copy.deepcopy(written.get(parts[0], {}))
                    shop["id"] = parts[0]
                    if len(parts) > 1 and parts[1]:
                        shop["name"] = parts[1]
                    else:
                        shop.pop("name", None)          # the game names it by its id
                    if len(parts) > 2 and parts[2]:
                        try:
                            shop["unlock"] = json.loads(parts[2])
                        except json.JSONDecodeError as problem:
                            return f"shop line {n}: the unlock is not JSON ({problem.msg})"
                    else:
                        shop.pop("unlock", None)
                    shops.append({"id": shop.pop("id"), **shop})
                if len({shop["id"] for shop in shops}) > packmath.SHOPS_MAX:
                    return f"at most {packmath.SHOPS_MAX} shops"
                new["shops"] = shops
            self.project.pack_shop = packmath.minimize_rules(new)
            self.edited()
            return None

        FormDialog(self, "Shop settings", build, ok)

    def simulate(self):
        entry = self.current()
        if entry is None or not self.commit():
            return
        pack, notes = self.parsed(entry)
        if pack is None:
            messagebox.showerror("Simulate", "The game leaves this pack out: " +
                                 "; ".join(m for level, m in notes if level == "error"), parent=self)
            return
        SimulateDialog(self, pack)


class SimulateDialog(tk.Toplevel):
    """Open N packs with the game's dealer (packs.py) and show what came.
    The packs are opened a slice at a time between the window's own work, so
    a million of them neither freezes the editor nor has to be waited out:
    Stop shows what came so far."""

    def __init__(self, tab, pack):
        super().__init__(tab)
        self.tab, self.pack = tab, pack
        self.simulator, self.total, self.job, self.result = None, 0, None, None
        self.title(f"Simulate {pack.name}")
        self.transient(tab)
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.count = tk.StringVar(value="1000")
        self.seed = tk.StringVar(value="1")
        ttk.Label(top, text="Packs").pack(side="left")
        ttk.Entry(top, textvariable=self.count, width=8).pack(side="left", padx=4)
        ttk.Label(top, text="Seed").pack(side="left", padx=(8, 0))
        ttk.Entry(top, textvariable=self.seed, width=12).pack(side="left", padx=4)
        self.open_button = ttk.Button(top, text="Open them", command=self.run)
        self.open_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(top, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.progress = ttk.Progressbar(top, length=px(self, 140), maximum=1.0)
        self.progress.pack(side="left", padx=8)
        self.summary = ttk.Label(self, padding=(8, 0), wraplength=px(self, 620), justify="left")
        self.summary.pack(fill="x")
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        frame, self.tiers = scrolled_tree(body, [("tier", "Tier"), ("n", "Cards"), ("share", "Share")], [90, 70, 70], 8)
        frame.pack(side="left", fill="y")
        frame, self.cards = scrolled_tree(body, [("id", "#"), ("name", "Card"), ("n", "Copies"), ("per", "Per pack")],
                                          [50, 240, 70, 80], 16)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ttk.Label(self, text="The game's own dealer and generator (Psy-Q rand from the seed, four numbers a card), "
                             f"the pity counted from one pack to the next as a save counts it, up to "
                             f"{max(1, min(SIMULATE_MAX, SIMULATE_CARDS // pack.count))} packs of this one. Cards the player holds are taken as none.", style="Hint.TLabel",
                  wraplength=px(self, 620), justify="left", padding=8).pack(fill="x")
        self.bind("<Destroy>", lambda e: self.cancel() if e.widget is self else None)
        self.run()

    @property
    def running(self) -> bool:
        return self.simulator is not None

    def run(self):
        try:
            most = max(1, min(SIMULATE_MAX, SIMULATE_CARDS // self.pack.count))
            count = whole(self.count.get(), "Packs", 1, most, 1000)
            seed = whole(self.seed.get(), "Seed", 0, 0xFFFFFFFF, 1)
        except ValueError as problem:
            self.summary.configure(text=str(problem))
            return
        self.cancel()
        self.simulator, self.total = packmath.Simulator(self.pack, seed), count
        self.open_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.job = self.after(0, self.work)

    def work(self):
        """Open packs for a slice of time, then give the window its turn."""
        self.job = None
        simulator = self.simulator
        if simulator is None:
            return
        batch = max(1, 400 // max(1, self.pack.count))
        start = time.monotonic()
        while simulator.opened < self.total and time.monotonic() - start < SIMULATE_SLICE:
            simulator.step(min(batch, self.total - simulator.opened))
        self.progress["value"] = simulator.opened / self.total
        if simulator.opened >= self.total:
            self.finish()
            return
        self.summary.configure(text=f"Opening... {simulator.opened} of {self.total} packs.")
        self.job = self.after(1, self.work)

    def stop(self):
        if self.simulator is not None:
            self.finish(stopped=True)

    def cancel(self):
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        self.simulator = None

    def finish(self, stopped=False):
        simulator = self.simulator
        self.cancel()
        self.open_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        if simulator is None or not simulator.opened:
            self.summary.configure(text="Stopped before a pack was opened.")
            return
        result = simulator.result()
        self.result = result
        count = result.packs
        dealt = sum(result.tiers.values()) or 1
        self.tiers.delete(*self.tiers.get_children())
        for name, n in sorted(result.tiers.items(), key=lambda kv: -kv[1]):
            self.tiers.insert("", "end", values=(name, n, f"{n / dealt * 100:.2f}%"))
        self.cards.delete(*self.cards.get_children())
        project = self.tab.project
        for cid, n in sorted(result.cards.items(), key=lambda kv: -kv[1]):
            card = project.cards.get(cid)
            self.cards.insert("", "end", values=(cid, card.name if card else "?", n, f"{n / count:.3f}"))
        parts = [f"Stopped after {count} of {self.total} packs:" if stopped else f"{count} packs,",
                 f"{dealt} cards, {result.draws} random numbers ({result.draws // count} a pack)."]
        for name, average in result.pity_waits.items():
            parts.append(f"{name}: one every {average:.1f} packs on average; the pity dealt it "
                         f"{result.pity_fired.get(name, 0)} times.")
        self.summary.configure(text=" ".join(parts))
