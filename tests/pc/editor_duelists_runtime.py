#!/usr/bin/env python3
"""Live FM Editor Duelists tab check (built game and user-supplied disc).

Makes a mod through the Duelists tab the way a modder would (its own
dialogs and buttons): three duelists added past the disc's thirty-nine, each
with a portrait, one at slot 45, one with its own deck and drops; and one of
the disc's own given a new name and face. Then plays it, through
tools/pc/yfm_control.py, and checks what the editor said the game would do:

1. the Free Duel grid has a second page, the added duelists on it;
2. each portrait is the editor's own 1x picture of it, pixel for pixel (at
   the console's 15-bit color), and at Internal 2x the PNG itself;
3. the disc duelist wears its new face, and the disc's again once the
   editor reverts it;
4. a duel against an added duelist is dealt from its own deck pool;
5. winning it gives a card of its own drop pools;
6. slot 45 is page 2's sixth cell (row 2, column 1), and an "unlock" written
   by hand keeps the duelist hidden until it is met, through an editor save;
7. the saved mod, opened and saved again, is the same files;
8. an added duelist's fixed deck, made on its deck pool, is the deck a duel
   against it deals, card for card;
9. an unlock made in the tab's Unlock, play, ranks... dialog ("beat Dark
   Simon") hides a duelist until Dark Simon is beaten, then shows it;
10. rank scoring made in that dialog (every change 0, so the score stays at
    50: D-POW, where the disc's scoring makes a quick win an S-POW) makes
    the drop come from Dark Simon's B/C/D pool;
11. the Values tab's starting LP for an added duelist, by its name, is the
    LP it starts the duel with.

The test portraits are drawn here; nothing is kept in the repository.
Screenshots and logs stay in tmp/pc/editor-duelists (or --out), the
screenshots in its shots/.

    python3 tests/pc/editor_duelists_runtime.py [--executable PATH] [--out DIR]

Needs a display for Tk (xvfb-run works).
"""
import argparse
import filecmp
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
OUT = ROOT / "tmp/pc/editor-duelists"
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
MOD = "editor-duelists"

FLAGS = 0x801D0618              # SaveDataState.campaign_flags (campaign_flags.h CAMPAIGN_FLAG_BANK_OFFSET)
FREE_DUEL_FLAGS = 0x6E0         # FREE_DUEL_UNLOCK_FLAG_BASE: duelist n is in Free Duel at 0x6E0 + n
LOCK_FLAG = 0x710               # a story flag a new game has not set: the hand-written unlock's
OPPONENT_LP = 0x800EA024        # D_800E9FF0[1].life_points
OPPONENT_SHOWN_LP = 0x800EA022  # and the value drawn
RESULT_RECORD = 0x8009B1E8      # D_8009B1E8, DuelResultDisplayState *
DROPPED_CARD = 0x3C
# The grid's cells on screen at 1x (FreeDuel_Init): five across from x 20 a
# 56-pixel step, eight down from y 40 a 52-pixel step, each 48x48.
CELL_X, CELL_Y, STEP_X, STEP_Y = 20, 40, 56, 52
DECK = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]      # Dark Simon's own deck pool
DROPS = {"pow": 19, "bcd": 20, "tec": 21}                           # one card a drop pool
FIXED = {cid: 4 for cid in range(22, 32)}                           # Pegasus Prime's fixed deck: ten cards, 4 each
DARK_SIMON_LP = 1234                                                # its starting LP (Values tab)
RIVAL_SLOT = 47                                                     # Victor Rival: shown once Dark Simon is beaten


# --- pictures -------------------------------------------------------------------

