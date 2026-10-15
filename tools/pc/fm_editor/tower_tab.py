"""The Tower tab: a mod's "tower" (tower.py, notes/tower-mode.md), the run of
duels the title's second menu offers with the mod on. The tower's name, its
menu button's words, when it opens, what a loss does and its story on the
left, with the mod's duelists that only the tower lets out; its floors on
the right, each with its opponent, field, LP, rules, deck, reward and lines.
Written to the manifest as "tower", and "tower_only" on the duelists."""
from __future__ import annotations

import base64
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import duelist_rules, file_dialogs, pngio, roster, tower, tower_art
from .tabs import Tab
from .widgets import ScrolledForm

STORY_HINT = ("A line is a page or more of the campaign's stone box, over a scene with up to two of its characters. "
              "On the line before one, what changes from it on: [scene: torch corridor] [left: 1] [right: opponent] "
              "[pan: 64 0 30 wait] (the Stage box writes them). @left: / @right: said by that side, @Name: by a "
              "duelist, @none: nobody's; #N: a campaign portrait (0-24) beside the box, #speaker: the speaker's "
              "own face. \\n breaks a line inside the box; a backslash keeps the next letter as it is.")
THUMB_SCENE = (160, 80)
THUMB_CHARACTER = (96, 96)
DROPS_CHOICES = ("1", "2", "3", "5", "10", "player")


