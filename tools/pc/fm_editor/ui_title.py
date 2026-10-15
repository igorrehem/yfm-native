"""The UI tab's Title screen and Menus pages (notes/modding.md "The title
screen", "The title's menus"): the title drawn as the game draws it, from
the disc's own pictures (ui_assets.TitleArt) and the mod's "title" and
"menu" over them, as title_config.c reads them and title_screen.c and
title_menu.c lay them out.

Title screen: the background (the game's wall, a color, a picture of the
mod's own), the logo, the copyright line and PUSH START BUTTON (moved,
colored, hidden, or a picture instead), pictures the mod adds and lines of
words. Menus: both menus' buttons in their order -- the game's entries and
the mod's own -- each with its words or picture, what it does and where it
stands, and the menus' own background."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import pngio, ui_assets as ua
from .ui_tab import (WARN, ColorButton, as_int, color_text, ensure, import_image, mod_image, page_layout, section,
                     set_member, sized)
from .widgets import px

LAYER_NAMES = ("logo", "copyright", "prompt")
LAYER_TITLES = {"logo": "Logo", "copyright": "Copyright line", "prompt": "PUSH START BUTTON"}
ENTRY_NAMES = ["new_game", "load", "duel", "trade", "options", "campaign", "free_duel", "build_deck", "library",
               "password", "save"]
ENTRY_TITLES = ["NEW GAME", "LOAD", "2P DUEL", "TRADE", "OPTION", "CAMPAIGN", "FREE DUEL", "BUILD DECK", "LIBRARY",
                "PASSWORD", "SAVE"]
ACTIONS = ENTRY_NAMES + ["back", "notice", "quit", "debug_menu", "event", "none"]
ACTION_TITLES = {"back": "Back", "notice": "Show a notice", "quit": "Quit the game", "debug_menu": "Debug menu",
                 "event": "Code mod event", "none": "Nothing (a buzz)"}
SHOW = ["always", "press_start", "menu"]
SHOW_TITLES = {"always": "Always", "press_start": "With PUSH START", "menu": "With a menu up"}
# title_config.c: the entries 32 apart around y 114 (first menu) and 122 (second),
# between y 16 and 204 (an entry's 28 rows, HALF either side, between 2 and 218).
SPACING, MIDDLES, TOP, MOST, HALF = 32, (114, 122), 16, 188, 14
MAX_PICTURES, MAX_LINES, MAX_BUTTONS = 8, 16, 16
LABEL_H, LABEL_PAD, LABEL_MIN, LABEL_MAX = 28, 14, 64, 240
# title_config.h: an item's "scale", in percent, about its middle.
SCALE_MIN, SCALE_MAX = 25, 400


def menu_of(item) -> int:
    return item.get("menu", 0)


def action_title(action: str) -> str:
    if action in ENTRY_NAMES:
        return ENTRY_TITLES[ENTRY_NAMES.index(action)].title()
    return ACTION_TITLES.get(action, action)


def allowed(action, menu: int) -> bool:
    """title_config.c allowed(): load, 2P duel and trade in the first menu,
    a loaded game's choices in the second, the rest in either."""
    if action is None or action in ACTION_TITLES or action in ("new_game", "options"):
        return True
    index = ENTRY_NAMES.index(action) if action in ENTRY_NAMES else -1
    return index < 5 if menu == 0 else index >= 5


def a_scale(value) -> bool:
    """A "scale" title_config.c takes: a whole number from 25 to 400."""
    return isinstance(value, int) and not isinstance(value, bool) and SCALE_MIN <= value <= SCALE_MAX


