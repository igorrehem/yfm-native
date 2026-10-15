"""Writes src/pc/text/accents.inc and src/pc/text/compose.inc from Python's unicodedata.

    python tools/pc/glyph_accents.py [--check]

accents.inc: every Latin letter that decomposes (NFD) into an ASCII letter and
one of the marks glyphs.c draws, or into an ASCII letter, a shape mark (^, the
breve or the horn) and a tone (grave, acute, hook, tilde or dot below): the
Vietnamese letters with two marks. compose.inc: the canonical compositions of
a letter and a combining mark whose result is a Latin letter (utf8.c's NFC),
and the combining classes of the marks they use. --check compares instead.
"""
import sys
import unicodedata
from pathlib import Path

MARKS = {
    0x0300: "MARK_GRAVE", 0x0301: "MARK_ACUTE", 0x0302: "MARK_CIRCUMFLEX", 0x0303: "MARK_TILDE",
    0x0304: "MARK_MACRON", 0x0306: "MARK_BREVE", 0x0307: "MARK_DOT", 0x0308: "MARK_DIAERESIS",
    0x030A: "MARK_RING", 0x030B: "MARK_DOUBLE_ACUTE", 0x030C: "MARK_CARON", 0x0327: "MARK_CEDILLA",
    0x0328: "MARK_OGONEK", 0x0309: "MARK_HOOK", 0x0323: "MARK_DOT_BELOW", 0x031B: "MARK_HORN",
}
SHAPES = (0x0302, 0x0306, 0x031B)
TONES = (0x0300, 0x0301, 0x0309, 0x0303, 0x0323)
TEXT = Path(__file__).resolve().parents[2] / "src/pc/text"


def latin(c):
    return "LATIN" in unicodedata.name(chr(c), "")


def accents():
    lines = ["/* Written out by tools/pc/glyph_accents.py from Python's unicodedata:",
             " * every Latin letter that decomposes into an ASCII letter and one of the",
             " * marks glyphs.c draws, or a shape mark (^, breve, horn) and a tone (the",
             " * Vietnamese letters with two marks: shape first). Included by glyphs.c only. */"]
    for c in range(0xC0, 0x3000):
        if not latin(c):
            continue
        d = unicodedata.normalize("NFD", chr(c))
        if len(d) < 2 or not ("A" <= d[0] <= "Z" or "a" <= d[0] <= "z"):
            continue
        marks = [ord(m) for m in d[1:]]
        if len(marks) == 1 and marks[0] in MARKS:
            lines.append(f"    {{0x{c:04X}, '{d[0]}', {MARKS[marks[0]]}, MARK_NONE}},")
        elif len(marks) == 2:
            shape = [m for m in marks if m in SHAPES]
            tone = [m for m in marks if m in TONES]
            if len(shape) == 1 and len(tone) == 1:
                lines.append(f"    {{0x{c:04X}, '{d[0]}', {MARKS[shape[0]]}, {MARKS[tone[0]]}}},")
    return "\n".join(lines) + "\n"


def compose():
    pairs = []
    used = set()
    for c in range(0xC0, 0x3000):
        if not latin(c):
            continue
        d = unicodedata.decomposition(chr(c)).split()
        if len(d) != 2 or d[0].startswith("<"):
            continue
        first, mark = int(d[0], 16), int(d[1], 16)
        if not 0x0300 <= mark <= 0x036F or unicodedata.normalize("NFC", chr(first) + chr(mark)) != chr(c):
            continue
        pairs.append((first, mark, c))
        used.add(mark)
    lines = ["/* Written out by tools/pc/glyph_accents.py from Python's unicodedata: a",
             " * Latin letter and a combining mark that compose (NFC) into one letter,",
             " * sorted, and the combining classes of those marks. Included by utf8.c. */",
             "static const struct { uint16_t letter, mark, composed; } compositions[] = {"]
    for first, mark, c in sorted(pairs):
        lines.append(f"    {{0x{first:04X}, 0x{mark:04X}, 0x{c:04X}}},")
    lines.append("};")
    lines.append("static const struct { uint16_t mark; unsigned char order; } mark_classes[] = {")
    for m in sorted(used):
        lines.append(f"    {{0x{m:04X}, {unicodedata.combining(chr(m))}}},")
    lines.append("};")
    return "\n".join(lines) + "\n"


def main():
    check = "--check" in sys.argv
    bad = 0
    for name, text in (("accents.inc", accents()), ("compose.inc", compose())):
        path = TEXT / name
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                print(f"{path}: out of date")
                bad = 1
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"{path}: {text.count(chr(10))} lines")
    return bad


if __name__ == "__main__":
    sys.exit(main())
