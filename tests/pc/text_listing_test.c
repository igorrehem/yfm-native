/* The text listing compiler (src/pc/text/listing.c): line breaks, items,
 * labels and targets, buffers, glyphs past the retail font, and what it
 * says about lines it cannot read. tools/pc/text_listing.py check covers the
 * same grammar against the whole retail text. */
#include "pc/text/listing.h"
#include "pc/text/glyphs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static const uint32_t bases[TEXT_BANK_COUNT] = {0x801B0000u, 0x801C0000u, 0x801D0000u};
static int reports;

/* The US layout's pages (src/pc/text/entry_layout.c): 254 letters, menus 159. */
int TextEntries_PageLetters(int channel) { return channel == 0 ? 254 : 159; }

/* Lower-case letters are 1-26, a space 0; an e with an acute accent is an
 * added glyph, 0x123; e with ^ and an acute (U+1EBF) 0x124, a with a dot
 * below and a breve (U+1EB7) 0x125, a lone combining acute 0x126. */
static int encode(uint32_t character)
{
    if (character == ' ') return 0;
    if (character >= 'a' && character <= 'z') return (int)(character - 'a' + 1);
    if (character == 0xE9) return 0x123;
    if (character == 0x1EBF) return 0x124;
    if (character == 0x1EB7) return 0x125;
    if (character == 0x301) return 0x126;
    return -1;
}

/* The 134 Vietnamese letters past ASCII, decomposed (NFD), and composed. */
static const char vietnamese_nfd[] =
    "\x61\xCC\x80\x61\xCC\x81\x61\xCC\x89\x61\xCC\x83\x61\xCC\xA3\x61\xCC\x86\x61\xCC\x86\xCC\x80\x61"
    "\xCC\x86\xCC\x81\x61\xCC\x86\xCC\x89\x61\xCC\x86\xCC\x83\x61\xCC\xA3\xCC\x86\x61\xCC\x82\x61\xCC"
    "\x82\xCC\x80\x61\xCC\x82\xCC\x81\x61\xCC\x82\xCC\x89\x61\xCC\x82\xCC\x83\x61\xCC\xA3\xCC\x82\x65"
    "\xCC\x80\x65\xCC\x81\x65\xCC\x89\x65\xCC\x83\x65\xCC\xA3\x65\xCC\x82\x65\xCC\x82\xCC\x80\x65\xCC"
    "\x82\xCC\x81\x65\xCC\x82\xCC\x89\x65\xCC\x82\xCC\x83\x65\xCC\xA3\xCC\x82\x69\xCC\x80\x69\xCC\x81"
    "\x69\xCC\x89\x69\xCC\x83\x69\xCC\xA3\x6F\xCC\x80\x6F\xCC\x81\x6F\xCC\x89\x6F\xCC\x83\x6F\xCC\xA3"
    "\x6F\xCC\x82\x6F\xCC\x82\xCC\x80\x6F\xCC\x82\xCC\x81\x6F\xCC\x82\xCC\x89\x6F\xCC\x82\xCC\x83\x6F"
    "\xCC\xA3\xCC\x82\x6F\xCC\x9B\x6F\xCC\x9B\xCC\x80\x6F\xCC\x9B\xCC\x81\x6F\xCC\x9B\xCC\x89\x6F\xCC"
    "\x9B\xCC\x83\x6F\xCC\x9B\xCC\xA3\x75\xCC\x80\x75\xCC\x81\x75\xCC\x89\x75\xCC\x83\x75\xCC\xA3\x75"
    "\xCC\x9B\x75\xCC\x9B\xCC\x80\x75\xCC\x9B\xCC\x81\x75\xCC\x9B\xCC\x89\x75\xCC\x9B\xCC\x83\x75\xCC"
    "\x9B\xCC\xA3\x79\xCC\x80\x79\xCC\x81\x79\xCC\x89\x79\xCC\x83\x79\xCC\xA3\xC4\x91\x41\xCC\x80\x41"
    "\xCC\x81\x41\xCC\x89\x41\xCC\x83\x41\xCC\xA3\x41\xCC\x86\x41\xCC\x86\xCC\x80\x41\xCC\x86\xCC\x81"
    "\x41\xCC\x86\xCC\x89\x41\xCC\x86\xCC\x83\x41\xCC\xA3\xCC\x86\x41\xCC\x82\x41\xCC\x82\xCC\x80\x41"
    "\xCC\x82\xCC\x81\x41\xCC\x82\xCC\x89\x41\xCC\x82\xCC\x83\x41\xCC\xA3\xCC\x82\x45\xCC\x80\x45\xCC"
    "\x81\x45\xCC\x89\x45\xCC\x83\x45\xCC\xA3\x45\xCC\x82\x45\xCC\x82\xCC\x80\x45\xCC\x82\xCC\x81\x45"
    "\xCC\x82\xCC\x89\x45\xCC\x82\xCC\x83\x45\xCC\xA3\xCC\x82\x49\xCC\x80\x49\xCC\x81\x49\xCC\x89\x49"
    "\xCC\x83\x49\xCC\xA3\x4F\xCC\x80\x4F\xCC\x81\x4F\xCC\x89\x4F\xCC\x83\x4F\xCC\xA3\x4F\xCC\x82\x4F"
    "\xCC\x82\xCC\x80\x4F\xCC\x82\xCC\x81\x4F\xCC\x82\xCC\x89\x4F\xCC\x82\xCC\x83\x4F\xCC\xA3\xCC\x82"
    "\x4F\xCC\x9B\x4F\xCC\x9B\xCC\x80\x4F\xCC\x9B\xCC\x81\x4F\xCC\x9B\xCC\x89\x4F\xCC\x9B\xCC\x83\x4F"
    "\xCC\x9B\xCC\xA3\x55\xCC\x80\x55\xCC\x81\x55\xCC\x89\x55\xCC\x83\x55\xCC\xA3\x55\xCC\x9B\x55\xCC"
    "\x9B\xCC\x80\x55\xCC\x9B\xCC\x81\x55\xCC\x9B\xCC\x89\x55\xCC\x9B\xCC\x83\x55\xCC\x9B\xCC\xA3\x59"
    "\xCC\x80\x59\xCC\x81\x59\xCC\x89\x59\xCC\x83\x59\xCC\xA3\xC4\x90";
