"""A mod's "guardian_stars" (notes/modding.md, "Guardian Stars"): the stars'
names and icons, new stars past the disc's ten, and the matchup table. The
port reads it in src/pc/cards/stars.c; the arithmetic and the checks here are
that file's, and tests/pc/guardian_stars/*.expected pins both to the same
table for every pair (tests/pc/stars_test.c and tests/test_guardian_stars.py).

The mod.json shape:

    "guardian_stars": {
        "stars": [{"id": 11, "name": "Fire", "icon": "icons/fire.png", "beats": ["Grass"]}],
        "matchups": [{"attacker": 1, "defender": 2, "bonus": 1000, "mirror": true}],
        "default_bonus": 500,
        "replace": false,
        "choice": "ask"
    }

The matchup table is one signed adjustment for each ORDERED pair (the
attacker's star, the defender's star): what Duel_CalcGuardianStarMatchup
returns, which the duel adds to the attacker's side of the comparison. The
editor keeps the section in Project.other["guardian_stars"] as written; the
Guardian Stars tab turns it into a `Stars` (`read`) and back (`Stars.build`),
which writes the stars it declares and only the pairs that differ from what
the rest of the section already gives.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .gamedata import STAR_NAMES


def _letters(text: str) -> str:
    return "".join(c.lower() if c.isascii() else c for c in text if not c.isascii() or c.isalnum())


def same_letters(a: str, b: str) -> bool:
    """stars.c's same_letters: ASCII letters and digits, case apart, and
    every byte past ASCII as it is (model.same_letters drops those, which
    made every name without an ASCII letter the same name)."""
    return _letters(a) == _letters(b)


def _whole(text: str):
    """The whole number a string holds, or None ("--5" and "²" hold none)."""
    return int(text) if re.fullmatch(r"-?[0-9]+", text.strip()) else None

RETAIL_COUNT = 10           # Mars .. Venus
MAX_STARS = 15              # the card record's 4-bit star fields
IDS = MAX_STARS + 1         # 0 (no star) to 15
RETAIL_BONUS = 500          # the disc's DUEL_GUARDIAN_STAR_BONUS
BONUS_MAX = 32767           # the on-screen modifier and the stats are 16-bit
STAT_CAP = 9999             # the game's ATK/DEF cap; a mod's "limits" moves it
KEYS = ("stars", "matchups", "default_bonus", "replace", "choice")
STAR_KEYS = ("id", "name", "icon", "palette", "beats")
CHOICES = ("ask", "first", "best")         # "choice": how a summoned monster's star is picked
PALETTES = ("game", "own")                 # an icon's colors: the disc's stars', or the PNG's
# Where the widening past 15 would have to start: every card's record.
PAST_15 = "a card holds a star in 4 bits, so there are 15 at most"


def retail_matchup(a0: int, a1: int) -> int:
    """Duel_CalcGuardianStarMatchup's arithmetic for any two 4-bit ids, as
    the disc runs it (stars.c Stars_RetailMatchup): 1-6 and 7-10 are two
    cycles, the next star is +500 and the previous -500. Ids outside 1-10 go
    through it too (0 against Mars is +500, 11 against Mercury +500)."""
    a0 -= 7
    if a0 >= 0:
        a1 -= 7
        if a1 < 0:
            return 0
        v1 = 4
    else:
        v1 = 6
        a1 -= 1
        a0 += v1
        if a1 >= v1:
            return 0
    a0 += 1
    if a0 >= v1:
        a0 = 0
    if a0 == a1:
        return RETAIL_BONUS
    a0 -= 2
    if a0 < 0:
        a0 += v1
    if a0 == a1:
        return -RETAIL_BONUS
    return 0


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def star_number(value) -> int:
    """An "id" as stars.c reads it (Json_Number): a whole number, or a string
    that holds one; -1 for anything else."""
    if _is_int(value):
        return value
    if isinstance(value, str) and _whole(value) is not None:
        return _whole(value)
    return -1


def name_list(name) -> list:
    """Every name a star's "name" gives, in any language."""
    if isinstance(name, str):
        return [name]
    if isinstance(name, dict):
        return [text for text in name.values() if isinstance(text, str)]
    return []


def display_name(name, star: int = 0) -> str:
    """The name the editor shows: the plain one, else "default", "en-us",
    "en" or the first; else the disc's English, else "Star N"."""
    if isinstance(name, str) and name:
        return name
    if isinstance(name, dict):
        for key in ("default", "en-us", "en"):
            if isinstance(name.get(key), str):
                return name[key]
        for text in name.values():
            if isinstance(text, str):
                return text
    if 1 <= star <= RETAIL_COUNT:
        return STAR_NAMES[star]
    return f"Star {star}" if star else ""


