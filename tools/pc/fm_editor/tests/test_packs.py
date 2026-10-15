"""Card packs ("packs", "pack_shop", notes/card-packs.md): the dealer against
the game's own deals (tests/pc/packs_golden.txt, written by the C dealer of
src/pc/cards/packs.c), the reader's defaults and rules, the manifest layer
and Simulate.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import unittest
from pathlib import Path

from fm_editor import manifest, packs, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "tests" / "pc" / "packs_fixture.json"
GOLDEN = ROOT / "tests" / "pc" / "packs_golden.txt"


def by_id(value):
    """The C test's card table (tests/pc/packs_test.c): a card is its id,
    1 to 2000; ids past 722 stand for a mod's."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if 1 <= value <= 2000 else -1
    if isinstance(value, str) and value.isdigit():
        return int(value) if 1 <= int(value) <= 2000 else -1
    return -1


def project() -> Project:
    return Project(fixture().game())


def read(source: dict):
    p = project()
    messages = manifest.apply(p, {"id": "m", **source})
    return p, messages


class GoldenTest(unittest.TestCase):
    """What the game deals, the editor deals: line for line, final
    generator state included (so the numbers spent agree too)."""

    def test_the_editor_deals_what_the_game_deals(self):
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))
        read_packs, notes = packs.read_packs(source["packs"], by_id, "golden")
        self.assertEqual(notes, [])
        found = {p.id: p for p in read_packs}
        lines = []
        for case in source["cases"]:
            pack = found[case["pack"]]
            pity = [0] * packs.TIERS_MAX
            for name, n in case.get("pity", {}).items():
                pity[pack.tier_named(name)] = n
            held = {int(k): v for k, v in case.get("held", {}).items()}
            for seed in case["seeds"]:
                lines.append(packs.golden_line(pack, seed, pity, lambda card: held.get(card, 0)))
        golden = GOLDEN.read_text(encoding="utf-8").replace("\r", "").splitlines()
        self.assertEqual(len(lines), len(golden))
        for mine, theirs in zip(lines, golden):
            self.assertEqual(mine, theirs)

    def test_four_numbers_a_slot_whatever_the_pack(self):
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for pack in packs.read_packs(source["packs"], by_id, "golden")[0]:
            for seed in range(50):
                count = {"n": 0}
                random = packs.Lcg(seed * 2654435761)

                def draw():
                    count["n"] += 1
                    return random()
                packs.deal(pack, draw, [5] * packs.TIERS_MAX, lambda card: 1)
                self.assertEqual(count["n"], packs.DRAWS_PER_SLOT * pack.count)

    def test_save_seed_is_the_game_s(self):
        # FNV-1a of "%08X:identity:opened", as packs.c Packs_SaveSeed.
        h = 2166136261
        for byte in b"12345678:test:a:3":
            h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
        self.assertEqual(packs.save_seed(0x12345678, "test:a", 3), h)
        self.assertNotEqual(packs.save_seed(0x12345678, "test:a", 3), packs.save_seed(0x12345678, "test:a", 4))


