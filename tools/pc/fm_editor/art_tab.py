"""The Art tab: a card's picture, thumbnail and name plate as the disc has
them, beside the mod's own and how the game draws them (art.py)."""
from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import art, file_dialogs, pngio, settings
from .tabs import Tab, type_label
from .widgets import card_matches, px, scrolled_tree, ui_font

# Each part shown at a zoom of its size on the disc (times ArtTab.k, as
# room allows), and the internal resolution its third view draws.
ZOOM = {"art": 2, "thumbnail": 4, "title": 2}
INTERNAL = {"art": 2, "thumbnail": 4}
MOST = 4        # ArtTab.k, at most
STEP = 8        # ArtTab.k in eighths: a window a little bigger draws nothing again
# What the View switch shows: the disc's, the game's at the console's
# resolution, or at Internal 2x (the picture) and 4x (the thumbnail; the
# name plate has none, so the game's 1x).
VIEWS = (("disc", "Disc"), ("game", "In game"), ("internal", "Internal 2x/4x"))


def photo(master, image: pngio.Image, width: int, height: int):
    """A Tk image of `image` at width x height (nearest)."""
    return tk.PhotoImage(master=master, data=pngio.ppm(pngio.scale_to(image, width, height)), format="PPM")


def say(label, text):
    """A label under a part's source line, shown only with text."""
    label.configure(text=text)
    if text and not label.winfo_manager():
        label.pack(anchor="w", pady=(2, 0), before=label.master.buttons)
    elif not text and label.winfo_manager():
        label.pack_forget()


