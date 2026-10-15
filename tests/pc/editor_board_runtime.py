#!/usr/bin/env python3
"""Live FM Editor Duel board check (built game and user-supplied disc).

Makes a mod through the UI tab's Duel board page the way a modder would
(its own controls, the file dialog answered with pictures drawn here):

* the Normal field's floor, one picture of the five rows (night blue tiles
  with silver lines, a white band across the centre strip) at 4x;
* Forest's floor, red tiles, at 1x;
* Wasteland's floor tinted blue (#6080FF): the game's own picture through
  rewritten palettes;
* on all seven fields: the walls' two wings as one banner (purple to teal,
  a white disc across the seam), a cyan top trim, the corner triangles
  tinted green.

Then plays it through tools/pc/yfm_control.py and takes pictures, at
Internal 1x and 2x, with the mod and without it:

1. a duel's start on the Normal field (the camera's sweep round the board
   and the dealt hand), and on Forest and on Wasteland (the field byte
   set before the duel loads its package, as a campaign duel's script
   does);
2. the field cards Forest and Wasteland played in a duel that began on
   Normal: the floor that comes in is the mod's (Forest replaced,
   Wasteland tinted), the walls stay;
3. at 1x, that duel played on to its end, turn after turn (monsters,
   battles, the opponent's turns), and the results;
4. the duel-effect bank still the game's own (native C) with the mod's
   palette patches;
5. without the mod, the same frames as with no mod at all (VRAM hashes
   from boot through the title and a duel's first turns).

Each picture is checked by its colors (the mod's floor where the board
is, none of it without the mod). The pictures are drawn here; nothing is
kept in the repository.

    python3 tests/pc/editor_board_runtime.py [--executable PATH] [--out DIR]

Needs a display for Tk (xvfb-run works).
"""
import argparse
import math
import os
from pathlib import Path
import shutil
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
MOD = "board-test"
OPPONENT = 1                    # Simon Muran: a duel the player's deck wins
FOREST, WASTELAND = 330, 331    # the field cards (gDuel_bTerrain = card - 0x149)
# The floor as the hand's camera shows it, in the game's 320 x 240: between
# the far edge and the hand's cards.
FLOOR_BOX = (90, 72, 140, 64)
TINT_WASTELAND, TINT_TRIANGLES = 0x6080FF, 0x60FF60

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)
    return ok


# --- pictures -----------------------------------------------------------------------

def floor_picture(scale, kind):
    """The floor in the board's order (board_art.FLOOR), `scale` times its
    256 x 254 texels: tiles of two colors, lines between them."""
    from fm_editor import board_art as ba, pngio
    w, h = ba.FLOOR_W * scale, ba.FLOOR_H * scale
    out = bytearray(w * h * 4)
    tops, at = [], 0
    for part in ba.FLOOR:
        tops.append((at, part))
        at += part.h
    for y in range(h):
        ty = y / scale
        top, part = next((t, p) for t, p in reversed(tops) if t <= ty)
        v = (ty - top) / part.h
        for x in range(w):
            tx = x / scale
            tile = min(4, int(tx // 51))
            u = (tx - tile * 51) / 51
            line = min(u, 1 - u, v, 1 - v) < 0.05
            dark = (tile + tops.index((top, part))) % 2
            if kind == "night":
                if line:
                    r, g, b = 190, 205, 235
                elif part.key == "centre" and abs(v - 0.5) < 0.12:
                    r, g, b = 240, 240, 250
                else:
                    r, g, b = (25, 55, 170) if dark else (50, 120, 225)
                    if math.hypot(u - 0.5, v - 0.3) < 0.1:      # a dot toward the far side
                        r, g, b = 255, 255, 255
            else:
                r, g, b = (30, 10, 10) if line else (175, 35, 35) if dark else (235, 105, 50)
            out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, 255))
    return pngio.Image(w, h, bytes(out))


def banner(scale):
    """Both wings (128 x 64 each) as one picture, a disc across the seam (the
    game puts the walls' middle block between them)."""
    from fm_editor import pngio
    w, h = 256 * scale, 64 * scale
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            t = x / w
            r, g, b = int(150 - 110 * t), int(40 + 140 * t), int(170 + 20 * t)
            if math.hypot(x / scale - 128, y / scale - 32) < 20:
                r, g, b = 250, 250, 240
            if y < 3 * scale or y >= h - 3 * scale:
                r, g, b = 240, 200, 80
            out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, 255))
    return pngio.Image(w, h, bytes(out))


