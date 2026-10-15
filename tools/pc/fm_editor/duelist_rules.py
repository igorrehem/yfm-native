"""What a duelist entry says beside its name, face and pools
(notes/more-duelists.md; src/pc/free_duel/duelists.c read_one_duelist):

    "unlock": {"beat": ..., "wins": n, "story": n, "card": ..., "copies": n, "tower": true or n}
    "ai":     {"copy": ..., "search": n, "values": [...], "sight": true}  or [n, ...]
    "ranks":  {"turns": [[threshold, change], ...], ...}

when the Free Duel grid shows it, how it plays, and how a duel against it is
scored. They stay in the entry's `extra` (roster.RosterDuelist) as written:
these read them as the game does, and write back the shortest form that says
the same -- or the entry's own, while it still does -- keeping a key the game
does not read where it was.

An added duelist ("copy") and a replacement ("replace") read them alike; a
replacement's "unlock" stands in place of the campaign flag that would show
the disc duelist.
"""
from __future__ import annotations

import copy as _copy

from .gamedata import (AI_FIELDS, AI_ROWS, AI_SEARCH, DUELIST_COUNT, DUELIST_NAMES, RANK_ABOVE, RANK_RETAIL,
                       RANK_RULES, RANK_STEPS, SIGHT_DUELISTS)
from .model import letters

UNLOCK_KEYS = ("beat", "wins", "story", "card", "copies")
AI_KEYS = ("copy", "search", "values", "sight")
SHORT = (-0x8000, 0x7FFF)           # a rank pair's two numbers (short)
BYTE = (-0x80, 0x7F)                # an AI byte (signed char)


