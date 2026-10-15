#!/usr/bin/env python3
"""Translate MODEL.MRG's variant control modules into C.

Every MODEL.MRG record carries per-monster MIPS modules that the loader swaps
into 0x8013B000 (slot A) and 0x8017B000 (slot B); src/pc/guest/mips.c used to
interpret them. The 1,181 distinct modules of the North American disc are 324
programs (the module's first word names its program) with per-monster data,
and every program is self-contained: its code reaches the game only through
direct calls, and every data word pointing into its code is a switch table.

This script reads MODEL.MRG out of the user's disc (the folder
tools/pc/extract_disc.py writes, or the .bin image), follows each
program's code from its entry at +4 (direct calls, branches and switch tables),
checks that the slot B copy differs from slot A only by the relocation of the
module's own addresses, and writes C with the interpreter's semantics into the
build folder (src/pc/guest/model_recomp.h is its runtime contract). Nothing
derived from the disc is written into the checkout. Without the disc, or for
another MODEL.MRG, the table is empty and the interpreter runs the modules.

    python3 tools/pc/model_recomp.py [--disc PATH] [--out DIR]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/project"))
from disc_image import LOGICAL_BLOCK_SIZE, DiscError, Mode2Image, parse_directory_record, walk_iso  # noqa: E402

MODEL_SHA256 = "6a738960cfae167d6612f190c07cf0147f3bcc8c2dd97814e154fecc283e1d4b"  # config/slus_01411/files.sha256
RECORD_SECTORS = 276            # Model_LoadMonsterMerge: MODEL_MRG_SECTOR_COUNT
VARIANT_PHASES = {0: (180, 200), 1: (190, 210)}  # slot -> sectors of its position-0 and position-1 variants
SLOT_BASE = {0: 0x8013B000, 1: 0x8017B000}
DELTA = SLOT_BASE[1] - SLOT_BASE[0]
MODULE_SIZE = 0x5000
FILES_PER_CHUNK = 40000         # translated instructions per generated C file
GENERATOR_VERSION = 1


class Untranslatable(Exception):
    pass


def s16(value):
    return value - 0x10000 if value & 0x8000 else value


def find_disc():
    """The extracted folder's index (game/yfm-disc.txt) or a .bin image."""
    disc = os.environ.get("MEMORIES_DISC")
    if disc:
        return Path(disc)
    if (ROOT / "game" / "yfm-disc.txt").is_file():
        return ROOT / "game" / "yfm-disc.txt"
    found = sorted(glob.glob(str(ROOT / "game" / "*.bin")))
    return Path(found[0]) if found else None


def model_file(disc: Path) -> Path | None:
    """MODEL.MRG as a plain file of an extracted folder (tools/pc/extract_disc.py), else None."""
    if disc.name != "yfm-disc.txt":
        return None
    for line in disc.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields and fields[0] == "data" and fields[-1].upper().endswith("/DATA/MODEL.MRG"):
            return disc.parent / fields[-1]
    raise DiscError(f"{disc}: no plain DATA/MODEL.MRG in the index")


def read_model_mrg(disc: Path) -> bytes:
    plain = model_file(disc)
    if plain:
        return plain.read_bytes()
    image = Mode2Image(disc)
    pvd = image.read_extent(16, LOGICAL_BLOCK_SIZE)
    if pvd[1:6] != b"CD001":
        raise DiscError("LBA 16 is not an ISO9660 primary volume descriptor")
    for path, record in walk_iso(image, parse_directory_record(pvd, 156)):
        if path.upper() == "DATA/MODEL.MRG":
            return image.read_extent(record.extent_lba, record.size)
    raise DiscError("DATA/MODEL.MRG is not on the disc")


# ---------------------------------------------------------------------------
# Decoding: exactly the subset src/pc/guest/mips.c interprets.

def word_at(data, base, address):
    return struct.unpack_from("<I", data, address - base)[0]


