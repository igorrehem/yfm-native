"""A mod's "starter_pools" (notes/starter-deck.md): pools of its own for a new
game's deck to be drawn from, in place of writing the forty cards down.

The port reads them in src/pc/cards/starter.c; the checks here are that file's,
so a problem shows in the editor rather than as a line in the Mods window.

The mod.json shape:

    "starter_pools": [
        {"name": "Weak monsters", "draws": 16, "cards": {"Mystical Elf": 100}},
        {"draws": 24, "cards": {"Dark Magician": 1, "My Added Card": 3}}
    ]

Each pool draws its own number of cards from its own weights, and the draws
must add up to the forty a deck holds. A draw spreads a random number over the
pool's weight total and walks its cards until the weights reach it, as the
disc's generator walks a row of its own.

What this does that the disc's rows cannot: the disc keeps 722 weights of a
fixed width and reads only the first 720, so no weight of its own can name a
card a mod added. A pool here names cards the way the rest of a manifest does,
so a mod's own are weighted like any other.

A written deck still wins: the port asks for one first, then for these, and
reads the disc's rows only when neither is offered.

The editor keeps the section in Project.other["starter_pools"] as written; the
Starter decks tab turns it into `Pool`s (`read`) and back (`build`).
"""
from __future__ import annotations

import json

import copy
from dataclasses import dataclass, field

from .gamedata import DECK_SIZE

DRAWS = DECK_SIZE           # the pools' draws add up to a deck
DRAW_MAX = DECK_SIZE
WEIGHT_MAX = 65535          # STARTER_POOL_WEIGHT_LIMIT
RETRIES = 64                # STARTER_POOL_RETRIES, before a draw gives up
COPY_LIMIT = 3              # DECK_CARD_COPY_LIMIT: what a retry is for
KEYS = ("name", "draws", "cards")


@dataclass
class Pool:
    """One pool: how many cards it draws, and a weight for each card."""
    name: str = None
    draws: int = 0
    cards: dict = field(default_factory=dict)   # card id -> weight
    kept: dict = field(default_factory=dict)    # name as written -> weight
    extra: dict = field(default_factory=dict)   # keys the editor does not show

    def total(self) -> int:
        return sum(self.cards.values()) + sum(self.kept.values())

    def count(self) -> int:
        return sum(1 for w in self.cards.values() if w) + sum(1 for w in self.kept.values() if w)

    def copy(self) -> "Pool":
        return Pool(self.name, self.draws, dict(self.cards), dict(self.kept), copy.deepcopy(self.extra))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read(section, resolve) -> list:
    """The tab's model from a section as a mod wrote it. `resolve` turns a
    card as the manifest names it into an id, 0 for one it cannot place."""
    if isinstance(section, dict):
        section = [section]
    if not isinstance(section, list):
        return []
    out = []
    for entry in section:
        if not isinstance(entry, dict):
            continue
        pool = Pool()
        pool.name = entry["name"] if isinstance(entry.get("name"), str) else None
        pool.draws = entry["draws"] if _is_int(entry.get("draws")) else 0
        pool.extra = {k: copy.deepcopy(v) for k, v in entry.items() if k not in KEYS}
        cards = entry.get("cards")
        if isinstance(cards, dict):
            for name, weight in cards.items():
                if not _is_int(weight):
                    continue
                cid = resolve(name)
                # A card the editor cannot place keeps its row under the name
                # it was written with, so somebody else's pool is not lost.
                if cid:
                    pool.cards[cid] = pool.cards.get(cid, 0) + weight
                else:
                    pool.kept[str(name)] = weight
        out.append(pool)
    return out


def readable(section) -> bool:
    """Whether the Weighted pools page reads all of a section: a pool or a
    list of them, each an object with whole-number draws and weights."""
    pools = [section] if isinstance(section, dict) else section
    if not isinstance(pools, list):
        return False
    for entry in pools:
        if not isinstance(entry, dict) or ("draws" in entry and not _is_int(entry["draws"])):
            return False
        cards = entry.get("cards", {})
        if not isinstance(cards, dict) or not all(_is_int(w) for w in cards.values()):
            return False
    return True


def build(pools, ref) -> list:
    """"starter_pools" for mod.json; None when no pool is offered. `ref` names
    a card as the manifest names one."""
    out = []
    for pool in pools:
        entry = dict(pool.extra)
        if pool.name:
            entry["name"] = pool.name
        entry["draws"] = pool.draws
        cards = {}
        for cid, weight in sorted(pool.cards.items()):
            cards[ref(cid)] = weight
        cards.update(pool.kept)
        entry["cards"] = cards
        out.append(entry)
    return out or None


def state(project) -> list:
    """The pools the project holds, read once and kept on it."""
    found = getattr(project, "starter_pool_state", None)
    # Read again when the section changed under it (Mod info's other keys).
    source = json.dumps(project.other.get("starter_pools"), default=str)
    if found is None or getattr(project, "starter_pool_source", None) != source:
        found = read(project.other.get("starter_pools"), project.resolve)
        project.starter_pool_state = found
        project.starter_pool_source = source
    return found


