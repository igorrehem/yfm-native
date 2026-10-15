"""A mod's "starter_pools": pools of its own for a new game's deck to be drawn
from (starter_pools.py, src/pc/cards/starter.c, notes/starter-deck.md).

The checks here are the port's, so what the editor refuses is what the Mods
window would have complained about.
"""
import json
import tempfile
import unittest
from pathlib import Path

from fm_editor import manifest, starter_pools as sp, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture


class ReadWriteTest(unittest.TestCase):
    def setUp(self):
        self.retail = fixture().game()
        self.project = Project(self.retail)

    def pools(self, section):
        self.project.other["starter_pools"] = section
        self.project.starter_pool_state = None
        return sp.state(self.project)

    def test_a_pool_is_read_as_the_mod_wrote_it(self):
        pools = self.pools([{"name": "Weak", "draws": 16, "cards": {"1": 100, "2": 50}}])
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0].name, "Weak")
        self.assertEqual(pools[0].draws, 16)
        self.assertEqual(pools[0].cards, {1: 100, 2: 50})
        self.assertEqual(pools[0].total(), 150)
        self.assertEqual(pools[0].count(), 2)

    def test_one_pool_on_its_own_is_a_pool(self):
        pools = self.pools({"draws": 40, "cards": {"1": 1}})
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0].draws, 40)

    def test_a_card_it_cannot_place_keeps_its_row(self):
        pools = self.pools([{"draws": 40, "cards": {"No Such Card": 3, "2": 1}}])
        self.assertEqual(pools[0].cards, {2: 1})
        self.assertEqual(pools[0].kept, {"No Such Card": 3})
        # And it is written back, so the mod is not quietly changed.
        built = sp.build(pools, self.project.ref)
        self.assertEqual(built[0]["cards"].get("No Such Card"), 3)

    def test_keys_the_editor_does_not_know_are_kept(self):
        pools = self.pools([{"draws": 40, "cards": {"1": 1}, "something": {"a": 1}}])
        self.assertEqual(pools[0].extra, {"something": {"a": 1}})
        self.assertEqual(sp.build(pools, self.project.ref)[0]["something"], {"a": 1})

    def test_storing_puts_it_back_into_the_manifest(self):
        pools = self.pools([])
        pools.append(sp.Pool(name="Weak", draws=40, cards={1: 100}))
        sp.store(self.project)
        self.assertEqual(self.project.other["starter_pools"],
                         [{"name": "Weak", "draws": 40, "cards": {self.project.ref(1): 100}}])
        pools.clear()
        sp.store(self.project)
        self.assertNotIn("starter_pools", self.project.other)

    def test_it_survives_saving_and_reopening(self):
        self.pools([{"name": "Weak", "draws": 16, "cards": {"1": 100}},
                    {"draws": 24, "cards": {"2": 5}}])
        self.project.info.id = "pooltest"
        self.project.info.name = "Pool test"
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "mod"
            manifest.save_mod(self.project, str(out))
            written = json.loads((out / "mod.json").read_text())
            self.assertEqual(len(written["starter_pools"]), 2)
            again, notes = manifest.open_mod(self.retail, str(out))
        self.assertEqual(notes, [])
        back = sp.state(again)
        self.assertEqual([p.draws for p in back], [16, 24])
        self.assertEqual(back[0].name, "Weak")
        self.assertEqual(back[0].cards, {1: 100})
        self.assertTrue(sp.deals(again))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.retail = fixture().game()
        self.project = Project(self.retail)

    def problems(self, section):
        self.project.other["starter_pools"] = section
        self.project.starter_pool_state = None
        out = []
        sp.check(self.project, out)
        return [(i.level, i.message) for i in out]

    def test_pools_that_draw_forty_say_nothing(self):
        self.assertEqual(self.problems([{"draws": 20, "cards": {"1": 1, "2": 1, "3": 1,
                                                                "4": 1, "5": 1, "6": 1, "7": 1}},
                                        {"draws": 20, "cards": {"8": 1, "9": 1, "10": 1,
                                                                "11": 1, "12": 1, "13": 1, "14": 1}}]), [])

    def test_draws_that_do_not_make_forty(self):
        found = self.problems([{"draws": 10, "cards": {"1": 1}}])
        self.assertTrue(any(level == "error" and "not the 40" in message
                            for level, message in found), found)

    def test_a_pool_that_draws_but_weights_nothing(self):
        found = self.problems([{"draws": 40, "cards": {}}])
        self.assertTrue(any(level == "error" and "weights none" in message
                            for level, message in found), found)

    def test_a_card_it_cannot_place_is_an_error(self):
        found = self.problems([{"draws": 40, "cards": {"No Such Card": 1}}])
        self.assertTrue(any(level == "error" and "no such card" in message
                            for level, message in found), found)

    def test_drawing_more_than_the_copy_limit_allows_is_a_warning(self):
        """The port retries a card already held three times, and gives up
        after a bounded number of tries."""
        found = self.problems([{"draws": 40, "cards": {"1": 1}}])
        self.assertTrue(any(level == "warning" and "copies each the draw is retried" in message
                            for level, message in found), found)

    def test_a_written_deck_takes_precedence_and_says_so(self):
        from fm_editor.model import StarterDeck
        self.project.starter.append(StarterDeck(name="written", cards={1: 40}))
        found = self.problems([{"draws": 40, "cards": {"1": 1, "2": 1, "3": 1,
                                                       "4": 1, "5": 1, "6": 1}}])
        self.assertTrue(any(level == "warning" and "dealt first" in message
                            for level, message in found), found)

    def test_validate_reports_them_with_the_rest(self):
        self.project.other["starter_pools"] = [{"draws": 10, "cards": {"1": 1}}]
        self.project.starter_pool_state = None
        issues = validate.validate(self.project)
        self.assertTrue(any(i.area == "Starter pools" for i in issues))


