/* A won duel's starchips past the results row's eight (starchip_prize.h).
 *
 * Written in the game's text codes, as drops.c and free_duel/page_box.c
 * write theirs: 0xF8 begins a command, 0x04 sets the cell size (2 is the
 * font's letters, which HD text can set) and 0x0A the color. */
#include "starchip_prize.h"
#include "pc/text/glyphs.h"
#include "game/duel_result_display.h"
#include <stdio.h>

enum { WHITE = 0x00 };

int StarchipPrize_Pictures(int prize)
{
    if (prize <= 0) return 0;
    return prize > STARCHIP_PRIZE_ROW ? 1 : prize;
}

int StarchipPrize_Counted(int prize)
{
    return prize > STARCHIP_PRIZE_ROW;
}

const unsigned char *StarchipPrize_Compose(int prize)
{
    static unsigned char text[STARCHIP_PRIZE_TEXT_SIZE];
    char letters[16];
    int at = 0, i;
    if (!StarchipPrize_Counted(prize)) return NULL;
    snprintf(letters, sizeof(letters), "x%d", prize);
    text[at++] = 0xF8;
    text[at++] = 0x04;
    text[at++] = 2;
    text[at++] = 0xF8;
    text[at++] = 0x0A;
    text[at++] = WHITE;
    for (i = 0; letters[i] && at + 3 < (int)sizeof(text); i++) {
        int code = Glyphs_Code((unsigned char)letters[i]);
        if (code < 0) continue;
        if (code >= 0xF0) text[at++] = (unsigned char)(0xF0 + (code >> 8));
        text[at++] = (unsigned char)(code & 0xFF);
    }
    text[at] = 0xFF;
    return text;
}

const unsigned char *StarchipPrize_Text(int id)
{
    if (id != STARCHIP_PRIZE_TEXT_ID || !D_8009B1E8) return NULL;
    return StarchipPrize_Compose(D_8009B1E8->starchip_prize);
}
