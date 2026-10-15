#!/usr/bin/env python3
"""Editor table edits exercised in the built game, with the player's disc.

Uses the tabs' controls to export fusion additions/removals, equip targets,
Guardian Star matchups, card art, a campaign camera/name panel and a pack. Checks
their effects with the mod enabled and disabled, rather than just checking
that their manifest sections exist. Settings, mods and saves are isolated.

    xvfb-run -a python3 tests/pc/editor_tables_runtime.py [--out DIR]
"""
import argparse
import json
import os
from pathlib import Path
import struct
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from fm_editor import campaign_map, manifest, pngio, validate
from yfm_control import Game

MOD = "editor-tables"
BLUE_EYES, ELF, GIANT, MUSHROOM, SWORD = 1, 2, 3, 8, 301
PRICE, COUNT = 37, 3


def make_mod(out):
    from fm_editor.app import App
    app = App(ask=False, autostart=False)
    app.withdraw()
    app.update()
    try:
        app.start(str(Path(os.environ.get("MEMORIES_DISC_DIR", ROOT / "game"))), None, False)
        app.update()
        app.info.vars["id"].set(MOD)
        assert app.info.commit()
        retail_map = campaign_map.state(app.project).retail.raw["before"]

        dialog = app.fusions.add()
        for key, value in zip("abr", (ELF, GIANT, BLUE_EYES)):
            dialog.fields[key].set(value)
        dialog.ok()
        app.fusions.show_card(ELF)
        app.fusions.tree.selection_set(f"{ELF}:{MUSHROOM}")
        app.fusions.remove()
        retail_fusion = app.project.retail.fusions[(ELF, MUSHROOM)]

        app.equips.show_card(SWORD)
        with mock.patch("fm_editor.tabs.pick_card", return_value=BLUE_EYES):
            app.equips.add()

        # Equal base stats isolate the stars' contribution to battle damage.
        for cid, star in ((ELF, "Mars"), (GIANT, "Jupiter")):
            app.cards.goto(cid)
            for key, value in (("attack", "2000"), ("defense", "2000"),
                               ("star1", star), ("star2", "(none)")):
                app.cards.vars[key].set(value)
            assert app.cards.apply()
        app.stars.pick_cell(1, 2)
        app.stars.value.set("700")
        app.stars.set_cell()

        app.duelists.goto((1, "deck"))
        fixed = app.duelists.fixed
        fixed.mode.set("fixed")
        fixed.switch()
        fixed.clear()
        fixed.copies.set("40")
        with mock.patch("fm_editor.fixed_deck_view.pick_card", return_value=GIANT):
            fixed.add_card()

        app.map.select(0)
        app.map.vars["distance"].set(int(app.map.vars["distance"].get()) + 321)
        edited_map = campaign_map.pack_table(campaign_map.state(app.project).locations)
        assert edited_map != retail_map

        card_art = out / "card-art.png"
        pngio.write(card_art, pngio.Image(102, 96, bytes((0, 255, 255, 255)) * (102 * 96)))
        app.art.goto(BLUE_EYES)
        assert app.art.use_file("art", str(card_art))
        from fm_editor.map_tab import MapPictures
        panel_art = out / "map-panel.png"
        pngio.write(panel_art, pngio.Image(128, 32, bytes((255, 0, 255, 255)) * (128 * 32)))
        pictures = MapPictures(app.map)
        pictures.sprite.set("Name panel")
        pictures.import_sprite(str(panel_art))
        pictures.destroy()

        packs = app.packs
        packs.add_pack()
        for key, value in (("name", "Editor Test Pack"), ("price", str(PRICE)), ("count", str(COUNT))):
            packs.vars[key].set(value)
        assert packs.commit()
        packs.add_cards([BLUE_EYES])
        assert not validate.errors(validate.validate(app.project))
        (out / "mods").mkdir(parents=True, exist_ok=True)
        with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out / "mods")):
            assert app.save(ask=True, export=True)
        before = manifest.build(app.project)
        app.load_mod(out / "mods" / MOD)
        assert manifest.build(app.project) == before, "save/reopen changed the table edits"
        return retail_map, edited_map, retail_fusion
    finally:
        app.dirty = False
        app.destroy()


def game(executable, out, name, enabled):
    return Game(executable=executable, out=out / name, mods_dir=out / "mods",
                settings={f"mod.{MOD}": int(enabled), "mod.3d-monsters": 0,
                          "mod.hand-camera": 0, "mod.ai-hard-mode": 0},
                env={"MEMORIES_TRACE": "mods"})


def duel(g, cards):
    deck = cards + [BLUE_EYES] * (40 - len(cards))
    g.goto("duel", opponent=1, deck=deck)
    g.duel_ready(before_deal=lambda g: g.arrange_deck(0, deck[:5]))


def colored(path, color):
    image = pngio.read(path)
    return sum(all(value >= 220 if want else value <= 32
                   for value, want in zip(image.rgba[i:i + 3], color))
               for i in range(0, len(image.rgba), 4))


