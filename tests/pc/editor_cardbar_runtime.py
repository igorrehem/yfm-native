#!/usr/bin/env python3
"""Live check of the card bar's parts (built game and user-supplied disc).

The duel's card bar shows the card under the cursor: its name, the sword
and ATK, the shield and DEF, the type's icon, the guardian stars (one on
the field), a magic or trap card's word. A mod's "ui"."duel"."card_bar"
moves each of them about on the bar, colors, hides them and spreads the
name's letters (notes/modding.md, "The card bar's parts"). Two mods are
made through the FM Editor's UI > Duel page, with its own controls:

* "rearranged": ATK and DEF to the bar's left, red and blue; the name after
  them, gold, a pixel down; the stars and the word where the type's icon
  was, green, and the type's icon at the right end of the bar's dark panel;
* "hidden": every part hidden;
* "spaced": the name's letters two pixels further apart, from the left of
  the bar's dark panel (played for the hand's first three pictures).

The same scripted duel is played three times -- without a mod, with
"hidden" and with "rearranged" -- with a picture at each step: the hand's
cursor on a monster, a magic card and a trap; two cards marked to fuse;
the fused monster being placed (the bar's higher look, over the hand); the
field browsed (the player's monster, an empty zone, the opponent's
face-down card); a magic card burning the opponent; an attack's target
chosen (GUARDIAN STAR over the field); battles; the opponent's turns; the
results. For each step, from where the game holds the bar's text boxes:

* without the parts ("hidden") the frame is the retail one except where
  the parts are, and there nothing of theirs is drawn;
* "rearranged" is "hidden" with each part's own pixels (where retail and
  hidden differ by more than a step of the GPU's color) put where the mod moved
  them, in its color, the name's letters spread, within the GPU's 5-bit
  rounding; where a part was or went and none of its own lands, the bar
  as "hidden" has it (a glyph's dark half-transparent texels blend with
  what is under them); the rest of the frame exactly the retail one;
* the editor's preview of the bar (duel_screen.bar_words) over "hidden"
  is "rearranged" (the card the game shows, its name, stats and icons).

Then "rearranged" at Internal 2x with HD text, and 16:9, in a window; and
without a mod, the same frames as the build given by --baseline. Pictures
go to <out>/shots, the editor's to <out>/editor; nothing is kept in the
repository.

    MEMORIES_NO_MONITOR=1 xvfb-run -n 221 python3 tests/pc/editor_cardbar_runtime.py \\
        [--executable PATH] [--out DIR] [--baseline PATH]
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
OPPONENT = 1                    # Simon Muran: a duel the player's deck wins
PARTS = ("name", "atk", "def", "type", "stars", "kind")
# Where each part is in its text box as the game lays it out (ui_rules.PART_HOME):
# the name's rows are 2 to 14, its letters 8 apart.
CHANNELS, CHANNEL_SIZE = 4, 0x64
BAR_TEXTS = range(0x50, 0x56)
TOLERANCE = 24                  # a tinted texel: the GPU's 5-bit color against ours
STEP = 8                        # one step of the GPU's 5-bit color: a part's pixel differs by more
REARRANGED = {"atk": (-195, 0, 0xFF8080), "def": (-195, 0, 0x80C0FF), "type": (35, 0, None),
              "stars": (-18, 0, 0xA0FFA0), "kind": (-18, 0, 0x80FF80)}
NAME = {"x": 44, "y": 1, "tint": 0xFFE040}
SPACED = 2                      # the "spaced" mod's name: two pixels more between letters, from the bar's left

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)
    return ok


# --- the editor ---------------------------------------------------------------------

def make_mods(game: Path, mods: Path, editor: Path) -> dict:
    """Both mods through the Duel page; its picture beside them."""
    from fm_editor import manifest, ui_rules
    from fm_editor.app import App
    app = App(ask=False, autostart=False)
    app.update()
    app.start(str(game), None, False)
    app.update()
    tab = app.ui
    app.notebook.select(tab)
    tab.page_name.set("duel")
    tab.show_page()
    app.update()
    page = tab.pages["duel"]
    made = {}
    for mod in ("hidden", "spaced", "rearranged"):
        app.info.vars["id"].set(f"cardbar-{mod}")
        app.info.vars["name"].set(f"Card bar {mod}")
        assert app.info.commit()
        for part in PARTS:              # back to the game's, one by one
            page.select(f"card_bar.{part}")
            page.reset()
        if mod == "hidden":
            for part in PARTS:
                page.select(f"card_bar.{part}")
                page.hidden.set(True)
                page.set_hidden()
        elif mod == "spaced":
            page.select("card_bar.name")
            page.moved("card_bar.name", 300, 0)
            page.vars["spacing"].set(str(SPACED))
            page.typed("spacing")
            check("the page brings a name spread too far right back on the bar",
                  page.element("card_bar.name").get("x") == ui_rules.part_range("name", SPACED)[1] == 12,
                  str(page.element("card_bar.name")))
            page.moved("card_bar.name", -400, 0)
            page.set_color("tint", NAME["tint"])
        else:
            for part, (x, y, tint) in REARRANGED.items():
                page.select(f"card_bar.{part}")
                page.moved(f"card_bar.{part}", x, y)
                if tint is not None:
                    page.set_color("tint", tint)
            page.select("card_bar.name")
            page.moved("card_bar.name", 300, NAME["y"])        # as far right as it stays on the bar
            check("the page keeps the name on the bar's panel (28 letters from x 66 reach its right)",
                  page.element("card_bar.name").get("x") == ui_rules.part_range("name")[1] == 66,
                  str(page.element("card_bar.name")))
            page.vars["x"].set(str(NAME["x"]))
            page.typed("x")
            page.set_color("tint", NAME["tint"])
        bar = app.project.other["ui"]["duel"]["card_bar"]
        made[mod] = json.loads(json.dumps(bar))
        from fm_editor import validate
        issues = [str(i) for i in validate.validate(app.project) if i.area in ("UI", "Mod info")]
        check(f"{mod}: the editor finds nothing wrong", not issues, "; ".join(issues))
        manifest.save_mod(app.project, mods / f"cardbar-{mod}")
    want = {"atk": {"x": -195, "tint": "#FF8080"}, "def": {"x": -195, "tint": "#80C0FF"}, "type": {"x": 35},
            "stars": {"x": -18, "tint": "#A0FFA0"}, "kind": {"x": -18, "tint": "#80FF80"},
            "name": {"x": 44, "y": 1, "tint": "#FFE040"}}
    check("the rearranged bar as the page wrote it", made["rearranged"] == want, json.dumps(made["rearranged"]))
    check("the hidden bar as the page wrote it", made["hidden"] == {p: {"hide": True} for p in PARTS},
          json.dumps(made["hidden"]))
    check("the spaced bar as the page wrote it",
          made["spaced"] == {"name": {"x": -2, "spacing": SPACED, "tint": "#FFE040"}}, json.dumps(made["spaced"]))
    # The page's picture: the window, each part chosen in turn.
    app.deiconify()
    app.geometry("1500x900+0+0")
    app.update()
    page.view.seen = None
    page.view.fit()
    app.update()
    editor.mkdir(parents=True, exist_ok=True)
    shots = {}
    for key, shows in (("card_bar.name", "Monster"), ("card_bar.atk", "Monster"), ("card_bar.kind", "Magic card")):
        page.bar_shows.set(shows)
        page.select(key)
        page.draw()
        app.update()
        app.after(300)
        app.update()
        path = editor / f"page-{key.split('.')[1]}-{shows.split()[0].lower()}.png"
        subprocess.run(["import", "-window", str(app.winfo_id()), str(path)], check=False)
        stage = editor / f"stage-{key.split('.')[1]}-{shows.split()[0].lower()}.png"
        subprocess.run(["import", "-window", str(page.stage.winfo_id()), str(stage)], check=False)
        shots[key, shows] = (path, stage, page.stage.zoom, page.warning.cget("text"))
    page.bar_shows.set("Monster")
    app.dirty = False
    app.destroy()
    return {"mods": made, "shots": shots}


# --- the game -----------------------------------------------------------------------

def game(executable, out, mods, name, mod=None, headless=True, settings=None, env=None):
    from yfm_control import Game
    flags = {"mod.cardbar-hidden": 0, "mod.cardbar-rearranged": 0, "mod.cardbar-spaced": 0, "mod.3d-monsters": 0,
             "mod.hand-camera": 0, "mod.ai-hard-mode": 0}
    if mod:
        flags[f"mod.cardbar-{mod}"] = 1
    flags.update(settings or {})
    return Game(executable=executable, out=out / name, mods_dir=mods, settings=flags, headless=headless,
                env=dict({"MEMORIES_DUMP_PICTURE": "1"}, **(env or {})))


def bar_boxes(g) -> list:
    """The card bar's text boxes on the screen: (x, y, string) of each drawn
    text of strings 0x50-0x55 (func_80023144), from its display object; an
    even string is a monster's, an odd one another card's."""
    base = g.address("D_800EB0F8")
    out = []
    for i in range(CHANNELS):
        data = g.peek(base + i * CHANNEL_SIZE, CHANNEL_SIZE)
        text, = struct.unpack_from("<H", data, 0x36)
        obj, = struct.unpack_from("<I", data, 0x28)
        if text in BAR_TEXTS and obj:
            x, y = struct.unpack("<hh", g.peek(obj, 0x34)[0x30:0x34])
            if -16 < y < 240:
                out.append((x, y, text))
    return sorted(out)


def deck_cards():
    from fm_editor import disc, gamedata
    files = disc.load(ROOT / "game")
    data = gamedata.load_game(files)
    names = {c.id: c.name for c in data.cards.values()}
    by = {n: next(cid for cid, name in names.items() if name == n) for n in
          ("Mystical Elf", "Blue-eyes White Dragon", "Dian Keto the Cure Master")}
    burn = next(cid for cid, n in names.items() if n == "Hinotama" and data.cards[cid].type == gamedata.TYPE_MAGIC)
    trap = next(cid for cid in sorted(data.cards) if data.cards[cid].type == gamedata.TYPE_TRAP)
    pair = next((a, b) for (a, b), r in data.fusions.items() if a == by["Mystical Elf"] and r and
                names.get(r) == "Dark Elf")
    hand = [pair[0], pair[1], burn, trap, by["Blue-eyes White Dragon"]]
    deck = hand + [by["Blue-eyes White Dragon"], burn, by["Dian Keto the Cure Master"]] + list(range(3, 35))
    return files, data, hand, deck[:40], burn


def play(executable, out, mods, name, mod, shots: Path, settings=None, headless=True, window=None, hand_only=False):
    """The scripted duel; the pictures and where the bar's texts were, by step."""
    from yfm_control import DUEL_PHASES
    files, data, hand, deck, burn = deck_cards()
    steps = []
    shots.mkdir(parents=True, exist_ok=True)

    def shot(label):
        path = shots / f"{len(steps) + 1:02d}-{label}.png"
        g.shot(path)
        if window:
            window(g, shots / f"{len(steps) + 1:02d}-{label}-window.png")
        steps.append({"label": label, "path": str(path), "boxes": bar_boxes(g),
                      "card": g.u16("gDuel_wSelectedCardID")})
        return path

    with game(executable, out, mods, name, mod, headless=headless, settings=settings) as g:
        g.goto("duel", opponent=OPPONENT, deck=deck)
        g.duel_ready(before_deal=lambda g: g.arrange_deck(0, hand))
        g.step(20)
        shot("hand-monster")
        g._hand_to(2)
        g.step(10)
        shot("hand-magic")
        g._hand_to(3)
        g.step(10)
        shot("hand-trap")
        if hand_only:
            (shots / "steps.json").write_text(json.dumps(steps, indent=1))
            return steps, True, 0, 0
        # A fusion: both marked, then placed (the bar's higher look over the hand).
        for slot in (0, 1):
            g._hand_to(slot)
            g.press("up", hold=4, after=16)
        shot("fusion-marked")
        g.press("cross", hold=4, after=30)
        g.press("right", hold=4, after=12)
        g.press_until(lambda g: g.phase() != DUEL_PHASES["hand"] or g.duel_over(), "cross", every=40,
                      timeout=1200, what="the zone choice")
        g.step(30)
        shot("fusion-placing")
        g.press_until(lambda g: g.phase() != DUEL_PHASES["placement"] or g.duel_over(), "cross", every=40,
                      timeout=1200, what="the zone")
        if g.phase() == DUEL_PHASES["position"]:
            shot("fusion-star")
            g.press_until(lambda g: g.phase() != DUEL_PHASES["position"] or g.duel_over(), "cross", every=40,
                          timeout=1200, what="the guardian star")
        g._settle()
        g.step(30)
        shot("field-own-fused")
        g.press("up", hold=4, after=20)
        shot("field-own-spell-zone")
        g.press("up", hold=4, after=20)
        shot("field-opponent-row")
        g.press("down", hold=4, after=20)
        g.press("down", hold=4, after=20)
        turns, battles = 0, 0
        while not g.duel_over() and turns < 24:
            turns += 1
            if turns > 1:
                g.wait_turn(("hand",), 30000)
                if g.duel_over():
                    break
                g.step(20)
                shot(f"turn{turns}-hand")
                slots = {i: c for i, c in enumerate(g.duel()[0]["hand"]) if c}
                magic = next((i for i, c in slots.items() if c["id"] == burn), None)
                monsters = [i for i, c in slots.items() if c["attack"] > 0]
                if magic is not None and turns == 2:
                    g._hand_to(magic)
                    g.step(10)
                    shot(f"turn{turns}-hand-magic")
                    g.play_card(magic, face_up=True)
                    g.step(30)
                    shot(f"turn{turns}-magic-burned")
                elif monsters:
                    g.play_card(max(monsters, key=lambda i: slots[i]["attack"]), face_up=True)
                    g.step(20)
                    shot(f"turn{turns}-played")
                else:
                    g.play_card(min(slots), face_up=False)
            for column in range(5 if turns > 1 else 0):
                if g.duel_over() or g.turn() != 0 or g.phase() != DUEL_PHASES["field"]:
                    break
                if not g.field()[2][column]:
                    continue
                theirs = [i for i, c in enumerate(g.field()[1]) if c]
                if theirs and battles == 0:
                    # Their card under the field's cursor, then the target chosen.
                    try:
                        aim(g, column, theirs[0], shot)
                    except Exception as problem:         # noqa: BLE001
                        print(f"    (no aim from column {column}: {problem})", flush=True)
                        continue
                    battles += 1
                    g.step(40)
                    shot("battle")
                    g._settle()
                    g.step(30)
                    shot(f"turn{turns}-after-battle")
                    continue
                try:
                    g.attack(column, theirs[0] if theirs else None)
                    battles += 1
                except Exception as problem:             # noqa: BLE001
                    print(f"    (no attack from column {column}: {problem})", flush=True)
                    continue
            if g.duel_over():
                break
            g.press_until(lambda g: g.turn() != 0 or g.duel_over(), "start", every=60, timeout=1200,
                          what="the end of the turn")
            if turns <= 2 and not g.duel_over():
                g.wait_until(lambda g: g.duel_over() or g.turn() == 1, 600, what="the opponent's turn")
                for k in range(3):
                    g.step(70)
                    if g.duel_over() or g.turn() != 1:
                        break
                    shot(f"turn{turns}-opponent-{k}")
        for _ in range(12):
            g.step(120)
            if g.phase() in (DUEL_PHASES["result"], DUEL_PHASES["rewards"]) or g.mode() != 3:
                break
        shot("result")
        over = g.duel_over()
    (shots / "steps.json").write_text(json.dumps(steps, indent=1))
    return steps, over, turns, battles


