"""The game's numbers a mod may change (notes/gameplay-tables.md, "Values"):
the caps (ATK, DEF, LP, starchips...) and the other values the port reads in
place of the disc's (a Build Deck's copies, Swords of Revealing Light's
turns, the rank score, the starchips a win gives...). They are a mod's
"limits", as the port has always read them: src/pc/cards/tables.c
(read_limits, read_values). The checks here are that file's, so a problem
shows in the editor rather than as a line in the Mods window.

The mod.json shape:

    "limits": {
        "stats": 30000, "attack": 30000, "defense": 30000,
        "life_points": 16000,                   or
        "life_points": {"start": 16000, "player": 8000, "opponent": 16000, "max": 30000,
                        "duelists": {"Heishin": 20000, "Seto": {"player": 8000, "opponent": 12000}}},
        "two_player": {"start": 8000, "max": 30000, "step": 500},
        "starchips": 999999, "chest": 250, "free_duel_record": 999, "two_player_record": 9999,
        "deck_copies": 3, "swords_turns": 3, "crush_card": 1500, "spellbinding_circle": 500, "shadow_spell": 1000,
        "rank_score": {"start": 50, "exodia": 40, "deck_out": -40},
        "starchip_prize": {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1},
        "new_game_starchips": 0,
        "card_drops": 5
    }

The editor keeps it in Project.other["limits"] as written; the Values tab
turns it into a form (`flatten`) and back (`build`).
"""
from __future__ import annotations

from .model import duelist_named

STAT_MAX = 32767            # s16 ATK/DEF in the duel's card records
LIFE_POINTS_MAX = 32767     # s16 LP in each side's record
CHEST_MAX = 255             # a byte a card in the chest
RECORD_MAX = 32767          # s16 Free Duel wins and losses
TWO_PLAYER_RECORD_MAX = 65535
STARCHIPS_MAX = 99999999    # eight digits on screen
DECK_SIZE = 40
SWORDS_MAX = 9              # one digit on the field's card bar
PRIZE_MAX = 1000            # a win's starchips; past PRIZE_ROW the results show one picture and "xN"
PRIZE_ROW = 8               # the starchip pictures the results' row draws
EFFECT_MAX = 9999           # four digits in the effect's number
CARD_DROPS_MAX = 99         # Game > Card drops' range (src/pc/cards/drops.h)

STAT = "a 16-bit number in every card record"
PRIZE_STORAGE = "the starchips a win gives"
LIFE = "a 16-bit number in each side's record"