def _number(value):
    """A JSON number as Json_Number reads it, or None (true is no number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _same(a, b) -> bool:
    import json
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --- unlock ------------------------------------------------------------------------------

def unlock_of(e) -> dict:
    """The conditions as the form shows them: beat and card as text ("" for
    none), wins and copies (0: the game's default), story (None: none). An
    "unlock" that is no object reads as no conditions (the game leaves it out)."""
    value = e.extra.get("unlock") if e is not None else None
    out = {"beat": "", "wins": 0, "story": None, "card": "", "copies": 0}
    if not isinstance(value, dict):
        return out
    for key in ("beat", "card"):
        given = value.get(key)
        if isinstance(given, str):
            out[key] = given
        elif _number(given) is not None:
            out[key] = str(_number(given))
    for key in ("wins", "copies"):
        out[key] = max(0, _number(value.get(key)) or 0)
    story = _number(value.get("story"))
    out["story"] = story if story is not None and story >= 0 else None
    return out


def unlock_value(e, beat="", wins=0, story=None, card="", copies=0):
    """The "unlock" these conditions make, over the entry's own (whose other
    keys stay); None when there is no condition, and the entry's own while it
    reads the same."""
    old = e.extra.get("unlock")
    if isinstance(old, dict) and unlock_of(e) == {"beat": beat, "wins": wins, "story": story, "card": card,
                                                   "copies": copies}:
        return old
    out = {k: _copy.deepcopy(v) for k, v in old.items() if k not in UNLOCK_KEYS} if isinstance(old, dict) else {}
    if beat:
        out["beat"] = int(beat) if beat.isdigit() else beat
    if wins:
        out["wins"] = wins
    if story is not None:
        out["story"] = story
    if card:
        out["card"] = int(card) if card.isdigit() else card
    if copies and card:
        out["copies"] = copies
    # A "tower" condition (kept from the mod) is a condition too.
    if not any(k in out for k in ("beat", "wins", "story", "card", "tower")):
        return None
    return {**{k: out[k] for k in UNLOCK_KEYS if k in out}, **{k: v for k, v in out.items() if k not in UNLOCK_KEYS}}


def tower_condition(e):
    """The "unlock" "tower" (notes/tower-mode.md): 0 for the whole tower
    won, a floor 1-99, or None for none (or one the game leaves out)."""
    value = e.extra.get("unlock") if e is not None else None
    tower = value.get("tower") if isinstance(value, dict) else None
    if tower is True:
        return 0
    floor = _number(tower)
    return floor if floor is not None and 1 <= floor <= 99 else None


def unlock_text(e) -> str:
    """"beat Heishin 2 times, story flag 1762" -- or "" with no unlock."""
    if e is None or "unlock" not in e.extra:
        return ""
    u = unlock_of(e)
    said = []
    tower = tower_condition(e)
    if tower is not None:
        said.append("the tower won" if tower == 0 else f"the tower's floor {tower} won")
    if u["beat"]:
        said.append(f"beat {u['beat']}" + (f" {u['wins']} times" if u["wins"] > 1 else ""))
    elif u["wins"]:
        said.append(f"{u['wins']} wins in all")
    if u["story"] is not None:
        said.append(f"story flag {u['story']} (0x{u['story']:X})")
    if u["card"]:
        said.append(f"hold {u['card']}" + (f" x{u['copies']}" if u["copies"] > 1 else ""))
    return ", ".join(said) or "nothing (shown from the start)"


# --- ai ------------------------------------------------------------------------------------

def ai_of(e) -> dict:
    """{"copy": the duelist it plays like ("" for its base), "values": nine
    numbers or None where the entry says nothing, "sight": True, False or
    None (its base's)}, as read_one_duelist reads "ai"."""
    value = e.extra.get("ai") if e is not None else None
    out = {"copy": "", "values": [None] * AI_FIELDS, "sight": None}
    if isinstance(value, list):
        for i, v in enumerate(value[:AI_FIELDS]):
            out["values"][i] = _number(v) if _number(v) is not None else 0
    elif isinstance(value, dict):
        if isinstance(value.get("copy"), str):
            out["copy"] = value["copy"]
        if "search" in value:
            out["values"][0] = _number(value["search"]) or 0
        listed = value.get("values")
        if isinstance(listed, list):
            for i, v in enumerate(listed[:AI_FIELDS]):
                # A value that is no number keeps what was there (Json_Number's fallback).
                number = _number(v)
                out["values"][i] = number if number is not None else (out["values"][i] or 0)
        if "sight" in value:
            out["sight"] = bool(value["sight"]) if isinstance(value["sight"], (bool, int, float)) else False
    return out


def _row_of(project, s, seen) -> list:
    """The row duelist s plays by, settled as settle_ai settles it."""
    from . import roster
    if isinstance(s, int):
        e = roster.replacement(project, s)
        base = s
    else:
        e, base = s, s.base
    row = list(AI_ROWS[base]) if 0 <= base < len(AI_ROWS) else list(AI_ROWS[1])
    if e is None or id(e) in seen or "ai" not in e.extra:
        return row
    seen.add(id(e))
    ai = ai_of(e)
    if ai["copy"]:
        other = roster.named(project, ai["copy"])
        if other is not None:
            row = _row_of(project, other, seen)
    for i, v in enumerate(ai["values"]):
        if v is not None:
            row[i] = v
    if ai["values"][0] is not None:
        row[0] = min(max(row[0], AI_SEARCH[0]), AI_SEARCH[1])
    return row


def ai_row(project, s) -> list:
    """The nine numbers duelist s plays by in the game."""
    return _row_of(project, s, set())


def under_row(project, s, copy: str) -> list:
    """The row its own numbers go over: `copy`'s, else its base's."""
    from . import roster
    base = s if isinstance(s, int) else s.base
    other = roster.named(project, copy) if copy else None
    if other is not None and other is not s:
        return ai_row(project, other)
    return list(AI_ROWS[base])


def sight_of(project, s) -> bool:
    """Whether it reads face-down cards: said outright, else its base's."""
    from . import roster
    e = roster.replacement(project, s) if isinstance(s, int) else s
    said = ai_of(e)["sight"] if e is not None else None
    if said is not None:
        return said
    return (s if isinstance(s, int) else s.base) in SIGHT_DUELISTS


def ai_value(e, copy="", values=(None,) * AI_FIELDS, sight=None, under=None):
    """The "ai" these make, over the entry's own (whose other keys stay):
    numbers given past a gap are written as a list from byte 0, the gap
    filled from `under` (the row they go over); None when it says nothing."""
    old = e.extra.get("ai")
    values = list(values) + [None] * (AI_FIELDS - len(values))
    if old is not None and ai_of(e) == {"copy": copy, "values": values, "sight": sight}:
        return old
    out = {k: _copy.deepcopy(v) for k, v in old.items() if k not in AI_KEYS} if isinstance(old, dict) else {}
    head = {}
    if copy:
        head["copy"] = copy
    given = [i for i, v in enumerate(values) if v is not None]
    if given == [0]:
        head["search"] = values[0]
    elif given:
        under = list(under or AI_ROWS[1])
        head["values"] = [values[i] if values[i] is not None else under[i] for i in range(given[-1] + 1)]
    if sight is not None:
        head["sight"] = sight
    if not head:
        return out or None
    return {**head, **out}


def ai_text(project, e) -> str:
    """"plays like Nitemare, search 20, sees face-down cards" -- or ""."""
    if e is None or "ai" not in e.extra:
        return ""
    ai = ai_of(e)
    said = []
    if ai["copy"]:
        said.append(f"plays like {ai['copy']}")
    given = [(i, v) for i, v in enumerate(ai["values"]) if v is not None]
    if given:
        said.append("search " + str(given[0][1]) if [i for i, _ in given] == [0] else
                    "bytes " + ", ".join(f"{i}={v}" for i, v in given))
    if ai["sight"] is not None:
        said.append("sees face-down cards" if ai["sight"] else "does not see face-down cards")
    return ", ".join(said) or "its base's"


# --- ranks ---------------------------------------------------------------------------------

def rule_named(text) -> int:
    for rule, name in enumerate(RANK_RULES):
        if isinstance(text, str) and letters(text) == letters(name):
            return rule
    return -1


def ranks_of(e) -> dict:
    """{rule: five (threshold, change) pairs} for each rule the entry gives
    whole, filled out with the last as the game fills a short one; the last
    threshold 32767, as Tables_SetRank makes it."""
    value = e.extra.get("ranks") if e is not None else None
    out = {}
    if not isinstance(value, dict):
        return out
    for name, steps in value.items():
        rule = rule_named(name)
        if rule < 0 or not isinstance(steps, list) or not steps:
            continue
        pairs = []
        for k in range(RANK_STEPS):
            pair = steps[min(k, len(steps) - 1)]
            if not isinstance(pair, list) or len(pair) < 2:
                break
            pairs.append((_number(pair[0]) or 0, _number(pair[1]) or 0))
        if len(pairs) == RANK_STEPS:
            pairs[-1] = (RANK_ABOVE, pairs[-1][1])
            out[rule] = tuple(pairs)
    return out


def ranks_value(e, rules: dict):
    """The "ranks" these rules make ({rule: five pairs}), over the entry's own:
    a rule it names that the game does not read stays; None when it says
    nothing."""
    old = e.extra.get("ranks")
    if isinstance(old, dict) and ranks_of(e) == {r: tuple(tuple(p) for p in pairs) for r, pairs in rules.items()}:
        return old
    out = {}
    for rule in sorted(rules):
        pairs = [list(p) for p in rules[rule]]
        while len(pairs) > 1 and pairs[-2][1] == pairs[-1][1] and pairs[-1][0] == RANK_ABOVE:
            # [.., [12, 0], [32767, 0]] says the same as [.., [32767, 0]]: the
            # walk stops at the first threshold above the value.
            pairs[-2][0] = RANK_ABOVE
            pairs.pop()
        out[RANK_RULES[rule]] = pairs
    if isinstance(old, dict):
        for name, steps in old.items():
            if rule_named(name) < 0:
                out[name] = _copy.deepcopy(steps)
    return out or None


def ranks_text(e) -> str:
    rules = ranks_of(e)
    return ", ".join(RANK_RULES[r] for r in sorted(rules))


def retail_rank(rule: int):
    return RANK_RETAIL[rule]


# --- applying ------------------------------------------------------------------------------

def _owner(project, s):
    """The entry that says it: a copy itself, a disc duelist's replacement
    (made when there is none)."""
    from . import roster
    return roster.take_over(project, s) if isinstance(s, int) else s


def _put(e, key, value):
    if value is None:
        e.extra.pop(key, None)
    else:
        e.extra[key] = value


def set_rules(project, s, unlock=None, ai=None, ranks=None):
    """Duelist s's unlock, ai and ranks (each a value as unlock_value,
    ai_value and ranks_value make, None to take it out); a disc duelist's go
    on its replacement, which goes when it no longer changes anything."""
    from . import roster
    e = _owner(project, s)
    _put(e, "unlock", unlock)
    _put(e, "ai", ai)
    _put(e, "ranks", ranks)
    if e.replace:
        roster.prune(project, e)
    return e


# --- checks -------------------------------------------------------------------------------

def check(project, e, add):
    """What read_one_duelist and settle_ai would note of the entry's unlock,
    ai and ranks: add(level, message)."""
    from . import roster
    unlock = e.extra.get("unlock")
    if unlock is not None and not isinstance(unlock, dict):
        add("error", "unlock is an object of conditions; the game leaves it out")
    elif isinstance(unlock, dict):
        u = unlock_of(e)
        for key in ("wins", "story", "copies"):
            if key in unlock and _number(unlock[key]) is None:
                add("error", f"unlock {key} is a number")
        if "tower" in unlock and tower_condition(e) is None and unlock["tower"] is not False:
            add("error", "unlock tower is true (the whole tower won) or a floor, 1 to 99")
        if not (u["beat"] or u["card"] or u["wins"] > 0 or u["story"] is not None or
                tower_condition(e) is not None):
            add("warning", "unlock names no condition, so it is shown from the start")
        if u["beat"]:
            found = roster.named(project, u["beat"])
            if found is None:
                add("warning", f"unlock beat {u['beat']!r} names no duelist here: unless another mod adds it, "
                               "it stays locked")
            elif found is e or (e.replace and found == e.base):
                add("error", "unlock beat names itself: it can never be beaten first, so it stays locked")
        if u["card"] and not project.resolve(u["card"], project.info.id):
            add("warning", f"unlock card {u['card']!r} names no card here: unless another mod adds it, "
                           "it stays locked")
    ai = e.extra.get("ai")
    if ai is not None and not isinstance(ai, (list, dict)):
        add("error", "ai is a list of numbers, or an object; the game leaves it out")
    elif ai is not None:
        a = ai_of(e)
        if a["copy"] and roster.named(project, a["copy"]) is None:
            add("warning", f"ai copy {a['copy']!r} names no duelist here: unless another mod adds it, it plays "
                           "as its base")
        if a["values"][0] is not None and not AI_SEARCH[0] <= a["values"][0] <= AI_SEARCH[1]:
            add("warning", f"ai search is {AI_SEARCH[0]} to {AI_SEARCH[1]}; the game holds {a['values'][0]} there")
        if any(v is not None and not BYTE[0] <= v <= BYTE[1] for v in a["values"]):
            add("error", f"an ai number is a byte, {BYTE[0]} to {BYTE[1]}")
    ranks = e.extra.get("ranks")
    if ranks is not None and not isinstance(ranks, dict):
        add("error", "ranks is an object of rules; the game leaves it out")
    elif isinstance(ranks, dict):
        for name, steps in ranks.items():
            if rule_named(name) < 0:
                add("error", f"ranks \"{name}\": no such rule ({', '.join(RANK_RULES)})")
            elif not isinstance(steps, list) or not steps or any(
                    not isinstance(p, list) or len(p) < 2 for p in steps[:RANK_STEPS]):
                add("error", f"ranks \"{name}\": up to {RANK_STEPS} [threshold, change] pairs; the game keeps "
                             "the disc's")
            elif any(_number(v) is None or not SHORT[0] <= _number(v) <= SHORT[1]
                     for p in steps[:RANK_STEPS] for v in p[:2]):
                add("error", f"ranks \"{name}\": a threshold or change is a whole number, {SHORT[0]} to {SHORT[1]}")


# --- naming a duelist ---------------------------------------------------------------------

def reference(project, s) -> str:
    """How a manifest names duelist s so the game finds it (Duelists_Named):
    a disc duelist by the disc's name, which it answers to however a mod
    renamed it; an added one by its name while that finds it, else by its
    identity."""
    from . import roster
    if isinstance(s, int):
        return DUELIST_NAMES[s] if 0 <= s < DUELIST_COUNT else str(s)
    name = roster.shown_name(project, s)
    return name if roster.named(project, name) is s else roster.identity(project, s)


def references(project, but=None) -> list:
    """Every opponent by reference(): the disc's, then the mod's own on the grid."""
    from . import roster
    out = [reference(project, d) for d in range(1, DUELIST_COUNT)]
    placed = sorted(((at, e) for e, at in roster.placement(project).items() if at is not None), key=lambda x: x[0])
    out += [reference(project, e) for _, e in placed if e is not but]
    return out
