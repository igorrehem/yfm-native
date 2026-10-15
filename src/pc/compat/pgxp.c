/* PGXP (pgxp.h): the vertices projected in the last two frames, in two hash
 * tables per kind, this frame's and the last's, swapped each frame. A slot
 * belongs to its table only when it carries that table's frame, so a new
 * frame starts with an empty table without clearing it, and a probe stops at
 * the first slot that is not this table's. */
#include "pgxp.h"
#include <math.h>
#include <string.h>

/* A power of two, four times a busy frame's vertices (a full duel field
 * projects about 16000 and places about 20000): full tables probed their
 * whole way on every miss, which halved the frame rate. */
#define TABLE_SIZE 65536
#define PROBES 64

/* The probe sequences below wrap with `& (TABLE_SIZE - 1)`, a fast modulo
 * that only wraps correctly when TABLE_SIZE is a power of two. */
typedef char TABLE_SIZE_must_be_a_power_of_two[(TABLE_SIZE & (TABLE_SIZE - 1)) == 0 ? 1 : -1];

typedef struct {
    uint32_t word;
    unsigned frame;
    int ambiguous;
    float x, y, w;
} Entry;

static Entry table[2][TABLE_SIZE];
static unsigned frame = 2;
int Pgxp_Active;

static unsigned first(uint32_t word)
{
    return (word * 2654435761u) >> 16; /* 16 bits */
}

/* This frame's entry for `word` (made when `make`), or the last frame's
 * (`age` 1), or NULL. */
static Entry *lookup(uint32_t word, unsigned age, int make)
{
    Entry *slots = table[(frame - age) & 1];
    unsigned at = first(word), n;
    for (n = 0; n < PROBES; n++, at = (at + 1) & (TABLE_SIZE - 1)) {
        Entry *entry = &slots[at];
        if (entry->frame != frame - age) {
            if (!make) return 0;
            entry->word = word;
            entry->frame = frame;
            entry->ambiguous = -1; /* new */
            return entry;
        }
        if (entry->word == word) return entry;
    }
    return 0; /* crowded: this one stays at whole pixels */
}

void Pgxp_Project(uint32_t word, double x, double y, double w)
{
    Entry *entry = lookup(word, 0, 1);
    if (!entry) return;
    if (entry->ambiguous < 0) {
        entry->ambiguous = 0;
    } else if (fabs(entry->x - x) > 1.0 / 64 || fabs(entry->y - y) > 1.0 / 64 || fabs(entry->w - w) > 1.0 / 64) {
        entry->ambiguous = 1; /* two vertices round to this word */
        return;
    }
    if (entry->ambiguous) return;
    entry->x = (float)x;
    entry->y = (float)y;
    entry->w = (float)w;
}

/* This frame's projection of `word`, else the last frame's. */
static const Entry *projected(uint32_t word)
{
    const Entry *entry = lookup(word, 0, 0);
    return entry ? entry : lookup(word, 1, 0);
}

int Pgxp_Find(uint32_t word, float *x, float *y, float *w)
{
    const Entry *entry = projected(word);
    if (!entry || entry->ambiguous) return 0;
    *x = entry->x;
    *y = entry->y;
    *w = entry->w;
    return 1;
}

/* By address: where the game's own drawing code wrote a vertex word, with
 * the word written, so nothing is guessed. Last write wins. */
typedef struct {
    uint32_t address, word;
    unsigned frame;
    int known; /* 1 with precise values, 0 without, -1 forgotten */
    float x, y, w;
} Placed;

static Placed placed[2][TABLE_SIZE];

static Placed *place(uint32_t address, unsigned age, int make)
{
    Placed *slots = placed[(frame - age) & 1];
    unsigned at = first(address), n;
    for (n = 0; n < PROBES; n++, at = (at + 1) & (TABLE_SIZE - 1)) {
        Placed *entry = &slots[at];
        if (entry->frame != frame - age) {
            if (!make) return 0;
            entry->address = address;
            entry->frame = frame;
            return entry;
        }
        if (entry->address == address) return entry;
    }
    return 0;
}

