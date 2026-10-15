"""The Duelists tab's fixed deck: a choice, for the deck pool, between the
weighted deck the disc deals and forty cards written down (fixed_decks.py),
and the editor of those forty -- the Starter decks tab's, with the weighted
deck beside each card and a way to start from it."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import fixed_decks, roster
from .gamedata import DECK_COPY_LIMIT, DECK_SIZE, DUELIST_NAMES, POOL_TOTAL, TYPE_NAMES
from .widgets import pick_card, px, scrolled_tree

STYLES = (("Hint.TLabel", "#777"), ("Ok.TLabel", "#26a269"), ("Error.TLabel", "#c01c28"))


def ensure_styles(widget):
    """The label styles the tabs name; left alone when a theme set them.
    (lookup() would answer with the color TLabel inherits, so ask the
    style for what it sets itself.)"""
    style = ttk.Style(widget)
    for name, color in STYLES:
        if not (style.configure(name) or {}).get("foreground"):
            style.configure(name, foreground=color)


class FixedDeckView:
    """Laid into the Duelists tab's right-hand side: the two radio buttons
    under the pool choice, and the fixed deck's panel in place of the
    weighted pool's list while the duelist's deck is fixed."""

    def __init__(self, tab, right, top):
        self.tab = tab
        self.top = top
        ensure_styles(right)
        self.right = right
        self.weighted = None        # the weighted pool's widgets as the tab packed them (show)
        self.mode = tk.StringVar(value="weighted")
        self.bar = ttk.Frame(right)
        ttk.Radiobutton(self.bar, text="Weighted deck (retail)", value="weighted", variable=self.mode,
                        command=self.switch).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(self.bar, text=f"Fixed deck ({DECK_SIZE} cards)", value="fixed", variable=self.mode,
                        command=self.switch).pack(side="left")
        self.panel = ttk.Frame(right)
        frame, self.tree = scrolled_tree(self.panel, [("id", "#"), ("name", "Card"), ("type", "Type"),
                                                      ("atk", "ATK"), ("def", "DEF"),
                                                      ("copies", "Copies"), ("weight", "Weighted"), ("note", "Note")],
                                         [50, 220, 100, 50, 50, 60, 70, 170], 14, selectmode="extended",
                                         sort_numeric=("id", "atk", "def", "copies", "weight"))
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        edit = ttk.Frame(self.panel)
        edit.pack(fill="x")
        ttk.Button(edit, text="Add a card...", command=self.add_card).pack(side="left")
        ttk.Label(edit, text="Copies").pack(side="left", padx=(10, 2))
        self.copies = tk.StringVar()
        entry = ttk.Entry(edit, textvariable=self.copies, width=5)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.set_copies())
        ttk.Button(edit, text="Set", command=self.set_copies).pack(side="left", padx=2)
        ttk.Button(edit, text="Remove selected", command=self.remove_cards).pack(side="left", padx=(8, 0))
        deck = ttk.Frame(self.panel)
        deck.pack(fill="x", pady=(4, 0))
        ttk.Button(deck, text=f"Copy the weighted deck's most likely {DECK_SIZE}",
                   command=self.copy_weighted).pack(side="left")
        ttk.Button(deck, text="Clear", command=self.clear).pack(side="left", padx=4)
        ttk.Button(deck, text="Revert to retail", command=self.revert).pack(side="left")
        ttk.Label(self.panel, style="Hint.TLabel", wraplength=px(right, 620), justify="left", text=(
            f"A fixed deck is these {DECK_SIZE} cards, shuffled for each duel, in place of the weighted deck. "
            f"A card may have 0 to {DECK_SIZE} copies (the weighted deal stops at {DECK_COPY_LIMIT}). A deck "
            f"that is not {DECK_SIZE} cards, or names a card the game does not have, is left out and the "
            "weighted deck is dealt.")).pack(anchor="w", pady=(4, 0))
        self.fixed_shown = False
        self.stash = {}             # duelist -> the fixed decks "Weighted" took out, to put back
        self.stash_of = None        # the project they belong to

    # --- which side shows --------------------------------------------------

    def show(self, fixed: bool):
        if fixed == self.fixed_shown:
            return
        if self.weighted is None:
            # Taken when first needed, so the tab may pack its own after this
            # was made; what is above the pool choice (the duelist's header)
            # stays.
            slaves = self.right.pack_slaves()
            below = slaves[slaves.index(self.top) + 1:] if self.top in slaves else slaves
            self.weighted = [(w, w.pack_info()) for w in below if w not in (self.bar, self.panel)]
        if fixed:
            for widget, _ in self.weighted:
                widget.pack_forget()
            self.panel.pack(fill="both", expand=True)
        else:
            self.panel.pack_forget()
            for widget, info in self.weighted:
                widget.pack(info)
        self.fixed_shown = fixed

    def deck(self):
        p = self.tab.project
        if p is None or self.tab.pool.get() != "deck":
            return None
        return fixed_decks.deck_of(p, self.tab.subject())

    def weights(self) -> dict:
        """The weighted deck pool of the duelist shown."""
        return roster.pools_of(self.tab.project, self.tab.subject())["deck"]

    def fill(self) -> bool:
        """Called first by DuelistsTab.fill: True when the fixed deck is what
        shows, and the tab has nothing more to fill."""
        p = self.tab.project
        if p is not self.stash_of:
            self.stash, self.stash_of = {}, p
        # A duelist the mod adds has either deck in decks/<id>.json (roster.py).
        if self.tab.pool.get() == "deck":
            self.bar.pack(fill="x", after=self.top, pady=(4, 0))
        else:
            self.bar.pack_forget()
        deck = self.deck()
        self.mode.set("fixed" if deck else "weighted")
        self.show(deck is not None)
        if deck is None:
            return False
        weights = self.weights()
        self.tree.delete(*self.tree.get_children())
        for cid in sorted(deck.cards):
            copies = deck.cards[cid]
            card = p.cards.get(cid)
            notes = []
            if card is None:
                notes.append("no such card")
            if copies > DECK_COPY_LIMIT:
                notes.append(f"more than the weighted deal's {DECK_COPY_LIMIT}")
            weight = weights.get(cid, 0)
            self.tree.insert("", "end", iid=str(cid), tags=("error",) if card is None else (), values=(
                cid, card.name if card else "?", (TYPE_NAMES[card.type] if 0 <= card.type < len(TYPE_NAMES)
                                                  else card.type) if card else "",
                card.attack if card else "", card.defense if card else "",
                copies, f"{weight * 100 / POOL_TOTAL:.2f}%" if weight else "", ", ".join(notes)))
        # A card the editor could not place keeps its row, so its copies are
        # not quietly lost.
        for name, copies in deck.kept.items():
            self.tree.insert("", "end", iid=f"kept:{name}", tags=("removed",),
                             values=("", name, "", "", "", copies, "", "no such card; the deck is left out"))
        self.tree.sorting.apply()
        total = deck.total()
        good = total == DECK_SIZE and not deck.kept
        self.tab.total.configure(text=f"{roster.label(p, self.tab.subject())}: fixed deck, {total} / {DECK_SIZE} cards",
                                 style="Ok.TLabel" if good else "Error.TLabel", foreground="")
        return True

    def edited(self):
        deck = self.deck()
        if deck:
            for cid in [c for c, n in deck.cards.items() if not n]:
                del deck.cards[cid]
        self.tab.app.changed()
        self.tab.fill()
        self.tab.fill_list()

    # --- the choice -------------------------------------------------------

    def switch(self):
        p = self.tab.project
        if p is None or self.tab.pool.get() != "deck":
            return
        d = self.tab.subject()
        if self.mode.get() == "fixed":
            if fixed_decks.deck_of(p, d) is None:
                if self.stash.get(d):
                    fixed_decks.restore(p, self.stash.pop(d))
                else:
                    # A start that deals: the forty the weighted deck most
                    # likely deals. Clear starts from nothing.
                    fixed_decks.set_deck(p, d, fixed_decks.most_likely(self.weights()))
        else:
            taken = fixed_decks.remove(p, d)
            if taken:
                self.stash[d] = taken
        self.edited()

    def copy_weighted(self):
        deck = self.deck()
        if deck is None:
            return
        if deck.cards and not messagebox.askyesno(
                "Fixed deck", f"Replace the {deck.total()} cards of this fixed deck with the {DECK_SIZE} the "
                              "weighted deck most likely deals?", parent=self.tab):
            return
        fixed_decks.set_deck(self.tab.project, self.tab.subject(), fixed_decks.most_likely(self.weights()))
        self.edited()

    def clear(self):
        deck = self.deck()
        if deck is None:
            return
        deck.cards, deck.kept = {}, {}
        self.edited()

    def revert(self):
        """Back to the disc's: no fixed deck, and the weighted deck retail's
        (an added duelist's, its base's)."""
        p, d = self.tab.project, self.tab.subject()
        if p is None:
            return
        whose = (f"Deal {DUELIST_NAMES[d]} the disc's weighted deck again?" if isinstance(d, int) else
                 f"Deal {roster.label(p, d)} {DUELIST_NAMES[d.base]}'s weighted deck from the disc again?")
        if not messagebox.askyesno("Revert to retail", f"{whose} The fixed deck and the weighted deck's edits are "
                                   "taken out.", parent=self.tab):
            return
        fixed_decks.remove(p, d)
        self.stash.pop(d, None)
        if isinstance(d, int):
            p.revert_pool(d, "deck")
        else:
            d.pools["deck"] = dict(roster.retail_pool(p, d, "deck"))
        self.edited()

    # --- cards -------------------------------------------------------------

    def pick_row(self):
        selection = self.tree.selection()
        deck = self.deck()
        if len(selection) == 1 and deck and not selection[0].startswith("kept:"):
            self.copies.set(str(deck.cards.get(int(selection[0]), 0)))

    def add_card(self):
        deck = self.deck()
        if deck is None:
            return
        cid = pick_card(self.tab, self.tab.project, "Card to add to the fixed deck")
        if not cid:
            return
        try:
            copies = int(self.copies.get() or "0")
        except ValueError:
            copies = 0
        deck.cards[cid] = copies if 0 < copies <= DECK_SIZE else 1
        self.edited()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))

    def set_copies(self):
        deck = self.deck()
        if deck is None:
            return
        try:
            copies = int(self.copies.get())
        except ValueError:
            messagebox.showerror("Copies", "Copies are a whole number.", parent=self.tab)
            return
        if not 0 <= copies <= DECK_SIZE:
            messagebox.showerror("Copies", f"A card's copies are 0 to {DECK_SIZE}.", parent=self.tab)
            return
        chosen = [i for i in self.tree.selection() if not i.startswith("kept:")]
        for iid in chosen:
            deck.cards[int(iid)] = copies
        self.edited()
        for iid in chosen:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

    def remove_cards(self):
        deck = self.deck()
        if deck is None:
            return
        for iid in self.tree.selection():
            if iid.startswith("kept:"):
                deck.kept.pop(iid[5:], None)
            else:
                deck.cards.pop(int(iid), None)
        self.edited()
