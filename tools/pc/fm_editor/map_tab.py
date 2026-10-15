"""The Map tab: the campaign map's sixteen places (campaign_map.py).

What a modder changes here is how the player gets around the map: at each
place, which arrows show, where each leads, which direction takes it and
when it is open (a story flag), what Confirm does, how the camera frames
the place and, in the town, where the Millennium Puzzle marker stands.

The place's screen is the tab's middle, as the game draws it: arrows and
the marker are dragged where they go, the map itself to move the camera
(the wheel zooms, a right drag turns it). The panel beside it edits the
arrow picked on the screen or in its list; the numbers behind all of it
are under Show advanced. All routes shows every place and where its arrows
lead, the world's sites where their cameras look and the town's where the
marker stands."""
from __future__ import annotations

import base64
import copy
import tkinter as tk
from tkinter import messagebox, ttk

from . import campaign_map as cm
from . import file_dialogs, map_art, pngio
from .tabs import Tab
from .widgets import WrapLabel, legend, px, ui_font, ui_scale

ZOOM = 2                 # the screen's scale at the usual interface size
FLAG_MAX = 0x7FF         # an exit's flag: the game reads 11 bits (campaign_map.check)
CONFIRM_SCENE = "Enter this place"
# An exit's condition, as the panel's switch names it: value, words.
CONDITIONS = (("always", "Always"), ("set", "After"), ("clear", "Before"))
EDGE_COLORS = {"always": "#4fc36b", "set": "#f2c04c", "clear": "#6fb1ff"}
ARROW_GLYPHS = {"up": "▲", "down": "▼", "left": "◀", "right": "▶"}
PICKED = "#f2c04c"       # the arrow picked, on the screen
# A new arrow by its direction: the arrow picture (cm.ARROWS) and where on
# the screen, as the disc's world sites have theirs.
NEW_ARROW = {"up": (6, 160, 64), "right": (0, 300, 120), "down": (2, 160, 192), "left": (4, 24, 120)}
CAMERA = ("distance", "heading", "pitch", "target_x", "target_z")
MARKER_KEYS = ("marker_x", "marker_y")
PREVIEW = 4              # a camera being dragged: drawn at a quarter of the pixels, 4x


def photo(master, image: pngio.Image, zoom: int = 1):
    """A Tk image keeping the picture's transparency (a PNG, Tk 8.6)."""
    image = pngio.scale_nearest(image, zoom)
    return tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")


def short(project, index):
    """A place's name as its screen shows it (the one before the coup)."""
    return cm.name(project, index).split(" / ")[0]


# Story flags known by what sets them: 0x47 swaps the town's map for the one
# after Heishin's coup (File_RequestEgyptOverworldPackage).
FLAG_NAMES = {0x47: "the coup"}


def when(e) -> str:
    """When an arrow is open, in words: "always", "after flag 84"..."""
    kind, flag = cm.condition_parts(e.condition)
    if kind == "always":
        return "always"
    return f"{'after' if kind == 'set' else 'before'} {FLAG_NAMES.get(flag, f'flag {flag}')}"


class MapTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Map")
        self.index = 0
        self.zoom = self.wanted_zoom()   # the screen's pixels a game pixel
        self.exit = 0               # the arrow picked (its slot, 0-3)
        self.filling = False
        self.photos = {}
        self.choices = {}           # the arrow pictures of the panel's choice
        self.drag = None
        self.references = {}        # camera -> a picture the player chose (this session only)
        self.backgrounds = {}       # (package, camera, spotlight, size) -> map_view picture, or None

        WrapLabel(self, style="Hint.TLabel",
                  text="The campaign map: where each arrow leads, when it opens, and how each place is framed. "
                       "Pick a place, then drag its arrows, its marker or the map itself.").pack(fill="x", pady=(0, 6))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", height=18)
        self.tree.widths = {"#0": px(left, 196)}
        self.tree.column("#0", width=self.tree.widths["#0"])
        from . import theme
        for tag in theme.TAGS:
            self.tree.tag_configure(tag, foreground=theme.tag_color(self.tree, tag))
        self.tree.tag_configure("group", font=ui_font(10))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        legend(left, ("changed", "changed")).pack(anchor="w", pady=(4, 0))
        ttk.Button(left, text="Revert every place", command=self.reset_all).pack(anchor="w", pady=(4, 0))

        middle = ttk.Frame(body, padding=(8, 0))
        middle.pack(side="left", fill="y")
        top = ttk.Frame(middle)
        top.pack(fill="x")
        self.view = tk.StringVar(value="screen")
        for value, text in (("screen", "This place"), ("overview", "All routes")):
            ttk.Radiobutton(top, text=text, value=value, variable=self.view, style="Segment.Toolbutton",
                            command=self.draw).pack(side="left")
        ttk.Button(top, text="Map pictures...", command=self.show_pictures).pack(side="right")
        # Which of the disc's two maps the pictures are drawn from (the
        # tables are written alike to both).
        self.package = tk.StringVar(value=cm.PACKAGE_LABELS["before"])
        for name, _ in reversed(cm.PACKAGES):
            label = cm.PACKAGE_LABELS[name]
            ttk.Radiobutton(top, text=label[0].upper() + label[1:], value=label, variable=self.package,
                            style="Segment.Toolbutton").pack(side="right", padx=(0, 6) if name == "after" else 0)
        ttk.Label(top, text="Map", style="Hint.TLabel").pack(side="right", padx=(0, 4))
        self.package.trace_add("write", lambda *_: self.draw())
        width, height = self.zoom * cm.SCREEN[0], self.zoom * cm.SCREEN[1]
        self.canvas = tk.Canvas(middle, width=width, height=height, background="#000000", highlightthickness=0)
        self.canvas.pack(pady=4)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Shift-ButtonPress-1>", lambda e: self.press(e, turn=True))
        for button in ("2", "3"):       # the right button (2 on macOS's Tk)
            self.canvas.bind(f"<ButtonPress-{button}>", lambda e: self.press(e, turn=True))
            self.canvas.bind(f"<B{button}-Motion>", self.motion)
            self.canvas.bind(f"<ButtonRelease-{button}>", self.release)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", self.wheel)
        self.canvas.bind("<Button-5>", self.wheel)
        self.caption = ttk.Label(middle, style="Hint.TLabel", wraplength=width, justify="left")
        self.caption.pack(anchor="w")
        self.problems = ttk.Label(middle, style="Warning.TLabel", wraplength=width, justify="left")
        self.problems.pack(anchor="w", pady=(4, 0))

        self.form_frame = ttk.Frame(body)
        self.form_frame.pack(side="left", fill="both", expand=True)
        self.build_form(self.form_frame)
        # Advanced: the camera's numbers, under the picture they make.
        self.camera_frame = ttk.Frame(middle)
        self.camera_fields(self.camera_frame)

    def wanted_zoom(self):
        """2x, more at a bigger View > Interface size (up to 4x)."""
        return max(ZOOM, min(4, round(ZOOM * ui_scale(self) + 0.01)))

    def rescaled(self):
        """View > Interface size changed: the screen and its pictures follow."""
        zoom = self.wanted_zoom()
        if zoom != self.zoom:
            self.zoom = zoom
            self.canvas.configure(width=zoom * cm.SCREEN[0], height=zoom * cm.SCREEN[1])
            for label in (self.caption, self.problems):
                label.configure(wraplength=zoom * cm.SCREEN[0])
            self.photos.clear()
            self.choices.clear()
            self.pictures_version = None
            if self.project is not None and cm.available(self.project):
                self.fill_form()
                self.draw()

    # --- the panel ----------------------------------------------------------------------

    def spin(self, parent, var, low, high, width=6):
        return ttk.Spinbox(parent, from_=low, to=high, textvariable=var, width=width, increment=1)

    def var(self, key, kind=tk.IntVar):
        """A field's variable: the place is stored at each change."""
        v = kind(self)
        v.trace_add("write", lambda *_: self.edited())
        self.vars[key] = v
        return v

    def field(self, box, key, text, row, column, low=-32768, high=32767, width=6):
        """A caption and its number, the caption in the color of a change
        once the number differs from the disc's."""
        caption = ttk.Label(box, text=text)
        caption.grid(row=row, column=column * 2, sticky="w", pady=1)
        self.captions[key] = caption
        spin = self.spin(box, self.var(key), low, high, width)
        spin.grid(row=row, column=column * 2 + 1, sticky="w", padx=(4, 10), pady=1)
        return spin

    def camera_fields(self, box):
        for n, (key, text) in enumerate((("distance", "Distance"), ("heading", "Turn"), ("pitch", "Tilt"),
                                         ("target_x", "Looks at x"), ("target_z", "z"))):
            self.field(box, key, text, 0, n, width=5)

    def build_form(self, parent):
        self.vars = {}
        self.captions = {}
        var, field = self.var, self.field

        self.heading = ttk.Label(parent, font=ui_font(13))
        self.heading.pack(anchor="w")
        self.area = ttk.Label(parent, style="Hint.TLabel")
        self.area.pack(anchor="w")
        # What differs from the disc, each with its own way back.
        self.changes = ttk.Frame(parent)
        self.changes.pack(fill="x", pady=(4, 0))

        head = ttk.Frame(parent)
        head.pack(fill="x", pady=(10, 2))
        ttk.Label(head, text="Arrows", font=ui_font(10)).pack(side="left")
        self.remove_button = ttk.Button(head, text="Remove", command=self.remove_exit)
        self.remove_button.pack(side="right")
        self.add_button = ttk.Button(head, text="+ Add", command=self.add_exit)
        self.add_button.pack(side="right", padx=(0, 4))
        self.exits = ttk.Treeview(parent, columns=("hold", "to", "when"), show="headings", height=4,
                                  selectmode="browse")
        self.exits.widths = {"hold": px(parent, 50), "to": px(parent, 150), "when": px(parent, 110)}
        for key, text in (("hold", "Press"), ("to", "Goes to"), ("when", "Open")):
            self.exits.heading(key, text=text, anchor="w")
            self.exits.column(key, width=self.exits.widths[key], stretch=key == "to", anchor="w")
        from . import theme
        for tag in theme.TAGS:
            self.exits.tag_configure(tag, foreground=theme.tag_color(self.exits, tag))
        self.exits.pack(fill="x")
        self.exits.bind("<<TreeviewSelect>>", lambda e: self.exit_picked())

        # The arrow picked: where it leads, the direction, when, its picture.
        box = self.exit_box = ttk.Frame(parent, padding=(0, 6, 0, 0))
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="Goes to").grid(row=0, column=0, sticky="w", pady=2)
        self.destination = ttk.Combobox(box, textvariable=var("destination", tk.StringVar), state="readonly",
                                        width=24)
        self.destination.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(box, text="Press").grid(row=1, column=0, sticky="w", pady=2)
        pad = ttk.Frame(box)
        pad.grid(row=1, column=1, sticky="w", pady=2)
        for name in ("left", "up", "down", "right"):
            ttk.Checkbutton(pad, text=ARROW_GLYPHS[name], style="Toolbutton", width=2,
                            variable=var(name, tk.BooleanVar)).pack(side="left", padx=(0, 2))
        ttk.Label(box, text="Open").grid(row=2, column=0, sticky="w", pady=2)
        row = ttk.Frame(box)
        row.grid(row=2, column=1, sticky="w", pady=2)
        kind = var("kind", tk.StringVar)
        for value, text in CONDITIONS:
            ttk.Radiobutton(row, text=text, value=value, variable=kind, style="Segment.Toolbutton").pack(side="left")
        self.flag = ttk.Frame(row)
        ttk.Label(self.flag, text="flag").pack(side="left", padx=(0, 4))
        self.spin(self.flag, var("flag"), 0, FLAG_MAX, 4).pack(side="left")
        ttk.Label(box, text="Picture").grid(row=3, column=0, sticky="w", pady=2)
        self.pictures_row = ttk.Frame(box)
        self.pictures_row.grid(row=3, column=1, sticky="w", pady=2)
        self.arrow_var = var("arrow")
        # Advanced: where the arrow stands (dragged on the screen) and how long the walk takes.
        arrow = self.arrow_frame = ttk.Frame(box)
        field(arrow, "x", "x", 0, 0, width=4)
        field(arrow, "y", "y", 0, 1, width=4)
        field(arrow, "steps", "Walk frames", 0, 2, 0, 255, width=4)

        ttk.Label(parent, text="Confirm", font=ui_font(10)).pack(anchor="w", pady=(10, 2))
        self.confirm = ttk.Combobox(parent, textvariable=var("confirm", tk.StringVar), state="readonly", width=28)
        self.confirm.pack(anchor="w")

        self.advanced_shown = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(parent, text="Show advanced", variable=self.advanced_shown,
                        command=self.show_advanced).pack(anchor="w", pady=(10, 0))
        self.advanced = ttk.Frame(parent)
        marker = self.marker_frame = ttk.Frame(self.advanced)
        marker.pack(fill="x", pady=(4, 0))     # a town's only: the world map draws none
        ttk.Label(marker, text="Puzzle marker").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.marker_x = field(marker, "marker_x", "x", 0, 1, width=4)
        self.marker_y = field(marker, "marker_y", "y", 0, 2, width=4)
        self.gate = ttk.Checkbutton(self.advanced, text="Confirm only while arrow 1 is open",
                                    variable=var("gate", tk.BooleanVar))
        self.gate.pack(anchor="w", pady=(4, 0))
        ttk.Button(self.advanced, text="Compare with a screenshot...",
                   command=self.choose_reference).pack(anchor="w", pady=(4, 0))

    def show_advanced(self):
        if self.advanced_shown.get():
            self.advanced.pack(fill="x")
            self.camera_frame.pack(anchor="w", pady=(2, 0), before=self.caption)
            self.arrow_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        else:
            self.advanced.pack_forget()
            self.camera_frame.pack_forget()
            self.arrow_frame.grid_remove()

    def arrow_pictures(self):
        """The eight arrows the map has, as the picture's choice: made again
        when the mod's sprites change."""
        for child in self.pictures_row.winfo_children():
            child.destroy()
        data = self.map.retail
        strips = self.strips()
        for n, name in enumerate(cm.ARROWS):
            found = cm.arrow_image(data, n, strips)
            if found and (n, self.version()) not in self.choices:
                self.choices[(n, self.version())] = photo(self, found[0], max(1, round(ui_scale(self))))
            image = self.choices.get((n, self.version()))
            ttk.Radiobutton(self.pictures_row, value=n, variable=self.arrow_var, style="Toolbutton",
                            image=image or "", text=str(n) if image is None else "").pack(side="left")
        self.pictures_version = (id(self.project), self.version())

    # --- the project ----------------------------------------------------------------------

    @property
    def map(self):
        return cm.state(self.project) if self.project is not None else None

    def refresh(self):
        self.backgrounds = {}
        if getattr(self, "pictures", None) is not None and self.pictures.winfo_exists():
            self.pictures.refresh()
        self.fill_list()
        state = "normal" if self.project is not None and cm.available(self.project) else "disabled"
        self.set_enabled(state == "normal")
        if state == "normal":
            names = [cm.label(self.project, i) for i in range(cm.COUNT)]
            self.confirm.configure(values=[CONFIRM_SCENE] + names[1:])
            self.destination.configure(values=names)
            self.select(min(self.index, cm.COUNT - 1))
        else:
            self.canvas.delete("all")
            self.heading.configure(text="")
            self.area.configure(text="")
            self.exits.delete(*self.exits.get_children())
            self.caption.configure(text="The game files hold no campaign map (the overworld packages of "
                                        "WA_MRG.MRG): choose the retail disc under File > Game files.")

    def set_enabled(self, on: bool):
        def walk(widget):
            for child in widget.winfo_children():
                try:
                    if isinstance(child, ttk.Combobox):
                        child.state(["!disabled", "readonly"] if on else ["disabled"])
                    elif isinstance(child, (ttk.Spinbox, ttk.Checkbutton, ttk.Radiobutton, ttk.Button, ttk.Entry)):
                        child.state(["!disabled"] if on else ["disabled"])
                except tk.TclError:
                    pass
                walk(child)
        walk(self.form_frame)

    def fill_list(self):
        self.tree.delete(*self.tree.get_children())
        if self.project is None or not cm.available(self.project):
            return
        for group, text in (("world", "World map"), ("town", "Town")):
            self.tree.insert("", "end", iid=group, text=text, open=True, tags=("group",))
        for i in range(cm.COUNT):
            self.tree.insert("town" if i >= cm.TOWN_FIRST else "world", "end", iid=str(i),
                             text=short(self.project, i), tags=self.row_tags(i))

    def row_tags(self, index):
        return ("changed",) if cm.changed(self.project, index) else ()

    def update_row(self, index):
        if self.tree.exists(str(index)):
            self.tree.item(str(index), tags=self.row_tags(index))

    def picked(self):
        selection = self.tree.selection()
        if not selection:
            return
        if not selection[0].isdigit():      # a group's row: its first place
            first = self.tree.get_children(selection[0])
            if first:
                self.select(int(first[0]))
            return
        if int(selection[0]) != self.index:
            self.select(int(selection[0]))

    def select(self, index):
        if index != self.index:
            self.exit = 0
        self.index = index
        if self.tree.exists(str(index)) and self.tree.selection() != (str(index),):
            self.tree.selection_set(str(index))
            self.tree.see(str(index))
        self.fill_form()
        self.draw()

    def goto(self, index):
        if isinstance(index, int) and 0 <= index < cm.COUNT:
            self.select(index)

    # --- the panel <-> the place ---------------------------------------------------------------

    def used(self, loc=None):
        loc = loc or self.map.locations[self.index]
        return [n for n, e in enumerate(loc.exits) if e.used]

    def fill_form(self):
        loc = self.map.locations[self.index]
        retail = self.map.retail.locations[self.index]
        used = self.used(loc)
        if self.exit not in used:
            self.exit = used[0] if used else 0
        if getattr(self, "pictures_version", None) != (id(self.project), self.version()):
            self.arrow_pictures()
        self.filling = True
        try:
            town = self.index >= cm.TOWN_FIRST
            self.heading.configure(text=cm.name(self.project, self.index))
            self.area.configure(text=f"{'Town' if town else 'World map'} · place {self.index}")
            for key in CAMERA + MARKER_KEYS:
                self.vars[key].set(getattr(loc, key))
                self.captions[key].configure(style="Changed.TLabel" if getattr(loc, key) != getattr(retail, key)
                                             else "TLabel")
            self.vars["gate"].set(bool(loc.gate))
            self.vars["confirm"].set(self.confirm_text(loc.confirm))
            if town:
                self.marker_frame.pack(fill="x", pady=(4, 0), before=self.gate)
            else:                       # the world map draws no marker: not a box of numbers
                self.marker_frame.pack_forget()
            self.fill_exits(loc)
            e = loc.exits[self.exit]
            self.vars["destination"].set(cm.label(self.project, e.destination) if e.destination < cm.COUNT
                                         else ("" if e.destination == cm.NO_EXIT else str(e.destination)))
            for name, bit in cm.DIRECTIONS:
                self.vars[name].set(bool(e.buttons & bit))
            kind, flag = cm.condition_parts(e.condition)
            self.vars["kind"].set(kind)
            self.vars["flag"].set(flag)
            self.vars["steps"].set(e.steps)
            self.vars["arrow"].set(e.arrow)
            self.vars["x"].set(e.x)
            self.vars["y"].set(e.y)
            other = retail.exits[self.exit]
            for key in ("steps", "x", "y"):
                self.captions[key].configure(style="Changed.TLabel" if getattr(e, key) != getattr(other, key)
                                             else "TLabel")
            if used:
                self.exit_box.pack(fill="x", after=self.exits)
            else:
                self.exit_box.pack_forget()
            self.remove_button.state(["!disabled"] if used else ["disabled"])
            self.flag_shown()
            self.add_button.state(["!disabled"] if len(used) < cm.EXITS else ["disabled"])
            self.fill_changes()
        finally:
            self.filling = False
        self.show_problems()

    def fill_exits(self, loc):
        retail = self.map.retail.locations[self.index]
        self.exits.delete(*self.exits.get_children())
        for n in self.used(loc):
            e = loc.exits[n]
            glyphs = "".join(ARROW_GLYPHS[d] for d in cm.direction_names(e.buttons)) or "—"
            to = short(self.project, e.destination) if e.destination < cm.COUNT else str(e.destination)
            self.exits.insert("", "end", iid=str(n), values=(glyphs, to, when(e)),
                              tags=("changed",) if e != retail.exits[n] else ())
        if self.exits.exists(str(self.exit)) and self.exits.selection() != (str(self.exit),):
            self.exits.selection_set(str(self.exit))

    def flag_shown(self):
        if self.vars["kind"].get() == "always":
            self.flag.pack_forget()
        else:
            self.flag.pack(side="left", padx=(6, 0))

    def parts(self):
        """(name, what puts it back) for each part of the place that differs
        from the disc."""
        loc, retail = self.map.locations[self.index], self.map.retail.locations[self.index]
        out = []
        for n in range(cm.EXITS):
            if loc.exits[n] != retail.exits[n]:
                out.append((f"Arrow {n + 1}", lambda n=n: self.revert_part(exits=[n])))
        if any(getattr(loc, k) != getattr(retail, k) for k in CAMERA):
            out.append(("Camera", lambda: self.revert_part(keys=CAMERA)))
        if any(getattr(loc, k) != getattr(retail, k) for k in MARKER_KEYS):
            out.append(("Marker", lambda: self.revert_part(keys=MARKER_KEYS)))
        if (loc.confirm, loc.gate, loc.pad) != (retail.confirm, retail.gate, retail.pad):
            out.append(("Confirm", lambda: self.revert_part(keys=("confirm", "gate", "pad"))))
        return out

    def fill_changes(self):
        for child in self.changes.winfo_children():
            child.destroy()
        parts = self.parts()
        if not parts:
            ttk.Label(self.changes, text="As in the game", style="Hint.TLabel").pack(side="left")
            return
        ttk.Label(self.changes, text="Changed:", style="Changed.TLabel").pack(side="left")
        for name, revert in parts + ([("All", self.reset_place)] if len(parts) > 1 else []):
            ttk.Button(self.changes, text=f"↺ {name}", style="Toolbutton", command=revert).pack(
                side="left", padx=(4, 0))

    def revert_part(self, keys=(), exits=()):
        loc = self.map.locations[self.index].copy()
        retail = self.map.retail.locations[self.index]
        for key in keys:
            setattr(loc, key, getattr(retail, key))
        for n in exits:
            loc.exits[n] = copy.copy(retail.exits[n])
        self.store(loc)
        self.fill_form()

    def confirm_text(self, value):
        if value == 0:
            return CONFIRM_SCENE
        return cm.label(self.project, value) if value < cm.COUNT else str(value)

    @staticmethod
    def number(var, default=0):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return None

    @staticmethod
    def index_of(text):
        head = str(text).split(":", 1)[0].split(" ", 1)[0]
        return int(head) if head.isdigit() else None

    def exit_picked(self):
        selection = self.exits.selection()
        if selection and int(selection[0]) != self.exit:
            self.exit = int(selection[0])
            self.fill_form()
            self.draw()

    def add_exit(self):
        """An arrow in the first free slot: a direction no other arrow of
        the place takes, its picture and place on the screen, to the first
        place none leads to yet."""
        if self.project is None or not cm.available(self.project):
            return
        loc = self.map.locations[self.index].copy()
        free = [n for n, e in enumerate(loc.exits) if not e.used]
        if not free:
            return
        taken = 0
        for n in self.used(loc):
            taken |= loc.exits[n].buttons
        name = next((d for d, bit in cm.DIRECTIONS if not taken & bit), "up")
        arrow, x, y = NEW_ARROW[name]
        if self.index >= cm.TOWN_FIRST:     # the town's arrows stand beside the marker
            dx, dy = {"up": (0, -24), "right": (24, 0), "down": (0, 24), "left": (-24, 0)}[name]
            x, y = loc.marker_x + dx, loc.marker_y + dy
        leads = {loc.exits[n].destination for n in self.used(loc)} | {self.index}
        group = range(cm.TOWN_FIRST, cm.COUNT) if self.index >= cm.TOWN_FIRST else range(cm.TOWN_FIRST)
        to = next((i for i in group if i not in leads), next(i for i in range(cm.COUNT) if i != self.index))
        e = loc.exits[free[0]]
        e.destination, e.buttons, e.arrow, e.x, e.y, e.condition = to, dict(cm.DIRECTIONS)[name], arrow, x, y, 0
        e.steps = e.steps or 16         # the game's usual length
        self.exit = free[0]
        self.store(loc)
        self.fill_form()

    def remove_exit(self):
        loc = self.map.locations[self.index].copy()
        if not loc.exits[self.exit].used:
            return
        loc.exits[self.exit].destination = cm.NO_EXIT
        self.store(loc)
        self.fill_form()

    def edited(self):
        """A field changed: store the panel in the place, when it reads."""
        if self.filling or self.project is None or not cm.available(self.project):
            return
        loc = self.map.locations[self.index].copy()
        names = {"distance": "Distance", "heading": "Turn", "pitch": "Tilt", "target_x": "Looks at x",
                 "target_z": "Looks at z", "marker_x": "Marker x", "marker_y": "Marker y"}
        for key in CAMERA + MARKER_KEYS:
            value = self.number(self.vars[key])
            if value is None or not -32768 <= value <= 32767:
                return self.refused(f"{names[key]} is a whole number, -32768 to 32767")
            setattr(loc, key, value)
        gate = bool(self.vars["gate"].get())
        loc.gate = (loc.gate or 1) if gate else 0
        confirm = self.vars["confirm"].get()
        loc.confirm = 0 if confirm == CONFIRM_SCENE else (self.index_of(confirm) if self.index_of(confirm) is not None
                                                          else loc.confirm)
        self.flag_shown()
        e = loc.exits[self.exit]
        if e.used:
            picked = self.index_of(self.vars["destination"].get())
            if picked is not None:
                e.destination = picked
            buttons = e.buttons & ~cm.DIRECTION_BITS
            for name, bit in cm.DIRECTIONS:
                if self.vars[name].get():
                    buttons |= bit
            e.buttons = buttons
            flag = self.number(self.vars["flag"])
            # Past 0x7FF the game reads another flag: a warning (the check
            # below the screen), not a refusal; past 0x7FFF it cannot be kept.
            if flag is None or not 0 <= flag <= 0x7FFF:
                return self.refused(f"Arrow {self.exit + 1}'s flag is a whole number, 0 to 32767 (past {FLAG_MAX} "
                                    "the game reads another flag)")
            kind = self.vars["kind"].get()
            e.condition = cm.condition_value(kind if kind in dict(CONDITIONS) else "always", flag)
            for key, name in (("steps", "Walk frames"), ("x", "screen x"), ("y", "y")):
                value = self.number(self.vars[key])
                if value is None:
                    return self.refused(f"Arrow {self.exit + 1}'s {name} is a whole number")
                setattr(e, key, value)
            if not 0 <= e.steps <= 255:
                return self.refused(f"Arrow {self.exit + 1}'s Walk frames is 0 to 255")
            if not -32768 <= e.x <= 32767 or not -32768 <= e.y <= 32767:
                return self.refused(f"Arrow {self.exit + 1}'s screen x and y are -32768 to 32767")
            arrow = self.number(self.vars["arrow"])
            if arrow is not None:
                e.arrow = arrow
        self.problems.configure(style="Warning.TLabel")
        self.store(loc, soon=True)
        self.show_problems()

    def refused(self, why):
        """A field that does not read: nothing of the place is stored until
        it does, and the tab says which (it was silently kept as it was)."""
        self.problems.configure(text=f"Not stored: {why}.", style="Error.TLabel")

    def store(self, loc, soon=False):
        """The place as the panel or a drag has it; `soon`: drawn once the
        typing stops (a camera field drew the 3D model at every key)."""
        if loc == self.map.locations[self.index]:
            return
        self.map.locations[self.index] = loc
        self.update_row(self.index)
        self.app.changed()
        if not self.filling:
            # The list, the marks and the ways back follow (the fields are as typed).
            self.filling = True
            try:
                self.fill_exits(loc)
                self.fill_changes()
                retail = self.map.retail.locations[self.index]
                for key in CAMERA + MARKER_KEYS:
                    self.captions[key].configure(style="Changed.TLabel" if getattr(loc, key) != getattr(retail, key)
                                                 else "TLabel")
                for key in ("steps", "x", "y"):
                    differs = getattr(loc.exits[self.exit], key) != getattr(retail.exits[self.exit], key)
                    self.captions[key].configure(style="Changed.TLabel" if differs else "TLabel")
            finally:
                self.filling = False
        if soon:
            self.draw_soon()
        else:
            self.draw()
        self.show_problems()

    def draw_soon(self):
        # One Tcl command made once (see FusionsTab.fill_soon).
        if getattr(self, "_draw_command", None) is None:
            self._draw_command = self.register(self._draw_due)
        if getattr(self, "_draw_job", None) is not None:
            self.tk.call("after", "cancel", self._draw_job)
        self._draw_job = self.tk.call("after", 150, self._draw_command)

    def _draw_due(self):
        self._draw_job = None
        self.draw()

    def show_problems(self):
        issues = []
        cm.check(self.project, issues)
        mine = [i for i in issues if i.target == self.index]
        self.problems.configure(text="\n".join(f"{i.level}: {i.message}" for i in mine[:6]))

    def reset_place(self):
        if self.project is None or not cm.available(self.project):
            return
        if cm.changed(self.project, self.index):
            cm.reset(self.project, self.index)
            self.app.changed()
            self.update_row(self.index)
            self.fill_form()
            self.draw()

    def reset_all(self):
        if self.project is None or not cm.any_changed(self.project):
            return
        if not messagebox.askyesno("Map", "Put every place back as the disc has it?", parent=self):
            return
        cm.reset_all(self.project)
        self.app.changed()
        self.fill_list()
        self.select(self.index)

    # --- the pictures ---------------------------------------------------------------------------

    def image(self, key, make):
        """A Tk image, made once per key (the sprites) and kept alive."""
        if key not in self.photos:
            made = make()
            self.photos[key] = made
        return self.photos[key]

    def sprite(self, key, found):
        if found is None:
            return None
        image, left, top = found
        return self.image((key, self.version()), lambda: photo(self, image, self.zoom)), left, top

    def version(self):
        return map_art.state(self.project).version

    def strips(self):
        return {p: image for p in map_art.STRIP_PALETTES
                if (image := map_art.strip_override(self.project, p)) is not None}

    def package_name(self):
        return next(name for name, sector in cm.PACKAGES if sector == self.package_sector())

    def overrides(self):
        return map_art.texture_overrides(self.project, self.package_name())

    def camera(self, index):
        loc = self.map.locations[index]
        return loc.distance, loc.heading, loc.pitch, loc.target_x, loc.target_z

    def package_sector(self):
        for name, sector in cm.PACKAGES:
            if cm.PACKAGE_LABELS[name] == self.package.get():
                return sector
        return cm.PACKAGES[0][1]

    def picture(self, key, make):
        """A map_view picture, drawn once; None when the disc's model cannot
        be read (said in the caption)."""
        if key not in self.backgrounds:
            try:
                self.backgrounds[key] = make()
            except Exception as problem:     # a disc whose map the renderer cannot read
                self.backgrounds[key] = None
                self.drawing_problem = f"The map could not be drawn: {problem}"
        return self.backgrounds[key]

    def background(self, index):
        """(image, where it comes from) for the place's screen, or None."""
        from . import map_view
        camera = self.camera(index)
        if camera in self.references:
            return self.references[camera], "your screenshot"
        files = self.app.files
        if files is None:
            return None
        sector = self.package_sector()
        picture = self.picture(("view", sector, camera, index < cm.TOWN_FIRST, self.version()),
                               lambda: map_view.render(map_view.model(files.wa, sector), camera,
                                                       spotlight=index < cm.TOWN_FIRST, overrides=self.overrides()))
        if picture is None:
            return None
        return picture, "drawn from the disc's map model"

    def draw(self):
        if getattr(self, "_draw_job", None) is not None:     # drawn now: the waiting draw is not needed
            self.tk.call("after", "cancel", self._draw_job)
            self._draw_job = None
        self.canvas.delete("all")
        if self.project is not None and getattr(self, "drawn_version", None) != (id(self.project), self.version()):
            self.photos.clear()         # the pictures of another mod, or before an import
            self.drawn_version = (id(self.project), self.version())
            self.pictures_version = None
        if self.project is None or not cm.available(self.project):
            return
        if self.view.get() == "overview":
            self.draw_overview()
        else:
            self.draw_screen()

    def draw_screen(self):
        data = self.map.retail
        loc = self.map.locations[self.index]
        found = self.background(self.index)
        if found is not None:
            picture, where = found
            key = ("bg", id(picture))
            self.canvas.create_image(0, 0, anchor="nw", tags=("bg",), image=self.image(key, lambda: photo(
                self, pngio.resample(picture, *cm.SCREEN) if picture.size != cm.SCREEN else picture, self.zoom)))
        else:
            where = getattr(self, "drawing_problem", "") or "no picture of the map"
            width, height = self.zoom * cm.SCREEN[0], self.zoom * cm.SCREEN[1]
            for x in range(0, width, 40):
                self.canvas.create_line(x, 0, x, height, fill="#1c2430")
            for y in range(0, height, 40):
                self.canvas.create_line(0, y, width, y, fill="#1c2430")
        strips = self.strips()
        panel = self.sprite("panel", cm.sprite_image(data, *cm.PANEL, strips))
        if panel:
            self.canvas.create_image((cm.PANEL_AT[0] + panel[1]) * self.zoom, (cm.PANEL_AT[1] + panel[2]) * self.zoom,
                                     anchor="nw", image=panel[0])
        self.canvas.create_text(160 * self.zoom, 30 * self.zoom, text=short(self.project, self.index),
                                fill="#ffffff", font=ui_font(12))
        labels = {}
        for n, e in enumerate(loc.exits):
            if e.used:
                text = short(self.project, e.destination) if e.destination < cm.COUNT else "?"
                if e.condition:
                    text += f" ({when(e)})"
                labels.setdefault((e.x, e.y), []).append((n, text))
        z = self.zoom
        for n, e in enumerate(loc.exits):
            if not e.used:
                continue
            x, y = e.x * z, e.y * z
            arrow = self.sprite(("arrow", e.arrow), cm.arrow_image(data, e.arrow, strips)) if e.arrow < 8 else None
            tag = ("exit", f"exit{n}", f"arrow{n}")
            if arrow:
                self.canvas.create_image(x + arrow[1] * z, y + arrow[2] * z, anchor="nw", image=arrow[0], tags=tag)
            else:
                self.canvas.create_rectangle(x - 5 * z, y - 5 * z, x + 5 * z, y + 5 * z, outline="#ff5050", tags=tag)
            if n == self.exit:          # the arrow the panel edits
                r = 13 * z
                self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=PICKED, width=2,
                                        tags=("exit", f"exit{n}", "ring"))
            group = labels.get((e.x, e.y), [])
            if not group or group[0][0] != n:
                continue        # one label for the exits that share a place
            text = chr(10).join(t for _, t in group)
            tag = ("exit", "label", f"exit{n}") + tuple(f"exit{m}" for m, _ in group[1:])
            anchor = "e" if e.x > 200 else "w" if e.x < 120 else "n"
            x += (-15 if anchor == "e" else 15 if anchor == "w" else 0) * z
            y += 14 * z if anchor == "n" else 0
            for ox, oy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):     # an outline: readable on any ground
                self.canvas.create_text(x + ox, y + oy, text=text, anchor=anchor, fill="#000000",
                                        font=ui_font(9, "normal"), tags=tag)
            self.canvas.create_text(x, y, text=text, anchor=anchor, fill="#ffffff", font=ui_font(9, "normal"), tags=tag)
        if self.index >= cm.TOWN_FIRST:
            marker = self.sprite("marker", cm.sprite_image(data, *cm.MARKER, strips))
            if marker:
                self.canvas.create_image((loc.marker_x + marker[1]) * z, (loc.marker_y + marker[2]) * z,
                                         anchor="nw", image=marker[0], tags=("marker",))
        self.canvas.tag_raise("label")      # the exits' names over the marker
        text = "Drag an arrow to move it, or the map to move the camera; the wheel zooms, a right drag turns."
        if self.index >= cm.TOWN_FIRST:
            text = "Drag an arrow or the Puzzle marker to move it, or the map to move the camera; the wheel " \
                   "zooms, a right drag turns."
        if where != "drawn from the disc's map model":
            text += f" ({where})"
        self.caption.configure(text=text)

    # --- overview -------------------------------------------------------------------------------

    WORLD_BOX = (0, 40, 440, 480)       # canvas box for the world map, from above
    TOWN_BOX = (448, 40, 640, 184)      # canvas box for the town: its screen at 0.6
    WORLD_CENTRE = (0, 0)               # the terrain spans -1333..1333 on x and z
    WORLD_SPAN = 2800

    def box(self, box):
        """A box of the overview's layout (made for the screen at 2x) at
        the screen's scale."""
        return tuple(v * self.zoom // ZOOM for v in box)

    def world_frame(self):
        x0, y0, x1, y1 = self.box(self.WORLD_BOX)
        scale = min(x1 - x0, y1 - y0) / self.WORLD_SPAN
        return self.WORLD_CENTRE[0], self.WORLD_CENTRE[1], scale, (x0 + x1) / 2, (y0 + y1) / 2

    def node(self, index):
        loc = self.map.locations[index]
        if index < cm.TOWN_FIRST:
            cx, cz, scale, ox, oy = self.world_frame()
            # Turned as the world's cameras mostly look (heading about half a
            # turn): -x up the picture, +z to the right.
            return ox + (loc.target_z - cz) * scale, oy + (loc.target_x - cx) * scale
        x0, y0, x1, y1 = self.box(self.TOWN_BOX)
        return x0 + loc.marker_x * (x1 - x0) / cm.SCREEN[0], y0 + loc.marker_y * (y1 - y0) / cm.SCREEN[1]

    def draw_overview(self):
        from . import map_view
        c = self.canvas
        files = self.app.files
        sector = self.package_sector()
        x0, y0, x1, y1 = self.box(self.WORLD_BOX)
        if files is not None:
            version = self.version()
            top = self.picture(("top", sector, version), lambda: map_view.render_top(
                map_view.model(files.wa, sector), self.WORLD_CENTRE, self.WORLD_SPAN, (x1 - x0, y1 - y0),
                overrides=self.overrides()))
            if top is not None:
                c.create_image(x0, y0, anchor="nw", image=self.image(("top", sector, version),
                                                                     lambda: photo(self, top)))
            town = self.map.locations[cm.TOWN_FIRST]
            if town:
                tx0, ty0, tx1, ty1 = self.box(self.TOWN_BOX)
                camera = self.camera(cm.TOWN_FIRST)
                view = self.picture(("view", sector, camera, False, version), lambda: map_view.render(
                    map_view.model(files.wa, sector), camera, overrides=self.overrides()))
                if view is not None:
                    small = pngio.resample(view, tx1 - tx0, ty1 - ty0)
                    c.create_image(tx0, ty0, anchor="nw", image=self.image(("town", sector, camera, version),
                                                                            lambda: photo(self, small)))
        tx0, ty0, tx1, ty1 = self.box(self.TOWN_BOX)
        c.create_rectangle(tx0, ty0, tx1, ty1, outline="#3b4b5e")
        c.create_text(tx0, ty0 - 4, text="The town", anchor="sw", fill="#c4c8cd", font=ui_font(9, "normal"))
        c.create_text(x0 + 4, y0 - 4, anchor="sw", fill="#c4c8cd", font=ui_font(9, "normal"),
                      text="The world map, from above")
        k = self.zoom / ZOOM
        legend_ = [("always", "always open"), ("set", "after a flag"), ("clear", "before a flag")]
        for n, (kind, text) in enumerate(legend_):
            y = (204 + n * 16) * k
            c.create_line(tx0, y, tx0 + 24 * k, y, fill=EDGE_COLORS[kind], width=2, arrow="last")
            c.create_text(tx0 + 30 * k, y, text=text, anchor="w", fill="#c4c8cd", font=ui_font(9, "normal"))
        c.create_line(tx0, 252 * k, tx0 + 24 * k, 252 * k, fill="#c4c8cd", width=2, arrow="last", dash=(4, 3))
        c.create_text(tx0 + 30 * k, 252 * k, text="Confirm", anchor="w", fill="#c4c8cd", font=ui_font(9, "normal"))
        locations = self.map.locations
        for index in range(cm.COUNT):
            ax, ay = self.node(index)
            for what, destination, condition in cm.edges(locations, index):
                if destination == index or what == "cancel":
                    continue
                bx, by = self.node(destination)
                kind = cm.condition_parts(condition)[0]
                width = 3 if self.index in (index, destination) else 1
                # A little to the side, so a way back does not cover the way there.
                dx, dy = by - ay, ax - bx
                length = max((dx * dx + dy * dy) ** 0.5, 1)
                sx, sy = dx / length * 3, dy / length * 3
                c.create_line(ax + sx, ay + sy, bx + sx, by + sy, fill=EDGE_COLORS[kind], width=width,
                              arrow="last", arrowshape=(10, 12, 4), dash=() if what != "confirm" else (4, 3))
        for index in range(cm.COUNT):
            x, y = self.node(index)
            selected = index == self.index
            fill = PICKED if selected else ("#8ab4f8" if index >= cm.TOWN_FIRST else "#e8eaed")
            c.create_oval(x - 6, y - 6, x + 6, y + 6, fill=fill, outline="#000000", tags=("place", f"place{index}"))
            right = x > (tx0 + tx1) / 2 if index >= cm.TOWN_FIRST else x > (x0 + x1) / 2 + 60
            name = short(self.project, index) if index < cm.TOWN_FIRST else ""
            if index >= cm.TOWN_FIRST:
                c.create_text(tx0, (284 + (index - cm.TOWN_FIRST) * 15) * k, anchor="w", fill="#c4c8cd",
                              font=ui_font(9, "bold" if selected else "normal"),
                              text=f"{index} {short(self.project, index)}")
            for ox, oy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
                c.create_text(x + (-9 if right else 9) + ox, y + oy, text=f"{index} {name}".strip(), fill="#000000",
                              anchor="e" if right else "w", font=ui_font(9, "bold" if selected else "normal"),
                              tags=("place", f"place{index}"))
            c.create_text(x + (-9 if right else 9), y, text=f"{index} {name}".strip(), anchor="e" if right else "w",
                          fill="#ffffff", font=ui_font(9, "bold" if selected else "normal"),
                          tags=("place", f"place{index}"))
        self.caption.configure(text="Every place and where its arrows lead. Click a place to pick it; drag a world "
                                    "site to aim its camera there, a town place to move its marker. (In the town, "
                                    "Cancel leads back to Metropolis once the tournament is over.)")

    # --- the mouse ---------------------------------------------------------------------------------

    def hit(self, event):
        for item in reversed(self.canvas.find_overlapping(event.x - 2, event.y - 2, event.x + 2, event.y + 2)):
            tags = self.canvas.gettags(item)
            if "ring" in tags:
                continue        # the picked arrow's ring: the ground through it
            for tag in tags:
                if tag.startswith("exit") and tag[4:].isdigit():
                    return "exit", int(tag[4:])
                if tag == "marker":
                    return "marker", None
                if tag.startswith("place") and tag[5:].isdigit():
                    return "place", int(tag[5:])
        return None

    def press(self, event, turn=False):
        if getattr(self, "_draw_job", None) is not None:
            self.draw()                 # the screen as the panel has it, before picking what is under the mouse
        if self.project is None or not cm.available(self.project):
            return
        found = None if turn else self.hit(event)
        if found is None and self.view.get() == "screen":
            # The map itself: the camera moves (or turns) with the mouse.
            found = ("turn" if turn else "pan", None)
            self.drag_camera = self.camera(self.index)
        self.drag = (found, event.x, event.y, False) if found else None
        if found and found[0] == "place" and found[1] != self.index:
            self.select(found[1])
            self.drag = (found, event.x, event.y, False)
        if found and found[0] == "exit" and found[1] != self.exit:
            self.exit = found[1]
            self.fill_form()
            self.draw()
            self.drag = (found, event.x, event.y, False)

    def motion(self, event):
        if not self.drag:
            return
        found, x, y, _ = self.drag
        kind, n = found
        if kind in ("pan", "turn"):
            self.drag = (found, x, y, True)
            self.preview(self.dragged_camera(kind, x, y, event.x, event.y))
            return
        tags = {"exit": f"exit{n}", "marker": "marker", "place": f"place{n}"}[kind]
        self.canvas.move(tags, event.x - x, event.y - y)
        self.drag = (found, event.x, event.y, True)

    def release(self, event):
        if not self.drag:
            return
        found, x, y, moved = self.drag
        self.drag = None
        if not moved:
            return
        kind, n = found
        loc = self.map.locations[self.index].copy()
        if kind in ("pan", "turn"):
            camera = self.dragged_camera(kind, x, y, event.x, event.y)
            loc.distance, loc.heading, loc.pitch, loc.target_x, loc.target_z = camera
        elif kind == "exit":
            items = self.canvas.find_withtag(f"arrow{n}")
            left, top = self.canvas.coords(items[0])[:2]
            arrow = cm.arrow_image(self.map.retail, loc.exits[n].arrow, self.strips()) \
                if loc.exits[n].arrow < 8 else None
            ox, oy = (arrow[1], arrow[2]) if arrow else (0, 0)
            if not arrow:
                left, top = left + 5 * self.zoom, top + 5 * self.zoom
            loc.exits[n].x = round(left / self.zoom) - ox
            loc.exits[n].y = round(top / self.zoom) - oy
        elif kind == "marker":
            left, top = self.canvas.coords(self.canvas.find_withtag("marker")[0])[:2]
            marker = cm.sprite_image(self.map.retail, *cm.MARKER, self.strips())
            loc.marker_x = round(left / self.zoom) - marker[1]
            loc.marker_y = round(top / self.zoom) - marker[2]
        elif kind == "place":
            ox, oy = self.node(n)
            items = self.canvas.find_withtag(f"place{n}")
            bx = self.canvas.coords(items[0])
            nx, ny = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
            if n < cm.TOWN_FIRST:
                _, _, scale, _, _ = self.world_frame()
                loc.target_z += round((nx - ox) / scale)
                loc.target_x += round((ny - oy) / scale)
            else:
                x0, y0, x1, y1 = self.box(self.TOWN_BOX)
                loc.marker_x = round((nx - x0) * cm.SCREEN[0] / (x1 - x0))
                loc.marker_y = round((ny - y0) * cm.SCREEN[1] / (y1 - y0))
        self.store(loc)
        self.fill_form()

    # --- the camera, by the mouse ---------------------------------------------------------------------

    @staticmethod
    def ground(camera, x, y):
        """The point of the ground (y 0) the screen shows at x, y (320x240),
        as map_view.render projects; None above the horizon."""
        import math
        from . import map_view
        vp, vr = map_view.eye(camera)
        f = [vr[i] - vp[i] for i in range(3)]
        length = math.sqrt(sum(a * a for a in f)) or 1.0
        f = [a / length for a in f]
        r = [f[2], 0.0, -f[0]]
        length = math.sqrt(r[0] * r[0] + r[2] * r[2])
        r = [a / length for a in r] if length > 1e-9 else [1.0, 0.0, 0.0]
        u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]]
        a, b = (x - 160) / map_view.PROJECTION, (y - 120) / map_view.PROJECTION
        d = [f[i] + a * r[i] + b * u[i] for i in range(3)]
        if abs(d[1]) < 1e-9:
            return None
        t = -vp[1] / d[1]
        if t <= 0:
            return None
        return vp[0] + t * d[0], vp[2] + t * d[2]

    def dragged_camera(self, kind, x0, y0, x1, y1):
        """The camera the press took, moved by the mouse from x0, y0 to x1,
        y1 (canvas pixels): the ground under the mouse stays under it (a
        pan), or the camera turns about what it looks at."""
        distance, heading, pitch, tx, tz = self.drag_camera
        clamp = lambda v: max(-32768, min(32767, round(v)))      # noqa: E731
        if kind == "turn":
            heading = (heading + (x1 - x0) * 4) % 4096
            pitch = max(16, min(1024, pitch + (y1 - y0) * 2))
            return distance, clamp(heading), clamp(pitch), tx, tz
        start = self.ground(self.drag_camera, x0 / self.zoom, y0 / self.zoom)
        now = self.ground(self.drag_camera, x1 / self.zoom, y1 / self.zoom)
        if start is None or now is None:
            return self.drag_camera
        return distance, heading, pitch, clamp(tx + start[0] - now[0]), clamp(tz + start[1] - now[1])

    def preview(self, camera):
        """The map under the screen's arrows as `camera` sees it, drawn small
        (a drag shows each step; the full picture comes on release)."""
        from . import map_view
        files = self.app.files
        if files is None or self.view.get() != "screen":
            return
        try:
            small = map_view.render(map_view.model(files.wa, self.package_sector()), camera,
                                    spotlight=self.index < cm.TOWN_FIRST,
                                    size=(cm.SCREEN[0] * self.zoom // PREVIEW, cm.SCREEN[1] * self.zoom // PREVIEW),
                                    overrides=self.overrides())
        except Exception:       # noqa: BLE001 -- the caption says it when the full picture fails too
            return
        self.photos["preview"] = photo(self, small, PREVIEW)
        self.canvas.delete("bg")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photos["preview"], tags=("bg",))
        self.canvas.tag_lower("bg")

    def wheel(self, event):
        if self.project is None or not cm.available(self.project) or self.view.get() != "screen":
            return "break"
        closer = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
        loc = self.map.locations[self.index].copy()
        loc.distance = max(64, min(32767, round(loc.distance * (0.9 if closer else 1 / 0.9))))
        self.filling = True
        try:
            self.vars["distance"].set(loc.distance)
        finally:
            self.filling = False
        self.preview(self.camera_of(loc))
        self.store(loc, soon=True)
        return "break"

    @staticmethod
    def camera_of(loc):
        return loc.distance, loc.heading, loc.pitch, loc.target_x, loc.target_z

    # --- reference pictures ---------------------------------------------------------------------------

    def choose_reference(self):
        if self.project is None or not cm.available(self.project):
            return
        path = file_dialogs.askopenfilename(parent=self, title="A screenshot of this place in the game",
                                            filetypes=[("PNG", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            picture = pngio.read(path)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Map", f"Could not read {path}: {problem}", parent=self)
            return
        self.references[self.camera(self.index)] = picture
        self.draw()

    # --- the map's pictures (map_art) ------------------------------------------------------------

    def show_pictures(self):
        if self.project is None or not cm.available(self.project):
            return
        if getattr(self, "pictures", None) is None or not self.pictures.winfo_exists():
            self.pictures = MapPictures(self)
        else:
            self.pictures.refresh()
            self.pictures.lift()

    def art_changed(self):
        self.app.changed()
        self.draw()
        if self.project is not None and cm.available(self.project):
            self.fill_form()            # the arrows' pictures, the mod's now


class MapPictures(tk.Toplevel):
    """The map's sprites and terrain textures in the mod's texture pack."""

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.title("Map pictures")
        self.photos = {}
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        sprites = ttk.LabelFrame(body, text="Sprites (the map's strip: name panel, marker, arrows)", padding=6)
        sprites.pack(fill="x")
        self.previews = ttk.Frame(sprites)
        self.previews.pack(anchor="w")
        row = ttk.Frame(sprites)
        row.pack(anchor="w", pady=(6, 0))
        self.sprite = tk.StringVar(value=map_art.SPRITES[0][0])
        ttk.Combobox(row, textvariable=self.sprite, values=[s[0] for s in map_art.SPRITES], state="readonly",
                     width=30).pack(side="left")
        ttk.Button(row, text="Import picture...", command=self.import_sprite).pack(side="left", padx=4)
        row = ttk.Frame(sprites)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Button(row, text="Export sprites...", command=self.export_sprites).pack(side="left")
        ttk.Button(row, text="Import sprites...", command=self.import_sprites).pack(side="left", padx=4)
        ttk.Button(row, text="Revert sprites", command=self.revert_sprites).pack(side="left")
        ttk.Label(sprites, style="Hint.TLabel", wraplength=px(self, 620), justify="left",
                  text="A picture of one sprite goes into every frame of its animation (the marker's 16, an "
                       "arrow's 10), so it keeps its motion; an arrow and its mirror share their cells. Export "
                       "sprites writes the strip through each palette (sprites-p0.png to p3.png, 256x256, or the "
                       "mod's at its size) to paint over; Import sprites takes those files back. Up to 4x: "
                       "Internal 2x and 4x draw the detail, the console's resolution averages it down.").pack(
            anchor="w", pady=(6, 0))
        terrain = ttk.LabelFrame(body, text="Terrain textures", padding=6)
        terrain.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(terrain)
        row.pack(anchor="w")
        ttk.Label(row, text="Map").pack(side="left")
        self.package = tk.StringVar(value=cm.PACKAGE_LABELS["before"])
        box = ttk.Combobox(row, textvariable=self.package, state="readonly", width=16,
                           values=[cm.PACKAGE_LABELS[name] for name, _ in cm.PACKAGES])
        box.pack(side="left", padx=4)
        self.package.trace_add("write", lambda *_: self.refresh())
        self.count = ttk.Label(row)
        self.count.pack(side="left", padx=8)
        row = ttk.Frame(terrain)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Button(row, text="Export textures...", command=self.export_textures).pack(side="left")
        ttk.Button(row, text="Import textures...", command=self.import_textures).pack(side="left", padx=4)
        ttk.Button(row, text="Revert textures", command=self.revert_textures).pack(side="left")
        ttk.Label(terrain, style="Hint.TLabel", wraplength=px(self, 620), justify="left",
                  text="The terrain is a 3D model with tiled textures (most are drawn in many places), so it is "
                       "repainted a texture at a time: Export writes each texture as the map draws it "
                       "(textureNN-PPPP.png, one per palette it is drawn with), Import takes the files of a "
                       "folder with those names. The map before the coup and the one after are two models with "
                       "textures of their own.").pack(anchor="w", pady=(6, 0))
        self.status = ttk.Label(body, style="Note.TLabel", wraplength=px(self, 620), justify="left")
        self.status.pack(anchor="w", pady=(8, 0))
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(8, 0))
        self.refresh()

    @property
    def project(self):
        return self.tab.project

    def package_name(self):
        return next(name for name, _ in cm.PACKAGES if cm.PACKAGE_LABELS[name] == self.package.get())

    def refresh(self):
        if self.project is None or not cm.available(self.project):
            self.destroy()
            return
        for child in self.previews.winfo_children():
            child.destroy()
        self.photos = {}
        data = cm.state(self.project).retail
        strips = {p: image for p in map_art.STRIP_PALETTES
                  if (image := map_art.strip_override(self.project, p)) is not None}
        shown = [("Marker", cm.MARKER), ("Name panel", cm.PANEL)] + \
            [(name, (2, i)) for i, name in enumerate(cm.ARROWS) if name in ("right", "down", "up", "up-right")]
        for column, (label, (animation, variant)) in enumerate(shown):
            found = cm.sprite_image(data, animation, variant, strips)
            if found is None:
                continue
            image = found[0]
            zoom = 1 if image.width > 64 else 2
            self.photos[label] = photo(self, image, zoom)
            ttk.Label(self.previews, text=label, style="Note.TLabel").grid(row=0, column=column, padx=4)
            ttk.Label(self.previews, image=self.photos[label]).grid(row=1, column=column, padx=4)
        st = map_art.state(self.project)
        package = self.package_name()
        total = len(map_art.package_textures(data, package))
        mine = sum(1 for t in st.textures if t.package == package)
        self.count.configure(text=f"{total} textures, {mine} replaced by the mod" if total else
                             "the disc's map model could not be read")

    def done(self, notes, what):
        self.tab.art_changed()
        self.refresh()
        self.status.configure(text=what + ("\n" + "\n".join(notes[:8]) if notes else ""))

    def import_sprite(self, path=None):
        label = self.sprite.get()
        _, animation, variant = next(s for s in map_art.SPRITES if s[0] == label)
        path = path or file_dialogs.askopenfilename(parent=self, title=f"A picture for the {label.lower()}",
                                                    filetypes=[("PNG", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            notes = map_art.set_sprite(self.project, animation, variant, pngio.read(path))
        except (OSError, pngio.PngError, ValueError) as problem:
            messagebox.showerror("Map pictures", f"Could not use {path}: {problem}", parent=self)
            return
        self.done(notes, f"{label}: {path}")

    def export_sprites(self, folder=None):
        folder = folder or file_dialogs.askdirectory(parent=self, title="A folder for the sprites")
        if folder:
            written = map_art.export_sprites(self.project, folder)
            self.status.configure(text=f"Wrote {len(written)} files to {folder}")

    def import_sprites(self, folder=None):
        folder = folder or file_dialogs.askdirectory(parent=self, title="The folder with sprites-p0.png to p3.png")
        if not folder:
            return
        try:
            notes = map_art.import_sprites(self.project, folder)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Map pictures", str(problem), parent=self)
            return
        self.done(notes, "Nothing named sprites-p0.png to p3.png there." if not notes else "Imported:")

    def revert_sprites(self):
        map_art.revert_sprites(self.project)
        self.done([], "The sprites are the disc's again.")

    def export_textures(self, folder=None):
        folder = folder or file_dialogs.askdirectory(parent=self, title="A folder for the textures")
        if folder:
            written = map_art.export_textures(self.project, self.package_name(), folder)
            self.status.configure(text=f"Wrote {len(written)} textures to {folder}")

    def import_textures(self, folder=None):
        folder = folder or file_dialogs.askdirectory(parent=self, title="The folder with the textures")
        if not folder:
            return
        try:
            notes = map_art.import_textures(self.project, self.package_name(), folder)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Map pictures", str(problem), parent=self)
            return
        self.done(notes, "No texture of this map is named there." if not notes else "Imported:")

    def revert_textures(self):
        map_art.revert_textures(self.project, self.package_name())
        self.done([], f"The textures of the map {self.package.get()} are the disc's again.")
