"""A mod's "guardian_stars" (guardian_stars.py, notes/modding.md): the table
the editor works out against the one the game does, the model's round trip,
the checks stars.c makes, the Cards tab's star lists, the rules for setting
many cards' stars, and the tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc

tests/pc/guardian_stars/*.expected is the game's table for each manifest
beside it, pair by pair: tests/pc/stars_test.c checks Duel_CalcGuardianStarMatchup
against the same files, so the editor and the game agree on every pair.
"""
import copy
import json
import unittest
from unittest import mock
from pathlib import Path

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import guardian_stars as gs, manifest, star_rules, validate
from fm_editor.bulk_fusions import CardFilter
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

GOLDEN = Path(__file__).resolve().parents[4] / "tests" / "pc" / "guardian_stars"


def project() -> Project:
    return Project(fixture().game())


def expected(name: str) -> list:
    rows = (GOLDEN / name).read_text().split("\n")
    return [[int(v) for v in row.split()] for row in rows if row.strip()]


class TableTest(unittest.TestCase):
    def test_same_as_the_game(self):
        """Every pair of every manifest, as the game's matchup gives it."""
        manifests = sorted(GOLDEN.glob("*.json"))
        self.assertGreaterEqual(len(manifests), 4)
        for path in manifests:
            section = json.loads(path.read_text()).get("guardian_stars")
            messages = []
            self.assertEqual(gs.table(section, messages), expected(path.stem + ".expected"), path.name)
            self.assertEqual(messages, [], path.name)

    def test_retail(self):
        self.assertEqual(gs.retail_matchup(1, 2), 500)
        self.assertEqual(gs.retail_matchup(2, 1), -500)
        self.assertEqual(gs.retail_matchup(6, 1), 500)
        self.assertEqual(gs.retail_matchup(10, 7), 500)
        self.assertEqual(gs.retail_matchup(1, 7), 0)
        self.assertEqual(gs.retail_matchup(0, 1), 500)     # the disc's arithmetic outside 1-10
        self.assertEqual(gs.retail_matchup(11, 7), 500)
        self.assertEqual(gs.table(None), gs.table({}))

    def test_round_trip(self):
        """The model writes the same table back, as the fewest matchups."""
        for path in sorted(GOLDEN.glob("*.json")):
            section = json.loads(path.read_text()).get("guardian_stars")
            model = gs.read(section)
            built = model.build()
            self.assertEqual(gs.table(built), gs.table(section), path.name)
            if built:
                again = gs.read(built).build()
                self.assertEqual(again, built, path.name)
        self.assertIsNone(gs.read({}).build())
        # One override is all a minimal mod holds.
        model = gs.read(None)
        model.grid[1][2] = 1000
        self.assertEqual(model.build(), {"matchups": [{"attacker": 1, "defender": 2, "bonus": 1000}]})

    def test_default_and_presets(self):
        model = gs.read({"matchups": [{"attacker": 1, "defender": 3, "bonus": 200}]})
        model.set_default(800)
        self.assertEqual(model.grid[1][2], 800)
        self.assertEqual(model.grid[2][1], -800)
        self.assertEqual(model.grid[1][3], 200)             # the mod's own pair stays
        self.assertEqual(model.build(), {"default_bonus": 800,
                                         "matchups": [{"attacker": 1, "defender": 3, "bonus": 200}]})
        model.preset_clear()
        self.assertTrue(all(v == 0 for row in model.grid for v in row))
        self.assertEqual(model.build(), {"replace": True, "default_bonus": 800})
        model.preset_retail()
        self.assertEqual(model.build(), {"default_bonus": 800})
        star = model.add_star()
        self.assertEqual(star, 11)
        self.assertEqual(model.grid[11][7], 0)              # declared: neutral, not the quirk
        model.stars[11].name = "Fire"
        self.assertEqual(model.build(), {"stars": [{"id": 11, "name": "Fire"}], "default_bonus": 800})
        model.remove_star(11)
        self.assertEqual(model.grid[11][7], gs.retail_matchup(11, 7))
        for _ in range(5):
            model.add_star()
        self.assertEqual(model.add_star(), 0)                # fifteen at most
        self.assertEqual(model.count, 15)

    def test_find_and_names(self):
        section = {"stars": [{"id": 11, "name": {"en-us": "Grass", "fr": "Plante"}}, {"id": 1, "name": "Ares"}]}
        self.assertEqual(gs.find("plante", section), 11)
        self.assertEqual(gs.find("Ares", section), 1)
        self.assertEqual(gs.find("Mars", section), 1)
        self.assertEqual(gs.find("12", section), 12)
        self.assertEqual(gs.find("nothing", section), -1)
        self.assertEqual(gs.count(section), 11)
        self.assertEqual(gs.display_name({"fr": "Plante", "en-us": "Grass"}, 11), "Grass")
        self.assertEqual(gs.display_name(None, 12), "Star 12")

    def test_checks(self):
        bad = {"stars": [{"id": 16}, {"id": 0}, {"name": "x"}],
               "matchups": [{"attacker": 1, "defender": 2, "bonus": 40000}, {"attacker": "Nowhere", "defender": 2},
                            {"attacker": 1, "defender": 2, "bonus": "a"}],
               "default_bonus": 99999, "color": 1, "choice": "sometimes"}
        errors = [m for level, where, m in gs.check(bad) if level == "error"]
        self.assertEqual(len(errors), 9, errors)            # stars.c's eight notes, and "choice"
        self.assertTrue(any("4 bits" in m for m in errors))
        warnings = gs.check({"stars": [{"id": 11}, {"id": 12, "beats": [11]}],
                             "matchups": [{"attacker": 1, "defender": 2, "bonus": 12000}]},
                            card_stars={11: 3, 14: 2})
        text = "\n".join(m for _, _, m in warnings)
        self.assertIn("no card has star 12", text)
        self.assertIn("which the mod does not declare", text)
        self.assertIn("past the ATK/DEF cap", text)
        self.assertEqual(gs.check(None), [])