class ReaderTest(unittest.TestCase):
    def one(self, entry):
        return packs.read_pack(entry, by_id, "m", 0)

    def errors(self, entry):
        pack, notes = self.one(entry)
        return pack, [m for level, m in notes if level == "error"]

    def test_the_smallest_pack(self):
        pack, notes = self.one({"name": "Dragons", "price": 50, "cards": [1, 2, 3]})
        self.assertEqual(notes, [])
        self.assertEqual((pack.id, pack.identity, pack.price, pack.count), ("dragons", "m:dragons", 50, 5))
        self.assertEqual([t.name for t in pack.tiers], ["cards"])
        self.assertEqual(pack.cover, 1)
        self.assertTrue(pack.listed)
        self.assertEqual(packs.slug("Legend of B.E.W.D."), "legend-of-b-e-w-d")

    def test_errors_leave_the_pack_out(self):
        for entry, words in (
                ({"cards": [1], "count": 0}, "\"count\" is 1 to 40"),
                ({"cards": [1], "count": 41}, "\"count\" is 1 to 40"),
                ({"cards": [1], "slots": [{"card": 1}] * 41}, "\"count\" is 1 to 40"),
                ({"tiers": {"a": {"cards": [1]}}, "count": 3, "slots": ["a", "a"]}, "a list of 3"),
                ({"tiers": {"a": {"cards": [1]}}, "slots": ["a", "b"]}, "no tier \"b\""),
                ({"cards": {"1": -2}}, "a weight is a whole number"),
                ({"cards": {"1": 600000, "2": 600000}}, "add up to 1200000"),
                ({"cards": [1], "price": 1000000}, "0 to 999999 starchips"),
                ({"cards": [1], "id": "bad id!"}, "\"id\" is 1-63"),
                ({"tiers": {"a": {"cards": [1]}}, "guarantee": {"b": 1}}, "not a tier of the pack"),
                ({"tiers": {"a": {"cards": [1]}}, "pity": {"a": 0}}, "not a tier of the pack"),
                ({"cards": [1, 2], "count": 3, "duplicates": "unique_in_pack"}, "unique_in_pack"),
                ({"cards": [1], "tiers": {"a": {"cards": [1]}}}, "give one"),
                ({"cards": [9999]}, "none of its cards are here"),
                ({"name": "no cards"}, "no \"cards\" or \"tiers\""),
                ({"tiers": {"a": {"odds": 0, "cards": [1]}}}, "every tier's"),
                ({"tiers": {"a b": {"cards": [1]}}}, "a tier's name")):
            pack, errors = self.errors(entry)
            self.assertIsNone(pack, entry)
            self.assertTrue(any(words in e for e in errors), (entry, errors))
        # A tier of odds 0 is fine when a slot names it.
        self.assertIsNotNone(self.one({"tiers": {"a": {"odds": 0, "cards": [1]}}, "slots": ["a"]})[0])

    def test_notes_keep_the_pack(self):
        pack, notes = self.one({"cards": [1, 9999, "Nobody"], "prise": 5, "restock": {},
                                "name": "A Very Long Pack Name Indeed"})
        text = "\n".join(m for _, m in notes)
        self.assertEqual(len(pack.tiers[0].pool), 1)
        self.assertIn("did you mean \"price\"", text)
        self.assertIn("\"restock\" is not built yet", text)
        self.assertIn("cut there", text)
        self.assertEqual(len(pack.name), packs.NAME_LETTERS)
        pack, notes = self.one({"cards": [1, 800], "include_added_cards": False})
        self.assertEqual(len(pack.tiers[0].pool), 1)
        pack, notes = self.one({"cards": [1], "password": "00001234"})
        self.assertEqual(pack.password, 0x1234)
        self.assertFalse(pack.listed)
        self.assertIn("\"autosave\" is not built yet",
                      "\n".join(m for _, m in packs.check_rules({"autosave": True})))

    def test_order_sorts_the_list(self):
        found, notes = packs.read_packs([{"id": "a", "cards": [1]}, {"id": "b", "cards": [1], "order": -5}], by_id)
        self.assertEqual([p.id for p in found], ["b", "a"])
        # Of two packs with one password the first in that order is sold.
        found, notes = packs.read_packs([{"id": "a", "cards": [1], "password": 7},
                                         {"id": "b", "cards": [1], "password": "7", "order": -5}], by_id)
        self.assertEqual([m for _, m in notes], ["pack \"a\": its password is pack \"mod:b\"'s too; that one is sold"])
        # A pack's place when it gives no "order" counts only the packs past
        # their id, as the game's `declared`: "a" is 0, as "b" says it is.
        found, notes = packs.read_packs([{"id": "bad id!", "cards": [1]}, {"id": "a", "cards": [1], "password": 7},
                                         {"id": "b", "cards": [1], "password": 7, "order": 0}], by_id)
        self.assertEqual([p.id for p in found], ["a", "b"])
        self.assertIn("pack \"b\": its password is pack \"mod:a\"'s too; that one is sold", [m for _, m in notes])
        # ...and one left out after its id is counted.
        found, _ = packs.read_packs([{"id": "x", "cards": [1], "price": -1}, {"id": "a", "cards": [1]},
                                     {"id": "b", "cards": [1], "order": 0}], by_id)
        self.assertEqual([p.id for p in found], ["b", "a"])

    def test_null_is_a_value_of_the_wrong_kind(self):
        """As the game's reader (packs.c) takes a key written null: not a key
        left out (tests/pc/packs_test.c holds the game to the same)."""
        for entry in ({"cards": [1], "price": None}, {"cards": [1], "cost": None}, {"cards": [1], "count": None},
                      {"cards": [1], "guarantee": None}, {"cards": [1], "max_copies": None},
                      {"cards": None}, {"tiers": {"a": {"odds": None, "cards": [1]}}},
                      {"tiers": {"a": {"cards": [1]}}, "slots": None}, {"cards": [1], "tiers": None},
                      {"cards": [1], "cost": {"starchips": None}}):
            self.assertIsNone(self.one(entry)[0], entry)
        for key, words in (("stock", "\"stock\" is 1 to 999999"), ("order", "\"order\" is a whole number"),
                           ("unlock", "\"unlock\" is an object"), ("locked", "\"locked\" is \"hidden\""),
                           ("image", "\"image\" is a PNG"), ("sounds", "\"sounds\" is {"),
                           ("when_nothing_left", "\"when_nothing_left\" is"), ("shop", "\"shop\" is a shop's id")):
            pack, notes = self.one({"cards": [1], key: None})
            self.assertIsNotNone(pack, key)
            self.assertTrue(any(words in m for _, m in notes), (key, notes))
        # ...and what Json_Bool makes of null, and of a number.
        self.assertTrue(self.one({"cards": [1], "include_added_cards": None})[0].include_added)
        self.assertTrue(self.one({"cards": [1], "once": 1})[0].once)
        notes = [m for _, m in packs.check_rules({"music": None, "shops": None, "password": None, "rng": 5})]
        self.assertEqual(len(notes), 4, notes)

    def test_numbers_as_the_game_reads_them(self):
        pack, notes = self.one({"cards": {"1": 2.0}, "price": 100.0, "count": 3.0})
        self.assertEqual((pack.price, pack.count, pack.tiers[0].pool), (100, 3, [(1, 2)]))
        self.assertIsNone(self.one({"cards": [1], "price": True})[0])
        self.assertEqual(packs.password_bits(1234.0), 0x1234)

    def test_keys_and_shops(self):
        self.assertIsNone(packs.KEY_RE.match("abc\n"))
        self.assertIsNone(self.one({"cards": [1], "id": "abc\n"})[0])
        notes = [m for _, m in packs.check_rules({"shops": [{"id": 5}, {"id": "abc\n"}]})]
        self.assertEqual(sum("a shop is {" in m for m in notes), 2)
        notes = [m for _, m in packs.check_rules({"shops": [{"id": f"s{i}"} for i in range(17)] + [{"id": "s0"}]})]
        self.assertEqual(notes, ["pack_shop shop \"s16\": there are 16 shops already, the most there can be; left out"])
        self.assertEqual(packs.shop_ids({"shops": [{"id": f"s{i}"} for i in range(17)]})[-1], "s15")
        self.assertEqual(packs.shop_ids(None), ["main"])
        # "where" of any other kind is said, as the game says it.
        notes = [m for _, m in packs.check_rules({"shops": [{"id": "a", "where": None}]})]
        self.assertTrue(any("only \"where\": \"password\"" in m for m in notes))
        # The shops a pack names, against this mod's.
        for shop, missing in (("main", []), ("*", []), (["main", "x"], ["x"]), ("a,b", ["a", "b"]), ("", []),
                              (["", 5, "main"], [])):
            pack, _ = self.one({"cards": [1], "shop": shop})
            self.assertEqual([m.rsplit(" ", 1)[1].strip("\"") for _, m in packs.shop_notes(pack, None)], missing, shop)
        pack, _ = self.one({"cards": [1], "shop": "black"})
        self.assertEqual(packs.shop_notes(pack, {"shops": [{"id": "black"}]}), [])

    def test_the_readers_other_checks(self):
        # "cost" "cards" is an object; "sounds" too (the game notes it, keeps the pack).
        self.assertIsNone(self.one({"cards": [1], "cost": {"cards": ["x"]}})[0])
        pack, notes = self.one({"cards": [1], "sounds": [1, 2]})
        self.assertTrue(pack and any("\"sounds\" is {" in m for _, m in notes))
        # A description past 255 bytes is cut between two letters.
        pack, notes = self.one({"cards": [1], "description": "x" + "é" * 200})
        self.assertEqual(len(pack.description.encode("utf-8")), 255)
        self.assertTrue(any("room for 255 bytes" in m for _, m in notes))
        # "unique_in_pack" counts fixed cards, and one card fixed twice cannot hold.
        self.assertIsNotNone(self.one({"cards": [1, 2], "slots": ["cards", "cards", {"card": 5}],
                                       "duplicates": "unique_in_pack"})[0])
        self.assertIsNone(self.one({"cards": [1, 5], "slots": ["cards", "cards", {"card": 5}],
                                    "duplicates": "unique_in_pack"})[0])
        pack, errors = self.errors({"cards": [1, 2, 3], "slots": [{"card": 5}, "cards", {"card": 5}],
                                    "duplicates": "unique_in_pack"})
        self.assertIsNone(pack)
        self.assertIn("fixed in slots 1 and 3", errors[0])

    def test_tiers_named_twice(self):
        """The file had a tier twice: Python keeps one, the game sees both and
        leaves the pack out; the editor says so too (manifest.read_json)."""
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mod.json"
            path.write_text('{"packs": [{"tiers": {"a": {"cards": [1]}, "a": {"cards": [2]}}, "price": 5, '
                            '"price": 6}]}', encoding="utf-8")
            entry = manifest.read_json(path)["packs"][0]
        pack, notes = self.one(entry)
        self.assertIsNone(pack)
        text = "\n".join(m for _, m in notes)
        self.assertIn("tier \"a\": named twice", text)
        self.assertIn("\"price\" is written twice", text)

    def test_when_nothing_left(self):
        pack, notes = self.one({"cards": [1, 2], "max_copies": 1})
        self.assertEqual(notes, [])
        self.assertFalse(packs.nothing_left(pack))
        self.assertFalse(packs.nothing_left(pack, lambda c: c == 1))
        self.assertTrue(packs.nothing_left(pack, lambda c: 1))
        self.assertTrue(packs.refuses_when_nothing_left(pack))
        self.assertFalse(packs.refuses_when_nothing_left(pack, {"when_nothing_left": "sell"}))
        pack, _ = self.one({"cards": [1], "max_copies": 1, "when_nothing_left": "refuse"})
        self.assertTrue(packs.refuses_when_nothing_left(pack, {"when_nothing_left": "sell"}))
        # A fixed card is always dealt; no "max_copies", always something.
        pack, _ = self.one({"cards": [1, 2], "slots": ["cards", {"card": 1}], "max_copies": 1})
        self.assertFalse(packs.nothing_left(pack, lambda c: 9))
        self.assertFalse(packs.nothing_left(self.one({"cards": [1]})[0], lambda c: 9))
        pack, notes = self.one({"cards": [1], "when_nothing_left": "give"})
        self.assertIsNone(pack.when_nothing_left)
        self.assertIn("the shop's is used", notes[0][1])
        self.assertIn("\"refuse\" is used", packs.check_rules({"when_nothing_left": 1})[0][1])
        # The pack's word is written even when it is the default: the shop's may differ.
        self.assertEqual(packs.minimize({"name": "A", "cards": [1], "when_nothing_left": "refuse"})["when_nothing_left"],
                         "refuse")
        self.assertIsNone(packs.minimize_rules({"when_nothing_left": "refuse"}))
        self.assertEqual(packs.minimize_rules({"when_nothing_left": "sell"}), {"when_nothing_left": "sell"})

    def test_minimize_keeps_listed_by_a_password_the_game_reads(self):
        entry = {"name": "X", "cards": [1], "password": "12ab", "listed": False}
        self.assertFalse(packs.minimize(entry)["listed"])
        self.assertNotIn("listed", packs.minimize({"name": "X", "cards": [1], "password": "1234", "listed": False}))


