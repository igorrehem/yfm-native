/* The menu cut of src/pc/text/menu_cut.c, driven as Text_NewLine and the
 * choice command drive it (notes/translation.md). */
#include "pc/text/menu_cut.h"
#include "pc/debug/log.h"
#include <assert.h>
#include <string.h>

static int logged;
static char last[256];
int Log_Wanted(LogChannel channel) { return channel == LOG_MODS; }
void Log_Printf(LogChannel channel, const char *format, ...)
{
    (void)channel;
    logged++;
    strncpy(last, format, sizeof(last) - 1);
}

/* A menu of `lines` lines with `heading` rows above its choices, starting
 * `row` rows down a box of `rows` rows, laid out as the game does: one
 * Text_NewLine per line, whose wrap is past the box from row `rows` on.
 * Returns the choice count the player picks from, -1 if the game stops. */
static int lay_out(int id, int channel, int rows, int row, int lines, int heading)
{
    int line, count = lines, cut = 0;
    TextMenu_Begin(channel);
    for (line = 1; line <= lines; line++) {
        /* The letters of this line are left out once a row ran out. */
        assert(TextMenu_Cutting(channel) == cut);
        if (row + 1 >= rows) {
            if (TextMenu_CutsLine(channel, line, lines)) cut = 1;
            else if (line < lines) return -1;
        } else {
            row++;
        }
    }
    /* Text_TryCompleteChoiceLayout: a heading gives two choices. */
    if (heading) count = 2;
    return TextMenu_Finish(id, channel, heading, count);
}

int main(void)
{
    /* Menus that fit: nothing is cut, nothing is said. */
    assert(lay_out(0x21, 0, 3, 0, 3, 0) == 3);   /* 3 lines in 3 rows */
    assert(lay_out(0xF5, 0, 3, 0, 3, 1) == 2);   /* the name's YES/NO */
    assert(lay_out(0x09, 1, 8, 2, 2, 0) == 2);
    assert(logged == 0);

    /* A, B, C, D in the name box (3 rows): the fourth is cut. */
    assert(lay_out(0xF5, 0, 3, 0, 4, 0) == 3);
    assert(logged == 1 && strstr(last, "more lines than its box"));
    /* Said once per string. */
    assert(lay_out(0xF5, 0, 3, 0, 4, 0) == 3);
    assert(logged == 1);
    /* A menu started on the box's last row: its first choice stays. */
    assert(lay_out(0xF6, 2, 3, 2, 2, 0) == 1);
    assert(logged == 2);
    /* A heading above two choices in a two-row box: one choice is left. */
    assert(lay_out(0xF7, 3, 2, 0, 3, 1) == 1);
    /* Never fewer than one, even with no choice line in the box. */
    assert(lay_out(0xF8, 0, 1, 0, 3, 1) == 1);

    /* A cut is the channel's own and ends with its menu. */
    TextMenu_Begin(0);
    assert(TextMenu_CutsLine(0, 3, 4));
    assert(TextMenu_Cutting(0) && !TextMenu_Cutting(1));
    TextMenu_Begin(0);
    assert(!TextMenu_Cutting(0));
    assert(TextMenu_Finish(0x10, 0, 0, 4) == 4);
    /* The last line is retail's: the menu completes there. */
    assert(!TextMenu_CutsLine(0, 4, 4) && !TextMenu_Cutting(0));
    /* Other channels are left as the console runs them. */
    assert(!TextMenu_CutsLine(4, 1, 4) && !TextMenu_CutsLine(-1, 1, 4) && !TextMenu_Cutting(4));

    /* A menu whose jump for the answer follows its last line, as all of
       the game's do ([00E3]: QUIT, then {choose 80 0 0}): nothing ends. */
    {
        static const unsigned char retail[] = {0xFE, 0xFB, 0x80, 0x00, 0x00, 0x00, 0x00, 0xFB, 0x6C, 0x02};
        static const unsigned char lost[] = {0xFE, 0xFB, 0x6C, 0x02, 0xFC, 0x14, 0x10};
        logged = 0;
        TextMenu_Begin(1);
        TextMenu_LaidOut(1, retail + 1);
        assert(!TextMenu_Unanswered(0xE3, 1, retail + 1));
        assert(logged == 0);
        /* Without it the text would go on into [00E4]'s menu: it ends
           there instead, once, and is said once per string. */
        TextMenu_Begin(1);
        TextMenu_LaidOut(1, lost + 1);
        assert(!TextMenu_Unanswered(0xE3, 0, lost + 1));   /* another channel's text */
        assert(!TextMenu_Unanswered(0xE3, 1, lost));       /* not where the menu left off */
        assert(TextMenu_Unanswered(0xE3, 1, lost + 1));
        assert(logged == 1 && strstr(last, "no {choose}"));
        assert(!TextMenu_Unanswered(0xE3, 1, lost + 1));   /* the text goes on as it may */
        TextMenu_LaidOut(1, lost + 1);
        assert(TextMenu_Unanswered(0xE3, 1, lost + 1) && logged == 1);
        /* A new menu forgets the last one's. */
        TextMenu_LaidOut(1, lost + 1);
        TextMenu_Begin(1);
        assert(!TextMenu_Unanswered(0xE3, 1, lost + 1));
        TextMenu_LaidOut(-1, lost + 1);
        TextMenu_LaidOut(4, lost + 1);
        assert(!TextMenu_Unanswered(0xE3, 4, lost + 1));
    }
    return 0;
}
