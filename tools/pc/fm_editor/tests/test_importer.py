"""The retail-diff importer on synthetic files: a "community mod" made by
changing the fixture's tables, text and bytes, imported back as a port mod."""
import random
import struct
import tempfile
import unittest
from pathlib import Path

from fm_editor import gamedata as g, importer, manifest
from fm_editor.disc import GameFiles
from fm_editor.model import Project
from fm_editor.tests import fixtures
from fm_editor.tests.test_data import fixture, state


def modded():
    f = fixture()
    cards = {cid: card.copy() for cid, card in f.cards.items()}
    cards[5].attack += 100
    cards[6].name = "Dark Card"
    cards[7].description = "New text."
    fusions = dict(f.fusions)
    fusions[(1, 2)] = 4
    fusions[(598, 599)] = 600
    equips = {k: list(v) for k, v in f.equips.items()}
    equips[652].append(8)
    pools = [{p: dict(v) for p, v in d.items()} for d in f.pools]
    deck = pools[3]["deck"]
    first, second = sorted(deck)[:2]
    deck[first] -= 50
    deck[second] += 50
    slus = bytearray(fixtures.make_slus(cards, {0x330: "Heishin X"}))
    slus[g.slus_offset(0x800917F0)] = 9                      # an AI parameter
    wa = bytearray(fixtures.make_wa(fusions, equips, f.rituals, pools))
    wa[0x100:0x104] = b"\x01\x02\x03\x04"                     # a small patch
    wa[0x169000:0x169000 + 5000] = bytes([7]) * 5000          # a long run: sectors
    return GameFiles(bytes(slus), bytes(wa), "modded"), cards, fusions, equips, pools