static const uint16_t vietnamese[134] = {
    0x00E0, 0x00E1, 0x1EA3, 0x00E3, 0x1EA1, 0x0103, 0x1EB1, 0x1EAF, 0x1EB3, 0x1EB5,
    0x1EB7, 0x00E2, 0x1EA7, 0x1EA5, 0x1EA9, 0x1EAB, 0x1EAD, 0x00E8, 0x00E9, 0x1EBB,
    0x1EBD, 0x1EB9, 0x00EA, 0x1EC1, 0x1EBF, 0x1EC3, 0x1EC5, 0x1EC7, 0x00EC, 0x00ED,
    0x1EC9, 0x0129, 0x1ECB, 0x00F2, 0x00F3, 0x1ECF, 0x00F5, 0x1ECD, 0x00F4, 0x1ED3,
    0x1ED1, 0x1ED5, 0x1ED7, 0x1ED9, 0x01A1, 0x1EDD, 0x1EDB, 0x1EDF, 0x1EE1, 0x1EE3,
    0x00F9, 0x00FA, 0x1EE7, 0x0169, 0x1EE5, 0x01B0, 0x1EEB, 0x1EE9, 0x1EED, 0x1EEF,
    0x1EF1, 0x1EF3, 0x00FD, 0x1EF7, 0x1EF9, 0x1EF5, 0x0111, 0x00C0, 0x00C1, 0x1EA2,
    0x00C3, 0x1EA0, 0x0102, 0x1EB0, 0x1EAE, 0x1EB2, 0x1EB4, 0x1EB6, 0x00C2, 0x1EA6,
    0x1EA4, 0x1EA8, 0x1EAA, 0x1EAC, 0x00C8, 0x00C9, 0x1EBA, 0x1EBC, 0x1EB8, 0x00CA,
    0x1EC0, 0x1EBE, 0x1EC2, 0x1EC4, 0x1EC6, 0x00CC, 0x00CD, 0x1EC8, 0x0128, 0x1ECA,
    0x00D2, 0x00D3, 0x1ECE, 0x00D5, 0x1ECC, 0x00D4, 0x1ED2, 0x1ED0, 0x1ED4, 0x1ED6,
    0x1ED8, 0x01A0, 0x1EDC, 0x1EDA, 0x1EDE, 0x1EE0, 0x1EE2, 0x00D9, 0x00DA, 0x1EE6,
    0x0168, 0x1EE4, 0x01AF, 0x1EEA, 0x1EE8, 0x1EEC, 0x1EEE, 0x1EF0, 0x1EF2, 0x00DD,
    0x1EF6, 0x1EF8, 0x1EF4, 0x0110,
};


