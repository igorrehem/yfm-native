"""Card packs ("packs" and "pack_shop", notes/card-packs.md): the port's
reader and dealer (src/pc/cards/packs.c) again in Python, for the Packs tab's
checks, its Chance column and Simulate.

The dealer must deal what the game deals for the same random numbers:
tests/pc/packs_fixture.json and packs_golden.txt hold packs the C dealt, and
tests/test_packs.py deals them here and compares, line for line. Every step
below follows a function of packs.c; change one only with the other.

A pack is kept in the editor as the JSON object the mod writes (a dict), so a
key the editor has no field for stays as written; `read_pack` makes of it what
the game makes, with the notes the game's Mods window would show, and
`minimize` writes back only what differs from the defaults.
"""
from __future__ import annotations

import bisect
import copy
import re
from dataclasses import dataclass, field

CARD_COUNT = 722
PACKS_MAX = 255
TIERS_MAX = 16
SHOPS_MAX = 16
COUNT_MAX = 40
COST_CARDS_MAX = 8
OPENED_MAX = 8
WEIGHT_TOTAL_MAX = 1000000
PRICE_MAX = 999999
DRAWS_PER_SLOT = 4
DEFAULT_COUNT = 5
DEFAULT_PRICE = 100
NAME_LETTERS = 16
DEFAULT_MUSIC = 29520
SOUND_KEYS = ("move", "buy", "refuse", "reveal", "back")
DEFAULT_SOUNDS = {"move": 47, "buy": 48, "refuse": 9, "reveal": 12, "back": 8}
REVEALS = ("flip", "quick", "list")
IMAGE_STYLES = ("card", "full")      # "image_style": the picture as a card's art, or the whole picture
CARD_VIEW = (140, 196)              # the big card's frame, where a "full" picture is fitted