def declared_names(section) -> dict:
    """{star id: [names]} for the stars a section declares."""
    out = {}
    stars = section.get("stars") if isinstance(section, dict) else None
    for entry in stars if isinstance(stars, list) else []:
        if isinstance(entry, dict) and 1 <= star_number(entry.get("id")) <= MAX_STARS:
            out.setdefault(star_number(entry["id"]), []).extend(name_list(entry.get("name")))
    return out


def find(name, section=None) -> int:
    """A star by its number, the disc's English name, or a name the section
    gives (stars.c Stars_Find); -1 for none."""
    if _is_int(name):
        return name
    if not isinstance(name, str) or not name:
        return -1
    text = name.strip()
    if _whole(text) is not None:
        number = _whole(text)
        return number if 0 <= number <= MAX_STARS else -1
    for star in range(1, RETAIL_COUNT + 1):
        if same_letters(text, STAR_NAMES[star]):
            return star
    for star, names in sorted(declared_names(section).items()):
        if any(same_letters(text, other) for other in names):
            return star
    return -1


def card_star(value, section=None) -> int:
    """One of a card's "stars" as stars.c Stars_Value reads it: a number (0 is
    none), a star's name, or none (null, "none", the Cards tab's "(none)"),
    which a star the mod names "None" stands over; -1 for anything else."""
    if value is None:
        return 0
    if _is_int(value):
        return value if value >= 0 else -1
    if not isinstance(value, str):
        return -1
    star = find(value, section)
    if star >= 0:
        return star
    return 0 if same_letters(value, "none") else -1


def normalized(first: int, second: int) -> tuple:
    """The stars a card has in the game (stars.c Stars_Normalize): a first of
    none with a second is that one star, [X, none]; anything else as it is."""
    return (second, 0) if first == 0 and second > 0 else (first, second)


def count(section) -> int:
    """How many stars there are: 10, or the highest one declared."""
    return max([RETAIL_COUNT] + list(declared_names_ids(section)))


def declared_names_ids(section):
    stars = section.get("stars") if isinstance(section, dict) else None
    for entry in stars if isinstance(stars, list) else []:
        if isinstance(entry, dict) and 1 <= star_number(entry.get("id")) <= MAX_STARS:
            yield star_number(entry["id"])


def _bonus_ok(value) -> bool:
    return _is_int(value) and -BONUS_MAX <= value <= BONUS_MAX


def table(section, messages: list = None) -> list:
    """The table a game with this section uses: table[attacker][defender]
    for every pair of 4-bit ids, as stars.c builds it and
    Duel_CalcGuardianStarMatchup returns it. `messages` gets what stars.c
    would note."""
    note = messages.append if messages is not None else (lambda text: None)
    out = [[retail_matchup(a, d) for d in range(IDS)] for a in range(IDS)]
    if section is None:
        return out
    if not isinstance(section, dict):
        note("\"guardian_stars\" is an object: \"stars\", \"matchups\", \"default_bonus\", \"replace\", \"choice\"")
        return out
    for key in section:
        if key not in KEYS:
            note(f"unknown key '{key}' (the keys are stars, matchups, default_bonus, replace, choice)")
    if "choice" in section and not (isinstance(section["choice"], str) and
                                    any(same_letters(section["choice"], c) for c in CHOICES)):
        note("\"choice\" is \"ask\", \"first\" or \"best\"")
    replace = section.get("replace") is True
    if replace:
        out = [[0] * IDS for _ in range(IDS)]
    default = RETAIL_BONUS
    if "default_bonus" in section:
        if _bonus_ok(section["default_bonus"]):
            default = section["default_bonus"]
            if not replace:
                for a in range(1, RETAIL_COUNT + 1):
                    for d in range(1, RETAIL_COUNT + 1):
                        retail = retail_matchup(a, d)
                        if retail:
                            out[a][d] = default if retail > 0 else -default
        else:
            note(f"default_bonus: a bonus is a whole number of points, -{BONUS_MAX} to {BONUS_MAX}")

    def star_id(value, where):
        star = find(value, section) if isinstance(value, (int, str)) and not isinstance(value, bool) else -1
        if 1 <= star <= MAX_STARS:
            return star
        if star > MAX_STARS:
            note(f"{where}: star {star}: {PAST_15}")
        else:
            note(f"{where}: not a star (a number 1-15, or a star's name)")
        return None

    stars = section.get("stars")
    declared = set()
    if stars is not None and not isinstance(stars, list):
        note("\"stars\" is a list of {\"id\", \"name\", \"icon\"}")
        stars = []
    for index, entry in enumerate(stars or []):
        where = f"stars[{index}]"
        if not isinstance(entry, dict) or "id" not in entry:
            note(f"{where}: an object with an \"id\" (1-15)")
            continue
        star = star_number(entry["id"])
        if not 1 <= star <= MAX_STARS:
            note(f"{where}: star {star}: {PAST_15}" if star > MAX_STARS
                 else f"{where}: not a star (a number 1-15, or a star's name)")
            continue
        if star > RETAIL_COUNT and star not in declared:
            for other in range(IDS):
                out[star][other] = 0
                out[other][star] = 0
        declared.add(star)
    for index, entry in enumerate(stars or []):
        if not isinstance(entry, dict) or not 1 <= star_number(entry.get("id")) <= MAX_STARS:
            continue
        me = star_number(entry["id"])
        beats = entry.get("beats")
        if beats is None:
            continue
        if not isinstance(beats, list):
            note(f"stars[{index}]: \"beats\" is a list of stars")
            continue
        for k, target in enumerate(beats):
            other = star_id(target, f"stars[{index}].beats[{k}]")
            if other is not None:
                out[me][other] = default
                out[other][me] = -default
    matchups = section.get("matchups")
    if matchups is not None and not isinstance(matchups, list):
        note("\"matchups\" is a list of {\"attacker\", \"defender\", \"bonus\"}")
        matchups = []
    for index, entry in enumerate(matchups or []):
        where = f"matchups[{index}]"
        if not isinstance(entry, dict):
            note(f"{where}: an object with \"attacker\", \"defender\" and \"bonus\"")
            continue
        attacker = star_id(entry.get("attacker"), where)
        if attacker is None:
            continue
        defender = star_id(entry.get("defender"), where)
        if defender is None:
            continue
        bonus = default
        if "bonus" in entry:
            if not _bonus_ok(entry["bonus"]):
                note(f"{where}: a bonus is a whole number of points, -{BONUS_MAX} to {BONUS_MAX}")
                continue
            bonus = entry["bonus"]
        out[attacker][defender] = bonus
        if entry.get("mirror") is True:
            out[defender][attacker] = -bonus
    return out


