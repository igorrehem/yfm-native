/* The text entries' layout (src/pc/text/entry_layout.c): the US table
 * until the game starts, the launch's then, and whichever a loaded state's
 * boundaries say after that. */
#include "pc/text/entry_layout.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>

char D_800EB288[TEXT_ENTRY_US_COUNT * TEXT_ENTRY_SIZE];
unsigned short gDuelEffect_awEntryRangeBoundaries[6] = {0, 255, 415, 575, 620, 0};
static const unsigned short us[6] = {0, 255, 415, 575, 620, 0}, pal[6] = {0, 280, 500, 720, 800, 0};

static void check_us(void)
{
    assert(TextEntries_Pool() == (void *)D_800EB288 && TextEntries_Total() == 620);
}

static void check_pal(void)
{
    assert((uintptr_t)TextEntries_Pool() == TEXT_ENTRY_PAL_POOL && TextEntries_Total() == 800);
}

int main(void)
{
    /* A US launch: nothing changes. */
    check_us();
    assert(TextEntries_PageLetters(0) == 254 && TextEntries_PageLetters(1) == 159);
    assert(TextEntries_PageLetters(2) == 159 && TextEntries_PageLetters(3) == 44);
    assert(TextEntries_PageLetters(4) == 0 && TextEntries_PageLetters(-1) == 0);

    /* A PAL launch: the text is compiled for the PAL pages, while the game
     * data keep the US boundaries (the port's startup picture of them). */
    TextEntries_UseLayout(1);
    check_us();
    assert(!memcmp(gDuelEffect_awEntryRangeBoundaries, us, sizeof(us)));
    assert(TextEntries_PageLetters(0) == 279 && TextEntries_PageLetters(3) == 79);
    TextEntries_Start();
    check_pal();
    assert(!memcmp(gDuelEffect_awEntryRangeBoundaries, pal, sizeof(pal)));
    assert(TextEntries_PageLetters(1) == 219 && TextEntries_PageLetters(3) == 79);

    /* A state with the US boundaries loaded into it: the US table, and its
     * pages; and one with the PAL ones back. */
    memcpy(gDuelEffect_awEntryRangeBoundaries, us, sizeof(us));
    check_us();
    assert(TextEntries_PageLetters(3) == 44);
    memcpy(gDuelEffect_awEntryRangeBoundaries, pal, sizeof(pal));
    check_pal();

    /* The language's text did not compile (Language_Drop): English (US). */
    TextEntries_UseLayout(0);
    TextEntries_Start();
    check_us();
    assert(!memcmp(gDuelEffect_awEntryRangeBoundaries, us, sizeof(us)));
    return 0;
}