def cdiv(a: int, b: int) -> int:
    """a / b as C divides: toward 0."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def scaled(d: int, scale: int) -> int:
    """title_menu.c scaled(): d * scale / 100, rounded half away from 0."""
    t = d * scale
    return (t + 50) // 100 if t >= 0 else -((-t + 50) // 100)


def opaque(image: pngio.Image) -> tuple:
    """(x0, y0, x1, y1) of the picture's drawn texels (alpha above 0), its
    whole when it has none."""
    key = (image.width, image.height, hash(image.rgba))
    if key not in _opaque:
        if len(_opaque) > 400:
            _opaque.clear()
        alpha = image.rgba[3::4]
        rows = [y for y in range(image.height) if any(alpha[y * image.width:(y + 1) * image.width])]
        if not rows:
            _opaque[key] = (0, 0, image.width, image.height)
        else:
            columns = [x for x in range(image.width) if any(alpha[x::image.width])]
            _opaque[key] = (columns[0], rows[0], columns[-1] + 1, rows[-1] + 1)
    return _opaque[key]


_opaque = {}


def fit(width: int, height: int, max_w: int, max_h: int, want_w=0, want_h=0, guess_h=None):
    """title_images.c measure(): the size a picture is drawn at."""
    guess_h = guess_h or max_h
    if want_w and want_h:
        w, h = want_w, want_h
    elif want_w:
        w, h = want_w, height * want_w // max(1, width)
    elif want_h:
        w, h = width * want_h // max(1, height), want_h
    else:
        factor = 1
        while width // factor > max_w or height // factor > guess_h:
            factor += 1
        w, h = width // factor, height // factor
    if w > max_w:
        w, h = max_w, h * max_w // max(1, w)
    if h > max_h:
        w, h = w * max_h // max(1, h), max_h
    return max(2, (w + 1) & ~1), max(1, h)


class Scene:
    """What the mod's "title" and "menu" make of the title, as title_config.c
    reads them: the backgrounds, the pictures, the items and the menus'
    order and places."""

    def __init__(self, project):
        self.project = project
        self.title = section(project, "title")
        self.menu = section(project, "menu")
        self.mod_id = project.info.id or "mod"

    def background(self, menu_up: bool) -> dict:
        own = self.title.get("background") if isinstance(self.title.get("background"), dict) else {}
        out = {"picture": True, "shade": True, "tint": 0xFFFFFF, "color": None, "image": "", "dim": 128}
        for key, value in own.items():
            out[key] = value
        if menu_up:
            given = self.menu.get("background") if isinstance(self.menu.get("background"), dict) else {}
            for key, value in given.items():
                out[key] = value
        out["dim"] = max(0, min(128, as_int(out.get("dim"), 128)))
        return out

    def items(self) -> list:
        """Every item: the eleven entries, then the buttons, each a dict of
        its keys with "name", "own" (a button of this mod), "menu"."""
        entries = {}
        for source in (self.title.get("entries"), self.menu.get("entries")):
            if isinstance(source, dict):
                for name, value in source.items():
                    index = ENTRY_NAMES.index(name) if name in ENTRY_NAMES else \
                        int(name) if isinstance(name, str) and name.isdigit() and int(name) < 11 else -1
                    if index >= 0 and isinstance(value, dict):
                        entries.setdefault(index, {}).update(value)
        out = []
        for i, name in enumerate(ENTRY_NAMES):
            item = dict(entries.get(i, {}))
            item.update(name=name, index=i, menu=0 if i < 5 else 1, own=False, entry=True)
            out.append(item)
        buttons = self.menu.get("buttons")
        for button in buttons if isinstance(buttons, list) else []:
            if not isinstance(button, dict) or not isinstance(button.get("id"), str):
                continue
            item = dict(button)
            bid = button["id"]
            item.update(name=bid if ":" in bid else f"{self.mod_id}:{bid}", index=len(out), entry=False,
                        own=":" not in bid, menu=1 if button.get("menu") == "second" else 0)
            out.append(item)
        return out

    def order(self, menu: int) -> list:
        """The menu's items top to bottom (title_config.c arrange()), hidden
        ones included, as (item, shown)."""
        items = [i for i in self.items() if i["menu"] == menu]
        given = self.menu.get("order")
        names = given.get(("first", "second")[menu]) if isinstance(given, dict) else (given if menu == 0 else None)
        listed = []
        for name in names if isinstance(names, list) else []:
            if not isinstance(name, str):
                continue
            full = name if (name in ENTRY_NAMES or ":" in name) else f"{self.mod_id}:{name}"
            for item in items:
                if item["name"] == full and item not in listed:
                    listed.append(item)
        listed += [i for i in items if i not in listed]
        shown = [i for i in listed if i.get("hide") is not True]
        if not shown:
            shown = [i for i in listed if i["entry"]]
        return [(i, i in shown) for i in listed]

    def menu_scale(self) -> int:
        """The menu's "scale": every item's without its own (100)."""
        return self.menu["scale"] if a_scale(self.menu.get("scale")) else 100

    def scale(self, item) -> int:
        """An item's size in percent: its own "scale", else the menu's."""
        return item["scale"] if a_scale(item.get("scale")) else self.menu_scale()

    def places(self, menu: int) -> dict:
        """Each shown item's middle (x, y), as stack() puts them: `spacing`
        apart at 100, each taking room as its size."""
        shown = [i for i, on in self.order(menu) if on]
        spacing = as_int(self.menu.get("spacing"), as_int(self.title.get("spacing"), SPACING))
        count = len(shown)
        scales = [self.scale(i) for i in shown]
        reach = [0]
        for a, b in zip(scales, scales[1:]):
            reach.append(reach[-1] + a + b)
        # The ends: an entry's 28 rows between y 2 and 218, moved by the
        # first's and the last's size.
        top, most = TOP, MOST
        if count:
            top = TOP - HALF + (HALF * scales[0] + 50) // 100
            most = TOP + MOST + HALF - (HALF * scales[-1] + 50) // 100 - top
        if count > 1 and cdiv(spacing * reach[-1], 200) > most:
            spacing = cdiv(most * 200, reach[-1])
        total = cdiv(spacing * reach[-1], 200) if count > 1 else 0
        first = MIDDLES[menu] - cdiv(total, 2)
        first = max(first, top)
        if first + total > top + most:
            first = top + most - total
        out = {}
        for row, item in enumerate(shown):
            at = first + cdiv(spacing * reach[row], 200)
            y = as_int(item.get("y"), at) if "y" in item else at
            out[item["name"]] = (160 + as_int(item.get("x")), y)
        return out


def label_width(text: str) -> int:
    """menu_label.c's width for a label's frame at 100."""
    import tkinter.font as tkfont
    try:
        font = tkfont.Font(family="Times", size=-17, weight="bold")
        words = font.measure(text)
    except tk.TclError:
        words = 8 * len(text)
    w = max(LABEL_MIN, min(LABEL_MAX, words + 2 * LABEL_PAD))
    return (w + 1) & ~1


def label_button(text: str, selected: bool) -> pngio.Image:
    """menu_label.c's frame for a label, at the console's size, the words
    left to the canvas (drawn over it in Times)."""
    w = label_width(text)
    h = LABEL_H
    rgba = bytearray(w * h * 4)

    def fill(x0, y0, x1, y1, color):
        for y in range(y0, y1):
            for x in range(x0, x1):
                rgba[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes(color + (255,))
    if selected:
        fill(0, 0, w, h, (168, 16, 16))
        fill(1, 1, w - 1, h - 1, (232, 136, 0))
        fill(2, 2, w - 2, h - 2, (168, 16, 16))
        fill(3, 3, w - 3, h - 3, (40, 24, 24))
        for y, color in ((4, (104, 96, 200)), (5, (224, 224, 248)), (6, (48, 64, 184)), (h - 7, (104, 96, 200)),
                          (h - 6, (224, 224, 248)), (h - 5, (48, 64, 184))):
            fill(5, y, w - 5, y + 1, color)
    else:
        fill(0, 0, w, h, (16, 8, 16))
        fill(1, 1, w - 1, h - 1, (96, 96, 8))
        fill(2, 2, w - 2, h - 2, (40, 32, 32))
        fill(6, 5, w - 6, 6, (128, 120, 120))
        fill(6, h - 6, w - 6, h - 5, (128, 120, 120))
    return pngio.Image(w, h, bytes(rgba))


def item_look(scene: Scene, item: dict, selected: bool, title_art):
    """An item as the game draws it, at its size ("scale", about its
    middle): (picture, left, top, words) with left, top from its middle and
    words (text, color, size, shadow) for a label, drawn over it; None
    for an entry without the disc's pictures."""
    scale = scene.scale(item)
    tint = ua.parse_color(item.get("tint"))
    name = item.get("selected_image" if selected else "image")
    image = mod_image(scene.project, name) if name else None
    if selected and image is None and item.get("image"):
        image = mod_image(scene.project, item.get("image"))
        level = 255
    else:
        level = 255 if selected or item.get("selected_image") or not item.get("image") else 0x60 * 255 // 0x80
    if image is not None:
        # title_images.c: its size at 100 (measure()), then at its scale.
        w, h = fit(image.width, image.height, 256, 64, as_int(item.get("width")), as_int(item.get("height")),
                   guess_h=32)
        w, h = max(1, (w * scale + 50) // 100), max(1, (h * scale + 50) // 100)
        return ua.tint(sized(image, w, h), tint, level), -(w // 2), -(h // 2), None
    if isinstance(item.get("label"), str) and item["label"] or not item["entry"]:
        text = item.get("label") or item["name"].split(":", 1)[-1]
        frame = label_button(text, selected)
        w, h = max(1, (frame.width * scale + 50) // 100), max(1, (frame.height * scale + 50) // 100)
        level = 255 if selected else 0x60 * 255 // 0x80
        ink = "#e0f8d8" if selected else "#b0b0b0"
        return (ua.tint(sized(frame, w, h), tint, level), -(w // 2), -(h // 2),
                (text, ink, 17 * scale / 100, not selected))
    if not title_art.ok:
        return None
    if scale == 100:
        picture, dx, dy = title_art.entry(item["index"], selected)
        return ua.tint(picture, tint), dx, dy, None
    return (ua.tint(sized_entry(title_art, item["index"], selected, scale), tint),
            scaled(min(p[0] for p in ua.ENTRY_SPRITES[item["index"]][1 if selected else 0]), scale),
            scaled(min(p[1] for p in ua.ENTRY_SPRITES[item["index"]][1 if selected else 0]), scale), None)


def sized_entry(title_art, index: int, selected: bool, scale: int) -> pngio.Image:
    """An entry of the game's at `scale`, as title_menu.c draws it: each of
    its sprites scaled about the entry's middle, its edges rounded there."""
    parts = ua.ENTRY_SPRITES[index][1 if selected else 0]
    left = scaled(min(p[0] for p in parts), scale)
    top = scaled(min(p[1] for p in parts), scale)
    right = max(scaled(p[0] + p[2], scale) for p in parts)
    bottom = max(scaled(p[1] + p[3], scale) for p in parts)
    out = ua.blank(right - left, bottom - top)
    for dx, dy, w, h, u, v in parts:
        piece = title_art.vram.sprite(512, 256, 8, 0, 240, u, v, w, h)
        x0, y0 = scaled(dx, scale), scaled(dy, scale)
        size = (max(1, scaled(dx + w, scale) - x0), max(1, scaled(dy + h, scale) - y0))
        out = ua.paste(out, pngio.scale_to(piece, *size), x0 - left, y0 - top)
    return out


def menu_warnings(scene: Scene, menu: int, boxes: dict) -> dict:
    """What can look off in a menu as drawn (boxes: TitleCanvas.item_boxes):
    for each item, its lines -- running into another item, or past the
    screen's edge."""
    out = {}
    titles = {}
    for item, shown in scene.order(menu):
        titles[item["name"]] = item.get("label") or (ENTRY_TITLES[item["index"]] if item["entry"] else
                                                     item["name"].split(":", 1)[-1])
    names = list(boxes)
    for name in names:
        x, y, w, h = boxes[name]
        lines = []
        for other in names:
            if other == name:
                continue
            ox, oy, ow, oh = boxes[other]
            if x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                lines.append(f"runs into {titles.get(other, other)}")
        if x < 0 or y < 0 or x + w > 320 or y + h > 240:
            lines.append("reaches past the edge of the screen (cut off there)")
        if lines:
            out[name] = lines
    return out


class TitleCanvas:
    """Draws a Scene on a Stage: the title, or a menu up with an item
    chosen. Keys: "background", a layer's name, ("picture", i),
    ("text", i), ("item", name)."""

    def __init__(self, tab, stage: Stage):
        self.tab, self.stage = tab, stage
        self.item_boxes = {}

    def draw(self, scene: Scene, menu=None, cursor=None, chosen=None):
        stage = self.stage
        stage.clear()
        title_art = self.tab.title_art()
        project = scene.project
        background = scene.background(menu is not None)
        dim = background["dim"] if menu is not None else 0
        base = ua.blank(320, 240, (0, 0, 0, 255))
        color = background.get("color")
        if color is not None:
            c = ua.parse_color(color, -1)
            if c >= 0:
                base = ua.blank(320, 240, (c >> 16, c >> 8 & 255, c & 255, 255))
        image = mod_image(project, background.get("image")) if background.get("image") else None
        if background.get("picture") is not False:
            if image is not None:
                base = ua.paste(base, ua.tint(sized(image, 320, 240), ua.parse_color(background.get("tint"))), 0, 0)
            elif title_art.ok:
                base = ua.paste(base, ua.tint(title_art.wall(), ua.parse_color(background.get("tint"))), 0, 0)
        if background.get("shade") is not False:
            rows = []
            for y in range(240):
                level = y * 255 // 239
                table = bytes(max(0, v - level) for v in range(256))
                line = bytearray(base.rgba[y * 1280:(y + 1) * 1280].translate(table))
                line[3::4] = b"\xff" * 320
                rows.append(bytes(line))
            base = pngio.Image(320, 240, b"".join(rows))
        if not title_art.ok and image is None and color is None:
            stage.create_text(160 * stage.zoom, 228 * stage.zoom, fill="#999",
                              text="The game's title pictures come from DATA/SU.MRG beside the game files.")
        # The layers and the pictures under the menu's dimming: drawn into the background's picture
        # only where they are not to be dragged; here each its own, dimmed alike.
        stage.picture("background", ua.subtract(base, dim), 0, 0, drag=False)
        stage.boxes["background"] = (0, 0, 320, 240)
        layers = self.tab_layers(scene, title_art, menu)
        for key, picture, x, y in layers:
            stage.picture(key, ua.subtract(picture, dim) if key != "prompt" else picture, x, y)
        # A hidden one as a dashed box where it would be, to choose it again.
        for name in LAYER_NAMES:
            layer = scene.title.get(name) if isinstance(scene.title.get(name), dict) else {}
            if layer.get("hide") is True and title_art.ok:
                picture, x, y = title_art.layer(name)
                stage.rectangle(name, x + as_int(layer.get("x")), y + as_int(layer.get("y")), picture.width,
                                picture.height, outline="#9a9a9a", drag=True, dash=(3, 3))
        for i, (picture, x, y) in enumerate(self.pictures(scene, menu)):
            if picture is not None:
                stage.picture(("picture", i), ua.subtract(picture, dim), x, y)
        if menu is not None:
            self.draw_menu(scene, menu, cursor, title_art)
        self.draw_text(scene, menu)
        stage.outline(chosen)

    def tab_layers(self, scene: Scene, title_art, menu):
        out = []
        for name in LAYER_NAMES:
            layer = scene.title.get(name) if isinstance(scene.title.get(name), dict) else {}
            if layer.get("hide") is True:
                continue
            if name == "prompt" and (menu is not None or scene.title.get("press_start") is False):
                continue
            show = layer.get("show", "always")
            if show == "menu" and menu is None or show == "press_start" and menu is not None:
                continue
            dx, dy = as_int(layer.get("x")), as_int(layer.get("y"))
            tint = ua.parse_color(layer.get("tint"))
            level = 0x58 * 255 // 0x80 if name == "prompt" else 255     # PUSH START's pulse, at its middle
            own = mod_image(scene.project, layer.get("image")) if layer.get("image") else None
            if own is not None:
                w, h = fit(own.width, own.height, 320, 240 if name == "logo" else 120, as_int(layer.get("width")),
                           as_int(layer.get("height")))
                mx, my = ua.LAYER_MIDDLES[name]
                out.append((name, ua.tint(sized(own, w, h), tint, level), mx + dx - w // 2, my + dy - h // 2))
            elif title_art.ok:
                picture, x, y = title_art.layer(name)
                out.append((name, ua.tint(picture, tint, level), x + dx, y + dy))
        return out

    def pictures(self, scene: Scene, menu):
        out = []
        images = scene.title.get("images")
        for entry in images if isinstance(images, list) else []:
            if not isinstance(entry, dict):
                out.append((None, 0, 0))
                continue
            show = entry.get("show", "always")
            own = mod_image(scene.project, entry.get("image"))
            if own is None or (show == "menu" and menu is None) or (show == "press_start" and menu is not None):
                out.append((None, 0, 0))
                continue
            w, h = fit(own.width, own.height, 320, 240, as_int(entry.get("width")), as_int(entry.get("height")))
            x, y = as_int(entry.get("x"), 160), as_int(entry.get("y"), 120)
            out.append((ua.tint(sized(own, w, h), ua.parse_color(entry.get("tint"))), x - w // 2, y - h // 2))
        return out

    def draw_menu(self, scene: Scene, menu: int, cursor, title_art):
        """The menu's items at their places and sizes; self.item_boxes gets
        each one's drawn box (what of it shows) in the game's pixels."""
        stage = self.stage
        places = scene.places(menu)
        self.item_boxes = {}
        for item, shown in scene.order(menu):
            if not shown:
                continue
            x, y = places[item["name"]]
            selected = item["name"] == cursor
            key = ("item", item["name"])
            drawn = item_look(scene, item, selected, title_art)
            if drawn is None:
                scale = scene.scale(item)
                box = (x + scaled(-48, scale), y + scaled(-14, scale), scaled(96, scale), scaled(28, scale))
                stage.rectangle(key, *box, fill="#28201f", outline="#606008", drag=True)
                stage.text(None, x, y, ENTRY_TITLES[item["index"]], "#ddd", 12 * scale / 100, anchor="center",
                           drag=False)
                self.item_boxes[item["name"]] = box
                continue
            picture, left, top, words = drawn
            stage.picture(key, picture, x + left, y + top)
            if words:
                text, ink, size, shadow = words
                stage.text(None, x, y, text, ink, size, anchor="center", font_family="Times", drag=False,
                           shadow=shadow)
            x0, y0, x1, y1 = opaque(picture)
            self.item_boxes[item["name"]] = (x + left + x0, y + top + y0, x1 - x0, y1 - y0)

    def draw_text(self, scene: Scene, menu):
        lines = scene.title.get("text")
        for i, line in enumerate(lines if isinstance(lines, list) else []):
            if not isinstance(line, dict) or not isinstance(line.get("text"), str):
                continue
            show = line.get("show", "always")
            if (show == "menu" and menu is None) or (show == "press_start" and menu is not None):
                continue
            size = max(1, min(8, as_int(line.get("size"), 1)))
            align = {"left": "w", "right": "e"}.get(line.get("align"), "center")
            color = color_text(ua.parse_color(line.get("color")))
            self.stage.text(("text", i), as_int(line.get("x"), 160), as_int(line.get("y"), 220), line["text"],
                            color, 12 * size, anchor=align)


# --- the pages -------------------------------------------------------------------------

def rows(frame):
    """line(caption, widget): the form's next row, the captions one column
    as wide as the others' forms have it."""
    frame.columnconfigure(0, minsize=px(frame, 110))
    row = 0

    def line(text, widget, pady=2):
        nonlocal row
        if text:
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=pady, padx=(0, 8))
        widget.grid(row=row, column=1, sticky="w", pady=pady)
        row += 1
        return widget
    return line


class BackgroundForm(ttk.Frame):
    """A "background" object's keys: the game's wall or a picture, its
    color, the shade, a color under it, the menu's dimming."""

    def __init__(self, master, page, menu: bool):
        super().__init__(master)
        self.page, self.menu = page, menu
        self.loading = False
        self.picture = tk.BooleanVar()
        self.shade = tk.BooleanVar()
        ttk.Checkbutton(self, text="The game's wall", variable=self.picture,
                        command=lambda: self.set("picture", self.picture.get(), True)).grid(row=0, column=0,
                                                                                         sticky="w")
        ttk.Checkbutton(self, text="Dark-to-light shade", variable=self.shade,
                        command=lambda: self.set("shade", self.shade.get(), True)).grid(row=0, column=1, sticky="w")
        ttk.Label(self, text="Wall color").grid(row=1, column=0, sticky="w", pady=2)
        self.tint = ColorButton(self, lambda v: self.set("tint", color_text(v) if v is not None else None, "#FFFFFF"),
                                 multiplies=True)
        self.tint.grid(row=1, column=1, sticky="w")
        ttk.Label(self, text="Color under it").grid(row=2, column=0, sticky="w", pady=2)
        self.color = ColorButton(self, lambda v: self.set("color", color_text(v) if v is not None else None),
                                   default=None, allow_none=True)
        self.color.grid(row=2, column=1, sticky="w")
        ttk.Label(self, text="Picture").grid(row=3, column=0, sticky="w", pady=2)
        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=1, sticky="w")
        ttk.Button(buttons, text="Choose PNG...", command=self.choose).pack(side="left")
        ttk.Button(buttons, text="None", command=lambda: self.set("image", None)).pack(side="left", padx=(4, 0))
        self.image = ttk.Label(self, style="Hint.TLabel")
        self.image.grid(row=4, column=1, sticky="w")
        ttk.Label(self, text="Menu dimming").grid(row=5, column=0, sticky="w", pady=2)
        self.dim = ttk.Scale(self, from_=0, to=128, length=px(self, 200), command=self.dimmed)
        self.dim.grid(row=5, column=1, sticky="w")
        self.columnconfigure(0, minsize=px(self, 130))

    def target(self) -> dict:
        return ensure(self.page.project, "menu" if self.menu else "title", "background")

    def current(self) -> dict:
        owner = section(self.page.project, "menu" if self.menu else "title")
        value = owner.get("background")
        return value if isinstance(value, dict) else {}

    def fill(self):
        self.loading = True
        bg = self.current()
        self.picture.set(bg.get("picture") is not False)
        self.shade.set(bg.get("shade") is not False)
        self.tint.set(ua.parse_color(bg.get("tint")))
        color = bg.get("color")
        self.color.set(ua.parse_color(color, 0) if color is not None else None)
        self.image.configure(text=bg.get("image") or ("the title's" if self.menu else "none"))
        self.dim.set(as_int(bg.get("dim"), 128))
        self.loading = False

    def set(self, key, value, default=None):
        if self.loading:
            return
        set_member(self.target(), key, value, default)
        self.page.edited()

    def choose(self):
        name = import_image(self, self.page.project, "menu-background" if self.menu else "title-background")
        if name:
            self.set("image", name)

    def dimmed(self, value):
        if self.loading:
            return
        value = int(float(value))
        if value != as_int(self.current().get("dim"), 128):
            set_member(self.target(), "dim", value, 128)
            self.page.edited(redraw_form=False)


WHAT = {"background": "Behind everything: the game's wall, a color, or a picture of yours.",
        "logo": "The game's logo.", "copyright": "The \u00a9 1996 line.",
        "prompt": "Blinks until a button is pressed.", "picture": "A picture of yours, by its middle.",
        "text": "A line of words, drawn by the port in its own letters."}


class TitlePage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.chosen = "background"
        self.loading = False
        page_layout(self, self.draw, on_select=self.select, on_move=self.moved, on_drag=self.dragging)
        self.canvas = TitleCanvas(tab, self.stage)
        self.menu_up = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.view.tools, text="With the menu up", variable=self.menu_up,
                        command=self.draw).pack(side="left")
        self.add_picture_button = ttk.Button(self.list_tools, text="+ Picture", command=self.add_picture)
        self.add_picture_button.pack(side="left")
        self.add_text_button = ttk.Button(self.list_tools, text="+ Words", command=self.add_text)
        self.add_text_button.pack(side="left", padx=(4, 0))
        self.form_box = ttk.Frame(self.side)
        self.form_box.grid(row=4, column=0, sticky="new")
        self.forms = {}
        self.forms["background"] = self.background_form()
        self.forms["layer"] = self.layer_form()
        self.forms["picture"] = self.picture_form()
        self.forms["text"] = self.text_form()
        self.status = ttk.Label(self.side, style="Hint.TLabel", wraplength=px(self, 440), justify="left")
        self.status.grid(row=5, column=0, sticky="w", pady=(8, 0))

    @property
    def project(self):
        return self.tab.project

    def title(self) -> dict:
        return ensure(self.project, "title")

    def edited(self, redraw_form=True):
        self.tab.changed("title")
        self.draw()
        if redraw_form:
            self.fill_form()

    # --- the forms ----------------------------------------------------------------

    def background_form(self):
        frame = ttk.Frame(self.form_box)
        self.background = BackgroundForm(frame, self, menu=False)
        self.background.pack(anchor="w", fill="x")
        screen = ttk.LabelFrame(frame, text="Start-up", padding=6)
        screen.pack(anchor="w", fill="x", pady=(10, 0))
        self.skip = tk.BooleanVar()
        self.press = tk.BooleanVar()
        ttk.Checkbutton(screen, text="Skip the intro movie", variable=self.skip,
                        command=lambda: self.set_title("skip_intro", True if self.skip.get() else None)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(screen, text="PUSH START BUTTON first", variable=self.press,
                        command=lambda: self.set_title("press_start", None if self.press.get() else False)).grid(
            row=1, column=0, columnspan=2, sticky="w")
        self.music = tk.StringVar()
        self.idle = tk.StringVar()
        ttk.Label(screen, text="Song (0x000)").grid(row=2, column=0, sticky="w", pady=2)
        music = ttk.Entry(screen, textvariable=self.music, width=8)
        music.grid(row=2, column=1, sticky="w")
        ttk.Label(screen, text="Intro again after (s, 0 never)").grid(row=3, column=0, sticky="w", pady=2)
        idle = ttk.Entry(screen, textvariable=self.idle, width=8)
        idle.grid(row=3, column=1, sticky="w")
        for entry in (music, idle):
            entry.bind("<Return>", lambda e: self.screen_typed())
            entry.bind("<FocusOut>", lambda e: self.screen_typed())
        return frame

    def place_fields(self, frame, variables, typed, centre=None):
        """x and y boxes (Return, leaving or the arrows apply), and a
        Centre button when there is one: a frame for the form's row."""
        places = ttk.Frame(frame)
        for key in ("x", "y"):
            ttk.Label(places, text=key).pack(side="left", padx=(0 if key == "x" else 8, 4))
            box = ttk.Spinbox(places, from_=-320, to=640, width=5, textvariable=variables[key],
                              command=lambda k=key: typed(k))
            box.pack(side="left")
            box.bind("<Return>", lambda e, k=key: typed(k))
            box.bind("<FocusOut>", lambda e, k=key: typed(k))
        if centre:
            ttk.Button(places, text="Centre", command=centre).pack(side="left", padx=(8, 0))
        return places

    def layer_form(self):
        frame = ttk.Frame(self.form_box)
        line = rows(frame)
        self.layer_vars = {"x": tk.StringVar(), "y": tk.StringVar(), "show": tk.StringVar()}
        line("Moved by", self.place_fields(frame, self.layer_vars, self.layer_typed))
        self.layer_tint = line("Color", ColorButton(frame, lambda v: self.set_layer(
            "tint", color_text(v) if v is not None else None, "#FFFFFF"), multiplies=True))
        self.show_box = line("Shown", ttk.Combobox(frame, state="readonly", width=18,
                                                    values=[SHOW_TITLES[s] for s in SHOW]))
        self.show_box.bind("<<ComboboxSelected>>", lambda e: self.set_layer(
            "show", SHOW[self.show_box.current()], "always"))
        buttons = ttk.Frame(frame)
        ttk.Button(buttons, text="Choose PNG...", command=self.layer_image).pack(side="left")
        ttk.Button(buttons, text="Game's", command=lambda: self.set_layer("image", None)).pack(side="left", padx=(4, 0))
        line("Picture", buttons)
        self.layer_image_name = line("", ttk.Label(frame, style="Hint.TLabel"))
        self.layer_hidden = tk.BooleanVar()
        line("", ttk.Checkbutton(frame, text="Hidden", variable=self.layer_hidden,
                                 command=lambda: self.set_layer("hide", True if self.layer_hidden.get() else None)))
        line("", ttk.Button(frame, text="Back to the game's", command=self.reset_layer), pady=(10, 0))
        return frame

    def picture_form(self):
        frame = ttk.Frame(self.form_box)
        line = rows(frame)
        self.picture_vars = {key: tk.StringVar() for key in ("width", "height", "x", "y")}
        line("Middle at", self.place_fields(frame, self.picture_vars, self.picture_place,
                                            centre=lambda: self.centre("picture")))
        self.picture_tint = line("Color", ColorButton(frame, lambda v: self.set_picture(
            "tint", color_text(v) if v is not None else None, "#FFFFFF"), multiplies=True))
        sizes = ttk.Frame(frame)
        for key in ("width", "height"):
            if key == "height":
                ttk.Label(sizes, text=" x ").pack(side="left")
            box = ttk.Spinbox(sizes, from_=0, to=320, width=5, textvariable=self.picture_vars[key],
                              command=lambda k=key: self.picture_typed(k))
            box.pack(side="left")
            box.bind("<Return>", lambda e, k=key: self.picture_typed(k))
            box.bind("<FocusOut>", lambda e, k=key: self.picture_typed(k))
        ttk.Label(sizes, text="  0: its own", style="Hint.TLabel").pack(side="left")
        line("Size", sizes)
        self.picture_show = line("Shown", ttk.Combobox(frame, state="readonly", width=18,
                                                        values=[SHOW_TITLES[s] for s in SHOW]))
        self.picture_show.bind("<<ComboboxSelected>>", lambda e: self.set_picture(
            "show", SHOW[self.picture_show.current()], "always"))
        buttons = ttk.Frame(frame)
        ttk.Button(buttons, text="Another PNG...", command=self.replace_picture).pack(side="left")
        ttk.Button(buttons, text="Remove", command=self.remove_picture).pack(side="left", padx=(4, 0))
        line("", buttons, pady=(10, 0))
        return frame

    def text_form(self):
        frame = ttk.Frame(self.form_box)
        line = rows(frame)
        self.text_vars = {"text": tk.StringVar(), "size": tk.StringVar(), "x": tk.StringVar(), "y": tk.StringVar()}
        words = line("Words", ttk.Entry(frame, textvariable=self.text_vars["text"], width=34))
        line("At", self.place_fields(frame, self.text_vars, self.text_place, centre=lambda: self.centre("text")))
        self.text_color = line("Color", ColorButton(frame, lambda v: self.set_text(
            "color", color_text(v) if v is not None else None, "#FFFFFF")))
        size = line("Size", ttk.Spinbox(frame, from_=1, to=8, width=4, textvariable=self.text_vars["size"],
                                        command=lambda: self.text_typed("size")))
        self.align_box = line("Lined up", ttk.Combobox(frame, state="readonly", width=10,
                                                       values=["left", "center", "right"]))
        self.align_box.bind("<<ComboboxSelected>>", lambda e: self.set_text("align", self.align_box.get(), "center"))
        self.text_show = line("Shown", ttk.Combobox(frame, state="readonly", width=18,
                                                     values=[SHOW_TITLES[s] for s in SHOW]))
        self.text_show.bind("<<ComboboxSelected>>", lambda e: self.set_text(
            "show", SHOW[self.text_show.current()], "always"))
        line("", ttk.Button(frame, text="Remove", command=self.remove_text), pady=(10, 0))
        for widget, key in ((words, "text"), (size, "size")):
            widget.bind("<Return>", lambda e, k=key: self.text_typed(k))
            widget.bind("<FocusOut>", lambda e, k=key: self.text_typed(k))
        return frame

    # --- drawing and choosing ---------------------------------------------------------

    def fill(self):
        if self.project is None:
            return
        self.check_choice()
        self.draw()
        self.fill_form()

    def reset_choice(self):
        self.chosen = "background"

    def check_choice(self):
        """The chosen thing still there (an undo may have taken it)."""
        if isinstance(self.chosen, tuple):
            title = section(self.project, "title")
            listed = title.get("images" if self.chosen[0] == "picture" else "text")
            if not isinstance(listed, list) or self.chosen[1] >= len(listed):
                self.chosen = "background"

    def draw(self):
        if self.project is None:
            return
        self.tab.draw_compared(self, lambda: self.canvas.draw(Scene(self.project), menu=0 if self.menu_up.get()
                                                              else None, cursor="new_game", chosen=self.chosen))
        self.fill_list()

    @staticmethod
    def chip_key(key) -> str:
        return key if isinstance(key, str) else f"{key[0]}:{key[1]}"

    @staticmethod
    def key_of(iid: str):
        kind, _, index = iid.partition(":")
        return (kind, int(index)) if index else kind

    def fill_list(self):
        """Everything on the title, grouped, a dot on what the mod changes."""
        title = section(self.project, "title")
        rows = [("screen", "", "The screen", (), False, ("group",)),
                ("background", "screen", "Background", (), bool(title.get("background")), ())]
        rows += [(name, "screen", LAYER_TITLES[name], (), bool(title.get(name)), ()) for name in LAYER_NAMES]
        images = title.get("images") if isinstance(title.get("images"), list) else []
        if images:
            rows.append(("pictures", "", "Pictures", (), False, ("group",)))
        for i, entry in enumerate(images):
            name = entry.get("image") if isinstance(entry, dict) else None
            label = f"Picture {i + 1}" + (f"  {name.rsplit('/', 1)[-1]}" if isinstance(name, str) else "")
            rows.append((f"picture:{i}", "pictures", label, (), True, ()))
        lines = title.get("text") if isinstance(title.get("text"), list) else []
        if lines:
            rows.append(("lines", "", "Words", (), False, ("group",)))
        for i, line in enumerate(lines):
            text = line.get("text") if isinstance(line, dict) else ""
            rows.append((f"text:{i}", "lines", f"\u201c{text}\u201d" if text else f"Words {i + 1}", (), True, ()))
        self.list.fill(rows, self.chip_key(self.chosen))
        self.add_picture_button.state(["disabled"] if len(images) >= MAX_PICTURES else ["!disabled"])
        self.add_text_button.state(["disabled"] if len(lines) >= MAX_LINES else ["!disabled"])

    def pick(self, iid, group=None):
        self.select(self.key_of(iid))

    def select(self, key):
        if key is None:
            key = "background"
        if isinstance(key, tuple) and key[0] == "item":
            return
        self.chosen = key
        self.stage.outline(key if key != "background" else None)
        self.list.show(self.chip_key(key))
        self.fill_form()

    def kind(self):
        if self.chosen == "background":
            return "background"
        if self.chosen in LAYER_NAMES:
            return "layer"
        return self.chosen[0]

    def fill_form(self):
        if self.project is None:
            return
        self.check_choice()
        self.loading = True
        kind = self.kind()
        for name, form in self.forms.items():
            if name == kind:
                form.pack(anchor="w", fill="x", pady=(6, 0))
            else:
                form.pack_forget()
        title = section(self.project, "title")
        self.what.configure(text=WHAT[self.chosen if kind == "layer" else kind])
        if kind == "background":
            self.heading.configure(text="Background")
            self.background.fill()
            self.skip.set(title.get("skip_intro") is True)
            self.press.set(title.get("press_start") is not False)
            music = title.get("music")
            self.music.set(music if isinstance(music, str) else f"0x{music:03X}" if isinstance(music, int) else "")
            idle = title.get("idle_seconds")
            self.idle.set(str(idle) if isinstance(idle, int) else "")
        elif kind == "layer":
            self.heading.configure(text=LAYER_TITLES[self.chosen])
            layer = title.get(self.chosen) if isinstance(title.get(self.chosen), dict) else {}
            self.layer_vars["x"].set(str(as_int(layer.get("x"))))
            self.layer_vars["y"].set(str(as_int(layer.get("y"))))
            self.layer_tint.set(ua.parse_color(layer.get("tint")))
            show = layer.get("show", "always")
            self.show_box.configure(values=[SHOW_TITLES[s] for s in SHOW if self.chosen != "prompt" or s != "menu"])
            self.show_box.current(SHOW.index(show) if show in SHOW else 0)
            self.layer_image_name.configure(text=layer.get("image") or "the game's own")
            self.layer_hidden.set(layer.get("hide") is True)
        elif kind == "picture":
            entry = self.picture_entry()
            self.heading.configure(text=f"Picture {self.chosen[1] + 1}")
            self.what.configure(text=entry.get("image", ""))
            self.picture_tint.set(ua.parse_color(entry.get("tint")))
            for key, default in (("width", 0), ("height", 0), ("x", 160), ("y", 120)):
                self.picture_vars[key].set(str(as_int(entry.get(key), default)))
            show = entry.get("show", "always")
            self.picture_show.current(SHOW.index(show) if show in SHOW else 0)
        elif kind == "text":
            line = self.text_entry()
            self.heading.configure(text=f"Words {self.chosen[1] + 1}")
            self.text_vars["text"].set(line.get("text", ""))
            self.text_vars["size"].set(str(as_int(line.get("size"), 1)))
            self.text_vars["x"].set(str(as_int(line.get("x"), 160)))
            self.text_vars["y"].set(str(as_int(line.get("y"), 220)))
            self.text_color.set(ua.parse_color(line.get("color")))
            self.align_box.set(line.get("align", "center"))
            show = line.get("show", "always")
            self.text_show.current(SHOW.index(show) if show in SHOW else 0)
        self.status.configure(text="")
        self.loading = False

    def dragging(self, key, dx, dy):
        """The form's place as the drag has it, before it lands."""
        if key != self.chosen:
            return
        if key in LAYER_NAMES:
            layer = section(self.project, "title").get(key)
            layer = layer if isinstance(layer, dict) else {}
            fields, start = self.layer_vars, (as_int(layer.get("x")), as_int(layer.get("y")))
        elif isinstance(key, tuple) and key[0] in ("picture", "text"):
            entry = self.picture_entry(key[1]) if key[0] == "picture" else self.text_entry(key[1])
            fields = self.picture_vars if key[0] == "picture" else self.text_vars
            start = (as_int(entry.get("x"), 160), as_int(entry.get("y"), 120 if key[0] == "picture" else 220))
        else:
            return
        fields["x"].set(str(start[0] + dx))
        fields["y"].set(str(start[1] + dy))

    def centre(self, kind):
        if self.kind() != kind:
            return
        entry = self.picture_entry() if kind == "picture" else self.text_entry()
        entry["x"] = 160
        if kind == "text":
            entry.pop("align", None)
        self.edited()

    def picture_place(self, key):
        self.placed(key, self.picture_vars, "picture", self.picture_entry)

    def text_place(self, key):
        self.placed(key, self.text_vars, "text", self.text_entry)

    def placed(self, key, fields, kind, entry):
        if self.kind() != kind or self.loading:
            return
        try:
            value = int(fields[key].get().strip())
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        target = entry()
        if target.get(key) != value:
            target[key] = max(-320, min(640, value))
            self.edited()

    def moved(self, key, dx, dy):
        if key in LAYER_NAMES:
            layer = ensure(self.project, "title", key)
            set_member(layer, "x", as_int(layer.get("x")) + dx, 0)
            set_member(layer, "y", as_int(layer.get("y")) + dy, 0)
        elif isinstance(key, tuple) and key[0] == "picture":
            entry = self.picture_entry(key[1])
            entry["x"] = as_int(entry.get("x"), 160) + dx
            entry["y"] = as_int(entry.get("y"), 120) + dy
        elif isinstance(key, tuple) and key[0] == "text":
            line = self.text_entry(key[1])
            line["x"] = as_int(line.get("x"), 160) + dx
            line["y"] = as_int(line.get("y"), 220) + dy
        else:
            return
        self.chosen = key
        self.edited()

    # --- the title's own keys ------------------------------------------------------------

    def set_title(self, key, value):
        if self.loading:
            return
        set_member(self.title(), key, value)
        self.edited()

    def screen_typed(self):
        if self.loading or self.project is None:
            return
        title = self.title()
        music, idle = self.music.get().strip(), self.idle.get().strip()
        try:
            if music:
                number = int(music, 0)
                if not 0 <= number <= 0xFFF:
                    raise ValueError
                title["music"] = f"0x{number:03X}"
            else:
                title.pop("music", None)
            if idle:
                seconds = int(idle)
                if seconds < 0:
                    raise ValueError
                title["idle_seconds"] = seconds
            else:
                title.pop("idle_seconds", None)
        except ValueError:
            self.status.configure(text="The song is a number from 0x000 to 0xFFF; the seconds 0 or more.")
            return
        self.edited(redraw_form=False)

    # --- the three pictures ------------------------------------------------------------

    def set_layer(self, key, value, default=None):
        if self.kind() != "layer":
            return
        if self.loading:
            return
        set_member(ensure(self.project, "title", self.chosen), key, value, default)
        self.edited()

    def layer_typed(self, key):
        if self.kind() != "layer":
            return
        if self.loading:
            return
        try:
            value = int(self.layer_vars[key].get().strip() or 0)
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        self.set_layer(key, value, 0)

    def layer_image(self):
        if self.kind() != "layer":
            return
        name = import_image(self, self.project, f"title-{self.chosen}")
        if name:
            self.set_layer("image", name)

    def reset_layer(self):
        if self.kind() != "layer":
            return
        title = self.title()
        title.pop(self.chosen, None)
        self.edited()

    # --- added pictures ------------------------------------------------------------------

    def pictures_list(self) -> list:
        title = self.title()
        if not isinstance(title.get("images"), list):
            title["images"] = []
        return title["images"]

    def picture_entry(self, index=None) -> dict:
        images = self.pictures_list()
        index = self.chosen[1] if index is None else index
        if not isinstance(images[index], dict):
            images[index] = {}
        return images[index]

    def add_picture(self):
        if self.project is None:
            return
        if len(self.pictures_list()) >= MAX_PICTURES:
            self.status.configure(text=f"At most {MAX_PICTURES} pictures.")
            return
        name = import_image(self, self.project, "title-picture")
        if not name:
            if not self.pictures_list():
                self.title().pop("images", None)
            return
        self.pictures_list().append({"image": name, "x": 160, "y": 120})
        self.chosen = ("picture", len(self.pictures_list()) - 1)
        self.edited()

    def replace_picture(self):
        if self.kind() != "picture":
            return
        name = import_image(self, self.project, "title-picture")
        if name:
            self.picture_entry()["image"] = name
            self.edited()

    def remove_picture(self):
        if self.kind() != "picture":
            return
        images = self.pictures_list()
        del images[self.chosen[1]]
        if not images:
            self.title().pop("images")
        self.chosen = "background"
        self.edited()

    def set_picture(self, key, value, default=None):
        if self.kind() != "picture":
            return
        if self.loading:
            return
        set_member(self.picture_entry(), key, value, default)
        self.edited()

    def picture_typed(self, key):
        if self.kind() != "picture":
            return
        if self.loading:
            return
        try:
            value = max(0, min(320 if key == "width" else 240, int(self.picture_vars[key].get().strip() or 0)))
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        self.set_picture(key, value or None)

    # --- lines of words ----------------------------------------------------------------

    def lines(self) -> list:
        title = self.title()
        if not isinstance(title.get("text"), list):
            title["text"] = []
        return title["text"]

    def text_entry(self, index=None) -> dict:
        lines = self.lines()
        index = self.chosen[1] if index is None else index
        if not isinstance(lines[index], dict):
            lines[index] = {"text": ""}
        return lines[index]

    def add_text(self):
        if self.project is None:
            return
        if len(self.lines()) >= MAX_LINES:
            self.status.configure(text=f"At most {MAX_LINES} lines.")
            return
        self.lines().append({"text": self.project.info.name or "My mod", "x": 160, "y": 228})
        self.chosen = ("text", len(self.lines()) - 1)
        self.edited()

    def remove_text(self):
        if self.kind() != "text":
            return
        lines = self.lines()
        del lines[self.chosen[1]]
        if not lines:
            self.title().pop("text")
        self.chosen = "background"
        self.edited()

    def set_text(self, key, value, default=None):
        if self.kind() != "text":
            return
        if self.loading:
            return
        set_member(self.text_entry(), key, value, default)
        self.edited()

    def text_typed(self, key):
        if self.kind() != "text":
            return
        if self.loading:
            return
        if key == "text":
            text = self.text_vars["text"].get()
            if len(text.encode("utf-8")) > 95:
                self.status.configure(text="At most 95 letters.")
                return
            self.text_entry()["text"] = text
            self.edited()
            return
        try:
            value = max(1, min(8, int(self.text_vars["size"].get().strip() or 1)))
        except ValueError:
            self.status.configure(text="A size from 1 to 8.")
            return
        self.set_text("size", value, 1)


class MenuPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.menu = tk.IntVar(value=0)
        self.chosen = "new_game"
        self.loading = False
        page_layout(self, self.draw, columns=(("#0", "Button", 190), ("does", "Does", 150)), list_height=7,
                    on_select=self.select_stage, on_move=self.moved, on_drag=self.dragging, on_wheel=self.wheel)
        self.canvas = TitleCanvas(tab, self.stage)
        ttk.Label(self.view.tools, text="Spacing").pack(side="left", padx=(0, 4))
        self.spacing = tk.StringVar()
        spacing = ttk.Spinbox(self.view.tools, from_=8, to=64, width=4, textvariable=self.spacing,
                              command=self.spaced)
        spacing.pack(side="left")
        spacing.bind("<Return>", lambda e: self.spaced())
        # Every item's size but those with their own (the menu's "scale").
        ttk.Label(self.view.tools, text="All buttons").pack(side="left", padx=(12, 4))
        self.all_scale = tk.StringVar()
        self.all_slider = ttk.Scale(self.view.tools, from_=SCALE_MIN, to=SCALE_MAX, length=px(self, 110),
                                    command=lambda v: self.all_slid(v))
        self.all_slider.pack(side="left")
        all_box = ttk.Spinbox(self.view.tools, from_=SCALE_MIN, to=SCALE_MAX, increment=5, width=4,
                              textvariable=self.all_scale, command=self.all_typed)
        all_box.pack(side="left", padx=(4, 0))
        all_box.bind("<Return>", lambda e: self.all_typed())
        all_box.bind("<FocusOut>", lambda e: self.all_typed())
        ttk.Label(self.view.tools, text="%").pack(side="left")
        ttk.Button(self.list_tools, text="\u25b2", width=3, command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(self.list_tools, text="\u25bc", width=3, command=lambda: self.move(1)).pack(side="left",
                                                                                            padx=(2, 8))
        ttk.Button(self.list_tools, text="+ Button", command=self.add_button).pack(side="left")
        self.hide_button = ttk.Button(self.list_tools, text="Hide", command=self.toggle_hidden)
        self.hide_button.pack(side="left", padx=(4, 0))
        self.remove_button = ttk.Button(self.list_tools, text="Remove", command=self.remove)
        self.remove_button.pack(side="left", padx=(4, 0))
        self.form_box = ttk.Frame(self.side)
        self.form_box.grid(row=4, column=0, sticky="new")
        self.item_form = self.make_item_form(self.form_box)
        self.background = BackgroundForm(self.form_box, self, menu=True)
        self.background.columnconfigure(0, minsize=px(self, 110))
        # What can look off with the sizes and places set (menu_warnings()).
        self.warning = ttk.Label(self.side, style="Warning.TLabel", wraplength=px(self, 440), justify="left")
        self.warning.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.status = ttk.Label(self.side, style="Hint.TLabel", wraplength=px(self, 440), justify="left")
        self.status.grid(row=6, column=0, sticky="w", pady=(6, 0))

    @property
    def project(self):
        return self.tab.project

    def edited(self, redraw_form=True):
        self.tab.changed("menu")
        self.draw()
        if redraw_form:
            self.fill_list()
            self.fill_form()

    def make_item_form(self, parent):
        frame = ttk.Frame(parent)
        self.item_vars = {key: tk.StringVar() for key in ("label", "notice_title", "notice", "value", "x", "y",
                                                          "scale")}
        frame.columnconfigure(0, minsize=px(frame, 110))
        row = 0

        def line(text, widget):
            nonlocal row
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
            widget.grid(row=row, column=1, sticky="w", pady=2)
            row += 1
            return widget
        label = line("Words", ttk.Entry(frame, textvariable=self.item_vars["label"], width=24))
        self.action_box = line("Does", ttk.Combobox(frame, state="readonly", width=22))
        self.action_box.bind("<<ComboboxSelected>>", lambda e: self.set_action())
        notice = ttk.Frame(frame)
        ttk.Entry(notice, textvariable=self.item_vars["notice_title"], width=10).pack(side="left")
        ttk.Entry(notice, textvariable=self.item_vars["notice"], width=22).pack(side="left", padx=(4, 0))
        self.notice_row = line("Notice", notice)
        self.notice_caption = frame.grid_slaves(row=row - 1, column=0)[0]
        self.value_box = line("Event value", ttk.Entry(frame, textvariable=self.item_vars["value"], width=8))
        self.value_caption = frame.grid_slaves(row=row - 1, column=0)[0]
        self.item_tint = line("Color", ColorButton(frame, lambda v: self.set_item(
            "tint", color_text(v) if v is not None else None, "#FFFFFF"), multiplies=True))
        pictures = ttk.Frame(frame)
        ttk.Button(pictures, text="PNG...", command=lambda: self.item_image("image")).pack(side="left")
        ttk.Button(pictures, text="With cursor...", command=lambda: self.item_image("selected_image")).pack(
            side="left", padx=(4, 0))
        ttk.Button(pictures, text="None", command=self.clear_images).pack(side="left", padx=(4, 0))
        line("Picture", pictures)
        self.item_image_name = ttk.Label(frame, style="Hint.TLabel")
        self.item_image_name.grid(row=row, column=1, sticky="w")
        row += 1
        places = ttk.Frame(frame)
        ttk.Label(places, text="x").pack(side="left", padx=(0, 4))
        x = ttk.Spinbox(places, from_=-214, to=214, width=5, textvariable=self.item_vars["x"],
                        command=lambda: self.item_typed("x"))
        x.pack(side="left")
        ttk.Label(places, text="y").pack(side="left", padx=(8, 4))
        y = ttk.Spinbox(places, from_=-40, to=280, width=5, textvariable=self.item_vars["y"],
                        command=lambda: self.item_typed("y"))
        y.pack(side="left")
        ttk.Button(places, text="In line", command=self.in_line).pack(side="left", padx=(6, 0))
        line("Middle at", places)
        sizes = ttk.Frame(frame)
        self.scale_slider = ttk.Scale(sizes, from_=SCALE_MIN, to=SCALE_MAX, length=px(frame, 150),
                                      command=self.slid)
        self.scale_slider.pack(side="left")
        scale = ttk.Spinbox(sizes, from_=SCALE_MIN, to=SCALE_MAX, increment=5, width=4,
                            textvariable=self.item_vars["scale"], command=lambda: self.item_typed("scale"))
        scale.pack(side="left", padx=(6, 0))
        ttk.Label(sizes, text="%").pack(side="left")
        self.scale_note = ttk.Label(sizes, style="Hint.TLabel")
        self.scale_note.pack(side="left", padx=(6, 0))
        line("Size", sizes)
        for widget, key in ((label, "label"), (x, "x"), (y, "y"), (self.value_box, "value"), (scale, "scale")):
            widget.bind("<Return>", lambda e, k=key: self.item_typed(k))
            widget.bind("<FocusOut>", lambda e, k=key: self.item_typed(k))
        for child in notice.winfo_children():
            child.bind("<Return>", lambda e: self.item_typed("notice"))
            child.bind("<FocusOut>", lambda e: self.item_typed("notice"))
        ttk.Button(frame, text="Back to the game's", command=self.reset_item).grid(row=row, column=1, sticky="w",
                                                                                pady=(8, 0))
        return frame

    # --- the menu's items -----------------------------------------------------------------

    def scene(self):
        return Scene(self.project)

    def item(self, name=None):
        name = name or self.chosen
        for item in self.scene().items():
            if item["name"] == name:
                return item
        return None

    def target(self, name=None) -> dict:
        """The object the mod keeps an item's keys in: an entry's under
        "menu"."entries", a button its own in "buttons"."""
        name = name or self.chosen
        if name in ENTRY_NAMES:
            return ensure(self.project, "menu", "entries", name)
        menu = ensure(self.project, "menu")
        buttons = menu.setdefault("buttons", [])
        own = self.project.info.id or "mod"
        for button in buttons:
            if isinstance(button, dict) and (button.get("id") == name or f"{own}:{button.get('id')}" == name):
                return button
        button = {"id": name}
        buttons.append(button)
        return button

    def short(self, name: str) -> str:
        own = (self.project.info.id or "mod") + ":"
        return name[len(own):] if name.startswith(own) else name

    def fill(self):
        if self.project is None:
            return
        if self.chosen != "background" and self.item() is None:
            self.reset_choice()
        self.draw()
        self.fill_list()
        self.fill_form()

    def reset_choice(self):
        self.chosen = "new_game" if self.menu.get() == 0 else "campaign"

    def switch_menu(self):
        order = self.scene().order(self.menu.get())
        if order and (self.item() is None or self.item()["menu"] != self.menu.get()):
            self.chosen = order[0][0]["name"]
        self.fill()

    def draw(self):
        if self.project is None:
            return
        scene = self.scene()
        chosen = ("item", self.chosen) if self.chosen != "background" else None
        self.tab.draw_compared(self, lambda: self.canvas.draw(self.scene(), menu=self.menu.get(),
                                                              cursor=self.chosen, chosen=chosen))
        spacing = as_int(scene.menu.get("spacing"), as_int(scene.title.get("spacing"), SPACING))
        self.spacing.set(str(spacing))
        self.all_scale.set(str(scene.menu_scale()))
        self.loading, held = True, self.loading
        self.all_slider.set(scene.menu_scale())
        self.loading = held
        self.warn()

    def warn(self):
        """The chosen item's rough edges in the menu drawn, and the others'."""
        if self.project is None or self.tab.comparing:
            self.warning.configure(text="")
            return
        scene = self.scene()
        # Not the logo or the copyright line: the game's own menus stand
        # over both (SAVE over the copyright line).
        found = menu_warnings(scene, self.menu.get(), self.canvas.item_boxes)
        titles = {item["name"]: item.get("label") or (ENTRY_TITLES[item["index"]] if item["entry"] else
                                                      self.short(item["name"]))
                  for item, _ in scene.order(self.menu.get())}
        lines = [WARN + line[0].upper() + line[1:] for line in found.get(self.chosen, [])]
        rest = [titles.get(name, name) for name in found if name != self.chosen]
        if rest:
            lines.append(WARN + "Also: " + ", ".join(rest) + (" runs into something or past the screen's edge"
                                                              if len(rest) == 1 else
                                                              " run into something or past the screen's edge"))
        self.warning.configure(text="\n".join(lines))

    def fill_list(self):
        """The menu background, then both menus' items in their order: the
        hidden greyed, a dot on what the mod changes."""
        if self.project is None:
            return
        scene = self.scene()
        bg = scene.menu.get("background")
        rows = [("background", "", "Menu background", ("",), bool(bg), ())]
        for menu, group, text in ((0, "first", "First menu"), (1, "second", "Second menu (a game loaded)")):
            rows.append((group, "", text, ("",), False, ("group",)))
            for item, shown in scene.order(menu):
                label = item.get("label") or (ENTRY_TITLES[item["index"]] if item["entry"] else
                                              self.short(item["name"]))
                action = item.get("action") or (item["name"] if item["entry"] else
                                                ("notice" if item.get("notice") else "none"))
                does = action_title(action) + ("" if allowed(action, menu) else " (not here)")
                changed = not item["entry"] or any(k not in ("name", "index", "menu", "own", "entry") for k in item)
                rows.append((item["name"], group, ("" if shown else "\u25cc ") + label, (does,), changed,
                             () if shown else ("note",)))
        self.list.fill(rows, self.chosen)

    def pick(self, iid, group=None):
        if iid == "background":
            self.background_chosen()
            return
        item = self.item(iid)
        if item is None:
            return
        self.chosen = iid
        if item["menu"] != self.menu.get():
            self.menu.set(item["menu"])
        self.draw()
        self.list.show(iid)
        self.fill_form()

    def picked(self):
        selection = self.list.tree.selection()
        if selection:
            self.pick(selection[0])

    def select_stage(self, key):
        if isinstance(key, tuple) and key[0] == "item":
            self.chosen = key[1]
            self.draw()
            self.list.show(self.chosen)
            self.fill_form()

    def background_chosen(self):
        self.chosen = "background"
        self.draw()
        self.list.show("background")
        self.fill_form()

    def dragging(self, key, dx, dy):
        if not (isinstance(key, tuple) and key[0] == "item") or key[1] != self.chosen:
            return
        item = self.item()
        place = self.scene().places(self.menu.get()).get(self.chosen)
        if item and place:
            self.item_vars["x"].set(str(as_int(item.get("x")) + dx))
            self.item_vars["y"].set(str(place[1] + dy))

    def fill_form(self):
        if self.project is None:
            return
        self.loading = True
        if self.chosen == "background":
            self.item_form.pack_forget()
            self.background.pack(anchor="w", fill="x", pady=(6, 0))
            self.heading.configure(text="Menu background")
            self.what.configure(text="Behind a menu. What it leaves out is the title's.")
            self.background.fill()
            self.loading = False
            return
        self.background.pack_forget()
        self.item_form.pack(anchor="w", fill="x", pady=(6, 0))
        item = self.item() or {"name": self.chosen, "entry": False, "menu": 0}
        self.heading.configure(text=ENTRY_TITLES[item["index"]] if item.get("entry") else
                               f"Button {self.short(item['name'])}")
        self.what.configure(text=("The game's entry" if item.get("entry") else "A button of the mod's own")
                            + (", in the second menu (a game loaded)." if menu_of(item) else ", in the first menu."))
        self.item_vars["label"].set(item.get("label") or "")
        menu = item["menu"]
        choices = [a for a in ACTIONS if allowed(a, menu)]
        self.action_choices = (["(its own)"] if item.get("entry") else []) + choices
        self.action_box.configure(values=[c if c == "(its own)" else action_title(c) for c in self.action_choices])
        action = item.get("action")
        if action in self.action_choices:
            self.action_box.current(self.action_choices.index(action))
        elif item.get("entry"):
            self.action_box.current(0)
        else:
            self.action_box.current(self.action_choices.index("notice" if item.get("notice") else "none"))
        notice = item.get("notice")
        self.item_vars["notice_title"].set(notice.get("title", "") if isinstance(notice, dict) else "")
        self.item_vars["notice"].set(notice.get("text", "") if isinstance(notice, dict) else
                                     notice if isinstance(notice, str) else "")
        self.item_vars["value"].set(str(as_int(item.get("value"))))
        shown_action = self.action_choices[self.action_box.current()]
        for widget in (self.notice_row, self.notice_caption):
            widget.grid() if shown_action == "notice" else widget.grid_remove()
        for widget in (self.value_box, self.value_caption):
            widget.grid() if shown_action == "event" else widget.grid_remove()
        self.item_tint.set(ua.parse_color(item.get("tint")))
        pictures = [item.get("image"), item.get("selected_image")]
        self.item_image_name.configure(text=" / ".join(p for p in pictures if p) or "the game's own" if item.get(
            "entry") else " / ".join(p for p in pictures if p) or "words on a frame")
        place = self.scene().places(menu).get(item["name"])
        self.item_vars["x"].set(str(as_int(item.get("x"))))
        self.item_vars["y"].set(str(as_int(item.get("y"))) if "y" in item else str(place[1]) if place else "")
        scale = self.scene().scale(item)
        self.item_vars["scale"].set(str(scale))
        self.scale_slider.set(scale)
        self.scale_note.configure(text="" if a_scale(item.get("scale")) else "all buttons'")
        self.hide_button.configure(text="Show" if item.get("hide") is True else "Hide")
        self.remove_button.state(["disabled"] if item.get("entry") or not item.get("own", True) else ["!disabled"])
        self.status.configure(text="")
        self.loading = False

    # --- edits ------------------------------------------------------------------------

    def set_item(self, key, value, default=None):
        if self.loading or self.chosen == "background":
            return
        set_member(self.target(), key, value, default)
        self.edited()

    def item_typed(self, key):
        if self.loading or self.chosen == "background":
            return
        target = self.target()
        if key == "label":
            text = self.item_vars["label"].get().strip()
            if len(text) > 31:
                self.status.configure(text="At most 31 letters.")
                return
            set_member(target, "label", text or None)
        elif key == "notice":
            title, text = self.item_vars["notice_title"].get(), self.item_vars["notice"].get()
            set_member(target, "notice", {"title": title, "text": text} if title else (text or None))
        else:
            try:
                value = int(self.item_vars[key].get().strip() or 0)
            except ValueError:
                self.status.configure(text="A whole number.")
                return
            if key == "y":
                target["y"] = value
            elif key == "scale":
                self.sized(target, value)
            else:
                set_member(target, key, value, 0)
        self.edited()

    def sized(self, target: dict, value: int):
        """An item's own size, or none when it is the menu's."""
        value = max(SCALE_MIN, min(SCALE_MAX, value))
        set_member(target, "scale", value, self.scene().menu_scale())

    def slid(self, value):
        if self.loading or self.chosen == "background" or self.project is None:
            return
        value = int(round(float(value)))
        if value == self.scene().scale(self.item() or {}):
            return
        self.item_vars["scale"].set(str(value))
        self.sized(self.target(), value)
        self.scale_note.configure(text="" if a_scale(self.target().get("scale")) else "all buttons'")
        self.edited(redraw_form=False)

    def wheel(self, key, step):
        """The mouse wheel over an item: 10 % bigger or smaller."""
        if self.project is None or not (isinstance(key, tuple) and key[0] == "item"):
            return
        self.chosen = key[1]
        item = self.item()
        if item is None:
            return
        self.sized(self.target(), self.scene().scale(item) + 10 * step)
        self.edited()
        self.list.show(self.chosen)

    def set_all(self, value: int):
        """The menu's "scale": every item's but those with their own."""
        value = max(SCALE_MIN, min(SCALE_MAX, value))
        menu = ensure(self.project, "menu")
        set_member(menu, "scale", value, 100)
        # An item at the new size needs none of its own.
        held = [menu.get("entries"), section(self.project, "title").get("entries")]
        places = [v for d in held if isinstance(d, dict) for v in d.values()]
        places += menu.get("buttons") if isinstance(menu.get("buttons"), list) else []
        for target in places:
            if isinstance(target, dict) and target.get("scale") == value:
                target.pop("scale")

    def all_slid(self, value):
        if self.loading or self.project is None:
            return
        value = int(round(float(value)))
        if value == self.scene().menu_scale():
            return
        self.all_scale.set(str(value))
        self.set_all(value)
        self.edited()

    def all_typed(self):
        if self.loading or self.project is None:
            return
        try:
            value = int(self.all_scale.get().strip() or 100)
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        if value == self.scene().menu_scale():
            return
        self.set_all(value)
        self.edited()

    def set_action(self):
        if self.chosen == "background" or self.project is None:
            return
        if self.loading:
            return
        choice = self.action_choices[self.action_box.current()]
        target = self.target()
        if choice == "(its own)":
            target.pop("action", None)
        else:
            target["action"] = choice
            if choice == "notice" and not target.get("notice"):
                target["notice"] = {"title": target.get("label") or "", "text": "..."}
        self.edited()

    def in_line(self):
        if self.chosen == "background" or self.project is None:
            return
        target = self.target()
        target.pop("y", None)
        target.pop("x", None)
        self.edited()

    def item_image(self, key):
        if self.chosen == "background" or self.project is None:
            return
        name = import_image(self, self.project, f"menu-{self.short(self.chosen).replace(':', '-')}"
                            + ("-on" if key == "selected_image" else ""))
        if name:
            self.set_item(key, name)

    def clear_images(self):
        if self.chosen == "background" or self.project is None:
            return
        target = self.target()
        for key in ("image", "selected_image", "width", "height"):
            target.pop(key, None)
        self.edited()

    def moved(self, key, dx, dy):
        if not (isinstance(key, tuple) and key[0] == "item"):
            return
        self.chosen = key[1]
        place = self.scene().places(self.menu.get()).get(self.chosen)
        target = self.target()
        set_member(target, "x", as_int(target.get("x")) + dx, 0)
        if dy and place:
            target["y"] = place[1] + dy
        self.edited()

    def spaced(self):
        if self.loading or self.project is None:
            return
        try:
            value = max(8, min(64, int(self.spacing.get())))
        except ValueError:
            return
        set_member(ensure(self.project, "menu"), "spacing", value, SPACING)
        self.edited(redraw_form=False)

    def order_names(self) -> list:
        """The shown menu's order as the mod writes it."""
        return [self.short(item["name"]) for item, _ in self.scene().order(self.menu.get())]

    def write_order(self, names: list):
        menu = ensure(self.project, "menu")
        order = menu.get("order")
        if not isinstance(order, dict):
            order = {"first": order} if isinstance(order, list) else {}
            menu["order"] = order
        order[("first", "second")[self.menu.get()]] = names

    def move(self, step: int):
        if self.chosen == "background":
            return
        names = self.order_names()
        name = self.short(self.chosen)
        if name not in names:
            return
        at = names.index(name)
        to = at + step
        if not 0 <= to < len(names):
            return
        names[at], names[to] = names[to], names[at]
        self.write_order(names)
        self.edited()

    def toggle_hidden(self):
        if self.chosen == "background":
            return
        item = self.item()
        set_member(self.target(), "hide", None if item and item.get("hide") is True else True)
        self.edited()

    def add_button(self):
        if self.project is None:
            return
        buttons = ensure(self.project, "menu").setdefault("buttons", [])
        if len([b for b in self.scene().items() if not b["entry"]]) >= MAX_BUTTONS:
            self.status.configure(text=f"At most {MAX_BUTTONS} buttons.")
            return
        taken = {b.get("id") for b in buttons if isinstance(b, dict)}
        n = 1
        while f"button{n}" in taken:
            n += 1
        button = {"id": f"button{n}", "label": f"BUTTON {n}", "action": "notice",
                  "notice": {"title": f"Button {n}", "text": "Words of your own."}}
        if self.menu.get() == 1:
            button["menu"] = "second"
        buttons.append(button)
        self.chosen = f"{self.project.info.id or 'mod'}:button{n}"
        self.edited()

    def remove(self):
        if self.chosen == "background" or self.project is None:
            return
        item = self.item()
        if not item or item.get("entry") or not item.get("own"):
            return
        menu = ensure(self.project, "menu")
        menu["buttons"] = [b for b in menu.get("buttons", []) if not (isinstance(b, dict) and b.get("id") ==
                                                                        self.short(self.chosen))]
        if not menu["buttons"]:
            menu.pop("buttons")
        order = menu.get("order")
        for names in (order.values() if isinstance(order, dict) else [order] if isinstance(order, list) else []):
            if isinstance(names, list) and self.short(self.chosen) in names:
                names.remove(self.short(self.chosen))
        self.chosen = self.scene().order(self.menu.get())[0][0]["name"]
        self.edited()

    def reset_item(self):
        if self.chosen == "background" or self.project is None:
            return
        if self.chosen in ENTRY_NAMES:
            entries = ensure(self.project, "menu", "entries")
            entries.pop(self.chosen, None)
            title_entries = section(self.project, "title").get("entries")
            if isinstance(title_entries, dict):
                title_entries.pop(self.chosen, None)
        else:
            target = self.target()
            keep = {k: target[k] for k in ("id", "menu") if k in target}
            target.clear()
            target.update(keep)
            target["label"] = self.short(self.chosen).upper()
        self.edited()
