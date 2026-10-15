"""What a modified executable's code says about its tables and rules.

A family of community mods made with one patch kit changes the duel in
MIPS: it jumps from
the retail functions to code of its own and keeps its parameters in tables
there. The addresses of that code move from one mod to the next; the places
it hooks and the shape of the code do not. Each reader here starts at a
retail function, follows the mod's jump, and reads the values the code
uses, or answers None when the code is not that shape.

Nothing here runs the mod's code: it is read as data, a few instructions at
a time, with the registers' constants followed (lui, addiu, ori).
"""
from __future__ import annotations

import struct

from . import gamedata as g

HEADER_ADDRESS = 0x8000B070      # where the BIOS leaves the executable's header, which the kit fills with code
EXE_START = 0x80010000

# RAM windows the duel package is loaded into (Duel_CheckEquip, Duel_CheckRitual), and where they come from.
EQUIP_ADDRESS, EQUIP_WINDOW = 0x8017A1D8, 0x2100
RITUAL_ADDRESS = 0x801799D8

CHECK_EQUIP = 0x80019A08         # Duel_CheckEquip
EQUIP_RECORD = 94                # u16 equip id and a bitmap of 92 bytes, most significant bit first


# --- reading code ------------------------------------------------------------------------

class Memory:
    """The executable's RAM image, with the header's code and the duel
    package's tables where the game puts them."""

    def __init__(self, slus: bytes, wa: bytes = b""):
        self.slus, self.wa = slus, wa

    def bytes(self, address: int, count: int) -> bytes:
        if HEADER_ADDRESS <= address < HEADER_ADDRESS + 0x800:
            at = address - HEADER_ADDRESS
            return self.slus[at:at + count]
        if EQUIP_ADDRESS <= address < EQUIP_ADDRESS + EQUIP_WINDOW and self.wa:
            at = g.TERRAIN_BASE + g.EQUIP_OFFSET + address - EQUIP_ADDRESS
            return self.wa[at:at + count]
        at = g.slus_offset(address)
        return self.slus[at:at + count] if 0 <= at else b""

    def word(self, address: int):
        data = self.bytes(address, 4)
        return struct.unpack("<I", data)[0] if len(data) == 4 else None

    def u16(self, address: int):
        data = self.bytes(address, 2)
        return struct.unpack("<H", data)[0] if len(data) == 2 else None

    def s8(self, address: int):
        data = self.bytes(address, 1)
        return struct.unpack("<b", data)[0] if data else None

    def u8(self, address: int):
        data = self.bytes(address, 1)
        return data[0] if data else None


def s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def jump_target(word: int, address: int) -> int:
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


class Ins:
    """One instruction's fields."""

    def __init__(self, word: int, address: int):
        self.word, self.address = word, address
        self.op, self.rs, self.rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        self.rd, self.sa, self.fn = (word >> 11) & 31, (word >> 6) & 31, word & 63
        self.imm = s16(word & 0xFFFF)

    @property
    def is_jump(self):          # j
        return self.op == 2

    @property
    def is_call(self):          # jal
        return self.op == 3

    @property
    def target(self):
        return jump_target(self.word, self.address)

    def load(self, op):          # lb 32, lh 33, lw 35, lbu 36, lhu 37
        return self.op == op

    def is_addiu(self, rs=None, rt=None):
        return self.op == 9 and (rs is None or self.rs == rs) and (rt is None or self.rt == rt)

    def is_slti(self):
        return self.op == 10

    def is_sltiu(self):
        return self.op == 11

    def is_sra(self):
        return self.op == 0 and self.fn == 3

    def is_srl(self):
        return self.op == 0 and self.fn == 2

    def is_branch_or_return(self):
        return 1 <= self.op <= 7 or (self.op == 0 and self.fn in (8, 9))


def instructions(memory: Memory, address: int, count: int):
    out = []
    for i in range(count):
        word = memory.word(address + 4 * i)
        if word is None:
            break
        out.append(Ins(word, address + 4 * i))
    return out


