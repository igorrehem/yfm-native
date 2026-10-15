"""The UI tab: what a mod changes of the screens' look, on pictures of them
drawn from the user's own disc (ui_assets.py). Three pages: the title
screen ("title", notes/modding.md "The title screen"), its two menus
("menu", "The title's menus") and the duel's pictures ("ui", "The duel's
pictures"). Each page is a picture to drag things on and, beside it, what
the chosen thing has; the pages are in ui_title.py and ui_duel.py.

The three keys are the mod's own `other` keys (manifest.py keeps them as
written): a page changes only the members it shows, and a key left empty
is taken out, so a mod that changes nothing here writes nothing."""
from __future__ import annotations

import base64
import os
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk

from . import board_art, file_dialogs, pngio, theme, ui_assets
from .tabs import Tab
from .widgets import px, ui_font

GAME_W, GAME_H = 320, 240
IMAGE_DIR = "ui"          # where the tab puts a PNG it is given, in the mod


# --- the mod's keys ---------------------------------------------------------------

def section(project, key: str) -> dict:
    value = project.other.get(key)
    return value if isinstance(value, dict) else {}


def ensure(project, *path) -> dict:
    """The object at project.other[path[0]][path[1]]..., made as needed."""
    at = project.other
    for key in path:
        if not isinstance(at.get(key), dict):
            at[key] = {}
        at = at[key]
    return at


def prune(project, key: str):
    """Empty objects under `key` taken out, then `key` itself if empty."""
    def tidy(value: dict):
        for k in list(value):
            if isinstance(value[k], dict):
                tidy(value[k])
                if not value[k]:
                    del value[k]
    value = project.other.get(key)
    if isinstance(value, dict):
        tidy(value)
        if not value:
            del project.other[key]


def set_member(target: dict, key: str, value, default=None):
    """target[key] = value, or the key taken out for its default."""
    if value is None or value == default:
        target.pop(key, None)
    else:
        target[key] = value


def color_text(value: int) -> str:
    return f"#{value:06X}"


