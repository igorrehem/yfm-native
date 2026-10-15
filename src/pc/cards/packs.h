#ifndef MEMORIES_PC_PACKS_H
#define MEMORIES_PC_PACKS_H
/* Card packs (booster packs): what mods declare and how a pack is opened
 * (notes/card-packs.md).
 *
 * A mod's manifest may carry "packs", a list of packs -- or the name of a
 * file of the mod that holds them -- and "pack_shop", the rules of the shop
 * they are sold in. The packs of every applied mod add up, as the starter
 * decks do; "pack_shop" is the last mod's in the load order, and its "shops"
 * add up by id. Everything is read once, from Cards_Build, and needs a
 * restart like the other tables.
 *
 * This part knows nothing of the screen (pack_shop.h): it reads the
 * manifests, checks them, and deals a pack from a stream of random numbers.
 * A pack always spends PACK_DRAWS_PER_SLOT numbers a slot, whatever it
 * holds, so a replay of the same input deals the same cards and spends the
 * same numbers: a guarantee, the pity, "unique_in_pack" and "max_copies"
 * choose among the numbers already drawn rather than drawing more.
 *
 * The FM Editor's Simulate (tools/pc/fm_editor/packs.py) is this dealer
 * again in Python; tests/pc/packs_golden.txt holds what both deal for the
 * same numbers.
 *
 * With no pack declared, nothing here is asked and nothing changes. */
#include <stdio.h>

#define PACKS_MAX 255
#define PACK_TIERS_MAX 16
#define PACK_SHOPS_MAX 16
#define PACK_COUNT_MAX 40
#define PACK_COST_CARDS_MAX 8
#define PACK_OPENED_MAX 8          /* "unlock": {"opened": {...}} entries */
#define PACK_KEY_MAX 64            /* an "id", a tier's or a shop's name: 1-63 of [A-Za-z0-9_-] */
#define PACK_IDENTITY_MAX 130      /* "mod-id:pack-id" */
#define PACK_TEXT_MAX 128          /* a name, a label: UTF-8 */
#define PACK_DESCRIPTION_MAX 256
#define PACK_PATH_MAX 1024
#define PACK_WEIGHT_TOTAL_MAX 1000000
#define PACK_PRICE_MAX 999999
#define PACK_DRAWS_PER_SLOT 4
#define PACK_DEFAULT_COUNT 5
#define PACK_DEFAULT_PRICE 100
#define PACK_NAME_LETTERS 16       /* the name's room between the list's arrows */

enum { PACK_REVEAL_FLIP, PACK_REVEAL_QUICK, PACK_REVEAL_LIST };
/* "image_style": the "image" as a card's art in the card's frame, or the
 * whole picture where the card is drawn (pack_shop.c). */
enum { PACK_IMAGE_CARD, PACK_IMAGE_FULL };
enum { PACK_SOUND_MOVE, PACK_SOUND_BUY, PACK_SOUND_REFUSE, PACK_SOUND_REVEAL, PACK_SOUND_BACK, PACK_SOUNDS };
/* "pack_shop": {"password": ...}: where the Password screen stands. */
enum { PACK_SHOP_BOTH, PACK_SHOP_PACKS_ONLY, PACK_SHOP_PASSWORD_ONLY };
enum { PACK_RNG_GAME, PACK_RNG_SAVE };
/* "when_nothing_left": a pack every card of which the player already holds
 * "max_copies" of. PACK_NOTHING_SHOPS: the pack says nothing, the shop's
 * rule is used. */
enum { PACK_NOTHING_SHOPS = -1, PACK_NOTHING_REFUSE, PACK_NOTHING_SELL };

typedef struct {
    unsigned short card;
    unsigned weight;
} PackEntry;

typedef struct {
    PackEntry *entries;
    int count;
} PackPool;

typedef struct {
    char name[PACK_KEY_MAX];
    unsigned odds;
    PackPool pool;
    char label[PACK_TEXT_MAX];     /* "ULTRA RARE!", or "" for none */
    int color;                     /* the game's text color ({f8 0A n}), -1 for the default */
    int sound;                     /* a sound effect id, -1 for the pack's reveal sound */
    int reveal;                    /* PACK_REVEAL_*, -1 for the pack's */
} PackTier;

enum { PACK_SLOT_ODDS, PACK_SLOT_TIER, PACK_SLOT_MIX, PACK_SLOT_POOL, PACK_SLOT_CARD };
typedef struct {
    int kind;
    int tier;                      /* PACK_SLOT_TIER */
    unsigned mix[PACK_TIERS_MAX];  /* PACK_SLOT_MIX: a weight by tier */
    PackPool pool;                 /* PACK_SLOT_POOL */
    int card;                      /* PACK_SLOT_CARD */
} PackSlot;

