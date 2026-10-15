"""Editor save/reopen -> native duel checks against the player's disc.

Compare CPU spell decisions and outcomes for retail spells and converted
copies, even after the original effect cards become monsters. Run both:
    python3 tests/pc/editor_mods_runtime.py --out tmp/pc/editor-runtime
    python3 tests/pc/editor_mods_runtime.py --hard-mode --out tmp/pc/editor-runtime-hard
Settings, mods and saves are isolated from the player's files.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from fm_editor import disc, fixed_decks, gamedata, manifest
from fm_editor.model import Project
from yfm_control import Game, SIDE_SIZE


def spell_project(retail, converted):
    project = Project(retail)
    project.info.id = "editor-runtime"
    effects = [cid for cid, card in sorted(retail.cards.items()) if card.type == gamedata.TYPE_MAGIC]
    cards = effects.copy()
    if converted:
        cards = []
        for effect in effects:
            cid = project.add_card(3, f"spell-{effect}")
            project.cards[cid] = project.cards[cid].copy(
                type=gamedata.TYPE_MAGIC, attack=0, defense=0, level=0,
                star1=0, star2=0, attribute=6)
            project.added[cid].extra["effect"] = effect
            cards.append(cid)
            project.cards[effect] = project.cards[effect].copy(type=0, attack=100, defense=100)
            project.card_extra[effect] = {"model": 5}
    decks = {gamedata.DUELIST_NAMES[i]: {"fixed": True, project.identity(cid) if converted else str(cid): 40}
             for i, cid in enumerate(cards, 1)}
    messages = []
    for name, entry in decks.items():
        fixed_decks.read_entry(project, name, entry, messages)
    assert not messages, messages
    return project, cards, effects


def spell_run(executable, out, retail, converted, hard_mode):
    project, cards, effects = spell_project(retail, converted)
    mod = out / "mods/editor-runtime"
    manifest.save_mod(project, mod)
    reopened, messages = manifest.open_mod(retail, mod)
    assert not messages, messages
    assert manifest.build(reopened) == manifest.build(project), "editor save/reopen changed the mod"
    if hard_mode:
        link = out / "mods/ai-hard-mode"
        if not link.exists():
            link.symlink_to((executable.parent / "mods/ai-hard-mode").resolve(), target_is_directory=True)
    results = {}
    with Game(executable=executable, out=out / "game", mods_dir=out / "mods",
              settings={"mod.editor-runtime": 1, "mod.ai-hard-mode": int(hard_mode),
                        "mod.ai-hard-mode.trace": int(hard_mode),
                        "mod.3d-monsters": 0, "mod.hand-camera": 0},
              env={"MEMORIES_TRACE_MODS": "1"}) as game:
        for opponent, (cid, effect) in enumerate(zip(cards, effects), 1):
            game.goto("duel", opponent=opponent, deck=[5, 4, 6, 7, 8, 9, 10])
            game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [5, 4, 6, 7, 8]))
            # Give healing a reason to activate and removal a real target.
            game.poke(game.address("D_800E9FF0") + SIDE_SIZE + 0x12, struct.pack("<HH", 4000, 4000))
            game.play_card(0, face_up=True)
            assert game.decks()[1] == [cid] * 40, game.decks()[1]
            game.end_turn()
            state = game.duel()
            for side in state:
                for zone in ("hand", "monsters", "spells"):
                    for card in side[zone]:
                        if card and card["id"] == cid:
                            card["id"] = effect
            results[effect] = {"sides": state, "terrain": game.u8("gDuel_bTerrain"),
                               "effect": game.u16("gDuel_wEffectCardID")}
            assert game.u16("gDuel_wCardEffectFlags") == 0, "CPU effect did not finish"
            if 343 <= effect <= 347:
                assert state[0]["lp"] == 8000 - (50, 100, 200, 500, 1000)[effect - 343], state
            elif 338 <= effect <= 342:
                assert state[1]["lp"] == min(8000, 4000 + (200, 500, 1000, 2000, 5000)[effect - 338]), state
            elif effect in (336, 337):
                assert not any(state[0]["monsters"]), state
            print(f"{'converted' if converted else 'retail'} CPU spell {effect}: turn completed", flush=True)
        if hard_mode:
            assert "ai-hard-mode: opponent=" in game.log_path.read_text(errors="replace")
    (out / "results.json").write_text(json.dumps(results, indent=2))
    return results


def run(executable, out, hard_mode):
    retail = gamedata.load_game(disc.find_game([ROOT / "game"]))
    baseline = spell_run(executable, out / "retail", retail, False, hard_mode)
    converted = spell_run(executable, out / "converted", retail, True, hard_mode)
    for effect, expected in baseline.items():
        assert converted[effect] == expected, (effect, expected, converted[effect])
    print(f"All {len(baseline)} CPU spell decisions/outcomes match retail after editor save/reopen.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--hard-mode", action="store_true")
    args = parser.parse_args()
    if args.out:
        run(args.executable.resolve(), args.out.resolve(), args.hard_mode)
    else:
        with tempfile.TemporaryDirectory(prefix="fm-editor-runtime-") as folder:
            run(args.executable.resolve(), Path(folder), args.hard_mode)