def control(word, pc):
    """(kind, target) for a control transfer, else None. kinds: branch, likely,
    jump, call, return, switch."""
    op, rs, rt, fn = word >> 26, (word >> 21) & 31, (word >> 16) & 31, word & 63
    branch_target = (pc + 4 + (s16(word & 0xFFFF) << 2)) & 0xFFFFFFFF
    if op == 0 and fn == 8:
        return ("return", None) if rs == 31 else ("switch", None)
    if op == 0 and fn == 9:
        raise Untranslatable(f"jalr at {pc:08x}")
    if op == 2:
        return "jump", (pc & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
    if op == 3:
        return "call", (pc & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
    if op == 1:
        if rt in (0, 1):
            return "branch", branch_target
        if rt in (2, 3):
            return "likely", branch_target
        raise Untranslatable(f"regimm {rt:#x} at {pc:08x}")
    if 4 <= op <= 7:
        return "branch", branch_target
    if 0x14 <= op <= 0x17:
        return "likely", branch_target
    return None


PLAIN_SPECIAL = {0, 2, 3, 4, 6, 7, 0x0D, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x1A, 0x1B,
                 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2A, 0x2B}
PLAIN_OPS = {8, 9, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF, 0x12, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
             0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x32, 0x3A}


def check_plain(word, pc):
    op, rs, fn = word >> 26, (word >> 21) & 31, word & 63
    if word == 0:
        return
    if op == 0 and fn in PLAIN_SPECIAL:
        return
    if op == 0x12 and ((word >> 25) & 1 or rs in (0, 2, 4, 6)):
        return
    if op != 0 and op != 0x12 and op in PLAIN_OPS:
        return
    raise Untranslatable(f"instruction {word:08x} at {pc:08x}")


def jump_table(data, base, pc):
    """Targets of the GCC switch idioms ending at the `jr` at pc, as in
    the analysis: lui[/addiu] builds the table, addu indexes it, lw reads it."""
    reg = (word_at(data, base, pc) >> 21) & 31
    value, derived = {}, {}
    bound = lw_base = lw_offset = None
    start = max(base + 4, pc - 4 * 64)
    for at in range(start, pc, 4):
        w = word_at(data, base, at)
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        if op == 0x0F:
            value[rt] = (w & 0xFFFF) << 16
            derived.pop(rt, None)
        elif op == 0x09 and rs in value:
            value[rt] = (value[rs] + s16(w & 0xFFFF)) & 0xFFFFFFFF
            derived.pop(rt, None)
        elif op == 0 and (w & 63) == 0x21:
            source = value.get(rs, value.get(rt))
            if rd not in (rs, rt):
                value.pop(rd, None)
            derived.pop(rd, None)
            if source is not None:
                derived[rd] = source
        elif op == 0x0B:
            bound = w & 0xFFFF
            value.pop(rt, None)
            derived.pop(rt, None)
        elif op == 0x23 and rt == reg:
            lw_base, lw_offset = rs, s16(w & 0xFFFF)
        else:
            written = destination(w)
            if written is not None:
                value.pop(written, None)
                derived.pop(written, None)
    if lw_base is None or bound is None:
        raise Untranslatable(f"unresolved switch at {pc:08x}")
    origin = derived.get(lw_base, value.get(lw_base))
    if origin is None:
        raise Untranslatable(f"unresolved switch at {pc:08x}")
    table = (origin + lw_offset) & 0xFFFFFFFF
    targets = []
    for i in range(bound):
        entry = table + 4 * i
        if not base <= entry < base + MODULE_SIZE:
            raise Untranslatable(f"switch table at {table:08x} leaves the module")
        targets.append(word_at(data, base, entry))
    return table, targets


def destination(word):
    """The general register a plain instruction writes, or None."""
    op, rt, rd, fn = word >> 26, (word >> 16) & 31, (word >> 11) & 31, word & 63
    if op == 0:
        return rd if fn in (0, 2, 3, 4, 6, 7, 0x10, 0x12, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
                            0x2A, 0x2B) else None
    if op in (8, 9, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26):
        return rt
    if op == 0x12 and ((word >> 21) & 31) in (0, 2):
        return rt
    return None


def analyze(data, base):
    """{function start: body addresses}, {switch pc: (table, targets)}, externals."""
    inside = lambda a: base + 4 <= a < base + MODULE_SIZE and not a & 3
    functions, switches, externals = {}, {}, set()
    pending = [base + 4]
    while pending:
        start = pending.pop()
        if start in functions:
            continue
        body, queue = set(), [start]
        while queue:
            pc = queue.pop()
            while True:
                if not inside(pc):
                    raise Untranslatable(f"flow leaves the module at {pc:08x}")
                if pc in body:
                    break
                word = word_at(data, base, pc)
                kind = control(word, pc)
                body.add(pc)
                if kind is None:
                    check_plain(word, pc)
                    pc += 4
                    continue
                slot = word_at(data, base, pc + 4)
                if control(slot, pc + 4) is not None:
                    raise Untranslatable(f"control transfer in a delay slot at {pc + 4:08x}")
                check_plain(slot, pc + 4)
                body.add(pc + 4)
                what, target = kind
                if what == "call":
                    if inside(target):
                        pending.append(target)
                    elif target >= 0x80130000:
                        raise Untranslatable(f"call into another overlay at {pc:08x}")
                    else:
                        externals.add(target)
                    pc += 8
                elif what in ("branch", "likely"):
                    if not inside(target):
                        raise Untranslatable(f"branch out of the module at {pc:08x}")
                    queue.append(target)
                    unconditional = (word >> 26) == 4 and not (word >> 16) & 0x3FF or \
                        (word >> 26) == 1 and ((word >> 16) & 31) == 1 and not (word >> 21) & 31
                    if unconditional:
                        break
                    pc += 8
                elif what == "jump":
                    if not inside(target):
                        raise Untranslatable(f"jump out of the module at {pc:08x}")
                    queue.append(target)
                    break
                elif what == "return":
                    break
                else:
                    table, targets = jump_table(data, base, pc)
                    for target in targets:
                        if not inside(target):
                            raise Untranslatable(f"switch at {pc:08x} reaches {target:08x}")
                    switches[pc] = (table, targets)
                    queue.extend(targets)
                    break
        functions[start] = body
    return functions, switches, externals


# ---------------------------------------------------------------------------
# Programs: a module's first word names its code.

def modules(mrg):
    """slot -> [module bytes], every variant module of every record."""
    out = {0: [], 1: []}
    for record in range(len(mrg) // (RECORD_SECTORS * LOGICAL_BLOCK_SIZE)):
        for slot, sectors in VARIANT_PHASES.items():
            for sector in sectors:
                start = (record * RECORD_SECTORS + sector) * LOGICAL_BLOCK_SIZE
                out[slot].append(mrg[start:start + MODULE_SIZE])
    return out


def runs(addresses):
    out, ordered = [], sorted(addresses)
    for address in ordered:
        if out and out[-1][0] + out[-1][1] == address:
            out[-1][1] += 4
        else:
            out.append([address, 4])
    return [tuple(run) for run in out]


def run_bytes(data, base, slot_runs, delta):
    return b"".join(data[start + delta - base:start + delta - base + length] for start, length in slot_runs)


def build_program(group_a, group_b):
    """Analyze one program from its slot A and slot B modules."""
    base_a, base_b = SLOT_BASE[0], SLOT_BASE[1]
    first = group_a[0]
    functions, switches, externals = analyze(first, base_a)
    code = set().union(*functions.values())
    code_runs = runs(code | {base_a})          # the identifier word too: it names the program
    expected = run_bytes(first, base_a, code_runs, 0)
    for other in group_a[1:]:
        if run_bytes(other, base_a, code_runs, 0) != expected:
            raise Untranslatable("modules naming this program differ in code")
        for pc, (table, targets) in switches.items():
            if [word_at(other, base_a, table + 4 * i) for i in range(len(targets))] != targets:
                raise Untranslatable(f"switch table of {pc:08x} differs between modules")
    expected_b = run_bytes(group_b[0], base_b, code_runs, DELTA)
    for other in group_b[1:]:
        if run_bytes(other, base_b, code_runs, DELTA) != expected_b:
            raise Untranslatable("slot B modules naming this program differ in code")
    # Relocation, by evidence: compare each instruction with its slot B copy.
    relocated = set()
    for pc in code:
        a, b = word_at(first, base_a, pc), word_at(group_b[0], base_b, pc + DELTA)
        if a == b:
            if (a >> 26) == 0x0F and 0x8013 <= (a & 0xFFFF) <= 0x8014:
                raise Untranslatable(f"module address at {pc:08x} is not relocated")
            continue
        if (a >> 26) == 0x0F and (a & 0xFFFF0000) == (b & 0xFFFF0000) and (b & 0xFFFF) - (a & 0xFFFF) == DELTA >> 16:
            relocated.add(pc)
        elif (a >> 26) in (2, 3) and (b >> 26) == (a >> 26) and (b & 0x3FFFFFF) - (a & 0x3FFFFFF) == DELTA >> 2:
            pass                                 # internal jump or call: translated to a label or C call
        else:
            raise Untranslatable(f"slot B differs at {pc:08x}: {a:08x} {b:08x}")
    for pc, (table, targets) in switches.items():
        for i, target in enumerate(targets):
            if word_at(group_b[0], base_b, table + DELTA + 4 * i) != target + DELTA:
                raise Untranslatable(f"slot B switch table of {pc:08x} is not relocated")
    identifier_a = word_at(first, base_a, base_a)
    identifier_b = word_at(group_b[0], base_b, base_b)
    return dict(identifier=(identifier_a, identifier_b), functions=functions, switches=switches,
                relocated=relocated, data=first, runs=code_runs,
                digests=(hashlib.sha256(expected).digest(), hashlib.sha256(expected_b).digest()))


# ---------------------------------------------------------------------------
# C emission.

def imm32(word):
    return f"0x{s16(word & 0xFFFF) & 0xFFFFFFFF:X}u"


def plain_c(word, pc, relocated):
    """C for one non-control instruction (mips.c's `plain`)."""
    op, rs, rt, rd, sa, fn = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31, (word >> 6) & 31, \
        word & 63
    if word == 0:
        return ""
    addr = f"R({rs}) + {imm32(word)}"
    zimm = f"0x{word & 0xFFFF:X}u"

    def set_reg(reg, expression):
        return "" if reg == 0 else f"R({reg}) = {expression};"

    if op == 0:
        table = {
            0: lambda: set_reg(rd, f"R({rt}) << {sa}"),
            2: lambda: set_reg(rd, f"R({rt}) >> {sa}"),
            3: lambda: set_reg(rd, f"(uint32_t)((int32_t)R({rt}) >> {sa})"),
            4: lambda: set_reg(rd, f"R({rt}) << (R({rs}) & 31)"),
            6: lambda: set_reg(rd, f"R({rt}) >> (R({rs}) & 31)"),
            7: lambda: set_reg(rd, f"(uint32_t)((int32_t)R({rt}) >> (R({rs}) & 31))"),
            0x0D: lambda: "",
            0x10: lambda: set_reg(rd, "c->hi"),
            0x11: lambda: f"c->hi = R({rs});",
            0x12: lambda: set_reg(rd, "c->lo"),
            0x13: lambda: f"c->lo = R({rs});",
            0x18: lambda: f"Rc_Mult(c, R({rs}), R({rt}));",
            0x19: lambda: f"Rc_Multu(c, R({rs}), R({rt}));",
            0x1A: lambda: f"Rc_Div(c, R({rs}), R({rt}));",
            0x1B: lambda: f"Rc_Divu(c, R({rs}), R({rt}));",
            0x20: lambda: set_reg(rd, f"R({rs}) + R({rt})"),
            0x21: lambda: set_reg(rd, f"R({rs}) + R({rt})"),
            0x22: lambda: set_reg(rd, f"R({rs}) - R({rt})"),
            0x23: lambda: set_reg(rd, f"R({rs}) - R({rt})"),
            0x24: lambda: set_reg(rd, f"R({rs}) & R({rt})"),
            0x25: lambda: set_reg(rd, f"R({rs}) | R({rt})"),
            0x26: lambda: set_reg(rd, f"R({rs}) ^ R({rt})"),
            0x27: lambda: set_reg(rd, f"~(R({rs}) | R({rt}))"),
            0x2A: lambda: set_reg(rd, f"(uint32_t)((int32_t)R({rs}) < (int32_t)R({rt}))"),
            0x2B: lambda: set_reg(rd, f"(uint32_t)(R({rs}) < R({rt}))"),
        }
        return table[fn]()
    if op in (8, 9):
        return set_reg(rt, f"R({rs}) + {imm32(word)}")
    if op == 0xA:
        return set_reg(rt, f"(uint32_t)((int32_t)R({rs}) < {s16(word & 0xFFFF)})")
    if op == 0xB:
        return set_reg(rt, f"(uint32_t)(R({rs}) < {imm32(word)})")
    if op == 0xC:
        return set_reg(rt, f"R({rs}) & {zimm}")
    if op == 0xD:
        return set_reg(rt, f"R({rs}) | {zimm}")
    if op == 0xE:
        return set_reg(rt, f"R({rs}) ^ {zimm}")
    if op == 0xF:
        value = f"0x{(word & 0xFFFF) << 16:08X}u"
        return set_reg(rt, f"{value} + c->delta" if pc in relocated else value)
    if op == 0x12:
        if (word >> 25) & 1:
            return f"Memories_GteCommand(0x{word:08X}u);"
        return {0: lambda: set_reg(rt, f"Memories_GteReadData({rd})"),
                2: lambda: set_reg(rt, f"Memories_GteReadControl({rd})"),
                4: lambda: f"Memories_GteWriteData({rd}, R({rt}));",
                6: lambda: f"Memories_GteWriteControl({rd}, R({rt}));"}[rs]()
    loads = {0x20: "(uint32_t)(int32_t)(int8_t)Rc_L8({a})", 0x21: "(uint32_t)(int32_t)(int16_t)Rc_L16({a})",
             0x23: "Rc_L32({a})", 0x24: "Rc_L8({a})", 0x25: "Rc_L16({a})"}
    if op in loads:
        return set_reg(rt, loads[op].format(a=addr))
    if op == 0x22:
        return set_reg(rt, f"Rc_Lwl(R({rt}), {addr})")
    if op == 0x26:
        return set_reg(rt, f"Rc_Lwr(R({rt}), {addr})")
    stores = {0x28: "Rc_S8({a}, (uint8_t)R({t}));", 0x29: "Rc_S16({a}, (uint16_t)R({t}));",
              0x2A: "Rc_Swl({a}, R({t}));", 0x2B: "Rc_S32({a}, R({t}));", 0x2E: "Rc_Swr({a}, R({t}));"}
    if op in stores:
        return stores[op].format(a=addr, t=rt)
    if op == 0x32:
        return f"Memories_GteLoad({rt}, (void *)Rc_At({addr}));"
    if op == 0x3A:
        return f"Memories_GteStore({rt}, (void *)Rc_At({addr}));"
    raise Untranslatable(f"instruction {word:08x} at {pc:08x}")


def condition(word):
    op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
    if op == 1:
        return f"(int32_t)R({rs}) < 0" if rt in (0, 2) else f"(int32_t)R({rs}) >= 0"
    base = op - 0x10 if op >= 0x14 else op
    return {4: f"R({rs}) == R({rt})", 5: f"R({rs}) != R({rt})", 6: f"(int32_t)R({rs}) <= 0",
            7: f"(int32_t)R({rs}) > 0"}[base]


def function_name(start, identity):
    return f"MemoriesRecomp_F{start:08X}_{identity[:10]}"


def emit_function(program, start, body, names):
    data, base, relocated, switches = program["data"], SLOT_BASE[0], program["relocated"], program["switches"]
    word = lambda a: word_at(data, base, a)
    targets = set()
    for pc in body:
        kind = control(word(pc), pc)
        if kind and kind[0] in ("branch", "likely", "jump"):
            targets.add(kind[1])
        elif kind and kind[0] == "switch":
            targets.update(switches[pc][1])
    units = []
    order = sorted(body)
    consumed = set()
    for pc in order:
        if pc in consumed:
            continue
        w = word(pc)
        kind = control(w, pc)
        if kind is None:
            units.append((pc, [plain_c(w, pc, relocated)], pc + 4))
            continue
        delay = plain_c(word(pc + 4), pc + 4, relocated)
        if pc + 4 not in targets:
            consumed.add(pc + 4)
        what, target = kind
        here = f"0x{pc:08X}u + c->delta"
        if what == "branch":
            unconditional = (w >> 26) == 4 and not (w >> 16) & 0x3FF or \
                (w >> 26) == 1 and ((w >> 16) & 31) == 1 and not (w >> 21) & 31
            if unconditional:
                units.append((pc, [f"{delay} goto L_{target:08X};"], None))
            else:
                units.append((pc, [f"{{ int t = {condition(w)}; {delay} if (t) goto L_{target:08X}; }}"], pc + 8))
        elif what == "likely":
            units.append((pc, [f"if ({condition(w)}) {{ {delay} goto L_{target:08X}; }}"], pc + 8))
        elif what == "jump":
            units.append((pc, [f"{delay} goto L_{target:08X};"], None))
        elif what == "call":
            link = f"0x{pc + 8:08X}u + c->delta"
            if target in names:
                call = f"{names[target]}(c, {link});"
            else:
                call = f"R(2) = Memories_RecompNative(c, 0x{target:08X}u, {here});"
            units.append((pc, [f"R(31) = {link}; {delay} {call}"], pc + 8))
        elif what == "return":
            units.append((pc, [f"{{ uint32_t t = R(31); {delay} if (t != ra) Memories_RecompBadReturn(c, {here}, t, ra); "
                               "return; }"], None))
        else:
            rs = (w >> 21) & 31
            cases = " ".join(f"case 0x{t:08X}u: goto L_{t:08X};" for t in sorted(set(switches[pc][1])))
            units.append((pc, [f"{{ uint32_t t = R({rs}); {delay} switch (t - c->delta) {{ {cases} "
                               f"default: Memories_RecompBadJump(c, {here}, t); }} }}"], None))
    lines = [f"void {names[start]}(MemoriesRecompContext *c, uint32_t ra)", "{"]
    needed = set(targets)
    for index, (pc, code, flow) in enumerate(units):
        following = units[index + 1][0] if index + 1 < len(units) else None
        if flow is not None and flow != following:
            needed.add(flow)
    for index, (pc, code, flow) in enumerate(units):
        if pc in needed:
            lines.append(f"L_{pc:08X}:;")
        lines.extend("    " + line for line in code if line)
        following = units[index + 1][0] if index + 1 < len(units) else None
        if flow is not None and flow != following:
            if flow not in body:
                raise Untranslatable(f"flow from {pc:08x} leaves {start:08x}")
            lines.append(f"    goto L_{flow:08X};")
    lines.append("}")
    return lines, len(body)


def function_identity(program, start, body):
    data, base = program["data"], SLOT_BASE[0]
    digest = hashlib.sha256()
    digest.update(struct.pack("<I", start))
    for pc in sorted(body):
        digest.update(struct.pack("<IIB", pc, word_at(data, base, pc), pc in program["relocated"]))
        if pc in program["switches"]:
            digest.update(struct.pack(f"<{len(program['switches'][pc][1])}I", *program["switches"][pc][1]))
    return digest.hexdigest()


def generate_sources(programs):
    """{file name: text}: chunks of translated functions and the program table."""
    header = ["/* Generated by tools/pc/model_recomp.py from the user's MODEL.MRG: not for the checkout. */",
              "#define MEMORIES_RECOMP_GENERATED", '#include "pc/guest/model_recomp.h"', ""]
    emitted, prototypes, chunks, current, size = {}, [], [], [], 0
    entries = []
    for program in programs:
        names = {}
        for start, body in program["functions"].items():
            names[start] = function_name(start, function_identity(program, start, body))
        for start, body in sorted(program["functions"].items()):
            name = names[start]
            if name in emitted:
                continue
            lines, count = emit_function(program, start, body, names)
            emitted[name] = True
            prototypes.append(f"void {name}(MemoriesRecompContext *c, uint32_t ra);")
            current.extend(lines + [""])
            size += count
            if size >= FILES_PER_CHUNK:
                chunks.append(current)
                current, size = [], 0
        entries.append((program, names[SLOT_BASE[0] + 4]))
    if current:
        chunks.append(current)
    files = {"model_recomp_functions.h": "\n".join(
        ["/* Generated by tools/pc/model_recomp.py. */", "#ifndef MEMORIES_MODEL_RECOMP_FUNCTIONS_H",
         "#define MEMORIES_MODEL_RECOMP_FUNCTIONS_H", '#include "pc/guest/model_recomp.h"', *prototypes,
         "#endif", ""])}
    for index, chunk in enumerate(chunks):
        files[f"model_recomp_{index:02d}.c"] = "\n".join(header + ['#include "model_recomp_functions.h"', ""] + chunk)
    table = ["/* Generated by tools/pc/model_recomp.py from the user's MODEL.MRG: not for the checkout. */",
             '#include "pc/guest/model_recomp.h"']
    if entries:
        table.append('#include "model_recomp_functions.h"')
    for index, (program, _) in enumerate(entries):
        flat = ", ".join(f"0x{start:08X}u, 0x{length:X}u" for start, length in program["runs"])
        table.append(f"static const uint32_t runs_{index}[] = {{{flat}}};")
    table.append("const MemoriesModelProgram Memories_ModelPrograms[] = {")
    for index, (program, entry) in enumerate(entries):
        digests = ", ".join("{" + ", ".join(f"0x{b:02X}" for b in digest) + "}" for digest in program["digests"])
        table.append(f"    {{{{0x{program['identifier'][0]:X}u, 0x{program['identifier'][1]:X}u}}, {entry}, runs_{index}, "
                     f"{len(program['runs'])}u, {{{digests}}}}},")
    if not entries:
        table.append("    {{0, 0}, 0, 0, 0, {{0}, {0}}},")
    table.append("};")
    table.append(f"const unsigned Memories_ModelProgramCount = {len(entries)}u;")
    files["model_recomp_table.c"] = "\n".join(table) + "\n"
    return files


def translate(mrg):
    """(programs, refusals) from MODEL.MRG's bytes."""
    by_slot = modules(mrg)
    groups = {0: {}, 1: {}}
    for slot, items in by_slot.items():
        for module in items:
            groups[slot].setdefault(word_at(module, SLOT_BASE[slot], SLOT_BASE[slot]), {})[hashlib.sha256(module).digest()] = module
    # A record's slot A and slot B variants are one program; pair identifiers by record.
    pairs = {}
    for a, b in zip(by_slot[0], by_slot[1]):
        ia, ib = word_at(a, SLOT_BASE[0], SLOT_BASE[0]), word_at(b, SLOT_BASE[1], SLOT_BASE[1])
        if pairs.setdefault(ia, ib) != ib:
            raise DiscError(f"slot A program {ia:#x} pairs with two slot B programs")
    programs, refusals = [], []
    for ia in sorted(pairs):
        ib = pairs[ia]
        try:
            programs.append(build_program(list(groups[0][ia].values()), list(groups[1][ib].values())))
        except Untranslatable as reason:
            refusals.append((ia, str(reason)))
    return programs, refusals


def write_if_changed(path: Path, text: str):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8", newline="\n")


def generate(out: Path, disc: Path | None = None, quiet=False):
    """Write the translated modules into `out`; return the C sources to compile."""
    out.mkdir(parents=True, exist_ok=True)
    disc = disc or find_disc()
    stamp_path = out / "stamp.json"
    generator = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    stamp = None
    if disc and disc.exists():
        try:
            source = model_file(disc) or disc
        except (DiscError, OSError):
            source = disc
        info = source.stat()
        stamp = dict(disc=str(source.resolve()), size=info.st_size, mtime=info.st_mtime_ns, generator=generator,
                     version=GENERATOR_VERSION)
    try:
        previous = json.loads(stamp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    if stamp and previous and previous.get("stamp") == stamp:
        return [str(out / name) for name in previous["sources"]]
    files, note = None, None
    if stamp:
        try:
            mrg = read_model_mrg(disc)
        except (DiscError, OSError) as error:
            note = f"cannot read MODEL.MRG from {disc}: {error}"
        else:
            if hashlib.sha256(mrg).hexdigest() != MODEL_SHA256:
                note = f"{disc}: MODEL.MRG is not the North American one; the interpreter runs its modules"
            else:
                programs, refusals = translate(mrg)
                files = generate_sources(programs)
                instructions = sum(len(body) for p in programs for body in p["functions"].values())
                note = (f"model modules: {len(programs)} programs translated ({instructions} instructions), "
                        f"{len(refusals)} left to the interpreter")
                for identifier, reason in refusals:
                    note += f"\n  program 0x{identifier:X}: {reason}"
    else:
        note = "model modules: no disc image in game/; the interpreter runs them"
    if files is None:
        files = generate_sources([])
    for stale in out.glob("model_recomp_*"):
        if stale.name not in files:
            stale.unlink()
    for name, text in files.items():
        write_if_changed(out / name, text)
    sources = sorted(name for name in files if name.endswith(".c"))
    stamp_path.write_text(json.dumps(dict(stamp=stamp, sources=sources), indent=1), encoding="utf-8")
    if not quiet and note:
        print(note)
    return [str(out / name) for name in sources]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--disc", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "tmp/pc/model-recomp")
    arguments = parser.parse_args()
    for source in generate(arguments.out, arguments.disc):
        print(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
