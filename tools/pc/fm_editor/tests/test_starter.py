"""The starter decks a mod offers a new game ("starter",
notes/starter-deck.md): the manifest layer, the checks, and the tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import manifest, validate
from fm_editor.gamedata import DECK_SIZE, EXODIA_FIRST_CARD_ID
from fm_editor.model import Project, StarterDeck
from fm_editor.tests.test_data import fixture


def project() -> Project:
    return Project(fixture().game())


def read(source: dict):
    p = project()
    messages = manifest.apply(p, {"id": "m", **source})
    return p, messages


def full(**cards) -> dict:
    """A deck of forty from three copies each, so nothing but what a case
    asks for is out of the ordinary."""
    deck = dict(cards)
    left, cid = DECK_SIZE - sum(deck.values()), 100
    while left > 0:
        take = min(3, left)
        deck[str(cid)] = take
        left -= take
        cid += 1
    return deck


class ManifestTest(unittest.TestCase):
    def test_one_deck_is_read_and_written_as_an_object(self):
        p, messages = read({"starter": full()})
        self.assertEqual(len(p.starter), 1)
        self.assertEqual(p.starter[0].total(), DECK_SIZE)
        self.assertTrue(p.starter[0].complete())
        self.assertEqual(messages, [])
        written = manifest.build(p)["starter"]
        self.assertIsInstance(written, dict)

    def test_several_decks_keep_their_order_and_weights(self):
        p, _ = read({"starter": [dict(full(), name="a", weight=3), dict(full(), name="b")]})
        self.assertEqual([(d.name, d.weight) for d in p.starter], [("a", 3), ("b", 1)])
        written = manifest.build(p)["starter"]
        self.assertIsInstance(written, list)
        self.assertEqual(written[0]["weight"], 3)
        self.assertNotIn("weight", written[1])      # 1 is the default, so it is not written

    def test_round_trip_is_identical(self):
        source = {"starter": [dict(full(**{"2": 3}), name="a", weight=2),
                              dict(full(**{"3": 1}), name="b")]}
        p, _ = read(source)
        again, _ = read({k: v for k, v in manifest.build(p).items() if k == "starter"})
        self.assertEqual([(d.name, d.weight, d.cards, d.kept) for d in p.starter],
                         [(d.name, d.weight, d.cards, d.kept) for d in again.starter])

    def test_a_card_it_cannot_place_is_kept_as_written(self):
        # A card a mod added, or a misspelling: either way the editor cannot
        # place it, and dropping it would throw away somebody else's deck.
        p, messages = read({"starter": full(**{"No Such Card": 4})})
        self.assertEqual(p.starter[0].kept, {"No Such Card": 4})
        self.assertTrue(any("kept as written" in m for m in messages))
        self.assertIn("No Such Card", manifest.build(p)["starter"])

    def test_a_short_deck_is_kept_so_it_can_be_finished(self):
        p, messages = read({"starter": {"2": 10}})
        self.assertEqual(len(p.starter), 1)
        self.assertFalse(p.starter[0].complete())
        self.assertTrue(any("40 cards" in m for m in messages))

    def test_copies_and_weights_out_of_range(self):
        p, messages = read({"starter": {"2": -1, "3": 40}})
        self.assertEqual(p.starter[0].cards, {3: 40})
        self.assertTrue(any("copies are a whole number" in m for m in messages))
        p, messages = read({"starter": dict(full(), weight=-1)})
        self.assertEqual(p.starter, [])         # the port leaves the whole deck out
        p, messages = read({"starter": dict(full(), weight="2")})
        self.assertEqual(p.starter, [])

    def test_zero_copies_are_no_card(self):
        p, _ = read({"starter": dict(full(), **{"2": 0})})
        self.assertNotIn(2, p.starter[0].cards)

    def test_starter_naming_a_file_stays_that_file(self):
        p, messages = read({"starter": "decks/starter.json"})
        self.assertEqual(p.starter_file, "decks/starter.json")
        self.assertEqual(manifest.build(p)["starter"], "decks/starter.json")
        self.assertTrue(any("kept as written" in m for m in messages))

    def test_a_deck_of_the_wrong_shape_is_left_out(self):
        p, messages = read({"starter": 40})
        self.assertEqual(p.starter, [])
        self.assertTrue(any("a deck, or a list of decks" in m for m in messages))
        p, messages = read({"starter": [40]})
        self.assertEqual(p.starter, [])

    def test_no_starter_key_writes_none(self):
        p, _ = read({})
        self.assertNotIn("starter", manifest.build(p))

    def test_it_is_no_longer_kept_as_an_unknown_key(self):
        p, _ = read({"starter": full()})
        self.assertNotIn("starter", p.other)


class ChecksTest(unittest.TestCase):
    def issues(self, source):
        p, _ = read(source)
        return [i for i in validate.validate(p) if i.area == "Starter decks"]

    def test_a_complete_deck_is_quiet(self):
        self.assertEqual(self.issues({"starter": full()}), [])

    def test_a_short_deck_is_an_error(self):
        found = self.issues({"starter": {"2": 10}})
        self.assertTrue(any(i.level == "error" and "40 cards" in i.message for i in found))

    def test_over_three_copies_warns_but_is_allowed(self):
        found = self.issues({"starter": full(**{"2": 4})})
        self.assertTrue(any(i.level == "warning" and "Build Deck" in i.message for i in found))
        self.assertFalse([i for i in found if i.level == "error"])

    def test_two_of_an_exodia_piece_warns(self):
        found = self.issues({"starter": full(**{str(EXODIA_FIRST_CARD_ID): 2})})
        self.assertTrue(any(i.level == "warning" and "Exodia" in i.message for i in found))

    def test_every_deck_weighing_nothing_warns(self):
        found = self.issues({"starter": [dict(full(), weight=0)]})
        self.assertTrue(any("never picked" in i.message or "none is ever picked" in i.message for i in found))


@unittest.skipIf(tk is None, "this Python has no Tk")
class TabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name) / "game"
        (folder / "DATA").mkdir(parents=True)
        f = fixture()
        (folder / "SLUS_014.11").write_bytes(f.slus)
        (folder / "DATA" / "WA_MRG.MRG").write_bytes(f.wa)
        cls.game = folder

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        from unittest import mock
        from fm_editor import settings
        from fm_editor.app import App
        # Never the user's own settings (a dark mode or interface size they
        # chose): a settings file of the test's own.
        own = Path(self.tmp.name) / "config" / "settings.json"
        own.unlink(missing_ok=True)
        patcher = mock.patch.object(settings, "path", lambda: own)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = App(ask=False, autostart=False)
        self.app.withdraw()
        self.app.update()
        self.app.start(str(self.game), None, False)
        self.app.update()

    def tearDown(self):
        self.app.dirty = False
        self.app.destroy()

    def test_a_deck_built_in_the_tab_is_saved(self):
        app, tab = self.app, self.app.starter
        app.project.starter.append(StarterDeck(name="Spellbinder", weight=2, cards={2: 3, 3: 37}))
        tab.refresh()
        self.assertEqual(len(tab.list.get_children()), 1)
        self.assertTrue(tab.tree.exists("2"))
        # the total line counts the forty
        self.assertIn(f"{DECK_SIZE} / {DECK_SIZE}", tab.total.cget("text"))
        with tempfile.TemporaryDirectory() as out:
            folder = Path(out) / "mod"
            manifest.save_mod(app.project, folder)
            written = json.loads((folder / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(written["starter"]["name"], "Spellbinder")
        self.assertEqual(written["starter"]["weight"], 2)

    def test_setting_copies_and_removing_a_card(self):
        app, tab = self.app, self.app.starter
        app.project.starter.append(StarterDeck(name="d", cards={2: 3, 3: 37}))
        tab.refresh()
        tab.tree.selection_set("2")
        tab.copies.set("5")
        tab.set_copies()
        self.assertEqual(app.project.starter[0].cards[2], 5)
        tab.tree.selection_set("3")
        tab.remove_card()
        self.assertNotIn(3, app.project.starter[0].cards)
        # setting a card to zero copies takes it out, as the pools do
        tab.tree.selection_set("2")
        tab.copies.set("0")
        tab.set_copies()
        self.assertEqual(app.project.starter[0].cards, {})

    def test_add_edit_and_remove_a_deck(self):
        from unittest import mock
        app, tab = self.app, self.app.starter
        # Cancelled, Add deck adds nothing.
        dialog = tab.add_deck()
        dialog.destroy()
        self.assertEqual(app.project.starter, [])
        self.assertFalse(app.dirty)
        # OKed, the deck is there, selected, with the name and weight typed.
        dialog = tab.add_deck()
        entries = [w for w in dialog.winfo_children()[0].winfo_children() if w.winfo_class() == "TEntry"]
        entries[0].delete(0, "end")
        entries[0].insert(0, "Dragons")
        entries[1].delete(0, "end")
        entries[1].insert(0, "3")
        dialog.ok()
        self.assertEqual([(d.name, d.weight) for d in app.project.starter], [("Dragons", 3)])
        self.assertEqual(tab.list.selection(), ("0",))
        self.assertTrue(app.dirty)
        # A weight out of range is refused, the deck as it was.
        dialog = tab.edit_deck()
        entries = [w for w in dialog.winfo_children()[0].winfo_children() if w.winfo_class() == "TEntry"]
        entries[1].delete(0, "end")
        entries[1].insert(0, "-1")
        dialog.ok()
        self.assertIn("weight", dialog.error.cget("text"))
        dialog.destroy()
        self.assertEqual(app.project.starter[0].weight, 3)
        with mock.patch("fm_editor.tabs.messagebox.askyesno", return_value=True):
            tab.remove_deck()
        self.assertEqual(app.project.starter, [])

    def test_ways_to_start_a_deck(self):
        """Add deck's menu (and the empty tab's buttons): an opponent's most
        likely 40, a deal of the disc's starter pools, a copy; each named in
        the dialog, which cancelled adds nothing."""
        from unittest import mock
        from fm_editor import fixed_decks, starter_pools
        app, tab = self.app, self.app.starter
        tab.refresh()
        self.assertTrue(tab.empty.winfo_manager())          # the empty tab says what a new game deals
        with mock.patch.object(tab, "ask_opponent", return_value=17):
            dialog = tab.add_deck("opponent")
        dialog.ok()
        deck = app.project.starter[0]
        self.assertEqual(deck.cards, fixed_decks.most_likely(app.project.pools[17]["deck"]))
        self.assertIn("deck", deck.name)
        self.assertFalse(tab.empty.winfo_manager())
        self.assertIn("Monsters", tab.makeup.cget("text"))
        dialog = tab.add_deck("copy")
        dialog.ok()
        self.assertEqual(app.project.starter[1].cards, deck.cards)
        self.assertIsNot(app.project.starter[1].cards, deck.cards)
        pools = starter_pools.retail(app.files.wa)
        if pools:
            dialog = tab.add_deck("retail")
            dialog.destroy()                                # cancelled: no deck
            self.assertEqual(len(app.project.starter), 2)
            dealt = starter_pools.deal(pools)
            self.assertEqual(sum(dealt.values()), starter_pools.retail_drawn(pools))
        with mock.patch.object(tab, "ask_opponent", return_value=None):
            self.assertIsNone(tab.add_deck("opponent"))

    def test_weighted_pools_page(self):
        """starter_pools on their own page: pools added, named and given their
        draws, cards weighted, the draws counted against forty, written as
        the game reads them; the disc's seven as a start."""
        from unittest import mock
        from fm_editor import starter_pools as sp
        app, tab = self.app, self.app.starter
        page = tab.pools
        tab.pages.select(page)
        app.update()
        self.assertTrue(page.empty.winfo_manager())
        dialog = page.add_pool()
        dialog.fields["name"].set("Weak")
        dialog.fields["draws"].set("30")
        dialog.ok()
        with mock.patch("fm_editor.starter_pools_view.pick_card", return_value=2):
            page.weight.set("100")
            page.add_card()
        with mock.patch("fm_editor.starter_pools_view.pick_card", return_value=3):
            page.add_card()
        self.assertEqual(page.total.cget("text"), "Draws 30 / 40")
        self.assertEqual(str(page.total.cget("style")), "Error.TLabel")
        dialog = page.add_pool()                    # the draws left, offered
        self.assertEqual(dialog.fields["draws"].get(), "10")
        dialog.ok()
        with mock.patch("fm_editor.starter_pools_view.pick_card", return_value=4):
            page.add_card()
        self.assertEqual(page.total.cget("text"), "Draws 40 / 40")
        self.assertTrue(sp.deals(app.project))
        # Weights set and cards removed on the selection.
        page.list.selection_set("0")
        page.select()
        page.tree.selection_set("3")
        page.weight.set("7")
        page.set_weight()
        self.assertEqual(sp.state(app.project)[0].cards, {2: 100, 3: 7})
        page.tree.selection_set("3")
        page.remove_cards()
        written = app.project.other["starter_pools"]
        self.assertEqual(written[0], {"name": "Weak", "draws": 30, "cards": {app.project.ref(2): 100}})
        self.assertEqual(written[1]["draws"], 10)
        self.assertTrue(app.dirty)
        # The disc's seven pools, in place of these (asked first).
        if sp.retail(app.files.wa):
            with mock.patch("fm_editor.starter_pools_view.messagebox.askyesno", return_value=True):
                page.from_retail()
            self.assertEqual(len(app.project.other["starter_pools"]), 7)
            self.assertEqual(sum(p["draws"] for p in app.project.other["starter_pools"]),
                             sp.retail_drawn(sp.retail(app.files.wa)))
        with mock.patch("fm_editor.starter_pools_view.messagebox.askyesno", return_value=True):
            while sp.state(app.project):
                page.remove_pool()
        self.assertNotIn("starter_pools", app.project.other)

    def test_a_deck_naming_an_unknown_card_is_not_complete(self):
        tab = self.app.starter
        self.app.project.starter.append(StarterDeck(name="d", cards={2: 3, 3: 36}, kept={"Nobody's card": 1}))
        tab.refresh()
        self.assertFalse(self.app.project.starter[0].complete())
        self.assertIn("error", tab.list.item("0", "tags"))

    def test_an_empty_tab_shows_no_deck(self):
        tab = self.app.starter
        tab.refresh()
        self.assertIsNone(tab.current())
        self.assertEqual(tab.title.cget("text"), "No starter deck")


if __name__ == "__main__":
    unittest.main()
