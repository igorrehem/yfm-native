/* PalText_Listing on a made-up language pack (nothing of the game's): the
 * ids, the PAL codes the US text spells another way, the menus the US text
 * keeps and the placeholder letters. */
#include "pc/text/pal_text.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char a[PAL_FILE_A_SIZE], b[PAL_FILE_B_SIZE], c[PAL_FILE_C_SIZE], glyphs[PAL_GLYPH_TABLE_SIZE];
static int failures;

static void put16(unsigned char *at, unsigned value)
{
    at[0] = (unsigned char)value;
    at[1] = (unsigned char)(value >> 8);
}

static void expect(const char *listing, const char *text, int present)
{
    if ((strstr(listing, text) != NULL) != present) {
        fprintf(stderr, "listing %s \"%s\"\n", present ? "lacks" : "has", text);
        failures++;
    }
}

int main(void)
{
    static const unsigned char hi[] = {1, 2, 0xFE, 3, 0xFF};
    static const unsigned char codes[] = {0xF8, 0x1B, 0xFC, 0x48, 0xF8, 0xF8, 0x03, 0x8C, 0xF8, 0x1B, 0x80, 0x00,
                                          0xF8, 0x1C, 0x00, 0xFF};
    static const unsigned char jump[] = {0xFD, 0x00, 0x02};
    /* The PAL's F8 07 takes a byte; its F8 00 03 is the US F8 00 01. */
    static const unsigned char limit[] = {0xF8, 0x00, 0x03, 0xF8, 0x07, 0x1C, 3, 0xFF};
    /* The PAL's text sizes: 2 (12x16) is the US letters on lines of 16, 0
     * back to normal the US 2; the card text's lines of 13 the US 12. */
    static const unsigned char sizes[] = {0xF8, 0x04, 0x02, 3, 0xF8, 0x04, 0x00, 0xF8, 0x05, 0x08, 0x0D, 0xFF};
    /* The star chips' heading, 12 cells with its space: wider in the US
     * box's cells of 16 than its 160 pixels, so in cells of 13. */
    static const unsigned char chips[] = {3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 0x31, 3, 0xFE, 0xF8, 0x04, 0x03, 2, 0xFF};
    /* Card texts longer than the US view's 8 lines: laid out again in its
     * width, a hyphen at a line's end before a lowercase word made whole;
     * nine lines that stay nine (20 letters each) are 11 pixels apart, from
     * 3 higher. */
    /* Free Duel's record, the name and a line below it: that line 16 pixels
     * under the first, as the PAL's lines are, not the US 12 (the first
     * break only). */
    static const unsigned char record[] = {0xF8, 0x09, 0xFE, 3, 0xFE, 3, 0xFF};
    static unsigned char nine[9 * 21];
    static const unsigned char ten[] = {3, 0x30, 0xFE, 2, 0xFE, 3, 0xFE, 3, 0xFE, 3, 0xFE, 3, 0xFE,
                                        3, 0xFE, 3, 0xFE, 3, 0xFE, 3, 0xFF};
    /* The password shop's menu, as the discs have it: [00E3] lays out two
     * lines and jumps for the answer ({choose 80 0 0}); [00E4], after it,
     * lays out its own choice and jumps into [00E3]'s lines. Read from
     * [00E4] first, those lines meet the jump before any choice: it is read
     * again once the choices are known, and kept. */
    static const unsigned char menu[] = {0xFB, 0x62, 3, 0xFE, 3, 0xFE, 0xFB, 0x80, 0x00, 0x00, 0x00, 0x00,
                                         0xFB, 0x6A, 0x02, 0xFD, 0x02, 0x14};
    char expected[512];
    int n;
    static const unsigned char e[] = {3, 0xFF}, i[] = {2, 0xFF}, accent[] = {0x3F, 0xFF}, name[] = {3, 2, 0xFF};
    PalTextPack pack = {a, b, c, glyphs};
    size_t length = 0;
    int problems = -1, shift;
    char *listing;

    /* The glyphs: H, i, E in full-width Shift-JIS; 0x3F a placeholder kanji
     * the Spanish font draws as á. */
    put16(glyphs + 1 * 4, 0x8267);
    put16(glyphs + 2 * 4, 0x8289);
    put16(glyphs + 3 * 4, 0x8264);
    put16(glyphs + 0x3F * 4, 0x89E7);

    put16(a, 0x0F + 3 * PAL_SPANISH);
    put16(a + 4 + 0x01 * 2, 0x1000);
    memcpy(a + 0x1000, hi, sizeof(hi));
    put16(a + 4 + 0x02 * 2, 0x1010);
    memcpy(a + 0x1010, codes, sizeof(codes));
    put16(a + 4 + 0x03 * 2, 0x1030);
    memcpy(a + 0x1030, jump, sizeof(jump));
    put16(a + 4 + 0x04 * 2, 0x1080);
    memcpy(a + 0x1080, limit, sizeof(limit));
    put16(a + 4 + 0x05 * 2, 0x1040);   /* no words, laid out for the PAL's frames: the US one stays */
    put16(a + 4 + 0xE1 * 2, 0x1200);   /* the star chips */
    memcpy(a + 0x1200, chips, sizeof(chips));
    put16(a + 4 + 0x0C * 2, 0x1300);   /* Free Duel's record */
    memcpy(a + 0x1300, record, sizeof(record));
    put16(a + 4 + 0xE3 * 2, 0x1400);
    put16(a + 4 + 0xE4 * 2, 0x140C);
    memcpy(a + 0x1400, menu, sizeof(menu));
    put16(a + 4 + 0x07 * 2, 0x1090);
    memcpy(a + 0x1090, sizes, sizeof(sizes));
    put16(glyphs + 0x30 * 4, 0x817C);   /* - */
    put16(glyphs + 0x31 * 4, 0x8140);   /* a space */
    memset(nine, 3, sizeof(nine));
    for (n = 1; n <= 9; n++) nine[n * 21 - 1] = n < 9 ? 0xFE : 0xFF;
    put16(a + 4 + 0x101 * 2, 0x1100);  /* card text 0x101: US D101 */
    memcpy(a + 0x1100, nine, sizeof(nine));
    put16(a + 4 + 0x102 * 2, 0x10A0);
    memcpy(a + 0x10A0, ten, sizeof(ten));
    memcpy(a + 0x0200, e, sizeof(e));
    put16(a + 4 + 0x10 * 2, 0x1040);   /* the debug menu: the US one stays */
    memcpy(a + 0x1040, e, sizeof(e));
    put16(a + 4 + 0x40 * 2, 0x1050);   /* the result pages: the US ones stay */
    memcpy(a + 0x1050, i, sizeof(i));
    put16(a + 4 + 0x44 * 2, 0x1060);
    memcpy(a + 0x1060, e, sizeof(e));
    put16(a + 4 + 0x100 * 2, 0x1070);  /* card text 1: US D101 is 0x100 + 1 */
    memcpy(a + 0x1070, e, sizeof(e));
    put16(a + 4 + 0x400 * 2, 0x0010);  /* the story's first line, in file B */
    put16(b, 0x10 + 3 * PAL_SPANISH);
    memcpy(b + 0x10, accent, sizeof(accent));
    put16(c, 0x11 + 3 * PAL_SPANISH);
    put16(c + 4 + 1 * 2, 0x5800 + 0x700); /* card 1's name */
    memcpy(c + 0x700, name, sizeof(name));

    listing = PalText_Listing(&pack, PAL_SPANISH, &length, &problems);
    if (!listing) {
        fprintf(stderr, "no listing\n");
        return 1;
    }
    expect(listing, "[0001]\nHi\nE{end}", 1);
    expect(listing, "[0002]\n{call L125A}{call L125A}{f8 03 08 56 1D 80 00}{end}", 1);
    expect(listing, "f8 1C", 0);
    expect(listing, "[0003]\n{jump LF000}", 1);
    expect(listing, "{f8 00 01}{f8 07 1C 00}E{end}", 1);
    expect(listing, "{:LF000}\nE{end}", 1);
    expect(listing, "[0010]", 0);
    expect(listing, "[0040]", 0);
    expect(listing, "[0044]", 0);
    expect(listing, "[D100]\nE{end}", 1);
    expect(listing, "[0005]", 0);
    expect(listing, "[00E1]\n{f8 05 0D 10}EEEEEEEEEE E\n{f8 04 03}i{end}", 1);
    expect(listing, "[000C]\n{f8 09}\n{f8 01 04}E\nE{end}", 1);
    expect(listing, "[0007]\n{f8 04 02}{f8 05 08 10}E{f8 04 02}{f8 05 08 0C}{end}", 1);
    strcpy(expected, "[D101]\n{f8 01 FD}{f8 05 08 0B}");
    for (n = 0; n < 9; n++) strcat(expected, n < 8 ? "EEEEEEEEEEEEEEEEEEEE\n" : "EEEEEEEEEEEEEEEEEEEE{end}");
    expect(listing, expected, 1);
    expect(listing, "[D102]\nEi E E E E E E E E{end}", 1);
    expect(listing, "@bank descriptions", 1);
    expect(listing, "[0500]\n\xC3\xA1{end}", 1);
    expect(listing, "[8001]\nEi{end}", 1);
    expect(listing, "\nE\nE\n{choose 80 0 0}\n", 1);
    expect(listing, "{nl}{cont}\n[00E4]", 0);
    if (problems) {
        fprintf(stderr, "%d problems\n", problems);
        failures++;
    }
    if (strlen(listing) != length) failures++;
    free(listing);

    /* The PAL font's spacing. */
    if (PalText_Advance(' ', &shift) != -1 || shift) failures++;
    if (PalText_Advance('i', &shift) != -2 || shift != -1) failures++;
    if (PalText_Advance('\'', &shift) != -6 || shift != -3) failures++;
    if (PalText_Advance('.', &shift) != -2 || shift) failures++;
    if (PalText_Advance(',', &shift) != -2 || shift) failures++;
    if (PalText_Advance('l', &shift) != -2 || shift != -1) failures++;

    /* F8 07's limit in pixels: the duel bar's 0x18 is 192; "Doppelkopfiger
     * Donnerdra" (20 letters of 8, three of 6, a space of 7) is 193 with
     * the next cell, so it is done there and not a letter before. */
    {
        int width = 0, n, done = 0;
        static const int steps[24] = {8, 8, 8, 8, 8, 6, 8, 8, 8, 6, 6, 8, 8, 8, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8};
        for (n = 0; n < 24; n++) {
            done = PalText_PastWidth(&width, steps[n], 8, 0x18);
            if (n < 23 && done) failures++;
        }
        if (!done || width != 185) failures++;
        width = 0;
        if (PalText_PastWidth(&width, 8, 8, 2) != 0 || PalText_PastWidth(&width, 8, 8, 2) != 1) failures++;
    }
    if (PalText_Advance('m', &shift) != 0 || shift) failures++;
    if (failures) fprintf(stderr, "%d failures\n", failures);
    return failures != 0;
}
