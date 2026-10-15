/* View > Free Duel progress: the counting (free_duel_progress.h). The screen
 * and the drawing are in free_duel_progress_view.c.
 *
 * The drop pools come off the disc as the yamyi-mods Library panel reads
 * them: WA_MRG 0xE9B000 + 0x1800 * (id - 1), three sectors an opponent,
 * four 1460-byte rows of 722 halfword weights (deck, S/A-POW, B/C/D,
 * S/A-TEC) and the rank table. Only the three drop rows count; the deck
 * pool is what an opponent plays with, not what it gives away. Each row
 * then goes through Tables_PoolFor, the call the game's own drop roll
 * makes, so what the player sees is what a duel would roll.
 *
 * Both are fixed for a session: the disc's files (and the data mods that
 * replace them) are put in place at startup, and so are the mods' tables
 * (Tables_Build). The rows are read once and each opponent's cards are
 * worked out once, the first time the cursor rests on it; only the owned
 * half is counted again, since the trunk changes. */
#include "free_duel_progress.h"
#include "tables.h"
#include "cards.h"
#include "pc/free_duel/duelists.h"
#include "pc/sdk/disc.h"
#include "game/card_constants.h"
#include <stdlib.h>
#include <string.h>

/* game/save_data.h: the save's deck, the trunk after it (Cards_ChestSlot). */
extern unsigned short gDuel_awPlayerDeck[];

#define WA_PATH "\\DATA\\WA_MRG.MRG;1"
#define DROPS_SECTOR 7478 /* 0xE9B000 / 2048 */
#define DROPS_SECTORS 3   /* one opponent's block */
#define DROP_ROW 1460     /* 722 weights and 16 bytes of padding */
#define DROP_POOLS 3
/* The disc's own rows: opponents 1-39. A duelist a mod added has none, and
 * reads its base's (Duelists_BaseId), as everything disc-shaped does. */
#define DUELISTS (TABLES_DUELIST_COUNT - 1) /* 1-39; 0 is no opponent */

static int read_state; /* 0 unread, 1 read, -1 not readable */
static unsigned short (*retail)[DROP_POOLS][CARD_COUNT];

/* Per opponent: its obtainable cards by id, once worked out. Grown to the
 * duelist list, which a mod's "duelists" takes past the disc's forty. */
typedef struct {
    int count, card_count; /* card_count: gCard_nCount they were worked out for */
    unsigned short *ids;
} Pool;
static Pool *pools;
static int pool_room;

/* `duelist`'s entry, made if it is not there yet; NULL if memory runs out. */
static Pool *pool_for(int duelist)
{
    if (duelist >= pool_room) {
        const int room = Duelists_Count() > duelist + 1 ? Duelists_Count() : duelist + 1;
        Pool *bigger = realloc(pools, (size_t)room * sizeof(*pools));
        if (!bigger) return NULL;
        memset(bigger + pool_room, 0, (size_t)(room - pool_room) * sizeof(*pools));
        pools = bigger;
        pool_room = room;
    }
    return &pools[duelist];
}

void FreeDuelProgress_Reset(void)
{
    int i;
    for (i = 0; i < pool_room; i++) {
        free(pools[i].ids);
        pools[i].ids = NULL;
        pools[i].count = pools[i].card_count = 0;
    }
    free(pools);
    pools = NULL;
    pool_room = 0;
    free(retail);
    retail = NULL;
    read_state = 0;
}

static int read_retail(void)
{
    static unsigned char block[DROPS_SECTORS * 2048];
    int lba, duelist, pool, i;
    unsigned size;
    if (read_state) return read_state > 0;
    read_state = -1;
    if (Memories_DiscFileInfo(WA_PATH, &lba, &size) != 0 || lba < 0 ||
        size < (unsigned)(DROPS_SECTOR + DUELISTS * DROPS_SECTORS) * 2048u)
        return 0;
    retail = calloc(DUELISTS, sizeof(*retail));
    if (!retail) return 0;
    for (duelist = 1; duelist <= DUELISTS; duelist++) {
        if (Memories_DiscReadSectors(lba + DROPS_SECTOR + (duelist - 1) * DROPS_SECTORS, DROPS_SECTORS, block) !=
            DROPS_SECTORS) {
            free(retail);
            retail = NULL;
            return 0;
        }
        for (pool = 0; pool < DROP_POOLS; pool++) {
            const unsigned char *row = block + (pool + 1) * DROP_ROW;
            for (i = 0; i < CARD_COUNT; i++)
                retail[duelist - 1][pool][i] = (unsigned short)(row[i * 2] | (unsigned)row[i * 2 + 1] << 8);
        }
    }
    read_state = 1;
    return 1;
}

/* The union of the three pools as the mods have them. Tables_PoolFor gives
 * weights by card id (gCard_nCount + 1 of them), or NULL when no mod edits
 * that pool and the disc's row (by id - 1) stands. */
static int work_out(int duelist)
{
    unsigned char *seen;
    int count = gCard_nCount < CARD_COUNT ? CARD_COUNT : gCard_nCount, pool, id, n = 0;
    const int base = Duelists_BaseId(duelist);
    Pool *mine = pool_for(duelist);
    if (!mine || base < 1 || base > DUELISTS) return 0;
    if (mine->ids && mine->card_count == gCard_nCount) return 1;
    seen = calloc((size_t)count + 1, 1);
    if (!seen) return 0;
    for (pool = 0; pool < DROP_POOLS; pool++) {
        /* The disc's row is the base's; the edits are this duelist's own. */
        const unsigned short *row = retail[base - 1][pool];
        const unsigned short *edited = Tables_PoolFor(duelist, TABLES_POOL_POW + pool, row);
        if (edited) {
            for (id = 1; id <= gCard_nCount; id++) seen[id] |= edited[id] != 0;
        } else {
            for (id = 1; id <= CARD_COUNT; id++) seen[id] |= row[id - 1] != 0;
        }
    }
    free(mine->ids);
    mine->ids = malloc(((size_t)count + 1) * sizeof(*mine->ids));
    if (!mine->ids) {
        free(seen);
        return 0;
    }
    for (id = 1; id <= count; id++) {
        if (seen[id]) mine->ids[n++] = (unsigned short)id;
    }
    free(seen);
    mine->count = n;
    mine->card_count = gCard_nCount;
    return 1;
}

/* Whether the deck or the trunk holds `id`, as drops.c's owned() counts. */
static int held(int id)
{
    int i;
    if (*Cards_ChestSlot(gDuel_awPlayerDeck, id)) return 1;
    for (i = 0; i < DECK_SIZE; i++) {
        if (gDuel_awPlayerDeck[i] == id) return 1;
    }
    return 0;
}

int FreeDuelProgress_Count(int duelist, int *owned, int *obtainable)
{
    int i, have = 0;
    if (duelist < 1 || !Duelists_Valid(duelist) || !read_retail() || !work_out(duelist)) return 0;
    for (i = 0; i < pools[duelist].count; i++) have += held(pools[duelist].ids[i]);
    *owned = have;
    *obtainable = pools[duelist].count;
    return 1;
}