def store(project):
    """The model back into the project's "starter_pools"."""
    built = build(state(project), project.ref)
    if built is None:
        project.other.pop("starter_pools", None)
    else:
        project.other["starter_pools"] = built
    project.starter_pool_source = json.dumps(project.other.get("starter_pools"), default=str)


def drawn(project) -> int:
    return sum(pool.draws for pool in state(project))


def deals(project) -> bool:
    """Whether the pools would deal a deck, as Starter_HasPools has it."""
    pools = state(project)
    return bool(pools) and drawn(project) == DRAWS


def check(project, out: list):
    """What the port would make of the pools, as validate.Issue."""
    from .validate import Issue
    pools = state(project)
    if not pools:
        return

    def add(level, index, message):
        where = f"pool {index + 1}" if index is not None else "starter_pools"
        out.append(Issue(level, "Starter pools", where, message, index))

    total = drawn(project)
    if total != DRAWS:
        add("error", None, f"the pools draw {total} cards, not the {DRAWS} a deck holds; "
                           "the game would read the disc's own rows instead")
    for index, pool in enumerate(pools):
        if not 0 <= pool.draws <= DRAW_MAX:
            add("error", index, f"a pool's draws are 0 to {DRAW_MAX}")
        for name, weight in pool.kept.items():
            add("error", index, f"\"{name}\": no such card; the game leaves it out")
        if any(not 0 <= w <= WEIGHT_MAX for w in pool.cards.values()):
            add("error", index, f"a weight is 0 to {WEIGHT_MAX}")
        if not pool.draws:
            continue
        if not pool.count():
            add("error", index, "it draws cards but weights none; the game leaves the pools out")
        elif pool.count() <= COPY_LIMIT and pool.draws > pool.count() * COPY_LIMIT:
            add("warning", index, f"it draws {pool.draws} from {pool.count()} card(s): past "
                                  f"{COPY_LIMIT} copies each the draw is retried, and after "
                                  f"{RETRIES} tries the last one stands")
    if project.starter:
        add("warning", None, "the mod writes starter decks down as well, and those are dealt first: "
                             "these pools are read only when no deck is offered")


# --- the disc's own rows ------------------------------------------------------
#
# Seven NameEntryStarterDeckPool records, byte-identical in both screen
# packages (notes/starter-deck-pools.md):
#
#     u16 draw_count; u16 weights[722]; u8 padding[18];   /* 0x5B8 */
#
# A weight's place is the card before it: index i weighs card i + 1. The
# generator reads only the first SCAN of them.

RETAIL_AT = 0xF92BD4        # the name-entry package's copy
RETAIL_COUNT = 7
RETAIL_STRIDE = 0x5B8
RETAIL_WEIGHTS = 722
RETAIL_SCAN = 720           # STARTER_DECK_WEIGHT_SCAN_COUNT
RETAIL_NAMES = ("Weakest monsters", "Weak monsters", "Middling monsters", "Strong monsters",
                "Dark Hole and Raigeki", "Terrain", "Equips")


def retail(wa: bytes) -> list:
    """The disc's seven pools, as `Pool`s; [] when the archive has not got
    them (a cut-down one, or none loaded)."""
    import struct
    end = RETAIL_AT + RETAIL_COUNT * RETAIL_STRIDE
    if not wa or len(wa) < end:
        return []
    out = []
    for n in range(RETAIL_COUNT):
        at = RETAIL_AT + n * RETAIL_STRIDE
        draws = struct.unpack_from("<H", wa, at)[0]
        weights = struct.unpack_from(f"<{RETAIL_WEIGHTS}H", wa, at + 2)
        pool = Pool(name=RETAIL_NAMES[n] if n < len(RETAIL_NAMES) else None, draws=draws)
        for index, weight in enumerate(weights[:RETAIL_SCAN]):
            if weight:
                pool.cards[index + 1] = weight
        out.append(pool)
    return out


def deal(pools, rng=None, cap: int = 3) -> dict:
    """One deck the pools could deal ({card: copies}): each pool draws its
    number of cards by the weights, a card already dealt `cap` times drawn
    again, as the disc's deal does (name_entry_main.c); an example, as a new
    game's is random."""
    import random
    rng = rng or random.Random()
    deck = {}
    for pool in pools:
        cards = [c for c, w in pool.cards.items() if w > 0]
        drawn = 0
        while drawn < pool.draws:
            free = [c for c in cards if deck.get(c, 0) < cap]
            if not free:
                break           # a pool too small for its draws: what it has
            cid = rng.choices(free, weights=[pool.cards[c] for c in free])[0]
            deck[cid] = deck.get(cid, 0) + 1
            drawn += 1
    return deck


def retail_drawn(pools) -> int:
    return sum(pool.draws for pool in pools)
