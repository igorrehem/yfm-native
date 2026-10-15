#!/usr/bin/env python3
"""Live check of the title menus' sizes (built game and user-supplied disc).

Makes a mod through the FM Editor's UI tab > Menus page the way a modder
would (its own controls; the file dialogs answered with pictures drawn
here):

* All buttons at 90 %;
* the first menu: LOAD at 150 % (typed), 2P DUEL at 70 % (the mouse wheel
  over it), OPTION as SETTINGS at 130 % (the slider), TRADE hidden, a
  CREDITS button of words at 60 % and a GALLERY button drawn from a
  picture, with another for the cursor, at 130 % that starts a new game;
* the second menu: CAMPAIGN at 140 % and a QUICK DUEL picture button at
  70 % that opens Free Duel;
* the menus' background a plain color and the logo and copyright line
  shown with PUSH START BUTTON only, so each item's box can be measured.

The page must find nothing wrong with it; then LOAD at 400 % is tried, the
page shows its warning, and that is not kept. Pictures of the page are
taken as it goes.

Then plays it through tools/pc/yfm_control.py, at Internal 1x and 2x, 4:3
and widescreen: each menu with the cursor on every item in turn, each item
measured where the game drew it against what the editor's preview draws
(its middle and size), the item under the cursor the same box as when it
is not (the cursor's look fits the resized button), and that look there
(the frame's red, the cursor's picture). Pressing GALLERY starts a new
game, SETTINGS opens the options, QUICK DUEL Free Duel. The same mod with
the game's own background and logo is pictured for the look. Without the
mod, every frame is the baseline build's (--baseline).

Pictures go to <out>/shots and <out>/editor; nothing is kept in the
repository.

    xvfb-run -a -s "-screen 0 1600x1000x24" python3 tests/pc/editor_menu_runtime.py \\
        [--executable PATH] [--out DIR] [--baseline PATH]

Needs a display for Tk and the 2x window, and ImageMagick's `import` for
the editor's pictures.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
MOD = "menusizes-test"
BACKGROUND = (0xFF, 0x00, 0xFF)     # the menus' plain background, a color none of theirs is near: what is not it is an item
WIDE_MARGIN = 54                   # title_config.h TITLE_WIDE_MARGIN

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)
    return ok


# --- pictures -----------------------------------------------------------------------

def drawn(w, h, kind):
    """A button picture, drawn rather than kept: a plate with a rim and a
    gem, red for the button, green for the one under the cursor."""
    from fm_editor import pngio
    out = bytearray(w * h * 4)
    body = {"red": (150, 24, 36), "green": (24, 150, 60), "blue": (30, 60, 170), "gold": (170, 130, 20)}[kind]
    for y in range(h):
        for x in range(w):
            rim = min(x, y, w - 1 - x, h - 1 - y) < max(2, h // 10)
            gem = math.hypot(x - w * 0.15, y - h / 2) < h * 0.25
            r, g, b = (240, 200, 90) if rim else (250, 250, 250) if gem else body
            out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, 255))
    return pngio.Image(w, h, bytes(out))


def pictures(folder: Path) -> dict:
    from fm_editor import pngio
    folder.mkdir(parents=True, exist_ok=True)
    made = {"gallery": drawn(416, 112, "red"), "gallery-on": drawn(416, 112, "green"),
            "quick": drawn(312, 84, "blue"), "quick-on": drawn(312, 84, "gold")}
    paths = {}
    for name, image in made.items():
        paths[name] = folder / f"{name}.png"
        pngio.write(paths[name], image)
    return paths


def screen(path: Path):
    """The whole display (the editor's window on it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["import", "-window", "root", str(path)], check=False)


# --- the editor ------------------------------------------------------------------------

def make_mod(game: Path, folder: Path, art: dict, editor_shots: Path) -> dict:
    """The mod, through the Menus page; what the editor predicts of each
    menu: {menu: [(name, x, y, (left, top, w, h) unselected, same selected)]}."""
    from fm_editor import manifest, validate
    from fm_editor.app import App
    from fm_editor.ui_title import item_look, menu_warnings, opaque
    app = App(ask=False, autostart=False)
    app.geometry("1560x960+0+0")
    app.update()
    app.start(str(game), None, False)
    app.update()
    app.info.vars["id"].set(MOD)
    app.info.vars["name"].set("Menu sizes test")
    assert app.info.commit()
    tab = app.ui
    app.notebook.select(tab)

    def page(name):
        tab.page_name.set(name)
        tab.show_page()
        app.update()
        return tab.pages[name]

    def choose(path):
        return mock.patch("fm_editor.file_dialogs.askopenfilename", return_value=str(path))

    def shoot(name):
        app.update()
        time.sleep(0.3)
        app.update()
        screen(editor_shots / name)

    title = page("title")
    for layer in ("logo", "copyright"):
        title.select(layer)
        title.show_box.current(2 - 1)               # "With PUSH START"
        title.show_box.event_generate("<<ComboboxSelected>>")
        app.update()
    menu = page("menu")
    menu.background_chosen()
    menu.background.picture.set(False)
    menu.background.set("picture", False, True)
    menu.background.shade.set(False)
    menu.background.set("shade", False, True)
    menu.background.set("color", "#%02X%02X%02X" % BACKGROUND)
    # All buttons at 90 %.
    menu.all_scale.set("90")
    menu.all_typed()
    # LOAD bigger, typed; 2P DUEL smaller, the wheel; OPTION as SETTINGS, the slider.
    menu.pick("load")
    menu.item_vars["scale"].set("150")
    menu.item_typed("scale")
    menu.wheel(("item", "duel"), -1)
    menu.wheel(("item", "duel"), -1)
    menu.pick("trade")
    menu.toggle_hidden()
    menu.pick("options")
    menu.item_vars["label"].set("SETTINGS")
    menu.item_typed("label")
    menu.slid("130")
    # CREDITS: words, smaller.
    menu.add_button()
    menu.item_vars["label"].set("CREDITS")
    menu.item_typed("label")
    menu.item_vars["notice_title"].set("Credits")
    menu.item_vars["notice"].set("Sized with the FM Editor.")
    menu.item_typed("notice")
    menu.item_vars["scale"].set("60")
    menu.item_typed("scale")
    # GALLERY: a picture and one for the cursor, bigger, starts a new game.
    menu.add_button()
    menu.item_vars["label"].set("")
    menu.item_typed("label")
    with choose(art["gallery"]):
        menu.item_image("image")
    with choose(art["gallery-on"]):
        menu.item_image("selected_image")
    menu.fill_form()
    menu.action_box.current(menu.action_choices.index("new_game"))
    menu.set_action()
    for _ in range(4):
        menu.wheel(("item", menu.chosen), 1)
    gallery = menu.chosen
    shoot("01-menus-page-first.png")
    # The second menu: CAMPAIGN bigger, a QUICK DUEL picture smaller.
    menu.menu.set(1)
    menu.switch_menu()
    menu.pick("campaign")
    menu.item_vars["scale"].set("140")
    menu.item_typed("scale")
    menu.add_button()
    with choose(art["quick"]):
        menu.item_image("image")
    with choose(art["quick-on"]):
        menu.item_image("selected_image")
    menu.fill_form()
    menu.action_box.current(menu.action_choices.index("free_duel"))
    menu.set_action()
    menu.slid("70")
    quick = menu.chosen
    shoot("02-menus-page-second.png")
    data = app.project.other["menu"]
    buttons = {b["id"]: b for b in data.get("buttons", [])}
    check("the page writes the sizes", data.get("scale") == 90 and data["entries"]["load"].get("scale") == 150 and
          data["entries"]["duel"].get("scale") == 70 and data["entries"]["options"].get("scale") == 130 and
          data["entries"]["campaign"].get("scale") == 140 and buttons["button1"].get("scale") == 60 and
          buttons["button2"].get("scale") == 130 and buttons["button3"].get("scale") == 70,
          json.dumps({k: v for k, v in data.items() if k in ("scale", "entries", "buttons")}))
    scene = menu.scene()
    title_art = tab.title_art()
    predicted, warnings = {}, {}
    for which in (0, 1):
        menu.menu.set(which)
        menu.switch_menu()
        menu.draw()
        app.update()
        warnings[which] = menu_warnings(scene, which, menu.canvas.item_boxes)
        places = scene.places(which)
        rows = []
        for item, shown in scene.order(which):
            if not shown:
                continue
            x, y = places[item["name"]]
            boxes = []
            for selected in (False, True):
                picture, left, top, _ = item_look(scene, item, selected, title_art)
                x0, y0, x1, y1 = opaque(picture)
                boxes.append((x + left + x0, y + top + y0, x1 - x0, y1 - y0))
            rows.append((item["name"], x, y, boxes[0], boxes[1], item))
        predicted[which] = rows
    check("the page finds nothing that looks off", not warnings[0] and not warnings[1], str(warnings))
    issues = [str(i) for i in validate.validate(app.project) if i.area in ("UI", "Mod info")]
    check("the editor finds nothing wrong with the mod", not issues, "; ".join(issues))
    manifest.save_mod(app.project, folder)
    # The warning, shown and not kept: LOAD at 400 % runs into the others.
    menu.menu.set(0)
    menu.switch_menu()
    menu.pick("load")
    menu.item_vars["scale"].set("400")
    menu.item_typed("scale")
    text = menu.warning.cget("text")
    check("LOAD at 400 % is warned of", "⚠" in text and "Runs into" in text, text.replace("\n", " / "))
    shoot("03-menus-page-warning.png")
    app.dirty = False
    app.destroy()
    return {"predicted": predicted, "gallery": gallery, "quick": quick}


# --- the game -----------------------------------------------------------------------

def game(executable, out, mods, name, mod=MOD, headless=True, settings=None):
    from yfm_control import Game
    flags = {"mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0}
    for other in (MOD, MOD + "-look"):
        flags[f"mod.{other}"] = 1 if other == mod else 0
    flags.update(settings or {})
    return Game(executable=executable, out=out / name, mods_dir=mods, settings=flags, headless=headless,
                env={"MEMORIES_DUMP_PICTURE": "1"})


def to_title(g):
    for i in range(240):
        g.step(30)
        if g.u32("D_80184558"):
            break
        if i % 4 == 3:
            g.press("start")
    g.step(150)


def first_menu(g):
    to_title(g)
    g.press("start")
    g.step(120)


def second_menu(g):
    """The second menu (a game loaded): Free Duel, its SELECT OPPONENT!
    box closed (Cross), and back out (Circle) to the title."""
    g.goto("free_duel")
    g.step(90)
    g.press("cross", hold=4, after=60)
    g.press_until(lambda g: g.mode() == 8, "circle", every=60, timeout=1200, what="back to the title")
    g.step(150)


def read_png(path):
    from fm_editor import pngio
    return pngio.read(path)


def segments(image, scale, margin):
    """The items as drawn: runs of rows with something not the background
    in them, each (x0, y0, x1, y1) in the game's pixels (x from the 4:3
    picture's left)."""
    # Widescreen: the 4:3 picture between black sides, the menus in it.
    left, right = margin * scale, (margin + 320) * scale
    bg = image.pixel(left + 2, 2)[:3]
    h = image.height
    rows = []
    boxes = []
    for y in range(h):
        xs = [x for x in range(left, right) if max(abs(a - b) for a, b in zip(image.pixel(x, y)[:3], bg)) > 40]
        rows.append((min(xs), max(xs)) if xs else None)
    y = 0
    while y < h:
        if rows[y] is None:
            y += 1
            continue
        top, x0, x1 = y, rows[y][0], rows[y][1]
        while y < h and rows[y] is not None:
            x0, x1 = min(x0, rows[y][0]), max(x1, rows[y][1])
            y += 1
        boxes.append((x0 / scale - margin, top / scale, (x1 + 1) / scale - margin, y / scale))
    return boxes


def color_in(image, box, scale, margin, test):
    x0, y0, x1, y1 = box
    return sum(1 for y in range(int(y0 * scale), int(y1 * scale)) for x in range(int((x0 + margin) * scale),
                                                                                   int((x1 + margin) * scale))
               if test(*image.pixel(x, y)[:3]))


def red_frame(r, g, b):
    """The cursor's frame: red and orange (the entries' and a label's)."""
    return r > 140 and g < 150 and b < 60 and r > g + 60


def near(a, b, slack=1.0):
    return all(abs(p - q) <= slack for p, q in zip(a, b))


def to_top(g, rows, shots, scale, margin):
    """The cursor down (it wraps) until the top row is lit, as the game's
    own entry there is under the cursor: whether it got there."""
    probe = shots / "probe.png"
    try:
        for _ in range(len(rows) + 1):
            image = read_png(g.shot(probe))
            found = segments(image, scale, margin)
            if found and color_in(image, found[0], scale, margin, red_frame) > 20:
                return True
            g.press("down", hold=4, after=16)
            g.step(30)
        return False
    finally:
        probe.unlink(missing_ok=True)


def walk_menu(g, which, rows, shots, tag, scale, margin):
    """The cursor on each item in turn: a picture each, each item measured."""
    names = [r[0] for r in rows]
    bad = []
    cursor_bad = []
    measured = {}
    for k in range(len(rows)):
        if k:
            g.press("down", hold=4, after=16)
            g.step(30)
        path = shots / f"{tag}-menu{which + 1}-{k + 1}-{names[k].split(':')[-1]}.png"
        g.shot(path)
        image = read_png(path)
        found = segments(image, scale, margin)
        if len(found) != len(rows):
            bad.append(f"{path.name}: {len(found)} items drawn, {len(rows)} wanted")
            continue
        for row, (name, x, y, plain, lit, item) in enumerate(rows):
            box = found[row]
            want = lit if row == k else plain
            want = (want[0], want[1], want[0] + want[2], want[1] + want[3])
            # Words are set by the game in its own face: their frame's
            # width may differ from the editor's guess; its middle, height
            # and place may not.
            words = not item.get("image") and (item.get("label") or not item["entry"])
            if words:
                fits = abs((box[0] + box[2]) / 2 - x) <= 1 and near((box[1], box[3]), (want[1], want[3]))
            else:
                fits = near(box, want)
            if not fits:
                bad.append(f"{path.name}: {name} drawn at {tuple(round(v, 1) for v in box)}, the editor's "
                           f"{want}")
            measured.setdefault(name, {})[row == k] = box
        # The item under the cursor: its look there.
        name, _, _, _, _, item = rows[k]
        box = found[k]
        if item.get("selected_image"):
            gold_or_green = color_in(image, box, scale, margin,
                                      lambda r, g_, b: (g_ > r + 60 and g_ > b + 40) or (r > 150 and g_ > 110 and b < 60))
            if gold_or_green < 20:
                cursor_bad.append(f"{name}: not its picture for the cursor")
        elif color_in(image, box, scale, margin, red_frame) < 20:
            cursor_bad.append(f"{name}: no red frame under the cursor")
    check(f"{tag}: menu {which + 1} drawn where and as big as the editor shows it, the cursor on each item",
          not bad, "; ".join(bad[:4]))
    # The cursor's look about the button's own middle (its box is checked
    # against the editor's above: the game's own entries' look for the
    # cursor is a little wider than the other, at any size).
    unfit = [] if len(measured) == len(rows) else [f"{len(rows) - len(measured)} items not measured"]
    for name, boxes in measured.items():
        if True in boxes and False in boxes:
            lit, plain = boxes[True], boxes[False]
            if not near(((lit[0] + lit[2]) / 2, (lit[1] + lit[3]) / 2), ((plain[0] + plain[2]) / 2,
                                                                     (plain[1] + plain[3]) / 2)):
                unfit.append(f"{name}: {lit} under the cursor, {plain} not")
    check(f"{tag}: menu {which + 1}'s cursor look fits each resized button", not unfit and not cursor_bad,
          "; ".join(unfit + cursor_bad))
    return measured


def menus_measured(executable, out, mods, shots, predicted, tag, settings, headless=True):
    scale = settings.get("internal_scale", 1)
    margin = WIDE_MARGIN if settings.get("aspect") == 2 else 0
    with game(executable, out, mods, tag, headless=headless, settings=settings) as g:
        first_menu(g)
        image = read_png(g.shot(shots / f"{tag}-menu1-open.png"))
        check(f"{tag}: the picture is {('wide ' if margin else '')}{scale}x",
              image.width == (320 + 2 * margin) * scale and image.height == 240 * scale, f"{image.size}")
        sizes = walk_menu(g, 0, predicted[0], shots, tag, scale, margin)
        second_menu(g)
        check(f"{tag}: the second menu's cursor on its top row", to_top(g, predicted[1], shots, scale, margin))
        walk_menu(g, 1, predicted[1], shots, tag, scale, margin)
        return sizes


def presses(executable, out, mods, shots, made):
    """A resized button pressed does what it does."""
    with game(executable, out, mods, "press") as g:
        first_menu(g)
        g.save("first-menu.state")
        rows = made["predicted"][0]
        names = [r[0] for r in rows]
        # NEW GAME as the game has it, for what GALLERY (its action new_game) must do.
        g.load("first-menu.state")
        g.press("cross", hold=4, after=20)
        g.wait_until(lambda g: g.mode() != 8, 1200, what="a new game")
        g.step(120)
        new_game = (g.mode(), g.u8("D_8009B26C"))
        for name, wanted, what in ((made["gallery"], new_game, "a new game, as NEW GAME does"),
                                   ("options", (11, None), "the options")):
            g.load("first-menu.state")
            for _ in range(names.index(name)):
                g.press("down", hold=4, after=16)
            g.step(20)
            g.shot(shots / f"press-{name.split(':')[-1]}-chosen.png")
            g.press("cross", hold=4, after=20)
            g.wait_until(lambda g: g.mode() != 8, 1200, what=what)
            g.step(120)
            g.shot(shots / f"press-{name.split(':')[-1]}-done.png")
            got = (g.mode(), g.u8("D_8009B26C") if wanted[1] is not None else None)
            check(f"{name} (resized) pressed opens {what}", got == wanted, f"mode byte {got}, wanted {wanted}")
        g.load("first-menu.state")
        second_menu(g)
        names = [r[0] for r in made["predicted"][1]]
        lit = to_top(g, made["predicted"][1], shots, 1, 0)
        for _ in range(names.index(made["quick"])):
            g.press("down", hold=4, after=16)
        g.step(20)
        g.shot(shots / "press-quick-chosen.png")
        g.press("cross", hold=4, after=20)
        g.wait_until(lambda g: g.mode() == 6, 1200, what="Free Duel")
        g.step(120)
        g.shot(shots / "press-quick-done.png")
        check("QUICK DUEL (a picture at 70 %) pressed opens Free Duel", lit and g.mode() == 6, f"mode {g.mode()}")


def look(executable, out, mods, shots):
    """The same sizes over the game's own background and logo, sliding in."""
    for tag, settings, headless in (("look-1x", {}, True), ("look-2x", {"internal_scale": 2, "scale": 2}, False),
                                    ("look-2x-wide", {"internal_scale": 2, "scale": 2, "aspect": 2}, False)):
        with game(executable, out, mods, tag, mod=MOD + "-look", headless=headless, settings=settings) as g:
            to_title(g)
            g.press("start", hold=4, after=0)
            for frame in range(12):
                g.step(4)
                g.shot(shots / f"{tag}-menu1-slide-{frame:02d}.png")
            g.step(120)
            g.shot(shots / f"{tag}-menu1.png")
            g.press("down", hold=4, after=16)
            g.step(30)
            g.shot(shots / f"{tag}-menu1-load.png")
            second_menu(g)
            g.shot(shots / f"{tag}-menu2.png")


def baseline(executable, base, out, mods):
    """Without the mod: the same VRAM hashes as the build before, through
    boot, the title, both menus and the cursor moving."""
    from yfm_control import Game
    sequences = []
    for exe, name in ((base, "baseline"), (executable, "this-build")):
        hashes = []
        with Game(executable=exe, out=out / f"nomod-{name}", mods_dir=mods,
                  settings={f"mod.{MOD}": 0, f"mod.{MOD}-look": 0, "mod.3d-monsters": 0, "mod.hand-camera": 0,
                            "mod.ai-hard-mode": 0}) as g:
            for i in range(60):
                g.step(30)
                hashes.append(g.hash())
                if g.u32("D_80184558"):
                    break
                if i % 4 == 3:
                    g.press("start")
            for _ in range(10):
                g.step(20)
                hashes.append(g.hash())
            g.press("start")
            for _ in range(12):
                g.step(6)
                hashes.append(g.hash())
            for _ in range(6):
                g.press("down", hold=4, after=16)
                hashes.append(g.hash())
            second_menu(g)
            for _ in range(20):
                g.step(10)
                hashes.append(g.hash())
            for _ in range(7):
                g.press("down", hold=4, after=16)
                hashes.append(g.hash())
            g.shot(out / f"nomod-{name}-menu2.png")
        sequences.append(hashes)
    same = sum(1 for a, b in zip(*sequences) if a == b)
    check("without the mod, every frame as the baseline build's", sequences[0] == sequences[1],
          f"{same} of {len(sequences[0])} VRAM hashes equal")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", default=str(EXECUTABLE))
    parser.add_argument("--out", default=str(ROOT / "tmp/pc/editor-menu"))
    parser.add_argument("--baseline", help="a build without the menus' sizes, for the no-mod frames")
    parser.add_argument("--skip", default="", help="steps to leave out: 1x,wide,2x,2x-wide,press,look")
    args = parser.parse_args()
    os.environ.setdefault("MEMORIES_NO_MONITOR", "1")
    out = Path(args.out).resolve()
    shots, editor = out / "shots", out / "editor"
    for folder in (out / "mods", shots, editor):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    skip = set(filter(None, args.skip.split(",")))
    art = pictures(out / "art")
    print("the mod, through the Menus page:", flush=True)
    made = make_mod(ROOT / "game", out / "mods" / MOD, art, editor)
    # The look: the same mod over the game's own background and logo.
    look_dir = out / "mods" / (MOD + "-look")
    shutil.copytree(out / "mods" / MOD, look_dir)
    data = json.loads((look_dir / "mod.json").read_text(encoding="utf-8"))
    data["id"] = MOD + "-look"
    data["menu"].pop("background", None)
    data.pop("title", None)
    (look_dir / "mod.json").write_text(json.dumps(data, indent=4), encoding="utf-8")
    mods = out / "mods"
    runs = out / "runs"
    for tag, settings, headless in (("1x", {}, True), ("wide", {"aspect": 2}, True),
                                    ("2x", {"internal_scale": 2, "scale": 2}, False),
                                    ("2x-wide", {"internal_scale": 2, "scale": 2, "aspect": 2}, False)):
        if tag in skip:
            continue
        print(f"the menus measured, {tag}:", flush=True)
        menus_measured(args.executable, runs, mods, shots, made["predicted"], tag, settings, headless)
    if "press" not in skip:
        print("resized buttons pressed:", flush=True)
        presses(args.executable, runs, mods, shots, made)
    if "look" not in skip:
        print("the look:", flush=True)
        look(args.executable, runs, mods, shots)
    if args.baseline:
        print("without the mod:", flush=True)
        baseline(args.executable, args.baseline, runs, mods)
    failed = [name for name, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} checks passed; pictures in {shots} and {editor}",
          flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