class Constants:
    """Registers' values as lui, addiu and ori set them, followed through
    straight-line code; each load's address when its base is known."""

    def __init__(self):
        self.value = {0: 0}

    def step(self, ins: Ins):
        """The address a load or store uses, or None."""
        address = None
        if 32 <= ins.op <= 46 and ins.rs in self.value:
            address = (self.value[ins.rs] + ins.imm) & 0xFFFFFFFF
        if ins.op == 15:                                   # lui
            self.value[ins.rt] = (ins.word & 0xFFFF) << 16
        elif ins.op == 9:                                  # addiu
            if ins.rs in self.value:
                self.value[ins.rt] = (self.value[ins.rs] + ins.imm) & 0xFFFFFFFF
            else:
                self.value.pop(ins.rt, None)
        elif ins.op == 13 and ins.rs in self.value:        # ori
            self.value[ins.rt] = self.value[ins.rs] | (ins.word & 0xFFFF)
        elif ins.op in (32, 33, 35, 36, 37) or (ins.op == 0 and ins.fn not in (8, 9, 12, 13) and ins.word):
            target = ins.rt if ins.op else ins.rd
            if target:
                self.value.pop(target, None)
        self.value[0] = 0
        return address


def hook(retail: Memory, memory: Memory, start: int, end: int):
    """(address, target) of the first j the mod put in [start, end) where
    retail has other code, landing outside the retail executable's code
    (the header, or past it); else None."""
    for at in range(start, end, 4):
        word = memory.word(at)
        if word is None or word == retail.word(at) or word >> 26 != 2:
            continue
        return at, jump_target(word, at)
    return None


# --- equips as bitmaps (Duel_CheckEquip) ---------------------------------------------------

class EquipBitmaps:
    """The kit's equip table: records of an equip id and a bitmap of the
    monsters it equips; after `limit` of them (or at id 0), optional
    records of a monster and a bitmap of the equips it takes; and monsters
    no equip may equip."""

    def __init__(self):
        self.records = []           # [(equip id, {monster ids})], in the table's order
        self.limit = None           # how many records the game reads; None: up to id 0
        self.by_monster = []        # [(monster id, {equip ids})]
        self.blocked = set()        # monsters nothing equips
        self.where = ""

    def allowed(self, equip: int) -> set:
        """The monsters `equip` equips, as the mod's Duel_CheckEquip decides."""
        for key, monsters in self.records:
            if key == equip:
                return monsters - self.blocked
        return {m for m, equips in self.by_monster if equip in equips} - self.blocked


def _bitmap(data: bytes) -> set:
    return {m for m in range(1, g.CARD_COUNT + 1) if m >> 3 < len(data) and data[m >> 3] >> (7 - (m & 7)) & 1}


def _read_records(memory: Memory, address: int, limit):
    records = []
    most = limit if limit is not None else EQUIP_WINDOW // EQUIP_RECORD
    for k in range(most):
        at = address + k * EQUIP_RECORD
        key = memory.u16(at)
        if key is None or (limit is None and key == 0) or at + EQUIP_RECORD > EQUIP_ADDRESS + EQUIP_WINDOW:
            break
        if key == 0:
            break
        records.append((key, _bitmap(memory.bytes(at + 2, EQUIP_RECORD - 2))))
    return records


