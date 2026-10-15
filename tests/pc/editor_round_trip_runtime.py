#!/usr/bin/env python3
"""Live FM Editor round trip (built game and user-supplied disc).

Makes a mod through every tab of the FM Editor the way a modder would (the
tabs' own buttons and dialogs: a card renamed and one added, a picture
imported, a fusion added and one taken away, an equip given every Dragon, a
ritual's recipe removed, a duelist's deck reweighted, a starter deck from
Kaiba's, a value, a Guardian Star matchup, a pack of Heishin's drops, the
map's camera, a setting), exports it as File > Export would, and starts the
game on it into the first duel: the game must read every part of it and
say nothing against any. Artifacts stay in tmp/pc/fm-editor-mod (or --out).

    python3 tests/pc/editor_round_trip_runtime.py [--executable PATH] [--out DIR]
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/pc/fm-editor-mod"
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
MOD = "editor-round-trip"
POOLS_MOD = "editor-round-trip-pools"
FRAMES = 6600     # past the new game's starter deck, into the first duel (tests/pc/smoke/duel-hand-camera.json)


def make_mod(game: Path, out: Path) -> list:
    """The mod, made through the tabs; what each tab did."""
    sys.path.insert(0, str(ROOT / "tools/pc"))
    from fm_editor.app import App
    from fm_editor import pngio
    from fm_editor.gamedata import TYPE_NAMES
    from fm_editor.tests.test_art import gradient

    answers = [mock.patch("tkinter.messagebox." + n, return_value=True) for n in ("askyesno", "askokcancel")]
    for patch in answers:
        patch.start()
    app = App(ask=False, autostart=False)
    app.withdraw()
    app.update()
    app.start(str(game), None, False)
    app.update()
    p = app.project
    done = []
    info = app.info
    info.vars["id"].set(MOD)
    info.vars["name"].set("FM Editor round trip")
    assert info.commit()
    dialog = info.add_setting()
    dialog.fields["key"].set("extra")
    dialog.fields["default"].set("1")
    dialog.ok()
    done.append("Mod info: a setting")

    cards = app.cards
    cards.goto(3)
    cards.vars["name"].set("Hitotsu-me Titan")
    cards.vars["attack"].set("2600")
    assert cards.apply()
    cards.goto(1)
    cards.add_card()
    added = max(p.added)
    cards.vars["name"].set("Blue-eyes Round Trip")
    assert cards.apply()
    done.append(f"Cards: 3 renamed, {added} added")

    app.art.goto(3)
    picture = out / "art3.png"
    pngio.write(picture, gradient(102, 96))
    app.art.use_file("art", str(picture))
    done.append("Art: card 3's picture")

    fusions = app.fusions
    dialog = fusions.add()
    for key, value in zip("abr", (3, added, 1)):
        dialog.fields[key].set(value)
    dialog.ok()
    pair = sorted(p.retail.fusions)[0]
    fusions.show_card(pair[0])
    fusions.tree.selection_set(f"{pair[0]}:{pair[1]}")
    fusions.remove()
    done.append(f"Fusions: 3 + {added} = 1, {pair} taken away")

    equips = app.equips
    equips.show_card(301)
    dragon = TYPE_NAMES.index("Dragon")
    equips.type_boxes[dragon][1].set(1)
    equips.toggle_type(dragon)
    done.append("Equips: Legendary Sword fits every Dragon")

    rituals = app.rituals
    ritual = sorted(p.retail.rituals)[0]
    rituals.tree.selection_set(str(ritual))
    rituals.remove()
    done.append(f"Rituals: {ritual}'s recipe removed")

    duelists = app.duelists
    duelists.goto((1, "deck"))
    duelists.tree.selection_set(duelists.tree.get_children()[0])
    duelists.weight.set("300")
    duelists.set_weight()
    done.append("Duelists: Simon Muran's deck reweighted")

    with mock.patch.object(app.starter, "ask_opponent", return_value=17):
        app.starter.add_deck("opponent").ok()
    done.append("Starter decks: Kaiba's likeliest forty")

    app.values.vars["stats"].set("12000")
    assert app.values.commit()
    done.append("Values: ATK/DEF cap 12000")

    stars = app.stars
    stars.pick_cell(1, 2)
    stars.value.set("700")
    stars.set_cell()
    done.append("Guardian Stars: Mars over Jupiter by 700")

    dialog = app.packs.add_from_drops()
    boxes = [w for w in dialog.winfo_children()[0].winfo_children() if w.winfo_class() == "TCombobox"]
    boxes[0].set("8 Heishin")
    boxes[1].set("B/C/D drops")
    dialog.ok()
    done.append("Packs: a pack of Heishin's B/C/D drops")

    app.map.select(0)
    app.map.vars["distance"].set(int(app.map.vars["distance"].get()) + 200)
    done.append("Map: Metropolis' camera further away")

    app.update()
    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out / "mods")):
        assert app.save(ask=True, export=True)
    app.dirty = False
    app.destroy()
    for patch in answers:
        patch.stop()
    return done


def make_pools_mod(game: Path, out: Path):
    """A second mod, a new game's deck drawn from weighted pools (the
    Starter decks tab's Weighted pools page): the disc's seven, one card's
    weight changed. A written deck would be dealt first, so it is alone."""
    from fm_editor.app import App
    answers = [mock.patch("tkinter.messagebox." + n, return_value=True) for n in ("askyesno", "askokcancel")]
    for patch in answers:
        patch.start()
    app = App(ask=False, autostart=False)
    app.withdraw()
    app.update()
    app.start(str(game), None, False)
    app.update()
    app.info.vars["id"].set(POOLS_MOD)
    assert app.info.commit()
    page = app.starter.pools
    page.from_retail()
    page.tree.selection_set(page.tree.get_children()[0])
    page.weight.set("500")
    page.set_weight()
    app.update()
    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out / "pool-mods")):
        assert app.save(ask=True, export=True)
    app.dirty = False
    app.destroy()
    for patch in answers:
        patch.stop()


def play(executable: Path, mods: Path, out: Path, mod: str) -> str:
    """A new game into the first duel on the mods; what the game said."""
    opening = json.loads((ROOT / "tests/pc/smoke/duel-hand-camera.json").read_text())["input"]
    settings = out / f"{mod}.settings.txt"
    settings.write_text(f"mod.3d-monsters=0\nmod.hand-camera=0\nmod.ai-hard-mode=0\nmod.{mod}=1\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
    env.update(MEMORIES_HEADLESS="1", MEMORIES_NO_AUDIO="1", MEMORIES_NO_GAMEPAD="1", MEMORIES_SPEED="-1",
               MEMORIES_NO_MONITOR="1", MEMORIES_DETERMINISTIC="1", MEMORIES_SETTINGS=str(settings),
               MEMORIES_USER_DIR=str(out / f"{mod}.user"), MEMORIES_INPUT=opening, MEMORIES_DUMP_FRAME=str(FRAMES),
               MEMORIES_DUMP_PATH=str(out / f"{mod}.ppm"), MEMORIES_TRACE="mods",
               MEMORIES_LOG=str(out / f"{mod}.trace.log"), MEMORIES_MODS_DIR=str(mods))
    with (out / f"{mod}.run.log").open("w") as log:
        subprocess.run([str(executable)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=600)
    said = (out / f"{mod}.run.log").read_text(errors="replace") + \
        (out / f"{mod}.trace.log").read_text(errors="replace")
    complaints = [line for line in said.splitlines() if f"mod {mod}:" in line]
    assert not complaints, f"the game said of the editor's {mod}:\n" + "\n".join(complaints)
    return said


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", type=Path, default=EXECUTABLE)
    parser.add_argument("--out", type=Path, default=OUT)
    arguments = parser.parse_args()
    out = arguments.out
    shutil.rmtree(out, ignore_errors=True)
    (out / "mods").mkdir(parents=True)
    game = Path(os.environ.get("MEMORIES_DISC_DIR", ROOT / "game"))
    done = make_mod(game, out)
    manifest = json.loads((out / "mods" / MOD / "mod.json").read_text(encoding="utf-8"))

    said = play(arguments.executable, out / "mods", out, MOD)
    expected = [f"{MOD}: 0 replaced regions, 2 patched runs",                      # the map
                "texture pack", "2 images",                                       # the art
                "card 3 Hitotsu-me Giant replaced", "cards 723-723 are copies of 1",
                "tables: 2 fusion rules, 1 equip rules", "1 rituals, 1 pool edits",
                "limits: ATK 12000, DEF 12000",
                f"starter: \"Kaiba's deck\" from {MOD}"]
    missing = [text for text in expected if text not in said]
    assert not missing, f"not read by the game: {missing} (see {out})"
    for key in ("guardian_stars", "packs", "settings"):
        assert key in manifest, key
    make_pools_mod(game, out)
    said = play(arguments.executable, out / "pool-mods", out, POOLS_MOD)
    assert "starter: dealt from 7 pools" in said, f"the pools were not dealt from (see {out})"
    done.append("Starter decks, Weighted pools: the disc's seven, one weight changed (dealt from 7 pools)")
    print("fm editor mod: the game read every tab's part, without a note:\n  " + "\n  ".join(done))


if __name__ == "__main__":
    main()
