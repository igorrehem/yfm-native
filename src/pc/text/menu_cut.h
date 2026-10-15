#ifndef MEMORIES_PC_TEXT_MENU_CUT_H
#define MEMORIES_PC_TEXT_MENU_CUT_H
/* A menu with choices is laid out in one go: func_80039794 steps its text
 * with no frame in between while flags_34 & 0x1000 is up, until the last
 * choice line is down (Text_TryCompleteChoiceLayout). A menu with more
 * lines than its box has rows under where it starts reaches a new line
 * whose row is past the box before that: Text_NewLine then waits for a
 * button (state 4) that nothing in that loop reads, and the game stops for
 * good, the console's too (notes/translation.md). There, and only there,
 * the port cuts the menu instead: the lines past the box are left out and
 * the choices are the ones in the box. A menu that fits never gets here.
 *
 * Kept by text channel (index_57, the four text boxes); no game headers,
 * so tests/pc/menu_cut_test.c runs it as it is. */

/* A menu starts on `channel` (the choice command). */
void TextMenu_Begin(int channel);
/* A new line of the menu on `channel` wraps past the box: `lines` lines of
 * the menu's `count` are down. 1: its rows are cut and the page wait is
 * skipped; 0: retail's path (the last line, which completes the menu). */
int TextMenu_CutsLine(int channel, int lines, int count);
/* Whether the menu on `channel` is being cut (its letters are left out). */
int TextMenu_Cutting(int channel);
/* The menu on `channel` of string `id` is laid out, with `heading` rows
 * above its choices ({choice} bits 4-5) and `count` choices: the count the
 * player picks from, cut to the choices in the box (at least one). */
int TextMenu_Finish(int id, int channel, int heading, int count);

/* After its last line a menu's text goes on with the jump that takes the
 * answer somewhere ({choose 80 ...}, FB with bit 7): every menu of the
 * game's text has it, and once the player answers, the text goes on from
 * there. A menu without it (a translation written from a listing that had
 * lost it, [00E3], the password shop's EXCHANGE/QUIT) would go on into
 * whatever text follows, the next string's menu, and never end: the screen
 * waits for the text to end and the game stops. The menu on `channel` is
 * laid out, and its text goes on at `next`. */
void TextMenu_LaidOut(int channel, const unsigned char *next);
/* The text of string `id` on `channel` goes on at `at`, after its menu is
 * answered: 1 when that menu has no jump there, and the text ends instead,
 * as the jump's null target would end it (said once per string); else 0. */
int TextMenu_Unanswered(int id, int channel, const unsigned char *at);

#endif
