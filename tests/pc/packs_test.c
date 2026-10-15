/* Card packs (src/pc/cards/packs.c, notes/card-packs.md): real manifests
 * through the real JSON reader, over a made-up card table where a card is
 * named by its id. What is checked without a screen: every rule the reader
 * enforces, the numbers a pack spends (always four a slot), the guarantee,
 * the pity, "unique_in_pack", "max_copies", the fall to a commoner tier,
 * "when_nothing_left", the unlock conditions, the progress file, and the
 * golden deals the FM Editor's Simulate must match (packs_fixture.json,
 * packs_golden.txt).
 *
 * PACKS_GOLDEN_WRITE=1 writes packs_golden.txt anew from this build. */
#define _POSIX_C_SOURCE 200809L /* scratch.h: mkdtemp, lstat, kill */
#include "scratch.h"
#include "../../src/pc/cards/packs.c"
#include <stdarg.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

#ifndef PACKS_TEST_DIR
#define PACKS_TEST_DIR "tests/pc"
#endif

/* --- the port around packs.c ---------------------------------------------- */

int Cards_Named(const char *text)
{
    char *end;
    long id;
    if (!text || !*text) return 0;
    id = strtol(text, &end, 10);
    return !*end && id >= CARD_ID_FIRST && id <= 2000 ? (int)id : -1;
}
int Cards_Reference(const JsonValue *value)
{
    if (!value || Json_TypeOf(value) == JSON_NULL) return 0;
    if (Json_TypeOf(value) == JSON_NUMBER) {
        long id = Json_Number(value, 0);
        return id >= CARD_ID_FIRST && id <= 2000 ? (int)id : -1;
    }
    return Cards_Named(Json_String(value, NULL));
}
int Paths_Contained(const char *relative) { return relative && *relative && relative[0] != '/' && !strstr(relative, ".."); }