class Tip:
    """A line of help that shows under the pointer while it rests on a widget."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.window, self.job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        self.job = self.widget.after(450, self._show)

    def _show(self):
        self.job = None
        if self.window is not None or not self.widget.winfo_ismapped():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{self.widget.winfo_rootx() + 12}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 4}")
        ttk.Label(self.window, text=self.text, wraplength=380, justify="left", relief="solid", borderwidth=1,
                  padding=(6, 3)).pack()

    def _hide(self, _event=None):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class TowerTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Tower")
        self.scroll = ScrolledForm(self)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.body
        self.has = tk.BooleanVar()
        ttk.Checkbutton(body, text="This mod has a tower (a button in the title's second menu)", variable=self.has,
                        command=self.toggle).pack(anchor="w")
        ttk.Label(body, style="Hint.TLabel", text="Each floor is a duel; a save keeps how far it climbed. "
                                                  "notes/tower-mode.md says the rest.").pack(anchor="w")
        help_row = ttk.Frame(body)
        help_row.pack(anchor="w", pady=(2, 0))
        ttk.Button(help_row, text="How to build a tower...", command=self.show_guide).pack(side="left")
        start = ttk.Button(help_row, text="Start from an example", command=self.start_example)
        start.pack(side="left", padx=(6, 0))
        Tip(start, "Fills in a small working tower of three floors (with stories, a reward and an unlock) "
                   "to change as you like. It replaces the tower this mod has, after asking.")
        self.guide = None
        self.status = ttk.Label(body, style="Error.TLabel", wraplength=1100, justify="left")
        self.status.pack(anchor="w", pady=(2, 4))
        columns = ttk.Frame(body)
        columns.pack(fill="both", expand=True)
        left = ttk.Frame(columns)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        right = ttk.Frame(columns)
        right.grid(row=0, column=1, sticky="nw")
        self.vars = {}
        self.texts = {}
        self._tower_form(left)
        self._floors_form(right)
        self.floors = []          # the floors as the form edits them
        self.current = None       # the floor in the form
        self.kept = {}            # the tower's keys the form does not show, as written
        self.written = None       # the tower as the project had it when the form was filled
        self.shown = None         # (floor, form) as _show_floor filled it
        self.top_shown = None     # the tower's own form as refresh filled it

    # The fields of a floor and of the tower itself, in the form.  A form
    # nobody touched writes nothing back: the mod keeps its own spelling
    # ("Yami", {"text": ...} lines, key order) instead of the tab's.
    FLOOR_FIELDS = ("duelist", "field", "lp.player", "lp.opponent", "no_fusions", "no_equips", "checkpoint",
                    "unlock_opponent",
                    "reward.cards", "reward.starchips", "reward.unlock_duelist")
    FLOOR_TEXTS = ("deck", "before", "after")
    TOP_FIELDS = ("name", "label", "music", "unlock", "unlock.beat", "unlock.wins", "unlock.story", "unlock.card",
                  "unlock.copies", "unlock.after_ending", "on_lose", "on_leave", "drops", "save_states", "cheats",
                  "scene", "dim")
    TOP_TEXTS = ("intro", "ending", "lose")

    def _form(self, fields, texts) -> tuple:
        return tuple(self.vars[k].get() for k in fields) + tuple(self._get_text(k) for k in texts)

    # --- the form -------------------------------------------------------------------

    def _entry(self, parent, row, key, label, width=24, hint=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        var = self.vars[key] = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)
        entry.bind("<FocusOut>", lambda e: self.commit())
        entry.bind("<Return>", lambda e: self.commit())
        if hint:
            ttk.Label(parent, style="Hint.TLabel", text=hint).grid(row=row, column=2, sticky="w", padx=(4, 0))
        return entry

    def _text(self, parent, key, height=3, width=52):
        text = tk.Text(parent, height=height, width=width, wrap="none", undo=True)
        text.bind("<FocusOut>", lambda e: self.commit())
        if key != "deck":
            text.bind("<FocusIn>", lambda e, key=key: setattr(self, "last_story", key))
        self.texts[key] = text
        return text

    def _tower_form(self, parent):
        frame = ttk.LabelFrame(parent, text="The tower", padding=(6, 2))
        frame.pack(fill="x")
        self._entry(frame, 0, "name", "Name")
        self._entry(frame, 1, "label", "Menu button", hint="31 letters at most; TOWER without")
        music = self._entry(frame, 2, "music", "Music", width=8, hint="a song id, 0x000-0xFFF")
        Tip(music, "The song the tower's screen plays. Empty: the Free Duel screen's.")
        ttk.Label(frame, text="Opens").grid(row=3, column=0, sticky="w")
        self.vars["unlock"] = tk.StringVar(value="always")
        unlock = ttk.Combobox(frame, textvariable=self.vars["unlock"], values=tower.UNLOCKS, state="readonly", width=14)
        unlock.grid(row=3, column=1, sticky="w", padx=(4, 0))
        unlock.bind("<<ComboboxSelected>>", lambda e: self.commit())
        ttk.Label(frame, style="Hint.TLabel", text="after_ending: the ending seen").grid(
            row=3, column=2, sticky="w", padx=(4, 0))
        conditions = ttk.Frame(frame)
        conditions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        for column, (key, label, width) in enumerate((("beat", "beat", 14), ("wins", "wins", 4), ("story", "story", 5),
                                                      ("card", "hold", 14), ("copies", "copies", 4))):
            ttk.Label(conditions, text=label).grid(row=0, column=column * 2, sticky="w", padx=(0 if not column else 6, 2))
            var = self.vars["unlock." + key] = tk.StringVar()
            entry = ttk.Entry(conditions, textvariable=var, width=width)
            entry.grid(row=0, column=column * 2 + 1, sticky="w")
            entry.bind("<FocusOut>", lambda e: self.commit())
        self.vars["unlock.after_ending"] = tk.BooleanVar()
        ttk.Checkbutton(conditions, text="and the ending seen", variable=self.vars["unlock.after_ending"],
                        command=self.commit).grid(row=1, column=0, columnspan=6, sticky="w")
        ttk.Label(frame, text="A loss").grid(row=5, column=0, sticky="w")
        self.vars["on_lose"] = tk.StringVar(value="checkpoint")
        lose = ttk.Combobox(frame, textvariable=self.vars["on_lose"], values=("checkpoint", "restart"),
                            state="readonly", width=14)
        lose.grid(row=5, column=1, sticky="w", padx=(4, 0))
        lose.bind("<<ComboboxSelected>>", lambda e: self.commit())
        ttk.Label(frame, style="Hint.TLabel", text="last checkpoint, or floor 1").grid(
            row=5, column=2, sticky="w", padx=(4, 0))
        ttk.Label(frame, text="Scene").grid(row=6, column=0, sticky="w")
        self.vars["scene"] = tk.StringVar()
        scene = ttk.Combobox(frame, textvariable=self.vars["scene"], values=tower.SCENE_NAMES, width=22)
        scene.grid(row=6, column=1, sticky="w", padx=(4, 0))
        scene.bind("<<ComboboxSelected>>", lambda e: self.commit())
        scene.bind("<FocusOut>", lambda e: self.commit())
        Tip(scene, "The background of a story that names no scene of its own. Empty: the torch corridor.")
        ttk.Label(frame, style="Hint.TLabel", text="when a story names none").grid(
            row=6, column=2, sticky="w", padx=(4, 0))
        self.vars["dim"] = tk.BooleanVar()
        dim = ttk.Checkbutton(frame, text="Draw the character not speaking darker", variable=self.vars["dim"],
                              command=self.commit)
        dim.grid(row=7, column=0, columnspan=3, sticky="w")
        Tip(dim, "The campaign only keeps the one not speaking still; ticked, the tower also draws it darker.")
        ttk.Label(frame, text="Leaving").grid(row=8, column=0, sticky="w")
        self.vars["on_leave"] = tk.StringVar(value="resume")
        leave = ttk.Combobox(frame, textvariable=self.vars["on_leave"], values=tower.ON_LEAVE, state="readonly",
                             width=14)
        leave.grid(row=8, column=1, sticky="w", padx=(4, 0))
        leave.bind("<<ComboboxSelected>>", lambda e: self.commit())
        ttk.Label(frame, style="Hint.TLabel", text="resume, checkpoint or floor 1").grid(
            row=8, column=2, sticky="w", padx=(4, 0))
        Tip(leave, "What LEAVE (or any other way out of the tower) does to the climb. resume: the player comes "
                   "back where they were. checkpoint: back to the floor after the last checkpoint won. restart: "
                   "back to floor 1. With checkpoint or restart no save keeps a floor past it, so quitting or "
                   "saving outside the tower is no way around it.")
        ttk.Label(frame, text="Cards a win").grid(row=9, column=0, sticky="w")
        self.vars["drops"] = tk.StringVar(value=str(tower.DROPS_DEFAULT))
        drops = ttk.Combobox(frame, textvariable=self.vars["drops"], values=DROPS_CHOICES, width=8)
        drops.grid(row=9, column=1, sticky="w", padx=(4, 0))
        drops.bind("<<ComboboxSelected>>", lambda e: self.commit())
        drops.bind("<FocusOut>", lambda e: self.commit())
        drops.bind("<Return>", lambda e: self.commit())
        ttk.Label(frame, style="Hint.TLabel", text="1-99; player: Game > Card drops").grid(
            row=9, column=2, sticky="w", padx=(4, 0))
        Tip(drops, "The cards a won tower duel gives on its results screen, whatever the player set Game > "
                   "Card drops to (up to 99). \"player\" follows that setting. A floor's reward is given as well.")
        self.vars["save_states"] = tk.BooleanVar(value=True)
        states = ttk.Checkbutton(frame, text="Allow save states in the tower", variable=self.vars["save_states"],
                                 command=self.commit)
        states.grid(row=10, column=0, columnspan=3, sticky="w")
        Tip(states, "Unticked: no save state is saved or loaded while the player is in the tower (its screen, "
                    "its stories, its duels), by hotkey, menu or anything else; the game says why.")
        self.vars["cheats"] = tk.BooleanVar(value=True)
        cheats = ttk.Checkbutton(frame, text="Allow cheats in the tower", variable=self.vars["cheats"],
                                 command=self.commit)
        cheats.grid(row=11, column=0, columnspan=3, sticky="w")
        Tip(cheats, "Unticked: in the tower the Cheats menu's Starting LP and Show CPU's hand do not apply, its "
                    "Give cards, Unlock all and StarChips are refused, and during a floor's duel so are the Debug jumps and "
                    "Restart game.")
        self._stage_form(parent)
        story = ttk.LabelFrame(parent, text="Story", padding=(6, 2))
        story.pack(fill="x", pady=(4, 0))
        ttk.Label(story, style="Hint.TLabel", text=STORY_HINT, wraplength=420, justify="left").pack(anchor="w")
        for key, label in (("intro", "Before the first climb"), ("ending", "At the top"), ("lose", "After a loss")):
            ttk.Label(story, text=label).pack(anchor="w")
            self._text(story, key).pack(anchor="w", fill="x")
        only = ttk.LabelFrame(parent, text="The tower's own duelists (hidden in Free Duel until the tower lets them out)",
                              padding=(6, 2))
        only.pack(fill="x", pady=(4, 0))
        ttk.Label(only, style="Hint.TLabel", wraplength=420, justify="left",
                  text="Checked: not in Free Duel until a won floor fights it or names it in its reward "
                       "(\"tower_only\"). The mod's added duelists, from the Duelists tab.").pack(anchor="w")
        self.only = tk.Listbox(only, selectmode="multiple", height=5, exportselection=False)
        self.only.pack(anchor="w", fill="x")
        self.only.bind("<<ListboxSelect>>", lambda e: self.commit())
        self.only_keys = []

    # --- the stage: pickers that write a story's bracketed lines ----------------------

    def _stage_form(self, parent):
        frame = ttk.LabelFrame(parent, text="Stage (into the story last clicked, before its line)", padding=(6, 2))
        frame.pack(fill="x", pady=(4, 0))
        self.last_story = "intro"
        scenes = list(tower.SCENE_NAMES) + [str(m * 100 + i) for m, count in ((1, 42), (2, 13)) for i in range(count)]
        self.stage_scene = tk.StringVar(value=tower.SCENE_NAMES[tower.SCENE_DEFAULT])
        box = ttk.Combobox(frame, textvariable=self.stage_scene, values=scenes, state="readonly", width=22)
        box.grid(row=0, column=0, sticky="w")
        box.bind("<<ComboboxSelected>>", lambda e: self._preview())
        ttk.Button(frame, text="Scene", command=lambda: self._insert(f"[scene: {self.stage_scene.get()}]")).grid(
            row=0, column=1, sticky="w", padx=4)
        ttk.Button(frame, text="Scene PNG...", command=self._scene_png).grid(row=0, column=2, sticky="w")
        self.stage_character = tk.StringVar(value="1")
        characters = [str(n) for n in range(1, tower.CHARACTERS + 1) if n not in tower.EMPTY_CHARACTERS]
        box = ttk.Combobox(frame, textvariable=self.stage_character, values=characters, state="readonly", width=6)
        box.grid(row=1, column=0, sticky="w", pady=(2, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self._preview())
        self.stage_side = tk.StringVar(value="left")
        sides = ttk.Frame(frame)
        sides.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 0))
        for side in tower.SIDES:
            ttk.Radiobutton(sides, text=side, value=side, variable=self.stage_side).pack(side="left")
        self.stage_expression = tk.StringVar(value="0")
        ttk.Label(sides, text="expression").pack(side="left", padx=(6, 2))
        ttk.Spinbox(sides, from_=0, to=3, width=2, textvariable=self.stage_expression).pack(side="left")
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Button(buttons, text="Character", command=self._character).pack(side="left")
        ttk.Button(buttons, text="The opponent",
                   command=lambda: self._insert(f"[{self.stage_side.get()}: opponent]")).pack(side="left", padx=4)
        ttk.Button(buttons, text="Nobody", command=lambda: self._insert(f"[{self.stage_side.get()}: none]")).pack(
            side="left")
        ttk.Button(buttons, text="Character PNG...", command=self._character_png).pack(side="left", padx=4)
        self.stage_flip = tk.BooleanVar()
        ttk.Checkbutton(buttons, text="flip", variable=self.stage_flip).pack(side="left")
        pictures = ttk.Frame(frame)
        pictures.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.scene_picture = ttk.Label(pictures, text="(the scenes and characters show with the game's files)")
        self.scene_picture.pack(side="left")
        self.character_picture = ttk.Label(pictures)
        self.character_picture.pack(side="left", padx=(6, 0))
        self._photos = {}

    def _photo(self, key, image, size):
        if image is None:
            return None
        if key not in self._photos:
            scale = min(size[0] / image.width, size[1] / image.height)
            image = pngio.scale_to(image, max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            self._photos[key] = tk.PhotoImage(master=self.winfo_toplevel(),
                                              data=base64.b64encode(pngio.encode(image)), format="png")
        return self._photos[key]

    def _preview(self):
        """The chosen scene and character, made from the player's disc now
        (tower_art.py) and kept in memory; nothing of the disc's is written."""
        files = getattr(self.app, "files", None)
        wa = getattr(files, "wa", None) if files is not None else None
        if wa is None:
            return
        number = tower.scene_number(self.stage_scene.get())
        if isinstance(number, int):
            scene = (number // 100) << 8 | (number % 100 // 10) << 4 | number % 10
            photo = self._photo(("scene", number), tower_art.scene_image(wa, scene), THUMB_SCENE)
            self.scene_picture.configure(image=photo or "", text="" if photo else "(none)")
        character = int(self.stage_character.get() or 0)
        photo = self._photo(("character", character), tower_art.character_image(wa, character), THUMB_CHARACTER)
        self.character_picture.configure(image=photo or "")

    def _insert(self, directive: str):
        """A bracketed line before the line the cursor is on, in the story
        last clicked."""
        text = self.texts.get(self.last_story)
        if text is None:
            return
        text.insert(text.index("insert linestart"), directive + "\n")
        self.commit()

    def _character(self):
        expression = self.stage_expression.get().strip()
        words = self.stage_character.get() + (f" expression {expression}" if expression not in ("", "0") else "")
        self._insert(f"[{self.stage_side.get()}: {words}]")

    def _mod_png(self, title: str):
        """A PNG for the mod: its path inside the mod's folder, or, from
        elsewhere, copied into the mod's tower/ when it is saved."""
        path = file_dialogs.askopenfilename(parent=self, title=title,
                                            filetypes=[("PNG pictures", "*.png"), ("All files", "*")])
        if not path or self.project is None:
            return None
        return self.use_png(path)

    def use_png(self, path):
        try:
            data = Path(path).read_bytes()
            pngio.decode(data)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Picture", f"{path} cannot be used: {problem}", parent=self)
            return None
        source = getattr(self.project, "source_dir", None)
        if source:
            try:
                return Path(path).resolve().relative_to(Path(source).resolve()).as_posix()
            except ValueError:
                pass
        stem, n = Path(path).stem, 1
        name = f"tower/{stem}.png"
        while name in self.project.files and self.project.files[name] != data:   # another picture's name
            n += 1
            name = f"tower/{stem}-{n}.png"
        self.project.files[name] = data
        return name

    def _scene_png(self):
        name = self._mod_png("A scene for the story (drawn at 320 x 160)")
        if name:
            self._insert(f"[scene: {name}]")

    def _character_png(self):
        name = self._mod_png("A character for the story (up to 256 x 256, standing on the box)")
        if name:
            self._insert(f"[{self.stage_side.get()}: {name}{' flip' if self.stage_flip.get() else ''}]")

    # --- help, the example, the floor's unlocks ----------------------------------------

    def show_guide(self):
        """The steps of building a tower, in a window of their own."""
        if self.guide is not None and self.guide.winfo_exists():
            self.guide.lift()
            return
        self.guide = tk.Toplevel(self)
        self.guide.title("How to build a tower")
        frame = ttk.Frame(self.guide)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, width=72, height=30, wrap="word", padx=10, pady=8, font="TkDefaultFont")
        bar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.tag_configure("head", font=("TkDefaultFont", 10, "bold"))
        for head, body in tower.GUIDE:
            text.insert("end", head + "\n", "head")
            text.insert("end", body + "\n\n")
        text.insert("end", "Every key, with an example: notes/tower-mode.md (Help > Tower mode).")
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        buttons = ttk.Frame(self.guide, padding=(8, 4))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Start from an example", command=self.start_example).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.guide.destroy).pack(side="right")

    def start_example(self, ask=True):
        if self.project is None:
            return
        if ask and self.project.other.get("tower") is not None and not messagebox.askyesno(
                "Start from an example", "Replace this mod's tower with the example?", parent=self):
            return
        self.project.other["tower"] = tower.example_tower()
        self.refresh()
        self.app.changed()

    @staticmethod
    def _drops_shown(value) -> str:
        """The drops as the game reads them: 1-99, "player", else the default."""
        if isinstance(value, str) and value.lower() == "player":
            return "player"
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= tower.DROPS_MAX:
            return str(value)
        return str(tower.DROPS_DEFAULT)

    def _duelist_of_floor(self):
        text = self.vars["duelist"].get().strip()
        return roster.named(self.project, text) if self.project is not None and text else None

    def _unlock_default(self) -> bool:
        """Whether a floor that does not say so lets its opponent into Free
        Duel: a duelist the mod adds as the tower's own, yes; any other, no."""
        e = self._duelist_of_floor()
        return e is not None and not isinstance(e, int) and getattr(e, "extra", {}).get("tower_only") is True

    def _unlock_touched(self):
        self.unlock_touched = True
        self.commit()

    def _unlock_note(self):
        e = self._duelist_of_floor()
        if e is None:
            text = ""
        elif not isinstance(e, int) and e.extra.get("tower_only") is True:
            text = "This opponent is the tower's own: hidden in Free Duel until it is beaten (if ticked)."
        else:
            text = "Ticked, beating it puts this opponent on the Free Duel grid."
        self.unlock_hint.configure(text=text)

    def _unlock_choices(self):
        if self.project is not None:
            self.unlock_box.configure(values=duelist_rules.references(self.project))

    def _add_unlock(self):
        pick = self.unlock_pick.get().strip()
        if not pick:
            return
        names = [n.strip() for n in self.vars["reward.unlock_duelist"].get().split(",") if n.strip()]
        if pick not in names:
            names.append(pick)
        self.vars["reward.unlock_duelist"].set(", ".join(names))
        self.commit()

    def _remove_unlock(self):
        names = [n.strip() for n in self.vars["reward.unlock_duelist"].get().split(",") if n.strip()]
        self.vars["reward.unlock_duelist"].set(", ".join(names[:-1]))
        self.commit()

    def _floors_form(self, parent):
        frame = ttk.LabelFrame(parent, text="Floors", padding=(6, 2))
        frame.pack(fill="x")
        self.list = ttk.Treeview(frame, columns=("duelist", "field", "rules"), height=6, selectmode="browse")
        self.list.heading("#0", text="#")
        self.list.heading("duelist", text="Opponent")
        self.list.heading("field", text="Field")
        self.list.heading("rules", text="Rules")
        self.list.column("#0", width=40)
        self.list.column("duelist", width=160)
        self.list.column("field", width=80)
        self.list.column("rules", width=190)
        self.list.pack(fill="x")
        self.list.bind("<<TreeviewSelect>>", lambda e: self.pick())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(2, 0))
        for label, command in (("Add floor", self.add), ("Remove", self.remove), ("Up", lambda: self.move(-1)),
                               ("Down", lambda: self.move(1))):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=(0, 4))
        form = ttk.LabelFrame(parent, text="The floor", padding=(6, 2))
        form.pack(fill="x", pady=(4, 0))
        ttk.Label(form, text="Opponent").grid(row=0, column=0, sticky="w")
        self.vars["duelist"] = tk.StringVar()
        self.duelist_box = ttk.Combobox(form, textvariable=self.vars["duelist"], width=22,
                                        postcommand=self.duelist_choices)
        self.duelist_box.grid(row=0, column=1, sticky="w", padx=(4, 0))
        self.duelist_box.bind("<<ComboboxSelected>>", lambda e: self.commit())
        self.duelist_box.bind("<FocusOut>", lambda e: self.commit())
        ttk.Label(form, text="Field").grid(row=1, column=0, sticky="w")
        self.vars["field"] = tk.StringVar(value="none")
        field = ttk.Combobox(form, textvariable=self.vars["field"], values=tower.TERRAINS, state="readonly", width=12)
        field.grid(row=1, column=1, sticky="w", padx=(4, 0))
        field.bind("<<ComboboxSelected>>", lambda e: self.commit())
        lp = ttk.Frame(form)
        lp.grid(row=2, column=0, columnspan=2, sticky="w")
        for column, (key, label) in enumerate((("lp.player", "Your LP"), ("lp.opponent", "Its LP"))):
            ttk.Label(lp, text=label).grid(row=0, column=column * 2, sticky="w", padx=(0 if not column else 8, 2))
            var = self.vars[key] = tk.StringVar()
            entry = ttk.Entry(lp, textvariable=var, width=7)
            entry.grid(row=0, column=column * 2 + 1)
            entry.bind("<FocusOut>", lambda e: self.commit())
        ttk.Label(lp, style="Hint.TLabel", text="empty: the usual").grid(row=0, column=4, padx=(6, 0))
        flags = ttk.Frame(form)
        flags.grid(row=3, column=0, columnspan=2, sticky="w")
        for key, label in (("no_fusions", "No fusions"), ("no_equips", "No equips"),
                           ("checkpoint", "Checkpoint (a loss after it comes back here)")):
            self.vars[key] = tk.BooleanVar()
            ttk.Checkbutton(flags, text=label, variable=self.vars[key], command=self.commit).pack(side="left",
                                                                                                padx=(0, 8))
        self.vars["unlock_opponent"] = tk.BooleanVar()
        unlock_box = ttk.Checkbutton(form, text="Unlock this opponent in Free Duel when beaten",
                                     variable=self.vars["unlock_opponent"], command=self._unlock_touched)
        unlock_box.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
        Tip(unlock_box, "Beaten for the first time, the floor's opponent appears on the Free Duel grid. A duelist "
                        "the mod adds as the tower's own (tower_only) is hidden there until then; unticked, it "
                        "stays hidden.")
        self.unlock_hint = ttk.Label(form, style="Hint.TLabel")
        self.unlock_hint.grid(row=5, column=0, columnspan=2, sticky="w")
        reward = ttk.Frame(form)
        reward.grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 0))
        for row, (key, label, width, hint) in enumerate((
                ("reward.cards", "Reward cards", 34, "names or ids, a comma between"),
                ("reward.starchips", "Starchips", 8, "the first win only"))):
            ttk.Label(reward, text=label).grid(row=row, column=0, sticky="w")
            var = self.vars[key] = tk.StringVar()
            entry = ttk.Entry(reward, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)
            entry.bind("<FocusOut>", lambda e: self.commit())
            ttk.Label(reward, style="Hint.TLabel", text=hint).grid(row=row, column=2, sticky="w", padx=(4, 0))
        ttk.Label(reward, text="Also unlocks").grid(row=2, column=0, sticky="w")
        self.vars["reward.unlock_duelist"] = tk.StringVar()
        ttk.Entry(reward, textvariable=self.vars["reward.unlock_duelist"], width=34, state="readonly").grid(
            row=2, column=1, sticky="w", padx=(4, 0), pady=1)
        pick = ttk.Frame(reward)
        pick.grid(row=3, column=1, columnspan=2, sticky="w", padx=(4, 0))
        self.unlock_pick = tk.StringVar()
        self.unlock_box = ttk.Combobox(pick, textvariable=self.unlock_pick, width=22, state="readonly",
                                       postcommand=self._unlock_choices)
        self.unlock_box.pack(side="left")
        ttk.Button(pick, text="Add", command=self._add_unlock).pack(side="left", padx=(4, 0))
        ttk.Button(pick, text="Remove last", command=self._remove_unlock).pack(side="left", padx=(4, 0))
        Tip(self.unlock_box, "More duelists this floor puts on the Free Duel grid the first time it is won: the "
                             "disc's or the mod's own.")
        ttk.Label(form, text="Its deck").grid(row=7, column=0, sticky="nw")
        deck = ttk.Frame(form)
        deck.grid(row=7, column=1, sticky="w", padx=(4, 0))
        self._text(deck, "deck", height=4, width=40).pack(anchor="w")
        ttk.Label(deck, style="Hint.TLabel", text="a card a line, \"Card x3\"; forty in all, or empty for its own"
                  ).pack(anchor="w")
        for row, (key, label) in enumerate((("before", "Before the duel"), ("after", "After a win")), start=8):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="nw")
            self._text(form, key, height=3, width=46).grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)

    # --- the floors list ----------------------------------------------------------

    def duelist_choices(self):
        if self.project is not None:
            self.duelist_box.configure(values=duelist_rules.references(self.project))

    def _floor_row(self, index, floor):
        rules = []
        if floor.get("no_fusions") is True:
            rules.append("no fusions")
        if floor.get("no_equips") is True:
            rules.append("no equips")
        if floor.get("life_points") is not None:
            rules.append("LP")
        if floor.get("deck") is not None:
            rules.append("deck")
        if floor.get("checkpoint") is True:
            rules.append("checkpoint")
        field = tower.terrain_of(floor.get("field"))
        return (str(floor.get("duelist", "")), tower.TERRAINS[field] if field is not None else str(floor.get("field")),
                ", ".join(rules))

    def _fill_list(self):
        self.list.delete(*self.list.get_children())
        for index, floor in enumerate(self.floors):
            values = self._floor_row(index, floor) if isinstance(floor, dict) else ("(not an object)", "", "")
            self.list.insert("", "end", iid=str(index), text=str(index + 1), values=values)
        if self.current is not None and self.current < len(self.floors):
            self.list.selection_set(str(self.current))

    def _show_floor(self):
        floor = self.floors[self.current] if self.current is not None and self.current < len(self.floors) else {}
        floor = floor if isinstance(floor, dict) else {}
        self.vars["duelist"].set(str(floor.get("duelist", "")))
        field = tower.terrain_of(floor.get("field"))
        self.vars["field"].set(tower.TERRAINS[field] if field is not None else "none")
        lp = floor.get("life_points")
        sides = lp if isinstance(lp, dict) else {"player": lp, "opponent": lp} if lp is not None else {}
        self.vars["lp.player"].set("" if sides.get("player") is None else str(sides["player"]))
        self.vars["lp.opponent"].set("" if sides.get("opponent") is None else str(sides["opponent"]))
        for key in ("no_fusions", "no_equips", "checkpoint"):
            self.vars[key].set(floor.get(key) is True)
        reward = floor.get("reward") if isinstance(floor.get("reward"), dict) else {}
        cards = []
        for key in ("card", "cards"):
            value = reward.get(key)
            cards += value if isinstance(value, list) else [] if value is None else [value]
        self.vars["reward.cards"].set(tower.names_text(cards))
        self.vars["reward.starchips"].set("" if reward.get("starchips") is None else str(reward["starchips"]))
        self.vars["reward.unlock_duelist"].set(tower.names_text(reward.get("unlock_duelist")))
        self.unlock_touched = False
        self.vars["unlock_opponent"].set(floor["unlock_opponent"] is True if isinstance(floor.get("unlock_opponent"),
                                                                                       bool)
                                         else self._unlock_default())
        self._unlock_note()
        self._set_text("deck", tower.deck_text(floor.get("deck")))
        self._set_text("before", tower.story_text(floor.get("before")))
        self._set_text("after", tower.story_text(floor.get("after")))
        self.shown = (self.current, self._form(self.FLOOR_FIELDS, self.FLOOR_TEXTS))

    def _set_text(self, key, value):
        text = self.texts[key]
        text.delete("1.0", "end")
        text.insert("1.0", value)
        text.edit_reset()

    def _get_text(self, key) -> str:
        return self.texts[key].get("1.0", "end-1c")

    def _read_floor(self) -> dict:
        """The form's floor, over the floor's own keys the form does not show."""
        old = self.floors[self.current] if self.current is not None and self.current < len(self.floors) else {}
        old = old if isinstance(old, dict) else {}
        floor = {k: tower.copy(v) for k, v in old.items() if k not in tower.FLOOR_KEYS}
        duelist = self.vars["duelist"].get().strip()
        floor["duelist"] = int(duelist) if duelist.isdigit() else duelist
        field = self.vars["field"].get()
        if field and field != "none":
            # The terrain as the mod wrote it ("Yami" is "Dark") while it is the same one.
            same = "field" in old and tower.terrain_of(old["field"]) == tower.terrain_of(field)
            floor["field"] = old["field"] if same else field
        sides = {}
        for side in ("player", "opponent"):
            text = self.vars["lp." + side].get().strip()
            if text:
                sides[side] = int(text) if text.isdigit() else text
        if sides:
            floor["life_points"] = sides["player"] if len(sides) == 2 and sides["player"] == sides["opponent"] \
                else sides
        for key in ("no_fusions", "no_equips"):
            if self.vars[key].get():
                floor[key] = True
        deck = tower.deck_value(self._get_text("deck"))
        if deck is not None:
            floor["deck"] = deck if old.get("deck") is None or tower.deck_value(tower.deck_text(old["deck"])) != deck \
                else old["deck"]
        reward = {k: tower.copy(v) for k, v in (old.get("reward") or {}).items()
                  if isinstance(old.get("reward"), dict) and k not in tower.REWARD_KEYS}
        cards = tower.names_value(self.vars["reward.cards"].get())
        if cards is not None:
            reward["cards"] = cards if isinstance(cards, list) else [cards]
        chips = self.vars["reward.starchips"].get().strip()
        if chips:
            reward["starchips"] = int(chips) if chips.isdigit() else chips
        duelists = tower.names_value(self.vars["reward.unlock_duelist"].get())
        if duelists is not None:
            reward["unlock_duelist"] = duelists
        if reward:
            floor["reward"] = reward
        if self.vars["checkpoint"].get():
            floor["checkpoint"] = True
        # Written when the mod had it or the box was ticked or unticked by
        # hand; else the box follows the opponent's default (a tower-only
        # one unlocks, any other not) as the opponent changes.
        unlock = self.vars["unlock_opponent"].get()
        if "unlock_opponent" in old or getattr(self, "unlock_touched", False):
            floor["unlock_opponent"] = unlock
        else:
            self.vars["unlock_opponent"].set(self._unlock_default())
            self._unlock_note()
        for key in ("before", "after"):
            value = tower.story_value(self._get_text(key))
            if value is not None:
                floor[key] = old[key] if tower.same_story(old.get(key), self._get_text(key)) else value
        order = list(tower.FLOOR_KEYS)
        return {**{k: floor[k] for k in order if k in floor}, **{k: v for k, v in floor.items() if k not in order}}

    def _store_floor(self):
        if self.current is not None and self.current < len(self.floors):
            if self.shown == (self.current, self._form(self.FLOOR_FIELDS, self.FLOOR_TEXTS)):
                return
            self.floors[self.current] = self._read_floor()
            self.shown = (self.current, self._form(self.FLOOR_FIELDS, self.FLOOR_TEXTS))

    def pick(self):
        chosen = self.list.selection()
        if not chosen or int(chosen[0]) == self.current:
            return
        self.commit()
        self.current = int(chosen[0])
        self._show_floor()

    def add(self):
        if self.project is None:
            return
        self._store_floor()
        if len(self.floors) >= tower.TOWER_MAX_FLOORS:
            self.status.configure(text=f"A tower has at most {tower.TOWER_MAX_FLOORS} floors")
            return
        self.has.set(True)
        self.floors.append(tower.new_floor())
        self.current = len(self.floors) - 1
        self._fill_list()
        self._show_floor()
        self.commit()

    def remove(self):
        if self.current is None or self.current >= len(self.floors):
            return
        del self.floors[self.current]
        self.current = min(self.current, len(self.floors) - 1) if self.floors else None
        self._fill_list()
        self._show_floor()
        self.commit(stored=True)

    def move(self, step):
        if self.current is None:
            return
        self._store_floor()
        to = self.current + step
        if not 0 <= to < len(self.floors):
            return
        self.floors[self.current], self.floors[to] = self.floors[to], self.floors[self.current]
        self.current = to
        if self.shown is not None:
            self.shown = (to, self.shown[1])   # the same floor, still in the form
        self._fill_list()
        self.commit(stored=True)

    def toggle(self):
        if self.project is None:
            return
        if self.has.get() and not self.floors:
            self.floors = [tower.new_floor()]
            self.current = 0
            self._fill_list()
            self._show_floor()
        self.commit()

    # --- the tab --------------------------------------------------------------------

    def refresh(self):
        if self.project is None:
            return
        value = self.project.other.get("tower")
        written = value if isinstance(value, dict) else {}
        self.has.set(value is not None)
        self.written = value
        self.kept ={k: tower.copy(v) for k, v in written.items() if k not in tower.TOWER_KEYS}
        self.vars["name"].set(str(written.get("name", "")))
        self.vars["label"].set(str(written.get("label", "")))
        self.vars["music"].set("" if written.get("music") is None else str(written["music"]))
        unlock = written.get("unlock")
        self.vars["unlock"].set("conditions" if isinstance(unlock, dict) else
                                unlock if unlock in ("always", "after_ending") else "always")
        conditions = unlock if isinstance(unlock, dict) else {}
        for key in ("beat", "wins", "story", "card", "copies"):
            self.vars["unlock." + key].set("" if conditions.get(key) is None else str(conditions[key]))
        self.vars["unlock.after_ending"].set(conditions.get("after_ending") is True)
        self.vars["on_lose"].set(written.get("on_lose") if written.get("on_lose") in ("checkpoint", "restart")
                                 else "checkpoint")
        scene = written.get("scene")
        number = tower.scene_number(scene) if scene is not None else None
        self.vars["scene"].set("" if scene is None else tower.scene_label(number) if number is not None else str(scene))
        self.vars["dim"].set(written.get("dim") is True)
        leave = str(written.get("on_leave", "resume")).lower()
        self.vars["on_leave"].set(leave if leave in tower.ON_LEAVE else "resume")
        self.vars["drops"].set(self._drops_shown(written.get("drops")))
        # As the game reads them: only false turns one off (a wrong value is as if not written).
        self.vars["save_states"].set(written.get("save_states") is not False)
        self.vars["cheats"].set(written.get("cheats") is not False)
        self._preview()
        for key in ("intro", "ending", "lose"):
            self._set_text(key, tower.story_text(written.get(key)))
        floors = written.get("floors")
        self.floors = [tower.copy(f) if isinstance(f, dict) else f for f in floors] if isinstance(floors, list) else []
        self.current = 0 if self.floors else None
        self._fill_list()
        self._show_floor()
        self.top_shown = self._form(self.TOP_FIELDS, self.TOP_TEXTS)
        self.only_keys = [e.key for e in roster.copies(self.project)]
        self.only.delete(0, "end")
        marked = set(tower.tower_only(self.project))
        for index, key in enumerate(self.only_keys):
            self.only.insert("end", f"{roster.identity(self.project, roster.find(self.project, key))}")
            if key in marked:
                self.only.selection_set(index)
        self._report()

    def _build(self) -> dict | None:
        if not self.has.get():
            return None
        written = self.written if isinstance(self.written, dict) else None
        if written is not None and self.top_shown == self._form(self.TOP_FIELDS, self.TOP_TEXTS):
            # The tower's own fields untouched: only the floors can change.
            out = tower.copy(written)
            if "floors" in out or self.floors:
                out["floors"] = [tower.copy(f) for f in self.floors]
            return out
        out = {}
        for key in ("name", "label"):
            text = self.vars[key].get().strip()
            if text:
                out[key] = text
        music = self.vars["music"].get().strip()
        if music:
            try:
                out["music"] = int(music, 0)
            except ValueError:
                out["music"] = music
        kind = self.vars["unlock"].get()
        if kind == "after_ending":
            out["unlock"] = "after_ending"
        elif kind == "conditions":
            conditions = {}
            if self.vars["unlock.after_ending"].get():
                conditions["after_ending"] = True
            for key in ("beat", "wins", "story", "card", "copies"):
                text = self.vars["unlock." + key].get().strip()
                if text:
                    conditions[key] = int(text) if text.isdigit() else text
            out["unlock"] = conditions
        if self.vars["on_lose"].get() == "restart":
            out["on_lose"] = "restart"
        scene = self.vars["scene"].get().strip()
        if scene:
            old = written.get("scene") if written is not None else None
            number = tower.scene_number(scene)
            out["scene"] = old if old is not None and tower.scene_number(old) == number else \
                number if isinstance(number, int) and scene.isdigit() else scene
        if self.vars["dim"].get():
            out["dim"] = True
        if self.vars["on_leave"].get() in ("checkpoint", "restart"):
            out["on_leave"] = self.vars["on_leave"].get()
        drops = self.vars["drops"].get().strip().lower()
        old_drops = written.get("drops") if written is not None else None
        if drops == "player":
            out["drops"] = old_drops if str(old_drops).lower() == "player" else "player"
        elif drops.isdigit() and 1 <= int(drops) <= tower.DROPS_MAX and int(drops) != tower.DROPS_DEFAULT:
            out["drops"] = int(drops)
        self.vars["drops"].set(self._drops_shown(out.get("drops")))
        for key in ("save_states", "cheats"):
            if not self.vars[key].get():
                out[key] = False
        for key in ("intro", "ending", "lose"):
            value = tower.story_value(self._get_text(key))
            if value is not None:
                old = written.get(key) if written is not None else None
                out[key] = old if tower.same_story(old, self._get_text(key)) else value
        out["floors"] = [tower.copy(f) for f in self.floors]
        out.update(self.kept)
        return out

    def _report(self):
        if self.project is None:
            return
        problems = tower.check(self.project.other.get("tower"), lambda name: roster.named(self.project, name),
                               lambda name: self.project.resolve(name))
        self.status.configure(text="\n".join(f"{level}: {where}: {message}" for level, where, message in problems))
        for index, floor in enumerate(self.floors):
            if isinstance(floor, dict) and self.list.exists(str(index)):
                self.list.item(str(index), values=self._floor_row(index, floor))

    def commit(self, stored=False):
        if self.project is None:
            return True
        if not stored:
            self._store_floor()
        before = self.project.other.get("tower")
        after = self._build()
        # Untouched, the tower stays as the mod wrote it: every tab switch
        # commits, and rebuilding it would reorder its keys and mark the mod
        # changed.
        if after is not None and before is not None and tower.copy(after) == before:
            after = before
        if after is None:
            self.project.other.pop("tower", None)
        else:
            self.project.other["tower"] = after
        changed = after != before
        selected = {self.only_keys[i] for i in self.only.curselection()} if self.only_keys else set()
        for key in self.only_keys:
            changed = tower.set_tower_only(self.project, key, key in selected) or changed
        self._report()
        if changed:
            self.app.changed()
        self.applied()
        return True