class DealTest(unittest.TestCase):
    def test_a_deal_never_has_four_of_a_card(self):
        """As the disc's deal: a card dealt three times is drawn again."""
        import random
        pools = [sp.Pool(draws=40, cards={1: 1000, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1, 10: 1, 11: 1,
                                          12: 1, 13: 1, 14: 1})]
        for seed in range(50):
            deck = sp.deal(pools, random.Random(seed))
            self.assertEqual(sum(deck.values()), 40)
            self.assertLessEqual(max(deck.values()), 3)
        # A pool too small for its draws deals what it has.
        self.assertEqual(sum(sp.deal([sp.Pool(draws=10, cards={1: 5})]).values()), 3)


if __name__ == "__main__":
    unittest.main()


class RetailTest(unittest.TestCase):
    """The disc's own seven rows (notes/starter-deck-pools.md)."""

    def test_an_archive_without_them_offers_none(self):
        self.assertEqual(sp.retail(b""), [])
        self.assertEqual(sp.retail(b"\0" * 1024), [])

    def test_the_rows_are_read_where_the_archive_has_them(self):
        """A record apiece: the draws, then a weight for each card."""
        import struct
        blob = bytearray(sp.RETAIL_AT + 7 * sp.RETAIL_STRIDE)
        for n, draws in enumerate((16, 16, 4, 1, 1, 1, 1)):
            at = sp.RETAIL_AT + n * sp.RETAIL_STRIDE
            struct.pack_into("<H", blob, at, draws)
            struct.pack_into("<H", blob, at + 2, 2048)          # card 1 takes it all
        pools = sp.retail(bytes(blob))
        self.assertEqual([pool.draws for pool in pools], [16, 16, 4, 1, 1, 1, 1])
        self.assertEqual(sp.retail_drawn(pools), sp.DRAWS)
        self.assertEqual(pools[0].cards, {1: 2048})
        self.assertEqual(pools[0].name, "Weakest monsters")

    def test_the_last_two_weights_are_past_what_the_game_reads(self):
        """The generator scans 720 of the 722 stored."""
        import struct
        blob = bytearray(sp.RETAIL_AT + 7 * sp.RETAIL_STRIDE)
        at = sp.RETAIL_AT
        struct.pack_into("<H", blob, at + 2 + sp.RETAIL_SCAN * 2, 500)
        struct.pack_into("<H", blob, at + 2 + (sp.RETAIL_WEIGHTS - 1) * 2, 500)
        self.assertEqual(sp.retail(bytes(blob))[0].cards, {})