static int notes;
static char note[512], all_notes[8192];
void Mods_Note(const char *id, const char *format, ...)
{
    va_list arguments;
    size_t used = strlen(all_notes);
    (void)id;
    notes++;
    va_start(arguments, format);
    vsnprintf(note, sizeof(note), format, arguments);
    va_end(arguments);
    snprintf(all_notes + used, sizeof(all_notes) - used, "%s\n", note);
}
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel; (void)format; }
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { (void)index; return 0; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return "test"; }
const char *Mods_Directory(int mod) { (void)mod; return "."; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

/* --- the harness -------------------------------------------------------------- */

static JsonDocument *documents[64];
static int document_count;

static void add(const char *mod, const char *text)
{
    char error[256];
    JsonDocument *document = Json_Parse(text, error, sizeof(error));
    if (!document) fprintf(stderr, "%s\n", error);
    CHECK(document != NULL);
    Packs_Add(mod, PACKS_TEST_DIR, Json_Root(document));
    if (document_count < 64) documents[document_count++] = document;
}

static void fresh(void)
{
    /* The reader copies what it keeps: the manifests can go (and the leak
       check under ASan finds none of them). */
    while (document_count) Json_Free(documents[--document_count]);
    Packs_Clear();
    notes = 0;
    note[0] = all_notes[0] = 0;
}

/* One manifest, finished: how many packs it gave. */
static int one(const char *text)
{
    fresh();
    add("test", text);
    Packs_Finish();
    return Packs_Count();
}

static int noted(const char *words) { return strstr(all_notes, words) != NULL; }

typedef struct {
    unsigned seed;
    int draws;
} Counting;

static int counting_random(void *context)
{
    Counting *c = context;
    c->draws++;
    return Packs_LcgNext(&c->seed);
}

typedef struct {
    int cards[8], copies[8], count;
} Held;

static int held_copies(int card, void *context)
{
    const Held *held = context;
    int i;
    for (i = 0; held && i < held->count; i++) if (held->cards[i] == card) return held->copies[i];
    return 0;
}

/* --- the reader --------------------------------------------------------------- */

static void test_minimal(void)
{
    const Pack *pack;
    CHECK(one("{\"packs\": [{\"name\": \"Dragons\", \"price\": 50, \"cards\": [1, 2, 3]}]}") == 1);
    pack = Packs_At(0);
    CHECK(!strcmp(pack->id, "dragons"));
    CHECK(!strcmp(pack->identity, "test:dragons"));
    CHECK(pack->price == 50 && pack->count == PACK_DEFAULT_COUNT);
    CHECK(pack->tier_count == 1 && pack->tiers[0].pool.count == 3);
    CHECK(pack->stock == -1 && !pack->has_unlock && pack->listed && pack->reveal == PACK_REVEAL_FLIP);
    CHECK(pack->cover == 1);
    CHECK(pack->sounds[PACK_SOUND_BUY] == 48 && pack->sounds[PACK_SOUND_MOVE] == 47);
    CHECK(Packs_Rules()->password == PACK_SHOP_BOTH && Packs_Rules()->shop_count == 1);
    CHECK(Packs_Rules()->music == 29520 && Packs_Rules()->rng == PACK_RNG_GAME);
    CHECK(pack->shops == 1u);
    CHECK(notes == 0);
    CHECK(Packs_Signature() != 0);
    /* No packs: nothing, and no signature. */
    CHECK(one("{\"name\": \"no packs\"}") == 0);
    CHECK(Packs_Signature() == 0);
}

static void test_errors(void)
{
    /* Each leaves the pack out, and says why. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"count\": 0}]}") == 0 && noted("\"count\" is 1 to 40"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"count\": 41}]}") == 0);
    {   /* 41 slots and no "count": the count the slots give is held to 40 too. */
        char text[1024];
        int n = snprintf(text, sizeof(text), "{\"packs\": [{\"cards\": [1], \"slots\": ["), i;
        for (i = 0; i < PACK_COUNT_MAX + 1; i++) n += snprintf(text + n, sizeof(text) - (size_t)n, "%s{\"card\": 1}", i ? ", " : "");
        snprintf(text + n, sizeof(text) - (size_t)n, "]}]}");
        CHECK(one(text) == 0 && noted("\"count\" is 1 to 40"));
    }
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"cards\": [1]}}, \"count\": 3, \"slots\": [\"a\", \"a\"]}]}") == 0 &&
          noted("\"slots\" is a list of 3"));
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"cards\": [1]}}, \"slots\": [\"a\", \"b\"]}]}") == 0 && noted("no tier \"b\""));
    CHECK(one("{\"packs\": [{\"cards\": {\"1\": -2}}]}") == 0 && noted("a weight is a whole number"));
    CHECK(one("{\"packs\": [{\"cards\": {\"1\": 600000, \"2\": 600000}}]}") == 0 && noted("add up to 1200000"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"price\": 1000000}]}") == 0 && noted("0 to 999999 starchips"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"cost\": {\"starchips\": 1000000}}]}") == 0);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"id\": \"bad id!\"}]}") == 0 && noted("\"id\" is 1-63"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"id\": \"x\"}, {\"cards\": [2], \"id\": \"x\"}]}") == 1 &&
          noted("another pack's of this mod"));
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"cards\": [1]}}, \"guarantee\": {\"b\": 1}}]}") == 0);
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"cards\": [1]}}, \"pity\": {\"a\": 0}}]}") == 0);
    CHECK(one("{\"packs\": [{\"cards\": [1, 2], \"count\": 3, \"duplicates\": \"unique_in_pack\"}]}") == 0 &&
          noted("unique_in_pack"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"tiers\": {\"a\": {\"cards\": [1]}}}]}") == 0 && noted("give one"));
    CHECK(one("{\"packs\": [{\"cards\": [9999]}]}") == 0 && noted("none of its cards are here"));
    CHECK(one("{\"packs\": [{\"name\": \"no cards\"}]}") == 0 && noted("no \"cards\" or \"tiers\""));
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"odds\": 0, \"cards\": [1]}}}]}") == 0 && noted("every tier's"));
    /* ...but a tier of odds 0 is fine when the slots name it. */
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"odds\": 0, \"cards\": [1]}}, \"slots\": [\"a\"]}]}") == 1);
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"cards\": [1]}}, \"slots\": [{\"card\": 5000}]}]}") == 0);
    CHECK(one("{\"packs\": [{\"tiers\": {\"a b\": {\"cards\": [1]}}}]}") == 0 && noted("a tier's name"));
    CHECK(one("{\"packs\": {\"cards\": [1]}}") == 0 && noted("\"packs\" is a list of packs"));
    /* An id past 63 letters is left out, not cut to fit. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"id\": \"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"}]}") == 0 &&
          noted("\"id\" is 1-63"));
    /* "cost" "cards" is an object of cards and copies, nothing else. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"cost\": {\"cards\": [\"x\"]}}]}") == 0 && noted("{card: copies}"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"cost\": {\"cards\": null}}]}") == 0);
    /* A null is a value of the wrong kind, not a key left out. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"price\": null}]}") == 0);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"guarantee\": null}]}") == 0);
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"odds\": null, \"cards\": [1]}}}]}") == 0);
    /* A whole number written with a fraction of zeroes is that number. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"price\": 100.0, \"count\": 2e0}]}") == 1);
    CHECK(Packs_At(0)->price == 100 && Packs_At(0)->count == 2);
    /* Tiers named twice. */
    CHECK(one("{\"packs\": [{\"tiers\": {\"a\": {\"cards\": [1]}, \"a\": {\"cards\": [2]}}}]}") == 0 &&
          noted("named twice"));
    /* "unique_in_pack" with one card fixed in two slots cannot hold. */
    CHECK(one("{\"packs\": [{\"cards\": [1, 2, 3], \"slots\": [{\"card\": 5}, \"cards\", {\"card\": 5}], "
              "\"duplicates\": \"unique_in_pack\"}]}") == 0 && noted("fixed in slots 1 and 3"));
    /* The fixed cards count among the different cards: 2 + 1 for 3 slots. */
    CHECK(one("{\"packs\": [{\"cards\": [1, 2], \"slots\": [\"cards\", \"cards\", {\"card\": 5}], "
              "\"duplicates\": \"unique_in_pack\"}]}") == 1);
    CHECK(one("{\"packs\": [{\"cards\": [1, 5], \"slots\": [\"cards\", \"cards\", {\"card\": 5}], "
              "\"duplicates\": \"unique_in_pack\"}]}") == 0 && noted("unique_in_pack"));
}

