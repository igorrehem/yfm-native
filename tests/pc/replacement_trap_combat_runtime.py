#!/usr/bin/env python3
"""Disc-backed regression for replacement attack traps and monster combat effects.

The first duel gives the CPU a replacement House of Adhesive Tape which heals
its owner.  The player's attacking monster deals 100 damage on ``combat``;
the final LP delta proves the trap's heal, one (not two) combat trigger, and
ordinary battle damage all completed. Destruction must cancel combat and its
damage trigger. Defended battles also
exercise healing, removal of only the defender, and removal of both
participants, including restoration of a surviving attacker.
"""
import argparse
import json
from pathlib import Path
import sys
import struct
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from fm_editor import disc, gamedata, manifest
from fm_editor.model import Project
from yfm_control import Game


def run(executable, out):
    retail = gamedata.load_game(disc.find_game([ROOT / "game"]))
    project = Project(retail)
    project.info.id = "replacement-trap-combat-test"
    # A 50-point attacker makes no, one or two combat triggers distinguishable.
    project.cards[5] = project.cards[5].copy(attack=50)
    project.set_monster_effects(5, [{"when": "combat", "do": "damage", "amount": 100}])
    project.cards[3] = project.cards[3].copy(attack=100, defense=0)
    cases = [(1, "heal", None, False), (2, "destroy", None, False),
             (3, "heal", None, True), (4, "destroy", "own", True),
             (5, "destroy", "all", True)]
    decks, traps = {}, {}
    for opponent, action, target, defended in cases:
        cid = project.add_card(3, f"replacement-{opponent}-{action}")
        project.cards[cid] = project.cards[cid].copy(type=21, attack=0, defense=0, level=0,
                                                      star1=0, star2=0, attribute=7)
        extra = project.added[cid].extra
        extra.update({"effect": 681, "trap_threshold": 1000,
                      "card_effects_mode": "replace",
                      "card_effects": [{"do": action, "amount": 200} if action == "heal"
                                       else {"do": action}]})
        if target:
            extra["card_effects"][0]["target"] = target
        decks[gamedata.DUELIST_NAMES[opponent]] = {"fixed": True, project.identity(cid): 35 if defended else 40}
        if defended:
            decks[gamedata.DUELIST_NAMES[opponent]]["3"] = 5
        traps[opponent] = cid
    built = manifest.build(project)
    built["decks"] = decks
    # The healing case deliberately distinguishes one combat trigger from
    # none or two. Keep the retail 8,000 start, but leave room for its +200.
    built["limits"] = {"life_points": {"max": 9999}}
    mod = out / "mods/replacement-trap-combat-test"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "mod.json").write_text(json.dumps(built), encoding="utf-8")

    failures = []
    with Game(executable=executable, out=out / "game", mods_dir=out / "mods",
              settings={"mod.replacement-trap-combat-test": 1, "mod.3d-monsters": 0,
                        "mod.hand-camera": 0, "mod.ai-hard-mode": 0}, env={"MEMORIES_TRACE": "mods,duel-effects"}) as game:
        for opponent, action, target, defended in cases:
            label = f"{action}-{target or 'opponent'}-{'defended' if defended else 'direct'}"
            game.goto("duel", opponent=opponent, deck=[5, 339, 339, 4, 6, 7, 8, 9, 10])

            def arrange(g):
                g.arrange_deck(0, [5, 339, 339, 4, 6])
                if defended:
                    g.arrange_deck(1, [traps[opponent]] * 5 + [3])

            game.duel_ready(before_deal=arrange)
            game.play_card(0, face_up=True)
            if defended:
                # Keep the weak attacker safe while the CPU sets its defender.
                player_record = game.address("D_801A7AD8") + 5 * 0x1c
                game.poke(player_record + 0x16, struct.pack("<H", game.u16(player_record + 0x16) | 0x800))
            game.end_turn()
            assert any(c and c["id"] == traps[opponent] for c in game.duel()[1]["spells"]), game.duel()
            # A new turn starts in the hand. Play Red Medicine to reach the
            # field before selecting the existing monster's attack; healing
            # the player leaves the CPU LP assertions unchanged.
            slot = next(i for i, card in enumerate(game.duel()[0]["hand"])
                        if card and card["id"] == 339)
            game.play_card(slot, face_up=True)
            if defended:
                game.end_turn()
                slot = next(i for i, card in enumerate(game.duel()[0]["hand"])
                            if card and card["id"] == 339)
                game.play_card(slot, face_up=True)
                defender = game.duel()[1]["monsters"][0]
                assert defender and defender["id"] == 3, game.duel()
                # Attack-position zero ATK makes damage match the direct case.
                record = game.address("D_801A7AD8") + 20 * 0x1c
                game.poke(record + 0x16, struct.pack("<H", game.u16(record + 0x16) & ~0x1800))
                game.poke(record + 0x0e, struct.pack("<h", 0))
                game.poke(player_record + 0x16, struct.pack("<H", game.u16(player_record + 0x16) & ~0x1800))
            before = game.duel()
            target_column = next(i for i, card in enumerate(game.field()[1]) if card) if defended else None
            game.attack(0, target=target_column)
            game.step(180)
            after = game.duel()
            game.shot(f"replacement-{label}.png")
            (out / f"replacement-{label}.json").write_text(
                json.dumps({"before": before, "after": after}, indent=2), encoding="utf-8")
            assert not any(after[1]["spells"]), after
            problems = []
            if action == "heal":
                # +200 from the trap, -50 ordinary direct damage, -100 from
                # exactly one combat trigger.
                if after[1]["lp"] != before[1]["lp"] + 50:
                    problems.append(f"CPU LP {after[1]['lp']}, expected {before[1]['lp'] + 50}")
                if not after[0]["monsters"][0]:
                    problems.append("healing trap removed the attacker")
            else:
                if target != "own" and after[0]["monsters"][0]:
                    problems.append("destroying trap left the attacker on the field")
                if target == "own" and not after[0]["monsters"][0]:
                    problems.append("defender destruction removed the surviving attacker")
                if defended and after[1]["monsters"][0]:
                    problems.append("destroying trap left the defender on the field")
                if after[1]["lp"] != before[1]["lp"]:
                    problems.append("cancelled combat changed CPU LP")
            failures.extend(f"{label}: {problem}" for problem in problems)
            print(f"replacement {label} trap combat path: " +
                  ("FAILED: " + "; ".join(problems) if problems else "passed"), flush=True)
    assert not failures, "\n".join(failures)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        raise SystemExit(run(args.executable, args.out))
    with tempfile.TemporaryDirectory(prefix="fm-replacement-traps-") as folder:
        raise SystemExit(run(args.executable, Path(folder)))
