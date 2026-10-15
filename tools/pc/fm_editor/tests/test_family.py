"""The importer on synthetic mods made the way a community MIPS patch kit
makes them: the archive changed all
over, tables in other formats, and code whose shape says what the mod does.
No byte of the game is in here: the "code" is assembled from the fixture's
made-up values."""
import struct
import tempfile
import unittest
from pathlib import Path

from fm_editor import compat, gamedata as g, importer, kit, manifest
from fm_editor.disc import GameFiles
from fm_editor.tests import fixtures
from fm_editor.tests.test_data import fixture


def imported(f, slus=None, wa=None):
    result = importer.import_modded(GameFiles(f.slus, f.wa, "retail"),
                                    GameFiles(slus or f.slus, wa or f.wa, "modded", 9173), "family")
    return result, "\n".join(result.report)


class ArchiveTest(unittest.TestCase):
    def test_many_changes_replace_the_whole_file(self):
        f = fixture()
        wa = bytearray(f.wa)
        for k in range(importer.WA_PATCHES_MOST + 1):             # small changes all over the pictures
            wa[0x169000 + 0x1000 * k] ^= 0x5A
        equip = g.TERRAIN_BASE + g.EQUIP_OFFSET
        wa[equip:equip + 8] = b"\x99" * 8                          # a table in a format mod.json carries otherwise
        starters = bytearray(g.STARTER_LENGTH)                     # starter decks as counts of 40
        for k in range(7):
            struct.pack_into("<H", starters, k * (g.STARTER_LENGTH // 7) + 2 + 2 * 4, 40)
        wa[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH] = starters
        result, report = imported(f, wa=bytes(wa))
        built = manifest.build(result.project)
        self.assertEqual(built["data"], [{"file": importer.WA_FILE, "replace": "WA_MRG.MRG"}])
        whole = result.project.files["WA_MRG.MRG"]
        self.assertEqual(len(whole), len(f.wa))
        self.assertEqual(whole[0x169000], wa[0x169000])            # the mod's bytes
        self.assertEqual(whole[equip:equip + 8], f.wa[equip:equip + 8])      # the table as retail's
        self.assertEqual(whole[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH],
                         f.wa[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH])
        self.assertIn("the whole file is replaced", report)
        self.assertIn("the starter decks are counts of cards", report)

    def test_a_larger_archive_keeps_the_tables_retail(self):
        f = fixture()
        wa = bytearray(f.wa) + bytes(4096)
        pool = g.DUELIST_BASE + 3 * g.DUELIST_STRIDE
        wa[pool:pool + 4] = b"\x01\x00\x02\x00"
        result, report = imported(f, wa=bytes(wa))
        whole = result.project.files["WA_MRG.MRG"]
        self.assertEqual(len(whole), len(wa))
        self.assertEqual(whole[pool:pool + 4], f.wa[pool:pool + 4])
        self.assertIn("its size differs", report)

    def test_the_programs_the_port_runs_stay_retail(self):
        f = fixture()
        wa = bytearray(f.wa)
        sector, sectors, what = g.PROGRAMS[0]
        wa[sector * 2048 + 100] ^= 0xFF                       # the mod's code in a program the port runs itself
        wa[0x300] = 9
        result, report = imported(f, wa=bytes(wa))
        data = manifest.build(result.project)["data"]
        self.assertEqual(data, [{"file": importer.WA_FILE, "patch": [{"at": "0x300", "bytes": "09"}]}])
        self.assertIn(f"{what} (sector {sector}) differs in 1 bytes", report)

    def test_few_changes_stay_patches_at_retail_sectors(self):
        f = fixture()
        wa = bytearray(f.wa)
        wa[0x200] = 1
        wa[0x169000:0x169000 + 5000] = bytes([7]) * 5000
        wa[0x169000 + 6000:0x169000 + 11000] = bytes([8]) * 5000   # the same or the next sectors: one region
        result, report = imported(f, wa=bytes(wa))
        data = manifest.build(result.project)["data"]
        self.assertEqual(data[0]["patch"], [{"at": "0x200", "bytes": "01"}])
        self.assertEqual(data[1:], [{"lba": 10102 + 0x169000 // 2048, "sectors": 6, "replace": "data/wa_002D2.bin"}])


def bitmap_record(key: int, ids) -> bytes:
    bits = bytearray(92)
    for m in ids:
        bits[m >> 3] |= 0x80 >> (m & 7)
    bits[91] = 0xFF                          # past the last card: the kit's padding, ignored
    return struct.pack("<H", key) + bytes(bits)


def with_equip_table(f, records: bytes) -> bytearray:
    wa = bytearray(f.wa)
    for k in range(g.TERRAIN_COPIES):
        at = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE + g.EQUIP_OFFSET
        wa[at:at + g.EQUIP_LENGTH] = records.ljust(g.EQUIP_LENGTH, b"\0")
    return wa


EQUIP_LO = kit.EQUIP_ADDRESS - 0x80180000     # the low half, as addiu adds it to lui 0x8018


class EquipTest(unittest.TestCase):
    def test_bitmaps_read_up_to_id_0(self):
        """One shape: Duel_CheckEquip itself steps 94 bytes."""
        f = fixture()
        slus = bytearray(f.slus)
        fixtures.put(slus, kit.CHECK_EQUIP, fixtures.asm(kit.CHECK_EQUIP, [
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", EQUIP_LO), ("lhu", "v1", 0, "v0"),
            ("bne", "v1", "zero", kit.CHECK_EQUIP + 0x1C), ("addiu", "a2", "v0", 2), ("jr", "ra"), ("nop",),
            ("bne", "v1", "a0", kit.CHECK_EQUIP + 8), ("addiu", "v0", "v0", 94), ("srl", "v1", "a1", 3),
            ("addu", "v1", "v1", "a2"), ("lbu", "v1", 0, "v1"), ("srlv", "v1", "v1", "v0"), ("jr", "ra"), ("nop",)]))
        wa = with_equip_table(f, bitmap_record(651, [1, 2, 3]) + bitmap_record(652, [9]) +
                              bitmap_record(10, [7]) + bitmap_record(0, []) + bitmap_record(653, [4]))
        result, report = imported(f, bytes(slus), bytes(wa))
        equips = result.project.equips
        self.assertEqual(equips[651], {1, 2, 3})
        self.assertEqual(equips[652], {9})
        self.assertEqual(equips[653], set())              # past id 0: the game never reads it
        self.assertNotIn(10, equips)
        self.assertIn("reads its table as bitmaps of 94 bytes", report)
        self.assertIn("1 records are for cards that are not equip cards (10 Card 10)", report)
        built = manifest.build(result.project)["equips"]
        self.assertIn({"card": "Card 653", "replace": True, "add": []}, built)
        # The archive's table itself stays retail's: the rules say it all.
        self.assertNotIn("data", manifest.build(result.project))

    def test_an_equip_the_mod_made_a_monster_is_left_alone(self):
        f = fixture()
        cards = {cid: card.copy() for cid, card in f.cards.items()}
        cards[653].type = 3                           # a Warrior now: the port would refuse an equips entry
        slus = bytearray(fixtures.make_slus(cards, f.other_names))
        fixtures.put(slus, kit.CHECK_EQUIP, fixtures.asm(kit.CHECK_EQUIP, [
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", EQUIP_LO), ("lhu", "v1", 0, "v0"),
            ("addiu", "v0", "v0", 94), ("srlv", "v1", "v1", "v0"), ("jr", "ra"), ("nop",)]))
        wa = with_equip_table(f, bitmap_record(651, [1]))
        result, report = imported(f, bytes(slus), bytes(wa))
        built = manifest.build(result.project)["equips"]
        self.assertFalse([e for e in built if e["card"] == "Card 653"])

    def test_bitmaps_with_monster_records_and_blocked_monsters(self):
        """Another shape: a jump to the mod's code, a count of
        records, records per monster after them and a list of monsters no
        equip takes."""
        f = fixture()
        slus = bytearray(f.slus)
        code = 0x8000B200
        fixtures.put(slus, kit.CHECK_EQUIP, fixtures.asm(kit.CHECK_EQUIP, [
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", EQUIP_LO), ("li", "a2", 0), ("j", code), ("lui", "a3", 0x801D)]))
        second = EQUIP_LO + 3 * 94
        fixtures.put(slus, code, fixtures.asm(code, [
            ("lhu", "a3", 0x197C, "a3"), ("srl", "a3", "a3", 4), ("beq", "a3", "a1", code + 0x60),
            ("lui", "a3", 0x801D), ("lhu", "a3", 0x197E, "a3"), ("srl", "a3", "a3", 4),
            ("lhu", "v1", 0, "v0"), ("beq", "v1", "a0", code + 0x70), ("addiu", "a2", "a2", 1),
            ("slti", "a3", "a2", 3), ("bne", "a3", "zero", code + 0x18), ("addiu", "v0", "v0", 94),
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", second), ("lhu", "v1", 0, "v0"), ("li", "a2", 0),
            ("addiu", "a2", "a2", 1), ("slti", "a3", "a2", 2), ("addiu", "v0", "v0", 94),
            ("srlv", "v1", "v1", "a3"), ("jr", "ra"), ("nop",)]))
        fixtures.put(slus, 0x801D197C, struct.pack("<HH", (2 << 4) | 1, 723 << 4))
        wa = with_equip_table(f, bitmap_record(651, [1, 2, 3]) + bitmap_record(652, [5]) + bitmap_record(10, [7]) +
                              bitmap_record(20, [653, 651]) + bitmap_record(21, [654]))
        result, report = imported(f, bytes(slus), bytes(wa))
        equips = result.project.equips
        self.assertEqual(equips[651], {1, 3})             # 2 is turned away; 20's record is not asked for 651
        self.assertEqual(equips[652], {5})
        self.assertEqual(equips[653], {20})               # in no record of its own: the monsters' records
        self.assertEqual(equips[654], {21})
        self.assertIn("2 records name a monster and the equips it takes", report)
        self.assertIn("no equip equips 2 Mystic Elf", report)

    def test_rituals_that_are_code_are_removed(self):
        f = fixture()
        wa = bytearray(f.wa)
        for k in range(g.TERRAIN_COPIES):
            at = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE + g.RITUAL_OFFSET
            wa[at:at + 20] = struct.pack("<10H", 0x2402, 0x27BD, 0xFFE8, 0xAFBF, 0x0010, 0x0C00, 0x1234, 0, 0, 0)
        result, report = imported(f, wa=bytes(wa))
        self.assertEqual(result.project.rituals, {})
        self.assertIn({"card": "Card 681", "result": None}, manifest.build(result.project)["rituals"])
        self.assertIn("the rituals were imported as removed", report)
        # A ritual the mod made a monster: no rule names it (the port would refuse one).
        cards = {cid: card.copy() for cid, card in f.cards.items()}
        cards[682].type = 3
        result, report = imported(f, slus=fixtures.make_slus(cards, f.other_names), wa=bytes(wa))
        self.assertEqual(manifest.build(result.project)["rituals"], [{"card": "Card 681", "result": None}])
        # Code whose bytes happen to spell one recipe among the rest: still code.
        for k in range(g.TERRAIN_COPIES):
            at = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE + g.RITUAL_OFFSET
            wa[at:at + 30] = struct.pack("<15H", 0x2402, 0x27BD, 0xFFE8, 0xAFBF, 0x0010,
                                         681, 1, 2, 3, 500, 0x0C00, 0x1234, 0x8000, 0x9000, 0xA000)
        result, report = imported(f, wa=bytes(wa))
        self.assertEqual(result.project.rituals, {})


def put_text(slus: bytearray, table_entry: int, bank: int, address: int, data: bytes):
    """A string's bytes at `address`, and the u16 offset entry pointing at it."""
    fixtures.put(slus, address, data)
    struct.pack_into("<H", slus, g.slus_offset(table_entry), address - bank)


class TextTest(unittest.TestCase):
    def test_colored_names_and_empty_texts_go_to_the_text_file(self):
        f = fixture()
        codes = fixtures.glyph_codes()
        slus = bytearray(f.slus)
        put_text(slus, g.NAME_TABLE + 6 * 2, g.NAME_BANK, 0x801DF000,
                 b"\xF8\x0A\x05" + fixtures.encode_text("Dark Card", codes))           # a colored name
        put_text(slus, g.NAME_TABLE + 9 * 2, g.NAME_BANK, 0x801DF100, fixtures.encode_text("Plain New", codes))
        put_text(slus, g.STRING_TABLE + (0x100 + 7) * 2, g.DESCRIPTION_BANK, 0x801CF000, b"\xFF")   # empty
        put_text(slus, g.STRING_TABLE + (0x100 + 8) * 2, g.DESCRIPTION_BANK, 0x801CF010,
                 b"\xF8\x0A\x05" + fixtures.encode_text("Effect", codes)[:-1] + b"\xF8\x0A\x00\xFE" +
                 fixtures.encode_text("Burns", codes))
        result, report = imported(f, slus=bytes(slus))
        project = result.project
        self.assertEqual(project.cards[6].name, "Dark Card")
        self.assertEqual(project.cards[7].description, "")
        self.assertEqual(project.cards[8].description, "{f8 0A 05}Effect{f8 0A 00}\nBurns")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "family"
            importer.save(result, folder)
            built = manifest.read_json(folder / "mod.json")
            entries = {e["replace"]: e for e in built["cards"]}
            self.assertNotIn(6, entries)                                  # the text file has it, color and all
            self.assertEqual(entries[9], {"replace": 9, "name": "Plain New"})
            self.assertNotIn(7, entries)
            self.assertNotIn(8, entries)
            text = (folder / "text.txt").read_text(encoding="utf-8")
            self.assertIn("[8006]\n{f8 0A 05}Dark Card{end}", text)
            self.assertIn("[D107]", text)
            self.assertIn("{f8 0A 05}Effect{f8 0A 00}", text)
            self.assertNotIn("Plain New", text)
            # Opened again, the editor shows them and writes the same mod.json.
            opened, messages = manifest.open_mod(f.game(), folder)
            self.assertEqual(opened.cards[6].name, "Dark Card")
            self.assertEqual(opened.cards[8].description, project.cards[8].description)
            self.assertEqual(manifest.build(opened)["cards"], built["cards"])
            opened.cards[6].name = "Darker Card"                          # an edit goes to cards[] again
            self.assertIn({"replace": 6, "name": "Darker Card"}, manifest.build(opened)["cards"])
        self.assertIn("carry color or icon codes or are empty on purpose (1 empty)", report)

    def test_the_name_entry_strings_stay_retail(self):
        f = fixture()
        codes = fixtures.glyph_codes()
        slus = bytearray(f.slus)
        dialog = 0x801B0000
        put_text(slus, g.STRING_TABLE + 0x10 * 2, dialog, dialog + 0x100, fixtures.encode_text("Hello", codes))
        put_text(slus, g.STRING_TABLE + 0xF5 * 2, dialog, dialog + 0x200, fixtures.encode_text("Pick a deck", codes))
        result, report = imported(f, slus=bytes(slus))
        text = result.project.files["text.txt"].decode("utf-8")
        self.assertIn("[0010]\nHello{end}", text)
        self.assertNotIn("Pick a deck", text)
        self.assertIn("the name entry's strings [00F5] stay retail's", report)

    def test_texts_kept_in_the_archive(self):
        """Texts kept in the archive: the string table points descriptions 1-8
        at slots of 0x100 and the texts are past the archive's retail end."""
        f = fixture()
        codes = fixtures.glyph_codes()
        slus = bytearray(f.slus)
        for k in range(8):
            struct.pack_into("<H", slus, g.slus_offset(g.STRING_TABLE + (0x101 + k) * 2), 0xA00 + 0x100 * k)
        fixtures.put(slus, 0x801C0A00, bytes(range(0x20, 0x40)) * 8)   # what the mod keeps there instead: code
        wa = bytearray(f.wa).ljust(g.WA_TEXT_BASE, b"\0")
        for cid in range(1, g.CARD_COUNT + 1):
            text = fixtures.encode_text(f"Kept {cid}", codes) if cid != 9 else \
                b"\xF8\x0A\x05" + fixtures.encode_text("Union", codes)
            wa += text.ljust(g.WA_TEXT_SLOT, b"\0")
        result, report = imported(f, bytes(slus), bytes(wa))
        project = result.project
        self.assertEqual(project.cards[5].description, "Kept 5")
        self.assertEqual(project.cards[9].description, "{f8 0A 05}Union")
        self.assertIn("the card texts are in WA_MRG.MRG", report)
        self.assertEqual(result.project.text_cards[9], {"description": "{f8 0A 05}Union"})
        self.assertIn("[D109]", result.project.files["text.txt"].decode("utf-8"))


class DeckAndDropTest(unittest.TestCase):
    def test_decks_dealt_by_count_are_fixed(self):
        f = fixture()
        slus = bytearray(f.slus)
        start = kit.SHUFFLE_DECK[0]
        fixtures.put(slus, start, fixtures.asm(start, [
            ("lhu", "v0", 0, "v1"), ("beq", "v0", "zero", start + 0x68), ("addiu", "s3", "s3", 1),
            ("slti", "v0", "s3", 40), ("bne", "v0", "zero", start + 8), ("nop",)]))
        pools = [{p: dict(v) for p, v in d.items()} for d in f.pools]
        pools[3]["deck"] = {5: 30, 6: 10}
        pools[5]["deck"] = {7: 2}                                  # too few: the shuffle would never end
        wa = fixtures.make_wa(f.fusions, f.equips, f.rituals, pools)
        result, report = imported(f, bytes(slus), wa)
        project = result.project
        decks = manifest.build(project)["decks"]
        self.assertEqual(decks["Jono"], {"fixed": True, "Card 5": 30, "Card 6": 10})
        first = sorted(f.pools[4]["deck"])                         # 2048 weights: the first cards up to 40
        self.assertEqual(decks["Villager 1"], {"fixed": True, str(project.ref(first[0])): 40})   # weights of 100+
        self.assertNotIn("Villager 2", decks)
        self.assertEqual(project.pools[3]["deck"], f.pools[3]["deck"])
        self.assertNotIn("scaled", report)
        self.assertIn("pools hold fewer than 40 cards (Villager 2)", report)
        from fm_editor.model import Project
        again = Project(f.game())                                  # read back, kept as written
        manifest.apply(again, manifest.build(project))
        self.assertEqual(manifest.build(again)["decks"], decks)

    def test_extra_draws_decoding_the_weights(self):
        from fm_editor.tests.test_importer import encoded_mod
        f, files, pools = encoded_mod(2512, 3, code=False)
        slus = bytearray(files.slus)
        loop, decode = 0x8000B300, 0x8000B380
        fixtures.put(slus, kit.RESULT_DRAW, fixtures.asm(kit.RESULT_DRAW, [("j", loop)]))
        fixtures.put(slus, loop, fixtures.asm(loop, [
            ("lui", "sp", 0x8001), ("lbu", "s6", -0x4C00, "sp"), ("lbu", "s7", -0x4BFF, "sp"),
            ("jal", decode), ("nop",), ("jr", "ra")]))
        fixtures.put(slus, decode, fixtures.asm(decode, [("addiu", "v0", "v0", -2512), ("sra", "v0", "v0", 3),
                                                         ("jr", "ra")]))
        fixtures.put(slus, 0x8000B400, bytes([0, 6]))
        result, report = imported(f, bytes(slus), files.wa)
        self.assertEqual(result.project.pools, pools)
        self.assertIn("the prize draw at 0x80021C6C jumps to the mod's code at 0x8000B300, which calls 0x8000B380", report)
        self.assertEqual(kit.extra_draws(f.slus, bytes(slus)).count, 5)
        # Five cards a win: the mod's "limits" "card_drops", which locks
        # Game > Card drops while it is applied (API 13).
        built = manifest.build(result.project)
        self.assertEqual(built["limits"], {"card_drops": 5})
        self.assertIn("\"limits\" \"card_drops\" 5, which locks Game > Card drops", report)
        self.assertEqual(compat.required(built)[0], 13)


class RulesTest(unittest.TestCase):
    def kit_mod(self):
        """The fixture with the kit's rules in made-up code and values."""
        f = fixture()
        slus = bytearray(f.slus)
        chest = 0x8000B100
        fixtures.put(slus, kit.AWARD_CARD, fixtures.asm(kit.AWARD_CARD, [("j", chest)]))
        fixtures.put(slus, chest, fixtures.asm(chest, [
            ("sltiu", "t3", "v0", 8), ("bne", "t3", "zero", chest + 0x30), ("nop",), ("addiu", "v0", "v0", -1),
            ("lui", "t4", 0x801D), ("addiu", "t4", "t4", 0x7E0), ("lw", "t5", 0, "t4"), ("addiu", "t5", "t5", 2),
            ("lui", "t3", 0xF), ("ori", "t3", "t3", 0x423F), ("jr", "ra"), ("nop",)]))
        trap = 0x8000B200
        fixtures.put(slus, kit.ATTACK_TRAP, fixtures.asm(kit.ATTACK_TRAP, [("j", trap)]))
        fixtures.put(slus, kit.TRAP_THRESHOLDS, struct.pack("<6H", 4, 8, 15, 20, 30, 300))
        boost = bytearray(fixtures.make_slus(f.cards)[g.slus_offset(kit.TERRAIN_BOOST):g.slus_offset(kit.TERRAIN_BOOST) + 120])
        boost[3 * 6 + 0] = 30                    # Warrior on the Forest: +300
        boost[19 * 6 + 5] = (-80) & 0xFF         # Plant on Yami: -800
        fixtures.put(slus, kit.TERRAIN_BOOST, bytes(boost))
        place = 0x8000B300
        start = kit.EQUIP_BONUS_SITE[0]
        fixtures.put(slus, start + 0x3C, fixtures.asm(start + 0x3C, [("j", place)]))
        table = 0x8000B600
        fixtures.put(slus, place, fixtures.asm(place, [
            ("li", "a2", 0), ("lui", "t0", 0x8001), ("addu", "t0", "t0", "a2"), ("lhu", "t0", table - 0x80010000, "t0"),
            ("beq", "a3", "t0", place + 0x24), ("nop",), ("addiu", "a2", "a2", 2), ("slti", "t0", "a2", 8),
            ("nop",), ("slti", "a1", "a2", 4), ("bne", "a1", "zero", place + 0x40), ("li", "v1", 700),
            ("slti", "a1", "a2", 8), ("bne", "a1", "zero", place + 0x40), ("li", "v1", 1500), ("nop",),
            ("li", "t0", 657), ("beq", "a3", "t0", place + 0x60), ("jr", "ra"), ("nop",)]))
        fixtures.put(slus, table, struct.pack("<4H", 651, 5, 652, 723))
        return f, bytes(slus)

    def test_the_kits_rules(self):
        f, slus = self.kit_mod()
        result, report = imported(f, slus=slus)
        built = manifest.build(result.project)
        self.assertEqual(built["chest_overflow"], {"limit": 7, "starchips": 2})
        self.assertEqual(built["trap_thresholds"]["House of Adhesive Tape"], 400)
        self.assertEqual(built["trap_thresholds"]["Widespread Ruin"], 30000)
        terrain = built["terrain_bonus"]
        self.assertEqual(terrain["Forest"]["Warrior"], 300)
        self.assertEqual(terrain["Yami"]["Plant"], -800)
        self.assertTrue(terrain["replace"])
        equips = {e["card"]: e for e in built["equips"]}
        self.assertEqual(equips["Card 651"], {"card": "Card 651", "bonus": 700})
        self.assertEqual(equips["Card 652"]["bonus"], 1500)
        self.assertIn("bonuses the mod gives cards that are not equip cards (5 Card 5)", report)
        self.assertIn("Card 657", report)                            # a card with code of its own
        readme = result.project.files["README.txt"].decode("utf-8")
        self.assertIn("The chest keeps 7 copies", readme)
        # Read back, the editor keeps the rules and the bonuses.
        from fm_editor.model import Project
        again = Project(f.game())
        manifest.apply(again, built)
        self.assertEqual(manifest.build(again), built)


    def test_reads_past_the_executable_end(self):
        """A table the mod's code points at the executable's last bytes, or
        an executable cut off before the thresholds: the readers say None or
        skip the entry (a TypeError and a struct.error before)."""
        f = fixture()
        slus = bytearray(f.slus)
        last = len(slus) + g.EXE_DELTA - 2          # the image's last u16: an id with no points after it
        struct.pack_into("<H", slus, len(slus) - 2, 651)
        place = 0x8000B300
        start = kit.EQUIP_BONUS_SITE[0]
        fixtures.put(slus, start, fixtures.asm(start, [("j", place)]))
        high, low = (last + 0x8000) >> 16, last & 0xFFFF
        for selector in ("lh", "scaled"):
            code = [("lui", "t0", high), ("addiu", "t0", "t0", low - 0x10000 if low & 0x8000 else low),
                    ("lhu", "t1", 0, "t0"), ("addiu", "a2", "a2", 4), ("slti", "at", "a2", 8)]
            code += [("lh", "t2", 2, "t0")] if selector == "lh" else [("nop",)]
            fixtures.put(slus, place, fixtures.asm(place, code + [("jr", "ra"), ("nop",)]))
            if selector == "scaled":
                fixtures.put(slus, place + 4 * 5, struct.pack("<I", (8 << 21) | (9 << 16) | 25))   # multu t0, t1
            found = kit.equip_bonus(f.slus, bytes(slus))
            self.assertTrue(found is None or (651 not in found.fixed and not found.conditional), selector)
        cut = bytearray(f.slus[:g.slus_offset(kit.TRAP_THRESHOLDS) + 4])
        fixtures.put(cut, kit.ATTACK_TRAP, fixtures.asm(kit.ATTACK_TRAP, [("j", 0x8000B200)]))
        self.assertIsNone(kit.trap_thresholds(f.slus, bytes(cut)))


if __name__ == "__main__":
    unittest.main()
