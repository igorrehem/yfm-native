"""Ritual recipes: condition-based tributes, one to five of them, from the
field, the hand or both; reading, writing, checking, and the Rituals tab."""
import json
import unittest

from unittest import mock

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import gamedata as g, manifest, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture
from fm_editor.tests import test_gui


def reopen(retail, p: Project) -> Project:
    again = Project(retail)
    manifest.apply(again, json.loads(manifest.dumps(manifest.build(p))))
    return again


class RequirementsTest(unittest.TestCase):
    def setUp(self):
        self.retail = fixture().game()

    def load(self, rituals) -> tuple:
        p = Project(self.retail)
        messages = manifest.apply(p, {"id": "t", "rituals": rituals})
        return p, messages

    def test_round_trip(self):
        p, messages = self.load([{"card": 681, "result": 500, "tributes": [
            {"type": "Dragon", "min_attack": 0}, 5, {"fusion_group": "female", "defense_gt_attack": True}]}])
        self.assertEqual(messages, [])
        # A minimum of 0 is a requirement (any monster); a group in any case is the group.
        self.assertEqual(p.ritual_requirements[681], [
            {"type": "Dragon", "min_attack": 0}, {"card": 5}, {"fusion_group": "Female", "defense_gt_attack": True}])
        self.assertEqual(p.ritual_status(681), "changed")
        built = manifest.build(p)["rituals"]
        self.assertEqual(built, [{"card": p.ref(681), "result": p.ref(500), "tributes": [
            {"type": "Dragon", "min_attack": 0}, {"card": p.ref(5)},
            {"fusion_group": "Female", "defense_gt_attack": True}]}])
        self.assertEqual(reopen(self.retail, p).ritual_requirements, p.ritual_requirements)

    def test_plain_recipes_stay_plain(self):
        p, _ = self.load([{"card": 681, "tributes": [4, 5, 6], "result": 500}])
        self.assertEqual(p.ritual_requirements, {})
        self.assertEqual(manifest.build(p)["rituals"],
                         [{"card": p.ref(681), "tributes": [p.ref(4), p.ref(5), p.ref(6)], "result": p.ref(500)}])

    def test_later_entry_wins(self):
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, 5, 6], "result": 500},
                          {"card": 681, "tributes": [4, 5, 6], "result": 501}])
        self.assertNotIn(681, p.ritual_requirements)
        self.assertEqual(p.rituals[681], (4, 5, 6, 501))
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, 5, 6], "result": 500},
                          {"card": 681, "result": None}])
        self.assertNotIn(681, p.ritual_requirements)
        self.assertNotIn(681, p.rituals)

    def test_what_the_editor_cannot_place_is_kept(self):
        for tribute in ({"attribute": "Light"}, {"type": "Magic"}, {"fusion_group": "Elves"}, {},
                        {"min_level": 5, "max_level": 4}, {"min_attack": 10000}, {"defense_gt_attack": 1}):
            p, messages = self.load([{"card": 681, "tributes": [tribute, 5, 6], "result": 500}])
            self.assertIn("kept as written", " ".join(messages), tribute)
            self.assertNotIn(681, p.ritual_requirements)
            self.assertEqual(manifest.build(p)["rituals"][-1]["tributes"][0], tribute)

    def test_revert_clears_the_requirements(self):
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, 5, 6], "result": 500}])
        p.revert_ritual(681)
        self.assertEqual(p.ritual_requirements, {})
        self.assertEqual(p.rituals[681], self.retail.rituals[681])
        self.assertEqual(p.ritual_status(681), "")

    def test_one_to_five_and_where_from(self):
        p, messages = self.load([
            {"card": 681, "tributes": [4], "result": 500},
            {"card": 682, "tributes_from": "both", "result": 501,
             "tributes": [4, 5, {"type": "Dragon"}, {"min_attack": 0}, 6]}])
        self.assertEqual(messages, [])
        self.assertEqual(p.rituals[681], (4, 500))
        self.assertNotIn(681, p.ritual_from)
        self.assertEqual(p.ritual_from[682], "both")
        self.assertEqual(p.ritual_recipe(682)[0][2], {"type": "Dragon"})
        self.assertEqual(p.ritual_recipe(682)[1:], (501, "both"))
        self.assertEqual(p.ritual_status(681), "changed")
        built = manifest.build(p)["rituals"]
        self.assertEqual(built[0], {"card": p.ref(681), "tributes": [p.ref(4)], "result": p.ref(500)})
        self.assertEqual(built[1]["tributes_from"], "both")
        self.assertEqual(len(built[1]["tributes"]), 5)
        again = reopen(self.retail, p)
        self.assertEqual((again.rituals, again.ritual_requirements, again.ritual_from),
                         (p.rituals, p.ritual_requirements, p.ritual_from))
        self.assertEqual([i.message for i in validate.validate(p) if i.area == "Rituals"], [])

    def test_hand_only_three_is_not_the_disc_recipe(self):
        p, _ = self.load([{"card": 681, "tributes_from": "hand", "tributes": [1, 2, 3], "result": 500}])
        self.assertEqual(p.rituals[681], self.retail.rituals[681])
        self.assertEqual(p.ritual_status(681), "changed")
        self.assertEqual(manifest.build(p)["rituals"][0]["tributes_from"], "hand")
        # Written out, "field" is the disc's recipe again: nothing to write.
        p, _ = self.load([{"card": 681, "tributes_from": "field", "tributes": [1, 2, 3], "result": 500}])
        self.assertEqual(p.ritual_status(681), "")
        self.assertEqual(manifest.build(p).get("rituals", []), [])

    def test_what_the_game_leaves_out(self):
        for entry, words in (({"tributes": [1, 2, 3, 4, 5, 6]}, "one to five"), ({"tributes": []}, "one to five"),
                             ({"tributes": [1], "tributes_from": "deck"}, "\"field\", \"hand\" or \"both\""),
                             ({"tributes": [1], "tributes_from": True}, "\"field\", \"hand\" or \"both\"")):
            p, messages = self.load([dict(entry, card=681, result=500)])
            self.assertTrue(any(words in m for m in messages), (entry, messages))
            self.assertEqual(p.rituals[681], self.retail.rituals[681])

    def test_set_remove_revert_and_card_removal(self):
        p = Project(self.retail)
        p.set_ritual(681, [{"card": 4}, {"min_attack": 0}], 500, "hand")
        self.assertEqual(p.rituals[681], (4, 0, 500))
        self.assertEqual(p.ritual_requirements[681], [{"card": 4}, {"min_attack": 0}])
        self.assertEqual(p.ritual_from[681], "hand")
        p.set_ritual(681, [{"card": 4}], 500, "field")      # plain again, from the field
        self.assertEqual((p.rituals[681], p.ritual_requirements.get(681), p.ritual_from.get(681)), ((4, 500), None, None))
        p.set_ritual(681, [{"card": 4}], 500, "both")
        p.revert_ritual(681)
        self.assertEqual((p.rituals[681], p.ritual_from.get(681)), (self.retail.rituals[681], None))
        p.set_ritual(681, [{"card": 4}], 500, "both")
        p.remove_ritual(681)
        self.assertNotIn(681, p.ritual_from)
        self.assertEqual(manifest.build(p)["rituals"][0], {"card": p.ref(681), "result": None})
        copy = p.add_card(4, "gone")
        p.set_ritual(682, [{"card": copy}], 501, "hand")
        p.remove_card(copy)
        self.assertNotIn(682, p.rituals)
        self.assertNotIn(682, p.ritual_from)

    def test_validate_five_from_the_hand(self):
        p, _ = self.load([{"card": 681, "tributes_from": "hand", "tributes": [4, 5, 6, 7, 8], "result": 500}])
        found = [i for i in validate.validate(p) if i.area == "Rituals"]
        self.assertEqual([i.level for i in found], ["warning"], [i.message for i in found])
        self.assertIn("set face down first", found[0].message)

    def test_validate(self):
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, {"card": 5}, 6], "result": 500}])
        p.cards[5].type = g.TYPE_MAGIC
        found = [i.message for i in validate.validate(p) if i.area == "Rituals"]
        self.assertTrue(any("is not a monster" in m for m in found), found)


