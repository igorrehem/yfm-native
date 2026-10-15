#ifndef MEMORIES_PC_PAL_TEXT_H
#define MEMORIES_PC_PAL_TEXT_H
/* The official European languages (Game > Language, language.h): the text of
 * a PAL disc's language pack turned into a listing with the US string ids,
 * which translation.c compiles as it does a mod's (notes/translation.md,
 * "The official languages"). Pure: the caller reads the disc.
 *
 * A PAL disc keeps its text in DATA/WA_MRG.MRG, one pack per language
 * (English, French, German, Italian, Spanish), and in each pack three files,
 * every one a u16 id (0x0F, 0x10, 0x11 + 3 per language) and a u16 0, then:
 *   A (0xF000 bytes): a u16 table at +4, offsets from the file's start, of
 *      the menus (0x000-0x0FF), the card texts (0x100-0x3FF) and, into file
 *      B, the story's lines (0x400-0x4F9); then the menus and card texts
 *   B (0x10000): the story's lines
 *   C (0x7180): the names, a u16 table at +4 (0x360 of them), offsets from
 *      0x5800 before the file's start, as the US names bank's
 * The codes are the US text's but for three: F8 1B, with no operand, is the
 * player's name; the name buffers sit at A+0xF800/F814/F848; and F8 03's
 * numbers are 0x15D7C lower in RAM. The sizes of F8 04 and F8 05 are laid
 * out for the PAL's frames, and are written for the US ones the port draws
 * (notes/translation.md, "Frames"). The glyph codes are the PAL
 * executable's (a Shift-JIS table at 0x801D9000, 0x400 bytes), with the
 * accented letters on placeholder codes each language's font draws its own
 * way (the tables in pal_text.c). */
#include <stddef.h>
#include <stdint.h>

enum { PAL_ENGLISH, PAL_FRENCH, PAL_GERMAN, PAL_ITALIAN, PAL_SPANISH, PAL_LANGUAGES };

#define PAL_FILE_A_SIZE 0xF000u
#define PAL_FILE_B_SIZE 0x10000u
#define PAL_FILE_C_SIZE 0x7180u
#define PAL_GLYPH_TABLE_SIZE 0x400u

typedef struct {
    const unsigned char *a, *b, *c;   /* PAL_FILE_*_SIZE bytes each */
    const unsigned char *glyphs;      /* the executable's table, PAL_GLYPH_TABLE_SIZE bytes */
} PalTextPack;

/* The listing (UTF-8, '\0'-ended, malloc'd; free it), or NULL when out of
 * memory. `problems` (may be NULL) counts what could not be written as it
 * was: a glyph with no character, a bank that did not decode. */
char *PalText_Listing(const PalTextPack *pack, int language, size_t *length, int *problems);

/* The PAL font's spacing, in the dialogue boxes' mode (EU func_80036A78,
 * which returns it and TextBox_BuildStep adds to the 8 pixels a letter
 * takes): pixels to add to the step past `character`, and in `shift` how far
 * left of the cell the US letter is drawn so that its ink is where the PAL
 * font has the same letter's. 0 for the rest. */
int PalText_Advance(uint32_t character, int *shift);

/* The PAL's F8 07 limit (EU 0x80038190 sets it, one byte times 8 pixels;
 * TextBox_BuildStep checks it at 0x80039508-0x80039558): adds `step`, the
 * pixels a letter took, to `*width` and says whether the box is done, which
 * is when the next cell of `cell` pixels would pass `limit` * 8. */
int PalText_PastWidth(int *width, int step, int cell, int limit);

#endif
