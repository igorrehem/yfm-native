"""The Fusions tab's "Bulk..." window: every pair of the cards chosen as A
with the cards chosen as B made into a card, or taken away, with a preview
before anything changes (bulk_fusions.py holds the rules)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import bulk_fusions as bulk, theme
from .gamedata import ATTRIBUTE_NAMES, STAR_NAMES, TYPE_NAMES
from .widgets import CardField, grab, px, scrolled_tree, show_text, ui_font

MONSTER_TYPES = TYPE_NAMES[:20]
DELAY = 300          # ms of quiet before the preview is worked out again


def _number(text: str):
    """A bound: a whole number, or None when blank; ValueError otherwise."""
    text = text.strip()
    if not text:
        return None
    return int(text)


# The conditions a side can have, in the order they show: (key, label).
# A side shows only those added (or holding something), not all of them.
CONDITIONS = (("kind", "Kind"), ("type", "Monster type"), ("attribute", "Attribute"), ("star", "Guardian star"),
              ("atk", "ATK"), ("def", "DEF"), ("level", "Level"), ("name", "Name has"), ("text", "Text has"),
              ("cards", "Cards"), ("result", "Made by a fusion"))


class FilterPanel(ttk.LabelFrame):
    """One side's cards: any card, narrowed by the conditions added (all of
    them hold for a card to be chosen)."""

    def __init__(self, master, title, on_change, star_names=None):
        super().__init__(master, text=title, padding=8)
        self.on_change = on_change
        self.kinds = {k: tk.BooleanVar() for k in bulk.KINDS}
        self.attributes = [tk.BooleanVar() for _ in ATTRIBUTE_NAMES]
        self.texts = {k: tk.StringVar() for k in ("atk_min", "atk_max", "def_min", "def_max", "level_min",
                                                  "level_max", "name", "text", "cards")}
        self.results_only = tk.BooleanVar()
        self.added = set()         # conditions shown though still empty
        self.other = None          # the other side (Copy from)

        head = ttk.Frame(self)
        head.pack(fill="x")
        self.count = ttk.Label(head, font=ui_font(13))
        self.count.pack(side="left")
        link = ttk.Label(head, text="List", style="Changed.TLabel", cursor="hand2")
        link.pack(side="left", padx=8, pady=(4, 0))
        link.bind("<Button-1>", lambda e: self.list_cards())
        self.summary = ttk.Label(self, text="Any card. Add a condition to narrow it.", style="Hint.TLabel")

        self.box = ttk.Frame(self)
        self.box.pack(fill="x", pady=(6, 0))
        self.box.columnconfigure(1, weight=1)
        self.rows = {key: self._row(key, label, star_names) for key, label in CONDITIONS}

        line = ttk.Frame(self)
        line.pack(fill="x", pady=(8, 0))
        self.add_button = ttk.Menubutton(line, text="+ Add condition")
        self.add_menu = tk.Menu(self.add_button, tearoff=False)
        self.add_button["menu"] = self.add_menu
        for key, label in CONDITIONS:
            self.add_menu.add_command(label=label, command=lambda k=key: self.add(k))
        self.add_button.pack(side="left")
        ttk.Button(line, text="Clear", command=self.clear).pack(side="right")
        self.copy_button = ttk.Button(line, text="Copy from", command=lambda: self.write(self.other))
        self.copy_button.pack(side="right", padx=4)
        for var in self.texts.values():
            var.trace_add("write", lambda *_: on_change())
        self.chosen = []
        self.project = None
        self.sync()

    # --- the rows -------------------------------------------------------------------

    def _row(self, key, label, star_names):
        caption = ttk.Label(self.box, text=label)
        body = ttk.Frame(self.box)
        if key == "kind":
            for n, (kind, var) in enumerate(self.kinds.items()):
                ttk.Checkbutton(body, text=kind.capitalize(), variable=var, command=self.on_change).grid(
                    row=n // 3, column=n % 3, sticky="w", padx=(0, 6))
        elif key == "attribute":
            for n, (name, var) in enumerate(zip(ATTRIBUTE_NAMES, self.attributes)):
                ttk.Checkbutton(body, text=name, variable=var, command=self.on_change).grid(
                    row=n // 3, column=n % 3, sticky="w", padx=(0, 6))
        elif key == "type":
            self.types = self._listbox(body, MONSTER_TYPES)
        elif key == "star":
            self.stars = self._listbox(body, star_names or STAR_NAMES[1:])
        elif key in ("atk", "def", "level"):
            ttk.Entry(body, textvariable=self.texts[key + "_min"], width=7).pack(side="left")
            ttk.Label(body, text="to").pack(side="left", padx=4)
            ttk.Entry(body, textvariable=self.texts[key + "_max"], width=7).pack(side="left")
        elif key == "result":
            caption.configure(text="Only cards a fusion makes")
        else:
            ttk.Entry(body, textvariable=self.texts[key]).pack(fill="x")
            if key == "cards":
                ttk.Label(body, text="numbers, 10-20 or names, comma between", style="Hint.TLabel").pack(
                    anchor="w")
        remove = ttk.Label(self.box, text="✕", cursor="hand2", style="Hint.TLabel")
        remove.bind("<Button-1>", lambda e: self.remove(key))
        return caption, body, remove

    def _listbox(self, master, names):
        frame = ttk.Frame(master)
        frame.pack(fill="x")
        box = tk.Listbox(frame, selectmode="multiple", height=5, exportselection=False, activestyle="none")
        for name in names:
            box.insert("end", name)
        bar = ttk.Scrollbar(frame, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=bar.set)
        box.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        box.bind("<<ListboxSelect>>", lambda e: self.on_change())
        return box

    def holds(self, key) -> bool:
        """The condition has something in it."""
        if key == "kind":
            return any(v.get() for v in self.kinds.values())
        if key == "attribute":
            return any(v.get() for v in self.attributes)
        if key == "type":
            return bool(self.types.curselection())
        if key == "star":
            return bool(self.stars.curselection())
        if key == "result":
            return self.results_only.get()
        if key in ("atk", "def", "level"):
            return bool(self.texts[key + "_min"].get().strip() or self.texts[key + "_max"].get().strip())
        return bool(self.texts[key].get().strip())

    def sync(self):
        """Show the conditions added or holding something, the others in the menu."""
        shown = []
        for n, (key, label) in enumerate(CONDITIONS):
            caption, body, remove = self.rows[key]
            visible = key in self.added or self.holds(key)
            if visible:
                shown.append(label)
                if key == "result":
                    caption.grid(row=n, column=0, columnspan=2, sticky="w", pady=2)
                else:
                    caption.grid(row=n, column=0, sticky="nw", pady=2, padx=(0, 8))
                    body.grid(row=n, column=1, sticky="we", pady=2)
                remove.grid(row=n, column=2, sticky="ne", padx=(6, 0), pady=2)
            else:
                for widget in (caption, body, remove):
                    widget.grid_remove()
            self.add_menu.entryconfigure(n, state="disabled" if visible else "normal")
        if not shown:
            self.box.configure(height=1)
        if shown:
            self.summary.pack_forget()
        else:
            self.summary.pack(fill="x", before=self.box)

    def add(self, key):
        self.added.add(key)
        if key == "result":
            self.results_only.set(True)
        self.sync()
        body = self.rows[key][1]
        entry = next((w for w in body.winfo_children() if isinstance(w, (ttk.Entry, tk.Listbox))), None)
        if entry is not None:
            entry.focus_set()
        self.on_change()

    def remove(self, key):
        self.added.discard(key)
        if key == "kind":
            for var in self.kinds.values():
                var.set(False)
        elif key == "attribute":
            for var in self.attributes:
                var.set(False)
        elif key == "type":
            self.types.selection_clear(0, "end")
        elif key == "star":
            self.stars.selection_clear(0, "end")
        elif key == "result":
            self.results_only.set(False)
        elif key in ("atk", "def", "level"):
            self.texts[key + "_min"].set("")
            self.texts[key + "_max"].set("")
        else:
            self.texts[key].set("")
        self.sync()
        self.on_change()

    # --- reading and writing ----------------------------------------------------------

    def read(self) -> bulk.CardFilter:
        """The filter; ValueError naming a bound that is not a number."""
        numbers = {}
        for key in ("atk_min", "atk_max", "def_min", "def_max", "level_min", "level_max"):
            try:
                numbers[key] = _number(self.texts[key].get())
            except ValueError:
                raise ValueError(f"{self.cget('text')}: {key.replace('_', ' ')} is not a whole number") from None
        return bulk.CardFilter(
            kinds={k for k, var in self.kinds.items() if var.get()},
            types=set(self.types.curselection()),
            attributes={i for i, var in enumerate(self.attributes) if var.get()},
            stars={i + 1 for i in self.stars.curselection()},
            name=self.texts["name"].get(), text=self.texts["text"].get(), cards=self.texts["cards"].get(),
            results_only=self.results_only.get(), **numbers)

    def write(self, other: "FilterPanel"):
        """Take the other side's conditions."""
        for key, var in self.kinds.items():
            var.set(other.kinds[key].get())
        for mine, theirs in zip(self.attributes, other.attributes):
            mine.set(theirs.get())
        for key, var in self.texts.items():
            var.set(other.texts[key].get())
        self.results_only.set(other.results_only.get())
        for box, source in ((self.types, other.types), (self.stars, other.stars)):
            box.selection_clear(0, "end")
            for i in source.curselection():
                box.selection_set(i)
        self.added = set(other.added)
        self.sync()
        self.on_change()

    def clear(self):
        for var in list(self.kinds.values()) + self.attributes + [self.results_only]:
            var.set(False)
        for var in self.texts.values():
            var.set("")
        for box in (self.types, self.stars):
            box.selection_clear(0, "end")
            box.see(0)
        self.added.clear()
        self.sync()
        self.on_change()

    def show_count(self, project, chosen):
        self.project, self.chosen = project, chosen
        self.count.configure(text=f"{len(chosen)} cards")
        self.sync()

    def list_cards(self):
        if self.project is None:
            return
        lines = [f"{cid:4}  {self.project.cards[cid].name}  (ATK {self.project.cards[cid].attack}, "
                 f"{self.project.type_names[self.project.cards[cid].type] if 0 <= self.project.cards[cid].type < len(self.project.type_names) and self.project.type_names[self.project.cards[cid].type] else '?'})"
                 for cid in self.chosen]
        show_text(self, f"{self.cget('text')}: {len(lines)} cards", "\n".join(lines) or "(none)", width=70, height=30)