class ImageStyleTest(unittest.TestCase):
    def test_image_style(self):
        """As packs.c reads it: "card" unless it says "full"; another word, or
        "full" with no "image", is said."""
        for entry, words in (({"cards": [1], "image_style": "card"}, None),
                             ({"cards": [1], "image": "packs/a.png", "image_style": "full"}, None),
                             ({"cards": [1], "image_style": "full"}, "there is none"),
                             ({"cards": [1], "image_style": "poster"}, "\"image_style\" is \"card\" or \"full\""),
                             ({"cards": [1], "image_styl": "full"}, "did you mean \"image_style\"")):
            pack, notes = packs.read_pack(entry, by_id, "m", 0)
            self.assertIsNotNone(pack, entry)
            said = [m for _, m in notes if "image" in m]
            if words is None:
                self.assertEqual(said, [], entry)
            else:
                self.assertTrue(any(words in m for m in said), (entry, notes))
        self.assertEqual(packs.minimize({"cards": [1], "image_style": "card"}), {"cards": [1]})
        self.assertEqual(packs.minimize({"cards": [1], "image_style": "full"})["image_style"], "full")

    def test_fit_full(self):
        """pack_shop.c fit_picture's sizes."""
        self.assertEqual(packs.fit_full(300, 500), (118, 196))
        self.assertEqual(packs.fit_full(600, 300), (140, 70))
        self.assertEqual(packs.fit_full(140, 196), (140, 196))
        self.assertEqual(packs.fit_full(1, 1000), (2, 196))