def check(section, stat_cap: int = STAT_CAP, card_stars=None) -> list:
    """(level, where, message) for what stars.c notes: "error" where it
    leaves something out; "warning" for a star no card has
    (`card_stars`: {star: how many card fields hold it}), a card star no
    section declares, a declared star with no matchup, and a bonus past the
    stat cap."""
    messages = []
    effective = table(section, messages)
    out = [("error", "guardian_stars", text) for text in messages]
    if section is None or not isinstance(section, dict):
        return out
    declared = declared_names(section)
    for star in sorted(declared):
        if card_stars is not None and not card_stars.get(star):
            out.append(("warning", f"star {star}", f"no card has star {star} ({display_name(_name_of(section, star), star)})"))
        if not any(effective[star][o] or effective[o][star] for o in range(1, IDS)):
            out.append(("warning", f"star {star}",
                        f"star {star} has no matchup: every battle with it is neutral"))
    for star, n in sorted((card_stars or {}).items()):
        if star > RETAIL_COUNT and n and star not in declared:
            out.append(("warning", f"star {star}", f"{n} cards have star {star}, which the mod does not declare"))
    for a in range(1, IDS):
        for d in range(1, IDS):
            if abs(effective[a][d]) > stat_cap and effective[a][d] != retail_matchup(a, d):
                out.append(("warning", f"star {a} against {d}",
                            f"{effective[a][d]} is past the ATK/DEF cap of {stat_cap}"))
                return out
    return out


def _name_of(section, star):
    stars = section.get("stars") if isinstance(section, dict) else None
    for entry in stars if isinstance(stars, list) else []:
        if isinstance(entry, dict) and star_number(entry.get("id")) == star and "name" in entry:
            return entry["name"]
    return None


def choices(section) -> list:
    """The stars a card may have with this section: "(none)", the disc's ten
    (a renamed one as "Ares (Mars)") and the mod's own past them ("11 Fire"),
    each at its number's place in the list."""
    out = ["(none)"]
    for star in range(1, count(section) + 1):
        name = display_name(_name_of(section, star) if section else None, star)
        if star <= RETAIL_COUNT:
            out.append(name if name == STAR_NAMES[star] else f"{name} ({STAR_NAMES[star]})")
        else:
            out.append(f"{star} {name}")
    return out


@dataclass
class Star:
    id: int
    name: object = None          # str, {language: str}, or None (the disc's / "Star N")
    icon: str = None             # a PNG's path inside the mod
    palette: str = None          # "own" keeps the PNG's colors; None/"game" the disc's stars'
    extra: dict = field(default_factory=dict)   # keys the editor does not show, kept


