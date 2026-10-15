"""Synthetic game files for the tests: made-up cards and tables laid out at
the retail offsets. No byte of the game is in here."""
from __future__ import annotations

import random
import struct

from fm_editor import gamedata as g
from fm_editor.gamedata import Card

GLYPH_TABLE = 0x801D9000
NAME_TEXT = 0x801D9200          # after the glyph table
DESCRIPTION_TEXT = 0x801C0A00   # after the string table (dialog entries 0x400-0x4F9 included)

# Glyph codes 1.. for these characters, skipping the codes text_listing spells
# its own way; each is the full-width Shift-JIS form, as the retail table's.
CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-."
SPECIAL = {0x1B, 0x40, 0x27, 0x28, 0x30, 0x47}


def _sjis(ch: str) -> int:
    if ch == "-":
        return 0x817C
    if ch == ".":
        return 0x8144
    return int.from_bytes(chr(ord(ch) + 0xFEE0).encode("shift_jis"), "big")


def glyph_codes() -> dict:
    codes, code = {" ": 0}, 1
    for ch in CHARACTERS:
        while code in SPECIAL:
            code += 1
        codes[ch] = code
        code += 1
    return codes


def card_type(cid: int) -> int:
    if cid <= 600:
        return cid % 20
    if cid <= 650:
        return g.TYPE_MAGIC
    if cid <= 680:
        return g.TYPE_EQUIP
    if cid <= 700:
        return g.TYPE_RITUAL
    return g.TYPE_TRAP


def make_cards() -> dict:
    cards = {}
    for cid in range(1, g.CARD_COUNT + 1):
        monster = card_type(cid) < g.TYPE_MAGIC
        name = {1: "Blue Dragon", 2: "Mystic Elf", 3: "Kuriboh"}.get(cid, f"Card {cid}")
        cards[cid] = Card(
            id=cid, name=name, description=f"Text of card {cid}.\nSecond line." if cid % 3 else f"Card {cid} text.",
            attack=(cid * 10) % 3000 if monster else 0, defense=(cid * 70) % 2500 if monster else 0,
            type=card_type(cid), attribute=cid % 6 if monster else 6, level=cid % 12 + 1 if monster else 0,
            star1=cid % 10 + 1 if monster else 0, star2=(cid + 3) % 10 + 1 if monster else 0)
    return cards


def make_tables():
    rng = random.Random(1411)
    monsters = [cid for cid in range(1, 601)]
    fusions = {}
    while len(fusions) < 300:
        a, b = rng.choice(monsters), rng.choice(monsters)
        if a != b:
            fusions[(min(a, b), max(a, b))] = rng.choice(monsters)
    fusions[(1, 2)] = 3
    equips = {651: list(range(1, 31)), 652: [5, 6, 7], 653: [300, 400]}
    rituals = {681: (1, 2, 3, 500), 682: (10, 11, 12, 501)}
    pools = []
    for d in range(g.DUELIST_COUNT):
        record = {}
        for pool in g.POOLS:
            chosen = rng.sample(monsters, 20)
            weights = {cid: 100 for cid in chosen}
            weights[chosen[0]] += g.POOL_TOTAL - 2000
            record[pool] = weights
        pools.append(record)
    return fusions, equips, rituals, pools


def encode_text(text: str, codes: dict) -> bytes:
    out = bytearray()
    for ch in text:
        out.append(0xFE if ch == "\n" else codes[ch])
    return bytes(out) + b"\xFF"


def make_slus(cards: dict, other_names: dict = None) -> bytes:
    """The executable: glyphs, stats, names and texts; `other_names` are
    names-bank strings past the cards ({index: text}, a duelist's say)."""
    data = bytearray(0x1D0800)
    at = g.slus_offset
    codes = glyph_codes()
    for ch, code in codes.items():
        if code:
            struct.pack_into("<I", data, at(GLYPH_TABLE + code * 4), _sjis(ch))
    name_at, text_at = NAME_TEXT, DESCRIPTION_TEXT
    for cid, card in cards.items():
        struct.pack_into("<I", data, at(g.STATS_ADDRESS + (cid - 1) * 4), g.pack_stats(card))
        data[at(g.LEVEL_ATTR_ADDRESS + cid)] = card.level | (card.attribute << 4)
        name = encode_text(card.name, codes)
        struct.pack_into("<H", data, at(g.NAME_TABLE + cid * 2), name_at - g.NAME_BANK)
        data[at(name_at):at(name_at) + len(name)] = name
        name_at += len(name)
        text = encode_text(card.description, codes)
        struct.pack_into("<H", data, at(g.STRING_TABLE + (0x100 + cid) * 2), text_at - g.DESCRIPTION_BANK)
        data[at(text_at):at(text_at) + len(text)] = text
        text_at += len(text)
    for index, text in (other_names or {}).items():
        name = encode_text(text, codes)
        struct.pack_into("<H", data, at(g.NAME_TABLE + index * 2), name_at - g.NAME_BANK)
        data[at(name_at):at(name_at) + len(name)] = name
        name_at += len(name)
    assert name_at < 0x801E0000 and text_at < 0x801D0000
    return bytes(data)