class ManifestTest(unittest.TestCase):
    def test_round_trip_writes_only_what_differs(self):
        source = {"packs": [
            {"id": "dragons", "name": "Dragons", "price": 100, "count": 5, "duplicates": "allow",
             "cards": {"1": 1, "2": 1}, "reveal": "flip", "include_added_cards": True, "mine": {"kept": 1},
             "tiers_note": "x", "sounds": {"buy": 48, "move": 3}},
            {"name": "Rares", "tiers": {"common": {"odds": 1, "cards": {"5": 3}}, "rare": {"odds": 2, "cards": [7]}},
             "cost": {"starchips": 250}}],
            "pack_shop": {"password": "both", "rng": "save", "music": 29520}}
        p, messages = read(source)
        self.assertEqual(messages, [])
        self.assertNotIn("packs", p.other)
        out = manifest.build(p)
        self.assertEqual(out["packs"][0], {"name": "Dragons", "cards": ["1", "2"], "mine": {"kept": 1},
                                           "tiers_note": "x", "sounds": {"move": 3}})
        self.assertEqual(out["packs"][1], {"name": "Rares", "tiers": {"common": {"cards": {"5": 3}},
                                                                      "rare": {"odds": 2, "cards": [7]}},
                                           "price": 250})
        self.assertEqual(out["pack_shop"], {"rng": "save"})
        again, _ = read({k: v for k, v in out.items() if k in ("packs", "pack_shop")})
        self.assertEqual(manifest.build(again)["packs"], out["packs"])

    def test_a_packs_file_stays_that_file(self):
        p, messages = read({"packs": "packs.json"})
        self.assertEqual(manifest.build(p)["packs"], "packs.json")
        self.assertTrue(any("kept as written" in m for m in messages))

    def test_no_packs_writes_none(self):
        p, _ = read({})
        out = manifest.build(p)
        self.assertNotIn("packs", out)
        self.assertNotIn("pack_shop", out)

    def test_checks_report_the_readers_words(self):
        p, _ = read({"packs": [{"name": "Ok", "cards": [1, 2]}, {"name": "Bad", "cards": [1], "count": 99},
                               {"name": "Pw", "cards": [3], "password": "00000001"},
                               {"name": "Pw2", "cards": [3], "password": 1}],
                     "pack_shop": {"campaign_shop": True}})
        issues = [i for i in validate.validate(p) if i.area == "Packs"]
        errors = [i for i in issues if i.level == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].target, 1)
        self.assertIn("\"count\" is 1 to 40", errors[0].message)
        text = "\n".join(i.message for i in issues)
        self.assertIn("its password is pack", text)
        self.assertIn("\"campaign_shop\" is not built yet", text)


