#ifndef MEMORIES_PC_TEXT_ENTRY_LAYOUT_H
#define MEMORIES_PC_TEXT_ENTRY_LAYOUT_H
/* The text boxes' letters are entries of one table, each of the four text
 * channels a slice of it (gDuelEffect_awEntryRangeBoundaries). The US
 * executable has 620 entries at D_800EB288, sliced 255, 160, 160 and 45;
 * the five PAL executables (SLES-03947 to 03951) have 800, sliced 280, 220,
 * 220 and 80, because their text is longer: the French card shop's menu
 * alone has 54 letters, past the US channel 3's 44. With a PAL language on,
 * the port lays the table out as the PAL game does, in 800 entries of
 * guest RAM the US game leaves free (the console's stack, where the port's
 * game does not run); with English (US) nothing changes.
 *
 * Which table is in use follows the boundaries. They are game data, which
 * a save state keeps: the port's startup picture of them is always the US
 * one (they become the PAL ones only as the game starts, after it), so a
 * state whose boundaries are the PAL ones keeps them when loaded, and one
 * with the US ones takes this build's US ones (state.c's rule for words
 * the game never changed). A state goes on with the table its text boxes
 * point into, whichever language the game was launched in.
 *
 * No game headers here or in entry_layout.c: tests/pc/entry_layout_test.c
 * and the tests of its users build without them. */

#define TEXT_ENTRY_SIZE 0x1C       /* sizeof(DuelEffectEntry), checked in duel_effect.h */
#define TEXT_ENTRY_US_COUNT 620    /* DUEL_EFFECT_ENTRY_COUNT, checked there too */
#define TEXT_ENTRY_PAL_COUNT 800
#define TEXT_ENTRY_PAL_POOL 0x801F8000u
#define TEXT_ENTRY_CHANNELS 4

/* At launch, once the language is known: whether this launch has the PAL
 * layout. Nothing in the game changes yet. */
void TextEntries_UseLayout(int pal);
/* As the game starts, after the port's startup picture of the game data
 * (main.c, Memories_StateRunGame's entry): the launch's boundaries. */
void TextEntries_Start(void);
/* The table in use, DuelEffectEntry[]: D_800EB288, or the PAL one
 * (duel_effect.h). */
void *TextEntries_Pool(void);
/* Its entries: 620, or 800. */
int TextEntries_Total(void);
/* The most letters one page of `channel` (0-3) holds: its slice less the
 * entry that ends the list, in the boundaries in use once the game has
 * started, in the launch's before. */
int TextEntries_PageLetters(int channel);

#endif
