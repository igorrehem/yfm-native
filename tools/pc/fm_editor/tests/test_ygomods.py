"""The .ygomods importer on a package written here (synthetic cards)."""
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from fm_editor import art, cli, gamedata as g, manifest, pngio, validate, ygomods
from fm_editor.tests.test_data import fixture, state


def package(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return out.getvalue()


FILES = {
    "manifest.ini": "; test\nformat = YGOFM-MOD-PACKAGE\nversion = 1\ngame = SLUS-01411\n",
    "cards/1/card.ini": "color = pink\nname = Big Dragon\nattack = 2070\nstar1 = Pluto\nstar2 = Uranus\n"
                        "price = 4100\npassword = 70022514\ndescription = Line one|line two\non_flip = raigeki\n",
    "cards/1/art.png": pngio.encode(pngio.Image(102, 96, b"\x10\x20\x30\xff" * (102 * 96))),
    "cards/651/card.ini": "equips = 1, 2, 3\n",
    "cards/681/card.ini": "ritual = 4, 5, 6 -> 7\n",
    "fusion-edits.txt": "# a b result\n1\t2\t9\n2\t1\t0\n5\t6\t7\n",
    "drop_table_edits.ini": "; weights\n[Simon Muran]\n5 = 100, 0, 3\ncard = 92\n[Starchip Reward 1]\nmode = x\n",
    "cpu-duelists.ini": "[Heishin]\nname = Heishin X\nai = 5, 20, 9, 1, 1, 0, 0, 25, 50\n" +
                        "".join(f"{c} = {10 + c}\n" for c in range(1, 16)),
    "duelists/10/portrait.png": b"\x89PNG portrait",
    "dialogue.txt": "[127A]\nhello\n",
    "mod_settings.ini": "card_drops = 15\n",
}


class YgomodsTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.retail = self.f.game()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.ygomods"
        self.path.write_bytes(package(FILES))

    def tearDown(self):
        self.tmp.cleanup()

    def test_import(self):
        project, report = ygomods.import_package(self.retail, self.f.wa, self.path, "pkg")
        text = "\n".join(report)
        card = project.cards[1]
        self.assertEqual((card.name, card.attack, card.star1, card.star2), ("Big Dragon", 2070, 5, 4))
        self.assertEqual(card.description, "Line one\nline two")
        self.assertEqual(project.card_extra[1], {"art": "images/001-art.png"})
        self.assertEqual(project.equips[651], {1, 2, 3})
        self.assertEqual(project.rituals[681], (4, 5, 6, 7))
        self.assertEqual(project.fusions.get((1, 2)), None)          # the later line removes it
        self.assertEqual(project.fusions[(5, 6)], 7)
        self.assertEqual(project.pools[1]["pow"][5], 100)
        self.assertEqual(sum(project.pools[1]["pow"].values()), 2048)
        self.assertEqual(sorted(project.pools[8]["deck"]), list(range(1, 16)))
        self.assertIn(b"[8330]\nHeishin X{end}", project.files["text.txt"])
        entries = json.loads(project.files["textures/manifest.json"])
        self.assertEqual(entries[0]["offset"], 0xF55000 + 10 * 0x980)
        patch = project.other["data"][0]["patch"][0]
        self.assertEqual(patch["at"], f"0x{0xFB9800 + 8:X}")
        self.assertEqual(patch["bytes"], "04 10 00 00 14 25 02 70")
        for what in ("on_flip", "color", "AI profile", "dialogue.txt", "StarChip", "scripted rewards", "mod_settings"):
            self.assertIn(what, text)
        self.assertEqual(validate.errors(validate.validate(project)), [])
        with tempfile.TemporaryDirectory() as out:
            manifest.save_mod(project, out)
            self.assertTrue((Path(out) / "images" / "001-art.png").exists())
            self.assertTrue((Path(out) / "textures" / "portraits" / "freeduel-10.png").exists())
            opened, messages = manifest.open_mod(self.retail, out)
            self.assertEqual(messages, [])
            self.assertEqual(state(opened), state(project))

    def test_portraits_kept_with_new_art(self):
        """The package's portraits share the texture pack with the Art tab's
        pictures: both stay through two saves."""
        project, _ = ygomods.import_package(self.retail, self.f.wa, self.path, "pkg")
        art.set_image(project, 2, "art", pngio.Image(102, 96, b"\x40\x50\x60\xff" * (102 * 96)))
        with tempfile.TemporaryDirectory() as out:
            for _ in range(2):
                manifest.save_mod(project, out)
                entries = json.loads((Path(out) / "textures" / "manifest.json").read_text(encoding="utf-8"))
                self.assertIn(0xF55000 + 10 * 0x980, [e["offset"] for e in entries])
                self.assertIn((2, "art"), [art.entry_card(e) for e in entries])

    def test_thumbnail_keeps_imported_art(self):
        """The package's card art is the Art tab's: a thumbnail imported
        after it moves it to the pack instead of dropping it."""
        project, _ = ygomods.import_package(self.retail, self.f.wa, self.path, "pkg")
        imported = pngio.decode(project.files["images/001-art.png"])
        self.assertEqual(art.shown_image(project, self.f.wa, 1, "art")[1], "the mod")
        art.set_image(project, 1, "thumbnail", pngio.Image(40, 32, b"\x10\x20\x30\xff" * (40 * 32)))
        with tempfile.TemporaryDirectory() as out:
            manifest.save_mod(project, out)
            entries = json.loads((Path(out) / "textures" / "manifest.json").read_text(encoding="utf-8"))
            files = {art.entry_card(e): e["file"] for e in entries if art.entry_card(e)}
            self.assertEqual(pngio.read(Path(out) / "textures" / files[(1, "art")]), art.normalize(imported, "art")[0])
            written = json.loads((Path(out) / "mod.json").read_text(encoding="utf-8"))
            self.assertNotIn("art", next(e for e in written["cards"] if e.get("replace") == 1))

    def write(self, files: dict) -> Path:
        path = Path(self.tmp.name) / "case.ygomods"
        path.write_bytes(package({"manifest.ini": "format = YGOFM-MOD-PACKAGE\n", **files}))
        return path

    def test_zero_padded_folders(self):
        # "duelists/007/" once reached save_mod as None (TypeError).
        path = self.write({"duelists/007/portrait.png": b"\x89PNG seven", "cards/005/card.ini": "attack = 1230\n"})
        project, _ = ygomods.import_package(self.retail, self.f.wa, path, "pad")
        self.assertEqual(project.files["textures/portraits/freeduel-07.png"], b"\x89PNG seven")
        self.assertEqual(project.cards[5].attack, 1230)
        with tempfile.TemporaryDirectory() as out:
            manifest.save_mod(project, out)
            self.assertTrue((Path(out) / "textures" / "portraits" / "freeduel-07.png").exists())

    def test_out_of_range_values(self):
        ritual = next(c for c, card in self.retail.cards.items() if card.type == g.TYPE_RITUAL)
        equip = next(c for c, card in self.retail.cards.items() if card.type == g.TYPE_EQUIP)
        path = self.write({
            "cards/5/card.ini": "type = 99\nattack = 99999\nlevel = 200\nprice = -5\nequips = 1, 2\n"
                                "ritual = 1, 2, 3 -> 4\n",
            f"cards/{ritual}/card.ini": "ritual = 9999, 0, 5 -> 70000\n",
            f"cards/{equip}/card.ini": "equips = 1, 99999\n",
            "cards/6/card.ini": "price = 5000000\n",
            "drop_table_edits.ini": "[Simon Muran]\n5 = -100, 99999, 3\npow_table = 5:-10, 6:100\n",
            "cpu-duelists.ini": "[Heishin]\n" + "".join(f"{c} = -{c}\n" for c in range(1, 30)),
        })
        project, report = ygomods.import_package(self.retail, self.f.wa, path, "range")
        text = "\n".join(report)
        retail5 = self.retail.cards[5]
        card = project.cards[5]
        self.assertEqual((card.type, card.attack, card.level), (retail5.type, retail5.attack, retail5.level))
        self.assertNotIn(5, project.rituals)
        self.assertEqual(project.rituals.get(ritual), self.retail.rituals.get(ritual))
        self.assertEqual(project.equips.get(equip), {1})
        self.assertEqual(project.pools[1]["pow"], {6: 2048})          # pow_table: the negative weight left out
        self.assertEqual(project.pools[8]["deck"], self.retail.pools[8]["deck"])   # no deck of negative counts
        costs = {p["at"]: p["bytes"] for p in project.other["data"][0]["patch"]}
        self.assertEqual(costs.get(f"0x{0xFB9800 + 8 * 5:X}", "00 00 00 00")[:11], "00 00 00 00")   # patched or already 0
        self.assertEqual(costs[f"0x{0xFB9800 + 8 * 6:X}"][:11], "3F 42 0F 00")     # 999999
        for what in ("out of range", "not equip cards", "not ritual cards", "no card of the disc", "prices outside"):
            self.assertIn(what, text)
        self.assertEqual(validate.errors(validate.validate(project)), [])

    def test_unreadable_entry(self):
        path = self.write({"cards/5/card.ini": "attack = 1230\n" * 50})
        blob = bytearray(path.read_bytes())
        at = blob.find(b"attack = 1230")
        blob[at] ^= 0xFF                                            # a bad CRC
        path.write_bytes(bytes(blob))
        with self.assertRaises(ygomods.PackageError):
            ygomods.import_package(self.retail, self.f.wa, path, "crc")

    def test_closed_when_refused(self):
        bad = self.write({"manifest.ini": "format = OTHER\n"})
        close = zipfile.ZipFile.close
        with mock.patch.object(zipfile.ZipFile, "close", autospec=True, side_effect=close) as closed:
            with self.assertRaises(ygomods.PackageError):
                ygomods.Package(bad)
        self.assertEqual(closed.call_count, 1)

    def test_command_line_import(self):
        game = Path(self.tmp.name) / "game"
        (game / "DATA").mkdir(parents=True)
        (game / "SLUS_014.11").write_bytes(self.f.slus)
        (game / "DATA" / "WA_MRG.MRG").write_bytes(self.f.wa)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["import", str(self.path), "-o", str(Path(self.tmp.name) / "mod"), "--game", str(game)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue((Path(self.tmp.name) / "mod" / "mod.json").exists())
        self.assertIn("fusions:", out.getvalue())
        bad = self.write({"manifest.ini": "format = OTHER\n"})
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit):
            cli.main(["import", str(bad), "-o", str(Path(self.tmp.name) / "bad"), "--game", str(game)])

    def test_not_a_package(self):
        bad = Path(self.tmp.name) / "bad.ygomods"
        bad.write_bytes(package({"manifest.ini": "format = OTHER\n"}))
        with self.assertRaises(ygomods.PackageError):
            ygomods.import_package(self.retail, self.f.wa, bad)
        bad.write_bytes(b"not a zip")
        with self.assertRaises(ygomods.PackageError):
            ygomods.import_package(self.retail, self.f.wa, bad)


if __name__ == "__main__":
    unittest.main()
