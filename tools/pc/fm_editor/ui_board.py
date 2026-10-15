"""The UI tab's Duel board page: the textures of the duel's 3D board (the
floor's rows of zones and the platform's walls), field by field, drawn from
the user's own disc (board_art.py has where each is and what the mod
writes). On the left the board itself, the game's model with the mod's
textures (board_model.py), from the duel's camera at first: the middle
mouse button turns it round (Shift or Ctrl: moves it), the wheel brings it
nearer, a double middle click or "Game's view" puts the duel's camera
back. Clicking a part there or in the list chooses it. Beside them the
chosen texture: replace it with a PNG, export the game's to paint over,
tint the game's, or put it back."""
from __future__ import annotations

import time
import tkinter as tk
from collections import OrderedDict
from tkinter import messagebox, ttk

from . import board_art as ba, board_model as bm, file_dialogs, pngio
from .pngio import Image
from .ui_tab import ColorButton
from .widgets import px, ui_font

FLOOR_ITEM = "floor"            # the whole floor, one picture
GROUPS = (("Floor", ba.FLOOR), ("Walls and trim", ba.WALLS))
DRAG_SCALE = 3                  # while the camera moves: a picture a third the size, enlarged...
DRAG_SCALES = (2, 3, 4, 5, 6, 8)    # ...or as small as this machine draws in FRAME
FRAME = 0.030                   # seconds a picture may take while the camera moves
SLICE = 0.025                   # the full picture is drawn this long at a time, the window live between
KEPT = 7                        # full pictures kept (some 8 MB each at 1600x960): the fields seen
AHEAD = 500                     # ms the page is left alone before it draws the other fields ahead
GAME = ("the game's",)          # a view's board while the tab holds the game's up
HINT = "Middle drag turns the board, Shift+middle drag moves it, the wheel zooms."