def make_wa(fusions, equips, rituals, pools) -> bytes:
    data = bytearray(0xFC0000)   # through the password table
    for k in range(g.TERRAIN_COPIES):
        base = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE
        for offset, blob in ((g.EQUIP_OFFSET, g.encode_equips(equips)), (g.FUSION_OFFSET, g.encode_fusions(fusions)),
                             (g.RITUAL_OFFSET, g.encode_rituals(rituals))):
            data[base + offset:base + offset + len(blob)] = blob
    for d, record in enumerate(pools):
        for pool, offset in g.POOL_OFFSETS.items():
            blob = g.encode_pool(record[pool])
            start = g.DUELIST_BASE + d * g.DUELIST_STRIDE + offset
            data[start:start + len(blob)] = blob
    for cid in ART_CARDS:
        paint_art(data, cid)
    for d in range(g.DUELIST_COUNT):
        paint_portrait(data, d)
    for cid in range(1, g.CARD_COUNT + 1):
        code = int(password_of(cid), 16) if password_of(cid) else g.PASSWORD_NONE
        struct.pack_into("<II", data, g.PASSWORD_TABLE + 8 * cid, cid * 10, code)
    return bytes(data)


def password_of(cid: int) -> str:
    """The synthetic disc's password of a card: its number times 7919, in
    8 digits; the last two cards have none, as the disc's 721 and 722."""
    return "" if cid > g.CARD_COUNT - 2 else f"{cid * 7919:08d}"


ART_CARDS = (1, 2, 3, 5)


def art_color(cid: int, index: int) -> int:
    """The synthetic palette: a 15-bit color per entry (never 0, the
    transparent one)."""
    return ((index * 7 + cid) & 0x1F) | (((index * 3) & 0x1F) << 5) | (((cid * 5 + index) & 0x1F) << 10) | 0x8000


def paint_art(data: bytearray, cid: int):
    """A recognizable art record and thumbnail sector for a card: a
    diagonal pattern through its own palette, and plate inks 0-7."""
    base = ((cid - 1) * 7 + 722) * 2048
    for y in range(96):
        for x in range(102):
            data[base + y * 102 + x] = 1 + (x + y * 2 + cid) % 255
    for i in range(256):
        struct.pack_into("<H", data, base + 0x2640 + i * 2, art_color(cid, i))
    for i in range(48 * 14):
        data[base + 0x2840 + i] = (i % 8) | (((i + cid) % 8) << 4)
    small = (cid - 1) * 2048
    for y in range(32):
        for x in range(40):
            data[small + y * 40 + x] = 1 + (x * 3 + y + cid) % 63
    for i in range(64):
        struct.pack_into("<H", data, small + 0x500 + i * 2, art_color(cid + 1, i))


PORTRAITS = 0xF55000     # portrait.BASE: a 0x980-byte Free Duel portrait to a duelist