def drawn(w, h, kind, color):
    """A test portrait, drawn rather than kept: rings, stripes or a face."""
    from fm_editor import pngio
    out = bytearray(w * h * 4)
    r0 = min(w, h) / 2
    for y in range(h):
        for x in range(w):
            dx, dy = (x - w / 2) / r0, (y - h / 2) / r0
            d = math.hypot(dx, dy)
            if kind == "rings":
                v = 0.5 + 0.5 * math.cos(d * 18)
            elif kind == "stripes":
                v = 1 if int((x + y) / (w / 12)) % 2 else 0.25
            else:
                v = 1 if d < 0.8 and not any(math.hypot(dx - ex, dy + 0.25) < 0.12 for ex in (-0.3, 0.3)) and \
                    not (0.35 < math.hypot(dx, dy + 0.05) < 0.48 and dy > 0.12) else 0.1
            out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((*(int(c * v) for c in color), 255))
    return pngio.Image(w, h, bytes(out))


def pictures(folder: Path) -> dict:
    from fm_editor import pngio
    folder.mkdir(parents=True, exist_ok=True)
    made = {"rings": drawn(512, 512, "rings", (255, 120, 40)), "stripes": drawn(640, 400, "stripes", (60, 200, 255)),
            "face": drawn(256, 256, "face", (250, 210, 40)), "small": drawn(48, 48, "face", (60, 220, 90)),
            "rival": drawn(200, 200, "stripes", (200, 60, 255))}
    paths = {}
    for name, image in made.items():
        paths[name] = folder / f"{name}.png"
        pngio.write(paths[name], image)
    return paths


def cell_box(slot, scale=1):
    row, column = divmod(slot % 40, 5)
    return (CELL_X + STEP_X * column) * scale, (CELL_Y + STEP_Y * row) * scale


def mismatch(shot, face, slot, scale=1):
    """Pixels of the cell that differ from `face` at the console's 15 bits."""
    x0, y0 = cell_box(slot, scale)
    side = 48 * scale
    wrong = 0
    for y in range(side):
        for x in range(side):
            a, b = shot.pixel(x0 + x, y0 + y), face.pixel(x, y)
            if any(a[i] >> 3 != b[i] >> 3 for i in range(3)):
                wrong += 1
    return wrong


def distance(shot, face, slot, scale):
    """The mean difference a channel between the cell and `face`."""
    x0, y0 = cell_box(slot, scale)
    side = 48 * scale
    total = 0
    for y in range(side):
        for x in range(side):
            a, b = shot.pixel(x0 + x, y0 + y), face.pixel(x, y)
            total += sum(abs(a[i] - b[i]) for i in range(3))
    return total / (side * side * 3)


# --- the editor -------------------------------------------------------------------

def editor(game: Path, mod: Path = None):
    from fm_editor.app import App
    app = App(ask=False, autostart=False)
    app.withdraw()
    app.update()
    app.start(str(game), None, False)
    app.update()
    if mod is not None:
        app.load_mod(mod)
        app.update()
    return app


def fields(dialog, key="name") -> dict:
    """The fields a Duelists tab dialog made (kept in its OK's closure)."""
    for cell in dialog.on_ok.__closure__ or ():
        if isinstance(cell.cell_contents, dict) and key in cell.cell_contents:
            return cell.cell_contents
    raise AssertionError("no fields in the dialog")