class ManifestTest(unittest.TestCase):
    def test_cards_name_new_stars(self):
        p = project()
        messages = manifest.apply(p, {"guardian_stars": {"stars": [{"id": 11, "name": "Fire"}]},
                                      "cards": [{"replace": 1, "stars": ["Fire", "Sun"]},
                                                {"replace": 2, "stars": [14, 0]},
                                                {"replace": 3, "stars": [0, "Moon"]}]})
        self.assertEqual((p.cards[1].star1, p.cards[1].star2), (11, 8))
        self.assertEqual((p.cards[2].star1, p.cards[2].star2), (14, 0))
        # [none, Moon] is kept as written; the game reads it as [Moon, none].
        self.assertEqual((p.cards[3].star1, p.cards[3].star2), (0, 9))
        self.assertFalse([m for m in messages if "stars" in m], messages)
        built = manifest.build(p)
        self.assertEqual(built["guardian_stars"], {"stars": [{"id": 11, "name": "Fire"}]})
        again = project()
        manifest.apply(again, json.loads(json.dumps(built)))
        self.assertEqual((again.cards[1].star1, again.cards[1].star2), (11, 8))
        issues = validate.validate(again)
        stars = [i for i in issues if i.area == "Guardian Stars"]
        self.assertTrue(any("does not declare" in i.message for i in stars), [i.message for i in stars])
        cards = [i.message for i in issues if i.area == "Cards"]
        self.assertTrue(any("past the 11" in m for m in cards), cards)
        self.assertFalse([i for i in issues if i.area == "Mod info" and i.where == "guardian_stars"])

    def test_cap_is_the_limits(self):
        """A bonus past 9999 is warned about, unless "limits" raises the cap."""
        p = project()
        p.other["guardian_stars"] = {"matchups": [{"attacker": 1, "defender": 2, "bonus": 12000}]}
        past = lambda: [i for i in validate.validate(p) if i.area == "Guardian Stars" and "cap" in i.message]
        self.assertTrue(past())
        p.other["limits"] = {"stats": 30000}
        self.assertFalse(past())

    def test_star_choices(self):
        """The Cards tab's star lists (tabs.star_choices is this, by project)."""
        self.assertEqual(len(gs.choices(None)), 11)
        choices = gs.choices({"stars": [{"id": 12, "name": "Water"}, {"id": 1, "name": "Ares"}]})
        self.assertEqual(len(choices), 13)
        self.assertEqual(choices[1], "Ares (Mars)")
        self.assertEqual(choices[11], "11 Star 11")
        self.assertEqual(choices[12], "12 Water")


