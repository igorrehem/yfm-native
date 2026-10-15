#include "menu_cut.h"
#include "pc/debug/log.h"

#define CHANNELS 4

/* The menu line whose row was the first past the box, by channel; 0 while
 * the menu fits. */
static int cut_at[CHANNELS];
/* Where the text of a menu with no jump for its answer goes on, by
 * channel; NULL for the rest. */
static const unsigned char *unanswered[CHANNELS];

void TextMenu_Begin(int channel)
{
    if (channel < 0 || channel >= CHANNELS) return;
    cut_at[channel] = 0;
    unanswered[channel] = 0;
}

int TextMenu_CutsLine(int channel, int lines, int count)
{
    if (channel < 0 || channel >= CHANNELS) return 0;
    /* The last line: Text_TryCompleteChoiceLayout takes over from the wait
     * right after, as on the console. */
    if (lines >= count) return 0;
    if (cut_at[channel] == 0) cut_at[channel] = lines;
    return 1;
}

int TextMenu_Cutting(int channel)
{
    return channel >= 0 && channel < CHANNELS && cut_at[channel] != 0;
}

int TextMenu_Finish(int id, int channel, int heading, int count)
{
    static unsigned char told[0x10000 / 8];
    int shown;
    if (!TextMenu_Cutting(channel)) return count;
    /* The lines down when the box ran out, less the heading's rows. */
    shown = cut_at[channel] - heading;
    cut_at[channel] = 0;
    if (shown < 1) shown = 1;
    if (shown >= count) return count;
    if (id >= 0 && id <= 0xFFFF && !(told[id >> 3] & (1 << (id & 7)))) {
        told[id >> 3] |= (unsigned char)(1 << (id & 7));
        LOG(LOG_MODS, "text: [%04X] has a menu with more lines than its box, which stops the game; "
                      "cut to its first %d choices of %d", id, shown, count);
    }
    return shown;
}

void TextMenu_LaidOut(int channel, const unsigned char *next)
{
    if (channel < 0 || channel >= CHANNELS) return;
    unanswered[channel] = next && !(next[0] == 0xFB && (next[1] & 0x80)) ? next : 0;
}

int TextMenu_Unanswered(int id, int channel, const unsigned char *at)
{
    static unsigned char told[0x10000 / 8];
    if (channel < 0 || channel >= CHANNELS || !unanswered[channel]) return 0;
    if (at != unanswered[channel]) return 0;
    unanswered[channel] = 0;
    if (id >= 0 && id <= 0xFFFF && !(told[id >> 3] & (1 << (id & 7)))) {
        told[id >> 3] |= (unsigned char)(1 << (id & 7));
        LOG(LOG_MODS, "text: [%04X] has a menu with no {choose} after its last line, which stops the game; "
                      "its text ends there instead", id);
    }
    return 1;
}