def fit_full(width: int, height: int):
    """pack_shop.c fit_picture: the size a PNG is drawn at with "image_style":
    "full", as large as fits the card with its shape kept, even across."""
    cw, ch = CARD_VIEW
    if width * ch > height * cw:
        w, h = cw, (height * cw + width // 2) // width
    else:
        w, h = (width * ch + height // 2) // height, ch
    return max(w & ~1, 2), max(h, 1)

NOTHING_LEFT = ("refuse", "sell")    # "when_nothing_left"; "refuse" is the shop's default
DESCRIPTION_BYTES = 255
# \A and \Z: "$" would let a trailing newline through.
KEY_RE = re.compile(r"\A[A-Za-z0-9_-]{1,63}\Z")

PACK_KEYS = ("id", "name", "description", "image", "image_style", "cover", "shop", "order", "price", "cost", "count",
             "cards", "tiers", "slots", "guarantee", "pity", "duplicates", "max_copies", "include_added_cards",
             "stock", "unlock", "locked", "password", "once", "listed", "reveal", "sounds", "when_nothing_left")
PACK_RESERVED = ("restock",)
TIER_KEYS = ("odds", "cards", "label", "color", "sound", "reveal")
COST_KEYS = ("starchips", "cards")
COST_RESERVED = ("currency",)
SLOT_KEYS = ("tiers", "cards", "card")
UNLOCK_KEYS = ("beat", "wins", "story", "card", "copies", "starchips_spent", "opened", "packs_opened")
RULES_KEYS = ("password", "shops", "rng", "music", "when_nothing_left", "campaign_shop", "main_menu",
              "sell_added_cards", "autosave")
RULES_RESERVED = ("currency", "earn")
RULES_LATER = ("campaign_shop", "main_menu", "sell_added_cards", "autosave")
SHOP_KEYS = ("id", "name", "unlock", "where")
SHOP_PASSWORD = ("both", "packs_only", "password_only")
# What the game has not built yet: the keys stay free for it (notes/card-packs.md).
NOT_YET = ("campaign_shop", "main_menu", "autosave", "sell_added_cards", "currency", "restock")

SLOT_ODDS, SLOT_TIER, SLOT_MIX, SLOT_POOL, SLOT_CARD = range(5)


class _Missing:
    """A key left out, apart from a key written null: the game's reader
    (packs.c) takes null for a value of the wrong kind."""

    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def whole(value):
    """The whole number a JSON number is (the game's reader takes 100.0 and
    1e2 for 100: json.c parse_number), or None for anything else."""
    if is_int(value):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def json_bool(value, fallback):
    """json.c Json_Bool: true/false, or a number (not 0 is true); anything
    else, null too, is the fallback."""
    if isinstance(value, bool):
        return value
    if whole(value) is not None:
        return whole(value) != 0
    if isinstance(value, float):
        return value != 0
    return fallback


def json_string(value, fallback):
    """json.c Json_String: the text, or the fallback for anything else."""
    return value if isinstance(value, str) else fallback


def slug(name: str) -> str:
    """The id a pack with no "id" gets from its name (packs.c slug)."""
    out, hyphen = [], False
    for c in name if isinstance(name, str) else "":
        if c.isascii() and c.isalnum():
            if hyphen and out:
                out.append("-")
            out.append(c.lower())
            hyphen = False
        else:
            hyphen = True
    return "".join(out)[:63] or "pack"


def _distance(a: str, b: str) -> int:
    if len(a) > 32 or len(b) > 32:
        return 99
    row = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        diagonal, row[0] = row[0], i
        for j in range(1, len(b) + 1):
            above = row[j]
            best = diagonal + (a[i - 1].lower() != b[j - 1].lower())
            best = min(best, above + 1, row[j - 1] + 1)
            diagonal, row[j] = above, best
    return row[len(b)]


def unknown_keys(where: str, obj: dict, known, reserved=()) -> list:
    """The notes packs.c check_keys writes: did-you-mean, or not built yet."""
    out = []
    for name in obj:
        if name in known:
            continue
        if name in reserved:
            out.append(("warning", f"{where}: \"{name}\" is not built yet (notes/card-packs.md); ignored"))
            continue
        best, closest = 3, None
        for key in known:
            apart = _distance(name, key)
            if apart < best:
                best, closest = apart, key
        out.append(("warning", f"{where}: unknown key \"{name}\"" + (f" (did you mean \"{closest}\"?)" if closest
                                                                     else "")))
    return out


def number(value, low, high, fallback):
    """(number, bad): the whole number in [low, high], or the fallback when
    left out, MISSING (packs.c number_in: a JSON number, not a string; null
    is bad)."""
    if value is MISSING:
        return fallback, False
    n = whole(value)
    if n is None or not low <= n <= high:
        return fallback, True
    return n, False


def password_bits(value):
    """Up to eight digits, four bits each (packs.c read_password); None."""
    if whole(value) is not None and 0 <= whole(value) <= 99999999:
        value = f"{whole(value):08d}"
    if not isinstance(value, str) or not 1 <= len(value) <= 8 or not value.isdigit() or not value.isascii():
        return None
    return int(value.zfill(8), 16)


# --- pools --------------------------------------------------------------------

def pool_items(value) -> list:
    """[(card as written, weight)] of a pool, list or object, in its order."""
    if isinstance(value, list):
        return [(item, 1) for item in value]
    if isinstance(value, dict):
        return list(value.items())
    return []


def pool_value(items):
    """A pool as the mod writes it: a list when every weight is 1."""
    if all(is_int(w) and w == 1 for _, w in items):
        return [ref for ref, _ in items]
    return {str(ref): w for ref, w in items}


@dataclass
class Tier:
    name: str
    odds: int = 1
    pool: list = field(default_factory=list)      # [(card id, weight)], weights > 0
    label: str = ""
    color: int = -1
    sound: int = -1
    reveal: int = -1


@dataclass
class Slot:
    kind: int
    tier: int = -1
    mix: list = field(default_factory=list)       # a weight by tier
    pool: list = field(default_factory=list)
    card: int = 0


@dataclass
class Pack:
    mod: str
    id: str
    identity: str
    name: str = ""
    description: str = ""
    count: int = DEFAULT_COUNT
    price: int = DEFAULT_PRICE
    cost_cards: list = field(default_factory=list)   # [(card, copies)]
    tiers: list = field(default_factory=list)
    slots: list = None
    guarantee: list = field(default_factory=lambda: [0] * TIERS_MAX)
    pity: list = field(default_factory=lambda: [0] * TIERS_MAX)
    unique: bool = False
    max_copies: int = 0
    include_added: bool = True
    stock: int = -1
    cover: int = 0
    listed: bool = True
    once: bool = False
    password: int = None
    order: int = 0
    reveal: int = 0
    when_nothing_left: str = None                    # "refuse", "sell", or None for the shop's
    shops: list = None                               # the shop ids it names; None for every shop

    def tier_named(self, name) -> int:
        for t, tier in enumerate(self.tiers):
            if tier.name == name:
                return t
        return -1

    def slot_kind(self, s: int) -> int:
        return self.slots[s].kind if self.slots else SLOT_ODDS


def _card_shown(value) -> str:
    """As packs.c pool_card shows a card it cannot find."""
    if whole(value) is not None:
        return str(whole(value))
    return value if isinstance(value, str) else "?"


def _pool_card(value, resolve, include_added, where, notes) -> int:
    cid = resolve(value)
    if not cid or cid <= 0:
        notes.append(("warning", f"{where}: no card \"{_card_shown(value)}\"; left out"))
        return 0
    if not include_added and cid > CARD_COUNT:
        notes.append(("warning", f"{where}: card {cid} is a mod's, and \"include_added_cards\" is false; left out"))
        return 0
    return cid


def read_pool(value, resolve, include_added, where, notes):
    """[(card, weight)] as packs.c read_pool, or None on an error that leaves
    the pack out (said in `notes`)."""
    pool = []
    if isinstance(value, list):
        for i, item in enumerate(value):
            cid = _pool_card(item, resolve, include_added, f"{where}[{i}]", notes)
            if cid > 0:
                pool.append((cid, 1))
    elif isinstance(value, dict):
        for name, weight in value.items():
            at = f"{where} \"{name}\""
            weight = whole(weight)
            if weight is None or not 0 <= weight <= WEIGHT_TOTAL_MAX:
                notes.append(("error", f"{at}: a weight is a whole number, 0 to {WEIGHT_TOTAL_MAX}; the pack is "
                                       "left out"))
                return None
            cid = _pool_card(name, resolve, include_added, at, notes)
            if cid > 0 and weight > 0:
                pool.append((cid, weight))
    else:
        notes.append(("error", f"{where}: a pool is a list of cards, or an object of cards and their weights; the "
                               "pack is left out"))
        return None
    total = sum(w for _, w in pool)
    if total > WEIGHT_TOTAL_MAX:
        notes.append(("error", f"{where}: the weights add up to {total}, more than {WEIGHT_TOTAL_MAX}; the pack is "
                               "left out"))
        return None
    return pool


def duplicate_keys(obj) -> tuple:
    """The keys an object had twice in its file (manifest.read_json marks
    them): Python keeps one, the game's reader sees both."""
    return tuple(getattr(obj, "duplicates", ()))


def entry_id(entry, taken_ids=()):
    """The id an entry of "packs" is read by, or None when the game leaves
    it out before counting it among the packs declared: not an object, an
    "id" that is not 1-63 of [A-Za-z0-9_-], or another pack's id."""
    if not isinstance(entry, dict):
        return None
    pid = json_string(entry["id"], "") if "id" in entry else slug(json_string(entry.get("name"), "pack"))
    if "id" in entry and not KEY_RE.match(pid):
        return None
    return None if pid in taken_ids else pid


def read_pack(entry, resolve, mod: str = "mod", index: int = 0, taken_ids=(), declared=None) -> tuple:
    """(Pack or None, notes): what the game makes of one entry of "packs"
    (packs.c read_pack), notes as ("error"|"warning", text). `resolve`
    names a card: its id, or 0/negative for none (Cards_Reference). A key
    written null is a value of the wrong kind, as the game reads it; a key
    left out takes its default. `declared` is the entry's place among the
    packs that got past their id (read_packs counts them), which a pack without
    "order" is ordered by; `index` when not given."""
    notes = []
    where = f"packs[{index}]"
    if not isinstance(entry, dict):
        return None, [("error", f"{where}: a pack is an object")]
    notes += unknown_keys(where, entry, PACK_KEYS, PACK_RESERVED)
    for key in duplicate_keys(entry):
        notes.append(("warning", f"{where}: \"{key}\" is written twice; the game reads the first, the editor the last"))
    if "id" in entry:
        pid = json_string(entry["id"], "")
        if not KEY_RE.match(pid):
            notes.append(("error", f"{where}: \"id\" is 1-63 letters, digits, '_' or '-'; the pack is left out"))
            return None, notes
    else:
        pid = slug(json_string(entry.get("name"), "pack"))
    if pid in taken_ids:
        notes.append(("error", f"{where}: the id \"{pid}\" is another pack's of this mod; the pack is left out"))
        return None, notes
    pack = Pack(mod=mod, id=pid, identity=f"{mod}:{pid}")
    where = f"pack \"{pid}\""
    name = json_string(entry.get("name"), pid)
    if len(name) > NAME_LETTERS:
        notes.append(("warning", f"{where}: the name has room for {NAME_LETTERS} letters; cut there"))
        name = name[:NAME_LETTERS]
    pack.name = name
    description = json_string(entry.get("description"), "")
    if len(description.encode("utf-8")) > DESCRIPTION_BYTES:
        notes.append(("warning", f"{where}: the description has room for {DESCRIPTION_BYTES} bytes of UTF-8; cut "
                                 "there"))
        description = description.encode("utf-8")[:DESCRIPTION_BYTES].decode("utf-8", "ignore")
    pack.description = description
    pack.order = index if declared is None else declared
    if "order" in entry:
        pack.order, bad = number(entry["order"], -1000000, 1000000, pack.order)
        if bad:
            notes.append(("warning", f"{where}: \"order\" is a whole number; the pack keeps its place"))

    bad_price = False
    price, bad = number(entry.get("price", MISSING), 0, PRICE_MAX, DEFAULT_PRICE)
    bad_price |= bad
    if "cost" in entry:
        cost = entry["cost"]
        if not isinstance(cost, dict):
            notes.append(("error", f"{where}: \"cost\" is {{\"starchips\": n, \"cards\": {{card: copies}}}}; the pack "
                                   "is left out"))
            return None, notes
        notes += unknown_keys(where, cost, COST_KEYS, COST_RESERVED)
        if "starchips" in cost:
            starchips, bad = number(cost["starchips"], 0, PRICE_MAX, price)
            bad_price |= bad
            if "price" in entry and starchips != price:
                notes.append(("warning", f"{where}: \"price\" and \"cost\" differ; \"cost\" is used"))
            price = starchips
        cards = cost.get("cards", MISSING)
        if cards is not MISSING and not isinstance(cards, dict):
            notes.append(("error", f"{where}: \"cost\" \"cards\" is {{card: copies}}; the pack is left out"))
            return None, notes
        for name_, copies in (cards.items() if isinstance(cards, dict) else []):
            cid = resolve(name_)
            copies = whole(copies)
            if copies is None or not 1 <= copies <= 250:
                notes.append(("error", f"{where}: \"cost\" takes 1 to 250 copies of a card; the pack is left out"))
                return None, notes
            if not cid or cid <= 0:
                notes.append(("warning", f"{where}: no card \"{name_}\"; left out"))
                notes.append(("error", f"{where}: a card \"cost\" names is not here; the pack is left out"))
                return None, notes
            if len(pack.cost_cards) >= COST_CARDS_MAX:
                notes.append(("error", f"{where}: \"cost\" names at most {COST_CARDS_MAX} cards; the pack is left out"))
                return None, notes
            pack.cost_cards.append((cid, copies))
    if bad_price:
        notes.append(("error", f"{where}: \"price\" (and \"cost\" \"starchips\") is 0 to {PRICE_MAX} starchips; the "
                               "pack is left out"))
        return None, notes
    pack.price = price

    pack.include_added = json_bool(entry.get("include_added_cards"), True)
    if "duplicates" in entry:
        if entry["duplicates"] == "unique_in_pack":
            pack.unique = True
        elif entry["duplicates"] != "allow":
            notes.append(("warning", f"{where}: \"duplicates\" is \"allow\" or \"unique_in_pack\"; allowed"))
    bad_count = False
    pack.max_copies, bad = number(entry.get("max_copies", MISSING), 1, 250, 0)
    bad_count |= bad
    tiers, cards, slots = entry.get("tiers"), entry.get("cards"), entry.get("slots")
    if "tiers" in entry and "cards" in entry:
        notes.append(("error", f"{where}: \"cards\" is a pack of one tier and \"tiers\" is several; give one; the "
                               "pack is left out"))
        return None, notes
    if "cards" in entry:
        pool = read_pool(cards, resolve, pack.include_added, f"{where} cards", notes)
        if pool is None:
            return None, notes
        pack.tiers.append(Tier("cards", 1, pool))
    elif isinstance(tiers, dict):
        for tname in duplicate_keys(tiers):
            notes.append(("error", f"{where} tier \"{tname}\": named twice; the pack is left out"))
            return None, notes
        for tname, value in tiers.items():
            at = f"{where} tier \"{tname}\""
            if not KEY_RE.match(tname):
                notes.append(("error", f"{at}: a tier's name is 1-63 letters, digits, '_' or '-'; the pack is left out"))
                return None, notes
            if len(pack.tiers) >= TIERS_MAX:
                notes.append(("error", f"{at}: a pack has at most {TIERS_MAX} tiers; the pack is left out"))
                return None, notes
            if not isinstance(value, dict):
                notes.append(("error", f"{at}: a tier is an object with \"odds\" and \"cards\"; the pack is left out"))
                return None, notes
            notes += unknown_keys(at, value, TIER_KEYS)
            odds, b1 = number(value.get("odds", MISSING), 0, WEIGHT_TOTAL_MAX, 1)
            color, b2 = number(value.get("color", MISSING), 0, 15, -1)
            sound, b3 = number(value.get("sound", MISSING), 0, 0xFFFF, -1)
            if b1 or b2 or b3:
                notes.append(("error", f"{at}: \"odds\" is 0 to {WEIGHT_TOTAL_MAX}, \"color\" 0 to 15 and \"sound\" a "
                                       "sound id; the pack is left out"))
                return None, notes
            tier = Tier(tname, odds, [], json_string(value.get("label"), ""), color, sound)
            if "reveal" in value:
                if value["reveal"] in REVEALS:
                    tier.reveal = REVEALS.index(value["reveal"])
                else:
                    notes.append(("warning", f"{at}: \"reveal\" is \"flip\", \"quick\" or \"list\"; the pack's is used"))
            pack.tiers.append(tier)
            if "cards" not in value:
                notes.append(("warning", f"{at}: no \"cards\""))
                continue
            pool = read_pool(value["cards"], resolve, pack.include_added, f"{where} tier \"{tname}\" cards", notes)
            if pool is None:
                return None, notes
            tier.pool = pool
    else:
        notes.append(("error", f"{where}: no \"cards\" or \"tiers\" to deal from; the pack is left out"))
        return None, notes
    if not any(t.pool for t in pack.tiers) and "slots" not in entry:
        notes.append(("error", f"{where}: none of its cards are here; the pack is left out"))
        return None, notes
    default = len(slots) if isinstance(slots, list) else DEFAULT_COUNT
    pack.count, bad = number(entry.get("count", MISSING), 1, COUNT_MAX, default)
    bad_count |= bad
    if bad_count or not 1 <= pack.count <= COUNT_MAX:  # "slots" of more, and no "count"
        notes.append(("error", f"{where}: \"count\" is 1 to {COUNT_MAX} cards and \"max_copies\" 1 to 250; the pack is "
                               "left out"))
        return None, notes
    if "slots" in entry:
        if not isinstance(slots, list) or len(slots) != pack.count:
            notes.append(("error", f"{where}: \"slots\" is a list of {pack.count}, one a card; the pack is left out"))
            return None, notes
        pack.slots = []
        for i, value in enumerate(slots):
            slot = _read_slot(pack, value, resolve, f"{where} slot {i + 1}", notes)
            if slot is None:
                return None, notes
            pack.slots.append(slot)
        dealt = False
        for slot in pack.slots:
            dealt |= slot.kind == SLOT_CARD or (slot.kind == SLOT_POOL and bool(slot.pool))
            if slot.kind in (SLOT_TIER, SLOT_MIX):
                dealt |= any(t.pool for t in pack.tiers)
        if not dealt:
            notes.append(("error", f"{where}: none of its cards are here; the pack is left out"))
            return None, notes
    for key, into in (("guarantee", pack.guarantee), ("pity", pack.pity)):
        if key not in entry:
            continue
        value = entry[key]
        if not isinstance(value, dict):
            notes.append(("error", f"{where}: \"{key}\" is {{tier: n}}; the pack is left out"))
            return None, notes
        for tname, n in value.items():
            t = pack.tier_named(tname)
            n = whole(n)
            if t < 0 or n is None or not 1 <= n <= 65535:
                notes.append(("error", f"{where}: \"{key}\": \"{tname}\" is not a tier of the pack with n of 1 or more; "
                                       "the pack is left out"))
                return None, notes
            into[t] = n
    if pack.unique:
        fixed = {}
        for s, slot in enumerate(pack.slots or []):
            if slot.kind != SLOT_CARD:
                continue
            if slot.card in fixed:
                notes.append(("error", f"{where}: \"unique_in_pack\" and card {slot.card} fixed in slots "
                                       f"{fixed[slot.card] + 1} and {s + 1}; the pack is left out"))
                return None, notes
            fixed[slot.card] = s
        distinct = len(distinct_cards(pack))
        if distinct < pack.count:
            notes.append(("error", f"{where}: \"unique_in_pack\" deals {pack.count} different cards and the pack has "
                                   f"{distinct} to deal from; the pack is left out"))
            return None, notes
    odds = sum(t.odds for t in pack.tiers)
    if odds > WEIGHT_TOTAL_MAX:
        notes.append(("error", f"{where}: the tiers' odds add up to {odds}, more than {WEIGHT_TOTAL_MAX}; the pack is "
                               "left out"))
        return None, notes
    if not odds and (not pack.slots or any(s.kind == SLOT_ODDS for s in pack.slots)):
        notes.append(("error", f"{where}: every tier's \"odds\" is 0, so a slot by the odds has no tier to deal from; "
                               "the pack is left out"))
        return None, notes

    if "image" in entry:
        image = json_string(entry["image"], "")
        if not image or image.startswith(("/", "\\")) or ".." in image or ":" in image:
            notes.append(("warning", f"{where}: \"image\" is a PNG inside the mod; its cover is shown instead"))
    if "cover" in entry:
        cid = resolve(entry["cover"])
        pack.cover = cid if cid and cid > 0 else 0
        if not pack.cover:
            notes.append(("warning", f"{where}: no card \"{_card_shown(entry['cover'])}\"; left out"))
    if not pack.cover:
        for tier in reversed(pack.tiers):
            if tier.pool:
                pack.cover = tier.pool[0][0]
                break
    if not pack.cover:
        for slot in pack.slots or []:
            if slot.kind == SLOT_CARD:
                pack.cover = slot.card
            elif slot.kind == SLOT_POOL and slot.pool:
                pack.cover = slot.pool[0][0]
            if pack.cover:
                break
    if "reveal" in entry:
        if entry["reveal"] in REVEALS:
            pack.reveal = REVEALS.index(entry["reveal"])
        else:
            notes.append(("warning", f"{where}: \"reveal\" is \"flip\", \"quick\" or \"list\"; \"flip\" is used"))
    if "sounds" in entry:
        sounds = entry["sounds"]
        if not isinstance(sounds, dict):
            notes.append(("warning", f"{where}: \"sounds\" is {{\"move\": id, ...}}; the screen's own are used"))
        else:
            notes += unknown_keys(where, sounds, SOUND_KEYS)
            for key in SOUND_KEYS:
                _, bad = number(sounds.get(key, MISSING), 0, 0xFFFF, 0)
                if bad:
                    notes.append(("warning", f"{where}: \"sounds\" \"{key}\" is a sound effect id; the screen's own is "
                                             "used"))
    if "when_nothing_left" in entry:
        if entry["when_nothing_left"] in NOTHING_LEFT:
            pack.when_nothing_left = entry["when_nothing_left"]
        else:
            notes.append(("warning", f"{where}: \"when_nothing_left\" is \"refuse\" or \"sell\"; the shop's is used"))
    pack.stock, bad = number(entry.get("stock", MISSING), 1, 999999, -1)
    if bad:
        notes.append(("warning", f"{where}: \"stock\" is 1 to 999999 purchases; no limit is kept"))
        pack.stock = -1
    notes += check_unlock(where, entry.get("unlock", MISSING))
    if "locked" in entry and entry["locked"] not in ("shown", "hidden"):
        notes.append(("warning", f"{where}: \"locked\" is \"hidden\" or \"shown\"; hidden"))
    if "image_style" in entry:
        if entry["image_style"] not in IMAGE_STYLES:
            notes.append(("warning", f"{where}: \"image_style\" is \"card\" or \"full\"; \"card\" is used"))
        elif entry["image_style"] == "full" and "image" not in entry:
            notes.append(("warning", f"{where}: \"image_style\" \"full\" shows the \"image\", and there is none; "
                                     "its cover is shown"))
    if "password" in entry:
        pack.password = password_bits(entry["password"])
        if pack.password is None:
            notes.append(("warning", f"{where}: \"password\" is up to 8 digits; the pack has none"))
    pack.once = json_bool(entry.get("once"), False)
    pack.listed = json_bool(entry.get("listed"), pack.password is None)
    if "shop" in entry:
        shop = entry["shop"]
        if isinstance(shop, (str, list)):
            # As packs.c keeps them: the names joined by commas, "*" alone for
            # every shop, an empty name skipped.
            joined = shop if isinstance(shop, str) else ",".join(json_string(s, "") for s in shop)
            pack.shops = [] if joined == "*" else [name for name in joined.split(",") if name]
        else:
            notes.append(("warning", f"{where}: \"shop\" is a shop's id, or a list of them; the pack is in every shop"))
    return pack, notes


def _read_slot(pack, value, resolve, where, notes):
    if isinstance(value, str):
        t = pack.tier_named(value)
        if t < 0:
            notes.append(("error", f"{where}: no tier \"{value}\"; the pack is left out"))
            return None
        return Slot(SLOT_TIER, tier=t)
    shape = (f"{where}: a slot is a tier's name, {{\"tiers\": {{...}}}}, {{\"cards\": ...}} or {{\"card\": ...}}; the "
             "pack is left out")
    if not isinstance(value, dict) or len(value) != 1:
        notes.append(("error", shape))
        return None
    notes += unknown_keys(where, value, SLOT_KEYS)
    if "card" in value:
        cid = _pool_card(value["card"], resolve, pack.include_added, where, notes)
        if cid <= 0:
            notes.append(("error", f"{where}: its card is not here; the pack is left out"))
            return None
        return Slot(SLOT_CARD, card=cid)
    if "cards" in value:
        pool = read_pool(value["cards"], resolve, pack.include_added, where, notes)
        return None if pool is None else Slot(SLOT_POOL, pool=pool)
    if isinstance(value.get("tiers"), dict):
        mix = [0] * len(pack.tiers)
        for tname, weight in value["tiers"].items():
            t = pack.tier_named(tname)
            if t < 0:
                notes.append(("error", f"{where}: no tier \"{tname}\"; the pack is left out"))
                return None
            weight = whole(weight)
            if weight is None or not 0 <= weight <= WEIGHT_TOTAL_MAX:
                notes.append(("error", f"{where}: a tier's weight is 0 to {WEIGHT_TOTAL_MAX}; the pack is left out"))
                return None
            mix[t] = weight
        if not 0 < sum(mix) <= WEIGHT_TOTAL_MAX:
            notes.append(("error", f"{where}: the tiers' weights add up to {sum(mix)}; 1 to {WEIGHT_TOTAL_MAX}; the pack "
                                   "is left out"))
            return None
        return Slot(SLOT_MIX, mix=mix)
    notes.append(("error", shape))
    return None


def check_unlock(where, value) -> list:
    """packs.c read_unlock's notes; MISSING when there is no "unlock"."""
    if value is MISSING:
        return []
    at = f"{where} unlock"
    if not isinstance(value, dict):
        return [("warning", f"{where}: \"unlock\" is an object of conditions; the pack stays locked")]
    notes = unknown_keys(at, value, UNLOCK_KEYS)
    bad, any_ = False, False
    any_ |= "beat" in value or "card" in value
    for key, low, high in (("wins", 0, 65535), ("copies", 0, 250), ("story", 0, 0xFFFF),
                           ("starchips_spent", 0, 999999999), ("packs_opened", 0, 999999999)):
        n, b = number(value.get(key, MISSING), low, high, None)
        bad |= b
        if n is not None and (n > 0 or key == "story"):
            any_ |= key != "copies"
    opened = value.get("opened", MISSING)
    if opened is not MISSING and not isinstance(opened, dict):
        bad = True
    for i, (name, times) in enumerate(opened.items() if isinstance(opened, dict) else []):
        if i >= OPENED_MAX:
            notes.append(("warning", f"{at}: \"opened\" names more than {OPENED_MAX} packs; the rest are left out"))
            break
        times = whole(times)
        if times is None or times < 1:
            bad = True
            continue
        any_ = True
    if bad:
        notes.append(("warning", f"{at}: a condition is not a whole number in range; the pack stays locked"))
    elif not any_:
        notes.append(("warning", f"{at}: names no condition, so it is open from the start"))
    return notes


def distinct_cards(pack) -> set:
    """The different cards a pack can deal, its fixed cards too (packs.c
    distinct_cards), for "unique_in_pack"."""
    out = set()
    for tier in pack.tiers:
        out |= {c for c, w in tier.pool if w}
    for slot in pack.slots or []:
        if slot.kind == SLOT_POOL:
            out |= {c for c, w in slot.pool if w}
        elif slot.kind == SLOT_CARD:
            out.add(slot.card)
    return out


def read_packs(value, resolve, mod="mod") -> tuple:
    """([Pack], notes) of a whole "packs" list, as Packs_Add and Packs_Finish
    read it: the list sorted by "order", then as declared; of two packs with
    one password, the first in that order is the one sold."""
    notes, out, ids, declared = [], [], set(), 0
    if not isinstance(value, list):
        return [], [("error", "\"packs\" is a list of packs, or the name of a file that holds them")]
    for i, entry in enumerate(value):
        if len(out) >= PACKS_MAX:
            notes.append(("error", f"packs[{i}]: there are {PACKS_MAX} packs already, the most there can be; left out"))
            break
        # Counted as the game counts: once past the id, whatever comes after.
        place = declared if entry_id(entry, ids) is not None else None
        declared += place is not None
        pack, more = read_pack(entry, resolve, mod, i, ids, place)
        notes += more
        if pack:
            out.append(pack)
            ids.add(pack.id)
    out.sort(key=lambda p: p.order)       # stable: ties keep the declaration order
    notes += password_notes(out)
    return out, notes


def password_notes(packs_in_order) -> list:
    """packs.c Packs_Finish: of two packs with one password, the first in
    the list's order is sold; the other says so."""
    notes, seen = [], {}
    for pack in packs_in_order:
        if pack.password is None:
            continue
        if pack.password in seen:
            notes.append(("warning", f"pack \"{pack.id}\": its password is pack \"{seen[pack.password]}\"'s too; that "
                                     "one is sold"))
        else:
            seen[pack.password] = pack.identity
    return notes


def shop_ids(rules) -> list:
    """The shops "pack_shop" gives, as packs.c read_rules keeps them (the
    first 16 ids), or the one it makes without: "main"."""
    ids = []
    shops = rules.get("shops") if isinstance(rules, dict) else None
    for shop in shops if isinstance(shops, list) else []:
        sid = json_string(shop.get("id"), "") if isinstance(shop, dict) else ""
        if KEY_RE.match(sid) and sid not in ids and len(ids) < SHOPS_MAX:
            ids.append(sid)
    return ids or ["main"]


def shop_notes(pack, rules) -> list:
    """packs.c Packs_Finish's note for a shop a pack names that no "pack_shop"
    has (of this mod: another mod may add it)."""
    ids = shop_ids(rules)
    return [("warning", f"pack \"{pack.id}\": no shop \"{name}\"") for name in pack.shops or [] if name not in ids]


def check_rules(value) -> list:
    """packs.c read_rules's notes for "pack_shop"."""
    if value is None:
        return []
    if not isinstance(value, dict):
        return [("warning", "\"pack_shop\" is an object of the shop's rules; left out")]
    notes = unknown_keys("pack_shop", value, RULES_KEYS, RULES_RESERVED)
    if "password" in value and value["password"] not in SHOP_PASSWORD:
        notes.append(("warning", "pack_shop: \"password\" is \"both\", \"packs_only\" or \"password_only\"; \"both\" is "
                                 "used"))
    if "rng" in value and value["rng"] not in ("game", "save"):
        notes.append(("warning", "pack_shop: \"rng\" is \"game\" or \"save\"; \"game\" is used"))
    if number(value.get("music", MISSING), 0, 0xFFFF, 0)[1]:
        notes.append(("warning", "pack_shop: \"music\" is a song id; the screen's own is used"))
    if "when_nothing_left" in value and value["when_nothing_left"] not in NOTHING_LEFT:
        notes.append(("warning", "pack_shop: \"when_nothing_left\" is \"refuse\" or \"sell\"; \"refuse\" is used"))
    for key in RULES_LATER:
        if json_bool(value.get(key), False):
            notes.append(("warning", f"pack_shop: \"{key}\" is not built yet (notes/card-packs.md); ignored"))
    shops = value.get("shops", MISSING)
    if shops is not MISSING and not isinstance(shops, list):
        notes.append(("warning", "pack_shop: \"shops\" is a list of shops; left out"))
    ids = []
    for shop in shops if isinstance(shops, list) else []:
        sid = json_string(shop.get("id"), "") if isinstance(shop, dict) else ""
        if not KEY_RE.match(sid):
            notes.append(("warning", "pack_shop: a shop is {\"id\": ..., \"name\": ...}, its id 1-63 letters, digits, "
                                     "'_' or '-'; left out"))
            continue
        where = f"pack_shop shop \"{sid}\""
        notes += unknown_keys(where, shop, SHOP_KEYS)
        if "where" in shop and shop["where"] != "password":
            notes.append(("warning", f"{where}: only \"where\": \"password\" is built yet; it is on the Password "
                                     "screen"))
        if sid not in ids:
            if len(ids) >= SHOPS_MAX:
                notes.append(("warning", f"{where}: there are {SHOPS_MAX} shops already, the most there can be; left "
                                         "out"))
                continue
            ids.append(sid)
        notes += check_unlock(where, shop.get("unlock", MISSING))
    return notes


# --- dealing --------------------------------------------------------------------

class Lcg:
    """The Psy-Q generator the game's rand() is (src/pc/rng.c), and the
    "save" rng's (packs.c Packs_LcgNext)."""

    def __init__(self, seed: int):
        self.seed = seed & 0xFFFFFFFF

    def __call__(self) -> int:
        self.seed = (self.seed * 1103515245 + 12345) & 0xFFFFFFFF
        return (self.seed >> 16) & 0x7FFF


def save_seed(duelist_code: int, identity: str, opened: int) -> int:
    """packs.c Packs_SaveSeed: FNV-1a of "%08X:identity:opened"."""
    h = 2166136261
    for byte in f"{duelist_code & 0xFFFFFFFF:08X}:{identity}:{opened}".encode("utf-8"):
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h


@dataclass
class Result:
    cards: list
    tiers: list
    redone: list


class _Dealing:
    def __init__(self, pack, held):
        self.pack = pack
        self.held = held or (lambda card: 0)
        self.taken = {}

    def take(self, card, step):
        if card > 0:
            self.taken[card] = self.taken.get(card, 0) + step

    def weight_now(self, card, weight):
        if not weight:
            return 0
        if self.pack.unique and self.taken.get(card, 0):
            return 0
        if self.pack.max_copies and self.held(card) + self.taken.get(card, 0) >= self.pack.max_copies:
            return 0
        return weight

    def pick(self, pool, roll):
        if not self.pack.unique and not self.pack.max_copies:
            # Every weight stands as written: the same walk down the pool,
            # by its running totals (Simulate opens many).
            cache = self.pack.__dict__.setdefault("_running", {})
            running = cache.get(id(pool))
            if running is None or running[0] is not pool:
                sums, total = [], 0
                for _, weight in pool:
                    total += weight
                    sums.append(total)
                running = cache[id(pool)] = (pool, sums)
            sums = running[1]
            if not sums or not sums[-1]:
                return 0
            return pool[bisect.bisect_right(sums, roll % sums[-1])][0]
        weights = [self.weight_now(c, w) for c, w in pool]
        total = sum(weights)
        if not total:
            return 0
        roll %= total
        for (card, _), weight in zip(pool, weights):
            if not weight:
                continue
            if roll < weight:
                return card
            roll -= weight
        return 0

    def pick_down(self, tier, roll):
        while tier >= 0:
            card = self.pick(self.pack.tiers[tier].pool, roll)
            if card:
                return card, tier
            tier -= 1
        return 0, -1


def _pick_tier(weights, roll) -> int:
    total = sum(weights)
    if not total:
        return -1
    roll %= total
    for t, weight in enumerate(weights):
        if not weight:
            continue
        if roll < weight:
            return t
        roll -= weight
    return -1


def deal(pack: Pack, random, pity=None, held=None) -> Result:
    """packs.c Packs_Deal: always DRAWS_PER_SLOT numbers a slot. `random()`
    gives 0-0x7FFF; `pity` the save's counts by tier index; `held(card)` the
    copies held, for "max_copies"."""
    tier_roll, card_roll = [], []
    for _ in range(pack.count):
        a, b, c, d = random() & 0x7FFF, random() & 0x7FFF, random() & 0x7FFF, random() & 0x7FFF
        tier_roll.append(a << 15 | b)
        card_roll.append(c << 15 | d)
    dealing = _Dealing(pack, held)
    odds = [t.odds for t in pack.tiers]
    cards, tiers, redone = [0] * pack.count, [-1] * pack.count, [False] * pack.count
    # A fixed card is dealt whatever comes before it: counted from the start,
    # so "unique_in_pack" and "max_copies" leave it to its slot.
    for s in range(pack.count):
        if pack.slot_kind(s) == SLOT_CARD:
            dealing.take(pack.slots[s].card, 1)
    for s in range(pack.count):
        slot = pack.slots[s] if pack.slots else None
        kind = pack.slot_kind(s)
        card, used = 0, -1
        if kind == SLOT_CARD:
            card = slot.card
        elif kind == SLOT_POOL:
            card = dealing.pick(slot.pool, card_roll[s])
        elif kind == SLOT_TIER:
            card, used = dealing.pick_down(slot.tier, card_roll[s])
        else:
            t = _pick_tier(slot.mix if kind == SLOT_MIX else odds, tier_roll[s])
            if t >= 0:
                card, used = dealing.pick_down(t, card_roll[s])
        cards[s], tiers[s] = card, used
        if kind != SLOT_CARD:
            dealing.take(card, 1)
    count = len(pack.tiers)
    need = []
    for t in range(count):
        n = pack.guarantee[t]
        if pack.pity[t] and pity is not None and pity[t] + 1 >= pack.pity[t] and n < 1:
            n = 1
        need.append(n)
    for g in range(count - 1, -1, -1):
        if not need[g]:
            continue
        have = sum(1 for t in tiers if t >= g)
        for s in range(pack.count - 1, -1, -1):
            if have >= need[g]:
                break
            kind = pack.slot_kind(s)
            if kind in (SLOT_CARD, SLOT_POOL) or tiers[s] >= g or redone[s]:
                continue
            old = cards[s]
            dealing.take(old, -1)
            card, used = 0, -1
            for t in range(g, count):
                card = dealing.pick(pack.tiers[t].pool, card_roll[s])
                if card:
                    used = t
                    break
            if not card:
                dealing.take(old, 1)
                break
            cards[s], tiers[s], redone[s] = card, used, True
            dealing.take(card, 1)
            have += 1
    return Result(cards, tiers, redone)


def record(pack: Pack, result: Result, pity: list):
    """packs.c Packs_Record's pity counts: a tier (or rarer) in the pack sets
    its count back to 0; without, one more."""
    for t in range(len(pack.tiers)):
        if not pack.pity[t]:
            continue
        if any(x >= t for x in result.tiers):
            pity[t] = 0
        elif pity[t] < 0xFFFF:
            pity[t] += 1


def nothing_left(pack: Pack, held=None) -> bool:
    """packs.c Packs_NothingLeft: the pack has "max_copies", no slot of a
    fixed card (always dealt), and the player holds that many of every card
    of every pool (`held(card)`). A pack with some cards left is not: it may
    still deal empty slots."""
    held = held or (lambda card: 0)
    if not pack.max_copies or any(slot.kind == SLOT_CARD for slot in pack.slots or []):
        return False
    pools = [tier.pool for tier in pack.tiers] + [slot.pool for slot in pack.slots or [] if slot.kind == SLOT_POOL]
    return all(not weight or held(card) >= pack.max_copies for pool in pools for card, weight in pool)


def refuses_when_nothing_left(pack: Pack, rules=None) -> bool:
    """packs.c Packs_RefusesWhenNothingLeft: the pack's "when_nothing_left",
    else the shop's, else "refuse"."""
    rule = pack.when_nothing_left
    if rule is None and isinstance(rules, dict) and rules.get("when_nothing_left") in NOTHING_LEFT:
        rule = rules["when_nothing_left"]
    return (rule or "refuse") == "refuse"


def tier_chance(pack: Pack, tier: int) -> float:
    """The share of a slot dealt by the tiers' odds that is of `tier`."""
    total = sum(t.odds for t in pack.tiers)
    return pack.tiers[tier].odds / total if total and 0 <= tier < len(pack.tiers) else 0.0


def card_chances(pack: Pack) -> dict:
    """{(tier, card): chance} for a slot dealt by the tiers' odds, before any
    card is taken out of the pools."""
    out = {}
    for t, tier in enumerate(pack.tiers):
        total = sum(w for _, w in tier.pool)
        for card, weight in tier.pool:
            if total:
                out[(t, card)] = out.get((t, card), 0.0) + tier_chance(pack, t) * weight / total
    return out


@dataclass
class Simulation:
    packs: int
    cards: dict            # card -> copies dealt
    tiers: dict            # tier name -> cards dealt ("(own)" for a slot's pool or card, "(none)" for nothing)
    pity_fired: dict       # tier name -> how often the pity dealt one
    pity_waits: dict       # tier name -> average openings between two of that tier (or rarer)
    draws: int


class Simulator:
    """Packs opened one after another from the game's generator at `seed`,
    the pity counts carried from one to the next as a save's are: `step(n)`
    opens n more, so a window can open many without stopping (Simulate)."""

    def __init__(self, pack: Pack, seed: int = 1, held=None):
        self.pack, self.held = pack, held
        self.random = Lcg(seed)
        self.draws = self.opened = 0
        self.pity = [0] * TIERS_MAX
        self.cards, self.tiers, self.fired, self.waits, self.since = {}, {}, {}, {}, {}

    def _draw(self):
        self.draws += 1
        return self.random()

    def step(self, packs: int):
        pack = self.pack
        for _ in range(max(0, packs)):
            before = list(self.pity)
            result = deal(pack, self._draw, self.pity, self.held)
            for card, tier in zip(result.cards, result.tiers):
                name = pack.tiers[tier].name if tier >= 0 else ("(own)" if card else "(none)")
                self.tiers[name] = self.tiers.get(name, 0) + 1
                if card:
                    self.cards[card] = self.cards.get(card, 0) + 1
            for t, tier in enumerate(pack.tiers):
                if not pack.pity[t]:
                    continue
                had = any(x >= t for x in result.tiers)
                if before[t] + 1 >= pack.pity[t] and any(r and x >= t for r, x in zip(result.redone, result.tiers)):
                    self.fired[tier.name] = self.fired.get(tier.name, 0) + 1
                self.since[tier.name] = self.since.get(tier.name, 0) + 1
                if had:
                    self.waits.setdefault(tier.name, []).append(self.since[tier.name])
                    self.since[tier.name] = 0
            record(pack, result, self.pity)
            self.opened += 1

    def result(self) -> Simulation:
        average = {k: sum(v) / len(v) for k, v in self.waits.items() if v}
        return Simulation(self.opened, dict(self.cards), dict(self.tiers), dict(self.fired), average, self.draws)


def simulate(pack: Pack, packs: int = 1000, seed: int = 1, held=None) -> Simulation:
    """Open `packs` packs one after another from the game's generator at
    `seed`, the pity counts carried from one to the next as a save's are."""
    simulator = Simulator(pack, seed, held)
    simulator.step(packs)
    return simulator.result()


def golden_line(pack: Pack, seed: int, pity=None, held=None) -> str:
    """One line of tests/pc/packs_golden.txt: the pack dealt from `seed`,
    and whether it has nothing left for the player (Packs_NothingLeft)."""
    random = Lcg(seed)
    result = deal(pack, random, pity, held)
    slots = " ".join(f"{c}/{t}{'*' if r else ''}" for c, t, r in zip(result.cards, result.tiers, result.redone))
    left = " | nothing left" if nothing_left(pack, held) else ""
    return f"{pack.id} {seed} {slots} | seed {random.seed:08X}{left}"


# --- writing what differs --------------------------------------------------------

def default_count(entry: dict) -> int:
    slots = entry.get("slots")
    return len(slots) if isinstance(slots, list) else DEFAULT_COUNT


def minimize(entry):
    """The pack as the editor writes it: the keys that say only what the game
    would do anyway left out ("the mod is the diff"), a pool of weights of 1
    written as a list. Keys the editor does not know stay as written."""
    if not isinstance(entry, dict):
        return copy.deepcopy(entry)
    out = copy.deepcopy(entry)
    # The game lists a pack by default unless it has a password it can read.
    has_password = password_bits(out["password"]) is not None if "password" in out else False
    defaults = {"price": DEFAULT_PRICE, "duplicates": "allow", "include_added_cards": True, "locked": "hidden",
                "reveal": "flip", "image_style": "card", "once": False, "listed": not has_password,
                "count": default_count(out)}
    for key, value in defaults.items():
        if key in out and out[key] == value and type(out[key]) is type(value):
            del out[key]
    if out.get("id") is not None and "name" in out and out["id"] == slug(out["name"]):
        del out["id"]
    for key in ("description", "image", "password"):
        if out.get(key) == "":
            del out[key]
    for key in ("guarantee", "pity", "unlock", "cost"):
        if out.get(key) == {}:
            del out[key]
    if isinstance(out.get("cost"), dict) and list(out["cost"]) == ["starchips"] and is_int(out["cost"]["starchips"]):
        # {"starchips": n} alone is a price: written as one.
        price = out.pop("cost")["starchips"]
        out.pop("price", None)
        if price != DEFAULT_PRICE:
            out["price"] = price
    sounds = out.get("sounds")
    if isinstance(sounds, dict):
        for key in list(sounds):
            if DEFAULT_SOUNDS.get(key) == sounds[key]:
                del sounds[key]
        if not sounds:
            del out["sounds"]
    if "cards" in out and isinstance(out["cards"], dict):
        out["cards"] = pool_value(pool_items(out["cards"]))
    if isinstance(out.get("tiers"), dict):
        for tier in out["tiers"].values():
            if not isinstance(tier, dict):
                continue
            if tier.get("odds") == 1 and is_int(tier.get("odds")):
                del tier["odds"]
            for key in ("label",):
                if tier.get(key) == "":
                    del tier[key]
            if isinstance(tier.get("cards"), dict):
                tier["cards"] = pool_value(pool_items(tier["cards"]))
    for slot in out.get("slots") or []:
        if isinstance(slot, dict) and isinstance(slot.get("cards"), dict):
            slot["cards"] = pool_value(pool_items(slot["cards"]))
    return out


def minimize_rules(rules):
    """"pack_shop" without its defaults; None when nothing is left."""
    if not isinstance(rules, dict):
        return copy.deepcopy(rules)
    out = copy.deepcopy(rules)
    for key, value in (("password", "both"), ("rng", "game"), ("music", DEFAULT_MUSIC), ("when_nothing_left", "refuse")):
        if out.get(key) == value:
            del out[key]
    for key in RULES_LATER:
        if out.get(key) is False:
            del out[key]
    if out.get("shops") == []:
        del out["shops"]
    return out or None


# --- editing helpers the tab uses ------------------------------------------------

def tiers_of(entry: dict) -> list:
    """[(name, tier dict)] of a pack: its "tiers", or its one pool as tier
    "cards" (a dict that is not in the entry)."""
    if isinstance(entry.get("tiers"), dict):
        tiers = [(k, v) for k, v in entry["tiers"].items() if isinstance(v, dict)]
        if tiers:       # none (a mod's own "tiers": {}): its one pool, so a tier is always there to pick
            return tiers
    return [("cards", {"odds": 1, "cards": entry.get("cards", [])})]


def ensure_tiers(entry: dict):
    """Make a one-pool pack a pack of tiers (its pool the tier "cards"), so
    another tier can be added; the key order is kept."""
    if isinstance(entry.get("tiers"), dict):
        return
    rebuilt = {}
    for key, value in entry.items():
        if key == "cards":
            rebuilt["tiers"] = {"cards": {"cards": value}}
        else:
            rebuilt[key] = value
    if "tiers" not in rebuilt:
        rebuilt["tiers"] = {"cards": {"cards": []}}
    entry.clear()
    entry.update(rebuilt)


def tier_pool(entry: dict, tier: str) -> list:
    """[(card as written, weight)] of one tier."""
    for name, value in tiers_of(entry):
        if name == tier:
            return pool_items(value.get("cards", []))
    return []


def set_tier_pool(entry: dict, tier: str, items: list):
    if not isinstance(entry.get("tiers"), dict) and tier == "cards":
        entry["cards"] = pool_value(items)
        return
    ensure_tiers(entry)
    entry["tiers"].setdefault(tier, {})["cards"] = pool_value(items)


def new_pack(name: str, taken: set) -> dict:
    base = slug(name)
    pid, n = base, 2
    while pid in taken:
        pid, n = f"{base}-{n}", n + 1
    entry = {"name": name}
    if pid != base:
        entry["id"] = pid
    entry["price"] = DEFAULT_PRICE
    entry["cards"] = []
    return entry


def pack_id(entry) -> str:
    if not isinstance(entry, dict):
        return "?"
    if isinstance(entry.get("id"), str):
        return entry["id"]
    return slug(entry.get("name") if isinstance(entry.get("name"), str) else "pack")


# --- the name plate --------------------------------------------------------------

def serif_path():
    """The face the game sets a pack's (and a card's) name plate in
    (art.c serif_file): Times, or what the system has for it."""
    import os
    import shutil
    import subprocess
    windows = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windows:
        for name in ("times.ttf", "georgia.ttf", "timesbd.ttf", "georgiab.ttf"):
            path = os.path.join(windows, "Fonts", name)
            if os.path.exists(path):
                return path
    match = shutil.which("fc-match")
    if match:
        try:
            path = subprocess.run([match, "-f", "%{file}", "Times:regular"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
            if path and os.path.exists(path):
                return path
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def name_plate_inks(name: str, font=None):
    """The 96x14 plate inks the game makes of a name (art.c set_name and
    CardArt_TitleFromName, closely): Times at 13 pixels, the baseline under
    row 11, from column 3, a name wider than 90 pixels squeezed. None when
    no serif face is found."""
    from . import art, ttf
    if font is None:
        path = serif_path()
        if not path:
            return None
        try:
            font = ttf.Font(path)
        except ttf.FontError:
            return None
    size, wide, height, baseline, left, room = 13, 512, 14, 11, 3, 90
    line = bytearray(wide * height)
    pen, low, high = left, wide, -1
    for c in name:
        outline = font.outline(ord(c))
        if outline is None:
            continue
        glyph = [[(x * size + pen, baseline - y * size) for x, y in contour] for contour in outline]
        cover = ttf.fill(glyph, wide, height)
        for i, v in enumerate(cover):
            if v > line[i]:
                line[i] = v
                x = i % wide
                low, high = min(low, x), max(high, x)
        pen += round(font.advance(ord(c)) * size)
        if pen >= wide:
            break
    out = [0] * (96 * height)
    if high >= low:
        if high - low + 1 <= room:
            for y in range(height):
                for x in range(96):
                    out[y * 96 + x] = line[y * wide + x]
        else:
            step = (high - low + 1) / room
            rows = []
            peak = 1.0
            for y in range(height):
                row = []
                for x in range(room):
                    at = max(0.0, low + (x + 0.5) * step - 0.5)
                    i0 = int(at)
                    t = at - i0
                    i1 = min(i0 + 1, wide - 1)
                    v = line[y * wide + i0] * (1 - t) + line[y * wide + i1] * t
                    peak = max(peak, v)
                    row.append(v)
                rows.append(row)
            for y in range(height):
                for x in range(room):
                    out[y * 96 + left + x] = int(rows[y][x] * 255 / peak + 0.5)
    return [art.ink_of(v) for v in out]