def make_mod(game: Path, out: Path, faces: dict) -> list:
    """The mod, through the Duelists tab; what was done."""
    from fm_editor import duelists_tab, roster
    done = []
    app = editor(game)
    app.info.vars["id"].set(MOD)
    app.info.vars["name"].set("FM Editor duelists")
    assert app.info.commit()
    tab = app.duelists
    p = app.project

    tab.goto((1, "deck"))                      # Add copies the duelist shown: Simon Muran
    dialog = tab.add()
    fields(dialog)["name"].set("Dark Simon")
    dialog.ok()
    tab.use_picture(str(faces["rings"]))
    simon = roster.find(p, "dark-simon")
    assert simon is not None and simon.base == 1
    # Its own deck: the weighted pool emptied, then sixteen cards put in.
    tab.tree.selection_set(tab.tree.get_children())
    tab.weight.set("0")
    tab.set_weight()
    for cid in DECK:
        with mock.patch.object(duelists_tab, "pick_card", return_value=cid):
            tab.weight.set("128")
            tab.add_card()
    assert tab.current_pool() == {cid: 128 for cid in DECK}, tab.current_pool()
    for pool, cid in DROPS.items():
        tab.pool.set(pool)
        tab.fill()
        tab.tree.selection_set(tab.tree.get_children())
        tab.weight.set("0")
        tab.set_weight()
        with mock.patch.object(duelists_tab, "pick_card", return_value=cid):
            tab.weight.set("2048")
            tab.add_card()
    done.append("Dark Simon: a copy of Simon Muran, a 512x512 picture, its own 16-card deck and one card a drop pool")
    # Its own rank scoring: every rule ticked, every change 0, so the score
    # stays at 50, a D-POW (a score below 50 is TEC, mirrored).
    dialog = tab.edit_rules()
    given = fields(dialog, "beat")
    for rule, own in enumerate(given["own"]):
        own.set(True)
        for _, change in given["pairs"][rule]:
            change.set("0")
    dialog.ok()
    assert not dialog.winfo_exists() and len(simon.extra["ranks"]) == 10, simon.extra
    done.append("Dark Simon: rank scoring of its own, every rule's change 0 (Unlock, play, ranks...)")
    # Its starting LP, on the Values tab, by its name.
    app.values.duelist_name.set("Dark Simon")
    app.values.duelist_opponent.set(str(DARK_SIMON_LP))
    app.values._set_duelist()
    assert p.other["limits"]["life_points"]["duelists"] == {"Dark Simon": DARK_SIMON_LP}, p.other["limits"]
    done.append(f"Values: Dark Simon starts with {DARK_SIMON_LP} LP")

    tab.goto((15, "deck"))
    dialog = tab.add()
    given = fields(dialog)
    given["name"].set("Pegasus Prime")
    given["auto"].set(False)
    given["slot"].set("45")
    dialog.ok()
    tab.use_picture(str(faces["stripes"]))
    # A fixed deck, on its deck pool: Fixed, Clear, then ten cards four times.
    from fm_editor import fixed_deck_view, fixed_decks
    pegasus = roster.find(p, "pegasus-prime")
    tab.pool.set("deck")
    tab.fill()
    tab.fixed.mode.set("fixed")
    tab.fixed.switch()
    tab.fixed.clear()
    for cid, copies in FIXED.items():
        with mock.patch.object(fixed_deck_view, "pick_card", return_value=cid):
            tab.fixed.copies.set(str(copies))
            tab.fixed.add_card()
    assert fixed_decks.deck_of(p, pegasus).cards == FIXED, fixed_decks.deck_of(p, pegasus).cards
    done.append("Pegasus Prime: a copy of Pegasus at slot 45, a 640x400 picture (its middle square is used), and a "
                "fixed deck of ten cards four times each")

    tab.goto((7, "deck"))
    dialog = tab.add()
    given = fields(dialog)
    given["name"].set("Victor Rival")
    given["auto"].set(False)
    given["slot"].set(str(RIVAL_SLOT))
    dialog.ok()
    tab.use_picture(str(faces["rival"]))
    dialog = tab.edit_rules()
    fields(dialog, "beat")["beat"].set("Dark Simon")
    dialog.ok()
    rival = roster.find(p, "victor-rival")
    assert rival.extra["unlock"] == {"beat": "Dark Simon"}, rival.extra
    done.append(f"Victor Rival: a copy of Seto at slot {RIVAL_SLOT}, unlocked by beating Dark Simon "
                "(Unlock, play, ranks...)")

    tab.goto((2, "deck"))
    dialog = tab.add()
    fields(dialog)["name"].set("Teana Locked")
    dialog.ok()
    tab.use_picture(str(faces["small"]))
    done.append("Teana Locked: a copy of Teana, a 48x48 picture")

    tab.goto((1, "deck"))
    dialog = tab.edit()
    fields(dialog)["name"].set("Simon the Wise")
    dialog.ok()
    tab.use_picture(str(faces["face"]))
    done.append("Simon Muran (the disc's): renamed Simon the Wise, a 256x256 picture")

    app.update()
    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out / "mods")):
        assert app.save(ask=True, export=True)
    app.dirty = False
    app.destroy()
    return done