class NoStarTest(unittest.TestCase):
    """A monster with no guardian star (notes/modding.md, "No star"): what
    the editor writes for (none) is what the game reads (stars.c
    Stars_Value and Stars_Normalize), and it comes back the same."""

    def test_card_star(self):
        for value, want in ((0, 0), (None, 0), ("none", 0), ("(none)", 0), ("(None)", 0), ("Mars", 1),
                            ("0", 0), (3, 3), (20, 20), (-2, -1), ("Nothing", -1), ("", -1), (True, -1), ([1], -1)):
            self.assertEqual(gs.card_star(value), want, value)
        # A star the mod names "None" is that star, as in the game.
        self.assertEqual(gs.card_star("(none)", {"stars": [{"id": 11, "name": "None"}]}), 11)
        self.assertEqual(gs.normalized(0, 8), (8, 0))
        self.assertEqual(gs.normalized(0, 0), (0, 0))
        self.assertEqual(gs.normalized(5, 6), (5, 6))

    def test_no_star_round_trip(self):
        p = project()
        monster = next(cid for cid in sorted(p.cards) if p.cards[cid].is_monster())
        p.cards[monster] = p.cards[monster].copy(star1=0, star2=0)
        built = manifest.build(p)
        entry = next(e for e in built["cards"] if e.get("replace") == monster)
        self.assertEqual(entry["stars"], [0, 0])
        again = project()
        messages = manifest.apply(again, json.loads(json.dumps(built)))
        self.assertEqual((again.cards[monster].star1, again.cards[monster].star2), (0, 0))
        self.assertFalse([m for m in messages if "stars" in m], messages)
        self.assertEqual(manifest.build(again)["cards"], built["cards"])
        # No warning: the game takes a monster with no star.
        cards = [i.message for i in validate.validate(again) if i.area == "Cards" and i.target == monster]
        self.assertFalse([m for m in cards if "star" in m], cards)

    def test_hand_written_none(self):
        p = project()
        messages = manifest.apply(p, {"cards": [{"replace": 1, "stars": [None, "(none)"]},
                                                {"replace": 2, "stars": ["none", "Sun"]},
                                                {"replace": 3, "stars": ["Mars"]},
                                                {"replace": 4, "stars": "Mars"}]})
        self.assertEqual((p.cards[1].star1, p.cards[1].star2), (0, 0))
        self.assertEqual((p.cards[2].star1, p.cards[2].star2), (0, 8))
        self.assertEqual(sum("a list of two" in m for m in messages), 2, messages)
        cards = [i.message for i in validate.validate(p) if i.area == "Cards" and i.target == 2]
        self.assertTrue(any("the one star Sun" in m for m in cards), cards)