static void report(void *context, int line, const char *message)
{
    (void)context;
    fprintf(stderr, "line %d: %s\n", line, message);
    reports++;
}

static TextUnit *compile(const char *text)
{
    return TextListing_Compile(text, strlen(text), bases, NULL, 0, encode, report, NULL);
}

static TextUnit *compile_after(const char *text, TextUnit *const *earlier, int earlier_count)
{
    return TextListing_Compile(text, strlen(text), bases, earlier, earlier_count, encode, report, NULL);
}

static const unsigned char *string(const TextUnit *unit, unsigned id)
{
    int i;
    for (i = 0; i < unit->string_count; i++) {
        if (unit->strings[i].id == id) return unit->data + unit->strings[i].offset;
    }
    return NULL;
}

static unsigned operand(const unsigned char *at)
{
    return at[0] | (unsigned)at[1] << 8;
}

int main(void)
{
    TextUnit *unit;
    const unsigned char *at;

    /* A line break inside a string is the game's; the one before the next
     * item is the listing's. Comments and blank lines between items; one
     * that runs on into the next says so. */
    unit = compile("# a comment\n@bank dialog\n\n[0500]\nab\nc{page}d\n{cont}\n[0501 0502]\nx{end}\n");
    assert(unit && reports == 0);
    at = string(unit, 0x500);
    assert(at && !memcmp(at, "\x01\x02\xFE\x03\xFA\x04\xFE", 7));   /* ...then 0501's own text */
    assert(!memcmp(string(unit, 0x501), "\x18\xFF", 2) && string(unit, 0x502) == string(unit, 0x501));
    TextListing_Free(unit);

    /* A label on a line of its own adds no line break; text on the label's
     * line does, like any line. {cont} and {nl}. */
    unit = compile("@bank dialog\n[0001]\na{cont}\n{:L0010}\nb{end}\n[0002]\n{:L0020}c\nd{nl}{cont}\n[0003]\ne{end}\n");
    assert(unit && reports == 0);
    assert(!memcmp(string(unit, 0x001), "\x01\x02\xFF", 3));
    assert(!memcmp(string(unit, 0x002), "\x03\xFE\x04\xFE\x05\xFF", 6));
    TextListing_Free(unit);

    /* Blank lines and comments after {cont} are the listing's, not a line
     * break of the string's (an imported mod's text has one after every
     * item). */
    unit = compile("@bank dialog\n[0001]\na{cont}\n\n# note\n\n{:L0010}\nb{end}\n\n[0002]\nc\n{cont}\n\n[0003]\nd{end}\n");
    assert(unit && reports == 0);
    assert(!memcmp(string(unit, 0x001), "\x01\x02\xFF", 3));
    assert(!memcmp(string(unit, 0x002), "\x03\xFE\x04\xFF", 4));
    TextListing_Free(unit);

    /* Jumps: a label the listing defines is in the unit, one it does not is
     * the retail address; the operand is an index into the targets. */
    unit = compile("@bank dialog\n[0010]\n{jump L0040}\n{:L0040}\na{call L125A}{if 006E L0040}{end}\n"
                   "[0011]\n{choice 02}a\nb\n{choose 80 L0040 0}\n");
    assert(unit && reports == 0 && unit->target_count == 5);
    at = string(unit, 0x010);
    assert(at[0] == 0xFD && unit->targets[operand(at + 1)] == at + 3);
    assert(at[3] == 0x01 && at[4] == 0xFC && unit->targets[operand(at + 5)] == (unsigned char *)(uintptr_t)0x801B125Au);
    assert(at[7] == 0xF9 && at[8] == 0x6E && at[9] == 0x00 && unit->targets[operand(at + 10)] == at + 3);
    at = string(unit, 0x011);
    assert(!memcmp(at, "\xFB\x02\x01\xFE\x02\xFE\xFB\x80", 8));
    assert(unit->targets[operand(at + 8)] == string(unit, 0x010) + 3);
    assert(unit->targets[operand(at + 10)] == (unsigned char *)(uintptr_t)0x801B0000u);
    TextListing_Free(unit);

    /* A buffer is not a string of the unit's; codes with operands; an
     * added glyph is written F1 and its low byte. */
    unit = compile("@bank dialog\n[00FE]\n{buffer}\n\n@bank names\n[8001]\n{\xC3\xA9}\xC3\xA9 {sp}{end}\n"
                   "@bank descriptions\n[D101]\n{state 05 01 01}{f8 03 08 56 1D 80 83}{g 5A}{end}\n");
    assert(unit && reports == 1);   /* {é} is not a code */
    assert(!string(unit, 0x0FE));
    assert(!memcmp(string(unit, 0x8001), "\xF1\x23\x00\x00\xFF", 5));
    assert(!memcmp(string(unit, 0xD101), "\xF7\x05\x01\x01\xF8\x03\x08\x56\x1D\x80\x83\x5A\xFF", 13));
    TextListing_Free(unit);

    /* The port's own strings (text.h, TEXT_OWN_FIRST) are in the dialogue
     * bank, and in no other. */
    reports = 0;
    unit = compile("@bank dialog\n[FE00]\nab{end}\n[FEFF]\nc{end}\n@bank names\n[FE01]\na{end}\n");
    assert(unit && reports == 1);
    assert(!memcmp(string(unit, 0xFE00), "\x01\x02\xFF", 3) && !memcmp(string(unit, 0xFEFF), "\x03\xFF", 2));
    assert(!string(unit, 0xFE01));
    TextListing_Free(unit);
    assert(TextListing_Bank(0xFDFF) < 0 && TextListing_Bank(0xFE10) == TEXT_BANK_DIALOG);

    /* What cannot be read is said and left out; the rest still compiles. */
    reports = 0;
    unit = compile("[0500]\nno bank\n@bank dialog\n[8001]\nwrong bank{end}\n[0500]\nA{nope}{g 700}\nb{end} c\n");
    assert(unit && reports == 6);
    assert(!memcmp(string(unit, 0x500), "\xFE\x02\xFF", 3));
    TextListing_Free(unit);

    /* A label another file defines: the latest file read before this one
     * that has it; a file read after does not count. */
    reports = 0;
    {
        TextUnit *first = compile("@bank dialog\n[0020]\n{:L0050}\na{end}\n{:L0060}\nb{end}\n");
        TextUnit *second = compile("@bank dialog\n{:L0060}\nc{end}\n@bank names\n{:L0050}\nd{end}\n");
        TextUnit *earlier[2];
        earlier[0] = first;
        earlier[1] = second;
        assert(first && second && reports == 0 && first->label_count == 2);
        unit = compile_after("@bank dialog\n[0021]\n{jump L0050}\n[0022]\n{jump L0060}\n[0023]\n{jump L0070}\n",
                             earlier, 2);
        assert(unit && reports == 0);
        assert(unit->targets[operand(string(unit, 0x021) + 1)] == string(first, 0x020));   /* not the names bank's */
        assert(*unit->targets[operand(string(unit, 0x022) + 1)] == 3);                     /* the second's c */
        assert(unit->targets[operand(string(unit, 0x023) + 1)] == (unsigned char *)(uintptr_t)0x801B0070u);
        TextListing_Free(unit);
        TextListing_Free(first);
        TextListing_Free(second);
    }

    /* Text that is not UTF-8 (Windows-1252 here) is said once, where it
     * starts, and its lines counted; the rest of the line is kept. */
    reports = 0;
    unit = compile("@bank dialog\n[0030]\ncaf\xE9 a\nb\n\xE9t\xE9{end}\n");
    assert(unit && reports == 1 && unit->not_utf8_lines == 2 && unit->first_not_utf8_line == 3);
    assert(!memcmp(string(unit, 0x030), "\x03\x01\x06\x00\x01\xFE\x02\xFE\x14\xFF", 10));
    TextListing_Free(unit);
    /* A UTF-16 file is not read at all. */
    reports = 0;
    assert(!TextListing_Compile("\xFF\xFE@\0b\0", 6, bases, NULL, 0, encode, report, NULL) && reports == 1);

    /* A string that runs on into the next item without {cont} is most
     * likely missing its {end}; a page longer than any box, likewise. */
    reports = 0;
    unit = compile("@bank dialog\n[0040]\na\n\nnote\n[0041]\nb{cont}\n{:L0010}\nc{end}\n");
    assert(unit && reports == 1);
    TextListing_Free(unit);
    {
        static char text[1024];
        int i, n = sprintf(text, "@bank dialog\n[0042]\n");
        for (i = 0; i < 5; i++) n += sprintf(text + n, "%s\n", "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz");
        sprintf(text + n, "{page}abc{end}\n");
        reports = 0;
        unit = compile(text);
        assert(unit && reports == 1);   /* 260 letters on the first page, said once */
        TextListing_Free(unit);
        memcpy(text + strlen("@bank dialog\n[0042]\n") + 20, "{page}", 6);   /* 20, then 234 */
        reports = 0;
        unit = compile(text);
        assert(unit && reports == 0);
        TextListing_Free(unit);
    }

    /* Text in NFD (an editor's decomposed letters) is composed (NFC): one
     * glyph a letter, not one a mark; marks in either order; a mark with
     * nothing to compose with stays a character of its own after it. */
    unit = compile("@bank names\n[8001]\ne\xCC\x82\xCC\x81 \xE1\xBA\xBF a\xCC\xA3\xCC\x86 a\xCC\x86\xCC\xA3 "
                   "e\xCC\x81 q\xCC\x81{end}\n");
    assert(unit && reports == 0);
    assert(!memcmp(string(unit, 0x8001), "\xF1\x24\x00\xF1\x24\x00\xF1\x25\x00\xF1\x25\x00\xF1\x23\x00\x11\xF1\x26\xFF",
                   19));
    TextListing_Free(unit);
    {
        /* Every Vietnamese letter, decomposed, composes back; marks that do
         * not compose come back in their canonical order. */
        const char *at = vietnamese_nfd;
        uint32_t left[GLYPHS_MARKS_MAX];
        int i, left_count;
        for (i = 0; i < 134; i++) {
            uint32_t letter = Glyphs_NextComposed(&at, left, &left_count);
            if (letter != vietnamese[i] || left_count) fprintf(stderr, "letter %d: U+%04X\n", i, (unsigned)letter);
            assert(letter == vietnamese[i] && left_count == 0);
        }
        assert(*at == '\0');
        at = "e\xCC\xA3\xCC\x82";                      /* e, dot below, ^: U+1EC7 */
        assert(Glyphs_NextComposed(&at, left, &left_count) == 0x1EC7 && left_count == 0 && !*at);
        at = "q\xCC\x81\xCC\xA3x";                     /* q composes with neither */
        assert(Glyphs_NextComposed(&at, left, &left_count) == 'q' && left_count == 2 && left[0] == 0x323 &&
               left[1] == 0x301 && *at == 'x');
        at = "\xCC\x81" "a";                             /* a mark with no letter is itself */
        assert(Glyphs_NextComposed(&at, left, &left_count) == 0x301 && left_count == 0 && *at == 'a');
    }

    puts("text listing: ok");
    return 0;
}