# The groups, in the tab's order: their title and their fields. A field is
# key ("a.b" for a member of a section), label, the game's own value (what
# an empty field means; None: the side's start), lowest, highest, a one-line
# hint, and what keeping more than the highest would take (None: more means
# nothing, and is left out as the game leaves it).
GROUPS = (
    ("Duel", (
        ("life_points.start", "Starting LP", 8000, 1, LIFE_POINTS_MAX, "Both sides vs the CPU", LIFE),
        ("life_points.player", "Your starting LP", 8000, 1, LIFE_POINTS_MAX, "Yours alone", LIFE),
        ("life_points.opponent", "CPU's starting LP", 8000, 1, LIFE_POINTS_MAX, "The CPU's alone", LIFE),
        ("life_points.max", "LP cap", None, 1, LIFE_POINTS_MAX, "Healing stops here", LIFE),
        ("stats", "ATK/DEF cap", 9999, 0, STAT_MAX, "With every bonus", STAT),
        ("attack", "ATK cap", 9999, 0, STAT_MAX, "ATK alone", STAT),
        ("defense", "DEF cap", 9999, 0, STAT_MAX, "DEF alone", STAT),
    )),
    ("Magic", (
        ("swords_turns", "Swords of Revealing Light", 3, 1, SWORDS_MAX, "Turns with no attack",
         "one digit on the field's card bar"),
        ("crush_card", "Crush Card", 1500, 0, STAT_MAX, "Destroys ATK from", STAT),
        ("spellbinding_circle", "Spellbinding Circle", 500, 0, EFFECT_MAX, "ATK/DEF taken off",
         "four digits in the effect's number"),
        ("shadow_spell", "Shadow Spell", 1000, 0, EFFECT_MAX, "ATK/DEF taken off", "four digits in the effect's number"),
    )),
    ("Deck and Trunk", (
        ("deck_copies", "Copies in a deck", 3, 1, DECK_SIZE, "Build Deck allows", "a deck of forty"),
        ("chest", "Copies in the Trunk", 250, 1, CHEST_MAX, "Kept of each card",
         "a byte a card in the memory card's save"),
    )),
    ("Rewards", (
        ("starchip_prize.S", "Starchips for S", 5, 0, PRIZE_MAX, "Per win", PRIZE_STORAGE),
        ("starchip_prize.A", "Starchips for A", 4, 0, PRIZE_MAX, "Per win", PRIZE_STORAGE),
        ("starchip_prize.B", "Starchips for B", 3, 0, PRIZE_MAX, "Per win", PRIZE_STORAGE),
        ("starchip_prize.C", "Starchips for C", 2, 0, PRIZE_MAX, "Per win", PRIZE_STORAGE),
        ("starchip_prize.D", "Starchips for D", 1, 0, PRIZE_MAX, "Per win", PRIZE_STORAGE),
        ("new_game_starchips", "New game starchips", 0, 0, STARCHIPS_MAX, "A new save has",
         "eight digits on screen"),
        ("starchips", "Most starchips", 999999, 0, STARCHIPS_MAX, "The save holds", "eight digits on screen"),
        ("card_drops", "Cards a win deals", 0, 1, CARD_DROPS_MAX, "Locks Game > Card drops", None),
    )),
    ("Rank", (
        ("rank_score.start", "Score at the start", 50, 0, 99, "Below 50 is TEC", None),
        ("rank_score.exodia", "Exodia win", 40, -99, 99, "Added to the score", None),
        ("rank_score.deck_out", "Win by empty deck", -40, -99, 99, "Added to the score", None),
    )),
    ("Records and 2P", (
        ("two_player.start", "2P starting LP", 8000, 1, LIFE_POINTS_MAX, "The choice starts at", LIFE),
        ("two_player.max", "2P most LP", 8000, 1, LIFE_POINTS_MAX, "Highest to pick", LIFE),
        ("two_player.step", "2P LP step", 500, 1, LIFE_POINTS_MAX, "Each press", LIFE),
        ("free_duel_record", "Free Duel record", 999, 1, RECORD_MAX, "Most wins, losses", "a 16-bit number in the save"),
        ("two_player_record", "2P record", 9999, 1, TWO_PLAYER_RECORD_MAX, "Most wins, losses",
         "a 16-bit number in the save"),
    )),
)
# A line under a group, for what its hints have no room to say.
GROUP_NOTES = {
    "Rewards": f"Past {PRIZE_ROW} starchips a win, the results show one starchip with \"xN\" beside it.",
}
# What a field's empty value means, where it is not a number of the game's.
RETAIL_TEXT = {"card_drops": "player"}
# A field's tooltip, where its hint line has no room for what it does.
TIPS = {
    "card_drops": "Every won duel deals exactly this many cards, 1 to 99, whatever the player set in "
                  "Game > Card drops. While the mod is applied the setting shows the mod's number, greyed, "
                  "with the mod's name; the player's own value comes back when the mod is removed. "
                  "Empty: the player chooses (1 is the console's). Needs the game of mod API 13.",
}
ALL_FIELDS = tuple(field for _, fields in GROUPS for field in fields)
FIELD = {field[0]: field for field in ALL_FIELDS}
TOP_KEYS = ("stats", "attack", "defense", "life_points", "two_player", "starchips", "chest", "free_duel_record",
            "two_player_record", "deck_copies", "swords_turns", "crush_card", "spellbinding_circle", "shadow_spell",
            "rank_score", "starchip_prize", "new_game_starchips", "card_drops")
LIFE_KEYS = ("start", "player", "opponent", "max", "duelists")
# The sections whose members are all fields: their keys, and the example a
# wrong kind of value is told.
SECTIONS = {
    "two_player": (("start", "max", "step"), "{\"start\": 8000, \"max\": 8000, \"step\": 500}"),
    "rank_score": (("start", "exodia", "deck_out"), "{\"start\": 50, \"exodia\": 40, \"deck_out\": -40}"),
    "starchip_prize": (("S", "A", "B", "C", "D"), "{\"S\": 5, \"A\": 4, \"B\": 3, \"C\": 2, \"D\": 1}"),
}


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _get(limits: dict, path: str):
    """The value at "a.b" in limits; a number "life_points" is its "start"."""
    top, _, sub = path.partition(".")
    value = limits.get(top) if isinstance(limits, dict) else None
    if not sub:
        return value
    if top == "life_points" and _int(value):
        return value if sub == "start" else None
    return value.get(sub) if isinstance(value, dict) else None


def retail_text(key) -> str:
    """The game's own value as the form shows it."""
    if key in RETAIL_TEXT:
        return RETAIL_TEXT[key]
    retail = FIELD[key][2]
    return "start" if retail is None else str(retail)


def flatten(limits) -> dict:
    """The form's values: "path": number for each field the mod sets, and
    "duelists": {name: (player or None, opponent or None)}."""
    limits = limits if isinstance(limits, dict) else {}
    flat = {}
    for key, *_ in ALL_FIELDS:
        value = _get(limits, key)
        if _int(value):
            flat[key] = value
    life = limits.get("life_points")
    duelists = life.get("duelists") if isinstance(life, dict) else None
    flat["duelists"] = {}
    if isinstance(duelists, dict):
        for name, entry in duelists.items():
            if _int(entry):
                flat["duelists"][name] = (None, entry)
            elif isinstance(entry, dict):
                flat["duelists"][name] = (entry.get("player"), entry.get("opponent"))
    return flat


