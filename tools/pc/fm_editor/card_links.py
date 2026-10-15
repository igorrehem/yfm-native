"""Links between the tabs by card.

* The card the window is on (app.current_card): the Cards and Art tabs show
  the same card, and Fusions and Equips follow it when it changes (each
  tab's follow()).
* A right-click on a card in any list: open it in Cards or Art, show its
  fusions or its equip targets, or list everything in the mod that uses it
  (Where it's used...), each line a link to its tab."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from . import fixed_decks, packs as packmath, roster, starter_pools, validate
from .gamedata import POOL_LABELS, POOL_TOTAL, POOLS, TYPE_EQUIP
from .widgets import px, scrolled_tree


_open_menu = None     # the right-click menu up, if any


def close_menu(event=None):
    """Take the right-click menu down on another tab, a click elsewhere or
    Escape. Its grab is released once it is posted (else the window's own
    clicks would be lost), so Tk itself would leave it up."""
    global _open_menu
    menu, _open_menu = _open_menu, None
    if menu is None:
        return
    if event is not None and str(event.widget).startswith(str(menu)):
        _open_menu = menu       # a click on the menu itself, or one of its cascades
        return
    try:
        menu.unpost()
        menu.destroy()
    except tk.TclError:
        pass


def install(app, tab, tree, cards_of=None):
    """Give a list of cards the right-click menu. cards_of(iid) names the
    row's cards; by default the row's iid or its "#" column."""
    def default(iid):
        if iid.isdigit():
            return [int(iid)]
        value = str(tree.set(iid, "id")) if "id" in tree.cget("columns") else ""
        return [int(value)] if value.isdigit() else []

    cards_of = cards_of or default
    tree.cards_of = cards_of        # what the menu lists for a row (tests ask too)

    def popup(event):
        iid = tree.identify_row(event.y)
        if not iid or app.project is None:
            return
        if iid not in tree.selection():
            tree.selection_set(iid)
            tree.focus(iid)
            tree.update_idletasks()
            if iid not in tree.selection():     # the tab kept its card (a form that cannot be stored)
                return
        cids = [cid for cid in dict.fromkeys(cards_of(iid)) if cid in app.project.cards]
        if not cids:
            return
        global _open_menu
        close_menu()
        menu = tk.Menu(tree, tearoff=False)
        _open_menu = menu
        if len(cids) == 1:
            fill_menu(menu, app, tab, cids[0])
        else:
            for cid in cids:
                sub = tk.Menu(menu, tearoff=False)
                fill_menu(sub, app, tab, cid)
                menu.add_cascade(label=app.project.card_label(cid), menu=sub)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    tree.bind("<Button-3>", popup, add=True)
    if sys.platform == "darwin":
        tree.bind("<Button-2>", popup, add=True)


def fill_menu(menu, app, tab, cid):
    if tab is not app.cards:
        menu.add_command(label="Open in Cards", command=lambda: app.open_card(app.cards, cid))
    if tab is not app.art:
        menu.add_command(label="Open in Art", command=lambda: app.open_card(app.art, cid))
    menu.add_command(label="Show its fusions", command=lambda: app.open_card(app.fusions, cid))
    if app.project.cards[cid].type == TYPE_EQUIP:
        menu.add_command(label="Edit its equip targets", command=lambda: app.open_card(app.equips, cid))
    menu.add_separator()
    menu.add_command(label="Where it's used...", command=lambda: UsesWindow(app, cid))


def install_all(app):
    app.bind_all("<ButtonPress>", close_menu, add="+")
    app.bind_all("<Escape>", lambda e: close_menu(), add="+")
    p = lambda: app.project     # noqa: E731 -- the project changes when a mod is opened

    def fusion_cards(iid):
        if ":" not in iid or not iid.split(":")[0].isdigit():
            return []           # a group's row (Fuses with, Made by)
        a, b = (int(x) for x in iid.split(":"))
        return [a, b, app.fusions.shown_result((a, b))]

    def ritual_cards(iid):
        ritual = int(iid)
        project = p()
        recipe = project.rituals.get(ritual)
        if recipe is None and ritual in project.added and not project.ritual_removed(ritual):
            recipe = project.rituals.get(project.base_of(ritual))      # a copy is its base's ritual
        cards = [c for c in (recipe or ()) if c]
        for req in project.ritual_requirements.get(ritual, ()):       # a conditional recipe's cards
            if req.get("card") and req["card"] not in cards:
                cards.append(req["card"])
        return [ritual] + cards

    for tab, tree, cards_of in ((app.cards, app.cards.tree, None), (app.art, app.art.tree, None),
                                (app.fusions, app.fusions.tree, fusion_cards),
                                (app.equips, app.equips.equips, None), (app.equips, app.equips.monsters, None),
                                (app.rituals, app.rituals.tree, ritual_cards),
                                (app.duelists, app.duelists.tree, None), (app.duelists, app.duelists.fixed.tree, None),
                                (app.starter, app.starter.tree, None), (app.packs, app.packs.tree, None)):
        install(app, tab, tree, cards_of)


# --- Where it's used ------------------------------------------------------------

def plural(n: int, one: str, many: str = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def uses(app, cid) -> list:
    """[(tab name, what, go)] of everything in the mod naming the card; go()
    shows it in its tab."""
    from .tabs import fusion_pairs
    p = app.project
    lines = []

    def add(where, what, go):
        lines.append((where, what, go))

    for other, added in sorted(p.added.items()):
        if added.base == cid and other != cid:
            add("Cards", f"Copy of it: {p.card_label(other)}", lambda o=other: app.open_card(app.cards, o))
    # What the game plays for each pair, as the Fusions tab shows it.
    own, pairs = fusion_pairs(p)
    material = made = 0
    for pair in pairs:
        result = own.get(pair)
        result = result if result is not None else p.fusions.get(pair)
        if result:
            material += cid in pair
            made += result == cid
    if material or made:
        add("Fusions", f"Material in {plural(material, 'fusion')}; made by {plural(made, 'fusion')}",
            lambda: app.open_card(app.fusions, cid))
    if p.cards[cid].type == TYPE_EQUIP:
        add("Equips", f"Equips {plural(len(p.equip_targets(cid)), 'monster')}", lambda: app.open_card(app.equips, cid))
    else:
        for equip in p.equip_cards():
            if equip in p.cards and cid in p.equip_targets(equip):
                add("Equips", f"Equipped by {p.card_label(equip)}", lambda e=equip: app.open_card(app.equips, e))
    for ritual in sorted(set(p.ritual_cards()) | set(p.rituals)):
        if ritual not in p.cards:
            continue
        recipe = list(p.rituals.get(ritual) or ())
        tributes = recipe[:-1] + [req.get("card") for req in p.ritual_requirements.get(ritual, [])]
        go = lambda r=ritual: app.open_card(app.rituals, r)     # noqa: E731
        if ritual == cid:
            add("Rituals", "Its ritual", go)
        if cid in tributes:
            add("Rituals", f"Tribute for {p.card_label(ritual)}", go)
        if recipe and recipe[-1] == cid:
            add("Rituals", f"Summoned by {p.card_label(ritual)}", go)
    for d, pools in enumerate(p.pools):
        if d == 0:      # "Unused": no duel deals or drops its pools
            continue
        name = roster.shown_name(p, d)
        deck = fixed_decks.deck_of(p, d)
        for pool in POOLS:
            if pool == "deck" and deck is not None:
                copies = deck.cards.get(cid, 0)
                if copies:
                    add("Duelists", f"{name}: fixed deck, {plural(copies, 'copy', 'copies')}",
                        lambda d=d: app.open_pool(d, "deck", cid))
                continue
            weight = pools[pool].get(cid, 0)
            if weight:
                add("Duelists", f"{name}: {POOL_LABELS[pool]}, {weight * 100 / POOL_TOTAL:.2f}%",
                    lambda d=d, pool=pool: app.open_pool(d, pool, cid))
    for e in roster.copies(p):          # the duelists the mod adds
        deck = fixed_decks.deck_of(p, e)
        for pool in POOLS:
            if pool == "deck" and deck is not None:
                copies = deck.cards.get(cid, 0)
                if copies:
                    add("Duelists", f"{roster.shown_name(p, e)} (added): fixed deck, "
                                    f"{plural(copies, 'copy', 'copies')}",
                        lambda key=e.key: app.open_pool(key, "deck", cid))
                continue
            weight = e.pools[pool].get(cid, 0)
            if weight:
                add("Duelists", f"{roster.shown_name(p, e)} (added): {POOL_LABELS[pool]}, "
                                f"{weight * 100 / POOL_TOTAL:.2f}%",
                    lambda key=e.key, pool=pool: app.open_pool(key, pool, cid))
    for i, deck in enumerate(p.starter):
        copies = deck.cards.get(cid, 0)
        if copies:
            add("Starter decks", f"{deck.name or '(unnamed)'}: {plural(copies, 'copy', 'copies')}",
                lambda i=i: app.open_starter(i, cid))
    resolve = validate.pack_resolver(p)
    for i, entry in enumerate(p.packs):
        if not isinstance(entry, dict):
            continue
        for tier, pool in packmath.tiers_of(entry):
            if any(resolve(ref) == cid for ref, _ in packmath.pool_items(pool.get("cards", []))):
                name = entry.get("name", packmath.pack_id(entry))
                add("Packs", name + (f" (tier {tier})" if tier != "cards" else ""),
                    lambda i=i: app.open_pack(i))
        unlock = entry.get("unlock")
        if isinstance(unlock, dict) and "card" in unlock and resolve(unlock["card"]) == cid:
            add("Packs", entry.get("name", packmath.pack_id(entry)) + ": unlocked by owning it",
                lambda i=i: app.open_pack(i))
    # The Starter decks tab's Weighted pools page.
    for i, pool in enumerate(starter_pools.state(p)):
        weight = pool.cards.get(cid, 0)
        if weight:
            add("Starter pools", f"{pool.name or f'pool {i + 1}'}: weight {weight}",
                lambda i=i: app.open_starter_pool(i, cid))
    return lines


class UsesWindow(tk.Toplevel):
    """Where it's used: a window of its own beside the main one, listed again
    each time it comes to the front, so it follows the edits."""

    def __init__(self, app, cid):
        super().__init__(app)
        self.app, self.cid = app, cid
        self.transient(app)
        self.title(f"Where {app.project.card_label(cid)} is used")
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        self.summary = ttk.Label(top)
        self.summary.pack(side="left")
        ttk.Label(top, text="Double-click a line to go to it.", style="Hint.TLabel").pack(side="right")
        frame, self.tree = scrolled_tree(self, [("where", "Where"), ("what", "What")], [110, 440], 16)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", lambda e: self.go())
        self.tree.bind("<Return>", lambda e: self.go())
        ttk.Button(self, text="Close", command=self.destroy).pack(anchor="e", padx=8, pady=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<FocusIn>", lambda e: self.fill() if e.widget is self else None)
        self.minsize(px(self, 420), px(self, 240))
        self.lines = []
        self.fill()
        self.tree.focus_set()

    def fill(self):
        if self.app.project is None or self.cid not in self.app.project.cards:
            self.destroy()
            return
        self.lines = uses(self.app, self.cid)
        self.tree.delete(*self.tree.get_children())
        for i, (where, what, _) in enumerate(self.lines):
            self.tree.insert("", "end", iid=str(i), values=(where, what))
        self.summary.configure(text=f"{len(self.lines)} uses" if self.lines else
                               "Nothing in the mod uses this card: no fusion, equip, ritual, deck, drop, pack or starter pool.")
        if self.lines:
            self.tree.selection_set("0")
            self.tree.focus("0")

    def go(self):
        selection = self.tree.selection()
        if selection and int(selection[0]) < len(self.lines) and self.lines[int(selection[0])][2]:
            self.lines[int(selection[0])][2]()
