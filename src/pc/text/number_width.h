#ifndef MEMORIES_PC_TEXT_NUMBER_WIDTH_H
#define MEMORIES_PC_TEXT_NUMBER_WIDTH_H
/* A number a string prints in a field of four digits or more ({f8 03 ...})
 * that has more digits than the field: ATK, DEF or LP past 9999, or
 * starchips past 999999, which a mod's "limits" allow (pc/cards/tables.h).
 * func_80038148 keeps all the digits, and what the string lays out round the
 * field must not move: the card's bar puts its type and stars right after
 * ATK and DEF, and the Password screen's starchip box ends where six digits
 * end. So the digits are drawn closer together, in the field's own width: 5
 * in 4 cells of 8 step 6, 6, 6, 7, 7 (the digits are 5 pixels wide). A
 * number that fits never gets here, so nothing the disc prints changes.
 *
 * Kept by text channel (index_57, the four text boxes); no game headers. */

/* The next `digits` glyphs of `channel` are a number of that many digits in
 * a field of `field` cells `advance` pixels wide. */
void NumberWidth_Squeeze(int channel, int digits, int field, int advance);
/* A text box starts on `channel`: nothing of an earlier number is left. */
void NumberWidth_Reset(int channel);
/* How many pixels less than its advance the glyph `channel` has just drawn
 * steps: 0 unless it is one of a squeezed number's. */
int NumberWidth_Take(int channel);

#endif