/* "unlock": every condition given must hold. The first five are the
 * duelists' own (pc/free_duel/duelists.h), read from the save. */
typedef struct {
    char beat[PACK_TEXT_MAX];
    int wins;
    int story;                     /* -1 for none */
    char card[PACK_TEXT_MAX];
    int copies;
    unsigned starchips_spent;      /* on packs, by this save */
    unsigned packs_opened;         /* all packs, by this save */
    int opened_count;
    char opened_name[PACK_OPENED_MAX][PACK_IDENTITY_MAX];
    int opened_pack[PACK_OPENED_MAX];   /* resolved once every pack is read; -1 for none */
    unsigned opened_times[PACK_OPENED_MAX];
    int never;                     /* written wrong: kept locked, so nothing opens by mistake */
} PackUnlock;

typedef struct {
    char mod[PACK_KEY_MAX];
    char id[PACK_KEY_MAX];
    char identity[PACK_IDENTITY_MAX];
    char name[PACK_TEXT_MAX];
    char description[PACK_DESCRIPTION_MAX];
    char image[PACK_PATH_MAX];     /* a PNG, whole path; "" for none */
    int cover;                     /* the card whose art stands in for an image */
    unsigned shops;                /* a bit per shop (PackShopRules), all when "shop" is left out */
    long order;
    int declared;                  /* its place among every pack read */
    unsigned price;                /* starchips */
    int cost_cards;
    unsigned short cost_card[PACK_COST_CARDS_MAX];
    unsigned char cost_copies[PACK_COST_CARDS_MAX];
    int count;
    PackTier tiers[PACK_TIERS_MAX];
    int tier_count;
    PackSlot *slots;               /* `count` of them, or NULL: every slot by the tiers' odds */
    int guarantee[PACK_TIERS_MAX]; /* at least n of that tier or above; 0 for none */
    int pity[PACK_TIERS_MAX];      /* the n-th opening in a row without it has one; 0 for none */
    int unique;                    /* "duplicates": "unique_in_pack" */
    int max_copies;                /* 0 for no limit */
    int when_nothing_left;         /* PACK_NOTHING_*: -1 for the shop's */
    int include_added;
    int stock;                     /* purchases a save may make; -1 for no limit */
    int has_unlock;
    PackUnlock unlock;
    int locked_shown;              /* "locked": "shown" */
    int has_password;
    unsigned password;             /* eight digits, four bits each, as the disc's table packs them */
    int once;                      /* a password pack a save may open only once */
    int listed;                    /* in the list; a password pack is not, unless it says */
    int reveal;
    int sounds[PACK_SOUNDS];
    int image_style;               /* PACK_IMAGE_*; last, so the fields before keep v0.2.0's offsets */
} Pack;

typedef struct {
    char id[PACK_KEY_MAX];
    char name[PACK_TEXT_MAX];
    int has_unlock;
    PackUnlock unlock;
} PackShop;

typedef struct {
    int password;                  /* PACK_SHOP_* */
    int rng;                       /* PACK_RNG_* */
    int music;                     /* the screen's song while it sells packs */
    int when_nothing_left;         /* PACK_NOTHING_REFUSE or _SELL: for a pack that says nothing */
    PackShop shops[PACK_SHOPS_MAX];
    int shop_count;
    char from[PACK_KEY_MAX];       /* the mod whose rules these are; "" for the defaults */
} PackShopRules;

/* --- what a save holds of the packs ------------------------------------- */

typedef struct {
    unsigned bought;               /* purchases, for "stock" */
    unsigned opened;
    unsigned short pity[PACK_TIERS_MAX];   /* openings in a row without the tier */
    unsigned char used;            /* a "once" password pack was opened */
} PackProgress;

typedef struct {
    unsigned starchips_spent;
    unsigned packs_opened;
    PackProgress packs[PACKS_MAX];
} PacksProgress;

/* --- reading ------------------------------------------------------------ */

/* Every applied mod's "packs" and "pack_shop"; once, from Cards_Build,
 * after the cards and duelists they name. */
void Packs_Build(void);
/* One manifest's, for the tests and Packs_Build: `directory` is the mod's,
 * for a "packs" file and the images. Call Packs_Finish once all are in. */
struct JsonValue;
void Packs_Add(const char *mod, const char *directory, const struct JsonValue *manifest);
void Packs_Finish(void);
void Packs_Clear(void);

int Packs_Count(void);
/* In the list's order ("order", then as declared). NULL past the end. */
const Pack *Packs_At(int index);
/* The pack an identity ("mod:id"), or an id alone that one pack has, names;
 * -1 for none. */
int Packs_Find(const char *name);
const PackShopRules *Packs_Rules(void);
/* A hash of what the manifests do not hold themselves: the "packs" files
 * and the images (Mods_Signature). 0 without packs. */
