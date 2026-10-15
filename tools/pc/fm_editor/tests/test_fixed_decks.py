"""Fixed opponent decks ("decks" with "fixed": true, tables.c read_fixed_deck):
the manifest round trip, the checks, the export and the Duelists tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import fixed_decks, manifest, validate
from fm_editor.gamedata import DECK_COPY_LIMIT, DECK_SIZE
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture


def project() -> Project:
    return Project(fixture().game())


def read(source: dict):
    p = project()
    messages = manifest.apply(p, {"id": "m", "name": "M", **source})
    return p, messages


def deck_issues(p):
    return [i for i in validate.validate(p) if i.area == "Duelists" and "fixed deck" in i.where]


def port_reads(p, entry: dict) -> dict:
    """What read_fixed_deck deals from an entry: card id -> copies, or None
    when it leaves the deck out."""
    if not isinstance(entry.get("fixed"), (bool, int)) or not entry["fixed"]:
        return None
    cards, total = {}, 0
    for name, copies in entry.items():
        if name in ("fixed", "replace"):
            continue
        if isinstance(copies, bool) or not isinstance(copies, int) or not 0 <= copies <= DECK_SIZE:
            continue
        cid = p.resolve(name)
        if not cid:
            continue
        total += copies
        if copies:
            cards[cid] = cards.get(cid, 0) + copies
    return cards if total == DECK_SIZE else None


# An entry as somebody wrote it by hand: names in any case, a number, a card
# named twice, "fixed" as 1 and a value that is not a card's copies.
UGLY = {"fixed": 1, "kuriboh": 4, "3": 1, "Mystic Elf": 5, "BLUE DRAGON": 10, "Card 100": 20, "note": "x"}


class ManifestTest(unittest.TestCase):
    def test_a_fixed_deck_is_read_for_its_duelist(self):
        p, messages = read({"decks": {"Simon Muran": {"fixed": True, "Kuriboh": 3, "Card 100": 37}}})
        deck = fixed_decks.deck_of(p, 1)
        self.assertIsNotNone(deck)
        self.assertEqual(deck.cards, {3: 3, 100: 37})
        self.assertEqual(deck.total(), DECK_SIZE)
        self.assertEqual(messages, [])
        self.assertEqual(deck_issues(p), [])

    def test_untouched_decks_are_written_as_they_were(self):
        source = {"decks": {"all": {"fixed": True, "Kuriboh": 40},
                            "Simon Muran": dict(UGLY),
                            "Teana": {"Kuriboh": 50},
                            "Nobody Added": {"fixed": True, "Kuriboh": 40},
                            "2": {"fixed": True, "Card 100": 40}}}
        p, messages = read(source)
        self.assertTrue(any("\"note\"" in m and "left out" in m for m in messages))
        self.assertTrue(any("every duelist" in m for m in messages))
        self.assertTrue(any("does not have" in m for m in messages))
        self.assertEqual(fixed_decks.deck_of(p, 1).cards, {3: 5, 2: 5, 1: 10, 100: 20})
        decks = manifest.build(p)["decks"]
        for key in ("all", "Simon Muran", "Nobody Added", "2"):
            self.assertEqual(decks[key], source["decks"][key], key)
        # Byte for byte, and the same again after a second trip.
        text = manifest.dumps(manifest.build(p))
        again, _ = read(json.loads(text))
        again.info.name = p.info.name
        self.assertEqual(manifest.dumps(manifest.build(again)), text)

    def test_the_order_the_editor_always_wrote(self):
        """The fixed decks go over the weighted edits, as kept decks did: one
        under a weighted edit's key takes its place, a new key goes after,
        and "all" goes first."""
        p, _ = read({"decks": {"Teana": {"Kuriboh": 50}, "Jono": {"fixed": True, "Kuriboh": 40},
                               "all": {"fixed": True, "Card 100": 40}}})
        p.pools[1]["deck"] = {**p.pools[1]["deck"], 3: 77}       # a weighted edit of Simon Muran
        fixed_decks.set_deck(p, 1, {3: 40})                             # and a fixed deck over it
        decks = manifest.build(p)["decks"]
        self.assertEqual(list(decks), ["all", "Simon Muran", "Teana", "Jono"])
        self.assertEqual(decks["Simon Muran"], {"fixed": True, "Kuriboh": 40})

    def test_an_edited_deck_is_written_in_card_order(self):
        p, _ = read({"decks": {"Simon Muran": dict(UGLY)}})
        deck = fixed_decks.deck_of(p, 1)
        deck.cards[100] -= 1
        deck.cards[5] = 1
        entry = manifest.build(p)["decks"]["Simon Muran"]
        self.assertEqual(entry, {"fixed": 1, "note": "x", "Blue Dragon": 10, "Mystic Elf": 5, "Kuriboh": 5,
                                 "Card 5": 1, "Card 100": 19})
        self.assertEqual(port_reads(p, entry), deck.cards)

    def test_a_new_deck_is_what_the_port_reads(self):
        p = project()
        p.info.id = "m"
        copy = p.add_card(1, "c1")
        fixed_decks.set_deck(p, 1, {3: 4, copy: 6, 100: 30})
        entry = manifest.build(p)["decks"]["Simon Muran"]
        self.assertEqual(entry, {"fixed": True, "Kuriboh": 4, "Card 100": 30, "m:c1:1": 6})
        self.assertEqual(port_reads(p, entry), {3: 4, 100: 30, copy: 6})
        self.assertEqual(deck_issues(p), [])

    def test_a_deck_naming_an_added_card_follows_the_mod_id(self):
        p = project()
        p.info.id = "m"
        copy = p.add_card(1, "c1")
        fixed_decks.set_deck(p, 1, {copy: 40})
        again, _ = read(json.loads(manifest.dumps(manifest.build(p))))
        self.assertEqual(manifest.build(again)["decks"]["Simon Muran"], {"fixed": True, "m:c1:1": 40})
        again.info.id = "renamed"
        self.assertEqual(manifest.build(again)["decks"]["Simon Muran"], {"fixed": True, "renamed:c1:1": 40})

    def test_weighted_again_and_back(self):
        p, _ = read({"decks": {"Simon Muran": {"fixed": True, "Kuriboh": 40}}})
        taken = fixed_decks.remove(p, 1)
        self.assertIsNone(fixed_decks.deck_of(p, 1))
        self.assertNotIn("decks", manifest.build(p))
        fixed_decks.restore(p, taken)
        self.assertEqual(manifest.build(p)["decks"], {"Simon Muran": {"fixed": True, "Kuriboh": 40}})

    def test_the_later_of_two_keys_is_the_deck(self):
        p, _ = read({"decks": {"1": {"fixed": True, "Kuriboh": 40}, "Simon Muran": {"fixed": True, "Card 100": 40}}})
        self.assertEqual(fixed_decks.deck_of(p, 1).cards, {100: 40})
        self.assertTrue(any("written 2 times" in i.message for i in deck_issues(p)))

    def test_drops_and_the_rest_are_unaffected(self):
        source = {"decks": {"Simon Muran": {"fixed": True, "Kuriboh": 40}},
                  "drops": {"Simon Muran": {"pow": {"Kuriboh": 30}}}}
        p, _ = read(source)
        plain, _ = read({"drops": source["drops"]})
        built, reference = manifest.build(p), manifest.build(plain)
        self.assertEqual(built["drops"], reference["drops"])
        self.assertEqual(p.pools, plain.pools)
        self.assertEqual({k: v for k, v in built.items() if k != "decks"}, reference)


class CheckTest(unittest.TestCase):
    def test_not_forty(self):
        p = project()
        fixed_decks.set_deck(p, 1, {3: 39})
        self.assertTrue(any(i.level == "error" and "has 39" in i.message for i in deck_issues(p)))

    def test_an_unknown_card_leaves_the_deck_out(self):
        p, messages = read({"decks": {"Simon Muran": {"fixed": True, "Kuriboh": 39, "Nothing Such": 1}}})
        self.assertTrue(any("no such card" in m for m in messages))
        issues = deck_issues(p)
        self.assertTrue(any(i.level == "error" and "Nothing Such" in i.message for i in issues))
        self.assertIsNone(port_reads(p, manifest.build(p)["decks"]["Simon Muran"]))
        self.assertEqual(issues[0].target, (1, "deck"))

    def test_a_removed_card(self):
        p = project()
        copy = p.add_card(1, "c1")
        fixed_decks.set_deck(p, 1, {copy: 1, 3: 39})
        p.remove_card(copy)
        self.assertTrue(any(f"no card {copy}" in i.message for i in deck_issues(p)))

    def test_many_copies_are_fine(self):
        p = project()
        fixed_decks.set_deck(p, 1, {3: 40})
        self.assertEqual(deck_issues(p), [])

    def test_weighted_edits_under_a_fixed_deck(self):
        p = project()
        fixed_decks.set_deck(p, 1, {3: 40})
        p.pools[1]["deck"] = {**p.pools[1]["deck"], 3: 77}
        self.assertTrue(any(i.level == "warning" and "not dealt" in i.message for i in deck_issues(p)))


class MostLikelyTest(unittest.TestCase):
    def test_retail_pools(self):
        p = project()
        for d in range(len(p.pools)):
            pool = p.pools[d]["deck"]
            deck = fixed_decks.most_likely(pool)
            self.assertEqual(sum(deck.values()), DECK_SIZE, d)
            self.assertTrue(all(0 < n <= DECK_COPY_LIMIT for n in deck.values()), d)
            self.assertTrue(set(deck) <= {c for c, w in pool.items() if w}, d)
            self.assertEqual(deck, fixed_decks.most_likely(dict(reversed(list(pool.items())))), d)

    def test_heavier_cards_first(self):
        pool = {c: 2 for c in range(1, 101)}
        pool.update({50: 1000, 60: 900, 70: 50})
        deck = fixed_decks.most_likely(pool)
        self.assertEqual(sum(deck.values()), DECK_SIZE)
        self.assertEqual((deck[50], deck[60]), (3, 3))
        self.assertIn(70, deck)
        self.assertEqual(sorted(c for c in deck if c not in (50, 60, 70))[:3], [1, 2, 3])   # ties: lower id

    def test_too_few_cards_lift_the_limit(self):
        deck = fixed_decks.most_likely({1: 1, 2: 1})
        self.assertEqual(deck, {1: 20, 2: 20})
        self.assertEqual(fixed_decks.most_likely({}), {})


class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
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

    def test_fixed_deck_in_the_duelists_tab(self):
        from fm_editor import fixed_deck_view
        app, tab = self.app, self.app.duelists
        app.notebook.select(tab)
        tab.goto((1, "deck"))
        app.update()
        view = tab.fixed
        self.assertEqual(view.mode.get(), "weighted")
        self.assertEqual(tab.tree.master.winfo_manager(), "pack")
        view.mode.set("fixed")
        view.switch()
        app.update()
        self.assertEqual(view.panel.winfo_manager(), "pack")
        self.assertEqual(tab.tree.master.winfo_manager(), "")
        deck = fixed_decks.deck_of(app.project, 1)
        self.assertEqual(deck.cards, fixed_decks.most_likely(app.project.pools[1]["deck"]))
        self.assertIn("40 / 40", tab.total.cget("text"))
        self.assertEqual(tab.list.set("1", "state"), "fixed deck")
        # Clear, add a card with its copies, then another.
        view.clear()
        self.assertIn("0 / 40", tab.total.cget("text"))
        self.assertEqual(str(tab.total.cget("style")), "Error.TLabel")
        self.assertEqual(ttk.Style(app).configure("Error.TLabel")["foreground"], "#c01c28")
        view.copies.set("37")
        deck.cards[3] = 37
        view.edited()
        view.tree.selection_set("3")
        view.copies.set("40")
        view.set_copies()
        self.assertEqual(deck.cards, {3: 40})
        self.assertEqual(str(tab.total.cget("style")), "Ok.TLabel")
        self.assertEqual(deck_issues(app.project), [])
        # The weighted deck again keeps the fixed one aside, and back.
        view.mode.set("weighted")
        view.switch()
        app.update()
        self.assertIsNone(fixed_decks.deck_of(app.project, 1))
        self.assertEqual(tab.tree.master.winfo_manager(), "pack")
        view.mode.set("fixed")
        view.switch()
        self.assertEqual(fixed_decks.deck_of(app.project, 1).cards, {3: 40})
        # A drop pool has no such choice.
        tab.pool.set("pow")
        tab.fill()
        app.update()
        self.assertEqual(view.bar.winfo_manager(), "")
        self.assertEqual(tab.tree.master.winfo_manager(), "pack")
        tab.pool.set("deck")
        tab.fill()
        # Saved, and read back.
        app.project.info.id = "fixed-gui"
        out = Path(self.tmp.name) / "saved-fixed"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(data["decks"], {"Simon Muran": {"fixed": True, "Kuriboh": 40}})
        app.load_mod(out)
        self.assertEqual(fixed_decks.deck_of(app.project, 1).cards, {3: 40})
        # Revert to retail: no fixed deck, the weighted deck the disc's.
        tab.goto((1, "deck"))
        asked = fixed_deck_view.messagebox.askyesno
        fixed_deck_view.messagebox.askyesno = lambda *a, **k: True
        try:
            view.revert()
        finally:
            fixed_deck_view.messagebox.askyesno = asked
        self.assertIsNone(fixed_decks.deck_of(app.project, 1))
        self.assertEqual(view.mode.get(), "weighted")
        self.assertNotIn("decks", manifest.build(app.project))


if __name__ == "__main__":
    unittest.main()