class BulkFusionsDialog(tk.Toplevel):
    """Material A + Material B = Result, then a preview of what it does."""

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.title("Bulk fusions")
        self.transient(tab.winfo_toplevel())
        self.pending = None
        self.current = None      # the last plan
        self.mode = tk.StringVar(value="add")
        self.result_mode = tk.StringVar(value="card")
        self.ladder = tk.StringVar()
        self.stronger = tk.BooleanVar(value=True)
        self.allow_self = tk.BooleanVar()
        self.overwrite = tk.StringVar(value="skip")

        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        for value, text in (("add", "Add fusions"), ("remove", "Remove fusions")):
            ttk.Radiobutton(top, text=text, value=value, variable=self.mode, style="Segment.Toolbutton",
                            command=self.mode_changed).pack(side="left")
        self.explain = ttk.Label(top, style="Hint.TLabel")
        self.explain.pack(side="left", padx=12)

        # The equation: A + B = Result, each a column.
        sides = ttk.Frame(self, padding=(10, 8))
        sides.pack(fill="x")
        from .tabs import star_choices
        names = star_choices(tab.project)[1:]
        self.a = FilterPanel(sides, "Material A", self.schedule, names)
        self.b = FilterPanel(sides, "Material B", self.schedule, names)
        self.a.other, self.b.other = self.b, self.a
        self.a.copy_button.configure(text="Same as B")
        self.b.copy_button.configure(text="Same as A")
        self.a.grid(row=0, column=0, sticky="nsew")
        ttk.Label(sides, text="+", font=ui_font(18)).grid(row=0, column=1, padx=8)
        self.b.grid(row=0, column=2, sticky="nsew")
        self.equals = ttk.Label(sides, text="=", font=ui_font(18))
        self.equals.grid(row=0, column=3, padx=8)
        for column in (0, 2):
            sides.columnconfigure(column, weight=1, uniform="side")

        self.outcome = ttk.LabelFrame(sides, text="Result", padding=8)
        self.outcome.grid(row=0, column=4, sticky="nsew")
        sides.columnconfigure(4, weight=1, uniform="side")
        self.card_choice = ttk.Radiobutton(self.outcome, text="This card", value="card", variable=self.result_mode,
                                           command=self.mode_changed)
        self.card_choice.grid(row=0, column=0, sticky="w")
        self.result = CardField(self.outcome, lambda: self.tab.project, width=24)
        self.result.grid(row=1, column=0, sticky="we", padx=(20, 0))
        self.result.var.trace_add("write", lambda *_: self.schedule())
        self.ladder_choice = ttk.Radiobutton(self.outcome, text="The weakest of these that beats both",
                                             value="ladder", variable=self.result_mode, command=self.mode_changed)
        self.ladder_choice.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.ladder_entry = ttk.Entry(self.outcome, textvariable=self.ladder, width=24)
        self.ladder_entry.grid(row=3, column=0, sticky="we", padx=(20, 0))
        self.ladder.trace_add("write", lambda *_: self.schedule())
        self.options = ttk.Frame(self.outcome)
        self.options.grid(row=4, column=0, sticky="we", pady=(10, 0))
        ttk.Separator(self.options).pack(fill="x", pady=(0, 6))
        self.stronger_box = ttk.Checkbutton(self.options, text="Only if the result's ATK beats both",
                                            variable=self.stronger, command=self.schedule)
        self.stronger_box.pack(anchor="w")
        ttk.Checkbutton(self.options, text="A card may fuse with itself", variable=self.allow_self,
                        command=self.schedule).pack(anchor="w")
        self.policy = ttk.Frame(self.options)
        self.policy.pack(anchor="w", pady=(6, 0))
        ttk.Label(self.policy, text="A pair that already fuses:").pack(anchor="w")
        ttk.Radiobutton(self.policy, text="keep its result", value="skip", variable=self.overwrite,
                        command=self.schedule).pack(anchor="w", padx=(12, 0))
        ttk.Radiobutton(self.policy, text="replace it", value="overwrite", variable=self.overwrite,
                        command=self.schedule).pack(anchor="w", padx=(12, 0))
        self.outcome.columnconfigure(0, weight=1)

        preview = ttk.LabelFrame(self, text="Preview", padding=8)
        preview.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.summary = ttk.Label(preview, justify="left", font=ui_font(13))
        self.summary.pack(fill="x")
        self.budget = ttk.Label(preview, style="Hint.TLabel")
        self.budget.pack(fill="x")
        self.problem = ttk.Label(preview, style="Error.TLabel", justify="left")
        self.problem.pack(fill="x")
        self.warning = ttk.Label(preview, style="Warning.TLabel", justify="left")
        self.warning.pack(fill="x")
        frame, self.tree = scrolled_tree(preview, [("a", "Material A"), ("b", "Material B"), ("before", "Now"),
                                                   ("after", "After"), ("what", "Change")],
                                         [220, 220, 220, 220, 70], 8)
        self.tree.tag_configure("kept", foreground=theme.tag_color(self.tree, "note"))  # the theme's grey, dark too
        frame.pack(fill="both", expand=True, pady=(4, 0))
        self.tree_frame = frame

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.apply_button = ttk.Button(buttons, text="Apply...", command=self.apply)
        self.apply_button.pack(side="right", padx=4)
        self.undo_button = ttk.Button(buttons, text="Undo last batch", command=self.undo)
        self.undo_button.pack(side="left")
        self.undo_note = ttk.Label(buttons, style="Hint.TLabel")
        self.undo_note.pack(side="left", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.minsize(px(self, 900), px(self, 560))
        self.mode_changed()
        self.show_undo()
        grab(self)

    def destroy(self):
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        super().destroy()

    # --- reading the form -----------------------------------------------------

    def spec(self) -> bulk.BulkSpec:
        ladder = self.mode.get() == "add" and self.result_mode.get() == "ladder"
        return bulk.BulkSpec(a=self.a.read(), b=self.b.read(), mode=self.mode.get(),
                             result=0 if ladder else self.result.get(),
                             ladder=self.ladder.get() if ladder else "",
                             stronger=self.stronger.get(), allow_self=self.allow_self.get(),
                             overwrite=self.overwrite.get() == "overwrite")

    def mode_changed(self):
        adding = self.mode.get() == "add"
        self.explain.configure(text="Every A card with every B card makes the result. A+B and B+A are one pair."
                               if adding else "Every A card with every B card stops fusing.")
        self.outcome.configure(text="Result" if adding else "Only those that make (optional)")
        self.equals.configure(text="=" if adding else "→")
        # Taking away: one card, or any; nothing else to choose.
        for widget in (self.card_choice, self.ladder_choice, self.ladder_entry, self.options):
            if adding:
                widget.grid()
            else:
                widget.grid_remove()
        if not adding:
            self.result_mode.set("card")
        self.result.grid_configure(padx=(20 if adding else 0, 0))
        # the list's choice beats both materials already
        self.stronger_box.configure(state="normal" if self.result_mode.get() == "card" else "disabled")
        self.result.entry.configure(state="normal" if self.result_mode.get() == "card" else "disabled")
        self.ladder_entry.configure(state="normal" if self.result_mode.get() == "ladder" else "disabled")
        self.apply_button.configure(text="Apply..." if adding else "Remove...")
        self.schedule()

    # --- the preview ------------------------------------------------------------

    def schedule(self, *_):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(DELAY, self.refresh)

    def refresh(self):
        if self.pending:            # called before the timer: it has nothing left to do
            self.after_cancel(self.pending)
        self.pending = None
        project = self.tab.project
        if project is None:
            return None
        try:
            spec = self.spec()
        except ValueError as problem:
            self.current = None
            self.show(None, str(problem))
            return None
        results = bulk.fusion_results(project) if (spec.a.results_only or spec.b.results_only) else None
        self.a.show_count(project, spec.a.select(project, results)[0])
        self.b.show_count(project, spec.b.select(project, results)[0])
        self.current = bulk.plan(project, spec)
        self.show(self.current)
        return self.current

    def started(self) -> bool:
        """Anything chosen yet (else the preview says what to do, no errors)."""
        return any(side.holds(key) for side in (self.a, self.b) for key, _ in CONDITIONS) or \
            bool(self.result.var.get().strip() or self.ladder.get().strip())

    def show(self, the_plan, problem=""):
        self.tree.delete(*self.tree.get_children())
        self.after_idle(self.fold_messages)
        if the_plan is None:
            self.summary.configure(text="")
            self.budget.configure(text="")
            self.problem.configure(text=problem)
            self.warning.configure(text="")
            self.apply_button.state(["disabled"])
            return
        p = self.tab.project
        if not self.started():
            self.summary.configure(text="Choose the cards of A and B, then the result.")
            self.budget.configure(text="")
            self.problem.configure(text="")
            self.warning.configure(text="")
            self.apply_button.state(["disabled"])
            return
        self.summary.configure(text=the_plan.headline())
        self.budget.configure(text=the_plan.details() + "\n" + the_plan.budget_line())
        self.problem.configure(text="\n".join(the_plan.errors))
        self.warning.configure(text="\n".join(the_plan.warnings))
        label = lambda cid: p.card_label(cid) if cid else ("(forbidden)" if cid == 0 else "(none)")
        tags = {"add": "added", "replace": "changed", "remove": "removed", "kept": "kept"}
        for i, (pair, before, after, what) in enumerate(the_plan.samples):
            self.tree.insert("", "end", iid=str(i), tags=(tags[what],),
                             values=(p.card_label(pair[0]), p.card_label(pair[1]), label(before),
                                     label(after) if what != "remove" else "(no fusion)", what))
        shown = len(the_plan.samples)
        if shown >= bulk.SAMPLE:
            self.tree.insert("", "end", iid="more", values=("", "", "", f"(the first {shown} shown)", ""))
        self.apply_button.state(["!disabled"] if the_plan.ok() else ["disabled"])

    def fold_messages(self):
        """An empty message line takes no room; one with words shows above the list."""
        for label in (self.budget, self.problem, self.warning):
            if label.cget("text"):
                label.pack(fill="x", before=self.tree_frame)
            else:
                label.pack_forget()

    # --- carrying it out ----------------------------------------------------------

    def apply(self):
        the_plan = self.refresh()
        if the_plan is None or not the_plan.ok():
            return
        if the_plan.mode == "add":
            what = f"add {the_plan.added} fusions and replace {the_plan.replaced}"
        else:
            what = f"take {the_plan.removed} fusions away"
        if not messagebox.askokcancel("Bulk fusions", f"{the_plan.summary()}\n\n{the_plan.budget_line()}\n\n"
                                      f"This will {what}. \"Undo last batch\" puts them back.", parent=self):
            return
        batch = bulk.apply(self.tab.project, the_plan, description=what)
        self.tab.bulk_batch = batch
        self.tab.app.changed()
        self.tab.fill()
        self.show_undo()
        self.refresh()

    def show_undo(self):
        batch = getattr(self.tab, "bulk_batch", None)
        usable = batch is not None and batch.project is self.tab.project
        self.undo_button.state(["!disabled"] if usable else ["disabled"])
        self.undo_note.configure(text=f"last: {batch.description}" if usable else "")

    def undo(self):
        batch = getattr(self.tab, "bulk_batch", None)
        if batch is None or batch.project is not self.tab.project:
            return
        restored, skipped = bulk.undo(self.tab.project, batch)
        self.tab.bulk_batch = None
        self.tab.app.changed()
        self.tab.fill()
        self.show_undo()
        note = f"{restored} pairs put back."
        if skipped:
            note += f" {skipped} changed since are left as they are."
        messagebox.showinfo("Bulk fusions", note, parent=self)
        self.refresh()


def open_bulk(tab):
    if tab.project is None:
        return None
    return BulkFusionsDialog(tab)