def build(flat: dict, kept=None):
    """"limits" from the form's values; None when nothing is set. What the
    form does not show (a key the editor does not know) is kept from `kept`,
    the mod's own "limits" as it was read."""
    kept = kept if isinstance(kept, dict) else {}
    out = {key: value for key, value in kept.items() if key not in TOP_KEYS}
    # What the form cannot show stays too, for Conflicts to report: a
    # misspelt key inside a section, and a field's value that is not a whole
    # number (the form shows it empty).
    known = dict({"life_points": LIFE_KEYS}, **{name: keys for name, (keys, _) in SECTIONS.items()})
    for top, keys in known.items():
        section = kept.get(top)
        if isinstance(section, dict):
            for sub, value in section.items():
                if sub not in keys:
                    out.setdefault(top, {})[sub] = value
    for key, *_ in ALL_FIELDS:
        value = flat.get(key)
        if value is None:
            written = _get(kept, key)
            if written is None or _int(written):
                continue
            value = written
        top, _, sub = key.partition(".")
        if sub:
            out.setdefault(top, {})[sub] = value
        else:
            out[top] = value
    duelists = {}
    for name, (player, opponent) in (flat.get("duelists") or {}).items():
        if player is None and opponent is None:
            continue
        duelists[name] = opponent if player is None else {k: v for k, v in (("player", player),
                                                                            ("opponent", opponent)) if v is not None}
    if duelists:
        out.setdefault("life_points", {})["duelists"] = duelists
    life = out.get("life_points")
    if isinstance(life, dict) and set(life) == {"start"}:
        out["life_points"] = life["start"]      # the short form, as a person would write it
    return out or None


def check(limits, named=None) -> list:
    """(level, where, message) for what read_limits would note: "error" where
    it leaves a value out, "warning" where it holds one at the most the game
    keeps. `named` finds a duelist the mod adds by a name (roster.named)."""
    out = []
    if limits is None:
        return out
    if not isinstance(limits, dict):
        return [("error", "limits", "\"limits\" is an object: {\"stats\": 30000, \"life_points\": 16000, ...}")]
    for key in limits:
        if key not in TOP_KEYS:
            out.append(("error", key, f"no value \"{key}\" ({', '.join(TOP_KEYS)})"))
    life = limits.get("life_points")
    if life is not None and (isinstance(life, bool) or not isinstance(life, (int, dict))):
        out.append(("error", "life_points", "a number (both sides' start) or an object of start, player, opponent, "
                                           "max and duelists"))
    for name, (keys, example) in SECTIONS.items():
        section = limits.get(name)
        if section is None:
            continue
        if not isinstance(section, dict):
            out.append(("error", name, f"an object: {example}"))
            continue
        for key in section:
            if key not in keys:
                out.append(("error", f"{name}.{key}", f"no \"{key}\" ({', '.join(keys)})"))
    for key, label, retail, low, high, hint, storage in ALL_FIELDS:
        top = key.partition(".")[0]
        if top in SECTIONS and not isinstance(limits.get(top), dict):
            continue
        value = _get(limits, key)
        if value is None:
            continue
        out += _number(key, value, low, high, storage)
    if isinstance(life, dict):
        for key in life:
            if key not in LIFE_KEYS:
                out.append(("error", f"life_points.{key}", f"no \"{key}\" ({', '.join(LIFE_KEYS)})"))
        duelists = life.get("duelists")
        if duelists is not None and not isinstance(duelists, dict):
            out.append(("error", "life_points.duelists", "an object of duelists and their LP"))
        for name, entry in (duelists.items() if isinstance(duelists, dict) else ()):
            where = f"life_points.duelists \"{name}\""
            if name.lower() != "all" and duelist_named(name) < 0 and (named is None or named(name) is None):
                out.append(("warning", where, "not one of the disc's forty duelists: the game looks for it among "
                                              "the mods' added duelists"))
            if isinstance(entry, dict):
                for side in ("player", "opponent"):
                    if side in entry:
                        out += _number(f"{where} {side}", entry[side], 1, LIFE_POINTS_MAX, LIFE)
            else:
                out += _number(where, entry, 1, LIFE_POINTS_MAX, LIFE)
    two = limits.get("two_player")
    if isinstance(two, dict):
        start, top, step = two.get("start", 8000), two.get("max", 8000), two.get("step", 500)
        if _int(start) and _int(top) and start > top:
            out.append(("warning", "two_player.start", f"past the most to pick ({top}): the choice starts at {top}"))
        if _int(step) and _int(top) and step > top:
            out.append(("warning", "two_player.step", f"past the most to pick ({top}): a step is {top}"))
    return out


def problem(key, text) -> str | None:
    """What is wrong with `text` typed in field `key`, or None: the form's
    own check, before the value is applied."""
    text = text.strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return f"{FIELD[key][1]}: a whole number"
    found = _number(key, value, *FIELD[key][3:5], FIELD[key][6])
    return found[0][2] if found else None


def _number(where, value, low, high, storage) -> list:
    if not _int(value):
        return [("error", where, f"a whole number, {low} to {high}, without quotes; left out")]
    if value < low:
        return [("error", where, f"at least {low}; left out")]
    if value > high:
        if storage is None:
            return [("error", where, f"at most {high}; left out")]
        return [("warning", where, f"{value} is past the {high} the game keeps ({storage}); {high} is used")]
    return []
