"""The Starter decks tab's Weighted pools page: a mod's own "starter_pools"
(starter_pools.py, notes/starter-deck.md), pools a new game's deck is drawn
from, each its number of cards by its own weights, the draws adding up to
the forty a deck holds. The disc's seven rows are a start."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import starter_pools as sp
from .gamedata import DECK_SIZE
from .widgets import FormDialog, WrapLabel, legend, pick_card, scrolled_tree, ui_font


class StarterPoolsPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master, padding=4)
        self.tab = tab
        self.index = 0
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        frame, self.list = scrolled_tree(left, [("n", "#"), ("name", "Pool"), ("draws", "Draws"), ("cards", "Cards")],
                                         [30, 150, 50, 50], 18)
        frame.pack(fill="y", expand=True)
        self.list.bind("<<TreeviewSelect>>", lambda e: self.select())
        self.list.bind("<Double-1>", lambda e: self.edit_pool())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Add pool", command=self.add_pool).pack(side="left")
        ttk.Button(buttons, text="Edit...", command=self.edit_pool).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove", command=self.remove_pool).pack(side="left")
        ttk.Button(left, text="Start from the disc's seven pools", command=self.from_retail).pack(fill="x",
                                                                                                 pady=(4, 0))
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        top = ttk.Frame(right)
        top.pack(fill="x")
        self.title = ttk.Label(top, font=ui_font(10))
        self.title.pack(side="left")
        self.total = ttk.Label(top, font=ui_font(10))
        self.total.pack(side="right")
        self.note = ttk.Label(right, style="Warning.TLabel")
        self.note.pack(anchor="w")
        frame, self.tree = scrolled_tree(right, [("id", "#"), ("name", "Card"), ("type", "Type"), ("w", "Weight"),
                                                 ("pct", "Per draw")], [50, 260, 110, 70, 80], 16,
                                         selectmode="extended", sort_numeric=("id", "w", "pct"))
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        self.tree.bind("<Delete>", lambda e: self.remove_cards())
        self.empty = ttk.Frame(frame, padding=20)
        WrapLabel(self.empty, 380, font=ui_font(10),
                  text="No pools of the mod's own: a new game deals a written deck if the mod has one, else "
                       "the disc's seven pools. Weighted pools draw a different deck each new game.").pack(fill="x")
        ttk.Button(self.empty, text="Start from the disc's seven pools", command=self.from_retail).pack(
            anchor="w", pady=(8, 0))
        ttk.Button(self.empty, text="An empty pool", command=self.add_pool).pack(anchor="w", pady=(6, 0))
        edit = ttk.Frame(right)
        edit.pack(fill="x")
        ttk.Button(edit, text="Add a card...", command=self.add_card).pack(side="left")
        ttk.Label(edit, text="Weight").pack(side="left", padx=(10, 2))
        self.weight = tk.StringVar(value="1")
        entry = ttk.Entry(edit, textvariable=self.weight, width=7)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.set_weight())
        ttk.Button(edit, text="Set weight", command=self.set_weight).pack(side="left", padx=2)
        ttk.Button(edit, text="Remove selected", command=self.remove_cards).pack(side="left", padx=(8, 0))
        legend(right, ("removed", "a card the editor cannot place (kept as written)")).pack(anchor="w", pady=(2, 0))
        WrapLabel(right, text=f"Each pool draws its number of cards by its weights; the draws add up to the "
                              f"{DECK_SIZE} a deck holds, or the game reads the disc's pools. A card dealt "
                              f"{sp.COPY_LIMIT} times is drawn again.", style="Hint.TLabel").pack(fill="x")

    @property
    def project(self):
        return self.tab.project

    def pools(self):
        return sp.state(self.project) if self.project else []

    def current(self):
        pools = self.pools()
        return pools[self.index] if 0 <= self.index < len(pools) else None

    def edited(self):
        sp.store(self.project)
        self.tab.app.changed()
        self.fill()

    # --- the list ----------------------------------------------------------------

    def fill(self):
        if self.project is None:
            return
        pools = self.pools()
        self.list.delete(*self.list.get_children())
        for i, pool in enumerate(pools):
            self.list.insert("", "end", iid=str(i), values=(i + 1, pool.name or "(unnamed)", pool.draws,
                                                            pool.count()),
                             tags=("error",) if pool.kept or (pool.draws and not pool.count()) else ())
        if pools:
            self.index = min(self.index, len(pools) - 1)
            self.list.selection_set(str(self.index))
        drawn = sum(pool.draws for pool in pools)
        self.total.configure(text=f"Draws {drawn} / {DECK_SIZE}" if pools else "",
                             style="Ok.TLabel" if drawn == DECK_SIZE else "Error.TLabel")
        self.note.configure(text="The mod writes starter decks down too: those are dealt first, and these "
                                 "pools only when none is offered." if pools and self.project.starter else "")
        self.fill_cards()

    def select(self):
        selection = self.list.selection()
        if selection and int(selection[0]) != self.index:
            self.index = int(selection[0])
            self.fill_cards()

    def fill_cards(self):
        self.tree.delete(*self.tree.get_children())
        pool = self.current()
        if pool is None:
            self.title.configure(text="No pool")
            self.empty.place(relx=0.5, rely=0.4, anchor="center", relwidth=0.7)
            return
        self.empty.place_forget()
        p = self.project
        self.title.configure(text=f"{pool.name or '(unnamed)'}: draws {pool.draws}")
        total = pool.total() or 1
        for cid, weight in sorted(pool.cards.items(), key=lambda item: (-item[1], item[0])):
            card = p.cards.get(cid)
            self.tree.insert("", "end", iid=str(cid), values=(
                cid, card.name if card else "?", self.tab.type_name(card) if card else "", weight,
                f"{100 * weight / total:.2f}%"))
        for name, weight in pool.kept.items():
            self.tree.insert("", "end", iid=f"kept:{name}", tags=("removed",),
                             values=("", name, "", weight, f"{100 * weight / total:.2f}%"))
        self.tree.sorting.apply()

    def pick_row(self):
        selection = self.tree.selection()
        pool = self.current()
        if len(selection) == 1 and pool and not selection[0].startswith("kept:"):
            self.weight.set(str(pool.cards.get(int(selection[0]), 0)))

    # --- pools -------------------------------------------------------------------

    def pool_dialog(self, title, pool, adding=False):
        fields = {}

        def build(dialog, body):
            for row, (key, label, value) in enumerate((("name", "Name", pool.name or ""),
                                                       ("draws", "Draws", str(pool.draws)))):
                ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
                fields[key] = tk.StringVar(value=value)
                ttk.Entry(body, textvariable=fields[key], width=30 if key == "name" else 8).grid(
                    row=row, column=1, sticky="w", pady=2)
            others = sum(p.draws for p in self.pools() if p is not pool)
            ttk.Label(body, text=f"How many of the deck's {DECK_SIZE} cards it draws (the other pools draw "
                                 f"{others}).", style="Hint.TLabel").grid(row=2, column=0, columnspan=2, sticky="w",
                                                                        pady=(6, 0))

        def ok(dialog):
            try:
                draws = int(fields["draws"].get().strip())
            except ValueError:
                draws = -1
            if not 0 <= draws <= sp.DRAW_MAX:
                return f"draws are a whole number, 0 to {sp.DRAW_MAX}"
            pool.name = fields["name"].get().strip() or None
            pool.draws = draws
            if adding:
                self.pools().append(pool)
                self.index = len(self.pools()) - 1
            self.edited()
            return None

        dialog = FormDialog(self, title, build, ok)
        dialog.fields = fields
        return dialog

    def add_pool(self):
        if self.project is None:
            return None
        left = max(0, DECK_SIZE - sum(p.draws for p in self.pools()))
        return self.pool_dialog("Add a pool", sp.Pool(name=f"Pool {len(self.pools()) + 1}", draws=left), adding=True)

    def edit_pool(self):
        pool = self.current()
        return self.pool_dialog("Pool", pool) if pool else None

    def remove_pool(self):
        pool = self.current()
        if pool is None:
            return
        if not messagebox.askyesno("Remove pool", f"Remove {pool.name or 'this pool'} and its {pool.count()} "
                                   "cards?", parent=self):
            return
        self.pools().pop(self.index)
        self.index = max(0, self.index - 1)
        self.edited()

    def from_retail(self):
        """The disc's seven pools as the mod's, to change (the one start
        that deals as the disc does)."""
        files = getattr(self.tab.app, "files", None)
        retail = sp.retail(files.wa if files else None)
        if not retail:
            messagebox.showinfo("Starter pools", "The game files have not got the disc's starter pools.",
                                parent=self)
            return
        if self.pools() and not messagebox.askyesno("Starter pools", "Put the disc's seven pools in place of "
                                                    "the mod's?", parent=self):
            return
        pools = self.pools()
        pools[:] = retail
        self.index = 0
        self.edited()

    # --- cards -------------------------------------------------------------------

    def chosen_weight(self):
        try:
            weight = int(self.weight.get().strip())
        except ValueError:
            weight = -1
        if not 0 <= weight <= sp.WEIGHT_MAX:
            messagebox.showinfo("Starter pools", f"A weight is a whole number, 0 to {sp.WEIGHT_MAX}.", parent=self)
            return None
        return weight

    def add_card(self):
        pool = self.current()
        if pool is None:
            messagebox.showinfo("Starter pools", "Add a pool first.", parent=self)
            return
        cid = pick_card(self, self.project, "Card to add to the pool")
        weight = self.chosen_weight() if cid else None
        if cid and weight is not None:
            pool.cards[cid] = weight or 1
            self.edited()
            if self.tree.exists(str(cid)):
                self.tree.selection_set(str(cid))
                self.tree.see(str(cid))

    def set_weight(self):
        pool, weight = self.current(), self.chosen_weight()
        if pool is None or weight is None:
            return
        chosen = [iid for iid in self.tree.selection()]
        for iid in chosen:
            if iid.startswith("kept:"):
                pool.kept[iid[5:]] = weight
            else:
                pool.cards[int(iid)] = weight
        if chosen:
            self.edited()
            for iid in chosen:
                if self.tree.exists(iid):
                    self.tree.selection_add(iid)

    def remove_cards(self):
        pool = self.current()
        if pool is None:
            return
        for iid in self.tree.selection():
            if iid.startswith("kept:"):
                pool.kept.pop(iid[5:], None)
            else:
                pool.cards.pop(int(iid), None)
        self.edited()