/* This frame's entry for `address`, else the last frame's. */
static const Placed *placed_at(uint32_t address)
{
    const Placed *entry = place(address, 0, 0);
    return entry ? entry : place(address, 1, 0);
}

static void forget_at(uint32_t address)
{
    Placed *entry;
    if (!placed_at(address)) return;
    entry = place(address, 0, 1); /* shadows the last frame's */
    if (entry) entry->known = -1;
}

void Pgxp_StoreAt(uint32_t address, uint32_t word, const float *xyw)
{
    Placed *entry = place(address, 0, 1);
    if (!entry) return; /* crowded: left to Pgxp_Find */
    entry->word = word;
    entry->known = xyw != 0;
    if (xyw) {
        entry->x = xyw[0];
        entry->y = xyw[1];
        entry->w = xyw[2];
    }
}

int Pgxp_FindAt(uint32_t address, uint32_t word, float *x, float *y, float *w)
{
    const Placed *entry = placed_at(address);
    if (!entry || entry->known < 0) return 0;
    if (entry->word != word) return 0; /* rewritten since */
    if (!entry->known) return -1;
    *x = entry->x;
    *y = entry->y;
    *w = entry->w;
    return 1;
}

/* The game's own stores of projected vertices (gte_stsxy: Memories_GteStore)
 * since its last addPrim; the primitive it adds is built from them. */
#define STORED 16

typedef struct {
    uint32_t word;
    int known;
    float xyw[3];
} Stored;

static Stored stored[STORED];
static unsigned stored_count;

void Pgxp_Stored(uint32_t word, const float *xyw)
{
    Stored *entry;
    if (stored_count == STORED) {
        memmove(stored, stored + 1, sizeof(stored[0]) * (STORED - 1));
        stored_count--;
    }
    entry = &stored[stored_count++];
    entry->word = word;
    entry->known = xyw != 0;
    if (xyw) memcpy(entry->xyw, xyw, sizeof(entry->xyw));
}

/* A stored word moved by (dx, dy), as GsSortPoly moves it. */
static uint32_t moved(uint32_t word, int dx, int dy)
{
    return ((word + (uint32_t)dx) & 0xffffu) | ((((word >> 16) + (uint32_t)dy) & 0xffffu) << 16);
}

void Pgxp_AddPrimMoved(const void *packet, int dx, int dy)
{
    const uint32_t *words = (const uint32_t *)packet;
    uint32_t base = (uint32_t)(uintptr_t)packet & 0x00ffffffu; /* physical, as packets link */
    unsigned length, i, k;
    if (!Pgxp_Active) {
        stored_count = 0;
        return;
    }
    length = words[0] >> 24;
    for (i = 1; i <= length; i++) {
        int found = -1, clash = 0;
        float xyw[3];
        /* Packet buffers are reused for projected and unprojected drawing.
         * Even an unchanged word is no longer the old address's vertex. */
        forget_at(base + i * 4);
        for (k = stored_count; k-- > 0;) {
            if (moved(stored[k].word, dx, dy) != words[i]) continue;
            if (found < 0) {
                found = (int)k;
            } else if (stored[k].known != stored[found].known ||
                       memcmp(stored[k].xyw, stored[found].xyw, sizeof(stored[k].xyw)) != 0) {
                clash = 1; /* two of this primitive's vertices round to one word */
            }
        }
        if (found < 0) continue;
        xyw[0] = stored[found].xyw[0] + (float)dx;
        xyw[1] = stored[found].xyw[1] + (float)dy;
        xyw[2] = stored[found].xyw[2];
        Pgxp_StoreAt(base + i * 4, words[i], stored[found].known && !clash ? xyw : 0);
    }
    stored_count = 0;
}

void Pgxp_AddPrim(const void *packet)
{
    Pgxp_AddPrimMoved(packet, 0, 0);
}

void Pgxp_NextFrame(void)
{
    frame++;
    stored_count = 0;
}