class SimulateTest(unittest.TestCase):
    def test_distribution_follows_the_odds_and_the_pity_fires(self):
        pack, _ = packs.read_pack({"count": 5, "tiers": {"common": {"odds": 90, "cards": [1, 2, 3]},
                                                         "ultra": {"odds": 10, "cards": [9]}},
                                   "pity": {"ultra": 1}}, by_id)
        result = packs.simulate(pack, 2000, 7)
        self.assertEqual(result.draws, 2000 * 5 * packs.DRAWS_PER_SLOT)
        self.assertEqual(sum(result.tiers.values()), 10000)
        # pity 1: every pack has one ultra at least.
        self.assertGreaterEqual(result.cards[9], 2000)
        self.assertEqual(result.pity_waits["ultra"], 1.0)
        pack, _ = packs.read_pack({"count": 5, "tiers": {"common": {"odds": 90, "cards": [1, 2, 3]},
                                                         "ultra": {"odds": 10, "cards": [9]}}}, by_id)
        share = packs.simulate(pack, 4000, 3).tiers["ultra"] / 20000
        self.assertAlmostEqual(share, 0.10, delta=0.01)
        self.assertAlmostEqual(packs.card_chances(pack)[(1, 9)], 0.10)


if __name__ == "__main__":
    unittest.main()