def aim(g, column, target, shot):
    """The field's cursor to the player's monster in `column` and then the
    opponent's card in `target`'s column (the bar shows it), then the
    attack's target chosen (the bar's higher look, GUARDIAN STAR)."""
    from yfm_control import FIELD_CURSOR, TARGET_CURSOR
    g.wait_turn()
    for _ in range(4):
        row = g.u8(FIELD_CURSOR + 1)
        if row == 1:
            break
        g.press("down" if row < 1 else "up", hold=4, after=16)
    g._cursor_to(FIELD_CURSOR, target, "field")
    g.step(20)
    shot("field-opponent-card")
    for _ in range(4):
        row = g.u8(FIELD_CURSOR + 1)
        if row == 2:
            break
        g.press("down" if row < 2 else "up", hold=4, after=16)
    g._cursor_to(FIELD_CURSOR, column, "field")
    g.step(20)
    shot("field-own-monster")
    g.press("cross", hold=4, after=40)
    g._cursor_to(TARGET_CURSOR, target, "target")
    g.step(20)
    shot("attack-target")
    g.press("cross", hold=1, after=0)


# --- the pictures -------------------------------------------------------------------

def read(path):
    from fm_editor import pngio
    return pngio.read(path)


def homes(box):
    """Each part's rectangle on the screen as the game draws it, for the
    text at `box` (x, y, string): ui_rules.PART_HOME, a monster's (its name
    ends before the sword at 195, 24 letters) or another card's (its name
    before its icon at 237, 28 letters)."""
    from fm_editor import ui_rules
    x0, y0, text = box
    monster = text % 2 == 0
    out = {}
    for part in (("name", "atk", "def", "type", "stars") if monster else ("name", "type", "kind")):
        x, y, w, h = ui_rules.part_home(part)
        if part == "name":
            w = 195 if monster else 237
        out[part] = (x0 + x, y0 + y, w, h)
    return out


