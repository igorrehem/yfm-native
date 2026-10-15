#!/usr/bin/env python3
"""Route writes through 32-bit pointers via 64-bit pointers (AArch64 builds).

The 64-bit builds keep the game's stored pointers 4 bytes wide with clang's
__ptr32 __uptr (G32, src/port_ptr.h), which puts them in LLVM address spaces
270-272. LLVM's AArch64 back end (clang 21 in NDK r29, and clang 22.1.8)
drops the truncation of a store through such a pointer: `p->u16 |= 0x28`
becomes `ldrh w8, [x9]; orr ...; str w8, [x9]`, at -O2 a plain `p->u16 = v`
or `p->u8 = v` becomes `str w0, [x8]`, and a 6-byte structure copied into
one ends in a 4-byte store of its last two bytes. The bytes after the field
are overwritten. (x86-64 is not affected; loads are selected correctly.) In
the game that cleared DisplayObject.field_0A beside the flags it updated,
which relinked the display lists and moved what the duel draws.

The front end's IR is right (`store i16 %v, ptr addrspace(271) %p`), so on
AArch64 each unit goes to IR, this sends every store and every memcpy,
memmove or memset whose pointer is in one of those address spaces through an
addrspacecast to an ordinary pointer (which extends the address as the
address space says, as the back end itself would), and the IR is compiled as
usual:

    %g32.0 = addrspacecast ptr addrspace(271) %p to ptr
    store i16 %v, ptr %g32.0

This is a workaround: compiler_bug() is the canary every arm64 build runs
first, and once it comes back empty for the NDK in use the pass can go
(notes/pc-build.md, "Android arm64").

rewrite() returns the new text and raises if such a write is left (a store,
a memory intrinsic, an atomicrmw or a cmpxchg), so a construct it does not
handle fails the build instead of miscompiling.

    python tools/pc/ptr32_stores.py unit.ll [out.ll]
"""
import re
import sys

SPACES = ("270", "271", "272")
_POINTER = re.compile(r"ptr addrspace\((27[012])\)")
_OPEN, _CLOSE = "([{<", ")]}>"
# The .inline forms first: else "memcpy" matches and "inline" lands in the
# type suffix, which then no longer lines up with the arguments.
_INTRINSIC = re.compile(r"@llvm\.(memcpy\.inline|memset\.inline|memcpy|memmove|memset)\.([\w.]+)\(")
_ORDERING = re.compile(r"\s(syncscope\(\"[^\"]*\"\)\s+)?(unordered|monotonic|acquire|release|acq_rel|seq_cst)$")


def _split_top(text):
    """Split at commas outside brackets and quotes."""
    parts, depth, start, quoted = [], 0, 0, False
    for i, ch in enumerate(text):
        if ch == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _matching(text, open_at):
    """Index of the bracket closing the one at open_at."""
    depth, quoted = 0, False
    for i in range(open_at, len(text)):
        ch = text[i]
        if ch == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"ptr32_stores: unbalanced brackets: {text.strip()}")


