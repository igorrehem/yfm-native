"""Fixed opponent decks: forty cards written down in place of a weighted pool.

The port reads them from "decks" (src/pc/cards/tables.c read_fixed_deck):

    "decks": { "Simon Muran": { "fixed": true, "Kuriboh": 4, "Mystical Elf": 2, ... } }

each card with its copies, 0 to 40, adding up to exactly 40. A card the port
cannot name is left out and not counted, so it leaves the whole deck out; a
deck that is not forty is left out too, and the duelist is dealt the weighted
deck. There is no limit of three here: the author wrote down every copy.
A fixed deck wins over weighted edits of the same duelist.

A deck the editor read is written back exactly as it was while it is
untouched; one the editor made or changed is written as the importer writes
it: "fixed" first, then the cards in id order, then the names it could not
place. An entry for "all", or for a duelist another mod adds, is kept as
written.

A duelist this mod adds (roster.py) has its fixed deck in decks/<id>.json, as
its weighted one is: a FixedDeck with `file`, naming its roster entry, written
there by roster.files and not in mod.json. One the mod wrote in mod.json's
"decks" under the duelist's name or identity is edited there.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from fractions import Fraction

from .gamedata import DECK_COPY_LIMIT, DECK_SIZE, DUELIST_NAMES
from .model import Project, duelist_named

SKIPPED = ("fixed", "replace")      # read_fixed_deck passes these over


@dataclass
class FixedDeck:
    """One "decks" entry with "fixed": its key as written, the duelist it
    names (a disc id; a roster entry the mod adds; -1: "all" or a duelist the
    editor cannot place, kept as written), the cards by their copies, the
    names it could not place, the entry's other keys as written, and the
    entry as it was read (None: made here). `file`: the deck is its added
    duelist's decks/<id>.json, not a "decks" entry."""
    key: str
    duelist: object = -1
    cards: dict = field(default_factory=dict)   # card id -> copies
    kept: dict = field(default_factory=dict)    # name as written -> copies
    extra: dict = field(default_factory=dict)   # "fixed", "replace" and what is not a card, as written
    written: dict = None
    file: bool = False

    def total(self) -> int:
        return sum(self.cards.values()) + sum(self.kept.values())

    def complete(self) -> bool:
        return self.total() == DECK_SIZE and not self.kept

    def editable(self) -> bool:
        return not isinstance(self.duelist, int) or self.duelist >= 0


