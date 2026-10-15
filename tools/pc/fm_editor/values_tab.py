"""The Values tab: the game's numbers a mod may change (values.py,
notes/gameplay-tables.md, "Values"), written as the mod's "limits". Each
value in its group, with the game's own beside it, marked when the mod
changes it, a button that puts the game's back, and a line that says what it
does. An empty field is the game's own number. Below, the LP each side
starts with against a given duelist."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import duelist_rules, roster, values
from .gamedata import DUELIST_NAMES
from .tabs import Tab
from .widgets import ScrolledForm, Tooltip

# The groups in each of the two columns, by title; the LP by duelist goes
# under the second.
COLUMNS = (("Duel", "Magic", "Deck and Trunk", "Rank"), ("Rewards", "Records and 2P"))


class ValuesTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Values")
        self.scroll = ScrolledForm(self)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.body
        top = ttk.Frame(body)
        top.pack(fill="x", pady=(0, 2))
        ttk.Label(top, style="Hint.TLabel",
                  text="Empty: the game's own value (grey). Changed values are blue; ↺ puts the game's back.").pack(
            side="left")
        ttk.Button(top, text="Reset all to the game's", command=self.clear).pack(side="right")
        self.status = ttk.Label(body, style="Error.TLabel", wraplength=1100, justify="left")
        self.vars, self.captions, self.reverts, self.wrong, self.tips = {}, {}, {}, set(), {}
        columns = ttk.Frame(body)
        columns.pack(fill="x")
        groups = dict(values.GROUPS)
        self.group_frames = {}
        for number, titles in enumerate(COLUMNS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=number, sticky="nw", padx=(0, 8) if number == 0 else 0)
            # One width for the captions of a column, so its groups line up.
            width = max(len(field[1]) for title in titles for field in groups[title])
            for title in titles:
                frame = ttk.LabelFrame(column, text=title, padding=(6, 0, 6, 2))
                frame.pack(fill="x", pady=(0, 2))
                self.group_frames[title] = frame
                self._fields(frame, groups[title], width)
                if title in values.GROUP_NOTES:
                    ttk.Label(frame, style="Hint.TLabel", text=values.GROUP_NOTES[title]).grid(
                        row=len(groups[title]), column=0, columnspan=5, sticky="w", pady=(1, 0))
            if number == 1:
                self._duelist_table(column)
        self.status.pack(anchor="w", pady=(2, 0))
        self.per_duelist = {}

    def _fields(self, parent, fields, width):
        for row, (key, label, retail, low, high, hint, _) in enumerate(fields):
            caption = ttk.Label(parent, text=label, width=width)
            caption.grid(row=row, column=0, sticky="w")
            self.captions[key] = caption
            var = self.vars[key] = tk.StringVar()
            var.trace_add("write", lambda *_, k=key: self._mark(k))
            entry = ttk.Entry(parent, textvariable=var, width=8)
            entry.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)
            entry.bind("<FocusOut>", lambda e: self.commit())
            entry.bind("<Return>", lambda e: self.commit())
            ttk.Label(parent, style="Hint.TLabel", width=6, anchor="e",
                      text=values.retail_text(key)).grid(row=row, column=2, sticky="e", padx=(4, 0))
            revert = ttk.Button(parent, text="↺", width=2, style="Toolbutton", state="disabled",
                                command=lambda k=key: self.revert(k))
            revert.grid(row=row, column=3, padx=(2, 0))
            self.reverts[key] = revert
            line = ttk.Label(parent, style="Hint.TLabel", text=f"{hint}, {low} to {high}")
            line.grid(row=row, column=4, sticky="w", padx=(4, 0))
            if key in values.TIPS:
                self.tips[key] = [Tooltip(widget, values.TIPS[key]) for widget in (caption, entry, line)]

    def _duelist_table(self, parent):
        per = ttk.LabelFrame(parent, text="Starting LP by duelist", padding=(6, 2))
        per.pack(fill="x")
        self.duelists = ttk.Treeview(per, columns=("player", "opponent"), height=3)
        self.duelists.heading("#0", text="Duelist")
        self.duelists.heading("player", text="Your LP")
        self.duelists.heading("opponent", text="Duelist's LP")
        self.duelists.column("#0", width=180)
        self.duelists.column("player", width=80, anchor="e")
        self.duelists.column("opponent", width=90, anchor="e")
        self.duelists.pack(fill="x")
        self.duelists.bind("<<TreeviewSelect>>", lambda e: self._pick_duelist())
        row = ttk.Frame(per)
        row.pack(fill="x", pady=(4, 2))
        self.duelist_name = tk.StringVar()
        self.duelist_player = tk.StringVar()
        self.duelist_opponent = tk.StringVar()
        # The disc's, then the duelists the mod adds, listed afresh as it
        # opens: the game names them as "drops" and "decks" do (tables.c
        # Duelists_Named).
        self.duelist_box = ttk.Combobox(row, textvariable=self.duelist_name, values=["all"] + DUELIST_NAMES[1:],
                                        width=16, postcommand=self.duelist_choices)
        self.duelist_box.pack(side="left")
        ttk.Label(row, text="You").pack(side="left", padx=(6, 2))
        ttk.Entry(row, textvariable=self.duelist_player, width=6).pack(side="left")
        ttk.Label(row, text="Duelist").pack(side="left", padx=(6, 2))
        ttk.Entry(row, textvariable=self.duelist_opponent, width=6).pack(side="left")
        ttk.Button(row, text="Set", command=self._set_duelist).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Remove", command=self._remove_duelist).pack(side="left", padx=(4, 0))

    def _mark(self, key):
        changed = bool(self.vars[key].get().strip())
        style = "Error.TLabel" if key in self.wrong else "Changed.TLabel" if changed else "TLabel"
        self.captions[key].configure(style=style)
        self.reverts[key].configure(state="normal" if changed else "disabled")

    def revert(self, key):
        """The game's own value back in field `key`."""
        self.vars[key].set("")
        self.commit()

    def _fill_duelists(self):
        self.duelists.delete(*self.duelists.get_children())
        for name, (player, opponent) in self.per_duelist.items():
            self.duelists.insert("", "end", iid=name, text=name,
                                 values=("" if player is None else player, "" if opponent is None else opponent))

    def _pick_duelist(self):
        chosen = self.duelists.selection()
        if not chosen:
            return
        player, opponent = self.per_duelist.get(chosen[0], (None, None))
        self.duelist_name.set(chosen[0])
        self.duelist_player.set("" if player is None else str(player))
        self.duelist_opponent.set("" if opponent is None else str(opponent))

    def _set_duelist(self):
        name = self.duelist_name.get().strip()
        try:
            numbers = [int(v.get()) if v.get().strip() else None for v in (self.duelist_player, self.duelist_opponent)]
        except ValueError:
            self.status.configure(text="A duelist's LP is a whole number")
            return
        if not name:
            return
        if numbers == [None, None]:
            self.per_duelist.pop(name, None)
        else:
            self.per_duelist[name] = tuple(numbers)
        self._fill_duelists()
        self.commit()

    def _remove_duelist(self):
        for name in self.duelists.selection():
            self.per_duelist.pop(name, None)
        self._fill_duelists()
        self.commit()

    def clear(self):
        for var in self.vars.values():
            var.set("")
        self.per_duelist = {}
        self._fill_duelists()
        self.commit()

    def refresh(self):
        if self.project is None:
            return
        self.duelist_choices()
        flat = values.flatten(self.project.other.get("limits"))
        for key, var in self.vars.items():
            var.set(str(flat[key]) if key in flat else "")
        self.per_duelist = dict(flat.get("duelists", {}))
        self._fill_duelists()
        self._report()

    def duelist_choices(self):
        if self.project is not None:
            self.duelist_box.configure(values=["all"] + duelist_rules.references(self.project))

    def named(self, name):
        """A duelist the mod adds that a name finds, or None (values.check)."""
        return roster.named(self.project, name)

    def _report(self):
        problems = values.check(self.project.other.get("limits"), self.named) if self.project else []
        self.status.configure(text="\n".join(f"{level}: {where}: {message}" for level, where, message in problems))
        # A value the game would hold back or leave out: its name in red.
        self.wrong = {where for _, where, _ in problems if where in self.captions}
        for key in self.captions:
            self._mark(key)

    def commit(self):
        if self.project is None:
            return True
        flat = {"duelists": dict(self.per_duelist)}
        for key, var in self.vars.items():
            text = var.get().strip()
            if not text:
                continue
            try:
                flat[key] = int(text)
            except ValueError:
                self.status.configure(text=f"Not applied: {values.FIELD[key][1]} is a whole number")
                return False
        before = self.project.other.get("limits")
        after = values.build(flat, before)
        # Untouched, the section stays as the mod wrote it: every tab switch
        # commits, and rebuilding it would drop what the form cannot show
        # (a misspelt key, a value that is not a number, which Conflicts
        # should still report) and mark the mod changed.
        if after == values.build(values.flatten(before), before):
            after = before
        if after is None:
            self.project.other.pop("limits", None)
        else:
            self.project.other["limits"] = after
        self._report()
        if after != before:
            self.app.changed()
        self.applied()
        return True