class ImporterTest(unittest.TestCase):
    def test_import(self):
        f = fixture()
        retail_files = GameFiles(f.slus, f.wa, "retail")
        modded_files, cards, fusions, equips, pools = modded()
        modded_files.wa_lba = 9173        # a modified disc lays its files out elsewhere: the lba stays retail's
        result = importer.import_modded(retail_files, modded_files, "community")
        report = "\n".join(result.report)
        self.assertIn("AI parameters", report)
        self.assertIn("cards: 3 changed", report)
        self.assertNotIn("in the names bank", report)               # the changed names are text, not code
        self.assertIn("where the retail text was", report)     # card 7's shorter text leaves old bytes behind
        project = result.project
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "community"
            importer.save(result, folder)
            data = manifest.read_json(folder / "mod.json")
            text = (folder / "text.txt").read_text(encoding="utf-8")
            self.assertIn("[8330]", text)
            self.assertIn("Heishin X", text)
            self.assertNotIn("Dark Card", text)          # card names go in cards[]
            self.assertEqual(data["text"], "text.txt")
            patch = data["data"][0]
            self.assertEqual(patch["patch"], [{"at": "0x100", "bytes": "01 02 03 04"}])
            sectors = data["data"][1]
            self.assertEqual((sectors["lba"], sectors["sectors"]), (10102 + 0x169000 // 2048, 3))
            self.assertEqual((folder / sectors["replace"]).read_bytes(), modded_files.wa[0x169000:0x169000 + 3 * 2048])
            self.assertTrue((folder / "import-report.txt").exists())
            # Opened over retail, the mod is the modified game's tables.
            opened, messages = manifest.open_mod(f.game(), folder)
            self.assertEqual(messages, [])
            expected = g.read_game(modded_files.slus, modded_files.wa)
            for cid in (5, 6, 7):
                self.assertTrue(opened.cards[cid].same(expected.cards[cid]))
            self.assertEqual(opened.fusions, expected.fusions)
            # The editor lists every equip card, those equipping nothing included.
            self.assertEqual({e: set(m) for e, m in expected.equips.items()},
                             {e: m for e, m in opened.equips.items() if m or e in expected.equips})
            self.assertEqual(opened.pools, expected.pools)
        self.assertEqual(state(project)[2], expected.fusions)

    def test_same_game_imports_nothing(self):
        f = fixture()
        files = GameFiles(f.slus, f.wa, "retail")
        result = importer.import_modded(files, files, "same")
        built = manifest.build(result.project)
        self.assertEqual(set(built) - {"id", "name", "version", "description"}, set())

    def test_runs(self):
        a = bytes(100)
        b = bytearray(a)
        b[10] = 1
        b[20] = 1
        b[90] = 1
        self.assertEqual(importer._runs(a, bytes(b), 0, 100), [(10, 21), (90, 91)])
        self.assertEqual(importer._subtract([(0, 100)], [(10, 20), (50, 60)]), [(0, 10), (20, 50), (60, 100)])


# --- encoded drop pools, text-bank code, WA runs, spaces ------------------------------

def _word_at(slus: bytearray, address: int, word: int):
    struct.pack_into("<I", slus, g.slus_offset(address), word)


def encoded_mod(bias: int, shift: int, code: bool):
    """The fixture with every drop pool of opponents 1-39 written as
    bias + (weight << shift) + noise (opponent 0 left alone), and, with
    `code`, the draw's add replaced by a jump to code in the dialog bank
    that undoes it (addiu v0, v0, -bias; sra v0, v0, shift)."""
    f = fixture()
    rng = random.Random(7)
    pools = [{p: dict(v) for p, v in d.items()} for d in f.pools]
    pools[1]["pow"] = {10: 1024, 11: 1000, 12: 24}
    wa = bytearray(f.wa)
    for d in range(1, g.DUELIST_COUNT):
        for p in importer.DROP_POOLS:
            raw = [bias + (pools[d][p].get(cid, 0) << shift) + rng.randrange(1 << shift)
                   for cid in range(1, g.CARD_COUNT + 1)]
            struct.pack_into("<%dH" % g.CARD_COUNT, wa, g.DUELIST_BASE + d * g.DUELIST_STRIDE + g.POOL_OFFSETS[p], *raw)
    slus = bytearray(f.slus)
    if code:
        cave = 0x801BFFD0
        _word_at(slus, importer.DRAW_ADD, (2 << 26) | ((cave >> 2) & 0x3FFFFFF))            # j cave
        _word_at(slus, cave, (9 << 26) | (2 << 21) | (2 << 16) | (-bias & 0xFFFF))          # addiu v0, v0, -bias
        _word_at(slus, cave + 4, (2 << 16) | (2 << 11) | (shift << 6) | 3)                  # sra v0, v0, shift
        _word_at(slus, cave + 8, 0x00822021)                                                 # addu a0, a0, v0
        _word_at(slus, cave + 12, (2 << 26) | (((importer.DRAW_ADD + 8) >> 2) & 0x3FFFFFF))  # j back
    return f, GameFiles(bytes(slus), bytes(wa), "modded"), pools


class ModdedGameTest(unittest.TestCase):
    def imported(self, f, modded_files):
        result = importer.import_modded(GameFiles(f.slus, f.wa, "retail"), modded_files, "community")
        return result.project, "\n".join(result.report)

    def test_encoded_pools_with_the_draw_code(self):
        f, files, pools = encoded_mod(1000, 2, code=True)       # not the tool's values: they come from the code
        project, report = self.imported(f, files)
        self.assertEqual(project.pools, pools)
        self.assertIn("jumps to the mod's code at 0x801BFFD0", report)
        self.assertIn("max(0, (raw - 1000) >> 2)", report)
        self.assertNotIn("scaled", report)
        # The code is reported where it is, with the jump that reaches it.
        self.assertIn("0x801BFFD0-0x801BFFE0 (13 bytes, in the dialog bank; reached by j at 0x80021860 (patched))",
                      report)

    def test_encoded_pools_without_recognized_code(self):
        for bias, shift in ((2512, 3), (3000, 3)):
            with self.subTest(bias=bias):
                f, files, pools = encoded_mod(bias, shift, code=False)
                project, report = self.imported(f, files)
                self.assertEqual(project.pools, pools)
                self.assertIn(f"max(0, (raw - {bias}) >> {shift})", report)
                self.assertIn("was not recognized", report)
                self.assertNotIn("scaled", report)

    def test_pools_off_2048_otherwise_are_scaled(self):
        f = fixture()
        pools = [{p: dict(v) for p, v in d.items()} for d in f.pools]
        pools[2]["bcd"] = {10: 3000, 11: 3000}
        project, report = self.imported(f, GameFiles(f.slus, fixtures.make_wa(f.fusions, f.equips, f.rituals, pools),
                                                     "modded"))
        self.assertEqual(project.pools[2]["bcd"], {10: 1024, 11: 1024})
        self.assertIn("scaled to 2048", report)

    def test_changes_beside_the_pools(self):
        f = fixture()
        pools = [{p: dict(v) for p, v in d.items()} for d in f.pools]
        for d, p, cid in ((5, "pow", g.CARD_COUNT), (5, "bcd", 1), (7, "deck", g.CARD_COUNT)):
            top = max(pools[d][p], key=pools[d][p].get)
            pools[d][p][top] -= 50
            pools[d][p][cid] = pools[d][p].get(cid, 0) + 50
        wa = bytearray(fixtures.make_wa(f.fusions, f.equips, f.rituals, pools))
        beside = g.DUELIST_BASE + 7 * g.DUELIST_STRIDE + g.POOL_OFFSETS["pow"] - 4    # between two pools
        wa[beside] = 0x5A
        project, report = self.imported(f, GameFiles(f.slus, bytes(wa), "modded"))
        self.assertEqual(project.pools, pools)
        # One patch of the one byte, none for the bytes between the changed pools.
        self.assertEqual(manifest.build(project)["data"], [{"file": importer.WA_FILE,
                                                            "patch": [{"at": f"0x{beside:X}", "bytes": "5A"}]}])

    def test_spaces_at_line_ends(self):
        f = fixture()
        cards = {cid: card.copy() for cid, card in f.cards.items()}
        cards[5].attack += 100
        cards[8].description = cards[8].description.replace("\n", "  \n") + " "
        cards[9].name += " "
        project, report = self.imported(f, GameFiles(fixtures.make_slus(cards, f.other_names), f.wa, "modded"))
        self.assertIn("cards: 1 changed", report)
        self.assertIn("2 names or texts differ from retail only by spaces", report)
        self.assertEqual(project.cards[8].description, f.cards[8].description)
        self.assertEqual(project.cards[9].name, f.cards[9].name)


if __name__ == "__main__":
    unittest.main()