static void test_warnings(void)
{
    const Pack *pack;
    /* An unknown card is dropped, the pack stays. */
    CHECK(one("{\"packs\": [{\"cards\": [1, 9999, \"Nobody\"]}]}") == 1 && noted("no card \"9999\"") && noted("Nobody"));
    CHECK(Packs_At(0)->tiers[0].pool.count == 1);
    /* A long name is cut at sixteen letters, the room between the arrows. */
    CHECK(one("{\"packs\": [{\"name\": \"A Very Long Pack Name Indeed\", \"cards\": [1]}]}") == 1 && noted("cut there"));
    CHECK(strlen(Packs_At(0)->name) == PACK_NAME_LETTERS);
    CHECK(!strcmp(Packs_At(0)->id, "a-very-long-pack-name-indeed"));
    /* A typo gets the likeliest key; a key of the design not built yet says so. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"prise\": 5, \"restock\": {}}]}") == 1 && noted("did you mean \"price\"") &&
          noted("\"restock\" is not built yet"));
    CHECK(one("{\"packs\": [{\"cards\": [1]}], \"pack_shop\": {\"autosave\": true, \"campaign_shop\": true}}") == 1 &&
          noted("\"autosave\" is not built yet") && noted("\"campaign_shop\" is not built yet"));
    /* "include_added_cards": false refuses a mod's cards. */
    CHECK(one("{\"packs\": [{\"cards\": [1, 800], \"include_added_cards\": false}]}") == 1 && noted("is a mod's"));
    CHECK(Packs_At(0)->tiers[0].pool.count == 1);
    /* An image that is not there: the cover stands in. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"image\": \"packs/missing.png\"}]}") == 1 && noted("cannot be read"));
    CHECK(Packs_At(0)->image[0] == 0);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"image\": \"../outside.png\"}]}") == 1 && noted("inside the mod"));
    /* "image_style": "card" unless it says "full"; another word is said. */
    CHECK(one("{\"packs\": [{\"cards\": [1]}, {\"id\": \"b\", \"cards\": [1], \"image_style\": \"card\"}]}") == 2);
    CHECK(Packs_At(0)->image_style == PACK_IMAGE_CARD && Packs_At(1)->image_style == PACK_IMAGE_CARD && notes == 0);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"image\": \"packs/missing.png\", \"image_style\": \"full\"}]}") == 1 &&
          noted("cannot be read") && !noted("there is none"));
    CHECK(Packs_At(0)->image_style == PACK_IMAGE_FULL);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"image_style\": \"full\"}]}") == 1 && noted("there is none"));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"image_style\": \"poster\"}]}") == 1 &&
          noted("\"image_style\" is \"card\" or \"full\""));
    CHECK(Packs_At(0)->image_style == PACK_IMAGE_CARD);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"image_styl\": \"full\"}]}") == 1 && noted("did you mean \"image_style\""));
    /* "price" and "cost" at odds: "cost" wins. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"price\": 5, \"cost\": {\"starchips\": 7, \"cards\": {\"3\": 2}}}]}") == 1 &&
          noted("\"cost\" is used"));
    pack = Packs_At(0);
    CHECK(pack->price == 7 && pack->cost_cards == 1 && pack->cost_card[0] == 3 && pack->cost_copies[0] == 2);
    /* A password: listed only if it says. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"password\": \"00001234\"}, {\"cards\": [2], \"id\": \"b\", \"password\": 1234, "
              "\"listed\": true}]}") == 2);
    CHECK(Packs_At(0)->password == 0x1234 && !Packs_At(0)->listed && Packs_At(1)->listed);
    CHECK(noted("its password is pack"));
    CHECK(Packs_WithPassword(0x1234) == 0 && Packs_WithPassword(0x4321) == -1);
    /* A pack without "order" is placed among the packs past their id (the
       editor counts the same): "a" is 0, as "b" says it is, and is sold. */
    CHECK(one("{\"packs\": [{\"id\": \"bad id!\", \"cards\": [1]}, {\"id\": \"a\", \"cards\": [1], \"password\": 7}, "
              "{\"id\": \"b\", \"cards\": [1], \"password\": 7, \"order\": 0}]}") == 2);
    CHECK(!strcmp(Packs_At(0)->id, "a") && noted("pack \"b\": its password is pack \"test:a\"'s too"));
    CHECK(one("{\"packs\": [{\"id\": \"x\", \"cards\": [1], \"price\": -1}, {\"id\": \"a\", \"cards\": [1]}, "
              "{\"id\": \"b\", \"cards\": [1], \"order\": 0}]}") == 2 && !strcmp(Packs_At(0)->id, "b"));
    /* "sounds" of the wrong kind (an array's items have no keys to check). */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"sounds\": [1, 2]}]}") == 1 && noted("\"sounds\" is {"));
    CHECK(Packs_At(0)->sounds[PACK_SOUND_BUY] == 48);
    CHECK(one("{\"packs\": [{\"cards\": [1], \"sounds\": {\"buy\": 60}}]}") == 1 && Packs_At(0)->sounds[PACK_SOUND_BUY] == 60);
    /* A description past its room is cut between two letters, never inside one. */
    {
        char text[1024];
        int n = snprintf(text, sizeof(text), "{\"packs\": [{\"cards\": [1], \"description\": \"x"), i;
        for (i = 0; i < 200; i++) n += snprintf(text + n, sizeof(text) - (size_t)n, "\xC3\xA9");   /* e acute */
        snprintf(text + n, sizeof(text) - (size_t)n, "\"}]}");
        CHECK(one(text) == 1 && noted("the description has room for 255 bytes"));
        CHECK(strlen(Packs_At(0)->description) == 255);   /* "x" and 127 whole letters */
        CHECK(((unsigned char)Packs_At(0)->description[254] & 0xC0) == 0x80);
    }
    /* The shop's rules: a value of the wrong kind is said, and the default kept. */
    CHECK(one("{\"packs\": [{\"cards\": [1]}], \"pack_shop\": {\"password\": 5, \"rng\": null, "
              "\"shops\": [{\"id\": \"a\", \"where\": null}, {\"id\": 5}]}}") == 1);
    CHECK(noted("\"password\" is \"both\"") && noted("\"rng\" is \"game\"") && noted("only \"where\": \"password\""));
    CHECK(noted("a shop is {") && Packs_Rules()->shop_count == 1);
    CHECK(Packs_Rules()->password == PACK_SHOP_BOTH && Packs_Rules()->rng == PACK_RNG_GAME);
}

/* The chest's room (Packs_SetChestRoom): Held lists the cards with less
 * than the disc's 250 left. */
