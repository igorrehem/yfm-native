"""The Guardian Stars tab: a mod's "guardian_stars" (guardian_stars.py,
notes/modding.md): the stars' names and icons, new stars past the disc's ten,
and the matchup grid, one signed bonus for each attacker's star against each
defender's. The simple view is the list, the grid and the default bonus; the
advanced one adds names by language, an icon's colors and the summon choice.
"Set stars by rule..." sets many cards' stars at once (star_rules.py)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import file_dialogs, guardian_stars as gs, pngio, theme
from .tabs import Tab
from .widgets import WrapLabel, px, scrolled_tree, ui_font

CELL = 44           # a grid cell's side at 96 dpi
HEAD = 78           # the header row's and column's
ICON_ZOOM = 3
# Cell colors by sign: light, dark.
COLORS = {
    "plus": ("#cdeccf", "#1f4d2c"),
    "minus": ("#f6d0cf", "#5a2323"),
    "zero": ("#f4f4f4", "#2a2b2f"),
    "head": ("#e2e4e8", "#35373c"),
    "line": ("#b8bcc2", "#55585e"),
    "ink": ("#202124", "#e8eaed"),
    "pick": ("#1a5fb4", "#8ab4f8"),
}


def color(widget, key: str) -> str:
    light, dark = COLORS[key]
    return dark if theme.is_dark(widget) else light


def _signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def _names_text(name) -> str:
    """A star's "name" object as the advanced box writes it: code=name, ..."""
    if isinstance(name, dict):
        return ", ".join(f"{k}={v}" for k, v in name.items() if isinstance(v, str))
    return ""


def _parse_names(text: str) -> dict:
    out = {}
    for part in text.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip() and value.strip():
                out[key.strip()] = value.strip()
    return out


class GuardianStarsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Guardian Stars")
        self.model = gs.Stars()
        self.selected_star = None
        self.cell = None          # (attacker, defender) the grid has picked
        self.photos = {}
        self.icon_images = {}     # star -> pngio.Image of the mod's icon, as loaded
        WrapLabel(self, style="Hint.TLabel",
                  text="Each cell is what the attacker's star (row) gets against the defender's star (column): "
                       "the disc gives +500 to the star just before in its cycle and -500 to the one just after, "
                       "0 otherwise. A card holds its stars in 4 bits, so 15 stars at most.").pack(fill="x")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(6, 0))
        # The stars.
        left = ttk.LabelFrame(body, text="Stars", padding=6)
        left.pack(side="left", fill="y")
        frame, self.tree = scrolled_tree(left, [("id", "#"), ("name", "Name"), ("icon", "Icon"), ("cards", "Cards")],
                                         [34, 130, 70, 50], 15)
        frame.pack(fill="y", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._pick_star())
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Add star", command=self.add_star).pack(side="left")
        self.remove_button = ttk.Button(row, text="Remove", command=self.remove_star, width=8)
        self.remove_button.pack(side="left", padx=4)
        form = ttk.Frame(left)
        form.pack(fill="x", pady=(6, 0))
        self.name = tk.StringVar()
        ttk.Label(form, text="Name").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(form, textvariable=self.name, width=18)
        name_entry.grid(row=0, column=1, sticky="w", padx=4)
        name_entry.bind("<Return>", lambda e: self.set_name())
        name_entry.bind("<FocusOut>", lambda e: self.set_name())
        self.icon_label = ttk.Label(form, relief="sunken")
        self.icon_label.grid(row=1, column=0, rowspan=2, pady=4)
        ttk.Button(form, text="Import icon (PNG)...", command=self.import_icon).grid(row=1, column=1, sticky="w",
                                                                                    padx=4)
        ttk.Button(form, text="Remove icon", command=self.remove_icon).grid(row=2, column=1, sticky="w", padx=4)
        self.advanced_star = ttk.Frame(form)
        self.names = tk.StringVar()
        self.palette = tk.StringVar(value="game")
        ttk.Label(self.advanced_star, text="By language").grid(row=0, column=0, sticky="w")
        names_entry = ttk.Entry(self.advanced_star, textvariable=self.names, width=24)
        names_entry.grid(row=0, column=1, sticky="w", padx=4)
        names_entry.bind("<FocusOut>", lambda e: self.set_name())
        ttk.Label(self.advanced_star, style="Hint.TLabel", text="fr=Feu, de=Feuer (en-us, en-eu, fr, de, it, es)"
                  ).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(self.advanced_star, text="Icon colors").grid(row=2, column=0, sticky="w")
        palette = ttk.Combobox(self.advanced_star, textvariable=self.palette, values=list(gs.PALETTES),
                               state="readonly", width=8)
        palette.grid(row=2, column=1, sticky="w", padx=4)
        palette.bind("<<ComboboxSelected>>", lambda e: self.set_palette())
        ttk.Label(self.advanced_star, style="Hint.TLabel", text="game: the disc's stars' 16 colors; own: the PNG's"
                  ).grid(row=3, column=0, columnspan=2, sticky="w")

        # The grid.
        right = ttk.LabelFrame(body, text="Matchups (row attacks column)", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.canvas = tk.Canvas(right, highlightthickness=0, width=px(self, HEAD + CELL * 10),
                                height=px(self, HEAD + CELL * 10))
        self.canvas.pack(anchor="nw")
        self.canvas.bind("<Button-1>", self._click)
        # A classic Canvas hears no theme change; the tab (a ttk widget) does.
        self.bind("<<ThemeChanged>>", lambda e: self.draw(), add="+")
        edit = ttk.Frame(right)
        edit.pack(fill="x", pady=(6, 0))
        self.cell_label = ttk.Label(edit, text="Click a cell, then its bonus:")
        self.cell_label.pack(side="left")
        self.value = tk.StringVar()
        value_entry = ttk.Entry(edit, textvariable=self.value, width=8)
        value_entry.pack(side="left", padx=4)
        value_entry.bind("<Return>", lambda e: self.set_cell())
        ttk.Button(edit, text="Set", command=self.set_cell).pack(side="left")
        ttk.Button(edit, text="+ default", command=lambda: self.set_cell(self._default())).pack(side="left", padx=2)
        ttk.Button(edit, text="- default", command=lambda: self.set_cell(-self._default())).pack(side="left", padx=2)
        ttk.Button(edit, text="0", width=3, command=lambda: self.set_cell(0)).pack(side="left", padx=2)
        self.mirror = tk.BooleanVar(value=True)
        ttk.Checkbutton(edit, text="Reverse pair gets the opposite", variable=self.mirror).pack(side="left", padx=8)

        # The whole table.
        options = ttk.Frame(self)
        options.pack(fill="x", pady=(6, 0))
        ttk.Label(options, text="Default bonus").pack(side="left")
        self.default = tk.StringVar()
        default_entry = ttk.Entry(options, textvariable=self.default, width=7)
        default_entry.pack(side="left", padx=4)
        default_entry.bind("<Return>", lambda e: self.set_default())
        default_entry.bind("<FocusOut>", lambda e: self.set_default())
        ttk.Label(options, style="Hint.TLabel", text="(500; what the cycles give)").pack(side="left")
        ttk.Button(options, text="Retail cycles", command=self.preset_retail).pack(side="left", padx=(12, 2))
        ttk.Button(options, text="Clear all", command=self.preset_clear).pack(side="left", padx=2)
        ttk.Button(options, text="Set stars by rule...", command=self.open_rules).pack(side="left", padx=(12, 2))
        ttk.Button(options, text="Revert to retail", command=self.revert).pack(side="right")
        self.advanced_shown = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(self, text="Show advanced", variable=self.advanced_shown,
                        command=self._show_advanced).pack(anchor="w", pady=(6, 0))
        self.advanced = ttk.Frame(self)
        ttk.Label(self.advanced, text="At summon").pack(side="left")
        self.choice = tk.StringVar(value="ask")
        choice = ttk.Combobox(self.advanced, textvariable=self.choice, values=list(gs.CHOICES), state="readonly",
                              width=7)
        choice.pack(side="left", padx=4)
        choice.bind("<<ComboboxSelected>>", lambda e: self.set_choice())
        WrapLabel(self.advanced, style="Hint.TLabel",
                  text="ask: the SELECT A GUARDIAN STAR box (the disc's); first: always the first star; best: the "
                       "star that does best against the opponent's face-up monsters. A card with one star (the "
                       "second none, or the same) never asks.").pack(side="left", fill="x", expand=True)
        self.status = WrapLabel(self, style="Warning.TLabel")
        self.status.pack(fill="x", pady=(6, 0))

    # --- the model and the project ---------------------------------------------

    def refresh(self):
        if self.project is None:
            return
        self.model = gs.read(self.project.other.get("guardian_stars"))
        self.icon_images = {}
        self.default.set("" if self.model.default_bonus is None else str(self.model.default_bonus))
        self.choice.set(self.model.choice or "ask")
        self.cell = None
        self.fill()
        # A star picked, so its name and icon show (an empty form, else).
        star = self.selected_star if self.tree.exists(str(self.selected_star or 0)) else 1
        if self.tree.exists(str(star)):
            self.tree.selection_set(str(star))
            self._pick_star()

    def commit(self):
        if self.project is None:
            return True
        before = self.project.other.get("guardian_stars")
        after = self.model.build()
        # Untouched, a section as the mod wrote it ("beats", "mirror", stars by
        # name) stays so: every tab switch commits, and it would otherwise be
        # rewritten as the model's matchups and the mod marked changed.
        if after == gs.read(before).build():
            after = before
        if after is None:
            self.project.other.pop("guardian_stars", None)
        else:
            self.project.other["guardian_stars"] = after
        if after != before:
            self.app.changed()
        self._report()
        return True

    def _default(self) -> int:
        return gs.RETAIL_BONUS if self.model.default_bonus is None else self.model.default_bonus

    def _card_stars(self) -> dict:
        counts = {}
        for card in self.project.cards.values():
            if card.is_monster():
                for star in (card.star1, card.star2):
                    counts[star] = counts.get(star, 0) + 1
        return counts

    def _report(self):
        problems = gs.check(self.project.other.get("guardian_stars"), card_stars=self._card_stars()) \
            if self.project else []
        self.status.configure(text="\n".join(f"{level}: {where}: {message}" for level, where, message in problems))

    # --- the list -------------------------------------------------------------------

    def fill(self):
        chosen = self.selected_star
        self.tree.delete(*self.tree.get_children())
        counts = self._card_stars() if self.project else {}
        for star in range(1, self.model.count + 1):
            entry = self.model.stars.get(star)
            tags = ("added",) if star > gs.RETAIL_COUNT else ("changed",) if entry else ()
            self.tree.insert("", "end", iid=str(star), tags=tags,
                             values=(star, self.model.name(star), "mod's" if entry and entry.icon else
                                     ("game's" if star <= gs.RETAIL_COUNT else "plain"), counts.get(star, 0)))
        if chosen and self.tree.exists(str(chosen)):
            self.tree.selection_set(str(chosen))
        self.draw()
        self._report()

    def _pick_star(self):
        chosen = self.tree.selection()
        if not chosen:
            return
        self.selected_star = int(chosen[0])
        entry = self.model.stars.get(self.selected_star)
        name = entry.name if entry else None
        self.name.set(name if isinstance(name, str) else gs.display_name(name, self.selected_star))
        self.names.set(_names_text(name))
        self.palette.set(entry.palette if entry and entry.palette else "game")
        self._show_icon()
        # A disc star is not removed, only given back its disc name and icon.
        self.remove_button.configure(text="Reset" if self.selected_star <= gs.RETAIL_COUNT else "Remove")

    def _star_entry(self, star: int) -> gs.Star:
        return self.model.stars.setdefault(star, gs.Star(star))

    def _tidy(self, star: int):
        """A disc star the mod says nothing of any more is not declared."""
        entry = self.model.stars.get(star)
        if entry and star <= gs.RETAIL_COUNT and entry.name in (None, "", {}) and not entry.icon and \
                not entry.palette and not entry.extra:
            del self.model.stars[star]

    def set_name(self):
        star = self.selected_star
        if not star:
            return
        text = self.name.get().strip()
        names = _parse_names(self.names.get())
        default = gs.display_name(None, star)
        if names:
            if text:
                names["default"] = text
            name = names
        else:
            name = text if text and text != default else None
        entry = self.model.stars.get(star)
        if (entry.name if entry else None) == name:
            return
        if name is None and star > gs.RETAIL_COUNT:
            self._star_entry(star).name = None
        elif name is not None or entry:
            self._star_entry(star).name = name
        self._tidy(star)
        self.fill()
        self.commit()

    def set_palette(self):
        star = self.selected_star
        if not star:
            return
        value = self.palette.get()
        entry = self._star_entry(star)
        entry.palette = None if value == "game" else value
        self._tidy(star)
        self.commit()

    def add_star(self):
        star = self.model.add_star()
        if not star:
            messagebox.showinfo("Guardian Stars", "All 15 stars are there: a card holds its stars in 4 bits, so "
                                "a sixteenth would need a wider card record.", parent=self)
            return
        self.selected_star = star
        self.fill()
        self.tree.selection_set(str(star))
        self.commit()

    def remove_star(self):
        star = self.selected_star
        if not star or star not in self.model.stars:
            return
        in_use = self._card_stars().get(star, 0)
        if star > gs.RETAIL_COUNT and in_use and not messagebox.askokcancel(
                "Guardian Stars", f"{in_use} card stars are {self.model.name(star)}; they keep the number {star}, "
                "which the game then warns about. Remove it?", parent=self):
            return
        if self.model.stars[star].icon:
            self.project.files.pop(self.model.stars[star].icon, None)
        self.model.remove_star(star)
        self.icon_images.pop(star, None)
        if self.cell and not all(self._exists(s) for s in self.cell):
            self.cell = None            # its row or column is gone with the star
            self.value.set("")
        self.fill()
        self.commit()

    # --- icons ------------------------------------------------------------------------

    def _icon_image(self, star: int):
        """The mod's icon for a star as a pngio.Image, or None."""
        entry = self.model.stars.get(star)
        if not entry or not entry.icon:
            return None
        if star in self.icon_images:
            return self.icon_images[star]
        image = None
        try:
            if entry.icon in self.project.files:
                image = pngio.decode(self.project.files[entry.icon])
            elif self.project.source_dir:
                image = pngio.read(Path(self.project.source_dir) / entry.icon)
        except (OSError, pngio.PngError, ValueError):
            image = None
        self.icon_images[star] = image
        return image

    def _photo(self, image, side: int):
        image = pngio.resample(image, side, side) if (image.width, image.height) != (side, side) else image
        return tk.PhotoImage(master=self, data=pngio.ppm(image, color_tuple(self)), format="PPM")

    def _show_icon(self):
        star = self.selected_star
        image = self._icon_image(star) if star else None
        if image is None:
            self.icon_label.configure(image="", text="game's" if star and star <= gs.RETAIL_COUNT else "no icon",
                                      width=8)
            return
        photo = self._photo(pngio.resample(image, 16, 16), 16)
        photo = photo.zoom(ICON_ZOOM, ICON_ZOOM)
        self.photos["preview"] = photo
        self.icon_label.configure(image=photo, text="")

    def use_icon(self, star: int, path) -> bool:
        """The PNG at `path` as `star`'s icon (the import without the dialog)."""
        data = Path(path).read_bytes()
        pngio.decode(data)          # a PNG it can read, or PngError
        name = f"icons/star-{star}.png"
        self.project.files[name] = data
        entry = self._star_entry(star)
        entry.icon = name
        self.icon_images.pop(star, None)
        self.fill()
        self._show_icon()
        self.commit()
        return True

    def import_icon(self):
        star = self.selected_star
        if not star:
            return
        path = file_dialogs.askopenfilename(parent=self, title="A guardian star's icon",
                                            filetypes=[("PNG images", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.use_icon(star, path)
        except (OSError, pngio.PngError, ValueError) as problem:
            messagebox.showerror("Guardian Stars", f"Could not read {path}: {problem}", parent=self)

    def remove_icon(self):
        star = self.selected_star
        entry = self.model.stars.get(star) if star else None
        if not entry or not entry.icon:
            return
        self.project.files.pop(entry.icon, None)
        entry.icon = None
        self.icon_images.pop(star, None)
        self._tidy(star)
        self.fill()
        self._show_icon()
        self.commit()

    # --- the grid ---------------------------------------------------------------------

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        n = self.model.count
        cell, head = px(self, CELL), px(self, HEAD)
        canvas.configure(width=head + cell * n + 1, height=head + cell * n + 1, background=color(self, "zero"))
        ink, line = color(self, "ink"), color(self, "line")
        for star in range(1, n + 1):
            x = head + cell * (star - 1)
            y = head + cell * (star - 1)
            name = self.model.name(star)
            short = name if len(name) <= 9 else name[:8] + "."
            canvas.create_rectangle(x, 0, x + cell, head, fill=color(self, "head"), outline=line)
            canvas.create_text(x + cell // 2, head - 4, text=short, fill=ink, anchor="w", angle=90)
            canvas.create_rectangle(0, y, head, y + cell, fill=color(self, "head"), outline=line)
            canvas.create_text(4, y + cell // 2, text=f"{star} {short}", fill=ink, anchor="w")
        for a in range(1, n + 1):
            for d in range(1, n + 1):
                value = self.model.grid[a][d]
                x, y = head + cell * (d - 1), head + cell * (a - 1)
                fill = color(self, "plus" if value > 0 else "minus" if value < 0 else "zero")
                canvas.create_rectangle(x, y, x + cell, y + cell, fill=fill, outline=line)
                if value:
                    changed = value != gs.retail_matchup(a, d)
                    canvas.create_text(x + cell // 2, y + cell // 2, text=_signed(value), fill=ink,
                                       font=ui_font(9, "bold" if changed else "normal"))
        if self.cell:
            a, d = self.cell
            x, y = head + cell * (d - 1), head + cell * (a - 1)
            canvas.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1, outline=color(self, "pick"), width=3)

    def _click(self, event):
        cell, head = px(self, CELL), px(self, HEAD)
        if event.x < head or event.y < head:
            return
        d, a = (event.x - head) // cell + 1, (event.y - head) // cell + 1
        if not (1 <= a <= self.model.count and 1 <= d <= self.model.count):
            return
        self.pick_cell(a, d)

    def pick_cell(self, a: int, d: int):
        self.cell = (a, d)
        self.cell_label.configure(text=f"{self.model.name(a)} attacking {self.model.name(d)}:")
        self.value.set(str(self.model.grid[a][d]))
        self.draw()

    def _exists(self, star) -> bool:
        """A star the grid shows: a disc star, one the mod declares, or a gap
        below the last declared (its matchups are written like any star's)."""
        return 1 <= star <= self.model.count

    def set_cell(self, value=None):
        if not self.cell or not all(self._exists(s) for s in self.cell):
            return
        if value is None:
            try:
                value = int(self.value.get().strip())
            except ValueError:
                self.status.configure(text=f"A bonus is a whole number, -{gs.BONUS_MAX} to {gs.BONUS_MAX}")
                return
        if not -gs.BONUS_MAX <= value <= gs.BONUS_MAX:
            self.status.configure(text=f"A bonus is a whole number, -{gs.BONUS_MAX} to {gs.BONUS_MAX}")
            return
        a, d = self.cell
        self.model.grid[a][d] = value
        if self.mirror.get() and a != d:
            self.model.grid[d][a] = -value
        self.value.set(str(value))
        self.draw()
        self.commit()

    # --- the whole table ------------------------------------------------------------

    def set_default(self):
        text = self.default.get().strip()
        try:
            value = int(text) if text else None
        except ValueError:
            self.status.configure(text="The default bonus is a whole number")
            return
        if value is not None and not -gs.BONUS_MAX <= value <= gs.BONUS_MAX:
            self.status.configure(text=f"The default bonus is -{gs.BONUS_MAX} to {gs.BONUS_MAX}")
            return
        if value == gs.RETAIL_BONUS:
            value = None
        if value == self.model.default_bonus:
            return
        self.model.set_default(value)
        self.draw()
        self.commit()

    def set_choice(self):
        self.model.choice = None if self.choice.get() == "ask" else self.choice.get()
        self.commit()

    def preset_retail(self):
        self.model.preset_retail()
        self.draw()
        self.commit()

    def preset_clear(self):
        self.model.preset_clear()
        self.draw()
        self.commit()

    def revert(self):
        if self.project is None or not messagebox.askokcancel(
                "Guardian Stars", "Put every star, name, icon and matchup back as the disc has them?", parent=self):
            return
        for entry in self.model.stars.values():
            if entry.icon:
                self.project.files.pop(entry.icon, None)
        self.project.other.pop("guardian_stars", None)
        self.app.changed()
        self.refresh()

    def open_rules(self):
        if self.project is None:
            return None
        from .star_rules_dialog import StarRulesDialog
        return StarRulesDialog(self)

    def _show_advanced(self):
        if self.advanced_shown.get():
            self.advanced.pack(fill="x", pady=(4, 0), before=self.status)
            self.advanced_star.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        else:
            self.advanced.pack_forget()
            self.advanced_star.grid_remove()


def color_tuple(widget):
    """The icon preview's background, the tab's own."""
    hex_color = color(widget, "zero").lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
