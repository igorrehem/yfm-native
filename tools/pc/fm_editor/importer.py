"""A community mod's modified game files, turned into a port mod.

The mods of the PS1 scene (Mod 13, FM 2023, Shin...) ship patched copies of
SLUS_014.11 and WA_MRG.MRG, or a patched disc. This compares them with the
player's retail files and writes what differs in the port's terms:

* cards, fusions, equips, rituals, deck and drop pools: the editor's own
  diff (manifest.build), so the result opens in the editor like any mod;
* other text (dialogue, menus, types, duelists, places): a partial text
  listing (text_listing.py's format), "text" in mod.json;
* other changed bytes of WA_MRG.MRG (images, passwords and costs, starter
  decks...): "data" patches, or sector replacements for long runs; the port
  reads WA_MRG.MRG through its override layer, so they apply;
* what the port cannot take from a data file (code and tables in the
  executable, such as the AI's parameters or the field bonuses; other disc
  files) is listed in the report instead.
"""
from __future__ import annotations

import bisect
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import gamedata as g, kit, manifest, values
from .fixed_decks import set_deck as set_fixed_deck
from .model import Project
from .pools import normalize

WA_FILE = "\\DATA\\WA_MRG.MRG;1"
MERGE_GAP = 32              # changed runs closer than this are one patch
PATCH_LIMIT = 4096          # longer runs become sector replacements
# The port holds 1024 patched runs and 64 replaced regions for all the mods
# together (src/pc/mods/mods.c); past these a mod replaces the whole file.
WA_PATCHES_MOST = 256
WA_REGIONS_MOST = 16

# Executable regions the port has no data key for, by RAM address.
SLUS_REGIONS = [
    (0x800909D4, 0x80090A4C, "field (terrain) bonus table"),
    (0x80090A4C, 0x80090AD4, "destroy-by-type/ATK effect table"),
    (0x80090AD4, 0x80090B39, "magic effect classes"),
    (0x800917F0, 0x80091958, "opponents' AI parameters (9 bytes each)"),
    (0x8009AF24, 0x8009AF40, "trap ceilings / heal and burn amounts"),
    (0x8001A7F8, 0x8001A7FC, "equip bonus (+500)"),
    (0x8001A820, 0x8001A824, "Megamorph bonus (+1000)"),
    (0x801D9000, 0x801D9170, "the font's glyph table"),
    (0x801D5EC0, 0x801D6000, "the names table's entries 0x8360-0x83FF (past the ones the text listing reads)"),
]
# Executable regions the editor turns into cards[]; the text banks' bytes
# the text listing reads are added per file (text_spans).
SLUS_HANDLED = [
    (g.STATS_ADDRESS, g.STATS_ADDRESS + 4 * g.CARD_COUNT),
    (g.LEVEL_ATTR_ADDRESS, g.LEVEL_ATTR_ADDRESS + g.CARD_COUNT + 1),
]
TEXT_BANKS = [(0x801B0000, 0x801C0000, "the dialog bank"), (0x801C0000, 0x801D0000, "the card texts' bank"),
              (0x801D0000, 0x801E0000, "the names bank")]
PLACES_SHOWN = 12           # changed places listed one by one in the report

# The drop draw (Duel_SelectCardDrop) adds each card's weight at this
# instruction. The TeaOnline drop tool's mods write every drop weight as
# bias + 8*weight + noise and replace it with a jump to code that undoes it.
DRAW_ADD = 0x80021860
TEAONLINE_ENCODING = (2512, 3)      # (bias, shift) that tool writes
DROP_POOLS = ("pow", "bcd", "tec")  # the deck pools are never encoded


def slug(text: str) -> str:
    """A mod id out of a file name (File > Import and the command line)."""
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(text).stem).strip("-").lower()
    return (text or "imported-mod")[:63]


@dataclass
class ImportResult:
    project: Project
    report: list = field(default_factory=list)       # lines for the user
    unhandled: int = 0                               # count of things the port cannot take


def _runs(a: bytes, b: bytes, start: int, end: int, gap: int = MERGE_GAP):
    """[start, end) runs where a and b differ, merged across small gaps."""
    runs = []
    at = start
    end = min(end, len(a), len(b))
    step = 4096
    while at < end:
        stop = min(at + step, end)
        if a[at:stop] == b[at:stop]:
            at = stop
            continue
        for i in range(at, stop):
            if a[i] != b[i]:
                if runs and i - runs[-1][1] <= gap:
                    runs[-1][1] = i + 1
                else:
                    runs.append([i, i + 1])
        at = stop
    return [tuple(r) for r in runs]


def _trim(a: bytes, b: bytes, runs):
    """Each run cut down to its first and last differing byte; runs where
    nothing differs (a gap between two regions, left by _subtract) dropped."""
    out = []
    for start, end in runs:
        while start < end and a[start] == b[start]:
            start += 1
        while end > start and a[end - 1] == b[end - 1]:
            end -= 1
        if start < end:
            out.append((start, end))
    return out


def _merge(runs, gap: int):
    out = []
    for start, end in sorted(runs):
        if out and start - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
    return out


def _subtract(runs, regions):
    """The parts of runs outside every region."""
    out = []
    for start, end in runs:
        pieces = [(start, end)]
        for low, high in regions:
            next_pieces = []
            for s, e in pieces:
                if e <= low or s >= high:
                    next_pieces.append((s, e))
                    continue
                if s < low:
                    next_pieces.append((s, low))
                if e > high:
                    next_pieces.append((high, e))
            pieces = next_pieces
        out += pieces
    return out


def wa_structured_regions():
    regions = []
    for k in range(g.TERRAIN_COPIES):
        base = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE
        regions += [(base + g.EQUIP_OFFSET, base + g.EQUIP_OFFSET + g.EQUIP_LENGTH),
                    (base + g.FUSION_OFFSET, base + g.FUSION_OFFSET + g.FUSION_LENGTH),
                    (base + g.RITUAL_OFFSET, base + g.RITUAL_OFFSET + g.RITUAL_LENGTH)]
    for d in range(g.DUELIST_COUNT):
        for offset in g.POOL_OFFSETS.values():
            start = g.DUELIST_BASE + d * g.DUELIST_STRIDE + offset
            regions.append((start, start + 2 * g.CARD_COUNT))
    return regions