def moved_rect(part, bar):
    """How a part is moved by a mod's card_bar `bar`: (dx, dy) and the
    name's spacing."""
    from fm_editor import ui_rules
    element = bar.get(part, {})
    dx, dy = ui_rules.part_offset(part, element)
    spacing = ui_rules.part_spacing(element) if part == "name" else 0
    return dx, dy, spacing


def tint_of(part, bar):
    from fm_editor import ui_assets
    return ui_assets.parse_color(bar.get(part, {}).get("tint"))


def compare_step(step, retail, hidden, rearranged, bar):
    """(problems with hiding, problems with rearranging, pixels put): the
    three frames of one step against each other."""
    a, b, c = read(retail), read(hidden), read(rearranged)
    w, h = a.width, a.height
    part_pixels = {}            # (x, y) -> part, the pixels a part has (retail and hidden differ)
    owned = set()               # every part's rectangle, at home and moved
    for box in step["boxes"]:
        for part, (x0, y0, pw, ph) in homes(box).items():
            dx, dy, spacing = moved_rect(part, bar)
            reach = spacing * 28 if spacing > 0 else 0
            for y in range(max(0, y0), min(h, y0 + ph)):
                for x in range(max(0, x0), min(w, x0 + pw)):
                    owned.add((x, y))
                    pa, pb = a.pixel(x, y)[:3], b.pixel(x, y)[:3]
                    if max(abs(pa[i] - pb[i]) for i in range(3)) > STEP:
                        part_pixels.setdefault((x, y), (part, box))
            for y in range(max(0, y0 + dy), min(h, y0 + ph + dy)):
                for x in range(max(0, x0 + dx), min(w, x0 + pw + dx + reach)):
                    owned.add((x, y))
    hide_bad = []
    for y in range(h):
        for x in range(w):
            if (x, y) not in owned and a.pixel(x, y)[:3] != b.pixel(x, y)[:3]:
                hide_bad.append((x, y))
    # The rearranged frame expected: hidden, with each part's pixels moved and
    # tinted; drawn last first (the name first, the ATK last: the order's
    # last-sorted is drawn first).
    expected = {}
    order = {p: i for i, p in enumerate(("name", "stars", "kind", "type", "def", "atk"))}
    for (x, y), (part, box) in sorted(part_pixels.items(), key=lambda kv: order[kv[1][0]]):
        dx, dy, spacing = moved_rect(part, bar)
        letter = (x - box[0]) // 8 if part == "name" else 0
        tint = tint_of(part, bar)
        at = (x + dx + spacing * letter, y + dy)
        if not (0 <= at[0] < w and 0 <= at[1] < h):
            continue
        factors = (tint >> 16 & 255, tint >> 8 & 255, tint & 255)
        here, there, drawn = b.pixel(x, y)[:3], b.pixel(*at)[:3], a.pixel(x, y)[:3]
        # An opaque texel is its own color wherever it goes; a half-transparent
        # one (the icons' dark edges) is half what is under it: its own half is
        # what it added at home.
        opaque = tuple(drawn[i] * factors[i] // 255 for i in range(3))
        half = tuple(max(0, min(255, (there[i] + max(0, 2 * drawn[i] - here[i]) * factors[i] // 255) // 2))
                     for i in range(3))
        expected[at] = (opaque, half)
    move_bad = []
    for y in range(h):
        for x in range(w):
            got = c.pixel(x, y)[:3]
            if (x, y) in expected:
                wants = expected[(x, y)]
                if all(any(abs(got[i] - want[i]) > TOLERANCE for i in range(3)) for want in wants):
                    move_bad.append((x, y, got, wants))
            elif (x, y) in owned:
                want = b.pixel(x, y)[:3]
                if any(abs(got[i] - want[i]) > TOLERANCE for i in range(3)):
                    move_bad.append((x, y, got, want))
            elif got != a.pixel(x, y)[:3]:
                move_bad.append((x, y, got, a.pixel(x, y)[:3]))
    return hide_bad, move_bad, len(expected)


def editor_matches(step, hidden, rearranged, bar, project_data, files):
    """The editor's preview of the bar's words (duel_screen.bar_words, the
    card the game shows, the rearranged parts) over the hidden frame: the
    rearranged frame, where they are drawn."""
    from types import SimpleNamespace
    from fm_editor import card_text, duel_screen, ui_assets
    b, c = read(hidden), read(rearranged)
    duel = ui_assets.DuelArt(files.wa)
    font = card_text.RetailFont(files.wa)
    project = SimpleNamespace(cards=project_data.cards)
    pieces = duel_screen.bar_words(project, files.wa, duel, font, step["card"], bar)
    box = step["boxes"][0]
    dx, dy = box[0] - 16, box[1] - 210
    bad = drawn = 0
    for picture, x, y, part in pieces:
        for py in range(picture.height):
            for px_ in range(picture.width):
                r, g, bl, alpha = picture.pixel(px_, py)
                if not alpha:
                    continue
                at = (x + px_ + dx, y + py + dy)
                if not (0 <= at[0] < c.width and 0 <= at[1] < c.height):
                    continue
                drawn += 1
                got = c.pixel(*at)[:3]
                if any(abs(got[i] - (r, g, bl)[i]) > 40 for i in range(3)):
                    bad += 1
    return bad, drawn


def side_by_side(game_frame, stage, out, zoom):
    """The game's frame beside the editor's stage, at the stage's zoom."""
    from PIL import Image
    a = Image.open(game_frame).convert("RGB").resize((320 * zoom, 240 * zoom), Image.NEAREST)
    b = Image.open(stage).convert("RGB")
    canvas = Image.new("RGB", (a.width + b.width + 8, max(a.height, b.height)), (40, 40, 40))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 8, 0))
    canvas.save(out)


def window_runs(executable, out, mods, shots):
    """Rearranged at Internal 2x with HD text, then 16:9, in a window."""
    from PIL import Image

    def screen(g, path):
        subprocess.run(["import", "-window", "root", str(path)], check=False)
    found = {}
    for name, settings in (("hd2x", {"internal_scale": 2, "hd_text": 1, "scale": 2}),
                           ("wide", {"aspect": 2, "scale": 2})):
        steps, over, _, _ = play(executable, out, mods, f"window-{name}", "rearranged", shots / name,
                                 settings=settings, headless=False, window=screen if name == "wide" else None)
        found[name] = steps
    # At 2x the name's gold letters where the mod put them, none at the game's place.
    steps = found["hd2x"]
    first = next(s for s in steps if s["label"] == "hand-monster")
    image = Image.open(first["path"]).convert("RGB")
    scale = image.width // 320
    box = first["boxes"][0]

    def gold(x0, y0, x1, y1):
        return sum(1 for y in range(y0 * scale, y1 * scale) for x in range(x0 * scale, x1 * scale)
                   if (lambda p: p[0] > 150 and p[1] > 120 and p[2] < 90)(image.getpixel((x, y))))
    moved = gold(box[0] + NAME["x"], box[1] + 3, box[0] + NAME["x"] + 60, box[1] + 15)
    home = gold(box[0], box[1] + 2, box[0] + NAME["x"] - 8, box[1] + 14)
    check("internal 2x, HD text: the name gold where the mod put it, not at the game's place",
          scale == 2 and moved > 200 and home == 0, f"{moved} gold pixels moved, {home} at home, x{scale}")
    return found


def baseline(executable, base, out, mods):
    """Without a mod: the same VRAM hashes as the build before."""
    from yfm_control import Game
    sequences = []
    for exe, name in ((base, "baseline"), (executable, "this-build")):
        hashes = []
        with Game(executable=exe, out=out / f"nomod-{name}", mods_dir=mods,
                  settings={"mod.cardbar-hidden": 0, "mod.cardbar-rearranged": 0, "mod.cardbar-spaced": 0,
                            "mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0}) as g:
            g.goto("duel", opponent=3, deck="1-40")
            g.duel_ready()
            for slot in (1, 2, 3, 4, 0):
                g._hand_to(slot)
                g.step(6)
                hashes.append(g.hash())
            g.play_card(0, face_up=True)
            for _ in range(6):
                g.step(10)
                hashes.append(g.hash())
            g.press("up", hold=4, after=20)
            hashes.append(g.hash())
            g.end_turn()
            for _ in range(20):
                g.step(20)
                hashes.append(g.hash())
        sequences.append(hashes)
    same = sum(1 for a, b in zip(*sequences) if a == b)
    check("without a mod, every frame as the baseline build's", sequences[0] == sequences[1],
          f"{same} of {len(sequences[0])} VRAM hashes equal")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", default=str(EXECUTABLE))
    parser.add_argument("--out", default="/tmp/cardbar")
    parser.add_argument("--baseline", help="a build without the card bar's parts, for the no-mod frames")
    parser.add_argument("--skip", default="", help="steps to leave out: window,baseline")
    args = parser.parse_args()
    os.environ.setdefault("MEMORIES_NO_MONITOR", "1")
    out = Path(args.out).resolve()
    skip = set(filter(None, args.skip.split(",")))
    mods, shots, editor = out / "mods", out / "shots", out / "editor"
    for folder in (mods, shots, editor):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    print("the mods, through the UI tab's Duel page:", flush=True)
    made = make_mods(ROOT / "game", mods, editor)
    print("the duel, three times:", flush=True)
    runs = {}
    for mod in (None, "hidden", "rearranged"):
        name = mod or "retail"
        runs[name] = play(args.executable, out / "runs", mods, name, mod, shots / name)
        steps, over, turns, battles = runs[name]
        check(f"{name}: the duel is played to its end", over, f"{len(steps)} pictures, {turns} turns, "
                                                                f"{battles} battles")
        log = (out / "runs" / name / "game.log").read_text(errors="replace")
        check(f"{name}: no notes in the Mods window", "ui:" not in log)
    labels = [[s["label"] for s in runs[n][0]] for n in ("retail", "hidden", "rearranged")]
    check("the three duels went the same way", labels[0] == labels[1] == labels[2],
          f"{len(labels[0])}, {len(labels[1])}, {len(labels[2])} steps")
    files, data, _, _, _ = deck_cards()
    looks = set()
    for retail, hidden, rearranged in zip(*(runs[n][0] for n in ("retail", "hidden", "rearranged"))):
        if retail["label"] != rearranged["label"] or retail["boxes"] != rearranged["boxes"]:
            check(f"{retail['label']}: the same step in all three", False, f"{retail} / {rearranged}")
            continue
        hide_bad, move_bad, put = compare_step(rearranged, retail["path"], hidden["path"], rearranged["path"],
                                               made["mods"]["rearranged"])
        looks.update(y for _, y, _ in rearranged["boxes"])
        check(f"{retail['label']}: hidden, the parts are gone and nothing else", not hide_bad,
              f"{len(hide_bad)} other pixels differ {hide_bad[:3]}; texts at {rearranged['boxes']}")
        check(f"{retail['label']}: rearranged, each part where the mod put it and nothing else moved",
              not move_bad, f"{put} part pixels moved; {len(move_bad)} wrong {move_bad[:3]}")
        if retail["label"] in ("hand-monster", "hand-magic", "hand-trap") and rearranged["boxes"]:
            bad, drawn = editor_matches(rearranged, hidden["path"], rearranged["path"], made["mods"]["rearranged"],
                                        data, files)
            check(f"{retail['label']}: the editor's preview of the bar is the game's", drawn > 100 and bad == 0,
                  f"{drawn} preview pixels, {bad} differ")
    check("both of the bar's looks were seen (its text at y 210 under the hand, 123 over it)",
          {210, 123} <= looks, str(sorted(looks)))
    # The name's letters spread: the hand's first three pictures.
    steps, _, _, _ = play(args.executable, out / "runs", mods, "spaced", "spaced", shots / "spaced", hand_only=True)
    for retail, hidden, spaced in zip(runs["retail"][0], runs["hidden"][0], steps):
        hide_bad, move_bad, put = compare_step(spaced, retail["path"], hidden["path"], spaced["path"],
                                               made["mods"]["spaced"])
        check(f"{retail['label']}: spaced, the name's letters {SPACED} further apart from the panel's left",
              retail["label"] == spaced["label"] and not move_bad and put > 100,
              f"{put} name pixels moved; {len(move_bad)} wrong {move_bad[:3]}")
        bad, drawn = editor_matches(spaced, hidden["path"], spaced["path"], made["mods"]["spaced"], data, files)
        check(f"{retail['label']}: spaced, the editor's preview is the game's", drawn > 100 and bad == 0,
              f"{drawn} preview pixels, {bad} differ")
    # The editor beside the game.
    by_label = {s["label"]: s["path"] for s in runs["rearranged"][0]}
    for (key, shows), (page_shot, stage, zoom, warning) in made["shots"].items():
        frame = by_label["hand-magic" if shows == "Magic card" else "hand-monster"]
        side_by_side(frame, stage, editor / f"beside-{key.split('.')[1]}-{shows.split()[0].lower()}.png", zoom)
        print(f"    editor {key} ({shows}): {warning or 'no warning'}", flush=True)
    if "window" not in skip:
        print("in a window: Internal 2x with HD text, 16:9:", flush=True)
        window_runs(args.executable, out / "runs", mods, shots / "window")
    if args.baseline and "baseline" not in skip:
        print("without a mod:", flush=True)
        baseline(args.executable, args.baseline, out / "runs", mods)
    failed = [name for name, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} checks passed; pictures in {shots}, {editor}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