def run(executable, out):
    with mock.patch("tkinter.messagebox.askyesno", return_value=True), \
            mock.patch("tkinter.messagebox.askokcancel", return_value=True):
        retail_map, edited_map, retail_fusion = make_mod(out)
    checks = []

    def passed(text):
        checks.append(text)
        print("ok:", text, flush=True)

    for enabled in (False, True):
        tag = "mod" if enabled else "retail"
        with game(executable, out, tag + "-duel", enabled) as g:
            duel(g, [ELF, GIANT])
            g.fuse([0, 1], face_up=True)
            expected = BLUE_EYES if enabled else GIANT
            assert [c for c in g.field()[2] if c] == [expected], g.field()
            g.shot("fusion-added.png")
            passed(f"{tag}: added fusion produces {expected}")

            duel(g, [ELF, MUSHROOM])
            g.fuse([0, 1], face_up=True)
            expected = MUSHROOM if enabled else retail_fusion
            assert [c for c in g.field()[2] if c] == [expected], g.field()
            g.shot("fusion-removed.png")
            passed(f"{tag}: removed fusion produces {expected}")

            duel(g, [BLUE_EYES, SWORD])
            g.fuse([0, 1], face_up=True)
            monster = next(c for c in g.duel()[0]["monsters"] if c)
            assert monster["id"] == BLUE_EYES
            expected = 500 if enabled else 0
            column = g.field()[2].index(BLUE_EYES)
            record = g.peek(g.address("D_801A7AD8") + (5 + column) * 0x1C, 0x1C)
            assert struct.unpack_from("<h", record, 0x12)[0] == expected
            g.shot("equip.png")
            passed(f"{tag}: equip grants {expected} points")

            duel(g, [BLUE_EYES])
            g.press("triangle", after=180)
            assert g.u16("gDuel_wViewerCardID") == BLUE_EYES
            pixels = colored(g.shot("card-art.png"), (0, 1, 1))
            assert (pixels > 5000) == enabled, (tag, pixels)
            passed(f"{tag}: card viewer renders {'imported' if enabled else 'retail'} artwork")

            if enabled:
                duel(g, [ELF, BLUE_EYES])
                g.play_card(0, face_up=True)
                g.end_turn()
                g.play_card(next(i for i, c in enumerate(g.duel()[0]["hand"])
                                 if c and c["id"] == BLUE_EYES), face_up=True)
                cpu = g.duel()[1]["monsters"]
                target = next(i for i, c in enumerate(g.field()[1]) if c == GIANT)
                # The CPU may set this equally strong monster in defense.
                # Put it in attack position to measure battle LP damage.
                cpu_column = next(i for i, c in enumerate(cpu) if c and c["id"] == GIANT)
                record = g.address("D_801A7AD8") + (20 + cpu_column) * 0x1C
                g.poke(record + 0x16, struct.pack("<H", cpu[cpu_column]["flags"] & ~0x1800))
                before = g.duel()[1]["lp"]
                g.attack(g.field()[2].index(ELF), target=target)
                assert before - g.duel()[1]["lp"] == 700, g.duel()
                g.shot("guardian-stars-battle.png")
                passed("mod: +700 Guardian Star matchup causes 700 battle damage between equal monsters")

        with game(executable, out, tag + "-map", enabled) as g:
            g.goto("map")
            g.wait_until(lambda g: g.resident("overworld"), 3000)
            g.step(300)
            expected = edited_map if enabled else retail_map
            actual = g.peek(0x80168000 + campaign_map.TABLE_OFFSET, len(expected))
            assert actual == expected, "campaign location table differs from the editor"
            pixels = colored(g.shot("map.png"), (1, 0, 1))
            assert (pixels > 1000) == enabled, (tag, pixels)
            passed(f"{tag}: live campaign map contains the expected camera and routes")
            passed(f"{tag}: campaign map renders {'imported' if enabled else 'retail'} name-panel artwork")

        with game(executable, out, tag + "-packs", enabled) as g:
            g.goto("password")
            g.step(300)
            g.poke("gLibrary_dwStarchips", struct.pack("<I", 1000))
            chest = g.peek("gLibrary_abCardChest", 722)
            start = g.vblank
            for at, button in ((30, "triangle"), (100, "cross"), (170, "cross"), (370, "square")):
                g.step(max(start + at - g.vblank, 0))
                g.press(button, hold=6, after=0)
            g.step(max(start + 490 - g.vblank, 0))
            expected = 1000 - PRICE if enabled else 1000
            assert g.u32("gLibrary_dwStarchips") == expected
            after = g.peek("gLibrary_abCardChest", 722)
            wanted = bytearray(chest)
            if enabled:
                wanted[BLUE_EYES - 1] += COUNT
            assert after == bytes(wanted), "pack awarded unexpected cards"
            g.shot("pack-purchase.png")
            passed(f"{tag}: pack purchase spends {1000 - expected} and awards {COUNT if enabled else 0} cards")
    (out / "checks.json").write_text(json.dumps(checks, indent=2))
    print(f"{len(checks)} live editor table checks passed; artifacts in {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path, default=ROOT / "tmp/pc/editor-tables")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    run(args.executable.resolve(), args.out.resolve())