def describe_wa(offset: int) -> str:
    if 0x169000 <= offset < 0x169000 + 0x3800 * g.CARD_COUNT:
        return "the cards' pictures and name plates"
    if offset < 0x800 * g.CARD_COUNT:
        return "the cards' small pictures"
    if 0xFB9800 <= offset < 0xFB9800 + 8 * 723:
        return "the cards' passwords and starchip costs"
    if g.STARTER_BASE <= offset < g.STARTER_BASE + g.STARTER_LENGTH:
        return "the starter deck pools"
    if 0xF55000 <= offset < 0xF55000 + 40 * 2432:
        return "the duelists' portraits"
    if g.DUELIST_BASE <= offset < g.DUELIST_BASE + g.DUELIST_COUNT * g.DUELIST_STRIDE:
        inside = (offset - g.DUELIST_BASE) % g.DUELIST_STRIDE
        return "the opponents' records (between their pools)" if inside < 4 * 0x5B4 else \
            "the opponents' records (rank tables)"
    if g.TERRAIN_BASE <= offset < g.TERRAIN_BASE + g.TERRAIN_COPIES * g.TERRAIN_STRIDE:
        return f"the duel package (terrain copy {(offset - g.TERRAIN_BASE) // g.TERRAIN_STRIDE})"
    return "WA_MRG.MRG"


# --- the executable's code ------------------------------------------------------------

def _word(slus: bytes, address: int):
    at = g.slus_offset(address)
    return struct.unpack_from("<I", slus, at)[0] if 0 <= at <= len(slus) - 4 else None