static int room_left(int card, void *context)
{
    const Held *room = context;
    int i;
    for (i = 0; i < room->count; i++) if (room->cards[i] == card) return room->copies[i];
    return 250;
}

/* A card the chest has no room for is not dealt, with or without
 * "max_copies"; a pack of nothing else has nothing left, and a fixed card
 * without room makes the pack not fit (the shop refuses it). */
static void test_chest_room(void)
{
    Held full1 = {{1}, {0}, 1}, both = {{1, 2}, {0, 0}, 2}, two_of_2 = {{1, 2}, {0, 2}, 2};
    Counting counting = {11, 0};
    PackResult result;
    int s, of2 = 0;
    CHECK(one("{\"packs\": [{\"cards\": [1, 2], \"count\": 5}]}") == 1);
    Packs_SetChestRoom(room_left, &full1);
    Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
    for (s = 0; s < result.count; s++) CHECK(result.cards[s] == 2);
    CHECK(!Packs_NothingLeft(0, NULL, NULL) && Packs_FixedCardsFit(0));
    /* Room for two of card 2: two slots, then nothing. */
    Packs_SetChestRoom(room_left, &two_of_2);
    Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
    for (s = 0; s < result.count; s++) of2 += result.cards[s] == 2;
    CHECK(of2 == 2);
    for (s = 0; s < result.count; s++) CHECK(result.cards[s] == 2 || result.cards[s] == 0);
    Packs_SetChestRoom(room_left, &both);
    CHECK(Packs_NothingLeft(0, NULL, NULL));
    Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
    for (s = 0; s < result.count; s++) CHECK(result.cards[s] == 0);
    /* Fixed cards: dealt, and two of card 2 fit in a room of two, three do not. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"slots\": [{\"card\": 2}, {\"card\": 2}, \"cards\"]}]}") == 1);
    Packs_SetChestRoom(room_left, &two_of_2);
    CHECK(Packs_FixedCardsFit(0) && !Packs_NothingLeft(0, NULL, NULL));
    CHECK(one("{\"packs\": [{\"cards\": [1], \"slots\": [{\"card\": 2}, {\"card\": 2}, {\"card\": 2}]}]}") == 1);
    CHECK(!Packs_FixedCardsFit(0));
    Packs_SetChestRoom(NULL, NULL);
    CHECK(Packs_FixedCardsFit(0));
}

/* "when_nothing_left": a pack of "max_copies" whose every card the player
 * holds that many of is refused by default; "sell" sells it anyway. */
static void test_when_nothing_left(void)
{
    Held none = {{0}, {0}, 0}, all = {{1, 2}, {1, 1}, 2}, some = {{1}, {1}, 1}, over = {{1, 2}, {3, 1}, 2};
    CHECK(one("{\"packs\": [{\"cards\": [1, 2], \"max_copies\": 1}]}") == 1);
    CHECK(!Packs_NothingLeft(0, held_copies, &none) && !Packs_NothingLeft(0, held_copies, &some));
    CHECK(Packs_NothingLeft(0, held_copies, &all) && Packs_NothingLeft(0, held_copies, &over));
    CHECK(Packs_RefusesWhenNothingLeft(0));
    {   /* Nothing left: every slot of the deal is empty, and it still spends four numbers a slot. */
        Counting counting = {7, 0};
        PackResult result;
        int s;
        Packs_Deal(0, NULL, held_copies, &all, counting_random, &counting, &result);
        for (s = 0; s < result.count; s++) CHECK(result.cards[s] == 0);
        CHECK(counting.draws == PACK_DRAWS_PER_SLOT * 5);
    }
    /* Without "max_copies" there is always something left. */
    CHECK(one("{\"packs\": [{\"cards\": [1, 2]}]}") == 1 && !Packs_NothingLeft(0, held_copies, &all));
    /* A fixed card is dealt whatever the player holds. */
    CHECK(one("{\"packs\": [{\"cards\": [1, 2], \"slots\": [\"cards\", {\"card\": 1}], \"max_copies\": 1}]}") == 1);
    CHECK(!Packs_NothingLeft(0, held_copies, &all));
    /* A slot's own pool counts; a card of weight 0 does not. */
    CHECK(one("{\"packs\": [{\"cards\": {\"1\": 1, \"3\": 0}, \"slots\": [\"cards\", {\"cards\": [2]}], "
              "\"max_copies\": 1}]}") == 1);
    CHECK(Packs_NothingLeft(0, held_copies, &all) && !Packs_NothingLeft(0, held_copies, &some));
    /* The pack's word, the shop's, and the pack's over the shop's. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"max_copies\": 1, \"when_nothing_left\": \"sell\"}]}") == 1);
    CHECK(!Packs_RefusesWhenNothingLeft(0) && Packs_At(0)->when_nothing_left == PACK_NOTHING_SELL);
    fresh();
    add("test", "{\"packs\": [{\"id\": \"a\", \"cards\": [1]}, {\"id\": \"b\", \"cards\": [1], "
                "\"when_nothing_left\": \"refuse\"}], \"pack_shop\": {\"when_nothing_left\": \"sell\"}}");
    Packs_Finish();
    CHECK(!Packs_RefusesWhenNothingLeft(0) && Packs_RefusesWhenNothingLeft(1) && notes == 0);
    /* A shop's rules given again by a later mod start from "refuse". */
    add("later", "{\"pack_shop\": {\"rng\": \"save\"}}");
    CHECK(Packs_RefusesWhenNothingLeft(0));
    /* Written wrong: said, and the default kept. */
    CHECK(one("{\"packs\": [{\"cards\": [1], \"when_nothing_left\": \"give\"}], \"pack_shop\": "
              "{\"when_nothing_left\": 1}}") == 1);
    CHECK(noted("\"when_nothing_left\" is \"refuse\" or \"sell\"; the shop's is used") &&
          noted("\"when_nothing_left\" is \"refuse\" or \"sell\"; \"refuse\" is used"));
    CHECK(Packs_At(0)->when_nothing_left == PACK_NOTHING_SHOPS && Packs_RefusesWhenNothingLeft(0));
}

/* A fixed card is counted from the start: "unique_in_pack" never deals it
 * again before its slot, and "max_copies" counts it wherever it sits. */
static void test_fixed_cards_first(void)
{
    unsigned seed;
    CHECK(one("{\"packs\": [{\"cards\": [1, 2, 3, 4], \"slots\": [\"cards\", \"cards\", \"cards\", {\"card\": 2}], "
              "\"duplicates\": \"unique_in_pack\"}]}") == 1);
    for (seed = 0; seed < 300; seed++) {
        Counting counting = {seed * 2654435761u, 0};
        PackResult result;
        int a, b;
        Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
        CHECK(result.cards[3] == 2);
        for (a = 0; a < result.count; a++)
            for (b = a + 1; b < result.count; b++) CHECK(!result.cards[a] || result.cards[a] != result.cards[b]);
    }
    CHECK(one("{\"packs\": [{\"cards\": [1, 2], \"slots\": [\"cards\", \"cards\", {\"card\": 2}], "
              "\"max_copies\": 2}]}") == 1);
    for (seed = 0; seed < 300; seed++) {
        Counting counting = {seed * 2654435761u, 0};
        PackResult result;
        Held held = {{2}, {1}, 1};
        int s, twos = 0;
        Packs_Deal(0, NULL, held_copies, &held, counting_random, &counting, &result);
        for (s = 0; s < result.count; s++) twos += result.cards[s] == 2;
        CHECK(twos == 1 && result.cards[2] == 2);   /* one held and the fixed one make the two */
    }
}

static void test_order_and_shops(void)
{
    fresh();
    add("one", "{\"packs\": [{\"id\": \"a\", \"cards\": [1]}, {\"id\": \"b\", \"cards\": [1], \"order\": -5, "
               "\"shop\": \"black\"}], \"pack_shop\": {\"shops\": [{\"id\": \"main\", \"name\": \"Card Shop\"}]}}");
    add("two", "{\"packs\": [{\"id\": \"a\", \"cards\": [2], \"shop\": [\"main\", \"black\"]}], \"pack_shop\": {\"password\": "
               "\"packs_only\", \"rng\": \"save\", \"music\": 7, \"shops\": [{\"id\": \"black\", \"name\": \"Black Market\", "
               "\"unlock\": {\"beat\": \"Seto\"}}]}}");
    Packs_Finish();
    CHECK(Packs_Count() == 3);
    CHECK(!strcmp(Packs_At(0)->identity, "one:b"));   /* order -5 first */
    CHECK(!strcmp(Packs_At(1)->identity, "one:a"));
    CHECK(!strcmp(Packs_At(2)->identity, "two:a"));
    CHECK(Packs_Rules()->shop_count == 2);
    CHECK(Packs_Rules()->password == PACK_SHOP_PACKS_ONLY && Packs_Rules()->rng == PACK_RNG_SAVE && Packs_Rules()->music == 7);
    CHECK(!strcmp(Packs_Rules()->from, "two") && noted("this mod's, later in the load order, are used"));
    CHECK(Packs_At(0)->shops == 2u && Packs_At(1)->shops == 3u && Packs_At(2)->shops == 3u);
    CHECK(Packs_Rules()->shops[1].has_unlock && !strcmp(Packs_Rules()->shops[1].unlock.beat, "Seto"));
    CHECK(Packs_Find("two:a") == 2 && Packs_Find("b") == 0 && Packs_Find("nothing") == -1);
}

/* --- the dealer ----------------------------------------------------------------- */

/* Always four numbers a slot, whatever the pack does with them. */
static void test_draw_count(void)
{
    const char *fixtures[] = {
        "{\"packs\": [{\"cards\": [1, 2, 3]}]}",
        "{\"packs\": [{\"count\": 9, \"tiers\": {\"c\": {\"odds\": 99, \"cards\": [1, 2]}, \"u\": {\"odds\": 1, \"cards\": [3]}}, "
        "\"guarantee\": {\"u\": 3}, \"pity\": {\"u\": 1}}]}",
        "{\"packs\": [{\"count\": 4, \"cards\": [1, 2, 3, 4], \"duplicates\": \"unique_in_pack\"}]}",
        "{\"packs\": [{\"count\": 6, \"cards\": [1, 2], \"max_copies\": 1}]}",
        "{\"packs\": [{\"tiers\": {\"c\": {\"cards\": [1]}, \"e\": {\"cards\": []}}, \"slots\": [\"e\", {\"card\": 2}, "
        "{\"cards\": [3]}, {\"tiers\": {\"c\": 1, \"e\": 1}}]}]}",
    };
    unsigned f, seed;
    for (f = 0; f < sizeof(fixtures) / sizeof(fixtures[0]); f++) {
        PacksProgress progress;
        CHECK(one(fixtures[f]) == 1);
        memset(&progress, 0, sizeof(progress));
        progress.packs[0].pity[1] = 5;
        for (seed = 0; seed < 200; seed++) {
            Counting counting = {seed * 2654435761u, 0};
            PackResult result;
            Held held = {{1, 3}, {1, 0}, 2};
            CHECK(Packs_Deal(0, &progress, held_copies, &held, counting_random, &counting, &result) == Packs_At(0)->count);
            CHECK(counting.draws == PACK_DRAWS_PER_SLOT * Packs_At(0)->count);
        }
    }
}

static void test_rules_while_dealing(void)
{
    PacksProgress progress;
    PackResult result;
    unsigned seed;
    int s, i, redone = 0;
    memset(&progress, 0, sizeof(progress));

    /* The guarantee: at least two of "u" (or rarer) in every pack. */
    CHECK(one("{\"packs\": [{\"count\": 5, \"tiers\": {\"c\": {\"odds\": 1000, \"cards\": [1, 2]}, \"r\": {\"odds\": 0, "
              "\"cards\": [3]}, \"u\": {\"odds\": 0, \"cards\": [4]}}, \"guarantee\": {\"r\": 2}}]}") == 1);
    for (seed = 1; seed < 100; seed++) {
        Counting counting = {seed, 0};
        int rare = 0;
        Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
        for (s = 0; s < 5; s++) rare += result.tiers[s] >= 1;
        CHECK(rare == 2);
        /* The last slots are the ones dealt again. */
        CHECK(result.redone[4] && result.redone[3] && !result.redone[0]);
        CHECK(result.cards[4] == 3 && result.cards[3] == 3);
    }

    /* The pity: the third pack in a row without "u" has one; then it resets. */
    CHECK(one("{\"packs\": [{\"count\": 2, \"tiers\": {\"c\": {\"odds\": 1, \"cards\": [1]}, \"u\": {\"odds\": 0, \"cards\": [9]}}, "
              "\"pity\": {\"u\": 3}}]}") == 1);
    for (i = 0; i < 7; i++) {
        Counting counting = {(unsigned)i, 0};
        int got = 0;
        Packs_Deal(0, &progress, NULL, NULL, counting_random, &counting, &result);
        for (s = 0; s < 2; s++) got |= result.cards[s] == 9;
        CHECK(got == (i % 3 == 2));
        Packs_Record(0, &result, 10, &progress);
        CHECK(progress.packs[0].pity[1] == (unsigned)(got ? 0 : i % 3 + 1));
    }
    CHECK(progress.packs[0].opened == 7 && progress.packs[0].bought == 7);
    CHECK(progress.packs_opened == 7 && progress.starchips_spent == 70);

    /* unique_in_pack: never twice in one pack. */
    CHECK(one("{\"packs\": [{\"count\": 4, \"cards\": {\"1\": 100, \"2\": 1, \"3\": 1, \"4\": 1}, \"duplicates\": "
              "\"unique_in_pack\"}]}") == 1);
    for (seed = 1; seed < 200; seed++) {
        Counting counting = {seed, 0};
        int seen[5] = {0};
        Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
        for (s = 0; s < 4; s++) CHECK(result.cards[s] >= 1 && result.cards[s] <= 4 && !seen[result.cards[s]]++);
    }
    /* ...nor when a full pack of different cards is dealt again for a
     * guarantee: forty dealt, forty more taken in their place. */
    {
        char text[1024];
        int n = snprintf(text, sizeof(text), "{\"packs\": [{\"count\": 40, \"duplicates\": \"unique_in_pack\", \"tiers\": "
                                             "{\"c\": {\"odds\": 1, \"cards\": [");
        for (i = 0; i < 40; i++) n += snprintf(text + n, sizeof(text) - (size_t)n, "%s%d", i ? "," : "", i + 1);
        n += snprintf(text + n, sizeof(text) - (size_t)n, "]}, \"r\": {\"odds\": 0, \"cards\": [");
        for (i = 0; i < 40; i++) n += snprintf(text + n, sizeof(text) - (size_t)n, "%s%d", i ? "," : "", i + 101);
        snprintf(text + n, sizeof(text) - (size_t)n, "]}}, \"guarantee\": {\"r\": 40}}]}");
        CHECK(one(text) == 1);
        for (seed = 1; seed < 50; seed++) {
            Counting counting = {seed, 0};
            int seen[141] = {0};
            Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
            for (s = 0; s < 40; s++) CHECK(result.cards[s] >= 101 && result.cards[s] <= 140 && !seen[result.cards[s]]++);
        }
    }

    /* max_copies: a card held twice is not dealt; one held once, once more at most. */
    CHECK(one("{\"packs\": [{\"count\": 6, \"cards\": {\"1\": 5, \"2\": 5, \"3\": 1}, \"max_copies\": 2}]}") == 1);
    for (seed = 1; seed < 200; seed++) {
        Counting counting = {seed, 0};
        Held held = {{1, 2}, {2, 1}, 2};
        int twos = 0;
        Packs_Deal(0, NULL, held_copies, &held, counting_random, &counting, &result);
        for (s = 0; s < 6; s++) {
            CHECK(result.cards[s] != 1);
            twos += result.cards[s] == 2;
        }
        CHECK(twos <= 1);
    }

    /* An empty tier falls to the one before it; with none left, nothing. */
    CHECK(one("{\"packs\": [{\"count\": 3, \"tiers\": {\"c\": {\"odds\": 1, \"cards\": [1]}, \"r\": {\"odds\": 1, "
              "\"cards\": [2]}}, \"slots\": [\"r\", \"r\", \"r\"], \"max_copies\": 1}]}") == 1);
    {
        Counting counting = {5, 0};
        Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
        CHECK(result.cards[0] == 2 && result.tiers[0] == 1);
        CHECK(result.cards[1] == 1 && result.tiers[1] == 0);
        CHECK(result.cards[2] == 0 && result.tiers[2] == -1);
    }

    /* A fixed slot and a slot's own pool are not dealt again for a guarantee. */
    CHECK(one("{\"packs\": [{\"tiers\": {\"c\": {\"odds\": 1, \"cards\": [1]}, \"u\": {\"odds\": 0, \"cards\": [9]}}, "
              "\"slots\": [\"c\", {\"card\": 5}, {\"cards\": [6]}], \"guarantee\": {\"u\": 1}}]}") == 1);
    for (seed = 1; seed < 20; seed++) {
        Counting counting = {seed, 0};
        Packs_Deal(0, NULL, NULL, NULL, counting_random, &counting, &result);
        CHECK(result.cards[0] == 9 && result.cards[1] == 5 && result.cards[2] == 6);
        CHECK(result.tiers[1] == -1 && result.tiers[2] == -1);
        redone += result.redone[0];
    }
    CHECK(redone == 19);
}

static int save_says_yes(const PackUnlock *unlock, void *context)
{
    (void)unlock;
    return *(int *)context;
}

static void test_unlock_and_stock(void)
{
    PacksProgress progress;
    int yes = 1, no = 0;
    fresh();
    add("test", "{\"packs\": [{\"id\": \"first\", \"cards\": [1], \"stock\": 2}, {\"id\": \"second\", \"cards\": [2], "
                "\"unlock\": {\"opened\": {\"first\": 2}, \"starchips_spent\": 100, \"packs_opened\": 2}, \"locked\": "
                "\"shown\"}, {\"id\": \"third\", \"cards\": [3], \"unlock\": {\"beat\": \"Heishin\", \"wins\": 2}}, "
                "{\"id\": \"fourth\", \"cards\": [4], \"unlock\": {\"opened\": {\"nothing\": 1}}}, "
                "{\"id\": \"fifth\", \"cards\": [5], \"unlock\": {\"wins\": \"many\"}}]}");
    Packs_Finish();
    CHECK(Packs_Count() == 5 && noted("names no pack \"nothing\"") && noted("stays locked"));
    memset(&progress, 0, sizeof(progress));
    CHECK(Packs_Unlocked(0, &progress, NULL, NULL));
    CHECK(!Packs_Unlocked(1, &progress, NULL, NULL));
    CHECK(Packs_At(1)->locked_shown && !Packs_At(0)->locked_shown);
    CHECK(Packs_StockLeft(0, &progress) == 2 && Packs_StockLeft(1, &progress) == -1);
    progress.packs[0].opened = progress.packs[0].bought = 2;
    progress.packs_opened = 2;
    progress.starchips_spent = 99;
    CHECK(Packs_StockLeft(0, &progress) == 0);
    CHECK(!Packs_Unlocked(1, &progress, NULL, NULL));
    progress.starchips_spent = 100;
    CHECK(Packs_Unlocked(1, &progress, NULL, NULL));
    /* The save's own conditions are the save's to answer. */
    CHECK(!Packs_Unlocked(2, &progress, NULL, NULL));
    CHECK(!Packs_Unlocked(2, &progress, save_says_yes, &no));
    CHECK(Packs_Unlocked(2, &progress, save_says_yes, &yes));
    CHECK(!strcmp(Packs_At(2)->unlock.beat, "Heishin") && Packs_At(2)->unlock.wins == 2);
    /* A pack that is not here, or a condition written wrong: locked for good. */
    CHECK(!Packs_Unlocked(3, &progress, save_says_yes, &yes));
    CHECK(!Packs_Unlocked(4, &progress, save_says_yes, &yes));
}

/* tmpfile() makes its file in the drive's root on Windows, which a CI runner
 * may not write to; a file in a scratch folder works everywhere. */
static FILE *scratch_file(void)
{
    static char directory[SCRATCH_MAX];
    static int files;
    char path[SCRATCH_MAX + 32];
    if (!*directory && !scratch_dir(directory, sizeof(directory), "memories-packs")) return NULL;
    snprintf(path, sizeof(path), "%s/progress%d.txt", directory, files++);
    return fopen(path, "w+b");
}

static void test_progress_file(void)
{
    PacksProgress progress, again;
    FILE *file;
    char text[2048];
    size_t length;
    fresh();
    add("test", "{\"packs\": [{\"id\": \"a\", \"tiers\": {\"c\": {\"cards\": [1]}, \"u\": {\"cards\": [2]}, \"x\": {\"cards\": [3]}},"
                "\"pity\": {\"u\": 5, \"x\": 9}}, {\"id\": \"b\", \"cards\": [2], \"password\": \"1\", \"once\": true}]}");
    Packs_Finish();
    memset(&progress, 0, sizeof(progress));
    progress.starchips_spent = 1250;
    progress.packs_opened = 12;
    progress.packs[0].bought = progress.packs[0].opened = 11;
    progress.packs[0].pity[1] = 3;
    progress.packs[0].pity[2] = 7;
    progress.packs[1].bought = progress.packs[1].opened = 1;
    progress.packs[1].used = 1;
    file = scratch_file();
    CHECK(file != NULL);
    /* A line of a pack another run had is kept, and written back. */
    fputs("spent 1\nopened 1\npack gone:old bought 4 opened 4 used 0\n", file);
    rewind(file);
    Packs_ReadProgress(file, &again);
    CHECK(again.starchips_spent == 1 && again.packs_opened == 1);
    CHECK(foreign && strstr(foreign, "gone:old"));
    fclose(file);
    file = scratch_file();
    Packs_WriteProgress(file, &progress);
    rewind(file);
    length = fread(text, 1, sizeof(text) - 1, file);
    text[length] = 0;
    CHECK(strstr(text, "pack test:a bought 11 opened 11 used 0 pity u=3 x=7\n"));
    CHECK(strstr(text, "pack test:b bought 1 opened 1 used 1\n"));
    CHECK(strstr(text, "pack gone:old bought 4"));
    rewind(file);
    Packs_ReadProgress(file, &again);
    fclose(file);
    CHECK(!memcmp(&again, &progress, sizeof(progress)));
    CHECK(!Packs_ProgressEmpty(&again));
    Packs_ForgetProgress(&again);
    CHECK(again.packs_opened == 0 && !foreign);
    CHECK(Packs_ProgressEmpty(&again));
    /* The save's seed: the same for the same save, pack and count. */
    CHECK(Packs_SaveSeed(0x12345678, "test:a", 3) == Packs_SaveSeed(0x12345678, "test:a", 3));
    CHECK(Packs_SaveSeed(0x12345678, "test:a", 3) != Packs_SaveSeed(0x12345678, "test:a", 4));
    CHECK(Packs_SaveSeed(0x12345678, "test:a", 3) != Packs_SaveSeed(0x12345679, "test:a", 3));
}

static void test_file_and_signature(void)
{
    unsigned inline_signature;
    CHECK(one("{\"packs\": [{\"cards\": [1]}]}") == 1);
    inline_signature = Packs_Signature();
    /* "packs": a file of the mod's, with rules of its own. */
    if (one("{\"packs\": \"packs_fixture.json\"}") != 10) fprintf(stderr, "%d packs, notes:\n%s", Packs_Count(), all_notes);
    CHECK(Packs_Count() == 10);
    CHECK(Packs_Signature() != inline_signature);
    CHECK(one("{\"packs\": \"missing.json\"}") == 0 && noted("missing.json"));
    CHECK(one("{\"packs\": \"../escape.json\"}") == 0 && noted("not a file inside the mod"));
}

/* --- golden deals, for the editor's Simulate -------------------------------- */

static void golden(void)
{
    char path[512], error[256], expected[65536], line[512];
    JsonDocument *fixture;
    const JsonValue *cases, *entry;
    FILE *file;
    size_t length = 0;
    int writing = getenv("PACKS_GOLDEN_WRITE") && !strcmp(getenv("PACKS_GOLDEN_WRITE"), "1"), lines = 0;
    char *out = calloc(1, 65536);
    CHECK(out != NULL);
    snprintf(path, sizeof(path), "%s/packs_fixture.json", PACKS_TEST_DIR);
    fixture = Json_ParseFile(path, error, sizeof(error));
    if (!fixture) fprintf(stderr, "%s: %s\n", path, error);
    CHECK(fixture != NULL);
    fresh();
    Packs_Add("golden", PACKS_TEST_DIR, Json_Root(fixture));
    Packs_Finish();
    CHECK(notes == 0);
    cases = Json_Member(Json_Root(fixture), "cases");
    for (entry = Json_At(cases, 0); entry; entry = Json_Next(entry)) {
        int pack = Packs_Find(Json_String(Json_Member(entry, "pack"), ""));
        const JsonValue *seed, *member;
        PacksProgress progress;
        Held held;
        CHECK(pack >= 0);
        memset(&progress, 0, sizeof(progress));
        memset(&held, 0, sizeof(held));
        for (member = Json_At(Json_Member(entry, "pity"), 0); member; member = Json_Next(member))
            progress.packs[pack].pity[tier_named(Packs_At(pack), Json_Name(member))] = (unsigned short)Json_Number(member, 0);
        for (member = Json_At(Json_Member(entry, "held"), 0); member; member = Json_Next(member)) {
            held.cards[held.count] = atoi(Json_Name(member));
            held.copies[held.count++] = (int)Json_Number(member, 0);
        }
        for (seed = Json_At(Json_Member(entry, "seeds"), 0); seed; seed = Json_Next(seed)) {
            Counting counting = {(unsigned)Json_Number(seed, 0), 0};
            PackResult result;
            int s, used = 0;
            Packs_Deal(pack, &progress, held_copies, &held, counting_random, &counting, &result);
            used = snprintf(line, sizeof(line), "%s %u", Packs_At(pack)->id, (unsigned)Json_Number(seed, 0));
            for (s = 0; s < result.count; s++)
                used += snprintf(line + used, sizeof(line) - (size_t)used, " %u/%d%s", result.cards[s], result.tiers[s],
                                 result.redone[s] ? "*" : "");
            length += (size_t)snprintf(out + length, 65536 - length, "%s | seed %08X%s\n", line, counting.seed,
                                       Packs_NothingLeft(pack, held_copies, &held) ? " | nothing left" : "");
            lines++;
        }
    }
    snprintf(path, sizeof(path), "%s/packs_golden.txt", PACKS_TEST_DIR);
    if (writing) {
        file = fopen(path, "wb");
        CHECK(file != NULL);
        fputs(out, file);
        fclose(file);
        printf("packs: wrote %d golden deals to %s\n", lines, path);
    } else {
        file = fopen(path, "rb");
        CHECK(file != NULL);
        length = fread(expected, 1, sizeof(expected) - 1, file);
        expected[length] = 0;
        fclose(file);
        {   /* A checkout may have given the file CRLF line ends. */
            size_t from, to = 0;
            for (from = 0; from < length; from++) if (expected[from] != 13) expected[to++] = expected[from];
            expected[to] = 0;
        }
        if (strcmp(expected, out)) {
            fprintf(stderr, "packs: the deals differ from %s; this build deals:\n%s", path, out);
            exit(1);
        }
    }
    free(out);
    Json_Free(fixture);
}

int main(void)
{
    test_minimal();
    test_errors();
    test_warnings();
    test_order_and_shops();
    test_draw_count();
    test_rules_while_dealing();
    test_when_nothing_left();
    test_chest_room();
    test_fixed_cards_first();
    test_unlock_and_stock();
    test_progress_file();
    test_file_and_signature();
    golden();
    Packs_Clear();
    while (document_count) Json_Free(documents[--document_count]);
    printf("packs: ok\n");
    return 0;
}