class ArtTab(Tab):
    FILTERS = ["All cards", "Art of the mod", "Added by the mod"]

    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Art")
        self.current = None
        self.photos = {}
        self.k = 1.0            # the pictures' zoom over ZOOM, grown to the room the tab has (fit())
        self.fit_job = None
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search, width=20)     # Ctrl+F
        self.search_entry.pack(side="left", padx=4)
        self.filter = tk.StringVar(value=self.FILTERS[0])
        ttk.Combobox(top, textvariable=self.filter, values=self.FILTERS, state="readonly", width=16).pack(side="left")
        self.search.trace_add("write", lambda *_: self.fill())
        self.filter.trace_add("write", lambda *_: self.fill())
        frame, self.tree = scrolled_tree(left, [("id", "#"), ("name", "Name"), ("type", "Type"), ("state", "Art")],
                                         [50, 200, 100, 110], 28, sort_numeric=("id",))
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())
        self.count = ttk.Label(left, style="Hint.TLabel")
        self.count.pack(anchor="w")

        right = self.right = ttk.Frame(self, padding=(10, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        self.heading = ttk.Label(right, font=ui_font(11))
        self.heading.pack(anchor="w")
        self.how = ttk.Label(right, style="Note.TLabel", wraplength=px(right, 720), justify="left")
        self.how.pack(anchor="w", pady=(0, 4))
        # One picture a part, in the view chosen here; a part the mod changes
        # shows the disc's beside it (before, after). Three of each, most
        # alike, took most of the tab and said little.
        switch = ttk.Frame(right)
        switch.pack(anchor="w", pady=(0, 4))
        ttk.Label(switch, text="View").pack(side="left", padx=(0, 6))
        chosen = settings.load().get("art_view")
        self.view = tk.StringVar(value=chosen if chosen in dict(VIEWS) else "game")
        for value, text in VIEWS:
            ttk.Radiobutton(switch, text=text, value=value, variable=self.view, style="Segment.Toolbutton",
                            command=self.view_changed).pack(side="left")
        self.rows = {}
        # The parts' boxes, stacked or the two small ones side by side under
        # the picture, whichever lets the pictures be bigger (fit()).
        self.parts = ttk.Frame(right)
        self.parts.pack(fill="x")
        self.parts.columnconfigure(1, weight=1)
        self.side_by_side = False
        for part in art.PARTS:
            w, h = art.SIZES[part]
            box = ttk.LabelFrame(self.parts, text=f"{art.LABELS[part]}  ({w}x{h} on the disc)", padding=6)
            # At the top: beside the taller buttons the name plate's sat
            # lower than the pictures above it.
            views = ttk.Frame(box)
            views.pack(side="left", anchor="n")
            labels, captions = [], []
            for column in range(2):         # the view; the disc's beside it when they differ
                caption = ttk.Label(views, style="Note.TLabel")
                caption.grid(row=0, column=column, padx=4)
                label = ttk.Label(views, relief="sunken", cursor="hand2")
                label.grid(row=1, column=column, padx=4, sticky="n")
                label.bind("<Double-1>", lambda e, p=part: self.import_png(p))
                labels.append(label)
                captions.append(caption)
            side = ttk.Frame(box, padding=(10, 0, 0, 0))
            side.pack(side="left", fill="both", expand=True, anchor="n")
            source = ttk.Label(side, font=ui_font(10))
            source.pack(anchor="w")
            # Packed only while they say something (say()): an empty label
            # still takes a line.
            info = ttk.Label(side, wraplength=px(side, 330), justify="left")
            where = ttk.Label(side, style="Hint.TLabel", wraplength=px(side, 330), justify="left")
            # Two rows of two: in one row the last were cut off beside three
            # pictures at 1440 wide, or at 125-150% on a 1080p screen. What
            # changes the mod above, what writes a file below.
            buttons = ttk.Frame(side)
            buttons.pack(anchor="w", pady=(6, 0))
            side.buttons = buttons
            ttk.Button(buttons, text="Import PNG...", command=lambda p=part: self.import_png(p)).grid(
                row=0, column=0, sticky="we")
            revert = ttk.Button(buttons, text="Revert to disc", command=lambda p=part: self.revert(p))
            revert.grid(row=0, column=1, sticky="we", padx=(4, 0))
            ttk.Button(buttons, text="Export disc's...", command=lambda p=part: self.export_png(p, False)).grid(
                row=1, column=0, sticky="we", pady=(4, 0))
            export_mod = ttk.Button(buttons, text="Export mod's...", command=lambda p=part: self.export_png(p, True))
            export_mod.grid(row=1, column=1, sticky="we", padx=(4, 0), pady=(4, 0))
            self.rows[part] = {"labels": labels, "captions": captions, "shown": 1, "source": source, "info": info, "where": where,
                               "export": export_mod, "revert": revert, "views": views, "side": side,
                               "box": box}
        self.arrange(False)
        self.tip = ttk.Label(right, style="Hint.TLabel", text="Double-click a picture to import a PNG for it.")
        self.tip.pack(anchor="w", pady=(2, 0))
        self.status = ttk.Label(right, style="Warning.TLabel", wraplength=px(right, 720), justify="left")
        self.status.pack(anchor="w", pady=4)
        # The long lines wrap at the room the page has (room()), not at the
        # column's own width: a label asks for its wrap length, so wrapped at
        # what the column had, it never let it narrow again (a window
        # restored from maximized scrolled sideways).
        for label in (self.how, self.status):
            label.configure(wraplength=px(right, 480))
        # The pictures grow with the room: the window's, the page's.
        self.page.canvas.bind("<Configure>", lambda e: self.fit_later(), add=True)
        self.fill()

    def fit_later(self):
        # On the window: its destroy() cancels what is still waiting.
        if self.fit_job is None:
            self.fit_job = self.app.after(100, self.fit)

    def fit(self):
        """The biggest zoom (k, in eighths) at which the pictures fit the
        page beside the list, the buttons and the text, so they take the
        same share of it at any window size (in whole steps, a window short
        of the next step kept them small): shown again when it changed."""
        self.fit_job = None
        if self.current is None or not self.photos:
            return
        page = self.page.canvas
        width = self.room()
        height = page.winfo_height() - px(self, 12)
        if width <= 1 or height <= 1:
            return
        # Less the right side's own left padding (10, as made): wrapped at
        # the whole room, the text asked a pixel more than the page had and
        # the bottom scrollbar showed.
        for label in (self.how, self.status):
            label.configure(wraplength=max(px(self, 300), width - 10 - px(self, 4)))
        rows = self.rows
        gap = px(self, 6)           # between two boxes, across or down (arrange())
        metrics = {}
        for part in art.PARTS:
            box, views, side = rows[part]["box"], rows[part]["views"], rows[part]["side"]
            tall_now = max(views.winfo_reqheight(), side.winfo_reqheight())
            metrics[part] = {
                "frame": box.winfo_reqheight() - tall_now,              # the box's own frame and title
                "captions": views.winfo_reqheight() - self.part_height(part),
                "side": side.winfo_reqheight(),                         # the source line, the buttons
                "across": box.winfo_reqwidth() - self.part_width(part),  # all but the pictures
            }
        other = self.right.winfo_reqheight() - self.parts.winfo_reqheight()

        def box_height(part, k):
            m = metrics[part]
            return m["frame"] + max(m["captions"] + round(art.SIZES[part][1] * ZOOM[part] * k), m["side"])

        def box_width(part, k):
            return metrics[part]["across"] + rows[part]["shown"] * round(art.SIZES[part][0] * ZOOM[part] * k)

        def fits(k, side_by_side):
            if side_by_side:
                wide = max(box_width("art", k), box_width("thumbnail", k) + gap + box_width("title", k))
                tall = box_height("art", k) + max(box_height("thumbnail", k), box_height("title", k)) + 2 * gap
            else:
                wide = max(box_width(part, k) for part in art.PARTS)
                tall = sum(box_height(part, k) for part in art.PARTS) + 3 * gap
            return wide <= width - self.parts.winfo_x() and other + tall <= height   # less the column's padding

        def biggest(side_by_side):
            k = MOST
            while k > 1.0 and not fits(k, side_by_side):
                k -= 1 / STEP
            return k

        stacked, beside = biggest(False), biggest(True)
        side_by_side = beside > stacked
        k = beside if side_by_side else stacked
        if side_by_side != self.side_by_side:
            self.arrange(side_by_side)
        if k != self.k:
            self.k = k
            self.show(self.current, keep_status=True)

    def arrange(self, side_by_side):
        """The boxes stacked, or the thumbnail's and the name plate's side by
        side under the picture's."""
        self.side_by_side = side_by_side
        gap = px(self, 6)
        art_box, thumb, plate = (self.rows[part]["box"] for part in art.PARTS)
        art_box.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, gap))
        if side_by_side:
            thumb.grid(row=1, column=0, columnspan=1, sticky="nwe", pady=(0, gap), padx=(0, gap))
            plate.grid(row=1, column=1, columnspan=1, sticky="nwe", pady=(0, gap))
        else:
            thumb.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, gap), padx=0)
            plate.grid(row=2, column=0, columnspan=2, sticky="we", pady=(0, gap))

    def view_changed(self):
        """The View switch: every part again, remembered for the next start."""
        settings.save("art_view", self.view.get())
        if self.current is not None:
            self.show(self.current, keep_status=True)

    def room(self):
        """How wide the right side may be: the page less the list beside it."""
        page = self.page.canvas
        return page.winfo_width() - (self.right.winfo_rootx() - page.winfo_rootx()) - px(self, 8)

    def part_width(self, part):
        """The width of the part's pictures shown now, side by side."""
        return sum(image.width() for (p, _), image in self.photos.items() if p == part)

    def part_height(self, part):
        """The height of the part's tallest picture shown now."""
        heights = [image.height() for (p, _), image in self.photos.items() if p == part]
        return max(heights, default=0)

    def rescaled(self):
        """View > Interface size changed: the captions grew, the room too.
        Fitted now, laid out (zoom.Zoom.apply), not a moment after."""
        self.fit()

    @property
    def wa(self):
        files = self.app.files
        return files.wa if files is not None else None

    # the list
    def wanted(self, cid) -> bool:
        f = self.filter.get()
        if f == "Art of the mod" and cid not in art.changed_cards(self.project):
            return False
        if f == "Added by the mod" and cid not in self.project.added:
            return False
        return card_matches(self.project, cid, self.search.get())

    def row(self, cid):
        card = self.project.cards[cid]
        st = art.state(self.project)
        parts = [art.LABELS[p].split()[-1].lower() for p in art.PARTS if (cid, p) in st.images]
        state = ", ".join(parts)
        return (cid, card.name, type_label(card.type), state), ("changed",) if state else ()

    def fill(self):
        if not hasattr(self, "tree") or self.project is None:
            return
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for cid in sorted(self.project.cards):
            if self.wanted(cid):
                values, tags = self.row(cid)
                self.tree.insert("", "end", iid=str(cid), values=values, tags=tags)
                shown += 1
        self.tree.sorting.apply()       # the order a heading chose
        total = len(self.project.cards)
        self.count.configure(text=f"{total} cards" if shown == total else f"{shown} of {total} cards")
        if self.current in self.project.cards and self.tree.exists(str(self.current)):
            self.tree.selection_set(str(self.current))
            self.tree.see(str(self.current))

    def refresh(self):
        self.current = None
        self.fill()
        self.show(None)
        rows = self.tree.get_children()
        if rows:                        # the first card: never an empty tab
            chosen = self.app.current_card   # not one the modder chose: nothing follows it
            self.tree.selection_set(rows[0])
            self.show(int(rows[0]))
            self.app.current_card = chosen

    def select(self):
        selection = self.tree.selection()
        cid = int(selection[0]) if selection else None
        if cid != self.current:
            self.show(cid)

    def show_card(self, cid):
        """Select the card, in the list as it is filtered if it is there."""
        if not self.tree.exists(str(cid)):
            self.goto(cid)
            return
        self.tree.selection_set(str(cid))
        self.tree.see(str(cid))
        self.select()

    def follow(self, cid):
        if cid != self.current and cid in self.project.cards:
            self.show_card(cid)

    def goto(self, cid):
        self.search.set("")
        self.filter.set(self.FILTERS[0])
        self.fill()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))
            self.show(cid)

    # the card
    def show(self, cid, keep_status=False):
        self.current = cid
        if not keep_status:
            self.status.configure(text="")
        self.photos = {}
        if cid is None or self.project is None or cid not in self.project.cards or self.wa is None:
            self.heading.configure(text="Choose a card" if self.wa is not None or self.project is None
                                   else "The Art tab needs the game files (File > Game files...)")
            self.how.configure(text="")
            for row in self.rows.values():
                for label, caption in zip(row["labels"], row["captions"]):
                    label.configure(image="")
                    caption.configure(text="")
                row["source"].configure(text="")
                say(row["info"], "")
                say(row["where"], "")
                for button in row["side"].buttons.winfo_children():     # no card: nothing to import or export
                    button.state(["disabled"])
            return
        for row in self.rows.values():
            for button in row["side"].buttons.winfo_children():
                button.state(["!disabled"])     # Revert and Export mod's follow below, by what the mod owns
        project = self.project
        self.app.current_card = cid
        base = project.base_of(cid)
        self.heading.configure(text=project.card_label(cid) + (f"  (a copy of {project.card_label(base)})"
                                                              if base != cid else ""))
        if cid in project.added:
            how = ("A card the mod adds keeps its picture and thumbnail in its mod.json entry (\"art\", "
                   "\"thumbnail\"): any size up to 4x; Internal 2x and 4x draw its own detail. Without a "
                   "thumbnail, the game cuts one from the picture; without either, it shows its base's. "
                   "Restart the game after a change.")
        else:
            how = ("A retail card's picture and thumbnail go in the mod's texture pack (\"textures\"): any size "
                   "up to 4x; the console's resolution averages it down, Internal 2x and 4x draw its own "
                   "detail. A copy of this card without art of its own shows it too.")
        self.how.configure(text=how + " The name plate is the entry's \"title\" PNG (dark ink on white).")
        for part in art.PARTS:
            self.show_part(cid, part)
        self.fit_later()

    def show_part(self, cid, part):
        project, wa, row = self.project, self.wa, self.rows[part]
        w, h = art.SIZES[part]
        size = (round(w * ZOOM[part] * self.k), round(h * ZOOM[part] * self.k))   # every view as big
        base = project.base_of(cid)
        views = []
        try:
            disc = art.disc_image(wa, base, part)
            if part == "title":
                disc = art.plate_image(art.disc_plate_inks(wa, base), background=art.GOLD)
            game = art.in_game(project, wa, cid, part, 1)
            view = self.view.get()
            if view == "disc" or game is None:
                chosen = (disc, "Disc")
            elif view == "internal" and part in INTERNAL:
                chosen = (art.in_game(project, wa, cid, part, INTERNAL[part]), f"Internal {INTERNAL[part]}x")
            else:
                chosen = (game, "In game (1x)")
            # The disc's beside it when the game shows something else.
            changed = game is not None and game.rgba != disc.rgba
            views = [(disc, "Disc (before)"), chosen] if changed and chosen[0] is not disc else [chosen]
            _, where = art.shown_image(project, wa, cid, part)
        except (OSError, pngio.PngError, ValueError) as problem:
            views, where = [], str(problem)
        row["shown"] = max(1, len(views))
        for i, (label, caption) in enumerate(zip(row["labels"], row["captions"])):
            image, title = views[i] if i < len(views) else (None, "")
            if image is None:
                label.configure(image="")
                label.grid_remove()
                caption.grid_remove()
                continue
            label.grid()
            caption.grid()
            caption.configure(text=title)
            self.photos[(part, i)] = photo(self, image, *size)
            label.configure(image=self.photos[(part, i)])
        owned = (cid, part) in art.state(project).images
        # Where it comes from at a glance; the details below it.
        if not views:
            source, style = "Cannot be shown", "Warning.TLabel"
        elif owned:
            source, style = "Replaced by the mod", "Changed.TLabel"
        elif where == "the disc":
            source, style = "As on the disc", "Hint.TLabel"
        else:
            source, style = f"The game shows {where}", "TLabel"
        row["source"].configure(text=source, style=style)
        info = art.describe(project, cid, part)
        say(row["info"], "" if info == "As the disc has it." else info)
        say(row["where"], where if not views else "")
        row["export"].state(["!disabled"] if owned else ["disabled"])
        row["revert"].state(["!disabled"] if owned else ["disabled"])

    def update_row(self, cid):
        if self.tree.exists(str(cid)):
            values, tags = self.row(cid)
            self.tree.item(str(cid), values=values, tags=tags)

    # actions
    def import_png(self, part):
        cid = self.current
        if cid is None:
            return
        path = file_dialogs.askopenfilename(parent=self, title=f"{art.LABELS[part]} for {self.project.card_label(cid)}",
                                            filetypes=[("PNG images", "*.png"), ("All files", "*.*")])
        if not path:
            return
        self.use_file(part, path)

    def use_file(self, part, path):
        """Import `path` as the current card's part (the Import button, and
        tests)."""
        cid = self.current
        try:
            image = pngio.read(path)
            before = image.size
            notes = art.set_image(self.project, cid, part, image)
        except (OSError, pngio.PngError, ValueError) as problem:
            messagebox.showerror("FM Editor", f"Could not use {path}: {problem}", parent=self)
            return False
        self.app.changed()
        self.update_row(cid)
        self.show(cid)
        w, h = art.SIZES[part]
        text = f"{Path(path).name} ({before[0]}x{before[1]}) is the {art.LABELS[part].lower()}"
        if notes:
            text += ": " + "; ".join(notes)
        self.status.configure(text=text + ".")
        self.app.say(f"Card {cid}: {art.LABELS[part].lower()} from {Path(path).name}. Save to write it.")
        if any("shape" in n for n in notes):
            messagebox.showwarning("FM Editor", f"The picture is not the {art.LABELS[part].lower()}'s shape "
                                   f"({w}:{h}), so only its middle is kept. Crop it yourself to choose "
                                   "the part.", parent=self)
        return True

    def export_png(self, part, own):
        cid = self.current
        if cid is None:
            return
        project = self.project
        base = project.base_of(cid)
        try:
            if own:
                image = art.replacement_image(project, cid, part)
            elif part == "title":
                image = art.plate_image(art.disc_plate_inks(self.wa, base))
            else:
                image = art.disc_image(self.wa, base, part)
        except (OSError, pngio.PngError, ValueError) as problem:
            messagebox.showerror("FM Editor", str(problem), parent=self)
            return
        if image is None:
            return
        name = re.sub(r"[^a-z0-9]+", "-", project.cards[cid].name.lower()).strip("-")
        suffix = {"art": "", "thumbnail": ".small", "title": ".title"}[part]
        path = file_dialogs.asksaveasfilename(parent=self, defaultextension=".png",
                                              initialfile=f"{cid:04d}-{name}{suffix}.png",
                                              filetypes=[("PNG images", "*.png")])
        if path:
            try:
                pngio.write(path, image)
            except OSError as problem:      # a folder it may not write, a full disk
                messagebox.showerror("FM Editor", f"Could not write {path}: {problem}", parent=self)
                return
            self.app.say(f"Wrote {path}")

    def revert(self, part):
        cid = self.current
        if cid is None:
            return
        art.revert(self.project, cid, part)
        self.app.changed()
        self.update_row(cid)
        self.show(cid)