unsigned Packs_Signature(void);
/* The pack whose password this is (eight digits, four bits each), or -1. */
int Packs_WithPassword(unsigned password);

/* --- opening ------------------------------------------------------------ */

/* One of the game's random numbers, 0 to 0x7FFF. */
typedef int (*PackRandom)(void *context);
/* Copies of a card the player holds, trunk and deck: for "max_copies". */
typedef int (*PackHeld)(int card, void *context);

typedef struct {
    int count;                                 /* slots dealt, = the pack's count */
    unsigned short cards[PACK_COUNT_MAX];      /* 0 where a slot had nothing to give */
    signed char tiers[PACK_COUNT_MAX];         /* the tier each came from; -1 for a slot's own pool or card */
    unsigned char redone[PACK_COUNT_MAX];      /* dealt again for a guarantee or the pity */
} PackResult;

/* Copies of a card the chest still takes (NULL for no limit, the start):
 * a card with no room left for one more, with what the pack already dealt,
 * is not dealt from a pool, as for "max_copies", so a purchase never pays
 * for a card the chest would drop. A fixed card is dealt whatever the room
 * (Packs_FixedCardsFit). */
void Packs_SetChestRoom(PackHeld room, void *context);

/* Deal pack `pack` from `random`: always PACK_DRAWS_PER_SLOT * count
 * numbers. `progress` gives the pity counters (NULL for none); `held` the
 * copies for "max_copies" (NULL for none). Returns the cards dealt. */
int Packs_Deal(int pack, const PacksProgress *progress, PackHeld held, void *held_context, PackRandom random,
               void *random_context, PackResult *result);

/* rng "save": a Psy-Q generator of its own, seeded by the save's duelist
 * code, the pack and how often the save has opened it, so reloading a save
 * deals the same pack again. The game's own numbers are left alone. */
unsigned Packs_SaveSeed(unsigned duelist_code, const char *identity, unsigned opened);
int Packs_LcgNext(void *seed);   /* a PackRandom over an unsigned seed */

/* A purchase went through: the counters, the stock and the pity. */
void Packs_Record(int pack, const PackResult *result, unsigned starchips, PacksProgress *progress);

/* Whether the save meets a pack's (or a shop's) "unlock". `save` answers
 * the conditions only the save holds (beat, wins, story, card, copies);
 * it is not asked when there are none. */
typedef int (*PackSaveCondition)(const PackUnlock *unlock, void *context);
int Packs_UnlockMet(const PackUnlock *unlock, const PacksProgress *progress, PackSaveCondition save, void *context);
int Packs_Unlocked(int pack, const PacksProgress *progress, PackSaveCondition save, void *context);
/* Purchases left, or -1 for no limit. */
int Packs_StockLeft(int pack, const PacksProgress *progress);
/* Whether the pack has nothing left to deal the player: it has no slot of
 * a fixed card (always dealt), and every card of every pool is one the
 * player holds "max_copies" of (`held`, as for Packs_Deal) or the chest has
 * no room for (Packs_SetChestRoom). A pack with some cards left is not: it
 * may still deal empty slots. */
int Packs_NothingLeft(int pack, PackHeld held, void *held_context);
/* Whether the chest has room for every fixed card ({"card": X} slots) the
 * pack deals; 1 without a room (Packs_SetChestRoom). */
int Packs_FixedCardsFit(int pack);
/* Whether such a pack is refused rather than sold ("when_nothing_left": the
 * pack's, else the shop's; "refuse" by default). */
int Packs_RefusesWhenNothingLeft(int pack);
/* The chance, in millionths, that one slot dealt by the tiers' odds is of
 * tier `tier`, and that a card of a tier's pool is `card` (the pack's
 * details page and the editor's Chance column). */
unsigned Packs_TierChance(int pack, int tier);

/* --- beside the save ---------------------------------------------------- */

/* The progress as text: lines by identity, so a pack a mod no longer has
 * keeps its line. Read replaces `progress`; lines of packs not here this run
 * are kept and written back. */
void Packs_ReadProgress(FILE *file, PacksProgress *progress);
void Packs_WriteProgress(FILE *file, const PacksProgress *progress);
void Packs_ForgetProgress(PacksProgress *progress);
/* Whether there is nothing to write: no pack bought, and no line kept of a
 * pack not here this run. */
int Packs_ProgressEmpty(const PacksProgress *progress);
/* The lines kept of packs not here this run ("" for none, `size` their
 * bytes), and setting them, for a save state (pack_shop.c PackShop_State):
 * they go with the progress the state holds. */
const char *Packs_ForeignLines(size_t *size);
void Packs_SetForeignLines(const char *text, size_t size);

#endif
