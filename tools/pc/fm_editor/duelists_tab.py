"""The Duelists tab: every opponent of the Free Duel grid, the disc's and the
mod's own (roster.py), with its face, its name, its place on the grid and
its deck and drop pools.

The list down the left is the grid's pages: page 1 is the disc's Deck Build
and thirty-nine, a page past it the duelists the mod adds, forty a page, a
small portrait beside each name. The right-hand side shows the one chosen:
its picture and the two the game draws of it (the 64-color 48x48 at
Internal 1x, the picture itself at 2x and above), where it sits on its page
(a map of the page, as the game lays it out), and its pools.
"""
from __future__ import annotations

import copy as _copy
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import duelist_rules, file_dialogs, fixed_decks, pngio, pools as poolmath, portrait, roster
from .fixed_deck_view import FixedDeckView
from .gamedata import (AI_FIELD_LABELS, AI_FIELDS, AI_SEARCH, DUELIST_COUNT, DUELIST_NAMES, POOL_LABELS, POOL_TOTAL,
                       POOLS, RANK_ABOVE, RANK_RETAIL, RANK_RULES, RANK_STEPS, SIGHT_DUELISTS, STORY_FREE_DUEL)
from .tabs import Tab, pool_summary, type_label
from .widgets import FormDialog, WrapLabel, pick_card, px, scrolled_tree, ui_font

FACE_ROW = 32          # the list's faces, square
FACE_BIG = 96          # the header's two in-game pictures
PICTURE = 104          # the whole PNG, the square the game takes marked on it
MAP_CELL = 20          # a face on the page map
MAP_GAP = 3
STAGE = "#1b2130"      # behind the pictures: the dark the game draws them over
EMPTY = "#2b3345"      # a cell of the page map no duelist is in
RING = "#f5c211"       # the chosen duelist's cell
DIM = 0.35             # the part of a picture the game leaves out, this bright


def photo(master, image: pngio.Image, size=None):
    """A Tk image of `image` (at `size` square, nearest)."""
    if size is not None and image.size != (size, size):
        image = pngio.scale_to(image, size, size)
    return tk.PhotoImage(master=master, data=pngio.ppm(image), format="PPM")


def dimmed_outside(image: pngio.Image, box) -> pngio.Image:
    """The picture with everything outside `box` (left, top, w, h) darkened."""
    left, top, w, h = box
    out = bytearray(pngio.flatten(image, (0x1B, 0x21, 0x30)).rgba)
    for y in range(image.height):
        for x in range(image.width):
            if left <= x < left + w and top <= y < top + h:
                continue
            at = (y * image.width + x) * 4
            out[at:at + 3] = bytes(int(v * DIM) for v in out[at:at + 3])
    return pngio.Image(image.width, image.height, bytes(out))


class GroupSort:
    """A heading click sorts the duelists within each page, the pages
    staying in order (widgets.TreeSort sorts the top rows only)."""

    def __init__(self, tree, labels: dict):
        self.tree, self.labels = tree, labels
        self.column, self.reverse = None, False
        for column in labels:
            tree.heading(column, command=lambda c=column: self.choose(c))

    def choose(self, column):
        self.reverse = not self.reverse if self.column == column else False
        self.column = column
        self.apply()

    def key(self, iid):
        if self.column == "#0":
            return (0, self.tree.item(iid, "text").casefold())
        value = self.tree.set(iid, self.column)
        return (0, int(value)) if value.isdigit() else (1, value.casefold())

    def apply(self):
        if self.column is None:
            return
        for page in self.tree.get_children():
            rows = list(self.tree.get_children(page))
            rows.sort(key=self.key, reverse=self.reverse)
            for index, iid in enumerate(rows):
                self.tree.move(iid, page, index)
        for column, label in self.labels.items():
            arrow = (" ▼" if self.reverse else " ▲") if column == self.column else ""
            self.tree.heading(column, text=label + arrow)


class DuelistsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Duelists")
        self.duelist = 1        # a disc duelist's id, or the id (str) of one the mod adds
        self.page_shown = 1     # the page the map shows
        self.faces = {}         # Tk images by what they show, kept while the game files are the same
        self.shown = []         # the header's Tk images (a label keeps none of its own)
        self.cell_at = {}       # the page map's cells: (row, column) -> the duelist there
        self.build_list()
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.build_header(right)
        ttk.Separator(right).pack(fill="x", pady=(8, 6))
        self.build_pools(right)

    # --- building -------------------------------------------------------------------

    def build_list(self):
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        frame = ttk.Frame(left)
        frame.pack(fill="y", expand=True)
        self.list = ttk.Treeview(frame, columns=("id", "state"), show="tree headings", height=14,
                                 selectmode="browse", style="Portrait.Treeview")
        self.list.heading("#0", text="Duelist")
        self.list.heading("id", text="#")
        self.list.heading("state", text="Status")
        self.list.widths = {"#0": px(left, 200), "id": px(left, 36), "state": px(left, 96)}
        self.list.column("#0", width=self.list.widths["#0"], stretch=True)
        self.list.column("id", width=self.list.widths["id"], stretch=False, anchor="e")
        self.list.column("state", width=self.list.widths["state"], stretch=False)
        bar = ttk.Scrollbar(frame, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=bar.set)
        self.list.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        from . import theme
        for tag in theme.TAGS:
            self.list.tag_configure(tag, foreground=theme.tag_color(self.list, tag))
        self.list.tag_configure("page", font=ui_font(10))
        self.list.sorting = GroupSort(self.list, {"#0": "Duelist", "id": "#"})
        self.list.bind("<<TreeviewSelect>>", lambda e: self.select())
        self.list.bind("<Double-1>", lambda e: self.edit())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(6, 0))
        self.add_button = ttk.Button(buttons, text="Add duelist...", command=self.add)
        self.add_button.pack(side="left")
        self.duplicate_button = ttk.Button(buttons, text="Duplicate", command=self.duplicate)
        self.duplicate_button.pack(side="left", padx=4)
        self.remove_button = ttk.Button(buttons, text="Remove", command=self.remove_duelist)
        self.remove_button.pack(side="left")
        # Wrapped at the list's width (a WrapLabel would take the window's).
        ttk.Label(left, style="Hint.TLabel", justify="left", wraplength=px(left, 350), text=(
            "A duelist you add is a copy of one of the disc's: its deck, drops, face and way of playing, "
            "under a name of its own. Added duelists fill the Free Duel grid's page 2 and on, forty a page; "
            "in the game L1 and R1 turn the page.")).pack(fill="x", pady=(6, 0))

    def build_header(self, right):
        header = ttk.Frame(right)
        header.pack(fill="x")
        self.header = header
        pictures = ttk.Frame(header)
        pictures.pack(side="left", anchor="n")
        self.canvases = {}
        for key, size, title in (("picture", PICTURE, "Your picture"), ("small", FACE_BIG, "In game (1x)"),
                                 ("sharp", FACE_BIG, "Internal 2x+")):
            column = ttk.Frame(pictures)
            column.pack(side="left", anchor="n", padx=(0, 8))
            ttk.Label(column, text=title, style="Note.TLabel").pack(anchor="w")
            canvas = tk.Canvas(column, width=px(self, size), height=px(self, PICTURE), background=STAGE,
                               highlightthickness=0, borderwidth=0)
            canvas.pack(anchor="w")
            caption = ttk.Label(column, style="Hint.TLabel", justify="left", wraplength=px(self, size + 4))
            caption.pack(anchor="w", pady=(2, 0))
            self.canvases[key] = (canvas, caption, size)
        self.canvases["picture"][0].bind("<Double-1>", lambda e: self.choose_picture())
        info = ttk.Frame(header)
        info.pack(side="left", fill="both", expand=True, anchor="n", padx=(6, 10))
        self.name_label = ttk.Label(info, font=ui_font(15))
        self.name_label.pack(anchor="w")
        self.kind_label = ttk.Label(info, style="Note.TLabel")
        self.kind_label.pack(anchor="w", pady=(2, 0))
        # Wrapped at a width of their own: the header's room is what the
        # pictures and the page map leave, and the tab must fit 1280 across.
        self.place_label = ttk.Label(info, justify="left", wraplength=px(self, 380))
        self.place_label.pack(anchor="w", pady=(6, 0))
        self.file_label = ttk.Label(info, style="Hint.TLabel")
        self.file_label.pack(anchor="w", pady=(2, 0))
        self.kept_label = ttk.Label(info, style="Hint.TLabel", justify="left", wraplength=px(self, 380))
        self.kept_label.pack(anchor="w", fill="x", pady=(2, 0))
        actions = ttk.Frame(info)
        actions.pack(anchor="w", pady=(10, 0))
        self.edit_button = ttk.Button(actions, text="Name and place...", command=self.edit)
        self.edit_button.pack(side="left")
        self.rules_button = ttk.Button(actions, text="Unlock, play, ranks...", command=self.edit_rules)
        self.rules_button.pack(side="left", padx=(4, 0))
        # Two rows: the tab must fit 1280 across.
        actions = ttk.Frame(info)
        actions.pack(anchor="w", pady=(4, 0))
        ttk.Button(actions, text="Picture...", command=self.choose_picture).pack(side="left", padx=(0, 4))
        self.revert_face_button = ttk.Button(actions, text="Disc's face", command=self.revert_picture)
        self.revert_face_button.pack(side="left")
        page = ttk.Frame(header)
        page.pack(side="right", anchor="n")
        top = ttk.Frame(page)
        top.pack(fill="x")
        ttk.Button(top, text="◀", width=2, style="Toolbutton", command=lambda: self.turn_page(-1)).pack(side="left")
        self.page_label = ttk.Label(top, anchor="center", style="Note.TLabel")
        self.page_label.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="▶", width=2, style="Toolbutton", command=lambda: self.turn_page(1)).pack(side="right")
        cell = px(self, MAP_CELL) + px(self, MAP_GAP)
        self.map = tk.Canvas(page, width=cell * roster.COLUMNS + px(self, MAP_GAP),
                             height=cell * (roster.PAGE // roster.COLUMNS) + px(self, MAP_GAP),
                             background=STAGE, highlightthickness=0, borderwidth=0)
        self.map.pack(pady=(2, 0))
        self.map.bind("<Button-1>", self.map_click)

    def build_pools(self, right):
        top = ttk.Frame(right)
        top.pack(fill="x")
        ttk.Label(top, text="Pools", font=ui_font(11)).pack(side="left", padx=(0, 10))
        self.pool = tk.StringVar(value="deck")
        for pool in POOLS:
            ttk.Radiobutton(top, text=POOL_LABELS[pool], value=pool, variable=self.pool,
                            command=self.fill).pack(side="left", padx=(0, 8))
        self.total = ttk.Label(top, font=ui_font(10))
        self.total.pack(side="right")
        self.summary = ttk.Label(right, style="Hint.TLabel")     # what the pool deals, against the disc's
        self.summary.pack(anchor="w", pady=(2, 0))
        frame, self.tree = scrolled_tree(right, [("id", "#"), ("name", "Card"), ("type", "Type"),
                                                 ("atk", "ATK"), ("def", "DEF"), ("w", "Weight"),
                                                 ("pct", "Chance"), ("retail", "Disc"), ("state", "Status")],
                                         [50, 220, 100, 50, 50, 60, 60, 60, 70], 14, selectmode="extended",
                                         sort_numeric=("id", "atk", "def", "w", "pct", "retail"))
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        edit = ttk.Frame(right)
        edit.pack(fill="x")
        self.fixed = FixedDeckView(self, right, top)     # a disc duelist's deck may be forty cards written down
        ttk.Button(edit, text="Add a card...", command=self.add_card).pack(side="left")
        ttk.Label(edit, text="Weight").pack(side="left", padx=(10, 2))
        self.weight = tk.StringVar()
        entry = ttk.Entry(edit, textvariable=self.weight, width=7)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.set_weight())
        ttk.Button(edit, text="Set", command=self.set_weight).pack(side="left", padx=2)
        ttk.Button(edit, text="Remove selected", command=self.remove).pack(side="left", padx=(8, 0))
        ttk.Button(edit, text="Scale to 2048 (100%)", command=self.normalize).pack(side="left", padx=4)
        ttk.Button(edit, text="Revert pool", command=self.revert).pack(side="left")
        # Above the list: below it, a window 800 high cut it off.
        WrapLabel(right, text="Weights are chances out of 2048. A deck is 40 cards dealt from at least 14; "
                              "a drop pool needs one card left.", style="Hint.TLabel").pack(
            fill="x", before=self.tree.master)

    # --- who is shown ------------------------------------------------------------------

    def subject(self):
        """The duelist shown: a disc id, or the mod's roster entry."""
        if isinstance(self.duelist, int):
            return self.duelist
        e = roster.find(self.project, self.duelist) if self.project is not None else None
        return e if e is not None and e.copy else 1

    def wa(self):
        files = getattr(self.app, "files", None)
        return files.wa if files is not None else None

    def face(self, s, size):
        """A Tk image of a duelist's face as the grid draws it at 1x, `size`
        square (kept: a list fills often)."""
        own = roster.replacement(self.project, s) if isinstance(s, int) else s
        png = own.portrait if own is not None else None
        base = s if isinstance(s, int) else s.base
        key = (png is not None and hash(png), base if png is None else None, size)
        if key not in self.faces:
            image = roster.face(self.project, self.wa(), s)
            if image is None:
                return ""
            self.faces[key] = photo(self, portrait.thumbnail(image, size))
            if len(self.faces) > 600:
                self.faces.pop(next(iter(self.faces)))
        return self.faces[key]

    def refresh(self):
        self.faces = {}
        if self.project is not None and not isinstance(self.duelist, int) and \
                roster.find(self.project, self.duelist) is None:
            self.duelist = 1
        self.fill_list()
        self.fill()

    @staticmethod
    def iid(s) -> str:
        return str(s) if isinstance(s, int) else "+" + s.key

    def fill_list(self):
        if self.project is None:
            return
        p = self.project
        tree = self.list
        open_pages = {iid: tree.item(iid, "open") for iid in tree.get_children()}
        tree.delete(*tree.get_children())
        size = px(self, FACE_ROW)
        tree.insert("", "end", iid="page:1", text="Page 1 · the disc's", values=("", f"{len(p.pools)} of {roster.PAGE}"),
                    open=open_pages.get("page:1", True), tags=("page",))
        for d in range(len(p.pools)):
            state = self.state_of(d)
            tags = ("changed",) if state and state != "not used" else ("note",) if state else ()
            tree.insert("page:1", "end", iid=str(d), text=" " + roster.shown_name(p, d), image=self.face(d, size),
                        values=(d, state), tags=tags)
        placed = roster.placement(p)
        pages = {}
        for e in roster.copies(p):
            slot = placed.get(e)
            pages.setdefault(roster.page_of(slot) if slot is not None else 0, []).append((slot, e))
        for page in sorted(pages, key=lambda n: n or 99):
            rows = sorted(pages[page], key=lambda row: (row[0] is None, row[0] or 0, row[1].key))
            iid = f"page:{page}"
            title = f"Page {page} · added" if page else "Not on the grid"
            tree.insert("", "end", iid=iid, text=title, values=("", f"{len(rows)} of {roster.PAGE}" if page else
                                                                "see Conflicts"),
                        open=open_pages.get(iid, True), tags=("page",))
            for slot, e in rows:
                if tree.exists(self.iid(e)):
                    continue        # a second entry of the same id: the game leaves it out
                state = self.state_of(e)
                tree.insert(iid, "end", iid=self.iid(e), text=" " + roster.shown_name(p, e), image=self.face(e, size),
                            values=("" if slot is None else slot, state), tags=("added",))
        tree.sorting.apply()
        chosen = self.iid(self.subject())
        if tree.exists(chosen):
            tree.selection_set(chosen)
            tree.see(chosen)
        self.update_buttons()

    def state_of(self, s) -> str:
        """The Status column: what the mod changes of a duelist."""
        p = self.project
        parts = []
        if isinstance(s, int):
            e = roster.replacement(p, s)
            if e is not None and e.name:
                parts.append("renamed")
            if e is not None and (e.portrait is not None or e.portrait_path):
                parts.append("face")
            if fixed_decks.deck_of(p, s):
                parts.append("fixed deck")
            elif any({c: w for c, w in p.pools[s][pool].items() if w} != p.retail.pools[s][pool] for pool in POOLS):
                parts.append("pools")
            parts += self.rules_state(e)
            if s == 0 and not parts:
                return "not used"   # no duel is fought against it
            return ", ".join(parts)
        # Its page row says it is added: what it has of its own beside its base's.
        if s.portrait is not None or s.portrait_path:
            parts.append("face")
        if fixed_decks.deck_of(p, s):
            parts.append("fixed deck")
        elif any({c: w for c, w in s.pools[pool].items() if w} != p.retail.pools[s.base][pool] for pool in POOLS):
            parts.append("pools")
        parts += self.rules_state(s)
        return ", ".join(parts) or "a copy"

    @staticmethod
    def rules_state(e) -> list:
        """The Status words for what an entry's unlock, ai and ranks change."""
        if e is None:
            return []
        return [word for key, word in (("unlock", "locked"), ("tower_only", "tower only"), ("ai", "plays"),
                                       ("ranks", "ranks")) if key in e.extra]

    def select(self):
        selection = self.list.selection()
        if not selection:
            return
        iid = selection[0]
        if iid.startswith("page:"):
            children = self.list.get_children(iid)
            if children:
                self.list.selection_set(children[0])
            return
        self.duelist = int(iid) if iid.isdigit() else iid[1:]
        self.update_buttons()
        self.fill()

    def update_buttons(self):
        added = not isinstance(self.subject(), int)
        for button in (self.duplicate_button, self.remove_button):
            button.state(["!disabled"] if added else ["disabled"])

    # --- the header -----------------------------------------------------------------------

    def fill_header(self):
        p, s = self.project, self.subject()
        self.shown = []
        e = roster.replacement(p, s) if isinstance(s, int) else s
        base = s if isinstance(s, int) else s.base
        name = roster.shown_name(p, s)
        self.name_label.configure(text=name)
        if isinstance(s, int):
            kind = "Deck Build: no duel is fought against it" if s == 0 else f"One of the disc's duelists, number {s}"
            if e is not None and e.name:
                kind += f" · was {DUELIST_NAMES[s]}"
        else:
            kind = f"Added by this mod · a copy of {DUELIST_NAMES[base]}"
        self.kind_label.configure(text=kind)
        slot = roster.slot_of(p, s)
        if slot is None:
            place = "Not on the Free Duel grid: another entry has its id, or there is no room left"
        else:
            row, column = roster.cell_of(slot)
            place = f"Free Duel page {roster.page_of(slot)}, row {row + 1}, column {column + 1}"
            if not isinstance(s, int):
                place += f"  ·  slot {slot}" + (", asked for" if s.slot == slot else ", the first free")
        self.place_label.configure(text=place)
        if e is None:
            where = "" if s == 0 else "Unchanged: its name and face are the disc's"
        else:
            where = f"Id {e.key} · " + {"folder": f"duelists/{e.key}.json", "manifest": "in mod.json's \"duelists\"",
                                         "file": f"in {p.roster_file}"}[e.origin]
        self.file_label.configure(text=where)
        self.kept_label.configure(text=self.kept_text(p, e))
        self.edit_button.state(["disabled"] if s == 0 else ["!disabled"])
        self.rules_button.state(["disabled"] if s == 0 else ["!disabled"])
        self.revert_face_button.state(["!disabled"] if roster.has_portrait(p, s) else ["disabled"])
        self.fill_pictures(s)
        self.page_shown = roster.page_of(slot) if slot is not None else self.page_shown
        self.fill_map()

    @staticmethod
    def kept_text(p, e) -> str:
        """The entry's unlock, way of playing and rank scoring said plainly,
        then the keys the editor has no field for."""
        if e is None or not e.extra:
            return ""
        lines = []
        if "unlock" in e.extra:
            lines.append("Unlocks after: " + duelist_rules.unlock_text(e))
        if "ai" in e.extra:
            lines.append("Plays: " + duelist_rules.ai_text(p, e))
        if "ranks" in e.extra:
            lines.append("Own rank scoring: " + (duelist_rules.ranks_text(e) or "none the game reads"))
        if e.extra.get("tower_only") is True:
            lines.append("The tower's alone: in Free Duel once a won floor lets it out (the Tower tab)")
        rest = [key for key in e.extra if key not in ("unlock", "ai", "ranks", "tower_only")]
        if rest:
            lines.append("Kept as written: " + ", ".join(rest))
        return "\n".join(lines)

    def fill_pictures(self, s):
        p = self.project
        own = roster.own_picture(p, s)
        for key, (canvas, caption, size) in self.canvases.items():
            canvas.delete("all")
            width, height = px(self, size), px(self, PICTURE)
            image, text = None, ""
            if key == "picture":
                if own is not None:
                    box = portrait.crop(own)
                    scale = min(width / own.width, height / own.height)
                    fit = (max(1, round(own.width * scale)), max(1, round(own.height * scale)))
                    shown = pngio.resample(own, *fit) if scale < 1 else pngio.scale_to(own, *fit)
                    box = tuple(round(v * scale) for v in box)
                    image = dimmed_outside(shown, box)
                    text = f"{own.width}×{own.height}" + ("" if own.width == own.height else
                                                         "; the game takes the middle square")
                else:
                    canvas.create_rectangle(px(self, 6), px(self, 6), width - px(self, 6), height - px(self, 6),
                                            outline="#5a6478", dash=(4, 3))
                    canvas.create_text(width // 2, height // 2, fill="#c4c8cd", justify="center",
                                       width=width - px(self, 16), font=ui_font(9, "normal"),
                                       text="None of its own:\nthe disc's face" if s != 0 else "The disc's")
                    text = "Any PNG: double-click, or Picture..." if s != 0 else ""
            elif key == "small":
                face = roster.face(p, self.wa(), s, 1)
                if face is not None:
                    image = pngio.scale_nearest(face, 2)
                text = ("Averaged to 48×48, shown at 2×" if own is not None and portrait.sharp(own) else
                        "48×48 in 64 colors, shown at 2×")
            else:
                if own is not None and portrait.sharp(own):
                    image = pngio.resample(portrait.hd_image(own), width, width)
                    text = "Your picture, at its own size"
                else:
                    face = roster.face(p, self.wa(), s, 1)
                    if face is not None:
                        image = pngio.scale_nearest(face, 2)
                    text = ("The same 48×48 (a bigger picture is sharper)" if own is not None else
                            "The disc's, or a texture pack's")
            if image is not None:
                tk_image = photo(self, image)
                self.shown.append(tk_image)
                canvas.create_image(width // 2, height // 2, image=tk_image)
            caption.configure(text=text)

    def fill_map(self):
        """The page as the game lays it out: five across, eight down, the
        chosen duelist's cell ringed."""
        p = self.project
        pages = roster.pages(p)
        self.page_shown = max(1, min(self.page_shown, pages))
        page = self.page_shown
        self.page_label.configure(text=f"Page {page} of {pages}")
        self.map.delete("all")
        self.cell_at = {}
        cell, gap = px(self, MAP_CELL), px(self, MAP_GAP)
        chosen = roster.slot_of(p, self.subject())
        here = {}
        if page == 1:
            here = {d: d for d in range(len(p.pools))}
        for e, slot in roster.placement(p).items():
            if slot is not None and roster.page_of(slot) == page:
                here[slot] = e
        for index in range(roster.PAGE):
            slot = (page - 1) * roster.PAGE + index
            row, column = divmod(index, roster.COLUMNS)
            x, y = gap + column * (cell + gap), gap + row * (cell + gap)
            who = here.get(slot)
            if who is None:
                self.map.create_rectangle(x, y, x + cell - 1, y + cell - 1, fill=EMPTY, outline="")
                continue
            self.cell_at[(row, column)] = who
            face = self.face(who, cell)
            if face:
                self.map.create_image(x, y, image=face, anchor="nw")
            if slot == chosen:
                self.map.create_rectangle(x - 2, y - 2, x + cell + 1, y + cell + 1, outline=RING, width=2)

    def map_click(self, event):
        cell, gap = px(self, MAP_CELL), px(self, MAP_GAP)
        column, row = (event.x - gap) // (cell + gap), (event.y - gap) // (cell + gap)
        who = self.cell_at.get((row, column))
        if who is not None:
            self.goto((who if isinstance(who, int) else who.key, None))

    def turn_page(self, step):
        if self.project is None:
            return
        self.page_shown = max(1, min(self.page_shown + step, roster.pages(self.project)))
        self.fill_map()

    # --- the roster's edits --------------------------------------------------------------

    def changed(self, s=None):
        self.app.changed()
        if s is not None:
            self.duelist = s if isinstance(s, int) else s.key
        self.fill_list()
        self.fill()

    def add(self):
        if self.project is None:
            return None
        s = self.subject()
        base = s if isinstance(s, int) and s > 0 else (s.base if not isinstance(s, int) else 1)
        return self.duelist_dialog(None, base)

    def edit(self):
        if self.project is None:
            return None
        s = self.subject()
        if s == 0:
            return None
        return self.duelist_dialog(s, s if isinstance(s, int) else s.base)

    def duelist_dialog(self, s, base: int):
        """Add a duelist (s None), or a duelist's name and place: a disc
        duelist's name only, as it keeps its place."""
        p = self.project
        adding = s is None
        disc = isinstance(s, int)
        names = [f"{d} {DUELIST_NAMES[d]}" for d in range(1, DUELIST_COUNT)]
        fields = {}

        def place_hint(*_):
            if "slot" not in fields:
                return
            if fields["auto"].get():
                fields["hint"].configure(text="The first free place on page 2 and after")
                return
            text = fields["slot"].get().strip()
            if not text.isdigit() or not roster.FIRST_SLOT <= int(text) <= roster.LAST_SLOT:
                fields["hint"].configure(text=f"A slot is {roster.FIRST_SLOT} to {roster.LAST_SLOT}")
                return
            slot = int(text)
            rival = next((o for o, at in roster.placement(p).items() if at == slot and o is not s), None)
            words = roster.where(slot)
            words = words[0].upper() + words[1:]
            fields["hint"].configure(text=words + (f": {roster.shown_name(p, rival)} has it now" if rival else ""))

        def name_typed(*_):
            if adding and not fields.get("key_typed"):
                typed = fields["name"].get().strip()
                fields["key"].set(roster.free_key(p, roster.slug(typed or DUELIST_NAMES[chosen_base()])))

        def chosen_base():
            return int(fields["base"].get().split(" ", 1)[0]) if "base" in fields else base

        def build(dialog, body):
            row = 0
            if not disc:
                ttk.Label(body, text="Copy of").grid(row=row, column=0, sticky="w", pady=3)
                fields["base"] = tk.StringVar(value=names[base - 1])
                box = ttk.Combobox(body, textvariable=fields["base"], values=names, state="readonly", width=28)
                box.grid(row=row, column=1, sticky="w", pady=3)
                box.bind("<<ComboboxSelected>>", name_typed)
                row += 1
            ttk.Label(body, text="Name").grid(row=row, column=0, sticky="w", pady=3)
            fields["name"] = tk.StringVar(value="" if adding else roster.shown_name(p, s))
            name = ttk.Entry(body, textvariable=fields["name"], width=32)
            name.grid(row=row, column=1, sticky="we", pady=3)
            name.focus_set()
            row += 1
            if not disc:
                ttk.Label(body, text="Id").grid(row=row, column=0, sticky="w", pady=3)
                fields["key"] = tk.StringVar(value=roster.free_key(p, roster.slug(DUELIST_NAMES[base])) if adding
                                             else s.key)
                key = ttk.Entry(body, textvariable=fields["key"], width=32)
                key.grid(row=row, column=1, sticky="we", pady=3)
                key.bind("<Key>", lambda e: fields.__setitem__("key_typed", True))
                row += 1
                ttk.Label(body, text="Its files are named for it (duelists/<id>.json...), and saves know it by it.",
                          style="Hint.TLabel").grid(row=row, column=1, sticky="w")
                row += 1
                ttk.Label(body, text="Place").grid(row=row, column=0, sticky="nw", pady=(8, 3))
                where = ttk.Frame(body)
                where.grid(row=row, column=1, sticky="w", pady=(8, 3))
                asked = None if adding else s.slot
                fields["auto"] = tk.BooleanVar(value=asked is None)
                ttk.Radiobutton(where, text="First free place", value=True, variable=fields["auto"],
                                command=place_hint).pack(side="left")
                ttk.Radiobutton(where, text="Slot", value=False, variable=fields["auto"],
                                command=place_hint).pack(side="left", padx=(10, 2))
                fields["slot"] = tk.StringVar(value=str(asked if asked is not None else
                                                        (roster.slot_of(p, s) or roster.FIRST_SLOT) if not adding
                                                        else roster.FIRST_SLOT))
                spin = ttk.Spinbox(where, textvariable=fields["slot"], from_=roster.FIRST_SLOT, to=roster.LAST_SLOT,
                                   width=5, command=lambda: (fields["auto"].set(False), place_hint()))
                spin.pack(side="left")
                spin.bind("<KeyRelease>", lambda e: (fields["auto"].set(False), place_hint()))
                row += 1
                fields["hint"] = ttk.Label(body, style="Hint.TLabel")
                fields["hint"].grid(row=row, column=1, sticky="w")
                row += 1
                place_hint()
            fields["name"].trace_add("write", name_typed)
            what = (f"A disc duelist keeps its place on the grid. Its new name is written as a \"replace\" entry; "
                    f"leave it as \"{DUELIST_NAMES[s]}\" for the disc's." if disc else
                    "It starts as its base: the same deck, drops, face and way of playing. Change any of "
                    "them here afterwards." if adding else
                    "Another base gives it that duelist's way of playing; its pools stay as they are.")
            ttk.Label(body, text=what, style="Hint.TLabel", wraplength=px(body, 420), justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def ok(dialog):
            name = fields["name"].get().strip()
            if any(ord(c) < 32 for c in name):
                return "A name has no control characters"
            if disc:
                roster.set_name(p, s, name)
                self.changed(s)
                return None
            new_base = chosen_base()
            key = fields["key"].get().strip()
            if (adding or key != s.key) and (not roster.KEY_RE.match(key) or len(key) > roster.KEY_MAX):
                return f"An id is 1 to {roster.KEY_MAX} letters, digits, hyphens or underscores"
            if any(o is not s and o.key.lower() == key.lower() for o in roster.entries(p)):
                return f"Another duelist has the id {key}"
            slot = None
            if not fields["auto"].get():
                text = fields["slot"].get().strip()
                if not text.isdigit() or not roster.FIRST_SLOT <= int(text) <= roster.LAST_SLOT:
                    return f"A slot is {roster.FIRST_SLOT} to {roster.LAST_SLOT}"
                slot = int(text)
            if adding:
                e = roster.add_copy(p, new_base, name, slot, key)
            else:
                e = s
                if key != e.key:
                    roster.rename_key(p, e, key)
                if new_base != e.base:
                    if e.pools == {pool: {c: w for c, w in p.pools[e.base][pool].items() if w} for pool in POOLS}:
                        e.pools = {pool: dict(p.pools[new_base][pool]) for pool in POOLS}
                    e.base = new_base
                roster.set_name(p, e, name)
                e.slot = slot
                e.extra.pop("slot", None)       # an id it could not have; the field says what it has now
            self.changed(e)
            return None

        title = "Add a duelist" if adding else f"{roster.shown_name(p, s)}: name and place"
        return FormDialog(self, title, build, ok)

    def edit_rules(self):
        if self.project is None:
            return None
        s = self.subject()
        if s == 0:
            return None
        return self.rules_dialog(s)

    def rules_dialog(self, s):
        """A duelist's "unlock", "ai" and "ranks" (duelist_rules.py): when the
        grid shows it, how it plays, how a duel against it is scored. A disc
        duelist's go on its replacement."""
        p = self.project
        e = roster.replacement(p, s) if isinstance(s, int) else s
        holder = e if e is not None else roster.RosterDuelist(key="", base=s, replace=True)
        base = s if isinstance(s, int) else s.base
        others = [""] + duelist_rules.references(p, but=holder)
        if isinstance(s, int):
            others.remove(duelist_rules.reference(p, s))
        unlock, ai, ranks = duelist_rules.unlock_of(holder), duelist_rules.ai_of(holder), duelist_rules.ranks_of(holder)
        fields = {}

        def number_text(value):
            return "" if value is None else str(value)

        def story_hint(*_):
            text = fields["story"].get().strip()
            try:
                flag = int(text, 0) if text else None
            except ValueError:
                fields["story_hint"].configure(text="A number: 1762, or 0x6E2")
                return
            n = None if flag is None else flag - STORY_FREE_DUEL
            fields["story_hint"].configure(text="" if flag is None else f"0x{flag:X}" + (
                f": {DUELIST_NAMES[n]} unlocked in Free Duel" if n is not None and 0 < n < DUELIST_COUNT else ""))

        def under_hint(*_):
            row = duelist_rules.under_row(p, s, fields["copy"].get().strip())
            for i, label in enumerate(fields["under"]):
                label.configure(text=f"else {row[i]}")
            mine = fields["copy"].get().strip()
            fields["copy_hint"].configure(text=f"blank: {DUELIST_NAMES[base]}'s, its base" if not mine else
                                          "" if roster.named(p, mine) is not None else
                                          "no duelist here: unless another mod adds it, its base's")

        def own_rule(rule):
            on = fields["own"][rule].get()
            for k, (threshold, change) in enumerate(fields["pairs"][rule]):
                if not on:
                    threshold.set(str(RANK_RETAIL[rule][k][0]) if k < RANK_STEPS - 1 else "above")
                    change.set(str(RANK_RETAIL[rule][k][1]))
            for widget in fields["rank_widgets"][rule]:
                widget.state(["!disabled"] if on else ["disabled"])

        def pick(dialog):
            cid = pick_card(dialog, p, "Card the player must hold")
            if cid:
                fields["card"].set(str(p.ref(cid)))

        def build(dialog, body):
            book = ttk.Notebook(body)
            book.pack(fill="both", expand=True)
            fields["book"] = book
            # Unlock: every condition given must hold.
            page = ttk.Frame(book, padding=8)
            book.add(page, text="Unlock")
            ttk.Label(page, text="Beat").grid(row=0, column=0, sticky="w", pady=3)
            fields["beat"] = tk.StringVar(value=unlock["beat"])
            ttk.Combobox(page, textvariable=fields["beat"], values=others, width=30).grid(row=0, column=1, sticky="w")
            ttk.Label(page, text="a duelist to beat first: by name, number or identity",
                      style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=6)
            ttk.Label(page, text="Wins").grid(row=1, column=0, sticky="w", pady=3)
            fields["wins"] = tk.StringVar(value=number_text(unlock["wins"] or None))
            ttk.Spinbox(page, textvariable=fields["wins"], from_=0, to=9999, width=6).grid(row=1, column=1, sticky="w")
            ttk.Label(page, text="against Beat (1 by default), or against everyone together without it",
                      style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=6)
            ttk.Label(page, text="Story flag").grid(row=2, column=0, sticky="w", pady=3)
            fields["story"] = tk.StringVar(value="" if unlock["story"] is None else f"0x{unlock['story']:X}")
            ttk.Entry(page, textvariable=fields["story"], width=8).grid(row=2, column=1, sticky="w")
            fields["story_hint"] = ttk.Label(page, style="Hint.TLabel")
            fields["story_hint"].grid(row=2, column=2, sticky="w", padx=6)
            fields["story"].trace_add("write", story_hint)
            ttk.Label(page, text="Card").grid(row=3, column=0, sticky="w", pady=3)
            cell = ttk.Frame(page)
            cell.grid(row=3, column=1, columnspan=2, sticky="w")
            fields["card"] = tk.StringVar(value=unlock["card"])
            ttk.Entry(cell, textvariable=fields["card"], width=30).pack(side="left")
            ttk.Button(cell, text="Pick...", command=lambda: pick(dialog)).pack(side="left", padx=4)
            ttk.Label(cell, text="in the trunk or deck", style="Hint.TLabel").pack(side="left", padx=2)
            ttk.Label(page, text="Copies").grid(row=4, column=0, sticky="w", pady=3)
            fields["copies"] = tk.StringVar(value=number_text(unlock["copies"] or None))
            ttk.Spinbox(page, textvariable=fields["copies"], from_=0, to=999, width=6).grid(row=4, column=1, sticky="w")
            ttk.Label(page, text="of Card (1 by default)", style="Hint.TLabel").grid(row=4, column=2, sticky="w", padx=6)
            ttk.Label(page, style="Hint.TLabel", justify="left", wraplength=px(page, 560), text=(
                "Every condition given must hold; with none it is shown from the start. Read from the save "
                "each time the Free Duel grid is built: nothing is stored." + (
                    " For one of the disc's duelists this stands in place of the campaign flag that shows it."
                    if isinstance(s, int) else ""))).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
            story_hint()
            # Way of playing: nine numbers over another's row or its base's.
            page = ttk.Frame(book, padding=8)
            book.add(page, text="Way of playing")
            ttk.Label(page, text="Play like").grid(row=0, column=0, sticky="w", pady=3)
            fields["copy"] = tk.StringVar(value=ai["copy"])
            ttk.Combobox(page, textvariable=fields["copy"], values=others, width=30).grid(
                row=0, column=1, columnspan=2, sticky="w")
            fields["copy_hint"] = ttk.Label(page, style="Hint.TLabel")
            fields["copy_hint"].grid(row=0, column=3, sticky="w", padx=6)
            fields["values"], fields["under"] = [], []
            for i, label in enumerate(AI_FIELD_LABELS):
                ttk.Label(page, text=f"{i}  {label}").grid(row=i + 1, column=0, sticky="w", pady=1)
                var = tk.StringVar(value=number_text(ai["values"][i]))
                ttk.Entry(page, textvariable=var, width=6).grid(row=i + 1, column=1, sticky="w")
                under = ttk.Label(page, style="Hint.TLabel")
                under.grid(row=i + 1, column=2, sticky="w", padx=6)
                fields["values"].append(var)
                fields["under"].append(under)
            ttk.Label(page, style="Hint.TLabel", justify="left", text=(
                f"Blank: the number of the row above it.\nSearch is {AI_SEARCH[0]} to {AI_SEARCH[1]} cards deep; "
                "the LP threshold\nis ÷100 (20 is 2000). Fusion depth 3\nfuses from the hand.")).grid(
                row=2, column=3, rowspan=6, sticky="nw", padx=6)
            fields["copy"].trace_add("write", under_hint)
            fields["sight"] = tk.StringVar(value={None: "base", True: "yes", False: "no"}[ai["sight"]])
            sight = ttk.Frame(page)
            sight.grid(row=AI_FIELDS + 1, column=0, columnspan=4, sticky="w", pady=(8, 0))
            ttk.Label(sight, text="Face-down cards").pack(side="left", padx=(0, 6))
            sees = "sees them" if base in SIGHT_DUELISTS else "does not see them"
            for value, text in (("base", f"its base's ({sees})"), ("yes", "sees them"), ("no", "does not")):
                ttk.Radiobutton(sight, text=text, value=value, variable=fields["sight"]).pack(side="left", padx=(0, 8))
            under_hint()
            # Rank scoring: five [threshold, change] pairs a rule.
            page = ttk.Frame(book, padding=8)
            book.add(page, text="Rank scoring")
            ttk.Label(page, text="Rule").grid(row=0, column=0, sticky="w")
            ttk.Label(page, text="Own").grid(row=0, column=1)
            for k in range(RANK_STEPS):
                ttk.Label(page, text=f"below · change {k + 1}", style="Hint.TLabel").grid(
                    row=0, column=2 + k * 2, columnspan=2)
            fields["own"], fields["pairs"], fields["rank_widgets"] = [], [], []
            for rule, name in enumerate(RANK_RULES):
                ttk.Label(page, text=name).grid(row=rule + 1, column=0, sticky="w", pady=1)
                own = tk.BooleanVar(value=rule in ranks)
                ttk.Checkbutton(page, variable=own, command=lambda r=rule: own_rule(r)).grid(row=rule + 1, column=1)
                pairs, widgets = [], []
                given = ranks.get(rule, RANK_RETAIL[rule])
                for k in range(RANK_STEPS):
                    threshold = tk.StringVar(value=str(given[k][0]) if k < RANK_STEPS - 1 else "above")
                    change = tk.StringVar(value=str(given[k][1]))
                    left = ttk.Entry(page, textvariable=threshold, width=6)
                    left.grid(row=rule + 1, column=2 + k * 2, padx=(6, 0))
                    right = ttk.Entry(page, textvariable=change, width=4)
                    right.grid(row=rule + 1, column=3 + k * 2)
                    if k < RANK_STEPS - 1:
                        widgets.append(left)
                    else:
                        left.state(["disabled"])        # "and above": the game makes it 32767
                    widgets.append(right)
                    pairs.append((threshold, change))
                fields["own"].append(own)
                fields["pairs"].append(pairs)
                fields["rank_widgets"].append(widgets)
                own_rule(rule)
            ttk.Label(page, style="Hint.TLabel", justify="left", wraplength=px(page, 620), text=(
                "A duel's score starts at 50; for each rule, what you managed walks the pairs until a threshold "
                "is above it, and that pair's change is added. 50 and up is POW, below 50 TEC, and the further "
                "from 50 the better the letter: S and A roll the POW or TEC drops, B to D the B/C/D drops. "
                "Unticked: the disc's, the same for every duelist.")).grid(
                row=len(RANK_RULES) + 1, column=0, columnspan=2 + RANK_STEPS * 2, sticky="w", pady=(10, 0))

        def whole(text, what, low, high, blank=None):
            text = text.strip()
            if not text:
                return blank
            try:
                value = int(text, 0)
            except ValueError:
                raise ValueError(f"{what} is a whole number")
            if not low <= value <= high:
                raise ValueError(f"{what} is {low} to {high}")
            return value

        def ok(dialog):
            try:
                beat, card = fields["beat"].get().strip(), fields["card"].get().strip()
                wins = whole(fields["wins"].get(), "Wins", 0, 0x7FFFFFFF, 0)
                story = whole(fields["story"].get(), "A story flag", 0, 0xFFFF)
                copies = whole(fields["copies"].get(), "Copies", 0, 0x7FFFFFFF, 0)
                values = [whole(v.get(), f"Number {i} of the way of playing", -128, 127)
                          for i, v in enumerate(fields["values"])]
                if values[0] is not None and not AI_SEARCH[0] <= values[0] <= AI_SEARCH[1]:
                    raise ValueError(f"Deck search is {AI_SEARCH[0]} to {AI_SEARCH[1]}")
                rules = {}
                for rule, pairs in enumerate(fields["pairs"]):
                    if not fields["own"][rule].get():
                        continue
                    rules[rule] = tuple(
                        (whole(t.get(), f"{RANK_RULES[rule]}: threshold {k + 1}", -0x8000, 0x7FFF, 0)
                         if k < RANK_STEPS - 1 else RANK_ABOVE,
                         whole(c.get(), f"{RANK_RULES[rule]}: change {k + 1}", -0x8000, 0x7FFF, 0))
                        for k, (t, c) in enumerate(pairs))
            except ValueError as problem:
                return str(problem)
            if beat and roster.named(p, beat) in (s, holder):
                return "It cannot be unlocked by beating itself"
            copy = fields["copy"].get().strip()
            sight = {"base": None, "yes": True, "no": False}[fields["sight"].get()]
            before = _copy.deepcopy(holder.extra)
            under = duelist_rules.under_row(p, s, copy)
            made = (duelist_rules.unlock_value(holder, beat, wins, story, card, copies),
                    duelist_rules.ai_value(holder, copy, values, sight, under),
                    duelist_rules.ranks_value(holder, rules))
            changed = {k: v for k, v in zip(("unlock", "ai", "ranks"), made) if v is not None} != \
                {k: before[k] for k in ("unlock", "ai", "ranks") if k in before}
            if changed:
                duelist_rules.set_rules(p, s, *made)
                self.changed(s)
            return None

        title = f"{roster.shown_name(p, s)}: unlock, way of playing and ranks"
        return FormDialog(self, title, build, ok)

    def duplicate(self):
        s = self.subject()
        if self.project is None or isinstance(s, int):
            return
        self.changed(roster.duplicate(self.project, s))

    def remove_duelist(self):
        s = self.subject()
        if self.project is None or isinstance(s, int):
            return
        if not messagebox.askyesno("Remove duelist", f"Take {roster.shown_name(self.project, s)} out of the mod? "
                                   "Its deck, drops and portrait go with it.", parent=self):
            return
        slot = roster.slot_of(self.project, s)
        roster.remove(self.project, s)
        # The one next to it on the grid, else the last of the disc's.
        rest = sorted((at, e) for e, at in roster.placement(self.project).items() if at is not None)
        after = [e for at, e in rest if slot is None or at > slot] or [e for _, e in rest]
        self.changed(after[0] if after else DUELIST_COUNT - 1)

    def choose_picture(self):
        s = self.subject()
        if self.project is None or s == 0:
            return
        path = file_dialogs.askopenfilename(parent=self, title=f"A picture for {roster.shown_name(self.project, s)}",
                                            filetypes=[("PNG pictures", "*.png"), ("All files", "*")])
        if path:
            self.use_picture(path)

    def use_picture(self, path):
        s = self.subject()
        try:
            data = Path(path).read_bytes()
            roster.set_portrait(self.project, s, data)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Picture", f"{path} cannot be used: {problem}", parent=self)
            return
        self.changed(s)

    def revert_picture(self):
        s = self.subject()
        if self.project is None or not roster.has_portrait(self.project, s):
            return
        roster.revert_portrait(self.project, s)
        self.changed(s)

    # --- the pools -----------------------------------------------------------------------------

    def current_pool(self):
        return roster.pools_of(self.project, self.subject())[self.pool.get()]

    def retail_pool(self):
        return roster.retail_pool(self.project, self.subject(), self.pool.get())

    def fill(self):
        if self.project is None:
            return
        self.fill_header()
        s = self.subject()
        self.tree.heading("retail", text="Disc" if isinstance(s, int) else "Base")
        if self.fixed.fill():
            return
        p = self.project
        self.tree.delete(*self.tree.get_children())
        pool = self.current_pool()
        retail = self.retail_pool()
        for cid in sorted(set(pool) | set(retail), key=lambda c: (-pool.get(c, 0), c)):
            weight, before = pool.get(cid, 0), retail.get(cid, 0)
            if not weight and not before:
                continue
            state = "" if weight == before else "added" if not before else "removed" if not weight else "changed"
            card = p.cards.get(cid)
            self.tree.insert("", "end", iid=str(cid), tags=(state,) if state else (), values=(
                cid, card.name if card else "?", type_label(card.type) if card else "",
                card.attack if card else "", card.defense if card else "", weight,
                f"{weight * 100 / POOL_TOTAL:.2f}%", before, state))
        self.tree.sorting.apply()
        total = sum(pool.values())
        cards = sum(1 for w in pool.values() if w)
        self.total.configure(text=f"{roster.label(p, s)}: {cards} cards, total {total} / {POOL_TOTAL}",
                             style="Ok.TLabel" if total == POOL_TOTAL else "Error.TLabel")
        summary = pool_summary(p, self.pool.get(), pool, retail)
        if not isinstance(s, int):
            summary = summary.replace("(the disc's:", f"({DUELIST_NAMES[s.base]}'s on the disc:")
        self.summary.configure(text=summary)

    def pick_row(self):
        selection = self.tree.selection()
        if len(selection) == 1:
            self.weight.set(str(self.current_pool().get(int(selection[0]), 0)))

    def edited(self):
        pool = self.current_pool()
        for cid in [c for c, w in pool.items() if not w]:
            del pool[cid]
        self.app.changed()
        self.fill()
        self.fill_list()

    def add_card(self):
        if self.project is None:
            return
        cid = pick_card(self, self.project, "Card to add to the pool")
        if not cid:
            return
        try:
            weight = int(self.weight.get() or "0")
        except ValueError:
            weight = 0
        self.current_pool()[cid] = weight if weight > 0 else 1
        self.edited()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))

    def set_weight(self):
        try:
            weight = int(self.weight.get())
        except ValueError:
            messagebox.showerror("Weight", "A weight is a whole number, 0 or more.", parent=self)
            return
        if weight < 0 or weight > 0xFFFF:
            messagebox.showerror("Weight", "A weight is 0 to 65535 (out of 2048).", parent=self)
            return
        pool = self.current_pool()
        chosen = [int(i) for i in self.tree.selection()]
        for cid in chosen:
            pool[cid] = weight
        self.edited()
        for cid in chosen:
            if self.tree.exists(str(cid)):
                self.tree.selection_add(str(cid))

    def remove(self):
        pool = self.current_pool()
        for iid in self.tree.selection():
            pool.pop(int(iid), None)
        self.edited()

    def normalize(self):
        if self.project is None:
            return
        roster.pools_of(self.project, self.subject())[self.pool.get()] = poolmath.normalize(self.current_pool())
        self.edited()

    def revert(self):
        p, s, pool = self.project, self.subject(), self.pool.get()
        if p is None:
            return
        retail = self.retail_pool()
        if {c: w for c, w in self.current_pool().items() if w} == retail:
            return
        whose = (f"{DUELIST_NAMES[s]}'s {POOL_LABELS.get(pool, pool)} back as the disc has it" if isinstance(s, int)
                 else f"{roster.shown_name(p, s)}'s {POOL_LABELS.get(pool, pool)} back as {DUELIST_NAMES[s.base]}'s "
                      "on the disc")
        if not messagebox.askyesno("Revert pool", f"Put {whose}? The mod's changes to it are lost.", parent=self):
            return
        roster.pools_of(p, s)[pool] = dict(retail)
        self.edited()

    def goto(self, target):
        """(duelist, pool): a disc id, an added duelist's id or its roster
        entry; pool None keeps the one shown."""
        d, pool = target
        if isinstance(d, roster.RosterDuelist):
            d = d.base if d.replace else d.key
        self.duelist = d
        if pool:
            self.pool.set(pool)
        self.fill_list()
        if self.list.exists(self.iid(self.subject())):
            self.list.see(self.iid(self.subject()))
        self.fill()
