"""The card view preview (card_view.py): the listing's strings, the text's
cursor, the European spacing, and, with the game files, the panel."""
import unittest
from pathlib import Path

from fm_editor import card_view, card_text, glyph_cells
from fm_editor.tests.test_card_text import synthetic_wa

GAME = Path(__file__).resolve().parents[4] / "game"


class ListingTest(unittest.TestCase):
    def test_cont_jump_and_names(self):
        listing = card_view.Listing(
            "@bank dialog\n"
            "[0003]  {:LF004}\n"
            "{f8 04 02}{f8 00 00}{f8 01 18}{f8 0A 05}SCHUTZSTERN\n"
            "{f8 0A 00} {f8 00 01}{cont}\n"
            "{:LF005}\n"
            "{f8 05 08 0C}{f8 00 40}{end}\n"
            "\n"
            "[0004]  {:LF006}\n"
            "{f8 00 00}{f8 01 50}{jump LF005}\n"
            "@bank names\n"
            "[8300 8322]\n"
            "Drache{end}\n")
        self.assertEqual(listing.text(0x8300), "Drache")
        self.assertEqual(listing.text(0x8322), "Drache")
        three = listing.tokens(3)
        self.assertIn(("nl",), three)
        self.assertEqual(three[-1], ("code", ["f8", "00", "40"]))       # on through {cont} into LF005
        self.assertEqual(listing.tokens(4)[-1], ("code", ["f8", "00", "40"]))   # by the jump
        self.assertIsNone(listing.tokens(5))

    def test_pal_spacing(self):
        self.assertEqual(card_view.pal_advance(" "), (-1, 0))
        self.assertEqual(card_view.pal_advance("'"), (-6, -3))
        self.assertEqual(card_view.pal_advance("i"), (-2, -1))
        self.assertEqual(card_view.pal_advance("A"), (0, 0))


class DrawingTest(unittest.TestCase):
    def setUp(self):
        self.retail = card_text.RetailFont(synthetic_wa())

    def drawing(self, european=False):
        return card_view.Drawing(bytearray(card_view.flat_panel()), self.retail,
                                 glyph_cells.GlyphCells(self.retail, european=european), european)

    def test_cursor(self):
        d = self.drawing()
        d.run(card_view.text_tokens("AA\nA{f8 01 10}A{f8 02 04}A"))
        self.assertEqual((d.x, d.y), (8 + 4 + 8, 12 + 16))
        # A line wraps once x reaches the box's 168; no row past 192 - 12.
        d = self.drawing()
        d.run(card_view.text_tokens("A" * 22))
        self.assertEqual((d.x, d.y), (8, 12))
        d.run(card_view.text_tokens("\n" * 20))
        self.assertTrue(d.done)
        # European: the space 7, f/i/l 6.
        d = self.drawing(european=True)
        d.run(card_view.text_tokens("A il"))
        self.assertEqual(d.x, 8 + 7 + 6 + 6)

    def test_first_drawn_stays_on_top(self):
        d = self.drawing()
        d.letters[(10, 10)] = (1, 2, 3)
        d.letters.setdefault((10, 10), (9, 9, 9))
        d.finish()
        at = (10 * card_view.WIDTH + 10) * 4
        self.assertEqual(tuple(d.rgba[at:at + 3]), (1, 2, 3))


@unittest.skipUnless((GAME / "SLUS_014.11").is_file() and (GAME / "DATA" / "WA_MRG.MRG").is_file(),
                     "needs the game files in game/")
class GameFilesTest(unittest.TestCase):
    def test_panel_and_names(self):
        view = card_view.CardView((GAME / "SLUS_014.11").read_bytes(), (GAME / "DATA" / "WA_MRG.MRG").read_bytes())
        self.assertIsNotNone(card_view.panel_picture(view.slus, (GAME / "DATA" / "WA_MRG.MRG").read_bytes()))
        names = "".join(t[1] for t in view.name(4, "en-us") if t[0] == "char")
        self.assertEqual(names.strip(), "BeastWarrior")
        image = view.render(4, 9, 1, "Hello {f8 0B 00}", scale=2)
        self.assertEqual((image.width, image.height), (2 * card_view.WIDTH, 2 * card_view.HEIGHT))
        # The stone's dark blue inside the description box, the frame's tan on its edge.
        self.assertEqual(view.render(4, 9, 1, "").pixel(100, 180)[2] > 40, True)


@unittest.skipUnless((GAME / "DATA" / "WA_MRG.MRG").is_file(), "needs the game files in game/")
class CardIconsTest(unittest.TestCase):
    def test_pictures_off_the_disc(self):
        from fm_editor import card_icons
        wa = (GAME / "DATA" / "WA_MRG.MRG").read_bytes()
        balls = [card_icons.attribute(wa, n) for n in range(8)]
        self.assertTrue(all(b is not None and (b.width, b.height) == (16, 16) for b in balls))
        # Light's middle is gold, Water's blue, Fire's red, Wind's green.
        r, g, b, _ = balls[0].pixel(8, 8)
        self.assertTrue(r > b and g > b)
        self.assertGreater(balls[3].pixel(8, 8)[2], balls[3].pixel(8, 8)[0])
        self.assertGreater(balls[4].pixel(8, 8)[0], balls[4].pixel(8, 8)[2])
        self.assertGreater(balls[5].pixel(8, 8)[1], balls[5].pixel(8, 8)[0])
        self.assertEqual((card_icons.level_star(wa).width, card_icons.sword(wa).width, card_icons.shield(wa).width),
                         (9, 8, 8))
        self.assertIsNone(card_icons.attribute(b"", 0))
