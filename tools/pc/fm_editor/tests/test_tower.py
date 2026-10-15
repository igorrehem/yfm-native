"""The Tower tab's "tower" (tower.py, notes/tower-mode.md): its story and deck
text forms and back, the checks tower_config.c makes, the tower-only
duelists, the manifest round trip and its mod API, and the tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import unittest

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import compat, manifest, roster, tower, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

TOWER = {
    "name": "The Test Tower", "label": "TEST TOWER", "unlock": "after_ending", "on_lose": "restart",
    "intro": ["Three floors.", {"text": "Win them all.", "portrait": 0}],
    "ending": "The top.",
    "floors": [
        {"duelist": "Simon Muran", "checkpoint": True, "life_points": {"opponent": 100},
         "reward": {"cards": ["Mystic Elf"], "starchips": 25}, "before": "Show me.", "after": "Well fought."},
        {"duelist": "m:ghost", "field": "Yami", "no_fusions": True, "life_points": {"player": 100},
         "deck": {"Mystic Elf": 20, "Kuriboh": 20},
         "before": ["Nobody fuses here.", {"text": "Not even me.", "speaker": "m:ghost"}]},
        {"duelist": 7, "no_equips": True, "reward": {"unlock_duelist": "Nitemare"}},
    ],
}
MOD = {"id": "m", "name": "M", "duelists": [{"id": "ghost", "copy": "Simon Muran", "name": "Ghost Simon",
                                            "tower_only": True}],
       "tower": TOWER}


def project() -> Project:
    p = Project(fixture().game())
    manifest.apply(p, json.loads(json.dumps(MOD)))
    return p


def problems(p, value):
    return tower.check(value, lambda name: roster.named(p, name), lambda name: p.resolve(name))


class TowerTest(unittest.TestCase):
    def test_story_text(self):
        value = ["Plain line.", {"text": "Said.", "speaker": "Seto"}, {"text": "Faced.", "portrait": 8},
                 {"text": "Nobody's.", "speaker": "none"}, {"text": "By number.", "speaker": 7}]
        text = tower.story_text(value)
        self.assertEqual(text, "Plain line.\n@Seto: Said.\n#8: Faced.\n@none: Nobody's.\n@7: By number.")
        self.assertEqual(tower.story_value(text), value)
        self.assertEqual(tower.story_value("One line."), "One line.")
        self.assertIsNone(tower.story_value("\n  \n"))
        self.assertEqual(tower.story_text("Alone"), "Alone")
        # A colon in plain words is words: only "@who:" and "#number:" speak.
        self.assertEqual(tower.story_value("Note: it is late.\n#x: no"), ["Note: it is late.", "#x: no"])
        # Nothing a mod writes is lost on the way through the tab: a line
        # break in a box, plain words that look like a speaker's, a
        # portrait with a speaker, a backslash.
        kept = ["One\nTwo", {"text": "A\nB", "speaker": "Seto"}, "@Seto: plain words", "#3: plain too",
                {"text": "x", "portrait": 3, "speaker": "Seto"}, "back\\slash", "\\lead",
                # A backslash and n written as such, spaces the trimming would take, a lone space.
                "C:\\new", "\\nope", "  @Seto: hi", " \\o/", "ends ", " ", "two  ", "slash\\ ",
                {"text": " spaced ", "speaker": "Seto"}, {"text": "", "portrait": 1}]
        text = tower.story_text(kept)
        self.assertEqual(len(text.splitlines()), len(kept))
        self.assertEqual(tower.story_value(text), kept)
        self.assertIn("#3 @Seto: x", text)

    def test_deck_text(self):
        self.assertEqual(tower.deck_text({"Mystic Elf": 20, "Kuriboh": 1}), "Mystic Elf x20\nKuriboh")
        self.assertEqual(tower.deck_value("Mystic Elf x20\nKuriboh\n5 x3\nKuriboh"),
                         {"Mystic Elf": 20, "Kuriboh": 2, 5: 3})
        self.assertEqual(tower.deck_text([1, 1, 2]), "1 x2\n2")
        self.assertIsNone(tower.deck_value(""))
        self.assertEqual(tower.deck_count({"a": 20, "b": 20}), 40)
        self.assertEqual(tower.names_value("Kuriboh, 5"), ["Kuriboh", 5])
        self.assertEqual(tower.names_value("Kuriboh"), "Kuriboh")
        self.assertEqual(tower.names_text(["Kuriboh", 5]), "Kuriboh, 5")

    def test_terrain(self):
        self.assertEqual([tower.terrain_of(t) for t in ("none", "Forest", "yami", "Sea", "4", 6, None)],
                         [0, 1, 6, 5, 4, 6, 0])
        self.assertIsNone(tower.terrain_of("Lava"))

    def test_check_good(self):
        p = project()
        self.assertEqual(problems(p, TOWER), [])
        self.assertEqual(problems(p, None), [])

    def test_check_mistakes(self):
        """What tower_config.c notes, the same way: an error where the game
        leaves a part out, a warning where it reads it otherwise."""
        p = project()
        self.assertEqual([lvl for lvl, _, _ in problems(p, [1])], ["error"])
        self.assertIn(("error", "tower.floors"), {(lvl, w) for lvl, w, _ in problems(p, {"name": "x"})})
        bad = {"unlock": "after-ending", "on_lose": "retry", "colour": 1, "music": 99999,
               "label": "A LABEL FAR LONGER THAN THIRTY ONE LETTERS",
               "floors": [{"duelist": "Nobody"},
                          {"duelist": "Seto", "field": "Lava", "no_fusions": "true", "life_points": 0,
                           "deck": {"Mystic Elf": 39}, "reward": {"cards": ["Nothing"], "starchips": -5, "gold": 1},
                           "before": [{"text": "Hi.", "portrait": 30}, 5], "checkpoint": 1, "boss": True}]}
        found = {(lvl, w) for lvl, w, _ in problems(p, bad)}
        for expected in (("error", "tower.unlock"), ("warning", "tower.on_lose"), ("warning", "tower"),
                         ("warning", "tower.music"), ("warning", "tower.label"), ("error", "tower.floors[0]"),
                         ("warning", "tower.floors[1].field"), ("warning", "tower.floors[1].no_fusions"),
                         ("warning", "tower.floors[1].life_points"), ("error", "tower.floors[1].deck"),
                         ("warning", "tower.floors[1].reward"), ("warning", "tower.floors[1].reward.starchips"),
                         ("warning", "tower.floors[1].before[0]"), ("error", "tower.floors[1].before[1]"),
                         ("warning", "tower.floors[1].checkpoint"), ("warning", "tower.floors[1]")):
            self.assertIn(expected, found)
        self.assertIn(("error", "tower.floors"),
                      {(lvl, w) for lvl, w, _ in problems(p, {"floors": [{"duelist": "Nobody"}]})})
        unlock = {(lvl, w) for lvl, w, _ in problems(p, {"unlock": {"wins": "many", "beat": "Nobody"},
                                                         "floors": [{"duelist": 1}]})}
        self.assertEqual(unlock, {("error", "tower.unlock.wins"), ("warning", "tower.unlock.beat")})
        # after_ending in quotes keeps the tower locked in the game: an error.
        self.assertIn(("error", "tower.unlock.after_ending"),
                      {(lvl, w) for lvl, w, _ in problems(p, {"unlock": {"after_ending": "yes"},
                                                              "floors": [{"duelist": 1}]})})

    def test_tower_condition_kept(self):
        """A duelist whose only condition is "tower" keeps it through the
        Duelists tab's unlock form, which does not show it."""
        from fm_editor import duelist_rules
        e = roster.find(project(), "ghost")
        e.extra["unlock"] = {"tower": 2}
        self.assertEqual(duelist_rules.unlock_value(e), {"tower": 2})
        self.assertEqual(duelist_rules.unlock_value(e, beat="Seto"), {"beat": "Seto", "tower": 2})

    def test_same_as_the_game(self):
        """The keys tower_config.c knows are the editor's."""
        import re
        from pathlib import Path
        source = (Path(__file__).resolve().parents[4] / "src/pc/tower/tower_config.c").read_text(encoding="utf-8")
        arrays = [tuple(re.findall(r'"(\w+)"', body)) for body in re.findall(r"known\[\] = \{(.*?)\};", source, re.S)]
        for keys in (tower.TOWER_KEYS, tower.FLOOR_KEYS, tower.REWARD_KEYS, tower.UNLOCK_KEYS, tower.LINE_KEYS):
            self.assertIn(tuple(keys), arrays)

    def test_stage_text(self):
        """A story's stage as the tab writes it: brackets on the line
        before, and back to what the manifest says, every key."""
        value = {"scene": "seal shrine", "characters": {"left": 1, "right": "opponent"},
                 "lines": [{"text": "My prince.", "speaker": "left"},
                           {"text": "Look.", "speaker": "right", "scene": "scenes/sky.png", "portrait": "speaker",
                            "characters": {"right": {"image": "art/hero.png", "flip": True, "duelist": "Seto"}}},
                           {"text": "Panned.", "pan": {"x": 64, "y": 0, "frames": 30, "wait": True}, "scene": 139,
                            "characters": {"left": {"character": 4, "expression": 2}, "right": "none"}},
                           {"text": "Plain.", "portrait": 3, "speaker": "Seto"}]}
        text = tower.story_text(value)
        self.assertEqual(text.splitlines(), [
            "[scene: seal shrine] [left: 1] [right: opponent]",
            "@left: My prince.",
            "[scene: scenes/sky.png] [right: art/hero.png flip as Seto]",
            "#speaker @right: Look.",
            "[scene: 139] [left: 4 expression 2] [right: none] [pan: 64 0 30 wait]",
            "Panned.",
            "#3 @Seto: Plain."])
        self.assertEqual(tower.canon_story(tower.story_value(text)), tower.canon_story(value))
        self.assertTrue(tower.same_story(value, text))
        # Words that read as a stage are words, behind a backslash.
        self.assertEqual(tower.story_text(["[scene: x]"]), "\\[scene: x]")
        self.assertEqual(tower.story_value("\\[scene: x]"), "[scene: x]")
        # A scene by number, by name or "none": the same scene.
        self.assertTrue(tower.same_story({"text": "A.", "scene": 22}, "[scene: torch corridor]\nA."))
        self.assertTrue(tower.same_story({"text": "A.", "scene": "none"}, "[scene: black]\nA."))
        self.assertFalse(tower.same_story({"text": "A.", "scene": 22}, "[scene: 23]\nA."))
        # A duelist by number stays a duelist; "as" keeps its expression;
        # names and paths with spaces; a pan however briefly written.
        for value in ({"text": "A.", "characters": {"left": {"duelist": 7}}},
                      {"text": "A.", "characters": {"right": {"image": "my art.png", "duelist": "Seto",
                                                              "expression": 2, "flip": True}}},
                      {"text": "A.", "characters": {"left": "Flip Master", "right": "a b.png"}},
                      {"text": "A.", "pan": {"x": 64}}):
            text = tower.story_text([value])
            self.assertEqual(tower.canon_story(tower.story_value(text)), tower.canon_story([value]), text)
            self.assertTrue(tower.same_story([value], text), text)
        self.assertEqual(tower.story_text([{"text": "A.", "characters": {"left": {"duelist": 7}}}]),
                         "[left: duelist 7]\nA.")
        # As the game reads a scene: a digit string is none of its (only the tab types numbers).
        self.assertIsNone(tower.scene_number("22"))
        self.assertEqual(tower.scene_number("22", typed=True), 22)
        self.assertIsNone(tower.scene_number(".png"))

    def test_stage_checks(self):
        p = project()
        bad = {"scene": 150, "dim": "yes", "intro": {"scene": "../out.png", "characters": {"middle": 1, "left": 39},
                                                    "lines": [{"text": "A.", "pan": {"x": 9999, "speed": 1},
                                                               "characters": {"right": {"character": 2,
                                                                                        "expression": 9}}},
                                                              {"text": "B.", "portrait": "face",
                                                               "characters": {"left": {"duelist": 7, "flip": True}}}],
                                                    "speed": 1},
               "floors": [{"duelist": 1}]}
        found = {(where, message.split(";")[0]) for _, where, message in problems(p, bad)}
        for where, start in (("tower.scene", "is a scene's name"), ("tower.dim", "is true or false"),
                             ("tower.intro", "unknown key \"speed\""), ("tower.intro.scene", "../out.png is not a path"),
                             ("tower.intro.characters", "unknown key \"middle\""),
                             ("tower.intro.characters.left.character", "is one of the campaign's"),
                             ("tower.intro[0].pan", "unknown key \"speed\""), ("tower.intro[0].pan.x", "is 0 to 576"),
                             ("tower.intro[0].characters.right.expression", "is 0 to 3"),
                             ("tower.intro[1]", "\"portrait\" is one of the campaign's portraits"),
                             ("tower.intro[1].characters.left.flip", "turns a PNG")):
            self.assertTrue(any(w == where and m.startswith(start) for w, m in found), (where, start, found))
        # The game's limits: five pictures of the mod's a story, "opponent" in a story of no floor,
        # a line without words but with a stage.
        many = {"intro": [{"text": "A.", "characters": {"left": f"c{n}.png"}} for n in range(6)] +
                [{"text": "", "scene": 1}, {"text": "B.", "characters": {"right": "opponent"}}],
                "floors": [{"duelist": 1, "before": {"text": "Hi.", "characters": {"right": "opponent"}}}]}
        found = [(where, message) for _, where, message in problems(p, many)]
        self.assertIn(("tower.intro", "a story shows at most 5 characters of the mod's; the rest are left out"), found)
        self.assertTrue(any(w == "tower.intro" and m.startswith("\"opponent\" is a floor's") for w, m in found))
        self.assertTrue(any(w == "tower.intro[6]" and m.startswith("a line without words") for w, m in found))
        self.assertFalse(any(w.startswith("tower.floors[0]") for w, m in found))
        self.assertEqual(problems(p, {"scene": "torch corridor", "intro": {"text": "A.", "scene": 205},
                                      "floors": [{"duelist": 1}]}), [])

    def test_scenes_same_as_the_game(self):
        """The scene names and the stage's keys are tower_config.c's."""
        import re
        from pathlib import Path
        source = (Path(__file__).resolve().parents[4] / "src/pc/tower/tower_config.c").read_text(encoding="utf-8")
        names = re.search(r"scene_names\[TOWER_SCENE_NAMES\] = \{(.*?)\};", source, re.S).group(1)
        self.assertEqual(tuple(re.findall(r'"([^"]*)"', names)), tower.SCENE_NAMES)
        arrays = [tuple(re.findall(r'"(\w+)"', body)) for body in re.findall(r"known\[\] = \{(.*?)\};", source, re.S)]
        for keys in (tower.STORY_KEYS, tower.CAST_KEYS, tower.PAN_KEYS, tower.SIDES):
            self.assertIn(tuple(keys), arrays)
        header = (Path(__file__).resolve().parents[4] / "src/pc/tower/tower.h").read_text(encoding="utf-8")
        self.assertIn(f"#define TOWER_STORY_TEXT {tower.STORY_LETTERS} ", header)

    def test_stage_pictures(self):
        """The pickers' pictures, made from a disc's bytes as the game
        reads them (a made-up archive here: nothing of the disc's)."""
        from fm_editor import tower_art
        wa = bytearray((tower_art.CHARACTER_BASE + 2 * 50) * tower_art.SECTOR)
        base = tower_art.SCENE_BASE * tower_art.SECTOR      # scene 0x000
        palette = base + 32 * tower_art.SECTOR
        wa[palette + 2:palette + 4] = (31).to_bytes(2, "little")        # color 1: red
        wa[palette + 4:palette + 6] = (31 << 10).to_bytes(2, "little")  # color 2: blue
        wa[base + 5 * 128 + 7] = 1                                      # picture (7, 5)
        wa[base + 16 * tower_art.SECTOR + 170 * 128 + 3] = 2            # column 1 (128 + 3), row 170: (259, 10)
        image = tower_art.scene_image(bytes(wa), 0x000)
        self.assertEqual(image.size, (320, 160))
        self.assertEqual(image.pixel(7, 5), (248, 0, 0, 255))
        self.assertEqual(image.pixel(259, 10), (0, 0, 248, 255))
        self.assertEqual(image.pixel(0, 0)[3], 0)
        # Character 1: one part of 16 x 8 at (-8, -8), texels 1 at its corner.
        record = (tower_art.CHARACTER_BASE + 50) * tower_art.SECTOR
        wa[record + 48 * tower_art.SECTOR + 2:record + 48 * tower_art.SECTOR + 4] = (31 << 5).to_bytes(2, "little")
        wa[record] = 1
        bank = record + 49 * tower_art.SECTOR
        for at, value in ((0, 8), (8, 14), (14, 16)):
            wa[bank + at:bank + at + 2] = value.to_bytes(2, "little")
        wa[bank + 16:bank + 19] = bytes((0, 20, 0))
        wa[bank + 20:bank + 24] = bytes((1, 0, 0, 0))
        wa[bank + 24:bank + 30] = bytes((0xF8, 0xF8)) + (0).to_bytes(2, "little") + ((1 << 5) | (0 << 9)).to_bytes(2, "little")
        image = tower_art.character_image(bytes(wa), 1)
        self.assertEqual(image.size, (16, 8))
        self.assertEqual(image.pixel(0, 0), (0, 248, 0, 255))
        self.assertIsNone(tower_art.character_image(bytes(wa), 5))      # one the disc keeps empty

    def test_tower_only(self):
        p = project()
        self.assertEqual(tower.tower_only(p), ["ghost"])
        self.assertTrue(tower.set_tower_only(p, "ghost", False))
        self.assertEqual(tower.tower_only(p), [])
        self.assertFalse(tower.set_tower_only(p, "ghost", False))
        self.assertTrue(tower.set_tower_only(p, "ghost", True))
        self.assertFalse(tower.set_tower_only(p, "nobody", True))

    def test_manifest_and_validate(self):
        p = project()
        built = manifest.build(p)
        self.assertEqual(built["tower"], TOWER)
        self.assertEqual(built["duelists"][0]["tower_only"], True)
        self.assertEqual(compat.required(built)[0], 14)
        self.assertEqual([i for i in validate.validate(p) if i.area == "Tower"], [])
        p.other["tower"] = {"floors": [{"duelist": "Nobody"}]}
        issues = [(i.level, i.where) for i in validate.validate(p) if i.area == "Tower"]
        self.assertIn(("error", "tower.floors"), issues)
        self.assertFalse([i for i in validate.validate(p) if i.area == "Mod info" and i.where == "tower"])