def paint_portrait(data: bytearray, d: int):
    """Duelist d's Free Duel portrait: 48x48 bands through a 64-color
    palette of its own."""
    at = PORTRAITS + d * 0x980
    for i in range(48 * 48):
        data[at + i] = (i // 48 + d) % 64
    for i in range(64):
        struct.pack_into("<H", data, at + 0x900 + i * 2, art_color(d + 40, i))


class Fixture:
    """The synthetic retail game: its source values and its two files."""

    def __init__(self):
        self.cards = make_cards()
        self.fusions, self.equips, self.rituals, self.pools = make_tables()
        self.other_names = {0x330: "Heishin"}
        self.slus = make_slus(self.cards, self.other_names)
        self.wa = make_wa(self.fusions, self.equips, self.rituals, self.pools)

    def game(self) -> g.GameData:
        return g.read_game(self.slus, self.wa)


def make_iso(files: dict, raw: bool = True) -> bytes:
    """A small ISO 9660 image holding `files` ({"SLUS_014.11": bytes,
    "DATA/WA_MRG.MRG": bytes}), in 2352-byte MODE2 sectors or 2048-byte ones."""
    def record(name: bytes, lba: int, size: int, directory: bool) -> bytes:
        length = 33 + len(name) + (len(name) + 1) % 2
        out = bytearray(length)
        out[0] = length
        struct.pack_into("<I", out, 2, lba)
        struct.pack_into(">I", out, 6, lba)
        struct.pack_into("<I", out, 10, size)
        struct.pack_into(">I", out, 14, size)
        out[25] = 2 if directory else 0
        out[32] = len(name)
        out[33:33 + len(name)] = name
        return bytes(out)

    sectors = {}
    next_lba = 24
    placed = {}
    for path, blob in files.items():
        placed[path] = (next_lba, len(blob))
        for i in range(0, max(len(blob), 1), 2048):
            sectors[next_lba] = blob[i:i + 2048].ljust(2048, b"\0")
            next_lba += 1
    root_lba, data_lba = 20, 21
    data_dir = record(b"\0", data_lba, 2048, True) + record(b"\1", root_lba, 2048, True)
    root = record(b"\0", root_lba, 2048, True) + record(b"\1", root_lba, 2048, True)
    root += record(b"DATA", data_lba, 2048, True)
    for path, (lba, size) in placed.items():
        name = path.split("/")[-1].encode() + b";1"
        if path.startswith("DATA/"):
            data_dir += record(name, lba, size, False)
        else:
            root += record(name, lba, size, False)
    sectors[root_lba] = root.ljust(2048, b"\0")
    sectors[data_lba] = data_dir.ljust(2048, b"\0")
    pvd = bytearray(2048)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[156:156 + 34] = record(b"\0", root_lba, 2048, True)
    sectors[16] = bytes(pvd)
    out = bytearray()
    for lba in range(next_lba):
        user = sectors.get(lba, bytes(2048))
        if raw:
            out += bytes(24) + user + bytes(2352 - 24 - 2048)
        else:
            out += user
    return bytes(out)


# --- a few MIPS instructions, for made-up mod code ----------------------------------------

REGISTERS = {name: i for i, name in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}


def _r(name):
    return REGISTERS[name]


def _i(op, rs, rt, imm):
    return (op << 26) | (_r(rs) << 21) | (_r(rt) << 16) | (imm & 0xFFFF)


def asm(address: int, lines) -> bytes:
    """Assemble ("op", args...) tuples at `address`: j, jal, lui, addiu,
    li, ori, lhu, lbu, lh, lw, sltiu, slti, srl, sra, srlv, addu, beq,
    bne, jr, nop. Branch targets are absolute."""
    out = bytearray()
    for n, (op, *a) in enumerate(lines):
        pc = address + 4 * n
        if op in ("j", "jal"):
            word = ((2 if op == "j" else 3) << 26) | ((a[0] >> 2) & 0x3FFFFFF)
        elif op == "lui":
            word = _i(15, "zero", a[0], a[1])
        elif op == "addiu":
            word = _i(9, a[1], a[0], a[2])
        elif op == "li":
            word = _i(9, "zero", a[0], a[1])
        elif op == "ori":
            word = _i(13, a[1], a[0], a[2])
        elif op in ("lb", "lh", "lw", "lbu", "lhu"):
            word = _i({"lb": 32, "lh": 33, "lw": 35, "lbu": 36, "lhu": 37}[op], a[2], a[0], a[1])
        elif op in ("sltiu", "slti"):
            word = _i(11 if op == "sltiu" else 10, a[1], a[0], a[2])
        elif op in ("srl", "sra"):
            word = (_r(a[1]) << 16) | (_r(a[0]) << 11) | (a[2] << 6) | (2 if op == "srl" else 3)
        elif op == "srlv":
            word = (_r(a[2]) << 21) | (_r(a[1]) << 16) | (_r(a[0]) << 11) | 6
        elif op == "addu":
            word = (_r(a[1]) << 21) | (_r(a[2]) << 16) | (_r(a[0]) << 11) | 33
        elif op in ("beq", "bne"):
            word = _i(4 if op == "beq" else 5, a[0], a[1], (a[2] - pc - 4) >> 2)
        elif op == "jr":
            word = (_r(a[0]) << 21) | 8
        elif op == "nop":
            word = 0
        else:
            raise ValueError(op)
        out += struct.pack("<I", word)
    return bytes(out)


def put(slus: bytearray, address: int, blob: bytes):
    """Bytes at a RAM address of the executable (its header's code at
    0x8000B070 and up, as the kit puts it)."""
    at = address - 0x8000B070 if address < 0x80010000 else g.slus_offset(address)
    slus[at:at + len(blob)] = blob
