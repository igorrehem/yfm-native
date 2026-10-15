#ifndef MEMORIES_PC_LANGUAGE_H
#define MEMORIES_PC_LANGUAGE_H
/* Game > Language: the game's own European translations (notes/translation.md,
 * "The official languages"). Their text ships with the port, one listing a
 * language in languages/ beside the program (en-eu, fr, de, it, es .txt),
 * written off the PAL discs by tools/pc/export_languages.py; a PAL disc in
 * `game/languages` or `game/pal` (any .bin or .cue, found by what is on it)
 * is read when a pack is not there. MEMORIES_LANGUAGES_DIR names the one
 * folder to look in for both. The setting takes effect at the next launch;
 * a mod's translation stands over it, string by string. Where the text
 * comes from is language.c's `sources` table. */
#include <stddef.h>

enum { LANGUAGE_US, LANGUAGE_EN_EU, LANGUAGE_FR, LANGUAGE_DE, LANGUAGE_IT, LANGUAGE_ES, LANGUAGE_COUNT };

/* The name the menu shows, in the language itself (UTF-8). */
const char *Language_Label(int language);
/* Whether a pack or disc has the language (English US always is). The
 * folders are searched once, on the first call. */
int Language_Available(int language);
/* For Text_Build, once: the chosen language's text as a listing the
 * translations' compiler reads (malloc'd; free it), or NULL for English (US)
 * or when no pack or disc has the language. The language counts as in use
 * from then on. */
char *Language_Listing(size_t *length);
/* The language this launch's text is in. */
int Language_Current(void);
/* A short name for the language that does not change with the menu's order
 * ("en-us", or its pack's: "en-eu", "fr", "de", "it", "es"); a save state
 * keeps it (state.c). "" for no language. */
const char *Language_Code(int language);
/* Back to English (US) for this launch: the listing did not compile. */
void Language_Drop(void);

/* MEMORIES_EXPORT_LANGUAGES (tools/pc/export_languages.py): each PAL
 * language's listing, from the first source that has it, written to
 * `folder`/<name>.txt as the packs are; 0 when all five were. */
int Language_Export(const char *folder);

/* TextBox_BuildStep: with a PAL language in use, the pixels to add to the
 * step past glyph `code` in a box with `flags` (0 for the small letters),
 * and in `shift` how far left the letter is drawn (pal_text.h). */
int Language_Advance(unsigned flags, int code, int *shift);

/* TextBox_BuildStep, after each letter: with a PAL language in use (and not
 * the small letters), whether text channel `channel` is past its F8 07
 * limit, which the PAL reads as `limit` * 8 pixels (pal_text.h); `count` is
 * the letter's number since
 * the limit was set, `step` the pixels it took and `cell` the box's cell.
 * -1 otherwise: the US count of letters holds. */
int Language_PastWidth(unsigned flags, int channel, int count, int step, int cell, int limit);

#endif