class TabTest(unittest.TestCase):
    """The Rituals tab, driven as a modder would."""
    # The window as test_gui starts it, without its tests.
    setUpClass = classmethod(test_gui.GuiTest.setUpClass.__func__)
    tearDownClass = classmethod(test_gui.GuiTest.tearDownClass.__func__)
    setUp = test_gui.GuiTest.setUp
    tearDown = test_gui.GuiTest.tearDown

    def widgets(self, root, kind):
        out = []
        for child in root.winfo_children():
            if isinstance(child, kind):
                out.append(child)
            out += self.widgets(child, kind)
        return out

    def open(self, ritual):
        tab = self.app.rituals
        self.app.notebook.select(tab.page)
        self.app.update()
        tab.show_card(ritual)
        self.app.update()
        return tab, self.app.project

    def button(self, root, text):
        return next(b for b in self.widgets(root, ttk.Button) + self.widgets(root, ttk.Radiobutton)
                    if b.cget("text") == text)

    def test_the_row_shows_the_recipe(self):
        tab, p = self.open(681)
        self.assertEqual(tab.tree.set("681", "tributes"), "3 \u00b7 field")
        items = {tab.row.gettags(i)[0] for i in tab.row.find_all() if tab.row.gettags(i)}
        self.assertTrue({"tile:ritual", "tile:0", "tile:1", "tile:2", "tile:result", "add"} <= items, items)
        self.assertIn("Play", tab.words.cget("text"))
        self.assertIn(p.cards[500].name, tab.words.cget("text"))

    def test_a_typed_card_is_checked(self):
        tab, p = self.open(681)
        tab.pick(0)
        entry = self.widgets(tab.editor, ttk.Entry)[0]
        entry.delete(0, "end")
        entry.insert(0, "No Such Card")
        tab._inputs["card"].picked()        # Enter, or leaving the box (the window is not on screen)
        self.app.update()
        self.assertIn("No card", tab.error.cget("text"))
        self.assertEqual(p.rituals[681], self.app.project.retail.rituals[681])
        entry.delete(0, "end")
        entry.insert(0, p.card_label(7))
        tab._inputs["card"].picked()
        self.app.update()
        self.assertEqual(p.rituals[681][0], 7)
        self.assertNotIn(681, p.ritual_requirements)
        self.assertEqual(tab.tree.set("681", "state"), "changed")

    def test_where_from_and_how_many(self):
        tab, p = self.open(681)
        self.button(tab, "In the hand").invoke()
        self.assertEqual(p.ritual_from[681], "hand")
        self.assertEqual(tab.tree.set("681", "tributes"), "3 \u00b7 hand")
        for n in (4, 5):
            tab.add_tribute()
            self.assertEqual(len(p.rituals[681]) - 1, n)
            self.assertEqual(p.ritual_requirements[681][-1], {"min_attack": 0})
        self.assertEqual(tab.picked, 4)
        items = {tab.row.gettags(i)[0] for i in tab.row.find_all() if tab.row.gettags(i)}
        self.assertNotIn("add", items)      # five is the most
        tab.add_tribute()
        self.assertEqual(len(p.rituals[681]) - 1, 5)
        for n in (4, 3, 2, 1):
            tab.remove_tribute(0)
            self.assertEqual(len(p.rituals[681]) - 1, n)
        tab.remove_tribute(0)       # one is the least
        self.assertEqual(len(p.rituals[681]) - 1, 1)
        self.assertFalse(any(t.startswith("remove:") for i in tab.row.find_all() for t in tab.row.gettags(i)))
        built = manifest.build_rituals(p)
        self.assertEqual(built[0]["tributes_from"], "hand")
        self.assertEqual(len(built[0]["tributes"]), 1)
        self.button(tab, "On the field").invoke()
        self.assertNotIn(681, p.ritual_from)

    def test_conditions(self):
        tab, p = self.open(681)
        tab.pick(1)
        self.button(tab.editor, "Any monster that...").invoke()
        self.app.update()
        kind = g.TYPE_NAMES[p.cards[2].type]
        self.assertEqual(p.ritual_requirements[681][1], {"type": kind})     # the card's type to start from
        tab.add_condition(1, "min_attack")
        self.assertEqual(p.ritual_requirements[681][1], {"type": kind, "min_attack": 1000})
        tab.add_condition(1, "max_attack")
        boxes = self.widgets(tab.editor, ttk.Spinbox)
        boxes[0].set("2500")        # above the most (2000)
        self.assertFalse(tab.commit())
        self.assertIn("least ATK is above the most", tab.error.cget("text"))
        boxes[0].set("x")
        self.assertFalse(tab.commit())
        boxes[0].set("1500")
        self.assertTrue(tab.commit())
        self.assertEqual(p.ritual_requirements[681][1]["min_attack"], 1500)
        self.assertIn("ATK 1500\u20132000", tab.words.cget("text"))
        tab.add_condition(1, "defense_gt_attack")
        self.assertTrue(p.ritual_requirements[681][1]["defense_gt_attack"])
        # A number still in its box is kept when another condition goes.
        self.widgets(tab.editor, ttk.Spinbox)[0].set("1600")
        drops = [b for b in self.widgets(tab.editor, ttk.Button) if b.cget("text") == "\u00d7"]
        drops[2].invoke()       # type, ATK at least, ATK at most, DEF above ATK: the most ATK
        self.assertEqual(p.ritual_requirements[681][1], {"type": kind, "min_attack": 1600, "defense_gt_attack": True})
        # Back to a card: the picker's choice.
        with mock.patch("fm_editor.rituals_tab.pick_card", return_value=9):
            self.button(tab.editor, "A specific card").invoke()
        self.assertEqual(p.rituals[681][1], 9)
        self.assertNotIn(681, p.ritual_requirements)
        validate.validate(p)

    def test_result_copy_remove_and_revert(self):
        tab, p = self.open(681)
        tab.pick("result")
        entry = self.widgets(tab.editor, ttk.Entry)[0]
        entry.delete(0, "end")
        entry.insert(0, p.card_label(20))
        tab._inputs["result"].picked()
        self.assertEqual(p.rituals[681][-1], 20)
        # The "..." picker applies its card as it closes.
        with mock.patch("fm_editor.widgets.pick_card", return_value=21):
            tab._inputs["result"].pick()
        self.app.update()
        self.assertEqual(p.rituals[681][-1], 21)
        copy = p.add_card(681, "own")
        tab.fill()
        tab.show_card(copy)
        self.assertEqual(tab.tree.set(str(copy), "state"), "as base")
        self.assertIn("base's recipe", tab.status.cget("text"))
        tab.make_own()
        self.assertEqual(p.rituals[copy], p.rituals[681])
        tab.remove()
        self.assertEqual(tab.tree.set(str(copy), "state"), "removed")
        self.assertIn({"card": p.ref(copy), "result": None}, manifest.build_rituals(p))
        tab.revert()
        self.assertEqual(tab.tree.set(str(copy), "state"), "as base")
        tab.show_card(681)
        tab.revert()
        self.assertEqual(p.rituals[681], p.retail.rituals[681])

    def test_search_and_changed_only(self):
        tab, p = self.open(681)
        tab.search.set(p.cards[501].name)
        self.assertEqual(tab.tree.get_children(), ("682",))
        tab.search.set("")
        p.set_ritual(681, [{"card": 4}], 500, "both")
        tab.changed_only.set(1)
        tab.fill()
        self.assertEqual(tab.tree.get_children(), ("681",))
        tab.show_card(682)          # shown even so: the filters give way
        self.assertEqual(tab.current, 682)
        self.assertFalse(tab.changed_only.get())

    def test_undo(self):
        tab, p = self.open(681)
        self.button(tab, "Both").invoke()
        self.pause()
        self.app.undo()
        self.app.update()
        p = self.app.project
        self.assertNotIn(681, p.ritual_from)
        self.assertEqual(tab.origin.get(), "field")

    pause = test_gui.GuiTest.pause