class ReviewTest(unittest.TestCase):
    def test_names_without_ascii_letters(self):
        """As stars.c: bytes past ASCII tell names apart."""
        section = {"stars": [{"id": 11, "name": "\u706b", "beats": ["\u6c34"]}, {"id": 12, "name": "\u6c34"}]}
        self.assertEqual(gs.find("\u6c34", section), 12)
        grid = gs.table(section)
        self.assertEqual((grid[11][12], grid[12][11], grid[11][11]), (500, -500, 0))

    def test_malformed_sections(self):
        self.assertEqual(gs.star_number("--5"), -1)
        self.assertEqual(gs.star_number("\u00b2"), -1)
        self.assertEqual(gs.find("--5"), -1)
        for section in ({"stars": 5}, [1], {"stars": [{"id": "\u00b2"}]}):
            self.assertEqual(len(gs.choices(section)), 11)
            gs.read(section)
            gs.table(section)

    def test_remove_star_under_replace(self):
        model = gs.read({"replace": True, "stars": [{"id": 11, "name": "Fire"}]})
        model.remove_star(11)
        built = model.build() or {}
        self.assertFalse(built.get("matchups"))

    def test_palette_any_case(self):
        self.assertEqual(gs.read({"stars": [{"id": 11, "palette": "Own"}]}).stars[11].palette, "own")


class RulesTest(unittest.TestCase):
    def test_plan_apply_undo(self):
        p = project()
        monsters = [cid for cid in sorted(p.cards) if p.cards[cid].is_monster()][:30]
        spec = star_rules.RuleSpec(filter=CardFilter(cards=", ".join(map(str, monsters))), which="first",
                                   source="attribute", mapping={a: 11 + a % 3 for a in range(6)})
        the_plan = star_rules.plan(p, spec)
        self.assertTrue(the_plan.ok(), the_plan.errors)
        self.assertEqual(the_plan.chosen, 30)
        for cid, before, after in the_plan.changes:
            self.assertEqual(after[0], 11 + p.cards[cid].attribute % 3)
            self.assertEqual(after[1], before[1])
        batch = star_rules.apply(p, the_plan, "test")
        self.assertTrue(all(p.cards[cid].star1 >= 11 for cid, _, _ in the_plan.changes))
        edited = the_plan.changes[0][0]
        p.cards[edited] = p.cards[edited].copy(star1=1)
        restored, skipped = star_rules.undo(p, batch)
        self.assertEqual((restored, skipped), (len(the_plan.changes) - 1, 1))
        # The second star as none: single-typed cards.
        spec = star_rules.RuleSpec(filter=CardFilter(cards=str(monsters[0])), which="second", source="star",
                                   mapping={None: 0})
        self.assertEqual(star_rules.plan(p, spec).changes[0][2][1], 0)
        # A first star of none leaves the second as the one star, as the game
        # reads it; both none, no star. An empty filter is refused.
        card = p.cards[monsters[0]]
        spec.which = "first"
        self.assertEqual(star_rules.plan(p, spec).changes[0][2], (card.star2, 0))
        spec.which = "both"
        self.assertEqual(star_rules.plan(p, spec).changes[0][2], (0, 0))
        self.assertTrue(star_rules.plan(p, star_rules.RuleSpec(mapping={None: 3}, source="star")).errors)


class GuardianStarsTabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
        try:
            cls.root = tk.Tk()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_tab(self):
        import tempfile
        from tkinter import ttk
        from fm_editor.guardian_stars_tab import GuardianStarsTab
        from fm_editor.tests.test_art import gradient
        from fm_editor import pngio

        class App:
            def __init__(self):
                self.project = project()
                self.changes = 0

            def changed(self):
                self.changes += 1

        app = App()
        app.project.other["guardian_stars"] = {"default_bonus": 700}
        notebook = ttk.Notebook(self.root)
        tab = GuardianStarsTab(notebook, app)
        tab.refresh()
        self.assertEqual(tab.default.get(), "700")
        # A star is picked from the start, its button saying what it does.
        self.assertEqual(tab.selected_star, 1)
        self.assertEqual(tab.remove_button.cget("text"), "Reset")
        self.assertEqual(len(tab.tree.get_children()), 10)
        tab.pick_cell(1, 2)
        self.assertEqual(tab.value.get(), "700")
        tab.value.set("1000")
        tab.set_cell()                          # and the reverse pair gets -1000
        self.assertEqual(app.project.other["guardian_stars"]["matchups"],
                         [{"attacker": 1, "defender": 2, "bonus": 1000},
                          {"attacker": 2, "defender": 1, "bonus": -1000}])
        tab.add_star()
        self.assertEqual(len(tab.tree.get_children()), 11)
        tab.tree.selection_set("11")
        tab._pick_star()
        self.assertEqual(tab.remove_button.cget("text"), "Remove")
        tab.name.set("Fire")
        tab.set_name()
        with tempfile.TemporaryDirectory() as folder:
            icon = Path(folder) / "fire.png"
            icon.write_bytes(pngio.encode(gradient(32, 32)))
            tab.use_icon(11, icon)
        section = app.project.other["guardian_stars"]
        self.assertEqual(section["stars"], [{"id": 11, "name": "Fire", "icon": "icons/star-11.png"}])
        self.assertIn("icons/star-11.png", app.project.files)
        tab.choice.set("best")
        tab.set_choice()
        self.assertEqual(app.project.other["guardian_stars"]["choice"], "best")
        tab.draw()                              # the grid, 11 by 11
        self.assertGreater(len(tab.canvas.find_all()), 11 * 11)
        # Dark mode: the grid redraws itself in the dark colors when the
        # theme changes, and back.
        from fm_editor import theme
        from fm_editor.guardian_stars_tab import COLORS
        looks = theme.Theme(self.root)
        looks.make_dark()
        light = looks.style.theme_use()
        fills = lambda: {tab.canvas.itemcget(item, "fill") for item in tab.canvas.find_all()
                         if tab.canvas.type(item) == "rectangle"}
        looks.style.theme_use(theme.DARK_THEME)
        self.root.update()
        self.assertIn(COLORS["plus"][1], fills())
        self.assertNotIn(COLORS["plus"][0], fills())
        looks.style.theme_use(light)
        self.root.update()
        self.assertIn(COLORS["plus"][0], fills())
        tab.remove_icon()
        self.assertNotIn("icons/star-11.png", app.project.files)
        # A cell of the star removed is no cell any more: the bonus buttons
        # write no matchup for a star that is gone.
        tab.pick_cell(11, 1)
        with mock.patch("fm_editor.guardian_stars_tab.messagebox.askokcancel", return_value=True):
            tab.remove_star()
        self.assertIsNone(tab.cell)
        tab.set_cell(500)
        self.assertFalse([m for m in app.project.other["guardian_stars"].get("matchups", [])
                          if 11 in (m["attacker"], m["defender"])])
        tab.preset_clear()
        self.assertTrue(app.project.other["guardian_stars"]["replace"])
        self.assertGreater(app.changes, 0)
        json.dumps(manifest.build(app.project))
        app.project.other.pop("guardian_stars")
        tab.refresh()
        self.assertEqual(len(tab.tree.get_children()), 10)

    def test_tab_keeps_what_it_did_not_change(self):
        """A tab switch commits every tab: a section as the mod wrote it
        (beats, mirror, stars by name) stays as it was, and the mod is not
        marked changed, until the tab changes something."""
        from tkinter import ttk
        from fm_editor.guardian_stars_tab import GuardianStarsTab

        class App:
            def __init__(self):
                self.project = project()
                self.changes = 0

            def changed(self):
                self.changes += 1

        for path in sorted(GOLDEN.glob("*.json")):
            section = json.loads(path.read_text()).get("guardian_stars")
            app = App()
            app.project.other["guardian_stars"] = copy.deepcopy(section)
            tab = GuardianStarsTab(ttk.Notebook(self.root), app)
            tab.refresh()
            tab.commit()
            self.assertEqual(app.project.other.get("guardian_stars"), section, path.name)
            self.assertEqual(app.changes, 0, path.name)
        tab.pick_cell(1, 2)
        tab.value.set("1234")
        tab.set_cell()
        self.assertGreater(app.changes, 0)
        self.assertIn({"attacker": 1, "defender": 2, "bonus": 1234}, app.project.other["guardian_stars"]["matchups"])


if __name__ == "__main__":
    unittest.main()