def lock_by_hand(folder: Path):
    """An "unlock" written into the duelist's file by hand, as a modder may
    (the editor keeps it as written); then the mod opened in the editor,
    something else changed, and saved in place."""
    path = folder / "duelists/teana-locked.json"
    entry = json.loads(path.read_text())
    entry["unlock"] = {"story": LOCK_FLAG}
    path.write_text(json.dumps(entry, indent=4) + "\n")
    from fm_editor import roster
    game = Path(os.environ.get("MEMORIES_DISC_DIR", ROOT / "game"))
    app = editor(game, folder)
    assert roster.find(app.project, "teana-locked").extra["unlock"] == {"story": LOCK_FLAG}
    app.duelists.goto(("pegasus-prime", "deck"))
    dialog = app.duelists.edit()
    fields(dialog)["name"].set("Pegasus Prime")
    dialog.ok()
    app.changed()
    assert app.save()
    app.dirty = False
    app.destroy()
    assert json.loads(path.read_text())["unlock"] == {"story": LOCK_FLAG}, "the editor lost the hand-written unlock"


def revert_simon(folder: Path, what: str):
    """Simon Muran's face (what="face") or his name too ("all") back to the
    disc's, through the tab, and saved in place."""
    app = editor(Path(os.environ.get("MEMORIES_DISC_DIR", ROOT / "game")), folder)
    tab = app.duelists
    tab.goto((1, "deck"))
    tab.revert_picture()
    if what == "all":
        dialog = tab.edit()
        fields(dialog)["name"].set("Simon Muran")
        dialog.ok()
    assert app.save()
    app.dirty = False
    app.destroy()


def expected_faces(game: Path, folder: Path) -> dict:
    """What the editor says each face is: {name: (1x, 2x) images}."""
    from fm_editor import manifest, roster, disc, gamedata
    files = disc.load(game)
    project, _ = manifest.open_mod(gamedata.load_game(files), folder)
    out = {}
    for key in ("dark-simon", "pegasus-prime", "teana-locked", "victor-rival"):
        e = roster.find(project, key)
        out[key] = (roster.face(project, files.wa, e, 1), roster.face(project, files.wa, e, 2), roster.slot_of(project, e))
    for d in (1, 2):
        out[d] = (roster.face(project, files.wa, d, 1), roster.face(project, files.wa, d, 2), d)
    return out, project


# --- the game ----------------------------------------------------------------------