def checker(w: int, h: int, cell: int = 6) -> Image:
    dark, light = bytes((0x50, 0x50, 0x50, 255)), bytes((0x6a, 0x6a, 0x6a, 255))
    rows = [b"".join(light if (x // cell + y) & 1 else dark for x in range(w)) for y in (0, 1)]
    return Image(w, h, b"".join(rows[(y // cell) & 1] for y in range(h)))


def over(base: Image, piece: Image) -> Image:
    """`piece` (as large as `base`) over it, alpha-mixed."""
    src = piece.rgba
    if src[3::4].count(255) == len(src) // 4:
        return Image(base.width, base.height, src)          # opaque all over: the piece itself
    out = bytearray(base.rgba)
    for i in range(0, len(src), 4):
        a = src[i + 3]
        if a == 255:
            out[i:i + 3] = src[i:i + 3]
        elif a:
            for c in range(3):
                out[i + c] = (src[i + c] * a + out[i + c] * (255 - a)) // 255
    return Image(base.width, base.height, bytes(out))


class BoardPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.terrain = ba.TERRAINS[0]
        self.chosen = FLOOR_ITEM
        self.loading = False
        self.camera = bm.CAMERA
        self.picture = None         # board_model.Picture shown, and its scale on the canvas
        self.scale = 1
        self.offset = (0, 0)
        self.photos = []
        self._job = None
        self._drag_job = None
        self.drag = None            # (kind, x, y, camera at the press) while the middle button is down
        self.drag_scale = DRAG_SCALE
        self.rate = None            # seconds a small picture's pixel takes, about (adapt)
        self.shown_view = None      # (field, camera, the mod's board) the picture shows
        self.pictures = OrderedDict()   # view + (size,) -> the full picture, the latest last
        self._disc = None           # the game files the pictures are of
        self._work = None           # (view + (size,), board_model.render_steps) being drawn
        self._work_job = None
        self._ahead_job = None

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Field").pack(side="left", padx=(0, 6))
        self.field = tk.StringVar(value=self.terrain)
        self.field_buttons = {}
        for terrain in ba.TERRAINS:
            button = ttk.Radiobutton(top, text=ba.TERRAIN_LABELS[terrain], value=terrain, variable=self.field,
                                     style="Toolbutton", command=self.choose_field)
            button.pack(side="left", padx=(0, 2))
            self.field_buttons[terrain] = button
        # The tab's own Revert to retail (top right) puts the board back too.
        self.revert_page = ttk.Button(top, text="Revert page", command=self.revert_all)
        self.revert_page.pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        # The board takes the room the list and the texture leave.
        left = ttk.Frame(body)
        middle = ttk.Frame(body, padding=(10, 0, 0, 0))
        side = ttk.Frame(body, padding=(12, 0, 0, 0), width=px(self, 330))
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        middle.pack(side="right", fill="y")
        left.pack(side="left", fill="both", expand=True)
        under = ttk.Frame(left)
        under.pack(side="bottom", fill="x", pady=(4, 0))
        self.game_view = ttk.Button(under, text="Game's view", command=self.reset_camera)
        self.game_view.pack(side="right")
        ttk.Label(under, text=HINT, style="Hint.TLabel").pack(side="left", anchor="w")
        self.canvas = tk.Canvas(left, width=px(self, 480), height=px(self, 360), highlightthickness=0,
                                background="#000000", cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.clicked)
        self.canvas.bind("<ButtonPress-2>", self.press)
        self.canvas.bind("<B2-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-2>", self.release)
        self.canvas.bind("<Double-Button-2>", lambda e: self.reset_camera())
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", self.wheel)
        self.canvas.bind("<Button-5>", self.wheel)

        self.tree = ttk.Treeview(middle, columns=("state",), show="tree", selectmode="browse",
                                 height=len(ba.PARTS) + 3)
        self.tree.column("#0", width=px(self, 180), stretch=False)
        self.tree.column("state", width=px(self, 64), stretch=False)
        self.tree.pack(fill="y", expand=True)
        for title, parts in GROUPS:
            group = self.tree.insert("", "end", iid=FLOOR_ITEM if parts is ba.FLOOR else "walls", text=title,
                                     open=True)
            for part in parts:
                self.tree.insert(group, "end", iid=part.key, text=part.label)
        self.tree.bind("<<TreeviewSelect>>", self.tree_selected)

        self.title = ttk.Label(side, font=("TkDefaultFont", 12, "bold"))
        self.title.pack(anchor="w")
        self.what = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 300), justify="left")
        self.what.pack(anchor="w", pady=(0, 6))
        self.preview = tk.Canvas(side, width=px(self, 300), height=px(self, 150), highlightthickness=0,
                                 background="#05060a")
        self.preview.pack(anchor="w")
        self.size = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 300), justify="left")
        self.size.pack(anchor="w", pady=(4, 6))
        buttons = ttk.Frame(side)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Replace...", command=self.replace).pack(side="left")
        ttk.Button(buttons, text="Export game's...", command=self.export).pack(side="left", padx=(4, 0))
        self.revert_button = ttk.Button(buttons, text="Revert", command=self.revert)
        self.revert_button.pack(side="left", padx=(4, 0))
        tints = ttk.Frame(side)
        tints.pack(anchor="w", pady=(8, 0))
        ttk.Label(tints, text="Tint").pack(side="left", padx=(0, 8))
        self.tint = ColorButton(tints, self.set_tint)
        self.tint.pack(side="left")
        self.all_fields = tk.BooleanVar(value=False)
        ttk.Checkbutton(side, text="All seven fields", variable=self.all_fields).pack(anchor="w", pady=(8, 0))
        self.warnings = ttk.Label(side, style="Warning.TLabel", wraplength=px(self, 300), justify="left")
        self.warnings.pack(anchor="w", pady=(8, 0))
        self.status = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 300), justify="left")
        self.status.pack(anchor="w", pady=(6, 0))
        self.canvas.bind("<Configure>", lambda e: self.draw_later())

    # --- the mod ---------------------------------------------------------------------

    @property
    def project(self):
        return self.tab.project

    def parts(self) -> list:
        return ba.FLOOR if self.chosen == FLOOR_ITEM else [ba.BY_KEY[self.chosen]]

    def terrains(self) -> list:
        return list(ba.TERRAINS) if self.all_fields.get() else [self.terrain]

    def edited(self, notes=()):
        self.status.configure(text="\n".join(notes))
        self.tab.app.changed()
        self.fill()
        self.tab.mark_reverts()

    # --- drawing -------------------------------------------------------------------------

    def fill(self):
        if self.project is None:
            return
        self.mark()
        self.fill_form()
        self.draw()

    def mark(self):
        """A dot on each field and part the mod changes."""
        for terrain, button in self.field_buttons.items():
            button.configure(text=ba.TERRAIN_LABELS[terrain] + (" •" if ba.changed(self.project, terrain) else ""))
        st = ba.state(self.project)
        for part in ba.PARTS:
            key = (self.terrain, part.key)
            state = "replaced" if key in st.pictures else "tinted" if key in st.tints else ""
            self.tree.set(part.key, "state", state)
        if self.tree.selection() != (self.chosen,):
            self.loading = True
            self.tree.selection_set(self.chosen)
            self.tree.see(self.chosen)
            self.loading = False

    def draw_later(self, delay: int = 120):
        if self._job is not None:
            self.after_cancel(self._job)
        self._job = self.after(delay, self.draw)

    def canvas_size(self):
        canvas = self.canvas
        width = canvas.winfo_width() if canvas.winfo_width() > 1 else int(canvas["width"])
        height = canvas.winfo_height() if canvas.winfo_height() > 1 else int(canvas["height"])
        return max(160, width), max(120, height)

    def view_key(self, terrain: str = None):
        """What a picture shows: the field, the camera and the mod's board
        (its state and version, or the game's while the tab holds it up)."""
        st = ba.state(self.project)
        held = GAME if getattr(self.tab, "comparing", False) else (st, st.version)
        return (terrain or self.terrain, self.camera) + held

    def sources(self, terrain: str):
        """The field's board and its pieces' pictures (the game's while the
        tab holds them up: its "Hold: the game's")."""
        comparing = getattr(self.tab, "comparing", False)
        held = self.project.board_art if comparing else None
        if comparing:
            self.project.board_art = ba.BoardArt()
        try:
            return bm.board(ba.disc(self.project), terrain), bm.pieces_of(self.project, terrain)
        finally:
            if comparing:
                self.project.board_art = held

    def cannot(self, problem):
        """The model cannot be read: said where the board would be."""
        width, height = self.canvas_size()
        self.picture = self.shown_view = None
        self.canvas.delete("all")
        self.canvas.create_text(width // 2, height // 2, fill="#ccc", width=width - 40,
                                text=f"The board's model cannot be read from these game files ({problem}).")

    def draw(self, scale: int = 1):
        """The board as the camera sees it, at the canvas's size (`scale`:
        that many times smaller, enlarged, while the camera moves). A full
        picture not drawn yet is drawn a little at a time (render_later),
        a small one shown first when the board shown is another field,
        camera or edit: a click never holds the window for long."""
        if self._job is not None and scale == 1:
            self.after_cancel(self._job)
        self._job = None
        canvas = self.canvas
        if self.project is None:
            return
        width, height = self.canvas_size()
        if not bm.available(self.project):
            self.stop_work()
            self.picture = self.shown_view = None
            canvas.delete("all")
            canvas.create_text(width // 2, height // 2, fill="#ccc", width=width - 40,
                               text="The board comes from the game files (File > Game files...).")
            return
        if ba.disc(self.project) is not self._disc:
            self._disc = ba.disc(self.project)
            self.pictures.clear()
        view = self.view_key()
        if scale > 1:
            self.stop_work()            # the camera is moving: no picture of where it was
            self.show_small(view, scale)
            return
        key = view + ((width, height),)
        picture = self.pictures.get(key)
        if picture is not None:
            self.pictures.move_to_end(key)
            self.picture, self.scale, self.shown_view = picture, 1, view
            self.show()
            self.ahead_later()
            return
        if self.shown_view != view and not self.show_small(view, self.drag_scale):
            return
        self.render_later(key)

    def show_small(self, view, scale: int) -> bool:
        """A picture `scale` times smaller than the canvas, drawn now; how
        long it took sets the next one's scale (adapt)."""
        width, height = self.canvas_size()
        start = time.perf_counter()
        try:
            board, pieces = self.sources(self.terrain)
            picture = bm.render(board, pieces, self.camera, (max(1, width // scale), max(1, height // scale)))
        except Exception as problem:        # noqa: BLE001 -- a disc whose model is not the game's
            self.cannot(problem)
            return False
        self.picture, self.scale, self.shown_view = picture, scale, view
        self.show()
        self.adapt(scale, time.perf_counter() - start)
        return True

    def adapt(self, scale: int, took: float):
        """The small pictures' scale from how long this one took a pixel
        (the mean with the last ones', so one slow picture, the first of a
        field, does not set it alone): the largest picture this machine
        draws within FRAME."""
        width, height = self.canvas_size()
        rate = took / max(1, (width // scale) * (height // scale))
        self.rate = rate if self.rate is None else (self.rate + rate) / 2
        for choice in DRAG_SCALES:
            if self.rate * (width // choice) * (height // choice) <= FRAME:
                break
        self.drag_scale = choice

    # --- the full picture, a little at a time ------------------------------------------------

    def render_later(self, key):
        """The full picture of `key` (a view and the canvas's size) drawn in
        SLICE-long steps, the window's events handled between them; shown
        when done if it is still the one wanted."""
        if self._work is not None and self._work[0] == key:
            return
        terrain, camera, size = key[0], key[1], key[-1]
        try:
            board, pieces = self.sources(terrain)
        except Exception as problem:        # noqa: BLE001 -- a disc whose model is not the game's
            self.cannot(problem)
            return
        self._work = (key, bm.render_steps(board, pieces, camera, size))
        if self._work_job is None:
            self._work_job = self.after_idle(self._step)

    def _step(self):
        self._work_job = None
        if self._work is None:
            return
        key, steps = self._work
        start = time.perf_counter()
        try:
            next(steps)
            while time.perf_counter() - start < SLICE:
                next(steps)
        except StopIteration as done:
            self._work = None
            wanted = self.project is not None and key == self.view_key() + (self.canvas_size(),)
            self.keep(key, done.value)
            if wanted and self.drag is None:
                self.picture, self.scale, self.shown_view = done.value, 1, key[:-1]
                self.show()
            # The next field ahead soon after one drawn ahead; after the one
            # wanted, once the page is left alone.
            self.ahead_later(AHEAD if wanted else 1)
            return
        except Exception as problem:        # noqa: BLE001 -- a disc whose model is not the game's
            self._work = None
            self.cannot(problem)
            return
        # Idle again: what came meanwhile (a click, a drag) first.
        self._work_job = self.after_idle(self._step)

    def keep(self, key, picture):
        """A full picture kept (KEPT at most, the latest), those of the
        mod's board before an edit let go."""
        if self.project is not None:
            boards = (self.view_key()[2:], GAME)
            for old in [k for k in self.pictures if k[2:-1] not in boards]:
                del self.pictures[old]
        self.pictures[key] = picture
        while len(self.pictures) > KEPT:
            self.pictures.popitem(last=False)

    def stop_work(self):
        self._work = None
        if self._work_job is not None:
            self.after_cancel(self._work_job)
            self._work_job = None
        if self._ahead_job is not None:
            self.after_cancel(self._ahead_job)
            self._ahead_job = None

    def ahead_later(self, delay: int = AHEAD):
        """Once the page is left alone a while: the other fields drawn
        ahead at this camera and size, one after another, so a field
        chosen next is there at once."""
        if self._ahead_job is not None:
            self.after_cancel(self._ahead_job)
        self._ahead_job = self.after(delay, self.draw_ahead)

    def draw_ahead(self):
        self._ahead_job = None
        if self.project is None or self._work is not None or self.drag is not None or \
                getattr(self.tab, "comparing", False) or not self.winfo_ismapped() or not bm.available(self.project):
            return
        order = list(ba.TERRAINS)
        at = order.index(self.terrain)
        for terrain in order[at + 1:] + order[:at]:
            key = self.view_key(terrain) + (self.canvas_size(),)
            if key not in self.pictures:
                self.render_later(key)
                return

    def show(self):
        """The picture on the canvas, the chosen parts outlined (not while
        the tab holds the game's up)."""
        canvas = self.canvas
        canvas.delete("all")
        if self.picture is None:
            return
        comparing = getattr(self.tab, "comparing", False)
        thickness = max(1, round(self.game_pixels() / 1.5 / self.scale))
        image = self.picture.image if comparing else bm.outline(self.picture, [p.key for p in self.parts()],
                                                                thickness)
        photo = self.photo(image)
        if self.scale > 1:
            photo = photo.zoom(self.scale)
        self.photos = [photo]
        canvas.create_image(*self.offset, image=photo, anchor="nw")
        if comparing:
            canvas.create_rectangle(0, 0, px(canvas, 96), px(canvas, 22), fill="#000", outline="#ffd34d")
            canvas.create_text(px(canvas, 48), px(canvas, 11), text="The game's", fill="#ffd34d", font=ui_font(10))

    def photo(self, image: Image):
        """A PhotoImage of the picture (PPM: no compressing, quick for the
        canvas's large ones)."""
        rgb = bytearray(image.width * image.height * 3)
        for c in range(3):
            rgb[c::3] = image.rgba[c::4]
        return tk.PhotoImage(master=self, data=b"P6 %d %d 255\n" % image.size + bytes(rgb), format="ppm")

    # --- the camera, by the mouse ------------------------------------------------------------

    def game_pixels(self) -> float:
        """Canvas pixels to one of the game's screen."""
        return bm.frame(self.canvas_size())[0]

    def press(self, event):
        if self.picture is None:
            return
        kind = "pan" if event.state & 0x5 else "turn"      # Shift or Ctrl held
        self.drag = (kind, event.x, event.y, self.camera)

    def motion(self, event):
        if self.drag is None:
            return
        kind, x, y, camera = self.drag
        k = self.game_pixels()
        dx, dy = (event.x - x) / k, (event.y - y) / k
        self.camera = bm.pan(camera, dx, dy) if kind == "pan" else bm.orbit(camera, dx, dy)
        self.draw_small()

    def draw_small(self):
        """The small picture, once the events waiting are handled: one
        picture for the motions that came while the last was drawn."""
        if self._drag_job is None:
            self._drag_job = self.after_idle(self._draw_small)

    def _draw_small(self):
        self._drag_job = None
        self.draw(self.drag_scale)

    def release(self, event):
        if self.drag is None:
            return
        self.drag = None
        if self._drag_job is not None:
            self.after_cancel(self._drag_job)
            self._drag_job = None
        self.draw_later(1)

    def wheel(self, event):
        if self.picture is None:
            return "break"
        nearer = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
        self.camera = bm.zoom(self.camera, 1 if nearer else -1)
        self.draw_small()
        self.draw_later(250)
        return "break"

    def reset_camera(self):
        """The duel's own camera again."""
        self.camera = bm.CAMERA
        self.draw()

    def current_image(self):
        if self.chosen == FLOOR_ITEM:
            return ba.floor_image(self.project, self.terrain)
        return ba.shown(self.project, self.terrain, ba.BY_KEY[self.chosen])

    def fill_form(self):
        self.loading = True
        parts = self.parts()
        st = ba.state(self.project)
        keys = [(self.terrain, p.key) for p in parts]
        replaced = [k for k in keys if k in st.pictures]
        if self.chosen == FLOOR_ITEM:
            self.title.configure(text="Floor")
            self.what.configure(text="All five rows as one picture, far to near: the opponent's back row at the top, "
                                     "the centre strip once, your back row at the bottom.")
            w, h = ba.FLOOR_W, ba.FLOOR_H
            warnings = [ba.BY_KEY["centre"].warnings[0]]
        else:
            part = parts[0]
            self.title.configure(text=part.label)
            self.what.configure(text=part.what)
            w, h = part.w, part.h
            warnings = list(part.warnings)
        self.size.configure(text=f"{w}x{h} texels, or 2x {w * 2}x{h * 2}, 4x {w * 4}x{h * 4} for Internal 2x and 4x. "
                                 "Other sizes are stretched to fit; at 1x a picture is averaged down.")
        image = self.current_image()
        self.preview.delete("all")
        if image is not None:
            box_w, box_h = px(self, 300), px(self, 160)
            scale = min(box_w / image.width, box_h / image.height)
            shown = pngio.scale_to(image, max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            shown = over(checker(*shown.size), shown)
            self.preview.configure(width=shown.width, height=shown.height)
            photo = self.photo(shown)
            self.preview_photo = photo
            self.preview.create_image(0, 0, image=photo, anchor="nw")
        tint = ba.common_tint(self.project, self.terrain, parts)
        self.tint.set(ba.WHITE if tint is None else tint)
        if replaced:
            self.tint.text.configure(text="off")
        if tint is None:
            warnings.append("The rows have different tints: a new one sets them all.")
        for widget in (self.tint.swatch,):
            widget.configure(cursor="arrow" if replaced else "hand2")
        self.tint.reset.state(["disabled"] if replaced or self.tint.value == ba.WHITE else ["!disabled"])
        if replaced:
            warnings.append("Replaced: the picture has its own colors, so the tint is off.")
        self.revert_button.state(["!disabled"] if replaced or any(k in st.tints for k in keys) else ["disabled"])
        self.warnings.configure(text="\n".join("⚠ " + w for w in warnings))
        self.loading = False

    # --- choosing ---------------------------------------------------------------------------

    def choose_field(self):
        self.terrain = self.field.get()
        self.status.configure(text="")
        self.fill()

    def select(self, key):
        if key is None or key == "walls":
            return
        self.chosen = key
        self.status.configure(text="")
        self.mark()
        self.fill_form()
        self.show()

    def tree_selected(self, event=None):
        if self.loading:
            return
        chosen = self.tree.selection()
        # A selection the page made itself (mark) comes back as an event: no second drawing.
        if chosen and chosen[0] != self.chosen:
            self.select(chosen[0])

    def clicked(self, event):
        if self.picture is None:
            return
        ox, oy = self.offset
        key = self.picture.part_at(int((event.x - ox) // self.scale), int((event.y - oy) // self.scale))
        if key is not None:
            self.select(key)

    # --- edits --------------------------------------------------------------------------------

    def replace(self, path=None):
        if self.project is None:
            return
        path = path or file_dialogs.askopenfilename(parent=self, title="Choose a PNG",
                                                    filetypes=[("PNG pictures", "*.png"), ("All files", "*")])
        if not path:
            return
        try:
            image = pngio.read(path)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("FM Editor", f"That PNG cannot be read: {problem}", parent=self)
            return
        if self.chosen == FLOOR_ITEM:
            notes = ba.set_floor(self.project, self.terrains(), image)
        else:
            notes = ba.set_piece(self.project, self.terrains(), ba.BY_KEY[self.chosen], image)
        self.edited(notes)

    def export(self, path=None):
        if self.project is None or not ba.disc(self.project).ok:
            return
        name = f"{self.terrain}-{self.chosen}.png"
        path = path or file_dialogs.asksaveasfilename(parent=self, title="Export the game's texture",
                                                      initialfile=name, defaultextension=".png",
                                                      filetypes=[("PNG pictures", "*.png")])
        if not path:
            return
        data = ba.disc(self.project)
        if self.chosen == FLOOR_ITEM:
            image = ba.floor_image(self.project, self.terrain, retail=True)
        else:
            image = ba.piece_image(data, self.terrain, ba.BY_KEY[self.chosen])
        pngio.write(path, image)
        self.status.configure(text=f"Wrote {path} ({image.width}x{image.height}).")

    def set_tint(self, value):
        if self.loading or self.project is None:
            return
        st = ba.state(self.project)
        if any((t, p.key) in st.pictures for t in self.terrains() for p in self.parts()):
            self.tint.set(ba.WHITE)
            self.status.configure(text="Revert the picture to tint the game's.")
            return
        ba.set_tint(self.project, self.terrains(), self.parts(), ba.WHITE if value is None else value)
        self.edited()

    def revert(self):
        if self.project is None:
            return
        ba.revert(self.project, self.terrains(), self.parts())
        self.edited()

    def revert_all(self):
        """Every field's board back as the game has it, asked first as the
        tab's other pages' Revert page is, and an undo step of its own."""
        if self.project is None or not ba.changed(self.project):
            return
        if not messagebox.askyesno("Revert page", "Put every field's duel board back as the game has it?\n\n"
                                   "Lost: the board's pictures and tints.\n\nEdit > Undo brings them back.",
                                   parent=self):
            return
        self.tab.app.flush_history()
        ba.revert_all(self.project)
        self.edited(["Every field's board is the game's again."])

    def reset_choice(self):
        """After the tab's Revert to retail: the board's floor, as it opens."""
        self.chosen = FLOOR_ITEM