@dataclass
class Stars:
    """The Guardian Stars tab's model: the declared stars, the default bonus,
    whether the disc's cycles are cleared first, and the full table."""
    stars: dict = field(default_factory=dict)       # id -> Star
    default_bonus: int = None                       # None: the disc's 500
    replace: bool = False
    choice: str = None                              # None: "ask", the disc's box
    grid: list = field(default_factory=lambda: table(None))
    kept: dict = field(default_factory=dict)        # keys of the section the editor does not know

    @property
    def count(self) -> int:
        return max([RETAIL_COUNT] + list(self.stars))

    def name(self, star: int) -> str:
        entry = self.stars.get(star)
        return display_name(entry.name if entry else None, star)

    def base(self) -> list:
        """What the section gives without its matchups: the disc's cycles (or
        none), at the default bonus, and every declared new star neutral."""
        section = {"replace": True} if self.replace else {}
        if self.default_bonus is not None:
            section["default_bonus"] = self.default_bonus
        section["stars"] = [{"id": star} for star in sorted(self.stars)]
        return table(section)

    def build(self):
        """The section for mod.json; None when it would change nothing."""
        out = dict(self.kept)
        stars = []
        for star in sorted(self.stars):
            entry = self.stars[star]
            item = {"id": star}
            if entry.name not in (None, "", {}):
                item["name"] = entry.name
            if entry.icon:
                item["icon"] = entry.icon
            if entry.palette:
                item["palette"] = entry.palette
            item.update({k: v for k, v in entry.extra.items() if k not in item})
            stars.append(item)
        if stars:
            out["stars"] = stars
        if self.replace:
            out["replace"] = True
        if self.choice and self.choice != "ask":
            out["choice"] = self.choice
        if self.default_bonus is not None:
            out["default_bonus"] = self.default_bonus
        base = self.base()
        matchups = [{"attacker": a, "defender": d, "bonus": self.grid[a][d]}
                    for a in range(1, IDS) for d in range(1, IDS) if self.grid[a][d] != base[a][d]]
        if matchups:
            out["matchups"] = matchups
        return out or None

    def set_default(self, bonus):
        """A new default bonus: the pairs that were at the old default's
        cycles move with it; pairs the mod set on their own stay."""
        before = self.base()
        self.default_bonus = bonus
        after = self.base()
        for a in range(IDS):
            for d in range(IDS):
                if self.grid[a][d] == before[a][d]:
                    self.grid[a][d] = after[a][d]

    def preset_retail(self):
        """The disc's two cycles at the default bonus; new stars neutral."""
        self.replace = False
        self.grid = self.base()

    def preset_clear(self):
        """Every pair neutral."""
        self.replace = True
        self.grid = [[0] * IDS for _ in range(IDS)]

    def add_star(self) -> int:
        """The next free id past the disc's; 0 when all fifteen are taken."""
        for star in range(RETAIL_COUNT + 1, MAX_STARS + 1):
            if star not in self.stars:
                before = self.base()
                self.stars[star] = Star(star)
                after = self.base()
                for o in range(IDS):
                    for a, d in ((star, o), (o, star)):
                        if self.grid[a][d] == before[a][d]:
                            self.grid[a][d] = after[a][d]
                return star
        return 0

    def remove_star(self, star: int):
        """A new star gone (its pairs back to what an undeclared star has:
        base(), so nothing of it is written); a disc star just loses its
        name and icon."""
        if star not in self.stars:
            return
        del self.stars[star]
        if star > RETAIL_COUNT:
            base = self.base()
            for o in range(IDS):
                self.grid[star][o] = base[star][o]
                self.grid[o][star] = base[o][star]


def read(section) -> Stars:
    """The tab's model from a section as a mod wrote it (beats and mirror
    turn into the table they give)."""
    model = Stars()
    if not isinstance(section, dict):
        return model
    model.kept = {k: copy.deepcopy(v) for k, v in section.items() if k not in KEYS}
    model.replace = section.get("replace") is True
    if isinstance(section.get("choice"), str):
        model.choice = next((c for c in CHOICES if same_letters(section["choice"], c)), None)
    if _bonus_ok(section.get("default_bonus")):
        model.default_bonus = section["default_bonus"]
    for entry in section["stars"] if isinstance(section.get("stars"), list) else []:
        if isinstance(entry, dict) and 1 <= star_number(entry.get("id")) <= MAX_STARS:
            number = star_number(entry["id"])
            star = model.stars.setdefault(number, Star(number))
            if "name" in entry:
                star.name = copy.deepcopy(entry["name"])
            if isinstance(entry.get("icon"), str):
                star.icon = entry["icon"]
            if isinstance(entry.get("palette"), str):
                star.palette = next((p for p in PALETTES if same_letters(entry["palette"], p)), star.palette)
            star.extra.update({k: copy.deepcopy(v) for k, v in entry.items() if k not in STAR_KEYS})
    model.grid = table(section)
    return model
