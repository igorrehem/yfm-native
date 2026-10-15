r"""A mod's "tower" (notes/tower-mode.md; src/pc/tower/tower_config.c): the
checks the game makes when it reads one, and the text forms the Tower tab
edits it in.

The tower stays in project.other["tower"] as written. The tab shows a story
as lines of text, a page or more of the box a line, its stage in brackets on
the line before the one it begins with:

    [scene: torch corridor] [left: 1] [right: opponent]
    Welcome to the tower.
    @right: You will not pass.       said by the right side's character
    @Seto: You will not pass.        said by a duelist (an id, a name, an identity)
    #8: The prince steps in.         with one of the campaign's 25 portraits
    #speaker @Seto: Both.            with the speaker's own face
    @none: The wind howls.           nobody's
    [scene: scenes/sky.png] [right: art/hero.png flip] [pan: 64 0 30 wait]
    \@ plain words                   a backslash: words that would read as a speaker's
    One\nTwo                         \n: a line break inside the box

and a deck as a card a line, "Blue-eyes White Dragon x3" (x1 when left out).
"""
from __future__ import annotations

import copy as _copy
import re

TOWER_MAX_FLOORS = 99
LABEL_MAX = 31
NAME_MAX = 63
LINE_MAX = 1023
CAMPAIGN_PORTRAITS = 25
REWARD_CARDS = 10
REWARD_DUELISTS = 8
DECK = 40
TERRAINS = ("none", "Forest", "Wasteland", "Mountain", "Meadow", "Sea", "Dark")
TERRAIN_WORDS = {"none": 0, "0": 0, "forest": 1, "wasteland": 2, "mountain": 3, "sogen": 4, "meadow": 4,
                 "umi": 5, "sea": 5, "yami": 6, "dark": 6}
UNLOCKS = ("always", "after_ending", "conditions")
TOWER_KEYS = ("name", "label", "music", "unlock", "on_lose", "on_leave", "drops", "save_states", "cheats", "scene",
              "dim", "intro", "ending", "lose", "floors")
ON_LEAVE = ("resume", "checkpoint", "restart")
DROPS_DEFAULT, DROPS_MAX = 1, 99
FLOOR_KEYS = ("duelist", "field", "deck", "life_points", "no_fusions", "no_equips", "reward", "checkpoint",
              "unlock_opponent",
              "before", "after")
REWARD_KEYS = ("card", "cards", "starchips", "unlock_duelist")
UNLOCK_KEYS = ("after_ending", "beat", "wins", "story", "card", "copies")
LINE_KEYS = ("text", "speaker", "portrait", "scene", "characters", "pan")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def terrain_of(value) -> int | None:
    """A floor's "field" as the game reads it: 0-6, or None for none it knows."""
    if value is None:
        return 0
    text = str(value).strip().lower()
    if text.isdigit():
        number = int(text)
        return number if 0 <= number <= 6 else None
    return TERRAIN_WORDS.get(text)


# --- the stage (notes/tower-mode.md, Story; src/pc/tower/tower_config.c) -----------------

# Mode 0's scenes by name, in their order (0x000-0x041): tower_config.c's scene_names.
SCENE_NAMES = (
    "black", "palace gate", "palace chamber", "jungle temple door", "card shop", "colonnade hall",
    "moonlit colonnade", "collapsed ruins", "classroom", "tournament lounge", "card collection",
    "shop street", "temple ruins", "destroyed town", "ruined altar room", "ruined chamber",
    "sunlit ruined hall", "fiery valley gate", "seal shrine", "green pyramid", "green mausoleum",
    "obelisk avenue", "torch corridor", "cliff temple", "night temple stairs", "jungle pyramid",
    "green shrine", "dusk tower", "altar hall", "desert sphinx", "sphinx shrine", "meadow temple",
    "twin statue shrine", "throne room", "hall of fires", "eye chamber", "town at night",
    "night balcony", "golden doors", "golden door chamber", "statue gallery", "burning pyramid",
)
SCENE_DEFAULT = 22                   # "torch corridor"
SCENE_COUNTS = (42, 42, 13)          # modes 0, 1, 2
CHARACTERS = 64
EMPTY_CHARACTERS = (0, 5, 11, 39, 40, 41)
SIDES = ("left", "right")
CAST_KEYS = ("character", "duelist", "image", "expression", "flip")
STORY_KEYS = ("scene", "characters", "lines")
PAN_KEYS = ("x", "y", "frames", "wait")
STORY_LETTERS = 12000
LINE_CODES = 48                      # what a line's stage may add to its letters (tower.h)
ARTS = 96                            # a tower's PNGs
STORY_PICTURES = 5                   # a story's characters of the mod's