def equip_bitmaps(retail_slus: bytes, slus: bytes, wa: bytes):
    """The mod's equip table when its Duel_CheckEquip steps 94 bytes a
    record and tests one bit per monster (signature A6), else None."""
    retail, memory = Memory(retail_slus), Memory(slus, wa)
    if memory.bytes(CHECK_EQUIP, 0x58) == retail.bytes(CHECK_EQUIP, 0x58):
        return None
    body = instructions(memory, CHECK_EQUIP, 0x58 // 4)
    found = hook(retail, memory, CHECK_EQUIP, CHECK_EQUIP + 0x58)
    code = body
    if found:           # the hook's own instructions set registers the mod's code then uses
        at = (found[0] - CHECK_EQUIP) // 4
        code = body[:at + 2] + instructions(memory, found[1], 64)
    if not any(ins.is_addiu() and ins.rs == ins.rt and ins.imm == EQUIP_RECORD for ins in code):
        return None
    if not any(ins.op == 0 and ins.fn == 6 for ins in code):            # srlv: the bit of the monster
        return None
    table = EquipBitmaps()
    constants = Constants()
    tables, limits, blocked = [], [], []
    upper = set()                   # registers a lui just set: lui and addiu make a table's address
    for i, ins in enumerate(code):
        was_upper = ins.is_addiu() and ins.rs in upper
        address = constants.step(ins)
        upper.discard(ins.rt if ins.op else ins.rd)
        if ins.op == 15:
            upper.add(ins.rt)
        if was_upper and ins.rt in constants.value:
            value = constants.value[ins.rt]
            if EQUIP_ADDRESS <= value < EQUIP_ADDRESS + EQUIP_WINDOW and value not in tables:
                tables.append(value)
        if ins.is_slti() and ins.rs != ins.rt and ins.imm < 100:
            limits.append((len(tables), ins.imm))
        if ins.load(37) and address is not None and i + 1 < len(code) and code[i + 1].is_srl() \
                and code[i + 1].sa == 4 and not EQUIP_ADDRESS <= address < EQUIP_ADDRESS + EQUIP_WINDOW:
            blocked.append(address)                      # a list of id << 4 the code turns away
    if not tables:
        return None
    first = [n for count, n in limits if count <= 1]
    table.limit = first[0] if first else None
    table.records = _read_records(memory, tables[0], table.limit)
    if len(tables) > 1:
        second = [n for count, n in limits if count == 2]
        table.by_monster = _read_records(memory, tables[1], second[0] if second else None)
    for address in blocked:
        value = memory.u16(address)
        if value is not None and 1 <= value >> 4 <= g.CARD_COUNT:
            table.blocked.add(value >> 4)
    table.where = f"Duel_CheckEquip (0x{CHECK_EQUIP:08X})" + (f", and the mod's code at 0x{found[1]:08X}" if found else "")
    return table


# --- the deck and the drops ------------------------------------------------------------------

SHUFFLE_DECK = 0x80024460, 0x800244E8      # Duel_ShuffleDeck's dealing loop
RESULT_DRAW = 0x80021C6C                   # DuelScene_UpdateResultRewards: the prize's draw
DECK_SIZE = 40


def deals_by_count(retail_slus: bytes, slus: bytes) -> bool:
    """Whether the mod's Duel_ShuffleDeck deals the deck pool as counts of
    copies (signature A4): the loop rewritten to walk the cards in order and
    stop at 40 (slti ..., 40), where retail draws weights of 2048."""
    retail, memory = Memory(retail_slus), Memory(slus)
    start, end = SHUFFLE_DECK
    if memory.bytes(start, end - start) == retail.bytes(start, end - start):
        return False
    return any(ins.is_slti() and ins.imm == DECK_SIZE for ins in instructions(memory, start, (end - start) // 4 + 2))


def dealt_by_count(pool: dict) -> dict:
    """The forty cards the kit's shuffle deals from a pool: every card in
    id order, as many copies as its number, until there are 40."""
    deck, total = {}, 0
    for cid in sorted(pool):
        take = min(pool[cid], DECK_SIZE - total)
        if take > 0:
            deck[cid] = take
            total += take
    return deck


def decoder_at(memory: Memory, code: int):
    """(bias, shift) when the code at `code` turns v-register weight into
    (weight - bias) >> shift (an addiu of -bias, then an sra) before it
    branches, else None."""
    bias = register = None
    for ins in instructions(memory, code, 8):
        if ins.is_addiu() and bias is None and ins.rs == ins.rt and ins.imm < 0:
            bias, register = -ins.imm, ins.rt
        elif ins.is_sra() and bias is not None and ins.rt == ins.rd == register:
            return bias, ins.sa
        elif ins.is_branch_or_return() or ins.is_jump or ins.is_call:
            return None
    return None


class ExtraDraws:
    count = None            # cards the mod draws a win, or None when not read
    encoding = None         # (bias, shift, code) of the weights' decoding, or None: raw weights
    code = 0


def extra_draws(retail_slus: bytes, slus: bytes):
    """The kit's drawing of several prizes (signature A1/A2): the result
    screen's draw jumps to the mod's loop, which counts draws in one byte
    against a limit in the next and may call code decoding the weights."""
    retail, memory = Memory(retail_slus), Memory(slus)
    word = memory.word(RESULT_DRAW)
    if word is None or word == retail.word(RESULT_DRAW) or word >> 26 != 2:
        return None
    found = ExtraDraws()
    found.code = jump_target(word, RESULT_DRAW)
    code = instructions(memory, found.code, 0x60)
    constants, loads = Constants(), []
    for ins in code:
        address = constants.step(ins)
        if ins.load(36) and address is not None:
            loads.append(address)
        if ins.is_call and found.encoding is None:
            decoded = decoder_at(memory, ins.target)
            if decoded:
                found.encoding = decoded + (ins.target,)
    for address in loads:
        if address + 1 in loads:
            limit = memory.bytes(address + 1, 1)
            if limit and limit[0] >= 2:
                found.count = limit[0] - 1
            break
    return found


# --- rules mod.json has keys for -------------------------------------------------------------

AWARD_CARD = 0x800218AC          # Duel_AwardCard: a card into the chest
STARCHIP_CAP = 999999            # 0xF423F


def chest_overflow(retail_slus: bytes, slus: bytes):
    """(limit, starchips) when the mod's Duel_AwardCard caps the chest at
    `limit` copies and pays `starchips` a card past it (signature A3):
    sltiu against limit + 1, the starchips word raised by an addiu, and the
    999999 cap; else None."""
    retail, memory = Memory(retail_slus), Memory(slus)
    found = hook(retail, memory, AWARD_CARD, AWARD_CARD + 4)
    if not found:
        return None
    constants, limit, pay, capped, loaded = Constants(), None, None, False, set()
    for ins in instructions(memory, found[1], 24):
        constants.step(ins)
        if ins.is_sltiu() and ins.rs == 2 and limit is None:
            limit = ins.imm - 1
        if ins.load(35):
            loaded.add(ins.rt)
        if ins.is_addiu() and ins.rs == ins.rt and ins.rt in loaded and ins.imm > 0 and pay is None:
            pay = ins.imm
        if STARCHIP_CAP in constants.value.values():
            capped = True
    if limit is None or pay is None or not capped or not 1 <= limit <= 250:
        return None
    return limit, pay


ATTACK_TRAP = 0x8001F0F0         # Duel_SelectAttackTrap
TRAP_THRESHOLDS = 0x8009AF24     # retail: six bytes, hundreds of ATK
ATTACK_TRAPS = ("House of Adhesive Tape", "Eatgaboon", "Bear Trap", "Invisible Wire", "Acid Trap Hole",
                "Widespread Ruin")


def trap_thresholds(retail_slus: bytes, slus: bytes):
    """{trap: points} when the mod's Duel_SelectAttackTrap is rewritten and
    reads the thresholds as u16 hundreds (signature A8), else None."""
    retail, memory = Memory(retail_slus), Memory(slus)
    if not hook(retail, memory, ATTACK_TRAP, ATTACK_TRAP + 4):
        return None
    data = memory.bytes(TRAP_THRESHOLDS, 12)
    if len(data) != 12:             # a cut-off executable
        return None
    values = struct.unpack("<6H", data)
    if not all(values) or list(values) != sorted(values) or max(values) > 655:
        return None
    return {trap: value * 100 for trap, value in zip(ATTACK_TRAPS, values)}


TERRAIN_BOOST = 0x800909D4       # gDuel_aTerrainBoost: s8 [20 monster types][6 terrains], tens of points
GET_TERRAIN_BOOST = 0x8002497C, 0x800249DC
TERRAIN_NAMES = ("Forest", "Wasteland", "Mountain", "Sogen", "Umi", "Yami")


class TerrainBonus:
    table = None             # {terrain 1-6: {type: points}}
    where = ""
    more_terrains = 0        # terrains past the six in the mod's rows
    by_attribute = None      # the first terrain that looks at the attribute instead, or None


def terrain_bonus(retail_slus: bytes, slus: bytes):
    """The mod's terrain bonuses (signature A9): the retail table with other
    values, or Duel_GetTerrainBoost rewritten to read a table
    of its own, a row of terrains per type."""
    retail, memory = Memory(retail_slus), Memory(slus)
    start, end = GET_TERRAIN_BOOST
    found = TerrainBonus()
    if memory.bytes(start, end - start) == retail.bytes(start, end - start):
        if memory.bytes(TERRAIN_BOOST, 120) == retail.bytes(TERRAIN_BOOST, 120):
            return None
        address, row = TERRAIN_BOOST, 6
        found.where = f"gDuel_aTerrainBoost (0x{TERRAIN_BOOST:08X})"
    else:
        constants, tables, bound = Constants(), [], None
        for ins in instructions(memory, start, (end - start) // 4):
            upper = ins.is_addiu() and ins.rs == ins.rt and ins.rs in constants.value and \
                constants.value[ins.rs] & 0xFFFF == 0
            constants.step(ins)
            if upper:
                tables.append(constants.value[ins.rt])
            if ins.is_slti() and bound is None and 7 <= ins.imm <= 32:
                bound = ins.imm
        if not tables or bound is None:
            return None
        address, row = tables[0], bound - 1
        found.more_terrains = row - 6
        found.by_attribute = bound
        found.where = f"Duel_GetTerrainBoost (0x{start:08X}), rewritten to read the mod's table at 0x{address:08X}"
    found.table = {}
    for terrain in range(1, 7):
        values = {}
        for t in range(g.TYPE_MAGIC):
            value = memory.s8(address + t * row + terrain - 1)
            if value is None:
                return None
            if value:
                values[t] = value * 10
        found.table[terrain] = values
    return found


# --- equip bonuses (DuelScene_UpdateCardPlacement) ----------------------------------------

EQUIP_BONUS_SITE = 0x8001A7F0, 0x8001A838
NO_CARD = 723                    # the kit's list end


class EquipBonus:
    def __init__(self):
        self.fixed = {}          # card -> points: a bonus of its own
        self.conditional = []    # (card, selector, points): scaled by a count the mod keeps
        self.special = []        # cards the mod's code gives a bonus of their own logic
        self.where = ""


def _loop_tables(code):
    """(index of the load, table address, step, entries) for each loop that
    walks a u16 table: a lui base (plus an index register), a load, and an
    addiu step and slti bound on the index."""
    found, base = [], {}
    for i, ins in enumerate(code):
        if ins.op == 15:
            base[ins.rt] = (ins.word & 0xFFFF) << 16
        elif ins.is_addiu() and ins.rt in base and ins.rs == ins.rt:
            base[ins.rt] = (base[ins.rt] + ins.imm) & 0xFFFFFFFF
        elif ins.op == 0 and ins.fn == 33 and ins.rd == ins.rs and ins.rd in base:
            pass                                          # addu base, base, index: still the table
        elif ins.load(37) and ins.rs in base:
            address = (base[ins.rs] + ins.imm) & 0xFFFFFFFF
            step = bound = None
            for later in code[i + 1:i + 8]:
                if later.is_addiu() and later.rs == later.rt and later.imm in (2, 4) and step is None:
                    step = later.imm
                if later.is_slti() and bound is None:
                    bound = later.imm
            if step and bound:
                found.append((i, address, step, bound // step))
            base.pop(ins.rt, None)
        elif ins.op not in (1, 2, 3, 4, 5, 6, 7, 40, 41, 43) and not (ins.op == 0 and ins.fn in (8, 9)):
            base.pop(ins.rt if ins.op else ins.rd, None)
    return found


def equip_bonus(retail_slus: bytes, slus: bytes):
    """What the mod's DuelScene_UpdateCardPlacement gives an equip (signature
    A7), else None: a table of (card, points), bands of
    cards per value, cards scaled by a count the mod keeps,
    and a chain of cards with code of their own."""
    retail, memory = Memory(retail_slus), Memory(slus)
    start, end = EQUIP_BONUS_SITE
    targets = []
    for at in range(start, end + 4, 4):
        word = memory.word(at)
        if word is not None and word != retail.word(at) and word >> 26 == 2:
            targets.append(jump_target(word, at))
    if not targets:
        return None
    found = EquipBonus()
    found.where = ", ".join(f"0x{t:08X}" for t in targets)
    for target in targets:
        code = instructions(memory, target, 96)
        for i, address, step, entries in _loop_tables(code):
            after = code[i + 1:i + 40]
            ids = [memory.u16(address + step * k) for k in range(entries)]
            if step == 4 and any(ins.load(33) and ins.imm == 2 for ins in after[:12]):
                for k, cid in enumerate(ids):
                    points = memory.u16(address + 4 * k + 2)
                    if cid and cid != NO_CARD and points is not None:      # None: past the executable's end
                        found.fixed[cid] = s16(points)
            elif step == 4 and any(ins.op == 0 and ins.fn == 25 for ins in after[:12]):       # multu: scaled
                for k, cid in enumerate(ids):
                    selector, points = memory.u8(address + 4 * k + 2), memory.u8(address + 4 * k + 3)
                    if cid and cid != NO_CARD and selector is not None and points is not None:
                        found.conditional.append((cid, selector, points * 10))
            elif step == 2:
                bands, pending = [], None
                for ins in after:
                    if ins.is_slti() and ins.rs != ins.rt:
                        pending = ins.imm
                    elif ins.is_addiu(rs=0) and pending is not None and ins.imm > 0:
                        bands.append((pending, ins.imm))
                        pending = None
                low = 0
                for high, value in bands:
                    for k in range(low // 2, min(high // 2, entries)):
                        if ids[k] and ids[k] != NO_CARD:
                            found.fixed.setdefault(ids[k], value)
                    low = high
        for i, ins in enumerate(code[:-1]):
            nxt = code[i + 1]
            if ins.is_addiu(rs=0) and 1 <= ins.imm <= g.CARD_COUNT and nxt.op in (4, 5) and \
                    ins.rt in (nxt.rs, nxt.rt) and ins.imm not in found.special and ins.imm not in found.fixed:
                found.special.append(ins.imm)
    if not (found.fixed or found.conditional or found.special):
        return None
    return found