def _jump_target(word: int, address: int) -> int:
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def jumps_into(retail_slus: bytes, slus: bytes, places) -> dict:
    """{(start, end): ["j at 0x80021860 (patched)", ...]}: the j and jal
    instructions of the executable that land in each [start, end) RAM range;
    "patched" when that instruction is not retail's."""
    found = {place: [] for place in places}
    ranges = sorted(places)
    starts = [start for start, _ in ranges]
    header = g.slus_offset(0x80010000)
    for index, (word,) in enumerate(struct.iter_unpack("<I", slus[header:header + (len(slus) - header) // 4 * 4])):
        if word >> 26 not in (2, 3):
            continue
        address = 0x80010000 + 4 * index
        target = _jump_target(word, address)
        k = bisect.bisect_right(starts, target) - 1
        if k >= 0 and target < ranges[k][1]:
            patched = " (patched)" if _word(retail_slus, address) != word else ""
            found[ranges[k]].append(f"{'j' if word >> 26 == 2 else 'jal'} at 0x{address:08X}{patched}")
    return found


def draw_code_encoding(retail_slus: bytes, slus: bytes):
    """(bias, shift, code address) when the drop draw's add (DRAW_ADD) is a
    jump to code that turns the weight into (weight - bias) >> shift with an
    addiu and an sra before anything else branches, else None."""
    word = _word(slus, DRAW_ADD)
    if word is None or word == _word(retail_slus, DRAW_ADD) or word >> 26 != 2:
        return None
    code = _jump_target(word, DRAW_ADD)
    bias = register = None
    for i in range(8):
        w = _word(slus, code + 4 * i)
        if w is None:
            return None
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        if op == 9 and bias is None and rs == rt:                       # addiu r, r, -bias
            imm = w & 0xFFFF
            bias, register = -(imm - 0x10000 if imm & 0x8000 else imm), rt
        elif op == 0 and w & 63 == 3 and bias is not None and rt == rd == register:     # sra r, r, shift
            return bias, (w >> 6) & 31, code
        elif 1 <= op <= 7 or (op == 0 and w & 63 in (8, 9)):             # a branch or a jump first
            return None
    return None


def _raw_pool(wa: bytes, duelist: int, pool: str):
    at = g.DUELIST_BASE + duelist * g.DUELIST_STRIDE + g.POOL_OFFSETS[pool]
    return struct.unpack_from("<%dH" % g.CARD_COUNT, wa, at)


def decode_weights(raw, bias: int, shift: int) -> dict:
    weights = {cid: max(0, (x - bias) >> shift) for cid, x in enumerate(raw, 1)}
    return {cid: w for cid, w in weights.items() if w}


def guess_encoding(raws):
    """(bias, shift) that makes every one of `raws` (pools not adding up to
    2048) add up to exactly 2048 once decoded: the TeaOnline tool's own
    values first, then biases just under the smallest weight. None if none."""
    if not raws:
        return None
    low = min(min(raw) for raw in raws)
    candidates = [TEAONLINE_ENCODING] + [(low - k, shift) for shift in (3, 1, 2, 4) for k in range(1 << shift)]
    for bias, shift in candidates:
        if bias >= 0 and all(sum(max(0, (x - bias) >> shift) for x in raw) == g.POOL_TOTAL for raw in raws):
            return bias, shift
    return None


def text_spans(slus: bytes):
    """[start, end) RAM ranges of the text banks that the text listing reads
    (the two offset tables and every string's bytes), or None when the
    listing cannot follow the file's text."""
    from .gamedata import _tl
    image = g._image(slus)
    spans = [(_tl.STRING_TABLE, _tl.STRING_TABLE + 2 * 0x4FA), (_tl.NAME_TABLE, _tl.NAME_TABLE + 2 * 0x360)]
    try:
        glyphs = _tl.glyph_characters(image)
        for bank in _tl.banks(image):
            ops, _ = _tl.decode_bank(image, bank, glyphs)
            spans += [(bank.base + op.offset, bank.base + op.offset + op.length) for op in ops.values()]
    except Exception:
        return None
    return _merge(spans, 0)


def _where(address: int) -> str:
    if address < 0x80010000:
        return f", in the executable's header (file offset 0x{address - kit.HEADER_ADDRESS:X})"
    for low, high, name in TEXT_BANKS:
        if low <= address < high:
            return f", in {name}"
    return ""


def describe_places(retail_slus: bytes, slus: bytes, pieces) -> list:
    """Report lines for changed file-offset pieces of the executable, grouped
    when close: RAM addresses, bytes, and the jumps that reach them."""
    groups = []
    for start, end in sorted(pieces):
        if groups and start - groups[-1][1] <= MERGE_GAP:
            groups[-1][1:] = [end, groups[-1][2] + end - start]
        else:
            groups.append([start, end, end - start])
    # The header's bytes are where the BIOS leaves them (the kit runs code there).
    places = [(start + (kit.HEADER_ADDRESS if start < 0x800 else g.EXE_DELTA),
               end + (kit.HEADER_ADDRESS if start < 0x800 else g.EXE_DELTA), count) for start, end, count in groups]
    callers = jumps_into(retail_slus, slus, [(start, end) for start, end, _ in places])
    lines = []
    for start, end, count in places[:PLACES_SHOWN]:
        reached = callers[(start, end)]
        more = f" and {len(reached) - 4} more" if len(reached) > 4 else ""
        lines.append(f"  0x{start:08X}-0x{end:08X} ({count} bytes{_where(start)}"
                     f"{'; reached by ' + ', '.join(reached[:4]) + more if reached else ''})")
    if len(places) > PLACES_SHOWN:
        lines.append(f"  ... and {len(places) - PLACES_SHOWN} more places")
    return lines


# --- text ---------------------------------------------------------------------------

USES_LABELS = re.compile(r"\{:L|\{(jump|call|if|choose|f8 1[78]|f8 2[78])\b")
_items = manifest.listing_items
CARD_BANKS = {"names": (0x8000, "name"), "descriptions": (0xD100, "description")}
# The name entry's own strings (the password overlay's box, three lines):
# a mod that turns them into its own menus (a starter deck
# chooser after YES) needs its code, and a menu taller than the box stops
# the retail text engine for good (TextBox_BuildStep waits on a page in a
# loop, func_80039794). They stay retail's.
NAME_ENTRY_IDS = range(0xF0, 0x100)


def _card_ids(bank: str, key: str) -> list:
    """The card ids an item of the names or descriptions bank is for."""
    if bank not in CARD_BANKS:
        return []
    first = CARD_BANKS[bank][0]
    return [i - first for i in manifest.item_ids(key) if 1 <= i - first <= g.CARD_COUNT]


def _card_item(bank: str, key: str) -> bool:
    """A card's name or text, which cards[] carries unless the text file must."""
    if bank == "descriptions":
        return True
    return bank == "names" and bool(manifest.item_ids(key)) and \
        len(_card_ids(bank, key)) == len(manifest.item_ids(key))


class _PackedTexts:
    """An executable whose descriptions bank holds packed card texts."""

    def __init__(self, image, memory: bytes):
        self.image, self.memory, self.data = image, memory, image.data

    def bytes(self, address: int, count: int) -> bytes:
        if address == g.DESCRIPTION_BANK and count == 0x10000:
            return self.memory
        return self.image.bytes(address, count)

    def __getattr__(self, name):
        return getattr(self.image, name)


def wa_description_listing(image, texts: dict, names: dict) -> str:
    """The descriptions a mod keeps in WA_MRG.MRG as listing items: packed
    into banks of under 64 KB (they are plain strings, no jumps), each
    listed as the executable's own bank would be."""
    from .gamedata import _tl
    out, group, size = [], [], 0
    groups = []
    for cid in sorted(texts):
        if size + len(texts[cid]) > 0xF000:
            groups.append(group)
            group, size = [], 0
        group.append(cid)
        size += len(texts[cid])
    groups.append(group)
    for group in groups:
        memory = bytearray(0x10000)
        bank = _tl.Bank("descriptions", g.DESCRIPTION_BANK)
        at = 0x10                                    # offset 0 means "no string"
        for cid in group:
            memory[at:at + len(texts[cid])] = texts[cid]
            bank.ids[0xD100 + cid] = at
            at += len(texts[cid])
        out.append(_tl.write_listing(_PackedTexts(image, bytes(memory)), [bank], names))
    return "\n".join(out)


def modded_listing(modded_slus: bytes, modded_wa: bytes, report: list) -> str:
    """The modified executable's text, bank by bank: a bank the listing
    cannot follow (its bytes are the mod's code) is left out and reported;
    card texts a mod keeps in WA_MRG.MRG are listed from there."""
    from .gamedata import _tl
    image = g._image(modded_slus)
    names = g.plain_names(image, _tl.glyph_characters(image))
    parts = []
    for bank in _tl.banks(image):
        if bank.name == "descriptions" and modded_wa and g.wa_descriptions(modded_slus, modded_wa):
            parts.append(wa_description_listing(image, g.description_bytes(modded_slus, modded_wa), names))
            report.append("text: the card texts are in WA_MRG.MRG (256 bytes a card from 0x2400000, sector "
                          f"{g.WA_TEXT_BASE // 2048}), where the mod's code loads them; read from there")
            continue
        try:
            parts.append(_tl.write_listing(image, [bank], names))
        except Exception as problem:      # a text bank the listing cannot follow
            report.append(f"text: the modified {bank.name} bank could not be read ({problem}); its strings are not "
                          "imported")
    return "\n".join(parts)


def text_changes(retail_slus: bytes, modded_slus: bytes, report: list, modded_wa: bytes = b"",
                 card_fields: dict = None):
    """(A partial listing of the text that differs, {(card id, field): its
    item}), the listing None when nothing differs. Card names and texts are
    left to cards[], except the `card_fields` ({field: card ids}) the text
    file must carry. A bank whose changed strings jump anywhere is written
    whole, so every place they name is in the file."""
    from .gamedata import _tl
    card_fields = card_fields or {}
    before = _items(_tl.write_listing(g._image(retail_slus)))
    after = _items(modded_listing(modded_slus, modded_wa, report))
    out, carried = [], {}

    def wanted(bank, key):
        if not _card_item(bank, key):
            return True
        field = CARD_BANKS.get(bank, (0, ""))[1]
        return any(cid in card_fields.get(field, ()) for cid in _card_ids(bank, key))

    for bank in ("dialog", "names", "descriptions"):
        old, new = before.get(bank, {}), after.get(bank, {})
        if not new:
            continue
        changed = [k for k in new if old.get(k) != new[k] and wanted(bank, k)]
        gone = [k for k in old if k not in new and not _card_item(bank, k)]
        if not changed and not gone:
            continue
        whole = bool(gone) or any(not k.startswith("[") or USES_LABELS.search(new[k]) for k in changed)
        keys = [k for k in new if wanted(bank, k)] if whole else changed
        if bank == "dialog":
            kept = [k for k in keys if any(i in NAME_ENTRY_IDS for i in manifest.item_ids(k))
                    and old.get(k) != new[k] and "{:L" not in new[k].split("\n")[0]]
            if kept:
                keys = [k for k in keys if k not in kept]
                report.append(f"text: the name entry's strings {', '.join(k for k in kept)} stay retail's: the mod "
                              "makes them its own menus (a starter deck chooser after the name), which need its "
                              "code, and a menu taller than the name box's three lines stops the game")
        out.append(f"@bank {bank}\n")
        # No blank line after an item that runs on: a game from before the
        # listing passed over it reads it as a line break of the string's.
        out += [new[k] + ("" if new[k].endswith("{cont}") else "\n") for k in keys]
        for k in keys:
            for cid in _card_ids(bank, k):
                carried[(cid, CARD_BANKS[bank][1])] = new[k]
        report.append(f"text: {len(changed)} strings of the {bank} bank differ" +
                      ("; the bank is written whole (its strings jump)" if whole else ""))
    if not out:
        return None, carried
    head = ("# Text of a modified game that differs from retail, written by the FM Editor's importer\n"
            "# (notes/translation.md). Card names and texts are in mod.json, except those with color\n"
            "# or icon codes and those the mod left empty, which only this file can carry.\n\n")
    return head + "\n".join(out), carried


# --- the import ------------------------------------------------------------------------

def _line_ends(text: str) -> str:
    return "\n".join(line.rstrip(" ") for line in text.split("\n"))


def _has_codes(text: bytes) -> bool:
    return any(0xF6 <= b < 0xFE for b in text)


def coded_card_texts(retail_files, modded_files) -> dict:
    """{field: card ids} of the names and texts that only a text listing can
    carry: changed ones with a color or icon code in them, and texts the
    mod left empty (cards.c reads "" as "not set")."""
    from .gamedata import _tl
    image, retail_image = g._image(modded_files.slus), g._image(retail_files.slus)
    out = {"name": set(), "description": set()}
    for cid in range(1, g.CARD_COUNT + 1):
        name = g.text_bytes(image, g.NAME_BANK + image.u16(g.NAME_TABLE + cid * 2), 128)
        old = g.text_bytes(retail_image, g.NAME_BANK + retail_image.u16(g.NAME_TABLE + cid * 2), 128)
        if name != old and _has_codes(name):
            out["name"].add(cid)
    texts, old_texts = g.description_bytes(modded_files.slus, modded_files.wa), g.description_bytes(retail_files.slus)
    for cid, text in texts.items():
        if text != old_texts[cid] and (_has_codes(text) or text == b"\xFF"):
            out["description"].add(cid)
    return out


def decode_drop_pools(retail, modded, retail_files, modded_files) -> list:
    """Decode the modded drop pools in place when the mod stores them
    encoded (DRAW_ADD); report lines saying which reading was used."""
    changed = [(d, p) for d in range(len(modded.pools)) for p in DROP_POOLS
               if modded.pools[d][p] != retail.pools[d][p]]
    if not changed:
        return []
    found = draw_code_encoding(retail_files.slus, modded_files.slus)
    where = f"the draw at 0x{DRAW_ADD:08X} jumps to the mod's code at 0x{found[2]:08X}" if found else ""
    extra = kit.extra_draws(retail_files.slus, modded_files.slus)
    if not found and extra and extra.encoding:
        found = extra.encoding
        where = (f"the prize draw at 0x{kit.RESULT_DRAW:08X} jumps to the mod's code at 0x{extra.code:08X}, which "
                 f"calls 0x{found[2]:08X}")
    notes = []
    if found:
        bias, shift, code = found
        decode = changed
        notes.append(f"pools: the drop pools are encoded: {where}, which reads each weight as max(0, (raw - {bias}) >> "
                     f"{shift}); the {len(decode)} changed drop pools were decoded that way (the deck pools are not "
                     "encoded)")
        kept = [f"{g.DUELIST_NAMES[d]} {p}" for d in range(len(modded.pools)) for p in DROP_POOLS
                if (d, p) not in changed]
        if kept:
            notes.append(f"pools: {len(kept)} drop pools are as retail wrote them (for example {'; '.join(kept[:3])})"
                         "; kept as retail, although the mod's draw would read them encoded")
    else:
        decode = [(d, p) for d, p in changed if sum(modded.pools[d][p].values()) != g.POOL_TOTAL]
        guess = guess_encoding([_raw_pool(modded_files.wa, d, p) for d, p in decode])
        if not guess:
            return []
        bias, shift = guess
        notes.append(f"pools: {len(decode)} changed drop pools do not add up to 2048 but do once each weight is read "
                     f"as max(0, (raw - {bias}) >> {shift}), the way the TeaOnline drop tool encodes them; the "
                     f"mod's draw code at 0x{DRAW_ADD:08X} was not recognized, so they were decoded that way")
    for d, p in decode:
        modded.pools[d][p] = decode_weights(_raw_pool(modded_files.wa, d, p), bias, shift)
    return notes


def _names(project: Project, ids, most: int = 8) -> str:
    ids = sorted(ids)
    shown = ", ".join(project.card_label(i) if i in project.cards else str(i) for i in ids[:most])
    return shown + (f" and {len(ids) - most} more" if len(ids) > most else "")


def read_equip_bitmaps(project: Project, modded, retail_files, modded_files) -> list:
    """The equips when the mod's Duel_CheckEquip reads a bitmap per equip
    (kit.equip_bitmaps): every equip card's monsters as the mod's code
    decides. Records of cards the port's equips cannot take are reported."""
    table = kit.equip_bitmaps(retail_files.slus, modded_files.slus, modded_files.wa)
    if table is None:
        return []
    cards = modded.cards
    monsters = {cid for cid, card in cards.items() if card.is_monster()}
    equips = {cid for cid, card in cards.items() if card.type == g.TYPE_EQUIP}
    project.equips = {e: table.allowed(e) & monsters for e in equips}
    project.equips = {e: m for e, m in project.equips.items() if m or e in project.retail.equips}
    for e, m in project.retail.equips.items():
        if e not in equips:         # no longer an equip card in the mod: nothing to say about it
            project.equips[e] = set(m)
    notes = [f"equips: the mod's {table.where} reads its table as bitmaps of {kit.EQUIP_RECORD} bytes per card "
             f"({len(table.records)} records{'' if table.limit is None else f', {table.limit} read'}); every "
             "equip card's monsters were read that way"]
    others = [key for key, _ in table.records if key not in equips]
    if others:
        notes.append(f"equips: {len(others)} records are for cards that are not equip cards ({_names(project, others)}): "
                     "monsters or magic used as equips (\"Union\"); the port's equips take equip cards only "
                     "(src/pc/cards/tables.c: \"not an equip card\"), so they are not imported")
    if table.by_monster:
        notes.append(f"equips: {len(table.by_monster)} records name a monster and the equips it takes "
                     f"({_names(project, [m for m, _ in table.by_monster])}); those equips' lists include it")
    if table.blocked:
        notes.append(f"equips: no equip equips {_names(project, table.blocked)}, as the mod's code decides")
    return notes


def check_rituals(project: Project, modded) -> list:
    """No rituals when the ritual table holds no recipe the game could
    read: the kit keeps code there and takes the rituals away."""
    cards = modded.cards
    valid = {r: rec for r, rec in project.rituals.items()
             if r in cards and cards[r].type == g.TYPE_RITUAL and all(1 <= c <= g.CARD_COUNT for c in rec)}
    bad = len(project.rituals) - len(valid)
    if bad and len(valid) * 2 < len(project.rituals):
        valid = {}      # mostly not recipes: the few that look like one are the code's bytes by chance
    # A retail ritual the mod made another kind of card: nothing to say (the
    # port refuses a rituals entry for a card that is not a ritual).
    other = {r: rec for r, rec in project.retail.rituals.items()
             if r not in valid and cards.get(r) and cards[r].type != g.TYPE_RITUAL}
    project.rituals = {**valid, **other}
    notes = [f"rituals: {len(other)} retail ritual cards are other cards in the mod; no rule names them"] if other else []
    if not bad:
        return notes
    if valid:
        return notes + [f"rituals: {bad} records of the modified ritual table name no ritual card or no card at all; "
                        "left out"]
    return notes + [f"rituals: the modified ritual table holds no recipe ({bad} records naming no ritual card or no "
                    "card: code, or another format); the rituals were imported as removed, as the game finds none there"]


def _starter_sums(wa: bytes) -> list:
    stride = g.STARTER_LENGTH // 7
    return [sum(struct.unpack_from("<%dH" % g.CARD_COUNT, wa, g.STARTER_BASE + k * stride + 2)) for k in range(7)]


def port_wa(retail_wa: bytes, modded_wa: bytes, keep_retail) -> bytes:
    """The modified archive with `keep_retail` ([start, end) regions: the
    tables mod.json carries, and what the port cannot read the mod's way)
    put back to the retail bytes."""
    out = bytearray(modded_wa)
    for start, end in keep_retail:
        end = min(end, len(retail_wa), len(out))
        if start < end:
            out[start:end] = retail_wa[start:end]
    return bytes(out)


def wa_data(project: Project, retail_files, modded_files, report: list) -> list:
    """The "data" entries that carry the rest of WA_MRG.MRG: patches and
    sector replacements at the retail disc's sectors when they are few, the
    whole file otherwise. Either way the structured tables (mod.json's
    fusions, equips, rituals and pools) stay retail's, so the port's rules
    apply over the disc's own tables."""
    wa_old, wa_new = retail_files.wa, modded_files.wa
    keep = wa_structured_regions()
    starters = _starter_sums(wa_new) if len(wa_new) >= g.STARTER_BASE + g.STARTER_LENGTH else []
    if starters and min(starters) < g.POOL_TOTAL // 2 and wa_new[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH] != \
            wa_old[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH]:
        keep.append((g.STARTER_BASE, g.STARTER_BASE + g.STARTER_LENGTH))
        report.append(f"WA_MRG.MRG: the starter decks are counts of cards (they add up to {', '.join(map(str, starters))}"
                      "), not weights of 2048; the port has no rule for a counted starter deck, so they stay retail's")
    for sector, sectors, what in g.PROGRAMS:
        start, end = sector * 2048, (sector + sectors) * 2048
        changed = sum(1 for a, b in zip(wa_old[start:end], wa_new[start:end]) if a != b)
        if changed:
            keep.append((start, end))
            report.append(f"WA_MRG.MRG: {what} (sector {sector}) differs in {changed} bytes: the mod's own code and "
                          "data there; the port runs its own code for that program over its data, so it stays "
                          "retail's")
    runs = _trim(wa_old, wa_new, _subtract(_runs(wa_old, wa_new, 0, min(len(wa_old), len(wa_new))), keep))
    patches, regions, places = [], [], {}
    for start, end in runs:
        count, runs_there = places.get(describe_wa(start), (0, 0))
        places[describe_wa(start)] = (count + end - start, runs_there + 1)
        if end - start <= PATCH_LIMIT:
            patches.append((start, end))
            continue
        first, last = start // 2048, (end + 2047) // 2048
        if regions and first <= regions[-1][1]:
            regions[-1][1] = max(last, regions[-1][1])
        else:
            regions.append([first, last])
    whole = None
    if len(wa_new) != len(wa_old):
        whole = f"its size differs ({len(wa_new)} bytes, retail {len(wa_old)})"
    elif len(patches) > WA_PATCHES_MOST or len(regions) > WA_REGIONS_MOST:
        whole = (f"{len(patches)} patches and {len(regions)} sector runs would be more than the port holds for every "
                 f"mod together (1024 and 64, src/pc/mods/mods.c PATCHES_MAX and REGIONS_MAX)")
    if whole:
        project.files["WA_MRG.MRG"] = port_wa(wa_old, wa_new, keep)
        report.append(f"WA_MRG.MRG: {whole}; the whole file is replaced, with the tables mod.json carries kept as "
                      "retail's")
        data = [{"file": WA_FILE, "replace": "WA_MRG.MRG"}]
    else:
        data = [{"file": WA_FILE, "patch": [{"at": f"0x{s:X}", "bytes": wa_new[s:e].hex(" ").upper()}
                                            for s, e in patches]}] if patches else []
        clean = None
        for first, last in regions:
            path = f"data/wa_{first:05X}.bin"
            if any(s < last * 2048 and e > first * 2048 for s, e in keep):
                clean = clean or port_wa(wa_old, wa_new, keep)
                project.files[path] = clean[first * 2048:last * 2048]
            else:
                project.files[path] = wa_new[first * 2048:last * 2048]
            # "lba" is a sector of the disc the port runs, the retail one.
            data.append({"lba": retail_files.wa_lba + first, "sectors": last - first, "replace": path})
    for place, (count, runs_there) in sorted(places.items()):
        report.append(f"WA_MRG.MRG: {place}: {count} bytes in {runs_there} places changed, carried as data")
    return data


def fixed_decks(project: Project, retail, modded, retail_files, modded_files) -> list:
    """Fixed decks when the mod's shuffle deals counts of copies (A4): each
    opponent's deck is the forty cards that shuffle deals from its pool,
    and its weighted pool stays retail's."""
    if not kit.deals_by_count(retail_files.slus, modded_files.slus):
        return []
    short, walked = [], []
    for d in range(len(modded.pools)):
        pool = modded.pools[d]["deck"]
        deck = kit.dealt_by_count(pool)
        if sum(deck.values()) < kit.DECK_SIZE:
            short.append(g.DUELIST_NAMES[d])
            project.pools[d]["deck"] = dict(retail.pools[d]["deck"])
            modded.pools[d]["deck"] = dict(retail.pools[d]["deck"])
            continue
        if sum(pool.values()) != kit.DECK_SIZE:
            walked.append(g.DUELIST_NAMES[d])
        set_fixed_deck(project, d, deck)      # the port deals this; the weighted pool stays retail's
        project.pools[d]["deck"] = dict(retail.pools[d]["deck"])
        modded.pools[d]["deck"] = dict(retail.pools[d]["deck"])       # nothing left to scale
    notes = [f"decks: the mod's Duel_ShuffleDeck deals each deck pool as counts of copies, in card order up to "
             f"{kit.DECK_SIZE}, with no limit of three (signature A4); {len(project.fixed)} decks written as "
             "fixed decks"]
    if walked:
        notes.append(f"decks: {len(walked)} pools do not add up to {kit.DECK_SIZE} ({', '.join(walked[:4])}"
                     f"{'...' if len(walked) > 4 else ''}): the fixed deck is what that shuffle deals from them, "
                     "the first cards by id")
    if short:
        notes.append(f"decks: {len(short)} pools hold fewer than {kit.DECK_SIZE} cards ({', '.join(short[:4])}); "
                     "the mod's shuffle would never finish; left as retail's")
    return notes


AI_COMMANDS = 0x800916E0, 0x800916E0 + 4 * 72    # gAiScript_apfnCommand
STAT_CAP_SITES = (0x800170E0, 0x80017200)       # Duel_CalcCardStats
OPPONENT_FIELD = 0x80024E08                     # func_80024DC8: the opponent's home field
CARD_FRAME = 0x8002C290                         # func_8002BFCC: the card's frame


def kit_rules(project: Project, modded, retail_files, modded_files) -> tuple:
    """(report lines, README lines): the rules the kit's code sets that
    mod.json has keys for, read from the code and its tables, and what it
    changes that no key carries, in the game's terms."""
    retail_slus, slus = retail_files.slus, modded_files.slus
    notes, readme, missing = [], [], []
    memory, retail = kit.Memory(slus), kit.Memory(retail_slus)
    cards = modded.cards

    chest = kit.chest_overflow(retail_slus, slus)
    if chest:
        limit, pay = chest
        project.other["chest_overflow"] = {"limit": limit, "starchips": pay}
        notes.append(f"rules: the mod's Duel_AwardCard keeps {limit} copies of a card in the chest and pays {pay} "
                     f"starchips for each card past them (A3): \"chest_overflow\"")
        readme.append(f"- The chest keeps {limit} copies of a card; each card won past them is worth {pay} starchips.")
    terrain = kit.terrain_bonus(retail_slus, slus)
    if terrain:
        table = {kit.TERRAIN_NAMES[t - 1]: {g.TYPE_NAMES[k]: v for k, v in sorted(values.items())}
                 for t, values in terrain.table.items() if values}
        table["replace"] = True
        project.other["terrain_bonus"] = table
        notes.append(f"rules: the terrain bonuses are the mod's, from {terrain.where} (A9): \"terrain_bonus\", every "
                     "pair, and no bonus for the others")
        readme.append("- Each field card's terrain gives the monster types the mod's bonuses (in steps of 10, "
                      "not the disc's +500/-500).")
        if terrain.more_terrains > 0:
            missing.append(f"{terrain.more_terrains} terrains of the mod's own past the six (7 and up, some opponents' "
                           "home fields): the port has six")
        if terrain.by_attribute:
            missing.append(f"terrains from {terrain.by_attribute} up that favour a monster's attribute, not its type")
    traps = kit.trap_thresholds(retail_slus, slus)
    if traps:
        project.other["trap_thresholds"] = traps
        notes.append(f"rules: the attack traps' thresholds are the mod's (A8): \"trap_thresholds\" "
                     f"({', '.join(f'{k} {v}' for k, v in traps.items())})")
        readme.append("- Attack traps spring up to the mod's attack thresholds.")
        missing.append("which cards act as which attack trap (the mod's lists, in its rewritten "
                       "Duel_SelectAttackTrap): the disc's six traps keep their places")
    bonus = kit.equip_bonus(retail_slus, slus)
    if bonus:
        equips = {cid: v for cid, v in bonus.fixed.items() if cid in cards and cards[cid].type == g.TYPE_EQUIP}
        others = [cid for cid in bonus.fixed if cid not in equips]
        for cid, points in sorted(equips.items()):     # the Cards tab's Equip bonus
            project.set_equip_bonus(cid, points)
        notes.append(f"rules: the mod's DuelScene_UpdateCardPlacement (code at {bonus.where}) sets {len(equips)} "
                     f"equips' bonuses (A7): \"equips\" \"bonus\"; the rest keep +500")
        if equips:
            readme.append(f"- {len(equips)} equips add the mod's own bonus instead of +500.")
        if others:
            missing.append(f"bonuses the mod gives cards that are not equip cards ({_names(project, others)}): "
                           "monsters used as equips and magic")
        if bonus.conditional:
            missing.append(f"{len(bonus.conditional)} equip bonuses that grow with a count the mod keeps "
                           f"({_names(project, [c for c, _, _ in bonus.conditional])})")
        if bonus.special:
            missing.append(f"{len(bonus.special)} equips (or more) with an effect of their own in the mod's code "
                           f"({_names(project, bonus.special)}): they keep +500 (Megamorph +1000)")
    draws = kit.extra_draws(retail_slus, slus)
    if draws and draws.count:
        # "limits" "card_drops" locks the player's Game > Card drops while
        # the mod is applied (1 to 99, the setting's range).
        count = min(max(draws.count, 1), values.CARD_DROPS_MAX)
        limits = project.other.get("limits")
        if not isinstance(limits, dict):
            limits = project.other["limits"] = {}
        limits["card_drops"] = count
        notes.append(f"rules: the mod draws {draws.count} prizes a win (A1: its loop at 0x{draws.code:08X}): "
                     f"\"limits\" \"card_drops\" {count}, which locks Game > Card drops while the mod is applied")
        if count != draws.count:
            missing.append(f"{draws.count} prizes a win: the port deals at most {values.CARD_DROPS_MAX}")
        readme.append(f"- The mod gives {count} cards a win: Game > Card drops shows {count}, set by the mod, "
                      "while it is applied.")
    if any(memory.bytes(a, 0x40) != retail.bytes(a, 0x40) and b"\x31\x75" in memory.bytes(a, 0x120)
           for a in STAT_CAP_SITES):
        missing.append("ATK, DEF and life points up to 30000 (5 digits): the port keeps 9999")
    if memory.word(OPPONENT_FIELD) != retail.word(OPPONENT_FIELD):
        missing.append("each opponent's home field from the mod's table")
    start, end = AI_COMMANDS
    changed = [k for k in range(0, end - start, 4) if memory.word(start + k) != retail.word(start + k)]
    if changed:
        missing.append(f"the opponents' play (AI): {len(changed)} of its script commands are the mod's code, and "
                       "the mod's scripts in WA_MRG.MRG expect them, so they play by the disc's commands")
    if memory.bytes(CARD_FRAME, 16) != retail.bytes(CARD_FRAME, 16):
        missing.append("each card's frame color by its class (Effect, Union...)")
    if any(slus[0x88:0x800]):
        notes.append("rules: the executable's header holds code (0x8000B070 and up): a mod made with the kit "
                     "that patches the duel in MIPS (A16)")
    effects = sum(1 for card in project.cards.values() if "Effect" in card.description)
    if effects:
        missing.append(f"monster effects: {effects} cards say «Effect» in their text, which the mod's code "
                       "carries out in battle and when summoned")
    for line in missing:
        notes.append(f"not imported: {line}")
    return notes, readme, missing


def write_readme(project: Project, readme: list, missing: list):
    if not readme and not missing:
        return
    lines = [f"{project.info.name}", "", "Imported by the FM Editor from a modified game. It plays close to the "
             "mod's own rules; what the mod does in code of its own is not here.", ""]
    if readme:
        lines += ["What the port does the mod's way:", ""] + readme + [""]
    if missing:
        lines += ["What the mod changes that this import cannot bring:", ""] + [f"- {m[0].upper()}{m[1:]}."
                                                                             for m in missing] + [""]
    lines.append("import-report.txt has the details.")
    project.files["README.txt"] = ("\n".join(lines) + "\n").encode("utf-8")


def import_modded(retail_files, modded_files, mod_id: str = "imported-mod", name: str = None) -> ImportResult:
    retail = g.load_game(retail_files)
    report = []
    try:
        modded = g.load_game(modded_files)
    except Exception as problem:
        raise ValueError(f"the modified files could not be read as the game's tables: {problem}")
    project = Project(retail)
    project.info.id = mod_id
    project.info.name = name or mod_id
    project.info.description = "Imported from a modified game by the FM Editor."
    result = ImportResult(project, report)
    for note in modded.notes:
        report.append(f"note: {note}")
        result.unhandled += 1

    # Cards and the rule tables: the editor's own diff.
    spaced = 0
    for cid, card in modded.cards.items():
        card = card.copy()
        old = retail.cards.get(cid)
        for name in ("name", "description"):
            if old is not None and getattr(card, name) != getattr(old, name) and \
                    _line_ends(getattr(card, name)) == _line_ends(getattr(old, name)):
                setattr(card, name, getattr(old, name))     # only spaces at line ends differ: the same text
                spaced += 1
        project.cards[cid] = card
    drop_notes = decode_drop_pools(retail, modded, retail_files, modded_files)
    project.fusions = dict(modded.fusions)
    project.equips = {e: set(m) for e, m in modded.equips.items()}
    equip_notes = read_equip_bitmaps(project, modded, retail_files, modded_files)
    project.rituals = dict(modded.rituals)
    ritual_notes = check_rituals(project, modded)
    project.pools = [{p: dict(modded.pools[d][p]) for p in g.POOLS} for d in range(len(modded.pools))]
    changed_cards = sum(1 for cid in retail.cards if project.card_changed(cid))
    report.append(f"cards: {changed_cards} changed")
    if spaced:
        report.append(f"cards: {spaced} names or texts differ from retail only by spaces at the end of a line; "
                      "kept as retail")
    report.append(f"fusions: {sum(1 for p in set(retail.fusions) | set(modded.fusions) if retail.fusions.get(p) != modded.fusions.get(p))} pairs differ")
    report.append(f"equips: {sum(1 for e in set(retail.equips) | set(project.equips) if set(retail.equips.get(e, [])) != set(project.equips.get(e, [])))} equip cards differ")
    report += equip_notes
    report.append(f"rituals: {sum(1 for r in set(retail.rituals) | set(project.rituals) if retail.rituals.get(r) != project.rituals.get(r))} differ")
    report += ritual_notes
    pools_changed = sum(1 for d in range(len(retail.pools)) for p in g.POOLS if retail.pools[d][p] != modded.pools[d][p])
    report.append(f"pools: {pools_changed} of {len(retail.pools) * len(g.POOLS)} differ")
    report += drop_notes
    report += fixed_decks(project, retail, modded, retail_files, modded_files)
    off_total = []
    for d in range(len(modded.pools)):
        for p in g.POOLS:
            total = sum(modded.pools[d][p].values())
            if modded.pools[d][p] != retail.pools[d][p] and total != g.POOL_TOTAL:
                off_total.append(f"{g.DUELIST_NAMES[d]} {p}: {total}")
                project.pools[d][p] = normalize(project.pools[d][p])
    if off_total:
        report.append(f"pools: {len(off_total)} pools do not add up to 2048 in the modified game (for example "
                      f"{'; '.join(off_total[:3])}), which the game's draw needs; the mod likely changes the draw "
                      "in its code. They are scaled to 2048, keeping each card's share")

    # Text.
    card_fields = coded_card_texts(retail_files, modded_files)
    text, carried = text_changes(retail_files.slus, modded_files.slus, report, modded_files.wa, card_fields)
    if text:
        project.files["text.txt"] = text.encode("utf-8")
        project.other["text"] = "text.txt"
    for (cid, field), item in carried.items():
        value = manifest.plain_name(item) if field == "name" else manifest.listing_plain(item)
        setattr(project.cards[cid], field, value)
        project.text_cards.setdefault(cid, {})[field] = value
    for field, label in (("name", "names"), ("description", "texts")):
        ids = [cid for cid in card_fields.get(field, ()) if (cid, field) in carried]
        empty = [cid for cid in ids if field == "description" and not project.cards[cid].description]
        if ids:
            report.append(f"cards: {len(ids)} card {label} carry color or icon codes"
                          + (f" or are empty on purpose ({len(empty)} empty)" if empty else "")
                          + "; text.txt carries them (cards[] cannot)")
    blank = [cid for cid, card in project.cards.items() if cid <= g.CARD_COUNT and not card.name
             and (cid, "name") not in carried]
    for cid in blank:
        project.cards[cid].name = retail.cards[cid].name
    if blank:
        report.append(f"cards: {len(blank)} names could not be read; kept as retail's")

    # Rules the kit's code sets.
    rule_notes, readme, missing = kit_rules(project, modded, retail_files, modded_files)
    report += rule_notes
    result.unhandled += len(missing)
    write_readme(project, readme, missing)

    # The rest of the executable.
    slus_runs = _runs(retail_files.slus, modded_files.slus, 0, max(len(retail_files.slus), len(modded_files.slus)), 0)
    if len(retail_files.slus) != len(modded_files.slus):
        report.append(f"executable: its size differs ({len(modded_files.slus)} bytes); only the tables were read")
        result.unhandled += 1
    text_read = text_spans(modded_files.slus) or []      # what text.txt carries; nothing when unreadable
    handled = [(g.slus_offset(a), g.slus_offset(b)) for a, b in SLUS_HANDLED + text_read]
    named = [(g.slus_offset(a), g.slus_offset(b), label) for a, b, label in SLUS_REGIONS]
    for low, high, label in named:
        count = sum(min(e, high) - max(s, low) for s, e in slus_runs if s < high and e > low)
        if count:
            report.append(f"executable: {label} changed ({count} bytes); the port reads the executable's code "
                          "and tables natively, so this cannot be imported")
            result.unhandled += 1
    other = _subtract(slus_runs, handled + [(low, high) for low, high, _ in named])
    # Bytes the retail text used that the modified text no longer reads:
    # left-over text of a repacked bank, or the mod's code written over it.
    old_text = [(g.slus_offset(a), g.slus_offset(b)) for a, b in text_spans(retail_files.slus) or []]
    code = _subtract(other, old_text)
    leftover = _subtract(other, code)
    if code:
        report.append(f"executable: {sum(e - s for s, e in code)} other bytes changed: code patches, or the mod's "
                      "own code and data, which the native port cannot take:")
        report += describe_places(retail_files.slus, modded_files.slus, code)
        result.unhandled += 1
    if leftover:
        report.append(f"executable: {sum(e - s for s, e in leftover)} bytes where the retail text was changed, and "
                      "the modified text does not read them (text left over, or code):")
        report += describe_places(retail_files.slus, modded_files.slus, leftover)
        result.unhandled += 1

    # The rest of WA_MRG.MRG.
    data = wa_data(project, retail_files, modded_files, report)
    if data:
        project.other["data"] = data
    if result.unhandled:
        report.append(f"{result.unhandled} kind(s) of change could not be imported (above)")
    project.files["import-report.txt"] = ("\n".join(report) + "\n").encode("utf-8")
    return result


def save(result: ImportResult, folder) -> None:
    """Write the imported mod: mod.json and the files it names."""
    folder = Path(folder)
    manifest.save_mod(result.project, folder)