def _copies(value):
    """Copies as the port reads them (Json_Number of a JSON number), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    return number if 0 <= number <= DECK_SIZE else None


def _parse(project: Project, entry: dict, messages: list = None, where: str = ""):
    """(cards, kept, extra) of an entry, reading it as read_fixed_deck does."""
    cards, kept, extra = {}, {}, {}
    for name, value in entry.items():
        if name in SKIPPED:
            extra[name] = value
            continue
        copies = _copies(value)
        if copies is None:
            if messages is not None:
                messages.append(f"{where} \"{name}\": a fixed deck gives each card its copies, 0 to {DECK_SIZE}; "
                                "left out")
            extra[name] = value
            continue
        cid = project.resolve(name)
        if not cid:
            if messages is not None:
                messages.append(f"{where} \"{name}\": no such card; kept as written")
            kept[name] = kept.get(name, 0) + copies
            continue
        if copies:
            # Two names for one card are its copies added up, as the port deals them.
            cards[cid] = cards.get(cid, 0) + copies
    return cards, kept, extra


def read_entry(project: Project, name: str, entry: dict, messages: list):
    """A "decks" entry whose "fixed" is true (manifest.read_pools)."""
    where = f"decks \"{name}\""
    every = "".join(c for c in name.lower() if c.isalnum()) == "all"
    d = -1 if every else duelist_named(name)
    if d < 0 and not every:
        from . import roster
        found = roster.named(project, name)        # one of the mod's own, by its name or identity
        d = found if found is not None else -1
    deck = FixedDeck(key=name, duelist=d, written=copy.deepcopy(entry))
    if not deck.editable():
        whose = "every duelist" if every else "a duelist the disc does not have"
        messages.append(f"{where}: a fixed deck for {whose}; kept as written")
    else:
        deck.cards, deck.kept, deck.extra = _parse(project, entry, messages, where)
        if deck.total() != DECK_SIZE:
            messages.append(f"{where}: a fixed deck is {DECK_SIZE} cards, and this one has {deck.total()}; "
                            "the port leaves it out until it is")
    project.fixed[name] = deck


def read_file(project: Project, rel: str, e, entry: dict, messages: list):
    """decks/<id>.json of a duelist the mod adds, holding a fixed deck
    (roster.read_pool_folders)."""
    deck = FixedDeck(key=rel, duelist=e, written=copy.deepcopy(entry), file=True)
    deck.cards, deck.kept, deck.extra = _parse(project, entry, messages, rel)
    if deck.total() != DECK_SIZE:
        messages.append(f"{rel}: a fixed deck is {DECK_SIZE} cards, and this one has {deck.total()}; "
                        "the port leaves it out until it is")
    project.fixed.pop(rel, None)
    project.fixed[rel] = deck
    return deck


def _entry(project: Project, deck: FixedDeck) -> dict:
    if deck.written is not None:
        if not deck.editable():
            return deck.written
        # Written back as it was while it still reads as what the deck holds
        # now: a card named by an identity whose mod id changed does not.
        cards, kept, _ = _parse(project, deck.written)
        if cards == deck.cards and kept == deck.kept:
            return deck.written
    entry = {"fixed": True}
    entry.update(deck.extra)
    for cid in sorted(deck.cards):
        if deck.cards[cid]:
            entry[str(project.ref(cid))] = deck.cards[cid]
    entry.update(deck.kept)
    return entry


def build(project: Project) -> dict:
    """{key: entry} in the order the mod had them, new decks after; laid over
    the weighted edits (manifest.build_pools), so a fixed deck takes the place
    of a weighted edit written under the same key. An added duelist's own
    file is keyed by its roster entry, as its weighted deck is (roster.files)."""
    return {(deck.duelist if deck.file else key): _entry(project, deck) for key, deck in project.fixed.items()}


def _is(deck: FixedDeck, d) -> bool:
    """Whether the deck names duelist d (an id, or a roster entry: itself)."""
    return deck.duelist is d if not isinstance(d, int) else isinstance(deck.duelist, int) and deck.duelist == d


def deck_of(project: Project, d):
    """The fixed deck the port deals duelist d (a disc id or an added
    duelist's roster entry): the latest one naming it, the folder's file
    being read after mod.json."""
    found = None
    for deck in project.fixed.values():
        if _is(deck, d):
            found = deck
    return found


def keys_of(project: Project, d) -> list:
    return [key for key, deck in project.fixed.items() if _is(deck, d)]


def set_deck(project: Project, d, cards: dict) -> FixedDeck:
    """Duelist d's fixed deck made `cards` (id -> copies); a new one is
    written under the duelist's name, as the weighted edits are, or for a
    duelist the mod adds in its decks/<id>.json."""
    deck = deck_of(project, d)
    if deck is None:
        if isinstance(d, int):
            key = DUELIST_NAMES[d] if d else "0"
            deck = FixedDeck(key=key, duelist=d, extra={"fixed": True})
        else:
            key = f"decks/{d.key}.json"
            while key in project.fixed:     # an older file's, the duelist since renamed
                key += "+"
            deck = FixedDeck(key=key, duelist=d, extra={"fixed": True}, file=True)
        project.fixed.pop(key, None)
        project.fixed[key] = deck
    deck.cards = {cid: n for cid, n in cards.items() if n}
    deck.kept = {}
    return deck


def remove(project: Project, d) -> list:
    """Duelist d dealt the weighted deck again: its fixed decks taken out
    (and returned, so the tab can put them back)."""
    taken = []
    for key in keys_of(project, d):
        taken.append(project.fixed.pop(key))
    return taken


def restore(project: Project, decks: list):
    for deck in decks:
        project.fixed[deck.key] = deck


def most_likely(pool: dict, size: int = DECK_SIZE, cap: int = DECK_COPY_LIMIT) -> dict:
    """The deck a weighted pool deals most likely: its weights apportioned to
    `size` cards (largest remainder), no card past the `cap` copies the
    retail deal allows (duel_shuffle_deck.c DECK_CARD_COPY_LIMIT) -- unless
    the pool has too few cards to fill a deck that way. Ties go to the
    heavier card, then the lower id."""
    weights = {c: w for c, w in pool.items() if w > 0}
    if not weights:
        return {}
    if len(weights) * cap < size:
        cap = size
    capped = {}
    while True:
        free = {c: w for c, w in weights.items() if c not in capped}
        room = size - sum(capped.values())
        total = sum(free.values())
        if not free or not total or room <= 0:
            break
        over = [c for c, w in free.items() if Fraction(room * w, total) > cap]
        if not over:
            break
        for c in over:
            capped[c] = cap
    counts = dict(capped)
    free = {c: w for c, w in weights.items() if c not in capped}
    room = size - sum(capped.values())
    total = sum(free.values())
    if free and total and room > 0:
        quotas = {c: Fraction(room * w, total) for c, w in free.items()}
        for c, q in quotas.items():
            counts[c] = int(q)
        left = room - sum(int(q) for q in quotas.values())
        order = sorted(free, key=lambda c: (-(quotas[c] - int(quotas[c])), -free[c], c))
        for c in order[:left]:
            counts[c] += 1
    return {c: n for c, n in counts.items() if n}


def check(project: Project, out: list):
    """What the port would refuse or not deal as meant (validate.validate)."""
    from . import roster
    from .validate import Issue
    seen = {}
    for key, deck in project.fixed.items():
        if not deck.editable():
            continue
        seen.setdefault(deck.duelist, []).append(key)
    for d, keys in sorted(seen.items(), key=lambda item: (not isinstance(item[0], int),
                                                         item[0] if isinstance(item[0], int) else item[0].key)):
        if not isinstance(d, int) and d not in roster.entries(project):
            continue        # a duelist taken out since (roster.remove takes its decks too)
        deck = deck_of(project, d)
        where = f"{roster.label(project, d)} fixed deck"
        target = (d, "deck")
        if len(keys) > 1:
            out.append(Issue("warning", "Duelists", where,
                             f"written {len(keys)} times ({', '.join(keys)}); the port deals the last one", target))
        total = deck.total()
        if total != DECK_SIZE:
            out.append(Issue("error", "Duelists", where,
                             f"a fixed deck is {DECK_SIZE} cards, and this one has {total}; the port leaves it out "
                             "and deals the weighted deck", target))
        for name in deck.kept:
            out.append(Issue("error", "Duelists", where,
                             f"\"{name}\" is no card the editor knows; the port leaves it out uncounted, and the "
                             "deck with it", target))
        for cid, copies in sorted(deck.cards.items()):
            if cid not in project.cards:
                out.append(Issue("error", "Duelists", where, f"no card {cid}", target))
            elif not 0 <= copies <= DECK_SIZE:
                out.append(Issue("error", "Duelists", where,
                                 f"{copies} copies of {project.card_label(cid)}: a card has 0 to {DECK_SIZE}", target))
        weighted = {c: w for c, w in roster.pools_of(project, d)["deck"].items() if w}
        if weighted != roster.retail_pool(project, d, "deck"):
            out.append(Issue("warning", "Duelists", where,
                             "the deck is fixed, so the weighted deck's edits are not dealt", target))