def as_int(value, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


# --- the mod's pictures --------------------------------------------------------------

def image_bytes(project, name: str):
    """A PNG the mod names, from what the editor holds or the mod's folder."""
    if not isinstance(name, str) or not name:
        return None
    if name in project.files:
        return project.files[name]
    source = project.source_dir
    if source:
        path = Path(source) / name
        if path.is_file():
            try:
                return path.read_bytes()
            except OSError:
                return None
    return None


_decoded = {}


def mod_image(project, name: str):
    """The PNG as a pngio.Image, or None (decoded once per content)."""
    data = image_bytes(project, name)
    if data is None:
        return None
    key = hash(data)
    if key not in _decoded:
        try:
            _decoded[key] = pngio.decode(data)
        except (pngio.PngError, ValueError, Exception):
            _decoded[key] = None
    return _decoded[key]


_sized = {}


def sized(image: pngio.Image, width: int, height: int) -> pngio.Image:
    """The picture at width x height as the game's console resolution draws
    it (each texel the average of what is under it, art.c), kept."""
    key = (id(image), width, height)
    if key not in _sized:
        if image.width <= width * 3 and image.height <= height * 3:
            _sized[key] = pngio.scale_to(image, max(1, width), max(1, height))
        else:   # a big picture: a cheap step down first, then the average
            step = pngio.scale_to(image, max(1, width * 2), max(1, height * 2))
            _sized[key] = pngio.resample(step, max(1, width), max(1, height))
    return _sized[key]


def add_image_file(project, path, stem: str) -> str:
    """The PNG at `path` put in the mod as ui/<stem>.png (another name when
    that holds another picture); its name. ValueError when it is no PNG."""
    data = Path(path).read_bytes()
    try:
        pngio.decode(data)
    except (pngio.PngError, ValueError) as problem:
        raise ValueError(f"{Path(path).name} is not a PNG the editor can read: {problem}")
    name, n = f"{IMAGE_DIR}/{stem}.png", 2
    while (name in project.files and project.files[name] != data) or \
            (name not in project.files and image_bytes(project, name) not in (None, data)):
        name = f"{IMAGE_DIR}/{stem}-{n}.png"
        n += 1
    project.files[name] = data
    return name


def import_image(widget, project, stem: str):
    """A PNG the user chooses, put in the mod (add_image_file); its name or None."""
    path = file_dialogs.askopenfilename(parent=widget, title="Choose a PNG",
                                        filetypes=[("PNG pictures", "*.png"), ("All files", "*")])
    if not path:
        return None
    try:
        return add_image_file(project, path, stem)
    except (OSError, ValueError) as problem:
        messagebox.showerror("FM Editor", str(problem), parent=widget)
        return None


# --- widgets ---------------------------------------------------------------------------

class ColorButton(ttk.Frame):
    """A swatch and its #RRGGBB; a click picks another, the x puts it back.
    multiplies: the color is a tint (it multiplies the picture's), so a
    bright one gets a note that it can only darken."""

    def __init__(self, master, on_change, default=0xFFFFFF, allow_none=False, multiplies=False):
        super().__init__(master)
        self.on_change, self.default, self.allow_none = on_change, default, allow_none
        self.multiplies = multiplies
        self.value = default
        self.swatch = tk.Canvas(self, width=px(self, 34), height=px(self, 18), highlightthickness=1,
                                highlightbackground="#888", cursor="hand2")
        self.swatch.pack(side="left")
        self.swatch.bind("<Button-1>", lambda e: self.pick())
        self.text = ttk.Label(self, width=8)
        self.text.pack(side="left", padx=(4, 0))
        self.reset = ttk.Button(self, text="×", width=2, command=self.clear)
        self.reset.pack(side="left")
        self.note = ttk.Label(self, style="Warning.TLabel")
        self.note.pack(side="left", padx=(6, 0))
        self.set(default)

    def set(self, value):
        self.value = value
        self.swatch.delete("all")
        if value is None:
            self.swatch.create_line(0, px(self, 18), px(self, 34), 0, fill="#c01c28", width=2)
            self.text.configure(text="none")
        else:
            self.swatch.configure(background=color_text(value))
            self.text.configure(text=color_text(value))
        self.reset.state(["disabled"] if value == self.default else ["!disabled"])
        self.note.configure(text=WARN + "only darkens" if self.multiplies and brightens(value) else "")

    def pick(self):
        start = color_text(self.value if self.value is not None else self.default)
        chosen = colorchooser.askcolor(color=start, parent=self, title="Choose a color")
        if chosen and chosen[1]:
            self.set(int(chosen[1][1:], 16))
            self.on_change(self.value)

    def clear(self):
        self.set(None if self.allow_none else self.default)
        self.on_change(self.value)


WARN = "\u26a0 "


def brightens(value) -> bool:
    """A tint someone may have chosen to brighten with: not white, with a
    channel near full (a multiply only darkens, so it reads darker)."""
    return isinstance(value, int) and value != 0xFFFFFF and max(value >> 16, value >> 8 & 255, value & 255) >= 0xC0


def fixed_cursor(widget) -> str:
    """The mouse pointer over a thing that is chosen but cannot be moved."""
    system = widget.tk.call("tk", "windowingsystem")
    return {"win32": "no", "aqua": "notallowed"}.get(system, "X_cursor")


class Stage(tk.Canvas):
    """The game's 320 x 240 at a whole zoom: pictures placed in the game's
    pixels, dragged with the mouse (the game's pixels again, on release;
    on_drag hears each step on the way) or nudged with the arrow keys (8
    with Shift), one chosen at a time with a dashed box round it. Pictures
    are pngio images, kept as Tk photos (zoomed by Tk) until they change.
    axes[key] says which ways a thing moves ("xy" unless set: "y" up and
    down only, "" not at all, though it is still chosen by a click); the
    pointer over it says so."""

    def __init__(self, master, zoom: int = 2, on_select=None, on_move=None, on_wheel=None, on_drag=None,
                 on_hover=None):
        super().__init__(master, width=GAME_W * zoom, height=GAME_H * zoom, highlightthickness=0,
                         background="#000", cursor="arrow", takefocus=1)
        self.zoom = zoom
        self.on_select, self.on_move, self.on_wheel = on_select, on_move, on_wheel
        self.on_drag, self.on_hover = on_drag, on_hover
        self.photos = {}          # (key, picture) -> (picture, zoom, photo): kept while their picture is
        self.shown = []           # the photos the canvas shows now (Tk forgets one nothing holds)
        self.items = {}           # key -> canvas items
        self.boxes = {}           # key -> (x, y, w, h) in the game's pixels
        self.draggable = set()
        self.axes = {}
        self.chosen = None
        self.drag = None
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self._wheel(e, 120))
        self.bind("<Button-5>", lambda e: self._wheel(e, -120))
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self.on_hover and self.on_hover(None))
        for key, (dx, dy) in (("Left", (-1, 0)), ("Right", (1, 0)), ("Up", (0, -1)), ("Down", (0, 1))):
            self.bind(f"<KeyPress-{key}>", lambda e, d=(dx, dy): self._nudge(e, *d))

    def set_zoom(self, zoom: int):
        if zoom != self.zoom:
            self.zoom = zoom
            self.configure(width=GAME_W * zoom, height=GAME_H * zoom)
            self.photos.clear()

    def photo(self, key, image: pngio.Image):
        """The Tk photo of a picture at the zoom, made again only when the
        picture (its bytes) or the zoom changes."""
        signature = (key, image.width, image.height, hash(image.rgba))
        held = self.photos.get(signature)
        if held and held[1] == self.zoom:
            self.shown.append(held[2])
            return held[2]
        base = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(image)), format="png")
        photo = base.zoom(self.zoom) if self.zoom > 1 else base
        if len(self.photos) > 400:
            self.photos.clear()
        self.photos[signature] = (image, self.zoom, photo)
        self.shown.append(photo)
        return photo

    def clear(self):
        self.delete("all")
        self.shown = []
        self.items.clear()
        self.boxes.clear()
        self.draggable.clear()
        self.axes.clear()

    def picture(self, key, image: pngio.Image, x: int, y: int, drag=True, box=None):
        """`image` with its top left at x, y; `box` (x, y, w, h) is what
        selects it (its own rectangle by default)."""
        z = self.zoom
        item = self.create_image(x * z, y * z, image=self.photo(key, image), anchor="nw")
        self.items.setdefault(key, []).append(item)
        if box is not None or key not in self.boxes:
            self.boxes[key] = box or (x, y, image.width, image.height)
        if drag:
            self.draggable.add(key)
        return item

    def rectangle(self, key, x, y, w, h, fill="", outline="", width=1, drag=False, dash=None):
        z = self.zoom
        item = self.create_rectangle(x * z, y * z, (x + w) * z, (y + h) * z, fill=fill, outline=outline,
                                     width=width, dash=dash)
        if key is not None:
            self.items.setdefault(key, []).append(item)
            self.boxes.setdefault(key, (x, y, w, h))
            if drag:
                self.draggable.add(key)
        return item

    def text(self, key, x, y, text, color, size, anchor="w", font_family="TkDefaultFont", drag=True, shadow=True):
        z = self.zoom
        font = (font_family, -max(6, int(size * z)), "bold")
        items = []
        if shadow:
            items.append(self.create_text(x * z + z, y * z + z, text=text, fill="#000", font=font, anchor=anchor))
        items.append(self.create_text(x * z, y * z, text=text, fill=color, font=font, anchor=anchor))
        if key is not None:
            self.items.setdefault(key, []).extend(items)
            x0, y0, x1, y1 = self.bbox(items[-1])
            self.boxes[key] = (x0 / z, y0 / z, (x1 - x0) / z, (y1 - y0) / z)
            if drag:
                self.draggable.add(key)
        return items

    def outline(self, key):
        """The chosen thing's dashed box, over everything."""
        self.delete("chosen")
        self.chosen = key
        if key not in self.boxes:
            return
        x, y, w, h = self.boxes[key]
        z = self.zoom
        accent = "#ffd34d"
        self.create_rectangle(x * z - 2, y * z - 2, (x + w) * z + 1, (y + h) * z + 1, outline="#000", width=3,
                              tags="chosen")
        self.create_rectangle(x * z - 2, y * z - 2, (x + w) * z + 1, (y + h) * z + 1, outline=accent, width=1,
                              dash=(4, 3), tags="chosen")

    def key_at(self, x, y):
        """The topmost draggable thing under the mouse (canvas pixels)."""
        gx, gy = x / self.zoom, y / self.zoom
        for item in reversed(self.find_overlapping(x, y, x, y)):
            for key, items in self.items.items():
                if item in items and key in self.draggable:
                    return key
        for key in reversed(list(self.boxes)):
            bx, by, bw, bh = self.boxes[key]
            if key in self.draggable and bx <= gx < bx + bw and by <= gy < by + bh:
                return key
        return None

    def moves(self, key) -> str:
        return self.axes.get(key, "xy")

    def _hover(self, event):
        key = self.key_at(event.x, event.y)
        if key is None:
            cursor = "arrow"
        else:
            cursor = {"xy": "fleur", "y": "sb_v_double_arrow", "x": "sb_h_double_arrow"}.get(self.moves(key)) or \
                fixed_cursor(self)
        if str(self.cget("cursor")) != cursor:
            self.configure(cursor=cursor)
        if self.on_hover and not self.drag:
            self.on_hover((event.x // self.zoom, event.y // self.zoom))

    def _nudge(self, event, dx, dy):
        step = 8 if event.state & 1 else 1          # Shift
        moves = self.moves(self.chosen)
        dx, dy = (dx if "x" in moves else 0), (dy if "y" in moves else 0)
        if self.chosen in self.draggable and self.on_move and (dx or dy):
            self.on_move(self.chosen, dx * step, dy * step)
        return "break"

    def _press(self, event):
        self.focus_set()
        key = self.key_at(event.x, event.y)
        self.drag = (key, event.x, event.y, 0, 0) if key is not None else None
        if self.on_select:
            self.on_select(key)

    def _motion(self, event):
        if not self.drag:
            return
        key, x0, y0, moved_x, moved_y = self.drag
        z = self.zoom
        moves = self.moves(key)
        dx = round((event.x - x0) / z) if "x" in moves else 0
        dy = round((event.y - y0) / z) if "y" in moves else 0
        if (dx, dy) != (moved_x, moved_y):
            for item in self.items.get(key, ()):
                self.move(item, (dx - moved_x) * z, (dy - moved_y) * z)
            self.move("chosen", (dx - moved_x) * z, (dy - moved_y) * z)
            self.drag = (key, x0, y0, dx, dy)
            if self.on_drag and key is not None:
                self.on_drag(key, dx, dy)

    def _release(self, event):
        if not self.drag:
            return
        key, _, _, dx, dy = self.drag
        self.drag = None
        if (dx or dy) and self.on_move:
            self.on_move(key, dx, dy)

    def _wheel(self, event, delta=None):
        delta = delta if delta is not None else event.delta
        key = self.key_at(event.x, event.y) or self.chosen
        if key is not None and self.on_wheel:
            self.on_wheel(key, 1 if delta > 0 else -1)


class StageView(ttk.Frame):
    """A page's picture as big as the room beside its form lets it be, at a
    whole zoom (the game's pixels stay square and sharp), centred, with a row
    of the page's own under it (tools) and where the mouse is in the
    game's pixels. Fitted once the size stops changing, not per event."""

    MOST = 6

    def __init__(self, master, draw, **callbacks):
        super().__init__(master)
        self.draw = draw
        self.inner = ttk.Frame(self)
        self.inner.place(relx=0.5, y=0, anchor="n")
        self.stage = Stage(self.inner, zoom=2, on_hover=self.hovered, **callbacks)
        self.stage.pack()
        self.tools = ttk.Frame(self.inner)
        self.tools.pack(fill="x", pady=(px(self, 6), 0))
        self.where = ttk.Label(self.tools, style="Hint.TLabel")
        self.where.pack(side="right")
        self.job = None
        self.seen = None
        # What it asks of the page: the picture at 2x (place() asks nothing).
        self.configure(width=GAME_W * 2, height=GAME_H * 2 + px(self, 40))
        self.bind("<Configure>", lambda e: self.fit_later())

    def hovered(self, at):
        self.where.configure(text="" if at is None else f"x {at[0]}  y {at[1]}")

    def fit_later(self):
        if self.job is None:
            self.job = self.winfo_toplevel().after(80, self.fit)

    def fit(self):
        self.job = None
        if not self.winfo_exists():
            return
        width = self.winfo_width()
        height = self.winfo_height() - self.tools.winfo_reqheight() - px(self, 6)
        if width <= 1 or (width, height) == self.seen:
            return
        self.seen = (width, height)
        zoom = max(1, min(self.MOST, width // GAME_W, height // GAME_H))
        if zoom != self.stage.zoom:
            self.stage.set_zoom(zoom)
            self.draw()


class ElementList(ttk.Frame):
    """A page's things in groups, a dot (and the editor's changed color) on
    each the mod changes. rows: (iid, parent, text, values, changed, tags);
    a group's row chooses its first."""

    def __init__(self, master, on_pick, columns=(), height=8):
        super().__init__(master)
        self.on_pick = on_pick
        self.loading = False
        names = tuple(key for key, _, _ in columns[1:]) + ("mark",)
        self.tree = ttk.Treeview(self, columns=names, height=height, selectmode="browse",
                                 show="tree headings" if columns else "tree")
        self.tree.widths = {"#0": px(self, 190), "mark": px(self, 24)}
        self.tree.heading("#0", text=columns[0][1] if columns else "")
        for key, text, width in columns[1:]:
            self.tree.heading(key, text=text)
            self.tree.widths[key] = px(self, width)
        for key, width in self.tree.widths.items():
            self.tree.column(key, width=width, stretch=key == "#0", anchor="center" if key == "mark" else "w")
        self.tree.heading("mark", text="")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        for tag in theme.TAGS:
            self.tree.tag_configure(tag, foreground=theme.tag_color(self.tree, tag))
        self.tree.tag_configure("group", font=ui_font(10))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        self.groups = {}
        self.current = None     # what show() selected: its <<TreeviewSelect>> comes later, and is no pick

    def fill(self, rows, chosen=None):
        self.loading = True
        self.current = None
        self.tree.delete(*self.tree.get_children())
        self.groups = {}
        for iid, parent, text, values, changed, tags in rows:
            tags = tuple(tags) + (("changed",) if changed else ())
            self.tree.insert(parent, "end", iid=iid, text=text, open=True, tags=tags,
                             values=tuple(values) + ("\u25cf" if changed else "",))
            if parent:
                self.groups.setdefault(parent, iid)
        self.show(chosen)
        self.loading = False

    def show(self, chosen):
        if chosen is not None and self.tree.exists(chosen):
            self.current = chosen
            if self.tree.selection() != (chosen,):
                self.tree.selection_set(chosen)
            self.tree.see(chosen)
        else:
            self.current = None
            if self.tree.selection():
                self.tree.selection_remove(*self.tree.selection())

    def picked(self):
        selection = self.tree.selection()
        if self.loading or not selection or selection[0] == self.current:
            return
        iid = selection[0]
        if iid in self.groups and not self.tree.parent(iid) and self.groups[iid] != iid:
            self.on_pick(self.groups[iid], group=iid)
        else:
            self.on_pick(iid, group=None)


def page_layout(page, draw, columns=(), list_height=4, **callbacks):
    """The page's picture (a StageView) on the left, growing with the room;
    on the right its list (taking what height the form leaves), a row for
    the list's buttons, the chosen thing's name, what it is and its form.
    Sets page.view, page.stage, page.list, page.list_tools, page.heading,
    page.what, page.side; the form goes in page.side at row 4."""
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)
    page.view = StageView(page, draw, **callbacks)
    page.view.grid(row=0, column=0, sticky="nsew")
    page.stage = page.view.stage
    side = page.side = ttk.Frame(page, padding=(px(page, 12), 0, 0, 0), width=px(page, 470))
    side.grid(row=0, column=1, sticky="nsew")
    page.columnconfigure(1, minsize=px(page, 470))
    side.columnconfigure(0, weight=1)
    side.rowconfigure(0, weight=1)
    page.list = ElementList(side, page.pick, columns=columns, height=list_height)
    page.list.grid(row=0, column=0, sticky="nsew")
    page.list_tools = ttk.Frame(side)
    page.list_tools.grid(row=1, column=0, sticky="ew", pady=(px(page, 4), 0))
    ttk.Separator(side).grid(row=2, column=0, sticky="ew", pady=(px(page, 8), px(page, 6)))
    head = ttk.Frame(side)
    head.grid(row=3, column=0, sticky="ew")
    page.heading = ttk.Label(head, font=ui_font(12))
    page.heading.pack(anchor="w")
    page.what = ttk.Label(head, style="Hint.TLabel", wraplength=px(page, 440), justify="left")
    page.what.pack(anchor="w")
    page.revert_page = ttk.Button(page.list_tools, text="Revert page", command=lambda: page.tab.revert_page(page))
    page.revert_page.pack(side="right")


# --- putting it back --------------------------------------------------------------------

# What each page writes: (key, members) -- None for the whole key. The
# title's "entries" and "spacing" are the menus' (title_config.c reads them
# for the menus as the "menu" key's own).
PAGE_KEYS = {"title": [("title", "screen")], "menu": [("menu", None), ("title", ("entries", "spacing"))],
             "duel": [("ui", None)]}
KEYS = ("title", "menu", "ui")


def _kept(key, members, member) -> bool:
    """Whether a revert of (key, members) leaves key's member alone."""
    if members is None:
        return False
    if members == "screen":
        return member in ("entries", "spacing")
    return member not in members


def owned(project, keys) -> dict:
    """What the mod has of keys (PAGE_KEYS' pairs): {key: {member: value}}
    (a key that is no object: {"": it})."""
    out = {}
    for key, members in keys:
        value = project.other.get(key)
        if value is None:
            continue
        if not isinstance(value, dict):
            out[key] = {"": value}
            continue
        picked = {k: v for k, v in value.items() if not _kept(key, members, k)}
        if picked:
            out.setdefault(key, {}).update(picked)
    return out


def stripped(other: dict, keys) -> dict:
    """other without the members of keys (the objects it changes copied)."""
    out = dict(other)
    for key, members in keys:
        value = out.get(key)
        if value is None:
            continue
        if not isinstance(value, dict):
            del out[key]
            continue
        kept = {k: v for k, v in value.items() if _kept(key, members, k)}
        if kept:
            out[key] = kept
        else:
            del out[key]
    return out


def strings(value) -> set:
    """Every string in a value: the pictures it names."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*map(strings, value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*map(strings, value)) if value else set()
    return set()


def orphans(project, other: dict) -> list:
    """The tab's own pictures (ui/...) the mod holds that other does not name."""
    used = strings(other)
    return [name for name in project.files if name.startswith(IMAGE_DIR + "/") and name not in used]


def revert(project, keys) -> list:
    """The members of keys taken out (project.other's order kept), then the
    tab's pictures nothing names any more; those pictures' names."""
    new = stripped(project.other, keys)
    dropped = orphans(project, new)
    project.other.clear()
    project.other.update(new)
    for name in dropped:
        del project.files[name]
    return dropped


def describe(project, keys) -> list:
    """What reverting keys loses, a line each, for the question."""
    have = owned(project, keys)
    lines = []
    title = have.get("title", {})
    screen = [k for k in title if k not in ("entries", "spacing")]
    if screen:
        pictures = len(title.get("images") or []) if isinstance(title.get("images"), list) else 0
        words = len(title.get("text") or []) if isinstance(title.get("text"), list) else 0
        extra = ", ".join(part for part in (f"{pictures} picture(s)" if pictures else "",
                                            f"{words} line(s) of words" if words else "") if part)
        lines.append("the title screen's changes" + (f" ({extra})" if extra else ""))
    menu = have.get("menu", {})
    if menu or "entries" in title or "spacing" in title:
        buttons = len(menu.get("buttons") or []) if isinstance(menu.get("buttons"), list) else 0
        lines.append("the menus' changes" + (f" ({buttons} button(s) of the mod's own)" if buttons else ""))
    duel = have.get("ui", {}).get("duel")
    if have.get("ui"):
        count = len(duel) if isinstance(duel, dict) else 0
        lines.append("the duel's pictures" + (f" ({count} changed)" if count else ""))
    return lines


class UiTab(Tab):
    """Title screen, Menus and Duel: a row to choose from (PAGES), the page
    under it (ui_title.TitlePage, ui_title.MenuPage, ui_duel.DuelPage).
    Revert to retail puts the whole tab back as the game has it; each page
    has its own (Revert page), each thing on it its own too."""

    # (key, button, its module and class, hint): a page more is a line more.
    PAGES = [("title", "Title screen", ("ui_title", "TitlePage"), "Drag to move, arrows nudge (Shift: 8). "
              "Click the background for its colors."),
             ("menu", "Menus", ("ui_title", "MenuPage"), "Drag a button to place it; the list sets the order."),
             ("duel", "Duel", ("ui_duel", "DuelPage"), "Drag to move, wheel to size, arrows nudge."),
             ("board", "Duel board", ("ui_board", "BoardPage"), "Click a part of the board or the list; Replace "
              "puts your PNG in its place.")]

    def __init__(self, notebook, app):
        super().__init__(notebook, app, "UI")
        import importlib
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.page_name = tk.StringVar(value=self.PAGES[0][0])
        for value, text, _, _ in self.PAGES:
            ttk.Radiobutton(top, text=text, value=value, variable=self.page_name, style="Segment.Toolbutton",
                            command=self.show_page).pack(side="left", padx=(0, 2))
        self.revert_button = ttk.Button(top, text="Revert to retail...", command=self.revert_all)
        self.revert_button.pack(side="right")
        # Held down, the page shows the game's own: before and after.
        self.compare = ttk.Button(top, text="Hold: the game's")
        self.compare.pack(side="right", padx=(0, 6))
        self.compare.bind("<ButtonPress-1>", lambda e: self.comparing_now(True))
        self.compare.bind("<ButtonRelease-1>", lambda e: self.comparing_now(False))
        self.comparing = False
        self.hint = ttk.Label(top, style="Hint.TLabel")
        self.hint.pack(side="left", padx=(12, 0))
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, pady=(6, 0))
        self.pages = {}
        for key, _, (module, name), _ in self.PAGES:
            page_class = getattr(importlib.import_module(f".{module}", __package__), name)
            self.pages[key] = page_class(self.body, self)
        self.assets = {}
        self.show_page()

    # The pictures off the disc, read once per game files.
    def title_art(self):
        files = getattr(self.app, "files", None)
        key = ("title", id(files))
        if key not in self.assets:
            self.assets[key] = ui_assets.TitleArt(ui_assets.read_su(files) if files else None)
        return self.assets[key]

    def duel_art(self, terrain: int = 0):
        files = getattr(self.app, "files", None)
        key = ("duel", id(files), terrain)
        if key not in self.assets:
            self.assets[key] = ui_assets.DuelArt(getattr(files, "wa", None), terrain)
        return self.assets[key]

    def current_page(self):
        return self.pages[self.page_name.get()]

    def show_page(self):
        name = self.page_name.get()
        for key, page in self.pages.items():
            if key == name:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self.hint.configure(text=next(hint for key, _, _, hint in self.PAGES if key == name))
        if self.project is not None:
            self.pages[name].fill()
        self.mark_reverts()

    def refresh(self):
        if self.project is None:
            return
        self.current_page().fill()
        self.mark_reverts()

    def rescaled(self):
        for page in self.pages.values():
            if hasattr(page, "view"):        # the board's sketch fits itself
                page.view.fit_later()

    def changed(self, key: str):
        """After an edit of project.other[key]: empty objects out, the window told."""
        prune(self.project, key)
        self.app.changed()
        self.mark_reverts()

    def mark_reverts(self):
        """The revert buttons usable only when there is something to put back."""
        if self.project is None:
            return
        anything = owned(self.project, [(k, None) for k in KEYS]) or board_art.changed(self.project)
        self.revert_button.state(["!disabled"] if anything else ["disabled"])
        for key, page in self.pages.items():
            if key in PAGE_KEYS:
                page.revert_page.state(["!disabled"] if owned(self.project, PAGE_KEYS[key]) else ["disabled"])
            elif key == "board":
                page.revert_page.state(["!disabled"] if board_art.changed(self.project) else ["disabled"])

    # --- before and after -------------------------------------------------------------

    def comparing_now(self, on: bool):
        if on == self.comparing or self.project is None:
            return
        self.comparing = on
        self.current_page().draw()

    def retail_view(self):
        """For a page's draw while comparing: the project without the tab's
        keys (put back by restore())."""
        held = self.project.other
        self.project.other = {k: v for k, v in held.items() if k not in KEYS}
        return held

    def draw_compared(self, page, draw):
        """draw() as the game has it while comparing, with a word saying so."""
        if not self.comparing:
            draw()
            return
        held = self.retail_view()
        try:
            draw()
        finally:
            self.project.other = held
        stage = page.stage
        stage.delete("chosen")
        stage.create_rectangle(0, 0, px(stage, 96), px(stage, 22), fill="#000", outline="#ffd34d")
        stage.create_text(px(stage, 48), px(stage, 11), text="The game's", fill="#ffd34d", font=ui_font(10))

    # --- putting it back ---------------------------------------------------------------

    def revert_all(self):
        self.revert([(k, None) for k in KEYS], "Revert to retail",
                    "Put the title screen, its menus, the duel's pictures and the duel board back as the game "
                    "has them?", board=True)

    def revert_page(self, page):
        key = next(k for k, p in self.pages.items() if p is page)
        text = next(t for k, t, _, _ in self.PAGES if k == key)
        self.revert(PAGE_KEYS[key], "Revert page", f"Put the {text.lower()} page back as the game has it?")

    def revert(self, keys, title, question, board=False):
        """keys back as the game has them, and, with board, every field's
        board textures (board_art: the texture pack and the palette patches)."""
        board = board and board_art.changed(self.project) if self.project is not None else False
        if self.project is None or not (owned(self.project, keys) or board):
            return
        lost = describe(self.project, keys)
        if board:
            lost.append("the duel board's textures")
        files = orphans(self.project, stripped(self.project.other, keys))
        text = question + "\n\nLost: " + "; ".join(lost or ["the tab's settings"])
        if files:
            text += f"; {len(files)} picture(s) in {IMAGE_DIR}/"
        text += ".\n\nEdit > Undo brings them back."
        if not messagebox.askyesno(title, text, parent=self):
            return
        self.app.flush_history()         # what was before: an undo step of its own
        revert(self.project, keys)
        if board:
            board_art.revert_all(self.project)
        for page in self.pages.values():
            page.reset_choice()
        self.app.changed()
        self.refresh()
