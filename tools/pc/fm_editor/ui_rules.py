"""What the game accepts in a mod's "ui" key, the title's "images" and the
menus' sizes (src/pc/platform/ui_config.c, title_config.c), checked before
saving as the Mods window would note it."""
from __future__ import annotations

from pathlib import PurePosixPath

ELEMENTS = ("lp_opponent", "lp_player", "field", "card_bar", "hand_cursor", "field_cursor")
KEYS = ("x", "y", "scale", "tint", "hide", "image", "width", "height", "label", "digits")
# ui_config.c `takes`: which way each moves. The game slides the LP halves
# and the FIELD box off the screen sideways (for a battle, the duel's end,
# Exodia), so they move up and down only and slide with the game's; the
# card bar stays where the game has it, its size too; only the LP halves
# have digits and words.
MOVES = {"lp_opponent": "y", "lp_player": "y", "field": "y", "card_bar": "", "hand_cursor": "xy",
         "field_cursor": "xy"}
SIZED = ("lp_opponent", "lp_player", "field", "hand_cursor", "field_cursor")
LABELLED = ("lp_opponent", "lp_player")
SCALE_MIN, SCALE_MAX = 25, 400
RANGES = {"x": (-400, 400), "y": (-300, 300), "scale": (SCALE_MIN, SCALE_MAX), "width": (0, 320), "height": (0, 240)}
# ui_config.c `slide_reach`, `own_reach`, `own_size`: how far a sliding one may
# reach from its middle and still be off the screen where the game slides it
# (the panel's middle at 384, 64 right of the screen; the box's at -36), how
# far the game's own pieces reach (the panel's half 32 and 8 for a fifth LP
# digit; the box 28), and each one's size.
SLIDE_REACH = {"lp_opponent": 64, "lp_player": 64, "field": 36}
OWN_REACH = {"lp_opponent": 40, "lp_player": 40, "field": 28}
OWN_SIZE = {"lp_opponent": (64, 20), "lp_player": (64, 20), "field": (56, 24), "card_bar": (320, 72),
            "hand_cursor": (16, 16), "field_cursor": (64, 64)}


def _scaled(d: int, scale: int) -> int:
    t = d * scale
    return (t + 50) // 100 if t >= 0 else -((-t + 50) // 100)


