#include "../../types.h"
#include "name_entry_keyboard.h"
#include "name_entry_starter_deck.h"
#include "../../game/main_frame.h"
#include "../../game/graphics_frame.h"
#include "../../game/save_data.h"
#include "../../game/card_constants.h"
#include "../../psyq/rand.h"
#include "../../psyq/stdio.h"
#include "../../game/campaign_flags.h"
#include "../../game/util_memory.h"
#ifdef MEMORIES_PC
#include "pc/cards/cards.h"
#include "pc/cards/starter.h"
#include "pc/platform/title_jump.h"
#include "pc/cards/tables.h"

/* The game's own generator, handed to Starter_DealPools so the numbers a new
 * game spends stay the ones the game spends. */
static unsigned NameEntry_StarterRandom(void)
{
    return (unsigned)rand();
}

/* A starter deck a mod wrote down (starter.h): its forty cards as they are,
   in place of the seven weighted pools below. One random number picks which
   deck, where the pools would have drawn one for each card and one for every
   weight they walked past; a new game that takes a mod's deck therefore
   leaves the stream somewhere the disc would not have, which is what letting
   a mod name the cards costs. Cards_MarkSeen rather than the Library's flag
   directly: a card a mod added sits past the range those flags cover, and is
   remembered beside them (cards.c). */
static s32 NameEntry_DealModStarterDeck(void)
{
    unsigned short cards[STARTER_DECK_SIZE];
    unsigned total = Starter_WeightTotal();
    s16 *out;
    s32 i;

    if (total == 0) {
        /* No deck written down: a mod may still weight its own pools, which
         * the disc's rows cannot do for a card a mod added (starter.h). */
        if (!Starter_DealPools(NameEntry_StarterRandom, cards)) {
            return 0;
        }
    } else if (!Starter_Deck(Starter_Roll((unsigned)rand()), cards, 0)) {
        return 0;
    }
    out = (s16 *)gDuel_awPlayerDeck;
    for (i = 0; i < STARTER_DECK_SIZE; i++) {
        out[i] = (s16)cards[i];
        Cards_MarkSeen((int)cards[i]);
    }
    return 1;
}
#endif

void NameEntry_BuildStarterDeck(void)
{
    u8 counts[CARD_COUNT];
    NameEntryStarterDeckPool *G32 *table;
    u16 *entry;
    u16 *p;
    s16 *out;
    s32 remaining;
    s32 acc;
    s32 threshold;
    s32 i;

#ifdef MEMORIES_PC
    if (NameEntry_DealModStarterDeck()) {
        return;
    }
#endif
    for (i = CARD_COUNT - 1; i >= 0; i--) {
        counts[i] = 0;
    }
    out = (s16 *)gDuel_awPlayerDeck;
    table = gNameEntry_apStarterDeckPools;
    entry = (u16 *)*table;
    while (entry != 0) {
        remaining = *entry;
        entry++;
        do {
            threshold = (rand() & 0x7FF) + 1;
            acc = 0;
            i = 0;
            p = entry;
            do {
                rand();
                acc += *p;
                if (acc >= threshold) {
                    if (counts[i] >= 3) {
                        remaining++;
                    } else {
                        counts[i] = counts[i] + 1;
                        *out = i + 1;
                        Library_UpdateCardUsedFlag(i + 289);
                        out++;
                    }
                    break;
                }
                i++;
                p++;
            } while (i < STARTER_DECK_WEIGHT_SCAN_COUNT);
            remaining--;
        } while (remaining != 0);
        table++;
        entry = (u16 *)*table;
    }
}

void NameEntry_Main(void)
{
    SaveDataState *state;
    u8 *entry;
    s32 checksum;
    s32 value;
    s32 i;

    Util_FillMemory(D_801D0000, 0, 0x3000);
    printf("SaveLoadBuf add = 0x%x size = 0x%x\n", D_801D0000, 0x3000);
    NameEntry_Init();
    do {
        Main_AdvanceFrame();
#ifdef MEMORIES_PC
        /* A new game's name entry is a frame loop of its own, before
           Main_Loop's: Game > Restart game is taken here too (title_jump.h),
           or it would wait for the name and stay off after a restart. */
        TitleJump_Poll();
#endif
        rand();
    } while (NameEntry_PollCompletion() == 0);
    NameEntry_BuildStarterDeck();
    state = (SaveDataState *)gDuel_awPlayerDeck;
#ifdef MEMORIES_PC
    /* The cleared save's 0, or a mod's "new_game_starchips" (tables.h),
       at most the starchips the save holds. */
    {
        u32 starchips = (u32)Tables_Value(TABLES_VALUE_NEW_GAME_STARCHIPS, 0);
        state->starchips = starchips > Tables_StarchipCap() ? Tables_StarchipCap() : starchips;
    }
#endif
    checksum = 0;
    entry = state->player_name_sjis;
    for (i = SAVE_DATA_PLAYER_NAME_SIZE - 1; i >= 0; i--) {
        checksum ^= *entry;
        entry++;
    }
    value = D_8009B09C << 8;
    while ((state->duelist_code = value | checksum) == 0) {
        value = rand() << 8;
    }
}