class _Rewriter:
    def __init__(self):
        self.count = 0
        self.declare = {}

    def cast(self, out, indent, space, operand):
        name = f"%g32.{self.count}"
        self.count += 1
        out.append(f"{indent}{name} = addrspacecast ptr addrspace({space}) {operand} to ptr")
        return name

    def store(self, line, out):
        indent = line[:len(line) - len(line.lstrip())]
        parts = _split_top(line)
        match = re.match(r"\s*ptr addrspace\((27[012])\) (.+)$", parts[1]) if len(parts) > 1 else None
        if not match:
            return False
        operand, tail = match.group(2), ""
        ordering = _ORDERING.search(operand)
        if ordering:
            operand, tail = operand[:ordering.start()], operand[ordering.start():]
        name = self.cast(out, indent, match.group(1), operand)
        out.append(",".join([parts[0], f" ptr {name}{tail}"] + parts[2:]))
        return True

    def intrinsic(self, line, out):
        match = _INTRINSIC.search(line)
        if not match:
            return False
        indent = line[:len(line) - len(line.lstrip())]
        close = _matching(line, match.end() - 1)
        arguments = _split_top(line[match.end():close])
        suffix = match.group(2).split(".")  # p271.p0.i64, or p271.i64 for memset
        changed = False
        for i, argument in enumerate(arguments):
            found = re.match(r"(\s*)ptr addrspace\((27[012])\) (.+)$", argument)
            if not found:
                continue
            # Parameter attributes (align 2, noundef, dereferenceable(6)...)
            # come before the value, which is a name or a constant expression.
            value = re.search(r"(?:^|\s)([%@]|(?:getelementptr|inttoptr|addrspacecast|bitcast|null|undef|poison)\b)",
                              found.group(3))
            if not value:
                raise ValueError(f"ptr32_stores: cannot read the pointer argument: {line.strip()}")
            start = value.start(1)
            name = self.cast(out, indent, found.group(2), found.group(3)[start:])
            arguments[i] = f"{found.group(1)}ptr {found.group(3)[:start]}{name}"
            if i < len(suffix) and suffix[i] == f"p{found.group(2)}":
                suffix[i] = "p0"
            changed = True
        if not changed:
            return False
        callee = f"llvm.{match.group(1)}.{'.'.join(suffix)}"
        self.declare[callee] = (match.group(1), suffix)
        out.append(line[:match.start()] + f"@{callee}(" + ",".join(arguments) + line[close:])
        return True

    def declarations(self, text):
        lines = []
        for callee, (kind, suffix) in sorted(self.declare.items()):
            if f"@{callee}(" in text.split("declare", 1)[-1] and re.search(rf"^declare .*@{re.escape(callee)}\(", text, re.M):
                continue
            size = suffix[-1]
            if kind.startswith("memset"):
                lines.append(f"declare void @{callee}(ptr writeonly captures(none), i8, {size}, i1 immarg)")
            else:
                lines.append(f"declare void @{callee}(ptr captures(none), ptr captures(none), {size}, i1 immarg)")
        return lines


def _writes_32(line):
    stripped = line.strip()
    if stripped.startswith("store ") or stripped.startswith("store\t"):
        parts = _split_top(stripped)
        return len(parts) > 1 and _POINTER.match(parts[1].strip()) is not None
    if re.search(r"\b(atomicrmw|cmpxchg)\b", stripped) and _POINTER.search(stripped):
        return True
    match = _INTRINSIC.search(stripped)
    return bool(match and _POINTER.search(stripped[match.end():]))


CANARY = """struct S { unsigned a; unsigned short f; unsigned char b, c; };
extern struct S *__ptr32 __uptr gp;
void canary_or16(void) { gp->f |= 1; }
void canary_set8(unsigned char v) { gp->b = v; }
"""
_WIDE_STORE = re.compile(r"^\s*(str|stur)\s+w\d+,\s*\[x\d+")


def compiler_bug(cc, flags, workdir):
    """The canary cases the compiler gets wrong: a 4-byte store (str w) to a
    2-byte field at -O0 or a 1-byte field at -O2, through a G32 pointer,
    compiled without this pass. Empty once the compiler is fixed."""
    import subprocess
    source = f"{workdir}/ptr32_canary.c"
    with open(source, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(CANARY)
    bad = []
    for level, function in (("-O0", "canary_or16"), ("-O2", "canary_set8")):
        result = subprocess.run([cc, *flags, "-fms-extensions", "-w", level, "-S", source, "-o", "-"],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"ptr32 canary did not compile: {result.stderr.strip()}")
        body = result.stdout.split(f"\n{function}:", 1)[-1].split(".Lfunc_end", 1)[0]
        if any(_WIDE_STORE.match(line) for line in body.splitlines()):
            bad.append(f"{function} at {level}")
    return bad


def rewrite(text):
    rewriter, out = _Rewriter(), []
    for line in text.splitlines():
        if "addrspace(27" in line and not line.lstrip().startswith(("declare", ";")):
            stripped = line.lstrip()
            if stripped.startswith("store") and rewriter.store(line, out):
                continue
            if _INTRINSIC.search(line) and rewriter.intrinsic(line, out):
                continue
        out.append(line)
    out.extend(rewriter.declarations("\n".join(out)))
    for line in out:
        if not line.lstrip().startswith("declare") and _writes_32(line):
            raise ValueError(f"ptr32_stores: a write through a 32-bit pointer is left: {line.strip()}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as handle:
        text = handle.read()
    with open(sys.argv[-1], "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rewrite(text))