def _int(value, default=0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def reach(name: str, scale: int, picture: bool = False, width: int = 0, height: int = 0) -> int:
    """UiConfig_Reach: how far the element at `scale` reaches from its middle."""
    if picture:
        w, h = OWN_SIZE[name]
        width = width or (w * height // h if height else w)
        return _scaled(width - width // 2, scale)
    return _scaled(OWN_REACH.get(name, 0), scale)


def scale_max(name: str, picture: bool = False, width: int = 0, height: int = 0) -> int:
    """UiConfig_ScaleMax: the most size at which it still leaves the screen
    with the game's (SCALE_MAX for one that does not slide, 100 for the card
    bar)."""
    if name not in SIZED:
        return 100
    if name not in SLIDE_REACH:
        return SCALE_MAX
    scale = SCALE_MAX
    while scale > SCALE_MIN and reach(name, scale, picture, width, height) > SLIDE_REACH[name]:
        scale -= 1
    return scale


def element_scale_max(name: str, element: dict) -> int:
    """scale_max for what the element has: a picture of its own and its size."""
    picture = isinstance(element.get("image"), str) and bool(element.get("image"))
    return scale_max(name, picture, _int(element.get("width")) if picture else 0,
                     _int(element.get("height")) if picture else 0)
LABEL_MAX = 15
PICTURES_MAX = 8

# The card bar's parts (ui_config.h UI_PART_*, ui_config.c part_home): the
# words, numbers and icons the game writes over the bar as one text, each
# where the game puts it in that text's box (16, 210 under the hand; x, y,
# w, h): the name's 8 x 12 letters from 0 (drawn 2 down), at most 28; the
# sword and four ATK digits from 195, the shield and DEF a row down; the
# type's icon; the stars' (the field's one at 263); a magic card's word.
PARTS = ("name", "atk", "def", "type", "stars", "kind")
PART_KEYS = ("x", "y", "tint", "hide", "spacing")
NAME_LETTERS, LETTER = 28, 8
PART_HOME = {"name": (0, 2, NAME_LETTERS * LETTER, 12), "atk": (195, 0, 40, 8), "def": (195, 8, 40, 8),
             "type": (237, 0, 16, 16), "stars": (255, 0, 34, 16), "kind": (255, 0, 32, 16)}
# Where a part stays, in the box's own pixels: the bar's dark panel, the same
# under the hand and on the bar's higher look (UI_BAR_*; the letters' cells
# are dark, and would show off it); how far the name's letters spread
# (UI_SPACING_*: by 2 the longest name just fits).
BAR_BOX = (16, 210)
BAR_REGION = (-2, 290, -2, 18)
SPACING_MIN, SPACING_MAX = -3, 2


def part_home(part: str, spacing: int = 0):
    """UiConfig_PartHome: (x, y, w, h) in the bar's text box, the name at its
    longest and spread by `spacing`."""
    x, y, w, h = PART_HOME[part]
    return x, y, w + ((NAME_LETTERS - 1) * spacing if part == "name" else 0), h


def part_range(part: str, spacing: int = 0):
    """UiConfig_PartRange: (x0, x1, y0, y1), how far it moves and stays on
    the bar."""
    x, y, w, h = part_home(part, spacing)
    left, right, top, bottom = BAR_REGION
    return left - x, right - (x + w), top - y, bottom - (y + h)


def part_spacing(element: dict) -> int:
    value = _int(element.get("spacing"))
    return value if SPACING_MIN <= value <= SPACING_MAX else 0


def part_offset(part: str, element: dict):
    """Where the game moves a part (ui_config.c read_part): its x and y (0
    for one out of -400..400, -300..300), brought onto the bar."""
    spacing = part_spacing(element) if part == "name" else 0
    x0, x1, y0, y1 = part_range(part, spacing)
    x, y = _int(element.get("x")), _int(element.get("y"))
    x = x if -400 <= x <= 400 else 0
    y = y if -300 <= y <= 300 else 0
    return max(x0, min(x1, x)), max(y0, min(y1, y))


def bar_parts(card_bar) -> dict:
    """The card bar's parts a mod's "card_bar" has (objects only)."""
    if not isinstance(card_bar, dict):
        return {}
    return {name: card_bar[name] for name in PARTS if isinstance(card_bar.get(name), dict)}


def _color(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 0xFFFFFF
    if isinstance(value, str):
        text = value[1:] if value.startswith("#") else value
        return len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text)
    return False


def _contained(name: str) -> bool:
    """paths.c Paths_Contained: relative, inside the mod."""
    return bool(name) and not name.startswith("/") and ".." not in PurePosixPath(name).parts and "\\" not in name


def _check_part(where: str, part: str, value) -> list:
    """read_part's notes for one of the card bar's parts."""
    where = f"{where}.{part}"
    if not isinstance(value, dict):
        return [("warning", where, "an object of keys")]
    out = []
    for key, member in value.items():
        if key not in PART_KEYS:
            out.append(("warning", where, f"unknown key \"{key}\""))
        elif key == "spacing" and part != "name":
            out.append(("warning", where, "has no \"spacing\" (the name's letters have)"))
        elif key == "spacing" and (isinstance(member, bool) or not isinstance(member, int) or
                                   not SPACING_MIN <= member <= SPACING_MAX):
            out.append(("warning", where, f"\"spacing\" is a whole number from {SPACING_MIN} to {SPACING_MAX}"))
        elif key in ("x", "y") and (isinstance(member, bool) or not isinstance(member, int) or
                                    not RANGES[key][0] <= member <= RANGES[key][1]):
            out.append(("warning", where, f"\"{key}\" is a whole number from {RANGES[key][0]} to {RANGES[key][1]}"))
        elif key == "tint" and not _color(member):
            out.append(("warning", where, "\"tint\" is a color, \"#RRGGBB\""))
        elif key == "hide" and not isinstance(member, bool):
            out.append(("warning", where, "\"hide\" is true or false"))
    x, y = _int(value.get("x")), _int(value.get("y"))
    if (x, y) != part_offset(part, value) and -400 <= x <= 400 and -300 <= y <= 300:
        out.append(("warning", where, "would leave the bar; moved by %d, %d instead" % part_offset(part, value)))
    return out


def check(project, has_file) -> list:
    """(level, where, message) for each thing the game would note;
    has_file(name) says whether the mod holds a file."""
    out = []
    ui = project.other.get("ui")
    if ui is not None:
        if not isinstance(ui, dict):
            out.append(("warning", "ui", "\"ui\" is an object"))
            ui = {}
        for key in ui:
            if key != "duel":
                out.append(("warning", f"ui.{key}", "unknown key (the game reads \"duel\")"))
        duel = ui.get("duel", {})
        if not isinstance(duel, dict):
            out.append(("warning", "ui.duel", "\"duel\" is an object of pictures by name"))
            duel = {}
        for name, element in duel.items():
            where = f"ui.duel.{name}"
            if name not in ELEMENTS:
                out.append(("warning", where, f"no duel picture \"{name}\" ({', '.join(ELEMENTS)})"))
                continue
            if not isinstance(element, dict):
                out.append(("warning", where, "an object of keys"))
                continue
            for key, value in element.items():
                if name == "card_bar" and key in PARTS:
                    out += _check_part(where, key, value)
                elif key not in KEYS:
                    out.append(("warning", where, f"unknown key \"{key}\""))
                elif key in ("x", "y", "scale") and not MOVES[name]:
                    out.append(("warning", where, f"the card bar stays where the game has it (the hand's cards slide "
                                                  f"with it); \"{key}\" is left out (its parts move)"))
                elif key == "x" and "x" not in MOVES[name]:
                    out.append(("warning", where, "the game slides it off the screen sideways, so it keeps its "
                                                  "place across; \"x\" is left out (\"y\" moves it)"))
                elif key in ("label", "digits") and name not in LABELLED:
                    out.append(("warning", where, f"has no \"{key}\""))
                elif key in RANGES and (isinstance(value, bool) or not isinstance(value, int) or
                                        not RANGES[key][0] <= value <= RANGES[key][1]):
                    out.append(("warning", where, f"\"{key}\" is a whole number from {RANGES[key][0]} to "
                                                  f"{RANGES[key][1]}"))
                elif key in ("tint", "digits") and not _color(value):
                    out.append(("warning", where, f"\"{key}\" is a color, \"#RRGGBB\""))
                elif key == "label" and (not isinstance(value, str) or len(value) > LABEL_MAX):
                    out.append(("warning", where, f"\"label\" is at most {LABEL_MAX} letters"))
                elif key == "hide" and not isinstance(value, bool):
                    out.append(("warning", where, "\"hide\" is true or false"))
                elif key == "image" and value:
                    if not isinstance(value, str) or not _contained(value):
                        out.append(("warning", where, "\"image\" is a PNG inside the mod"))
                    elif not has_file(value):
                        out.append(("warning", where, f"{value} is not in the mod"))
            scale = element.get("scale", 100)
            if name in SLIDE_REACH and isinstance(scale, int) and not isinstance(scale, bool) and \
                    SCALE_MIN <= scale <= SCALE_MAX:
                most = element_scale_max(name, element)
                picture = isinstance(element.get("image"), str) and bool(element.get("image"))
                if scale > most:
                    out.append(("warning", where, f"at {scale}% it would not leave the screen with the game's; "
                                                  f"drawn at {most}%"))
                elif picture and reach(name, scale, True, _int(element.get("width")),
                                       _int(element.get("height"))) > SLIDE_REACH[name]:
                    out.append(("warning", where, "\"image\" is too wide to leave the screen with the game's; "
                                                  "it is drawn narrower"))
    title = project.other.get("title")
    # The menus' sizes (title_config.c scale_member): a whole number from 25 to 400.
    menu = project.other.get("menu")
    sized = []
    if isinstance(menu, dict):
        sized.append(("menu", menu))
        for where, holder in (("menu.entries", menu.get("entries")),):
            if isinstance(holder, dict):
                sized += [(f"{where}.{name}", item) for name, item in holder.items()]
        buttons = menu.get("buttons")
        if isinstance(buttons, list):
            sized += [(f"menu.buttons.{b.get('id')}", b) for b in buttons if isinstance(b, dict)]
    if isinstance(title, dict) and isinstance(title.get("entries"), dict):
        sized += [(f"title.entries.{name}", item) for name, item in title["entries"].items()]
    for where, holder in sized:
        value = holder.get("scale") if isinstance(holder, dict) else None
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or
                                  not SCALE_MIN <= value <= SCALE_MAX):
            out.append(("warning", where, f"\"scale\" is a whole number from {SCALE_MIN} to {SCALE_MAX} (percent); "
                                          "the game leaves it out"))
    images = title.get("images") if isinstance(title, dict) else None
    if images is not None:
        if not isinstance(images, list):
            out.append(("warning", "title.images", "a list of pictures"))
            images = []
        if len(images) > PICTURES_MAX:
            out.append(("warning", "title.images", f"at most {PICTURES_MAX} pictures; the rest are left out"))
        for i, entry in enumerate(images):
            name = entry.get("image") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not name:
                out.append(("warning", f"title.images[{i}]", "a picture without an \"image\""))
            elif not _contained(name):
                out.append(("warning", f"title.images[{i}]", "\"image\" is a PNG inside the mod"))
            elif not has_file(name):
                out.append(("warning", f"title.images[{i}]", f"{name} is not in the mod"))
    return out