class TowerTabTest(unittest.TestCase):
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

    def make(self, p):
        from tkinter import ttk
        from fm_editor.tower_tab import TowerTab

        class App:
            def __init__(self):
                self.project = p
                self.changes = 0

            def changed(self):
                self.changes += 1

        app = App()
        tab = TowerTab(ttk.Notebook(self.root), app)
        tab.refresh()
        return app, tab

    def test_guide_and_example(self):
        """The tab's own help: the guide opens, and the example is a tower
        the game reads without a note."""
        p = project()
        app, tab = self.make(p)
        tab.show_guide()
        self.assertTrue(tab.guide.winfo_exists())
        tab.guide.destroy()
        tab.start_example(ask=False)
        self.assertEqual(p.other["tower"], tower.example_tower())
        self.assertEqual(problems(p, p.other["tower"]), [])
        self.assertTrue(tab.has.get() and len(tab.list.get_children()) == 3)
        self.assertEqual(app.changes, 1)
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"], tower.example_tower())   # shown and committed untouched: as it is

    def test_rules_of_the_run(self):
        """on_leave, drops, save_states and cheats: shown, written only when
        they differ from the defaults, kept as written."""
        p = project()
        app, tab = self.make(p)
        self.assertEqual((tab.vars["on_leave"].get(), tab.vars["drops"].get(), tab.vars["save_states"].get(),
                          tab.vars["cheats"].get()), ("resume", "1", True, True))
        tab.vars["on_leave"].set("checkpoint")
        tab.vars["drops"].set("player")
        tab.vars["save_states"].set(False)
        tab.vars["cheats"].set(False)
        self.assertTrue(tab.commit())
        written = p.other["tower"]
        self.assertEqual((written["on_leave"], written["drops"], written["save_states"], written["cheats"]),
                         ("checkpoint", "player", False, False))
        self.assertEqual(problems(p, written), [])
        tab.refresh()
        self.assertEqual(tab.vars["drops"].get(), "player")
        tab.vars["drops"].set("12")
        tab.vars["on_leave"].set("resume")
        tab.vars["save_states"].set(True)
        self.assertTrue(tab.commit())
        written = p.other["tower"]
        self.assertEqual(written["drops"], 12)
        self.assertNotIn("on_leave", written)
        self.assertNotIn("save_states", written)
        self.assertTrue(any(w == "tower.drops" for _, w, _ in problems(p, dict(written, drops=200))))
        # As the game reads them: any case, and a drops it cannot read is the default.
        p.other["tower"] = dict(written, on_leave="Checkpoint", drops="Player")
        tab.refresh()
        self.assertEqual((tab.vars["on_leave"].get(), tab.vars["drops"].get()), ("checkpoint", "player"))
        self.assertTrue(tab.commit())
        self.assertEqual((p.other["tower"]["on_leave"], p.other["tower"]["drops"]), ("Checkpoint", "Player"))
        tab.vars["drops"].set("abc")
        tab.vars["name"].set("Renamed")
        self.assertTrue(tab.commit())
        self.assertNotIn("drops", p.other["tower"])
        self.assertEqual(tab.vars["drops"].get(), "1")

    def test_unlock_opponent(self):
        """The floor's checkbox: a tower-only opponent unlocks by default
        (unticked writes false), a disc one does not (ticked writes true);
        the picker adds more duelists to unlock."""
        p = project()
        app, tab = self.make(p)
        tab.list.selection_set("1")      # the tower-only Ghost Simon
        tab.pick()
        self.assertTrue(tab.vars["unlock_opponent"].get())
        self.assertIn("tower's own", tab.unlock_hint.cget("text"))
        tab.vars["unlock_opponent"].set(False)
        tab._unlock_touched()            # unticked by hand
        self.assertIs(p.other["tower"]["floors"][1]["unlock_opponent"], False)
        tab.list.selection_set("2")      # Seto (7), the disc's
        tab.pick()
        self.assertFalse(tab.vars["unlock_opponent"].get())
        tab.vars["unlock_opponent"].set(True)
        tab._unlock_touched()
        tab.unlock_pick.set("Nitemare")
        tab._add_unlock()
        tab.unlock_pick.set("Rex Raptor")
        tab._add_unlock()
        tab._add_unlock()                # once
        self.assertTrue(tab.commit())
        floor = p.other["tower"]["floors"][2]
        self.assertIs(floor["unlock_opponent"], True)
        self.assertEqual(floor["reward"]["unlock_duelist"], ["Nitemare", "Rex Raptor"])
        tab._remove_unlock()
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"]["floors"][2]["reward"]["unlock_duelist"], "Nitemare")
        # A floor nobody touched keeps not saying it, and its box follows
        # the opponent: changed to the tower-only Ghost Simon, ticked.
        self.assertNotIn("unlock_opponent", p.other["tower"]["floors"][0])
        tab.list.selection_set("0")
        tab.pick()
        self.assertFalse(tab.vars["unlock_opponent"].get())
        tab.vars["duelist"].set("m:ghost")
        self.assertTrue(tab.commit())
        self.assertTrue(tab.vars["unlock_opponent"].get())
        self.assertNotIn("unlock_opponent", p.other["tower"]["floors"][0])

    def test_tab_shows_and_keeps(self):
        p = project()
        app, tab = self.make(p)
        self.assertTrue(tab.has.get())
        self.assertEqual(tab.vars["name"].get(), "The Test Tower")
        self.assertEqual(tab.vars["unlock"].get(), "after_ending")
        self.assertEqual(tab.vars["on_lose"].get(), "restart")
        self.assertEqual(len(tab.list.get_children()), 3)
        self.assertEqual(tab.vars["duelist"].get(), "Simon Muran")
        self.assertTrue(tab.vars["checkpoint"].get())
        self.assertEqual(tab.vars["lp.opponent"].get(), "100")
        self.assertEqual(tab.vars["reward.cards"].get(), "Mystic Elf")
        self.assertEqual(tab._get_text("intro"), "Three floors.\n#0: Win them all.")
        self.assertEqual(tab.only.curselection(), (0,))
        # Committed untouched (as every tab switch does): as written, unchanged.
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"], TOWER)
        self.assertEqual(app.changes, 0)
        # The second floor in the form, and back.
        tab.list.selection_set("1")
        tab.pick()
        self.assertEqual((tab.vars["field"].get(), tab.vars["no_fusions"].get(), tab.vars["lp.player"].get()),
                         ("Dark", True, "100"))
        self.assertEqual(tab._get_text("deck"), "Mystic Elf x20\nKuriboh x20")
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"], TOWER)

    def test_tab_keeps_spelling(self):
        """Floors and fields nobody touched stay as the mod wrote them, key
        order and spelling, even when another part of the tower changed."""
        p = project()
        odd = {"floors": [{"before": [{"text": "Hi."}], "duelist": "Simon Muran",
                           "life_points": {"player": 8000, "opponent": 8000}, "reward": {"card": "Mystic Elf"}},
                          {"duelist": 7, "field": "yami"}],
               "intro": [{"text": "One\nTwo"}], "name": "Odd"}
        p.other["tower"] = json.loads(json.dumps(odd))
        app, tab = self.make(p)
        tab.list.selection_set("1")
        tab.pick()
        tab.list.selection_set("0")
        tab.pick()
        self.assertTrue(tab.commit())
        self.assertEqual(json.dumps(p.other["tower"]), json.dumps(odd))
        self.assertEqual(app.changes, 0)
        # The name changed: the untouched intro and floors keep their spelling.
        tab.vars["name"].set("Even")
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"]["name"], "Even")
        self.assertEqual(p.other["tower"]["intro"], odd["intro"])
        self.assertEqual(json.dumps(p.other["tower"]["floors"]), json.dumps(odd["floors"]))
        # A floor moved stays as written too.
        tab.move(1)
        self.assertEqual(json.dumps(p.other["tower"]["floors"]), json.dumps(odd["floors"][::-1]))

    def test_tab_edits(self):
        p = project()
        app, tab = self.make(p)
        tab.list.selection_set("2")
        tab.pick()
        tab.vars["no_equips"].set(False)
        tab.vars["lp.player"].set("4000")
        tab.vars["lp.opponent"].set("4000")
        tab.vars["field"].set("Forest")
        tab._set_text("after", "@Seto: You win.\nThe end.")
        self.assertTrue(tab.commit())
        floor = p.other["tower"]["floors"][2]
        self.assertEqual(floor, {"duelist": 7, "field": "Forest", "life_points": 4000,
                                 "reward": {"unlock_duelist": "Nitemare"},
                                 "after": [{"text": "You win.", "speaker": "Seto"}, "The end."]})
        self.assertGreater(app.changes, 0)
        # A floor added, moved up, removed.
        tab.add()
        self.assertEqual(len(p.other["tower"]["floors"]), 4)
        tab.vars["duelist"].set("Heishin")
        tab.move(-1)
        self.assertEqual(p.other["tower"]["floors"][2]["duelist"], "Heishin")
        tab.remove()
        self.assertEqual([f["duelist"] for f in p.other["tower"]["floors"]], ["Simon Muran", "m:ghost", 7])
        # The tower's own duelists, and the conditions.
        tab.only.selection_clear(0, "end")
        tab.vars["unlock"].set("conditions")
        tab.vars["unlock.beat"].set("Seto")
        tab.vars["unlock.after_ending"].set(True)
        self.assertTrue(tab.commit())
        self.assertNotIn("tower_only", roster.find(p, "ghost").extra)
        self.assertEqual(p.other["tower"]["unlock"], {"after_ending": True, "beat": "Seto"})
        # Off: no tower in the mod.
        tab.has.set(False)
        tab.toggle()
        self.assertNotIn("tower", p.other)
        self.assertNotIn("tower", manifest.build(p))

    def test_tab_new_tower(self):
        p = Project(fixture().game())
        app, tab = self.make(p)
        self.assertFalse(tab.has.get())
        tab.has.set(True)
        tab.toggle()
        self.assertEqual(p.other["tower"], {"floors": [{"duelist": 1}]})
        tab.vars["name"].set("Mine")
        tab.vars["music"].set("0x2C0")
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"], {"name": "Mine", "music": 0x2C0, "floors": [{"duelist": 1}]})
        self.assertEqual(compat.required(manifest.build(p))[0], 14)

    def test_stage_keeps_spelling(self):
        """A mod that wrote its stage its own way keeps it through the tab."""
        p = project()
        odd = {"scene": 18, "dim": True, "intro": {"scene": 22, "characters": {"left": {"character": 1}},
                                                   "lines": ["One.", {"text": "Two.", "speaker": "left"}]},
               "floors": [{"duelist": 1, "before": [{"text": "Hi.", "scene": "TORCH_CORRIDOR"}]}]}
        p.other["tower"] = json.loads(json.dumps(odd))
        app, tab = self.make(p)
        self.assertEqual(tab.vars["scene"].get(), "seal shrine")
        self.assertTrue(tab.vars["dim"].get())
        self.assertTrue(tab.commit())
        self.assertEqual(json.dumps(p.other["tower"]), json.dumps(odd))
        self.assertEqual(app.changes, 0)
        tab.vars["name"].set("Named")
        self.assertTrue(tab.commit())
        self.assertEqual(p.other["tower"]["intro"], odd["intro"])
        self.assertEqual(p.other["tower"]["scene"], 18)
        self.assertEqual(p.other["tower"]["dim"], True)
        # The stage box writes a line before the cursor's.
        tab.last_story = "ending"
        tab._set_text("ending", "The top.")
        tab.stage_scene.set("burning pyramid")
        tab._insert("[scene: burning pyramid]")
        tab.stage_character.set("4")
        tab.stage_side.set("right")
        tab.stage_expression.set("1")
        tab._character()
        self.assertEqual(tower.canon_story(p.other["tower"]["ending"]),
                         [{"scene": 41, "characters": {"right": {"character": 4, "expression": 1}}, "text": "The top."}])


if __name__ == "__main__":
    unittest.main()