def pictures(folder: Path) -> dict:
    from fm_editor import pngio
    folder.mkdir(parents=True, exist_ok=True)
    whole = banner(4)
    made = {"night": floor_picture(4, "night"), "red": floor_picture(1, "red"),
            "wing_left": pngio.crop(whole, 0, 0, whole.width // 2, whole.height),
            "wing_right": pngio.crop(whole, whole.width // 2, 0, whole.width // 2, whole.height),
            "trim": pngio.Image(512, 64, bytes((40, 225, 225, 255)) * (512 * 64)), "banner": whole}
    paths = {}
    for name, image in made.items():
        paths[name] = folder / f"{name}.png"
        pngio.write(paths[name], image)
    return paths


# --- the editor ------------------------------------------------------------------------

def make_mod(game: Path, folder: Path, art: dict) -> list:
    """The mod, through the Duel board page; what was done."""
    from fm_editor import board_art as ba, manifest, validate
    from fm_editor.app import App
    done = []
    app = App(ask=False, autostart=False)
    app.withdraw()
    app.update()
    app.start(str(game), None, False)
    app.update()
    app.info.vars["id"].set(MOD)
    app.info.vars["name"].set("Duel board test")
    assert app.info.commit()
    tab = app.ui
    app.notebook.select(tab)
    tab.page_name.set("board")
    tab.show_page()
    app.update()
    page = tab.pages["board"]

    def choose(path):
        return mock.patch("fm_editor.file_dialogs.askopenfilename", return_value=str(path))

    def field(terrain):
        page.field.set(terrain)
        page.choose_field()

    page.all_fields.set(False)
    field("normal")
    page.select("floor")
    with choose(art["night"]):
        page.replace()
    field("forest")
    page.select("floor")
    with choose(art["red"]):
        page.replace()
    field("wasteland")
    page.select("floor")
    page.set_tint(TINT_WASTELAND)
    done.append("floors: Normal's a night-blue picture at 4x, Forest's red at 1x, Wasteland's tinted #6080FF")
    field("normal")
    page.all_fields.set(True)
    for part, picture in (("wall_left", "wing_left"), ("wall_right", "wing_right"), ("trim", "trim")):
        page.select(part)
        with choose(art[picture]):
            page.replace()
    page.select("corner_triangles")
    page.set_tint(TINT_TRIANGLES)
    done.append("all seven fields: the wings as one banner, a cyan trim, the corner triangles tinted #60FF60")
    st = ba.state(app.project)
    check("the page made 5 + 5 + 21 replaced pieces and 5 + 7 tints",
          len(st.pictures) == 31 and len(st.tints) == 12, f"{len(st.pictures)} pictures, {len(st.tints)} tints")
    issues = [str(i) for i in validate.validate(app.project) if i.area in ("UI", "Art", "Mod info")]
    check("the editor finds nothing wrong with the mod", not issues, "; ".join(issues))
    manifest.save_mod(app.project, folder)
    digest = ba.digest(app.project)
    opened, messages = manifest.open_mod(app.retail, folder)
    check("opened again, the mod is the same", ba.digest(opened) == digest and not messages,
          f"{ba.digest(opened)} vs {digest}; {messages}")
    app.dirty = False
    app.destroy()
    return done


# --- the game -----------------------------------------------------------------------

def game(executable, out, mods, name, mod_on=True, scale=1, env=None):
    from yfm_control import Game
    flags = {f"mod.{MOD}": 1 if mod_on else 0, "mod.3d-monsters": 0, "mod.hand-camera": 0,
             "mod.ai-hard-mode": 0, "internal_scale": scale}
    return Game(executable=executable, out=out / name, mods_dir=mods, settings=flags,
                env=dict({"MEMORIES_DUMP_PICTURE": "1"}, **(env or {})))


def read_png(path):
    from fm_editor import pngio
    return pngio.read(path)


def count_in(image, box, test, scale=1):
    x0, y0, w, h = box
    return sum(1 for y in range(y0 * scale, (y0 + h) * scale) for x in range(x0 * scale, (x0 + w) * scale)
               if test(*image.pixel(x, y)[:3]))


def mean_in(image, box, scale=1):
    x0, y0, w, h = box
    total, n = [0, 0, 0], 0
    for y in range(y0 * scale, (y0 + h) * scale):
        for x in range(x0 * scale, (x0 + w) * scale):
            p = image.pixel(x, y)
            for c in range(3):
                total[c] += p[c]
            n += 1
    return [t / n for t in total]


def blue(r, g, b):
    return b > r + 50 and b > g + 10


def red(r, g, b):
    return r > g + 60 and r > b + 60


def gold(r, g, b):
    """The Normal field's own floor (its tiles' sandy gold)."""
    return r > 120 and r - b > 70 and g > 70


def cyan(r, g, b):
    return g > 150 and b > 150 and r < 110


def start_duel(g, terrain, deck, hand=None):
    """A duel against OPPONENT on `terrain` (gDuel_bTerrain set while the
    deck screen shows, before the duel's package is read)."""
    g.goto("duel", opponent=OPPONENT, deck=deck)
    g.wait_until(lambda g: g.u8("D_8009B26E") == 0x80, 3000, what="the deck screen")
    g.poke("gDuel_bTerrain", bytes([terrain]))
    g.duel_ready(before_deal=(lambda g: g.arrange_deck(0, hand)) if hand else None)


def starts(executable, out, mods, shots, scale, mod_on):
    """The duel's start on Normal (with the camera's sweep), Forest and
    Wasteland; the pictures' names."""
    from yfm_control import DUEL_PHASES
    tag = f"{scale}x-{'mod' if mod_on else 'retail'}"
    taken = {}
    with game(executable, out, mods, f"starts-{tag}", mod_on, scale) as g:
        for terrain, name in ((0, "normal"), (1, "forest"), (2, "wasteland")):
            g.goto("duel", opponent=OPPONENT, deck=list(range(1 + terrain, 41 + terrain)))
            g.wait_until(lambda g: g.u8("D_8009B26E") == 0x80, 3000, what="the deck screen")
            g.poke("gDuel_bTerrain", bytes([terrain]))
            g.press_until(lambda g: g.u8("D_8009B26E") != 0x80, "circle", every=60, timeout=3000, what="the field")
            # The last duel's hand stays in memory until this one starts (Game.duel_ready).
            g.wait_until(lambda g: g.phase() == DUEL_PHASES["startup"] and
                         all(slot < 0 for slot in g.duel()[0]["hand_slots"]), 3000, what="the duel's start")
            if terrain == 0:
                for k, frames in enumerate((204, 24)):      # the sweep: the near end, then a corner
                    g.step(frames)
                    taken[f"sweep{k}"] = g.shot(shots / f"{tag}-normal-sweep{k}.png")
            g.wait_until(lambda g: all(g.duel()[0]["hand"]), 3000, every=10, what="the hand")
            g.step(200)
            taken[name] = g.shot(shots / f"{tag}-{name}-start.png")
            check(f"{tag}: the {name} duel's field byte", g.u8("gDuel_bTerrain") == terrain,
                  str(g.u8("gDuel_bTerrain")))
    return taken


def field_cards(executable, out, mods, shots, scale, mod_on, to_the_end):
    """Forest, then Wasteland, played in a duel begun on Normal; at 1x with
    the mod, the duel then played to its end."""
    from fm_editor import disc, gamedata
    from yfm_control import DUEL_PHASES
    tag = f"{scale}x-{'mod' if mod_on else 'retail'}"
    data = gamedata.load_game(disc.load(ROOT / "game"))
    names = {c.id: c.name for c in data.cards.values()}
    assert names[FOREST] == "Forest" and names[WASTELAND] == "Wasteland", (names[FOREST], names[WASTELAND])
    bewd = next(cid for cid, n in names.items() if n == "Blue-eyes White Dragon")
    hand = [FOREST, WASTELAND, bewd, bewd, bewd]
    deck = hand + [bewd] * 5 + list(range(3, 33))
    taken = {}
    count = 0

    def shot(label):
        nonlocal count
        count += 1
        path = shots / f"{tag}-duel-{count:02d}-{label}.png"
        g.shot(path)
        return path

    with game(executable, out, mods, f"duel-{tag}", mod_on, scale,
              env={"MEMORIES_TRACE": "mods"} if mod_on and scale == 1 else None) as g:
        start_duel(g, 0, deck, hand)
        taken["start"] = shot("normal")
        for turn, (card, terrain, name) in enumerate(((FOREST, 1, "forest"), (WASTELAND, 2, "wasteland"))):
            slot = next(i for i, c in enumerate(g.duel()[0]["hand"]) if c and c["id"] == card)
            g.play_card(slot)
            g.wait_until(lambda g: g.u8("gDuel_bTerrain") == terrain, 600, what=f"the {name} field")
            g.wait_turn()
            g.step(120)
            taken[name] = shot(f"{name}-played")
            check(f"{tag}: {name.title()} played, the field byte is {terrain}", g.u8("gDuel_bTerrain") == terrain)
            g.end_turn()
            if not to_the_end and turn == 1:
                break
            if turn == 0:
                g.step(60)
                shot("turn2-hand")
        if not to_the_end:
            return taken, g.log_path
        turns, battles = 2, 0
        while not g.duel_over() and turns < 30:
            turns += 1
            g.wait_turn(("hand",), 30000)
            if g.duel_over():
                break
            slots = [i for i, c in enumerate(g.duel()[0]["hand"]) if c and c["attack"] > 0]
            if slots:
                best = max(slots, key=lambda i: g.duel()[0]["hand"][i]["attack"])
                g.play_card(best, face_up=True)
            else:
                g.play_card(0)
            shot(f"turn{turns}-played")
            for column in range(5):
                if g.duel_over() or g.turn() != 0:
                    break
                if not g.field()[2][column] or g.phase() != DUEL_PHASES["field"]:
                    continue
                theirs = [i for i, c in enumerate(g.field()[1]) if c]
                try:
                    g.attack(column, theirs[0] if theirs else None)
                    battles += 1
                except Exception as problem:     # noqa: BLE001 -- a monster that cannot attack
                    print(f"    (no attack from column {column}: {problem})", flush=True)
                    continue
                if not g.duel_over():
                    shot(f"turn{turns}-battle{battles}")
            if g.duel_over():
                break
            g.press_until(lambda g: g.turn() != 0 or g.duel_over(), "start", every=60, timeout=1200,
                          what="the end of the turn")
            g.wait_until(lambda g: g.duel_over() or g.turn() == 1, 600, what="the opponent's turn")
            if not g.duel_over():
                g.step(90)
                shot(f"turn{turns}-opponent")
        lp = [s["lp"] for s in g.duel()]
        check(f"{tag}: the duel ends", g.duel_over(), f"after {turns} turns, {battles} battles, LP {lp}")
        for _ in range(12):
            g.step(120)
            if g.phase() in (DUEL_PHASES["result"], DUEL_PHASES["rewards"]):
                break
        shot("result")
        for _ in range(6):
            g.press("cross", hold=4, after=60)
            g.step(60)
            if g.mode() != 3:
                break
        g.step(240)
        shot("after")
        check(f"{tag}: the game goes on after the duel", g.mode() != 3 or g.phase() == DUEL_PHASES["rewards"],
              f"mode {g.mode()}, phase {g.phase()}")
        return taken, g.log_path


def compare(shots, scale, mod, retail, duel_mod, duel_retail):
    """The checks of a scale's pictures, with the mod and without it."""
    tag = f"{scale}x"
    box = FLOOR_BOX

    def counts(path, test):
        return count_in(read_png(path), box, test, scale)
    n = box[2] * box[3] * scale * scale
    for name, test, what in (("normal", blue, "night-blue"), ("forest", red, "red")):
        with_mod, without = counts(mod[name], test), counts(retail[name], test)
        check(f"{tag}: the {name} duel's floor is the mod's {what} picture", with_mod > n // 3 and without < n // 50,
              f"{with_mod} of {n} pixels with the mod, {without} without")
    whole = (FLOOR_BOX[0], 60, FLOOR_BOX[2], 86)     # every row of the floor in view, from far to near
    with_mod, without = (count_in(read_png(shot), whole, gold, scale) for shot in (mod["normal"], retail["normal"]))
    check(f"{tag}: none of the game's Normal floor is left",
          with_mod < 5 * scale * scale and without > 5000 * scale * scale,
          f"{with_mod} gold pixels with the mod, {without} without")
    tinted, plain = mean_in(read_png(mod["wasteland"]), box, scale), mean_in(read_png(retail["wasteland"]), box, scale)
    check(f"{tag}: the wasteland floor is the game's, tinted blue",
          tinted[0] < plain[0] * 0.6 and tinted[2] / max(1, tinted[0]) > 1.5 * plain[2] / max(1, plain[0]),
          f"mean {[round(c) for c in tinted]} with the mod, {[round(c) for c in plain]} without")
    trim_mod = count_in(read_png(mod["sweep0"]), (0, 0, 320, 240), cyan, scale)
    trim_retail = count_in(read_png(retail["sweep0"]), (0, 0, 320, 240), cyan, scale)
    check(f"{tag}: the sweep shows the mod's cyan trim", trim_mod > 30 * scale * scale and trim_retail == 0,
          f"{trim_mod} pixels with the mod, {trim_retail} without")
    with_mod, without = counts(duel_mod["forest"], red), counts(duel_retail["forest"], red)
    check(f"{tag}: Forest played mid-duel brings in the mod's red floor", with_mod > n // 3 and without < n // 50,
          f"{with_mod} of {n} pixels with the mod, {without} without")
    tinted = mean_in(read_png(duel_mod["wasteland"]), box, scale)
    plain = mean_in(read_png(duel_retail["wasteland"]), box, scale)
    check(f"{tag}: Wasteland played mid-duel brings in the tinted floor", tinted[0] < plain[0] * 0.6,
          f"mean {[round(c) for c in tinted]} with the mod, {[round(c) for c in plain]} without")


def same_without(executable, out, mods):
    """With the mod switched off, every frame as with no mods folder at
    all."""
    from yfm_control import Game
    empty = out / "no-mods"
    empty.mkdir(parents=True, exist_ok=True)
    sequences = []
    for folder, name in ((mods, "mod-off"), (empty, "no-mods")):
        hashes = []
        with Game(executable=executable, out=out / f"nomod-{name}", mods_dir=folder,
                  settings={f"mod.{MOD}": 0, "mod.3d-monsters": 0, "mod.hand-camera": 0,
                            "mod.ai-hard-mode": 0}) as g:
            for i in range(60):
                g.step(30)
                hashes.append(g.hash())
                if g.u32("D_80184558"):
                    break
                if i % 4 == 3:
                    g.press("start")
            g.goto("duel", opponent=OPPONENT, deck="1-40")
            g.duel_ready()
            for _ in range(10):
                g.step(10)
                hashes.append(g.hash())
            g.play_card(0, face_up=True)
            g.end_turn()
            for _ in range(20):
                g.step(20)
                hashes.append(g.hash())
        sequences.append(hashes)
    same = sum(1 for a, b in zip(*sequences) if a == b)
    check("with the mod off, every frame as with no mods at all", sequences[0] == sequences[1],
          f"{same} of {len(sequences[0])} VRAM hashes equal")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", default=str(EXECUTABLE))
    parser.add_argument("--out", default="/tmp/boardtex")
    parser.add_argument("--skip", default="", help="steps to leave out: 1x,2x,nomod")
    args = parser.parse_args()
    os.environ.setdefault("MEMORIES_NO_MONITOR", "1")
    out = Path(args.out).resolve()
    shots = out / "shots"
    for folder in (out / "mods", out / "runs", shots):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    skip = set(filter(None, args.skip.split(",")))
    art = pictures(out / "art")
    mods = out / "mods"
    print("the mod, through the Duel board page:", flush=True)
    for line in make_mod(ROOT / "game", mods / MOD, art):
        print("  " + line, flush=True)
    runs = out / "runs"
    for scale in (1, 2):
        if f"{scale}x" in skip:
            continue
        print(f"at Internal {scale}x:", flush=True)
        mod = starts(args.executable, runs, mods, shots, scale, True)
        retail = starts(args.executable, runs, mods, shots, scale, False)
        duel_mod, log = field_cards(args.executable, runs, mods, shots, scale, True, to_the_end=scale == 1)
        duel_retail, _ = field_cards(args.executable, runs, mods, shots, scale, False, to_the_end=False)
        compare(shots, scale, mod, retail, duel_mod, duel_retail)
        if scale == 1:
            text = Path(log).read_text(encoding="utf-8", errors="replace")
            check("the duel-effect bank stays the game's own with the mod's palette patches",
                  "duel_effects: retail bytes" in text and "changed bytes" not in text,
                  "native C" if "duel_effects: retail bytes" in text else "no verdict in the log")
    if "nomod" not in skip:
        print("without the mod:", flush=True)
        same_without(args.executable, runs, mods)
    failed = [name for name, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} checks passed; pictures in {shots}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