def game_for(executable: Path, out: Path, label: str, scale: int = 1):
    from yfm_control import Game
    settings = {f"mod.{MOD}": 1, "mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0}
    env = {"MEMORIES_NO_MONITOR": "1", "MEMORIES_TRACE": "mods", "MEMORIES_LOG": str(out / f"{label}.trace.log"),
           }
    if scale > 1:
        settings["internal_scale"] = scale
        env["MEMORIES_DUMP_PICTURE"] = "1"
    return Game(executable=executable, mods_dir=out / "mods", out=out / label, settings=settings, env=env)


def open_free_duel(g, flags=None):
    """The Free Duel screen with the disc's duelists unlocked (and `flags`
    set too), past its SELECT OPPONENT! box."""
    g.goto("free_duel")
    g.step(30)
    data = bytearray(g.peek(FLAGS, 0x100))
    for flag in [FREE_DUEL_FLAGS + n for n in range(1, 40)] + list(flags or ()):
        data[flag >> 3] |= 0x80 >> (flag & 7)
    g.poke(FLAGS, bytes(data))
    g.goto("free_duel")      # built again: the unlocks are read as the screen opens
    g.step(240)
    g.press("cross", after=60)


def shot(g, out: Path, name: str):
    from fm_editor import pngio
    path = out / "shots" / f"{name}.png"
    g.shot(path)
    return pngio.read(path)


def said(out: Path, label: str) -> str:
    """What the game said: its trace (MEMORIES_TRACE=mods) and its output,
    where a mod's notes go (mods.c Mods_Note)."""
    return "".join(path.read_text(errors="replace") for path in (out / f"{label}.trace.log", out / label / "game.log")
                   if path.exists())


def check(result: list, ok: bool, text: str):
    result.append(("PASS" if ok else "FAIL") + ": " + text)
    print(result[-1], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", type=Path, default=EXECUTABLE)
    parser.add_argument("--out", type=Path, default=OUT)
    arguments = parser.parse_args()
    out = arguments.out.resolve()
    for name in ("mods", "shots", "pictures", "again", "game1x", "game2x", "locked", "reverted", "fixed"):
        shutil.rmtree(out / name, ignore_errors=True)
        (out / f"{name}.trace.log").unlink(missing_ok=True)
    (out / "mods").mkdir(parents=True)
    (out / "shots").mkdir(parents=True)
    game = Path(os.environ.get("MEMORIES_DISC_DIR", ROOT / "game"))
    answers = [mock.patch("tkinter.messagebox." + n, return_value=True) for n in ("askyesno", "askokcancel")]
    for patch in answers:
        patch.start()
    faces = pictures(out / "pictures")
    done = make_mod(game, out, faces)
    folder = out / "mods" / MOD
    lock_by_hand(folder)
    done.append("Teana Locked: \"unlock\": {\"story\": %d} written by hand, kept through an editor save" % LOCK_FLAG)
    expect, project = expected_faces(game, folder)
    # The player's deck: forty monsters it can set at once (no Exodia).
    player_deck = [cid for cid, card in sorted(project.retail.cards.items())
                   if card.is_monster() and card.level <= 4 and not 17 <= cid <= 21][:40]
    results = []
    from fm_editor import pngio

    # 7. The round trip: opened and saved again, the same files.
    app = editor(game, folder)
    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out / "again")):
        assert app.save(ask=True, export=True)
    app.dirty = False
    app.destroy()
    compared = filecmp.dircmp(folder, out / "again" / MOD)
    same = not compared.diff_files and not compared.left_only and not compared.right_only and \
        all(not sub.diff_files and not sub.left_only and not sub.right_only for sub in compared.subdirs.values())
    check(results, same, f"round trip: the mod opened and saved again is the same files "
                         f"({sorted(str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file())})")

    # 1-6 at 1x.
    with game_for(arguments.executable, out, "game1x") as g:
        open_free_duel(g)
        page1 = shot(g, out, "1x-page1")
        check(results, mismatch(page1, expect[1][0], 1) == 0,
              "Simon Muran's cell shows the editor's 1x picture of his new face, pixel for pixel")
        check(results, mismatch(page1, expect[2][0], 2) == 0, "Teana's cell keeps the disc's face")
        g.press("right", hold=2, after=30)
        shot(g, out, "1x-page1-simon-name")
        g.press("left", hold=2, after=30)
        g.press("r1", after=60)
        shot(g, out, "1x-page2-dark-simon-name")
        # The cursor's frame off the cells checked: to the empty third cell.
        g.press("right", hold=2, after=30)
        g.press("right", hold=2, after=30)
        page2 = shot(g, out, "1x-page2")
        dark = expect["dark-simon"]
        check(results, dark[2] == 40 and mismatch(page2, dark[0], 40) == 0,
              "page 2: Dark Simon at slot 40 (page 2, row 1, column 1) wears the editor's 1x picture")
        pegasus = expect["pegasus-prime"]
        check(results, pegasus[2] == 45 and mismatch(page2, pegasus[0], 45) == 0,
              "slot 45: Pegasus Prime in page 2's sixth cell (row 2, column 1), the middle square of its 640x400")
        teana = expect["teana-locked"]
        check(results, teana[2] == 41 and mismatch(page2, teana[0], 41) > 1000,
              "Teana Locked (slot 41) is hidden while its hand-written unlock is not met")
        rival = expect["victor-rival"]
        check(results, rival[2] == RIVAL_SLOT and mismatch(page2, rival[0], RIVAL_SLOT) > 1000,
              f"Victor Rival (slot {RIVAL_SLOT}) is hidden until Dark Simon is beaten")
        # Into a duel against Dark Simon, page 2's first cell. The jump's
        # save has no deck, and the screen wants one.
        for _ in range(5):
            g.press("left", hold=2, after=20)
        g.poke("gDuel_awPlayerDeck", struct.pack("<40H", *player_deck))
        g.press("cross", after=30)
        g.wait_until(lambda game: game.u8("D_8009B26E") == 0x80, 6000, what="the deck screen")
        g.step(120)
        shot(g, out, "1x-duel-deck-screen")
        g.duel_ready()
        duel_shot = shot(g, out, "1x-duel-dark-simon")
        deck = g.decks()[1]
        check(results, len(deck) == 40 and set(deck) <= set(DECK),
              f"the duel against Dark Simon deals its own deck pool (opponent {g.u8('gDuel_bOpponentID')}, "
              f"its 40 from {sorted(set(deck))})")
        check(results, g.u8("gDuel_bOpponentID") == 40, "the duel's opponent is id 40")
        life = g.u16(OPPONENT_LP)
        check(results, life == DARK_SIMON_LP, f"Dark Simon starts with the Values tab's {DARK_SIMON_LP} LP ({life})")
        # 5. Won: its life points to nothing, a card played and the turn ended.
        chest = g.peek("gLibrary_abCardChest", 722)
        g.wait_turn()
        g.poke(OPPONENT_SHOWN_LP, struct.pack("<hH", 0, 0))
        g.play_card(0)
        try:
            g.end_turn(timeout=3000)
        except Exception:       # noqa: BLE001 -- the duel may end before the opponent's turn starts
            pass
        g.wait_until(lambda game: game.phase() in (12, 13), 6000, what="the duel's end")
        g.step(600)
        shot(g, out, "1x-results")
        record = g.u32(RESULT_RECORD)
        dropped = struct.unpack("<h", g.peek(record + DROPPED_CARD, 2))[0] if record else 0
        for _ in range(12):
            g.press("cross", after=60)
            if g.mode() != 3:
                break
        g.step(300)
        gained = [a - b for a, b in zip(g.peek("gLibrary_abCardChest", 722), chest)]
        won = [cid + 1 for cid, n in enumerate(gained) if n > 0]
        check(results, dropped in DROPS.values() and won == [dropped],
              f"the win drops a card of Dark Simon's own pools: card {dropped}, chest gained {won}")
        check(results, dropped == DROPS["bcd"],
              f"its own rank scoring (every change 0) makes the win a D-POW: the drop is its B/C/D card "
              f"{DROPS['bcd']} ({dropped})")
        # Dark Simon beaten: Victor Rival is on the grid now.
        open_free_duel(g)
        g.press("r1", after=60)
        g.press("right", hold=2, after=30)
        g.press("right", hold=2, after=30)
        page2 = shot(g, out, "1x-page2-rival-unlocked")
        check(results, mismatch(page2, rival[0], RIVAL_SLOT) == 0,
              f"with Dark Simon beaten, Victor Rival appears at slot {RIVAL_SLOT} with the editor's 1x picture")
    # 8. A duel against Pegasus Prime deals its fixed deck.
    with game_for(arguments.executable, out, "fixed") as g:
        open_free_duel(g)
        g.press("r1", after=60)
        g.press("down", hold=2, after=30)          # slot 45: row 2, column 1
        g.poke("gDuel_awPlayerDeck", struct.pack("<40H", *player_deck))
        g.press("cross", after=30)
        g.wait_until(lambda game: game.u8("D_8009B26E") == 0x80, 6000, what="the deck screen")
        g.step(120)
        g.duel_ready()
        shot(g, out, "1x-duel-pegasus-prime")
        deck = g.decks()[1]
        dealt = {cid: deck.count(cid) for cid in set(deck)}
        check(results, g.u8("gDuel_bOpponentID") == 45 and dealt == FIXED,
              f"the duel against Pegasus Prime (opponent {g.u8('gDuel_bOpponentID')}) deals its fixed deck, card "
              f"for card: {sorted(dealt.items())}")
    # The hand-written unlock met: shown.
    with game_for(arguments.executable, out, "locked") as g:
        open_free_duel(g, flags=[LOCK_FLAG])
        g.press("r1", after=60)
        g.press("right", hold=2, after=30)
        g.press("right", hold=2, after=30)
        page2 = shot(g, out, "1x-page2-unlocked")
        check(results, mismatch(page2, teana[0], 41) == 0,
              "with its story flag set, Teana Locked appears at slot 41 with its 48x48 picture")
    # 2. At Internal 2x: the PNG itself.
    with game_for(arguments.executable, out, "game2x", scale=2) as g:
        open_free_duel(g, flags=[LOCK_FLAG])
        page1 = shot(g, out, "2x-page1")
        g.press("r1", after=60)
        g.press("right", hold=2, after=30)
        g.press("right", hold=2, after=30)
        page2 = shot(g, out, "2x-page2")
        for key, image, slot in (("Simon the Wise", page1, 1), ("Dark Simon", page2, 40), ("Pegasus Prime", page2, 45)):
            face = expect[1] if slot == 1 else expect["dark-simon" if slot == 40 else "pegasus-prime"]
            sharp, blocky = distance(image, face[1], slot, 2), distance(image, pngio.scale_nearest(face[0], 2), slot, 2)
            check(results, image.size == (640, 480) and sharp < blocky and sharp < 12,
                  f"Internal 2x: {key} drawn from its PNG (mean difference {sharp:.1f} from the editor's 2x, "
                  f"{blocky:.1f} from its 1x doubled)")
        small = distance(page2, pngio.scale_nearest(expect["teana-locked"][0], 2), 41, 2)
        check(results, small < 6, f"Internal 2x: Teana Locked's 48x48 has no more to show: its 1x doubled "
                                  f"(mean difference {small:.1f})")
    # 3. Reverted: the disc's face, then the disc's name.
    revert_simon(folder, "face")
    from fm_editor import roster
    expect_after, after = expected_faces(game, folder)
    with game_for(arguments.executable, out, "reverted") as g:
        open_free_duel(g)
        page1 = shot(g, out, "1x-page1-reverted")
        check(results, mismatch(page1, expect_after[1][0], 1) == 0 and roster.replacement(after, 1).portrait is None,
              "the face reverted in the editor: Simon's cell is the disc's again (his new name stays)")
        g.press("right", hold=2, after=30)
        shot(g, out, "1x-page1-reverted-name")
    revert_simon(folder, "all")
    check(results, not (folder / "duelists/simon-muran.json").exists() and
          not (folder / "portraits/simon-muran.png").exists(),
          "name and face both back: the replacement's files are gone from the mod")
    for label in ("game1x", "locked", "game2x", "reverted", "fixed"):
        text = said(out, label)
        notes = [line for line in text.splitlines() if f"mod {MOD}:" in line]
        added = "duelists: 4 added, 1 replaced" in text
        check(results, added and not notes, f"{label}: the game read 4 added duelists and 1 replaced, and said nothing "
                                            "against the mod" + (f": {notes}" if notes else ""))
    for patch in answers:
        patch.stop()
    (out / "results.txt").write_text("\n".join(done + [""] + results) + "\n")
    print("\n".join(done))
    failed = [r for r in results if r.startswith("FAIL")]
    print(f"{len(results) - len(failed)} of {len(results)} checks passed; shots in {out / 'shots'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