def retail_scene(number) -> bool:
    """A scene's number (its id's decimal digits: 22, 139, 205) of the disc's."""
    if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= 299:
        return False
    return number % 100 < SCENE_COUNTS[number // 100]


def _is_png(text: str) -> bool:
    return len(text) > 4 and text[-4:].lower() == ".png"


def scene_number(value, typed: bool = False):
    """A "scene" as the game reads it (tower_config.c read_scene): a retail
    scene's number, a PNG's path, or None for none it knows. `typed`: the
    tab's own text, where a number is written as digits."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if retail_scene(value) else None
    if isinstance(value, str):
        text = value.strip() if typed else value
        if _is_png(text):
            return text
        word = text.lower().replace("_", " ").replace("-", " ")
        if word == "none":
            return 0
        if word in SCENE_NAMES:
            return SCENE_NAMES.index(word)
        if typed and text.isdigit() and retail_scene(int(text)):
            return int(text)
    return None


def scene_label(number) -> str:
    """How the tab shows a scene: its name, else its number, else the path."""
    if isinstance(number, int) and 0 <= number < len(SCENE_NAMES):
        return SCENE_NAMES[number]
    return str(number)


def _png_inside(path: str) -> bool:
    text = path.replace("\\", "/")
    return not (text.startswith("/") or (len(text) > 1 and text[1] == ":") or ".." in text.split("/"))


def _cast(value):
    """A side's character in one form: "none", {"character": n},
    {"duelist": ...}, {"image": ...} (with "duelist", "expression", "flip"
    as given)."""
    if value is None or (isinstance(value, str) and value.strip().lower() in ("", "none")):
        return "none"
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {"character": value}
    if isinstance(value, str):
        return {"image": value} if _is_png(value) else {"duelist": value}
    if isinstance(value, dict):
        out = dict(value)
        if "image" in out and (out.get("duelist") is None or str(out.get("duelist")).strip().lower() in
                               ("", "none")):
            out.pop("duelist", None)
        if out.get("expression") == 0:
            out.pop("expression")
        if out.get("flip") is False:
            out.pop("flip")
        return out
    return value


def _canon_line(item) -> dict:
    if isinstance(item, str):
        return {"text": item}
    if not isinstance(item, dict):
        return {"bad": item}
    out = {}
    for key, value in item.items():
        if key == "scene":
            number = scene_number(value)
            out[key] = number if number is not None else ("bad", value)
        elif key == "characters" and isinstance(value, dict):
            out[key] = {side: _cast(value[side]) for side in value}
        elif key == "speaker":
            out[key] = "none" if value in (None, "") else value.lower() if isinstance(value, str) and \
                value.lower() in ("none", "left", "right", "opponent") else value
        elif key == "pan" and isinstance(value, dict):
            out[key] = {"x": value.get("x", 0), "y": value.get("y", 0), "frames": value.get("frames", 60),
                        "wait": value.get("wait", False) is True}
        elif key == "portrait":
            out[key] = "speaker" if value is True else "none" if value is False or value is None else \
                value.lower() if isinstance(value, str) else value
        else:
            out[key] = value
    return out


def canon_story(value):
    """A story in one form, to compare two spellings of it: a list of line
    objects, a story object's stage on its first line."""
    if value is None:
        return None
    lines, stage = value, {}
    if isinstance(value, dict) and "lines" in value:
        lines = value["lines"]
        stage = {key: value[key] for key in ("scene", "characters") if key in value}
    items = lines if isinstance(lines, list) else [lines]
    out = [_canon_line(item) for item in items]
    if stage and out:
        first = _canon_line(stage)
        first.update({key: val for key, val in out[0].items()
                      if key != "characters"})
        if "characters" in out[0]:
            first["characters"] = dict(first.get("characters", {}), **out[0]["characters"])
        out[0] = first
    return out or None


# --- story lines ----------------------------------------------------------------------
#
# A story is shown as lines of text, one line of the story a line of the tab;
# before a line, its stage in brackets:
#
#     [scene: torch corridor] [left: Simon Muran] [right: art/hero.png flip]
#     @left: My dear prince!            said by the left side's character
#     #3 @right: Words.                 with campaign portrait 3 beside the box
#     #speaker @Seto: Words.            with the speaker's own face
#     [pan: 64 0 30 wait]
#     The view moves on.
#
# A side is none, a character's number (1-64), a duelist, "opponent", or a PNG
# ("flip" turns it; "as Seto" says whose it is); "expression 2" after a
# character's number or a duelist.

# "#8 @Seto: words": a campaign portrait, a speaker, or both, then the words.
LINE_RE = re.compile(r"^(?:#(\d+|speaker|none)\s*)?(?:@([^:]*))?:\s?(.*)$", re.I)
DIRECTIVE_RE = re.compile(r"\[\s*(scene|left|right|pan)\s*:\s*([^\]]*)\]", re.I)
DIRECTIVES_LINE_RE = re.compile(r"^(?:\s*\[\s*(?:scene|left|right|pan)\s*:[^\]]*\])+\s*$", re.I)
NEWLINE = r"\n"        # a line break inside a box's words, as the tab shows it: a backslash and n


def _speaks(line: str) -> bool:
    found = LINE_RE.match(line)
    return bool(found) and (found.group(1) is not None or found.group(2) is not None)


def _encode(text: str, plain: bool) -> str:
    """Words as a line of the tab: a backslash before a backslash, \\n for a
    line break, and a backslash before what the line's trimming, a
    speaker's "@Name:" or a stage's "[scene: ...]" would otherwise take."""
    out = text.replace("\\", "\\\\").replace("\n", NEWLINE)
    if out and out[-1].isspace():
        out = out[:-1] + "\\" + out[-1]
    if out and (out[0].isspace() or (plain and (_speaks(out) or DIRECTIVES_LINE_RE.match(out)))):
        out = "\\" + out
    return out


def _trim(text: str) -> str:
    """Spaces off both ends of a line, but for one a backslash keeps."""
    text = text.lstrip()
    kept = text.rstrip()
    if len(kept) < len(text) and (len(kept) - len(kept.rstrip("\\"))) % 2:
        kept += text[len(kept)]
    return kept


def _decode(text: str) -> str:
    """The tab's line back to its words, in one pass: \\n is a line break,
    a backslash before anything else is that letter."""
    return re.sub(r"\\(.)", lambda found: "\n" if found.group(1) == "n" else found.group(1), text)


def _cast_text(value) -> str:
    """A side as the tab shows it: "none", a character's number, a duelist
    ("duelist 7" when it is a number), "opponent", or a PNG; then "flip",
    "expression N", and last "as <duelist>" for a PNG's."""
    cast = _cast(value)
    if cast == "none" or not isinstance(cast, dict):
        return "none" if cast == "none" else str(cast)
    words = []
    if "image" in cast:
        words.append(str(cast["image"]))
    elif "character" in cast:
        words.append(str(cast["character"]))
    elif "duelist" in cast:
        who = str(cast["duelist"])
        words.append(f"duelist {who}" if who.isdigit() or who.lower() in ("none", "flip", "expression") else who)
    if cast.get("flip"):
        words.append("flip")
    if cast.get("expression"):
        words += ["expression", str(cast["expression"])]
    if "image" in cast and cast.get("duelist") not in (None, ""):
        words += ["as", str(cast["duelist"])]
    return " ".join(words)


def _cast_value(text: str):
    """A side as the tab writes it back: "none", a number, a name, a PNG, or
    an object when it says more. A name or a path may hold spaces: what
    comes off its end are "as <duelist>", "expression N" and "flip"."""
    text = text.strip()
    if not text or text.lower() == "none":
        return "none"
    whose = None
    lowered = text.lower()
    if " as " in lowered and ".png" in lowered[:lowered.rindex(" as ")]:
        at = lowered.rindex(" as ")
        text, whose = text[:at].strip(), text[at + 4:].strip()
    expression = flip = None
    while True:
        words = text.split()
        if len(words) >= 2 and words[-2].lower() == "expression" and words[-1].isdigit():
            expression = int(words[-1])
            text = " ".join(words[:-2])
        elif len(words) >= 2 and words[-1].lower() == "flip":
            flip = True
            text = " ".join(words[:-1])
        else:
            break
    if _is_png(text):
        out = {"image": text}
        if whose:
            out["duelist"] = int(whose) if whose.isdigit() else whose
        if flip:
            out["flip"] = True
    elif text.lower().startswith("duelist "):
        who = text[8:].strip()
        out = {"duelist": int(who) if who.isdigit() else who}
    elif text.isdigit():
        out = {"character": int(text)}
    else:
        out = {"duelist": text}
    if expression:
        out["expression"] = expression
    if len(out) == 1 and "image" in out:
        return out["image"]
    if len(out) == 1 and "character" in out:
        return out["character"]
    if len(out) == 1 and "duelist" in out and isinstance(out["duelist"], str):
        return out["duelist"]
    return out


def _pan_text(pan) -> str:
    if not isinstance(pan, dict):
        return str(pan)
    words = [str(pan.get("x", 0)), str(pan.get("y", 0)), str(pan.get("frames", 60))]
    if pan.get("wait"):
        words.append("wait")
    return " ".join(words)


def _pan_value(text: str):
    words = text.split()
    numbers = [int(w) for w in words if w.lstrip("-").isdigit()]
    out = {"x": numbers[0] if numbers else 0, "y": numbers[1] if len(numbers) > 1 else 0}
    if len(numbers) > 2:
        out["frames"] = numbers[2]
    if any(w.lower() == "wait" for w in words):
        out["wait"] = True
    return out


def story_text(value) -> str:
    """A story as the tab shows it: a line of text per line, its stage in
    brackets on the line before. A plain line that would read as a
    speaker's or a stage's starts with a backslash."""
    lines = canon_story(value)
    if lines is None:
        return ""
    out = []
    for item in lines:
        if "bad" in item:
            continue
        stage = []
        if "scene" in item:
            scene = item["scene"]
            stage.append(f"[scene: {scene_label(scene) if not isinstance(scene, tuple) else scene[1]}]")
        for side in SIDES:
            if side in item.get("characters", {}):
                stage.append(f"[{side}: {_cast_text(item['characters'][side])}]")
        if "pan" in item:
            stage.append(f"[pan: {_pan_text(item['pan'])}]")
        if stage:
            out.append(" ".join(stage))
        text = str(item.get("text", ""))
        head = f"#{item['portrait']}" if "portrait" in item else ""
        if "speaker" in item:
            speaker = item["speaker"]
            head += (" " if head else "") + f"@{'none' if speaker in (None, '') else speaker}"
        out.append(f"{head}: {_encode(text, False)}" if head else _encode(text, True))
    return "\n".join(out)


def same_story(old, text: str) -> bool:
    """Whether the tab's text still says what `old` (as written) says: then
    the mod keeps its own spelling of it."""
    return old is not None and canon_story(story_value(text)) == canon_story(old)


def story_value(text: str):
    """The tab's lines as the manifest writes them: None for none, a string
    for one plain line, else a list."""
    out = []
    stage = {}
    for line in text.splitlines():
        line = _trim(line)
        if not line:
            continue
        if not line.startswith("\\") and DIRECTIVES_LINE_RE.match(line):
            for found in DIRECTIVE_RE.finditer(line):
                key, value = found.group(1).lower(), found.group(2).strip()
                if key == "scene":
                    number = scene_number(value, typed=True)
                    stage["scene"] = value if number is None else number if isinstance(number, str) else \
                        SCENE_NAMES[number] if number < len(SCENE_NAMES) and not value.isdigit() else number
                elif key == "pan":
                    stage["pan"] = _pan_value(value)
                else:
                    stage.setdefault("characters", {})[key] = _cast_value(value)
            continue
        if line.startswith("\\"):
            entry = {"text": _decode(line)}
        else:
            found = LINE_RE.match(line)
            if found and (found.group(1) is not None or found.group(2) is not None):
                entry = {"text": _decode(_trim(found.group(3)))}
                if found.group(1) is not None:
                    face = found.group(1)
                    entry["portrait"] = int(face) if face.isdigit() else face.lower()
                if found.group(2) is not None:
                    who = found.group(2).strip()
                    entry["speaker"] = "none" if who.lower() in ("", "none") else int(who) if who.isdigit() else \
                        who.lower() if who.lower() in ("left", "right", "opponent") else who
            else:
                entry = {"text": _decode(line)}
        if stage:
            entry = dict(stage, **entry)
            stage = {}
        out.append(entry["text"] if list(entry) == ["text"] else entry)
    if not out:
        return None
    if len(out) == 1 and isinstance(out[0], str):
        return out[0]
    return out


# --- decks ------------------------------------------------------------------------------

DECK_LINE_RE = re.compile(r"^(.*?)(?:\s*[x×]\s*(\d+))?$", re.I)


def deck_text(value) -> str:
    """A floor's deck as the tab shows it: "Card x3" a line."""
    if isinstance(value, dict):
        return "\n".join(f"{card} x{copies}" if copies != 1 else str(card) for card, copies in value.items())
    if isinstance(value, list):
        counted = {}
        for card in value:
            counted[card] = counted.get(card, 0) + 1
        return deck_text(counted)
    return ""


def deck_value(text: str):
    """The tab's lines as {card: copies} (cards in the order written), or
    None for no deck."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        found = DECK_LINE_RE.match(line)
        card, copies = found.group(1).strip(), int(found.group(2) or 1)
        key = int(card) if card.isdigit() else card
        out[key] = out.get(key, 0) + copies
    return out or None


def deck_count(value) -> int:
    if isinstance(value, dict):
        return sum(_number(copies) or 0 for copies in value.values())
    if isinstance(value, list):
        return len(value)
    return 0


def names_text(value) -> str:
    """One name or a list of them, as "a, b"."""
    if value is None:
        return ""
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(item) for item in items)


def names_value(text: str):
    """"a, b" as a list (ids as numbers), one alone, or None."""
    items = [part.strip() for part in text.split(",") if part.strip()]
    items = [int(item) if item.isdigit() else item for item in items]
    if not items:
        return None
    return items[0] if len(items) == 1 else items


# --- the tower-only duelists --------------------------------------------------------------

def tower_only(project) -> list:
    """The mod's added duelists marked "tower_only", by key."""
    from . import roster
    return [e.key for e in roster.copies(project) if e.extra.get("tower_only") is True]


def set_tower_only(project, key: str, on: bool) -> bool:
    """Mark or unmark an added duelist; True when that changed it."""
    from . import roster
    e = roster.find(project, key)
    if e is None or e.replace or bool(e.extra.get("tower_only")) == on:
        return False
    if on:
        e.extra["tower_only"] = True
    else:
        e.extra.pop("tower_only", None)
    return True


# --- checks ---------------------------------------------------------------------------------

def check(tower, duelist_named, card_named) -> list:
    """What the game would note of a "tower" (tower_config.c): [(level,
    where, message)]. An error is something it leaves out (a floor, a deck,
    the whole tower); a warning what it reads otherwise than meant.
    duelist_named(text) is a duelist or None, card_named(text) a card or 0."""
    out = []
    if tower is None:
        return out

    def add(level, where, message):
        out.append((level, where, message))

    if not isinstance(tower, dict):
        add("error", "tower", "is an object ({\"floors\": [...]}); the game has no tower")
        return out
    for key in tower:
        if key not in TOWER_KEYS:
            add("warning", "tower", f"unknown key \"{key}\"")
    if not isinstance(tower.get("label", ""), str) or len(str(tower.get("label", ""))) > LABEL_MAX:
        add("warning", "tower.label", f"is text of at most {LABEL_MAX} letters")
    if len(str(tower.get("name", ""))) > NAME_MAX:
        add("warning", "tower.name", f"is at most {NAME_MAX} bytes; the rest is left out")
    music = tower.get("music")
    if music is not None:
        number = _number(music)
        if isinstance(music, str):
            try:
                number = int(music, 0)
            except ValueError:
                number = None
        if number is None or not 0 <= number <= 0xFFF:
            add("warning", "tower.music", "is a song id, 0x000 to 0xFFF; the Free Duel screen's is played")
    unlock = tower.get("unlock")
    if isinstance(unlock, str):
        if unlock not in ("always", "after_ending"):
            add("error", "tower.unlock", "is \"always\", \"after_ending\" or an object of conditions; "
                                         "the tower stays locked")
    elif isinstance(unlock, dict):
        for key in unlock:
            if key not in UNLOCK_KEYS:
                add("warning", "tower.unlock", f"unknown key \"{key}\"")
        if "after_ending" in unlock and not isinstance(unlock["after_ending"], bool):
            add("error", "tower.unlock.after_ending", "is true or false, without quotes; the game keeps the tower locked")
        for key, high in (("wins", 65535), ("copies", 250), ("story", 0x7FF)):
            if key in unlock and (_number(unlock[key]) is None or not 0 <= _number(unlock[key]) <= high):
                add("error", f"tower.unlock.{key}", f"is 0 to {high}; the tower stays locked")
        if "beat" in unlock and duelist_named(unlock["beat"]) is None:
            add("warning", "tower.unlock.beat", f"names no duelist ({unlock['beat']!r}); the tower stays locked")
        if "card" in unlock and not card_named(unlock["card"]):
            add("warning", "tower.unlock.card", f"names no card ({unlock['card']!r}); the tower stays locked")
    elif unlock is not None:
        add("error", "tower.unlock", "is \"always\", \"after_ending\" or an object of conditions; the tower stays locked")
    if tower.get("on_lose") not in (None, "checkpoint", "restart"):
        add("warning", "tower.on_lose", "is \"checkpoint\" or \"restart\"; checkpoint it is")
    if tower.get("on_leave") is not None and str(tower["on_leave"]).lower() not in ON_LEAVE:
        add("warning", "tower.on_leave", "is \"resume\", \"checkpoint\" or \"restart\"; resume it is")
    drops = tower.get("drops")
    if drops is not None and str(drops).lower() != "player" and \
            (_number(drops) is None or not 1 <= _number(drops) <= DROPS_MAX):
        add("warning", "tower.drops", f"is 1 to {DROPS_MAX} cards a won duel, or \"player\"; {DROPS_DEFAULT} it is")
    for key in ("save_states", "cheats"):
        if key in tower and not isinstance(tower[key], bool):
            add("warning", f"tower.{key}", "is true or false, without quotes; left as if not written")
    if "scene" in tower:
        _check_scene(tower["scene"], "tower", add)
    if "dim" in tower and not isinstance(tower["dim"], bool):
        add("warning", "tower.dim", "is true or false, without quotes")
    for key in ("intro", "ending", "lose"):
        _check_story(tower.get(key), f"tower.{key}", duelist_named, add)
    pictures = set()
    stories = [tower.get(key) for key in ("intro", "ending", "lose")]
    stories += [f.get(key) for f in tower.get("floors") or [] if isinstance(f, dict) for key in ("before", "after")]
    if isinstance(tower.get("scene"), str) and _is_png(tower["scene"]):
        pictures.add(("scene", tower["scene"]))
    for story in stories:
        scenes, characters = story_pictures(story)
        pictures |= {("scene", p) for p in scenes} | {("character",) + c for c in characters}
    if len(pictures) > ARTS:
        add("warning", "tower", f"a tower has at most {ARTS} PNGs of its own; the rest are left out")
    floors = tower.get("floors")
    if not isinstance(floors, list) or not floors:
        add("error", "tower.floors", "is a list of at least one floor; the game has no tower")
        return out
    if len(floors) > TOWER_MAX_FLOORS:
        add("warning", "tower.floors", f"at most {TOWER_MAX_FLOORS} floors; the rest are left out")
    fought = 0
    for index, floor in enumerate(floors):
        if _check_floor(floor, f"tower.floors[{index}]", duelist_named, card_named, add):
            fought += 1
    if not fought:
        add("error", "tower.floors", "no floor can be fought; the game has no tower")
    return out


def _check_scene(value, where, add):
    number = scene_number(value)
    if number is None:
        add("warning", f"{where}.scene", "is a scene's name (\"torch corridor\"), its number (0-41, 100-141, "
                                         "200-212) or a PNG of the mod's; the line keeps the scene before it")
    elif isinstance(number, str) and not _png_inside(number):
        add("warning", f"{where}.scene", f"{number} is not a path inside the mod; the line keeps the scene before it")


def _check_cast(value, where, duelist_named, add):
    cast = _cast(value)
    if cast == "none":
        return
    if not isinstance(cast, dict):
        add("warning", where, "is none, a character's number (1-64), a duelist, a PNG or an object of those")
        return
    for key in cast:
        if key not in CAST_KEYS:
            add("warning", where, f"unknown key \"{key}\"")
    if "expression" in cast and (_number(cast["expression"]) is None or not 0 <= _number(cast["expression"]) <= 3):
        add("warning", f"{where}.expression", "is 0 to 3")
    if "image" in cast:
        image = cast["image"]
        if not isinstance(image, str) or not image.lower().endswith(".png"):
            add("warning", f"{where}.image", "is a PNG of the mod's; the side stays empty")
        elif not _png_inside(image):
            add("warning", f"{where}.image", f"{image} is not a path inside the mod; the side stays empty")
        if "duelist" in cast and str(cast["duelist"]).lower() != "opponent" and duelist_named(cast["duelist"]) is None:
            add("warning", f"{where}.duelist", f"names no duelist ({cast['duelist']!r})")
        return
    if cast.get("flip"):
        add("warning", f"{where}.flip", "turns a PNG of the mod's, not a character of the campaign's")
    if "character" in cast:
        number = _number(cast["character"])
        if number is None or not 1 <= number <= CHARACTERS or number in EMPTY_CHARACTERS:
            add("warning", f"{where}.character", "is one of the campaign's, 1 to 64 (5, 11, 39, 40 and 41 are "
                                                 "empty); the side stays empty")
    elif "duelist" in cast:
        if str(cast["duelist"]).lower() != "opponent" and duelist_named(cast["duelist"]) is None:
            add("warning", f"{where}.duelist", f"names no duelist ({cast['duelist']!r}); the side stays empty")


def _check_stage(item, where, duelist_named, add):
    if "scene" in item:
        _check_scene(item["scene"], where, add)
    if "characters" in item:
        characters = item["characters"]
        if not isinstance(characters, dict):
            add("warning", f"{where}.characters", "is {\"left\": ..., \"right\": ...}")
        else:
            for side, value in characters.items():
                if side not in SIDES:
                    add("warning", f"{where}.characters", f"unknown key \"{side}\"")
                else:
                    _check_cast(value, f"{where}.characters.{side}", duelist_named, add)


def story_pictures(value) -> tuple:
    """The PNGs a story names: its scenes', and its characters' (a set of
    (path, flip) each, as tower_config.c counts them)."""
    scenes, characters = set(), set()
    for item in canon_story(value) or []:
        scene = item.get("scene")
        if isinstance(scene, str):
            scenes.add(scene)
        for cast in (item.get("characters") or {}).values() if isinstance(item.get("characters"), dict) else ():
            if isinstance(cast, dict) and isinstance(cast.get("image"), str):
                characters.add((cast["image"], bool(cast.get("flip"))))
    return scenes, characters


def _check_story(value, where, duelist_named, add, floor=False):
    if value is None:
        return
    scenes, characters = story_pictures(value)
    if len(characters) > STORY_PICTURES:
        add("warning", where, f"a story shows at most {STORY_PICTURES} characters of the mod's; the rest are left "
                              "out")
    if not floor:
        for item in canon_story(value) or []:
            sides = item.get("characters") if isinstance(item.get("characters"), dict) else {}
            if any(isinstance(c, dict) and str(c.get("duelist", "")).lower() == "opponent" for c in sides.values()) \
                    or str(item.get("speaker", "")).lower() == "opponent":
                add("warning", where, "\"opponent\" is a floor's: this story has none (its side stays empty)")
                break
    items = value
    if isinstance(value, dict) and "lines" in value:
        for key in value:
            if key not in STORY_KEYS:
                add("warning", where, f"unknown key \"{key}\"")
        _check_stage(value, where, duelist_named, add)
        items = value["lines"]
    items = items if isinstance(items, list) else [items]
    letters = 0
    for index, item in enumerate(items):
        at = f"{where}[{index}]" if isinstance(value, list) or isinstance(value, dict) and "lines" in value else where
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            for key in item:
                if key not in LINE_KEYS:
                    add("warning", at, f"unknown key \"{key}\"")
            text = item.get("text")
            speaker = item.get("speaker")
            if not (speaker in (None, "") or (isinstance(speaker, str) and
                                             speaker.lower() in ("none", "opponent", "left", "right"))) \
                    and duelist_named(speaker) is None:
                add("warning", at, f"\"speaker\" names no duelist ({speaker!r})")
            if "portrait" in item:
                face = item["portrait"]
                if not (isinstance(face, bool) or face is None or
                        (isinstance(face, str) and face.lower() in ("speaker", "none")) or
                        (_number(face) is not None and 0 <= _number(face) < CAMPAIGN_PORTRAITS)):
                    add("warning", at, f"\"portrait\" is one of the campaign's portraits (0 to "
                                       f"{CAMPAIGN_PORTRAITS - 1}), \"speaker\" or \"none\"")
            _check_stage(item, at, duelist_named, add)
            pan = item.get("pan")
            if pan is not None:
                if not isinstance(pan, dict):
                    add("warning", f"{at}.pan", "is {\"x\": ..., \"y\": ..., \"frames\": ...}")
                else:
                    for key in pan:
                        if key not in PAN_KEYS:
                            add("warning", f"{at}.pan", f"unknown key \"{key}\"")
                    for key, low, high in (("x", 0, 576), ("y", 0, 96), ("frames", 1, 3600)):
                        if key in pan and (_number(pan[key]) is None or not low <= _number(pan[key]) <= high):
                            add("warning", f"{at}.pan.{key}", f"is {low} to {high}")
            if not isinstance(text, str):
                add("error", at, "a line is text, or {\"text\": ..., \"speaker\": ...}; left out")
                continue
        else:
            add("error", at, "a line is text, or {\"text\": ..., \"speaker\": ...}; left out")
            continue
        if not text:
            if isinstance(item, dict) and any(key in item for key in ("scene", "characters", "pan")):
                add("warning", at, "a line without words is left out, and its stage with it")
            continue
        if len(text.encode("utf-8")) > LINE_MAX:
            add("warning", at, f"a line is at most {LINE_MAX} bytes; the rest is left out")
        letters += min(len(text.encode("utf-8")), LINE_MAX) + LINE_CODES
        if letters > STORY_LETTERS:
            add("warning", at, f"a story is at most about {STORY_LETTERS} letters (one box tells it); "
                               "this line and the rest are left out")
            break


def _check_floor(floor, where, duelist_named, card_named, add) -> bool:
    """1 when the game keeps the floor."""
    if not isinstance(floor, dict):
        add("error", where, "a floor is an object ({\"duelist\": ...}); left out")
        return False
    for key in floor:
        if key not in FLOOR_KEYS:
            add("warning", where, f"unknown key \"{key}\"")
    if "duelist" not in floor:
        add("error", where, "a floor needs a \"duelist\"; left out")
        return False
    if duelist_named(floor["duelist"]) is None:
        add("error", where, f"no duelist {floor['duelist']!r}; the floor is left out")
        return False
    if "field" in floor and terrain_of(floor["field"]) is None:
        add("warning", f"{where}.field", "is none, Forest, Wasteland, Mountain, Meadow, Sea or Dark (1-6)")
    if "unlock_opponent" in floor and not isinstance(floor["unlock_opponent"], bool):
        add("warning", f"{where}.unlock_opponent", "is true or false, without quotes; left as if not written")
    for key in ("no_fusions", "no_equips", "checkpoint"):
        if key in floor and not isinstance(floor[key], bool):
            add("warning", f"{where}.{key}", "is true or false, without quotes")
    lp = floor.get("life_points")
    if lp is not None:
        values = [lp] if not isinstance(lp, dict) else [lp[side] for side in ("player", "opponent") if side in lp]
        if isinstance(lp, dict) and any(side not in ("player", "opponent") for side in lp):
            add("warning", f"{where}.life_points", "is {\"player\": ..., \"opponent\": ...}")
        if any(_number(value) is None or not 1 <= _number(value) <= 65535 for value in values):
            add("warning", f"{where}.life_points", "is 1 to 65535")
    deck = floor.get("deck")
    if deck is not None:
        if not isinstance(deck, (dict, list)):
            add("error", f"{where}.deck", "is {card: copies} or a list of forty cards; the opponent's own is dealt")
        else:
            cards = deck if isinstance(deck, list) else list(deck)
            missing = [card for card in cards if not card_named(card)]
            if missing:
                add("error", f"{where}.deck", f"names no card {missing[0]!r}; the opponent's own is dealt")
            elif deck_count(deck) != DECK:
                add("error", f"{where}.deck", f"is {DECK} cards, and this one has {deck_count(deck)}; the "
                                              "opponent's own is dealt")
    reward = floor.get("reward")
    if reward is not None:
        if not isinstance(reward, dict):
            add("warning", f"{where}.reward", "is an object ({\"cards\": [...], \"starchips\": 100})")
        else:
            for key in reward:
                if key not in REWARD_KEYS:
                    add("warning", f"{where}.reward", f"unknown key \"{key}\"")
            cards = []
            for key in ("card", "cards"):
                value = reward.get(key)
                cards += value if isinstance(value, list) else [] if value is None else [value]
            for card in cards:
                if not card_named(card):
                    add("warning", f"{where}.reward", f"names no card {card!r}; left out")
            if len(cards) > REWARD_CARDS:
                add("warning", f"{where}.reward", f"at most {REWARD_CARDS} cards; the rest are left out")
            chips = reward.get("starchips")
            if chips is not None and (_number(chips) is None or not 0 <= _number(chips) <= 999999):
                add("warning", f"{where}.reward.starchips", "is 0 to 999999")
            duelists = reward.get("unlock_duelist")
            duelists = duelists if isinstance(duelists, list) else [] if duelists is None else [duelists]
            for name in duelists:
                if duelist_named(name) is None:
                    add("warning", f"{where}.reward.unlock_duelist", f"names no duelist {name!r}; left out")
    _check_story(floor.get("before"), f"{where}.before", duelist_named, add, floor=True)
    _check_story(floor.get("after"), f"{where}.after", duelist_named, add, floor=True)
    return True


def new_floor(duelist="1") -> dict:
    return {"duelist": int(duelist) if str(duelist).isdigit() else duelist}


def copy(value):
    return _copy.deepcopy(value)


# --- the guide and the example (the Tower tab's "How to build a tower") ------------------

GUIDE = (
    ("1. Turn it on", "Tick \"This mod has a tower\". The title's second menu gets a button for it (its label "
     "below; TOWER without one). \"Start from an example\" fills in a small tower to change."),
    ("2. The tower", "Name it, give the button its words and pick when it opens: always, after the save has seen "
     "the game's ending, or on conditions (a duelist beaten, wins, a story flag, a card held)."),
    ("3. Floors", "Add a floor for each duel, bottom first. Each has an opponent, a field, LP for either side, "
     "rules (no fusions, no equips) and, if you like, the opponent's own forty cards. A checkpoint floor is "
     "where a lost duel sends the player back to, and the tower offers a save there."),
    ("4. Rewards and unlocks", "The first win of a floor gives its reward cards and starchips. Tick \"Unlock "
     "this opponent in Free Duel when beaten\" to let the opponent onto the Free Duel grid, and pick more "
     "duelists to unlock in the list beside it. A duelist the mod adds that should be the tower's alone is "
     "ticked in \"The tower's own duelists\": hidden in Free Duel until the tower lets it out."),
    ("5. Stories", "Write what is said before the first climb, before and after each floor, at the top and "
     "after a loss: a line of text a page. The Stage box puts a scene behind them and the campaign's "
     "characters (or your own PNGs) on top: click a story, then a button."),
    ("6. The rules of the run", "On leaving: \"resume\" comes back where the player was, \"checkpoint\" or "
     "\"restart\" take the climb back (no save keeps a floor past it). A loss goes back to the checkpoint or "
     "to floor 1. Cards a won duel gives: 1 by default, whatever the player's Card drops setting says; "
     "\"player\" follows it. Untick save states or cheats to keep them out of the tower."),
    ("7. Try it", "Save the mod, turn it on in the game's Mods window and climb. The status line above lists "
     "anything the game would read otherwise than you meant."),
)


def example_tower() -> dict:
    """A small tower that works as it is, for "Start from an example"."""
    return {
        "name": "The Example Tower",
        "label": "TOWER",
        "unlock": "always",
        "on_lose": "checkpoint",
        "intro": {"scene": "seal shrine", "characters": {"left": "Simon Muran"},
                  "lines": [{"text": "Three floors stand between you and the top, my prince.", "speaker": "left"},
                            {"text": "Win them all.", "speaker": "left"}]},
        "ending": {"scene": "throne room", "lines": ["The tower is yours."]},
        "lose": "Down you go. Try again.",
        "floors": [
            {"duelist": "Simon Muran", "checkpoint": True, "life_points": {"opponent": 4000},
             "reward": {"cards": ["Kuriboh"], "starchips": 25},
             "before": "Show me what you have learned.", "after": "Well fought. Climb on."},
            {"duelist": "Teana", "field": "Forest", "no_fusions": True, "unlock_opponent": True,
             "before": "Nobody fuses on this floor."},
            {"duelist": "Seto", "no_equips": True, "reward": {"starchips": 100},
             "before": "No equips here. Only your monsters."},
        ],
    }
