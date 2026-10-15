/* Card packs: the mods' "packs" and "pack_shop", checked, and the dealer
 * (packs.h, notes/card-packs.md).
 *
 * Every key has a default, so a pack can be three lines of JSON; what a key
 * gets wrong is said in the Mods window (Mods_Note). A mistake that leaves a
 * pack unable to be dealt leaves the pack out; anything else is dropped or
 * cut and the pack stays. */
#include "packs.h"
#include "cards.h"
#include "pc/mods/mods.h"
#include "pc/mods/json.h"
#include "pc/platform/paths.h"
#include "pc/compat/fs.h"
#include "pc/debug/log.h"
#include "game/card_constants.h"
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static Pack *packs;
static int pack_count, pack_room, declared;
static PackShopRules rules;
static unsigned signature;

/* Lines of the progress file for packs not here this run, written back. */
static char *foreign;
static size_t foreign_size;

#define DEFAULT_MUSIC 29520   /* the Password screen's own (Password_InitShopScreen) */
static const int default_sounds[PACK_SOUNDS] = {47, 48, 9, 12, 8};

/* --- small helpers ------------------------------------------------------- */

/* Cut at `size` - 1 bytes, as snprintf would (which gcc 16 warns of). */
static void copy_text(char *out, size_t size, const char *text)
{
    size_t length = text ? strlen(text) : 0;
    if (!size) return;
    if (length >= size) length = size - 1;
    if (length) memcpy(out, text, length);
    out[length] = 0;
}

/* UTF-8 text into `size` bytes, cut before a letter that would not fit
 * whole rather than inside it. 1 when it was cut. */
static int copy_utf8(char *out, size_t size, const char *text)
{
    size_t length, keep;
    if (!text) text = "";
    length = keep = strlen(text);
    if (keep >= size) {
        keep = size - 1;
        while (keep && ((unsigned char)text[keep] & 0xC0) == 0x80) keep--;
    }
    memcpy(out, text, keep);
    out[keep] = '\0';
    return keep < length;
}

/* An "id", a tier's or a shop's name: 1-63 letters, digits, '_' or '-'. */
static int key_valid(const char *text)
{
    size_t length = text ? strlen(text) : 0;
    return length && length < PACK_KEY_MAX &&
           strspn(text, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") == length;
}

/* The id a pack with no "id" gets from its name: lower case, a hyphen for
 * anything else, runs of them one. */
static void slug(char *out, size_t size, const char *name)
{
    size_t n = 0;
    int hyphen = 0;
    for (; *name && n + 1 < size; name++) {
        unsigned char c = (unsigned char)*name;
        if (isalnum(c) && c < 0x80) {
            if (hyphen && n) out[n++] = '-';
            if (n + 1 < size) out[n++] = (char)tolower(c);
            hyphen = 0;
        } else {
            hyphen = 1;
        }
    }
    out[n] = '\0';
    if (!n) copy_text(out, size, "pack");
}

/* Characters of UTF-8 text, and the bytes of its first `letters`. */
static size_t utf8_letters(const char *text, size_t *bytes_of, size_t letters)
{
    size_t count = 0, i;
    for (i = 0; text[i]; i++) {
        if (((unsigned char)text[i] & 0xC0) != 0x80) {
            if (count == letters && bytes_of) *bytes_of = i;
            count++;
        }
    }
    if (count <= letters && bytes_of) *bytes_of = i;
    return count;
}

/* How many letters to add, remove or change to turn one word into the
 * other, for "did you mean" (the same measure mods.c uses for the
 * manifest's keys). */
static int distance(const char *a, const char *b)
{
    int row[33], i, j, length_a = (int)strlen(a), length_b = (int)strlen(b);
    if (length_a > 32 || length_b > 32) return 99;
    for (j = 0; j <= length_b; j++) row[j] = j;
    for (i = 1; i <= length_a; i++) {
        int diagonal = row[0];
        row[0] = i;
        for (j = 1; j <= length_b; j++) {
            int above = row[j], best = diagonal + (tolower((unsigned char)a[i - 1]) != tolower((unsigned char)b[j - 1]));
            if (above + 1 < best) best = above + 1;
            if (row[j - 1] + 1 < best) best = row[j - 1] + 1;
            diagonal = above;
            row[j] = best;
        }
    }
    return row[length_b];
}

/* Keys of an object that are none of `known`: a note each, with the
 * likeliest meant. `reserved` are keys of the design not built yet. */
static void check_keys(const char *mod, const char *where, const JsonValue *object, const char *const *known,
                       const char *const *reserved)
{
    const JsonValue *member;
    /* An array's items have no names: only an object has keys to check. */
    if (Json_TypeOf(object) != JSON_OBJECT) return;
    for (member = Json_At(object, 0); member; member = Json_Next(member)) {
        const char *name = Json_Name(member), *closest = NULL;
        int best = 3, i, found = 0;
        for (i = 0; known[i]; i++) {
            int apart;
            if (!strcmp(name, known[i])) { found = 1; break; }
            apart = distance(name, known[i]);
            if (apart < best) { best = apart; closest = known[i]; }
        }
        if (found) continue;
        for (i = 0; reserved && reserved[i]; i++) {
            if (!strcmp(name, reserved[i])) break;
        }
        if (reserved && reserved[i]) {
            Mods_Note(mod, "%s: \"%s\" is not built yet (notes/card-packs.md); ignored", where, name);
        } else if (closest) {
            Mods_Note(mod, "%s: unknown key \"%s\" (did you mean \"%s\"?)", where, name, closest);
        } else {
            Mods_Note(mod, "%s: unknown key \"%s\"", where, name);
        }
    }
}

static unsigned hash_bytes(unsigned hash, const void *data, size_t size)
{
    const unsigned char *bytes = data;
    size_t i;
    for (i = 0; i < size; i++) hash = (hash ^ bytes[i]) * 16777619u;
    return hash;
}

/* A file's bytes into the signature: a state saved with other packs or
 * other pictures is not this run's. 0 when it cannot be read. */
static int sign_file(const char *path)
{
    unsigned char buffer[4096];
    size_t got;
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    signature = hash_bytes(signature ? signature : 2166136261u, path, strlen(path));
    while ((got = fread(buffer, 1, sizeof(buffer), file)) > 0) signature = hash_bytes(signature, buffer, got);
    fclose(file);
    return 1;
}

/* A whole number in [low, high], or the fallback when left out; -1 in *bad
 * when given and not one. */
static long number_in(const JsonValue *value, long low, long high, long fallback, int *bad)
{
    long number;
    if (!value) return fallback;
    number = Json_Number(value, low - 1);
    if (Json_TypeOf(value) != JSON_NUMBER || number < low || number > high) {
        *bad = 1;
        return fallback;
    }
    return number;
}

/* "12345678" (or a number): up to eight digits, four bits each. */
static int read_password(const JsonValue *value, unsigned *out)
{
    char digits[16];
    const char *text;
    size_t length, i;
    if (Json_TypeOf(value) == JSON_NUMBER && Json_Number(value, -1) >= 0 && Json_Number(value, -1) <= 99999999) {
        snprintf(digits, sizeof(digits), "%08ld", Json_Number(value, 0));
        text = digits;
    } else {
        text = Json_String(value, NULL);
    }
    length = text ? strlen(text) : 0;
    if (!length || length > 8 || strspn(text, "0123456789") != length) return 0;
    *out = 0;
    for (i = 0; i < 8; i++) {
        /* Shorter than eight: the digits the player types end it, as a
         * card's password is right-aligned with leading zeros. */
        int digit = i < 8 - length ? 0 : text[i - (8 - length)] - '0';
        *out = (*out << 4) | (unsigned)digit;
    }
    return 1;
}

/* --- pools ---------------------------------------------------------------- */

static int pool_add(PackPool *pool, int card, unsigned weight)
{
    PackEntry *bigger = realloc(pool->entries, (size_t)(pool->count + 1) * sizeof(*bigger));
    if (!bigger) return 0;
    pool->entries = bigger;
    pool->entries[pool->count].card = (unsigned short)card;
    pool->entries[pool->count].weight = weight;
    pool->count++;
    return 1;
}

static void pool_free(PackPool *pool)
{
    free(pool->entries);
    pool->entries = NULL;
    pool->count = 0;
}

static unsigned pool_total(const PackPool *pool)
{
    unsigned total = 0;
    int i;
    for (i = 0; i < pool->count; i++) total += pool->entries[i].weight;
    return total;
}

/* A card a pool names: 0 and a note for none, and for a mod's card when the
 * pack takes only the disc's. */
static int pool_card(const char *mod, const char *where, const JsonValue *name_value, const char *name,
                     int include_added)
{
    int id;
    if (name_value) {
        id = Cards_Reference(name_value);
    } else {
        id = Cards_Named(name);
    }
    if (id <= 0) {
        char shown[96];
        if (name) copy_text(shown, sizeof(shown), name);
        else if (Json_TypeOf(name_value) == JSON_NUMBER) snprintf(shown, sizeof(shown), "%ld", Json_Number(name_value, 0));
        else copy_text(shown, sizeof(shown), Json_String(name_value, "?"));
        Mods_Note(mod, "%s: no card \"%s\"; left out", where, shown);
        return 0;
    }
    if (!include_added && id > CARD_COUNT) {
        Mods_Note(mod, "%s: card %d is a mod's, and \"include_added_cards\" is false; left out", where, id);
        return 0;
    }
    return id;
}

/* "cards": a list (a weight of 1 each) or {card: weight}. 1 when the pool
 * is sound (it may still be empty), 0 on an error that leaves the pack out. */
static int read_pool(const char *mod, const char *where, const JsonValue *value, int include_added, PackPool *pool)
{
    const JsonValue *item;
    char at[160];
    int i;
    if (Json_TypeOf(value) == JSON_ARRAY) {
        for (i = 0, item = Json_At(value, 0); item; item = Json_Next(item), i++) {
            int id;
            snprintf(at, sizeof(at), "%s[%d]", where, i);
            id = pool_card(mod, at, item, NULL, include_added);
            if (id > 0 && !pool_add(pool, id, 1)) return 0;
        }
    } else if (Json_TypeOf(value) == JSON_OBJECT) {
        for (item = Json_At(value, 0); item; item = Json_Next(item)) {
            const char *name = Json_Name(item);
            long weight = Json_Number(item, -1);
            int id;
            snprintf(at, sizeof(at), "%s \"%s\"", where, name);
            if (Json_TypeOf(item) != JSON_NUMBER || weight < 0 || weight > PACK_WEIGHT_TOTAL_MAX) {
                Mods_Note(mod, "%s: a weight is a whole number, 0 to %d; the pack is left out", at,
                          PACK_WEIGHT_TOTAL_MAX);
                return 0;
            }
            id = pool_card(mod, at, NULL, name, include_added);
            if (id > 0 && weight > 0 && !pool_add(pool, id, (unsigned)weight)) return 0;
        }
    } else {
        Mods_Note(mod, "%s: a pool is a list of cards, or an object of cards and their weights; the pack is left out",
                  where);
        return 0;
    }
    if (pool_total(pool) > PACK_WEIGHT_TOTAL_MAX) {
        Mods_Note(mod, "%s: the weights add up to %u, more than %d; the pack is left out", where, pool_total(pool),
                  PACK_WEIGHT_TOTAL_MAX);
        return 0;
    }
    return 1;
}

/* --- unlock ----------------------------------------------------------- */

static const char *const unlock_keys[] = {"beat", "wins", "story", "card", "copies", "starchips_spent", "opened",
                                          "packs_opened", NULL};

/* 1 when there is at least one condition. A value of the wrong kind is a
 * note, and the condition is kept unmeetable, so nothing opens by mistake. */
static int read_unlock(const char *mod, const char *where, const JsonValue *value, PackUnlock *unlock)
{
    const JsonValue *opened, *item;
    char at[160];
    int bad = 0, any = 0;
    memset(unlock, 0, sizeof(*unlock));
    unlock->story = -1;
    if (!value) return 0;
    snprintf(at, sizeof(at), "%s unlock", where);
    if (Json_TypeOf(value) != JSON_OBJECT) {
        Mods_Note(mod, "%s: \"unlock\" is an object of conditions; the pack stays locked", where);
        unlock->never = 1;
        return 1;
    }
    check_keys(mod, at, value, unlock_keys, NULL);
    if (Json_Member(value, "beat")) {
        if (Json_TypeOf(Json_Member(value, "beat")) == JSON_NUMBER)
            snprintf(unlock->beat, sizeof(unlock->beat), "%ld", Json_Number(Json_Member(value, "beat"), 0));
        else copy_utf8(unlock->beat, sizeof(unlock->beat), Json_String(Json_Member(value, "beat"), "?"));
        any = 1;
    }
    if (Json_Member(value, "card")) {
        if (Json_TypeOf(Json_Member(value, "card")) == JSON_NUMBER)
            snprintf(unlock->card, sizeof(unlock->card), "%ld", Json_Number(Json_Member(value, "card"), 0));
        else copy_utf8(unlock->card, sizeof(unlock->card), Json_String(Json_Member(value, "card"), "?"));
        any = 1;
    }
    unlock->wins = (int)number_in(Json_Member(value, "wins"), 0, 65535, 0, &bad);
    unlock->copies = (int)number_in(Json_Member(value, "copies"), 0, 250, 0, &bad);
    unlock->story = (int)number_in(Json_Member(value, "story"), 0, 0xFFFF, -1, &bad);
    unlock->starchips_spent = (unsigned)number_in(Json_Member(value, "starchips_spent"), 0, 999999999, 0, &bad);
    unlock->packs_opened = (unsigned)number_in(Json_Member(value, "packs_opened"), 0, 999999999, 0, &bad);
    any |= unlock->wins > 0 || unlock->story >= 0 || unlock->starchips_spent || unlock->packs_opened;
    opened = Json_Member(value, "opened");
    if (opened && Json_TypeOf(opened) != JSON_OBJECT) bad = 1;
    for (item = Json_TypeOf(opened) == JSON_OBJECT ? Json_At(opened, 0) : NULL; item; item = Json_Next(item)) {
        long times = Json_Number(item, -1);
        if (unlock->opened_count >= PACK_OPENED_MAX) {
            Mods_Note(mod, "%s: \"opened\" names more than %d packs; the rest are left out", at, PACK_OPENED_MAX);
            break;
        }
        if (Json_TypeOf(item) != JSON_NUMBER || times < 1) { bad = 1; continue; }
        copy_utf8(unlock->opened_name[unlock->opened_count], PACK_IDENTITY_MAX, Json_Name(item));
        unlock->opened_pack[unlock->opened_count] = -1;
        unlock->opened_times[unlock->opened_count++] = (unsigned)times;
        any = 1;
    }
    if (bad) {
        Mods_Note(mod, "%s: a condition is not a whole number in range; the pack stays locked", at);
        unlock->never = 1;
        return 1;
    }
    if (!any) Mods_Note(mod, "%s: names no condition, so it is open from the start", at);
    return any;
}

/* --- a pack ----------------------------------------------------------------- */

static const char *const pack_keys[] = {
    "id", "name", "description", "image", "image_style", "cover", "shop", "order", "price", "cost", "count", "cards",
    "tiers", "slots", "guarantee", "pity", "duplicates", "max_copies", "include_added_cards", "stock", "unlock", "locked",
    "password", "once", "listed", "reveal", "sounds", "when_nothing_left", NULL};
static const char *const pack_reserved[] = {"restock", NULL};
static const char *const tier_keys[] = {"odds", "cards", "label", "color", "sound", "reveal", NULL};
static const char *const cost_keys[] = {"starchips", "cards", NULL};
static const char *const cost_reserved[] = {"currency", NULL};
static const char *const sound_keys[] = {"move", "buy", "refuse", "reveal", "back", NULL};
static const char *const slot_keys[] = {"tiers", "cards", "card", NULL};

static int reveal_named(const char *text)
{
    if (!text) return -2;
    if (!strcmp(text, "flip")) return PACK_REVEAL_FLIP;
    if (!strcmp(text, "quick")) return PACK_REVEAL_QUICK;
    if (!strcmp(text, "list")) return PACK_REVEAL_LIST;
    return -2;
}

static int nothing_left_named(const char *text)
{
    if (!strcmp(text, "refuse")) return PACK_NOTHING_REFUSE;
    if (!strcmp(text, "sell")) return PACK_NOTHING_SELL;
    return PACK_NOTHING_SHOPS;
}

static int tier_named(const Pack *pack, const char *name)
{
    int t;
    for (t = 0; t < pack->tier_count; t++) {
        if (!strcmp(pack->tiers[t].name, name)) return t;
    }
    return -1;
}

static void free_pack(Pack *pack)
{
    int t;
    for (t = 0; t < pack->tier_count; t++) pool_free(&pack->tiers[t].pool);
    if (pack->slots) {
        for (t = 0; t < pack->count; t++) pool_free(&pack->slots[t].pool);
        free(pack->slots);
        pack->slots = NULL;
    }
}

/* A tier: {"odds": n, "cards": pool, "label", "color", "sound", "reveal"}. */
static int read_tier(const char *mod, const char *where, const char *name, const JsonValue *value, Pack *pack)
{
    PackTier *tier = &pack->tiers[pack->tier_count];
    char at[160];
    int bad = 0;
    snprintf(at, sizeof(at), "%s tier \"%s\"", where, name);
    if (!key_valid(name)) {
        Mods_Note(mod, "%s: a tier's name is 1-63 letters, digits, '_' or '-'; the pack is left out", at);
        return 0;
    }
    if (tier_named(pack, name) >= 0) {
        Mods_Note(mod, "%s: named twice; the pack is left out", at);
        return 0;
    }
    if (pack->tier_count >= PACK_TIERS_MAX) {
        Mods_Note(mod, "%s: a pack has at most %d tiers; the pack is left out", at, PACK_TIERS_MAX);
        return 0;
    }
    memset(tier, 0, sizeof(*tier));
    copy_text(tier->name, sizeof(tier->name), name);
    tier->color = tier->sound = tier->reveal = -1;
    if (Json_TypeOf(value) != JSON_OBJECT) {
        Mods_Note(mod, "%s: a tier is an object with \"odds\" and \"cards\"; the pack is left out", at);
        return 0;
    }
    check_keys(mod, at, value, tier_keys, NULL);
    tier->odds = (unsigned)number_in(Json_Member(value, "odds"), 0, PACK_WEIGHT_TOTAL_MAX, 1, &bad);
    tier->color = (int)number_in(Json_Member(value, "color"), 0, 15, -1, &bad);
    tier->sound = (int)number_in(Json_Member(value, "sound"), 0, 0xFFFF, -1, &bad);
    if (bad) {
        Mods_Note(mod, "%s: \"odds\" is 0 to %d, \"color\" 0 to 15 and \"sound\" a sound id; the pack is left out", at,
                  PACK_WEIGHT_TOTAL_MAX);
        return 0;
    }
    copy_utf8(tier->label, sizeof(tier->label), Json_String(Json_Member(value, "label"), ""));
    if (Json_Member(value, "reveal")) {
        tier->reveal = reveal_named(Json_String(Json_Member(value, "reveal"), NULL));
        if (tier->reveal < 0) {
            Mods_Note(mod, "%s: \"reveal\" is \"flip\", \"quick\" or \"list\"; the pack's is used", at);
            tier->reveal = -1;
        }
    }
    pack->tier_count++;   /* before the pool, so free_pack frees it */
    if (!Json_Member(value, "cards")) {
        Mods_Note(mod, "%s: no \"cards\"", at);
        return 1;
    }
    snprintf(at, sizeof(at), "%s tier \"%s\" cards", where, name);
    return read_pool(mod, at, Json_Member(value, "cards"), pack->include_added, &tier->pool);
}

/* One slot of "slots": a tier's name, {"tiers": {tier: weight}},
 * {"cards": pool} or {"card": X}. */
static int read_slot(const char *mod, const char *where, const JsonValue *value, Pack *pack, PackSlot *slot)
{
    const JsonValue *item;
    memset(slot, 0, sizeof(*slot));
    if (Json_TypeOf(value) == JSON_STRING) {
        slot->kind = PACK_SLOT_TIER;
        slot->tier = tier_named(pack, Json_String(value, ""));
        if (slot->tier < 0) {
            Mods_Note(mod, "%s: no tier \"%s\"; the pack is left out", where, Json_String(value, ""));
            return 0;
        }
        return 1;
    }
    if (Json_TypeOf(value) != JSON_OBJECT || Json_Count(value) != 1) {
        Mods_Note(mod, "%s: a slot is a tier's name, {\"tiers\": {...}}, {\"cards\": ...} or {\"card\": ...}; the pack is "
                       "left out", where);
        return 0;
    }
    check_keys(mod, where, value, slot_keys, NULL);
    if ((item = Json_Member(value, "card")) != NULL) {
        slot->kind = PACK_SLOT_CARD;
        slot->card = pool_card(mod, where, item, NULL, pack->include_added);
        if (slot->card <= 0) {
            Mods_Note(mod, "%s: its card is not here; the pack is left out", where);
            return 0;
        }
        return 1;
    }
    if ((item = Json_Member(value, "cards")) != NULL) {
        slot->kind = PACK_SLOT_POOL;
        return read_pool(mod, where, item, pack->include_added, &slot->pool);
    }
    if ((item = Json_Member(value, "tiers")) != NULL && Json_TypeOf(item) == JSON_OBJECT) {
        const JsonValue *member;
        unsigned total = 0;
        slot->kind = PACK_SLOT_MIX;
        for (member = Json_At(item, 0); member; member = Json_Next(member)) {
            int t = tier_named(pack, Json_Name(member));
            long weight = Json_Number(member, -1);
            if (t < 0) {
                Mods_Note(mod, "%s: no tier \"%s\"; the pack is left out", where, Json_Name(member));
                return 0;
            }
            if (Json_TypeOf(member) != JSON_NUMBER || weight < 0 || weight > PACK_WEIGHT_TOTAL_MAX) {
                Mods_Note(mod, "%s: a tier's weight is 0 to %d; the pack is left out", where, PACK_WEIGHT_TOTAL_MAX);
                return 0;
            }
            slot->mix[t] = (unsigned)weight;
            total += (unsigned)weight;
        }
        if (!total || total > PACK_WEIGHT_TOTAL_MAX) {
            Mods_Note(mod, "%s: the tiers' weights add up to %u; 1 to %d; the pack is left out", where, total,
                      PACK_WEIGHT_TOTAL_MAX);
            return 0;
        }
        return 1;
    }
    Mods_Note(mod, "%s: a slot is a tier's name, {\"tiers\": {...}}, {\"cards\": ...} or {\"card\": ...}; the pack is left "
                   "out", where);
    return 0;
}

/* {tier: n} for "guarantee" and "pity". */
static int read_tier_counts(const char *mod, const char *where, const char *key, const JsonValue *value,
                            const Pack *pack, int *counts)
{
    const JsonValue *member;
    if (!value) return 1;
    if (Json_TypeOf(value) != JSON_OBJECT) {
        Mods_Note(mod, "%s: \"%s\" is {tier: n}; the pack is left out", where, key);
        return 0;
    }
    for (member = Json_At(value, 0); member; member = Json_Next(member)) {
        int t = tier_named(pack, Json_Name(member));
        long n = Json_Number(member, 0);
        if (t < 0 || Json_TypeOf(member) != JSON_NUMBER || n < 1 || n > 65535) {
            Mods_Note(mod, "%s: \"%s\": \"%s\" is not a tier of the pack with n of 1 or more; the pack is left out",
                      where, key, Json_Name(member));
            return 0;
        }
        counts[t] = (int)n;
    }
    return 1;
}

/* The distinct cards a pack can deal, for "unique_in_pack". */
static int distinct_cards(const Pack *pack)
{
    int seen_count = 0, t, i, s, k;
    int *seen = NULL;
    const PackPool *pools[PACK_TIERS_MAX + PACK_COUNT_MAX];
    int pool_count = 0;
    for (t = 0; t < pack->tier_count; t++) pools[pool_count++] = &pack->tiers[t].pool;
    for (s = 0; pack->slots && s < pack->count; s++) {
        if (pack->slots[s].kind == PACK_SLOT_POOL) pools[pool_count++] = &pack->slots[s].pool;
    }
    /* A fixed card is one of them too. */
    for (s = 0; pack->slots && s < pack->count; s++) {
        int card = pack->slots[s].card, j, found = 0;
        if (pack->slots[s].kind != PACK_SLOT_CARD) continue;
        for (j = 0; j < seen_count; j++) found |= seen[j] == card;
        if (!found) {
            int *bigger = realloc(seen, (size_t)(seen_count + 1) * sizeof(*seen));
            if (!bigger) break;
            seen = bigger;
            seen[seen_count++] = card;
        }
    }
    for (i = 0; i < pool_count; i++) {
        for (k = 0; k < pools[i]->count; k++) {
            int card = pools[i]->entries[k].card, j, found = 0;
            if (!pools[i]->entries[k].weight) continue;
            for (j = 0; j < seen_count; j++) found |= seen[j] == card;
            if (!found) {
                int *bigger = realloc(seen, (size_t)(seen_count + 1) * sizeof(*seen));
                if (!bigger) break;
                seen = bigger;
                seen[seen_count++] = card;
            }
        }
    }
    free(seen);
    return seen_count;
}

static Pack *new_pack(void)
{
    if (pack_count >= pack_room) {
        int wanted = pack_room ? pack_room * 2 : 16;
        Pack *bigger = realloc(packs, (size_t)wanted * sizeof(*bigger));
        if (!bigger) return NULL;
        packs = bigger;
        pack_room = wanted;
    }
    memset(&packs[pack_count], 0, sizeof(packs[pack_count]));
    return &packs[pack_count];
}

/* The pack's "shop": its names, kept as written until every mod's shops
 * are in (Packs_Finish). */
static char shop_names[PACKS_MAX][PACK_DESCRIPTION_MAX];

static void read_pack(const char *mod, const char *directory, int index, const JsonValue *entry)
{
    Pack *pack;
    const JsonValue *value, *tiers, *cards, *slots;
    char where[PACK_KEY_MAX + 32], id[PACK_KEY_MAX];
    int bad = 0, i, t;
    long price;

    snprintf(where, sizeof(where), "packs[%d]", index);
    if (Json_TypeOf(entry) != JSON_OBJECT) {
        Mods_Note(mod, "%s: a pack is an object", where);
        return;
    }
    if (pack_count >= PACKS_MAX) {
        Mods_Note(mod, "%s: there are %d packs already, the most there can be; left out", where, PACKS_MAX);
        return;
    }
    check_keys(mod, where, entry, pack_keys, pack_reserved);
    pack = new_pack();
    if (!pack) return;
    copy_text(pack->mod, sizeof(pack->mod), mod);

    /* The id, then everything is said of the pack by it. */
    value = Json_Member(entry, "id");
    if (value) {
        /* Checked whole: a longer one is not cut to fit. */
        if (!key_valid(Json_String(value, ""))) {
            Mods_Note(mod, "%s: \"id\" is 1-63 letters, digits, '_' or '-'; the pack is left out", where);
            return;
        }
        copy_text(id, sizeof(id), Json_String(value, ""));
    } else {
        slug(id, sizeof(id), Json_String(Json_Member(entry, "name"), "pack"));
    }
    for (i = 0; i < pack_count; i++) {
        if (!strcmp(packs[i].mod, mod) && !strcmp(packs[i].id, id)) {
            Mods_Note(mod, "%s: the id \"%s\" is another pack's of this mod; the pack is left out", where, id);
            return;
        }
    }
    copy_text(pack->id, sizeof(pack->id), id);
    snprintf(pack->identity, sizeof(pack->identity), "%s:%s", mod, id);
    snprintf(where, sizeof(where), "pack \"%s\"", id);

    copy_utf8(pack->name, sizeof(pack->name), Json_String(Json_Member(entry, "name"), id));
    {
        size_t keep = 0;
        if (utf8_letters(pack->name, &keep, PACK_NAME_LETTERS) > PACK_NAME_LETTERS) {
            Mods_Note(mod, "%s: the name has room for %d letters; cut there", where, PACK_NAME_LETTERS);
            pack->name[keep] = '\0';
        }
    }
    if (copy_utf8(pack->description, sizeof(pack->description), Json_String(Json_Member(entry, "description"), "")))
        Mods_Note(mod, "%s: the description has room for %d bytes of UTF-8; cut there", where, PACK_DESCRIPTION_MAX - 1);
    pack->declared = declared++;
    pack->order = pack->declared;
    if ((value = Json_Member(entry, "order")) != NULL) {
        int wrong = 0;
        pack->order = number_in(value, -1000000, 1000000, pack->order, &wrong);
        if (wrong) Mods_Note(mod, "%s: \"order\" is a whole number; the pack keeps its place", where);
    }

    /* What it costs. */
    price = number_in(Json_Member(entry, "price"), 0, PACK_PRICE_MAX, PACK_DEFAULT_PRICE, &bad);
    if ((value = Json_Member(entry, "cost")) != NULL) {
        const JsonValue *member;
        if (Json_TypeOf(value) != JSON_OBJECT) {
            Mods_Note(mod, "%s: \"cost\" is {\"starchips\": n, \"cards\": {card: copies}}; the pack is left out", where);
            return;
        }
        check_keys(mod, where, value, cost_keys, cost_reserved);
        if (Json_Member(value, "starchips")) {
            long starchips = number_in(Json_Member(value, "starchips"), 0, PACK_PRICE_MAX, price, &bad);
            if (Json_Member(entry, "price") && starchips != price)
                Mods_Note(mod, "%s: \"price\" and \"cost\" differ; \"cost\" is used", where);
            price = starchips;
        }
        member = Json_Member(value, "cards");
        if (member && Json_TypeOf(member) != JSON_OBJECT) {
            Mods_Note(mod, "%s: \"cost\" \"cards\" is {card: copies}; the pack is left out", where);
            return;
        }
        for (member = Json_At(member, 0); member; member = Json_Next(member)) {
            long copies = Json_Number(member, 0);
            int card = pool_card(mod, where, NULL, Json_Name(member), 1);
            if (Json_TypeOf(member) != JSON_NUMBER || copies < 1 || copies > 250) {
                Mods_Note(mod, "%s: \"cost\" takes 1 to 250 copies of a card; the pack is left out", where);
                return;
            }
            if (card <= 0) {
                Mods_Note(mod, "%s: a card \"cost\" names is not here; the pack is left out", where);
                return;
            }
            if (pack->cost_cards >= PACK_COST_CARDS_MAX) {
                Mods_Note(mod, "%s: \"cost\" names at most %d cards; the pack is left out", where, PACK_COST_CARDS_MAX);
                return;
            }
            pack->cost_card[pack->cost_cards] = (unsigned short)card;
            pack->cost_copies[pack->cost_cards++] = (unsigned char)copies;
        }
    }
    if (bad) {
        Mods_Note(mod, "%s: \"price\" (and \"cost\" \"starchips\") is 0 to %d starchips; the pack is left out", where,
                  PACK_PRICE_MAX);
        return;
    }
    pack->price = (unsigned)price;

    /* What it deals. */
    pack->include_added = Json_Bool(Json_Member(entry, "include_added_cards"), 1);
    if ((value = Json_Member(entry, "duplicates")) != NULL) {
        const char *text = Json_String(value, "");
        if (!strcmp(text, "unique_in_pack")) pack->unique = 1;
        else if (strcmp(text, "allow")) Mods_Note(mod, "%s: \"duplicates\" is \"allow\" or \"unique_in_pack\"; allowed", where);
    }
    pack->max_copies = (int)number_in(Json_Member(entry, "max_copies"), 1, 250, 0, &bad);
    tiers = Json_Member(entry, "tiers");
    cards = Json_Member(entry, "cards");
    slots = Json_Member(entry, "slots");
    if (tiers && cards) {
        Mods_Note(mod, "%s: \"cards\" is a pack of one tier and \"tiers\" is several; give one; the pack is left out", where);
        return;
    }
    if (cards) {
        PackTier *tier = &pack->tiers[pack->tier_count++];
        memset(tier, 0, sizeof(*tier));
        copy_text(tier->name, sizeof(tier->name), "cards");
        tier->odds = 1;
        tier->color = tier->sound = tier->reveal = -1;
        snprintf(where + strlen(where), sizeof(where) - strlen(where), " cards");
        if (!read_pool(mod, where, cards, pack->include_added, &tier->pool)) { free_pack(pack); return; }
        snprintf(where, sizeof(where), "pack \"%s\"", id);
    } else if (Json_TypeOf(tiers) == JSON_OBJECT) {
        const JsonValue *member;
        for (member = Json_At(tiers, 0); member; member = Json_Next(member)) {
            if (!read_tier(mod, where, Json_Name(member), member, pack)) { free_pack(pack); return; }
        }
    } else {
        Mods_Note(mod, "%s: no \"cards\" or \"tiers\" to deal from; the pack is left out", where);
        return;
    }
    {
        int dealt = 0;
        for (t = 0; t < pack->tier_count; t++) dealt |= pack->tiers[t].pool.count > 0;
        if (!dealt && !slots) {
            Mods_Note(mod, "%s: none of its cards are here; the pack is left out", where);
            free_pack(pack);
            return;
        }
    }
    pack->count = (int)number_in(Json_Member(entry, "count"), 1, PACK_COUNT_MAX,
                                 Json_TypeOf(slots) == JSON_ARRAY ? Json_Count(slots) : PACK_DEFAULT_COUNT, &bad);
    if (bad || pack->count < 1 || pack->count > PACK_COUNT_MAX) {   /* "slots" of more, and no "count" */
        Mods_Note(mod, "%s: \"count\" is 1 to %d cards and \"max_copies\" 1 to 250; the pack is left out", where,
                  PACK_COUNT_MAX);
        free_pack(pack);
        return;
    }
    if (slots) {
        if (Json_TypeOf(slots) != JSON_ARRAY || Json_Count(slots) != pack->count) {
            Mods_Note(mod, "%s: \"slots\" is a list of %d, one a card; the pack is left out", where, pack->count);
            free_pack(pack);
            return;
        }
        pack->slots = calloc((size_t)pack->count, sizeof(*pack->slots));
        if (!pack->slots) return;
        for (i = 0, value = Json_At(slots, 0); value; value = Json_Next(value), i++) {
            char at[PACK_KEY_MAX + 48];
            snprintf(at, sizeof(at), "%s slot %d", where, i + 1);
            if (!read_slot(mod, at, value, pack, &pack->slots[i])) { free_pack(pack); return; }
        }
        {   /* A slot with nothing to deal from is a pack that cannot be dealt whole. */
            int dealt = 0;
            for (i = 0; i < pack->count; i++) {
                const PackSlot *slot = &pack->slots[i];
                dealt |= slot->kind == PACK_SLOT_CARD || (slot->kind == PACK_SLOT_POOL && slot->pool.count);
                if (slot->kind == PACK_SLOT_TIER || slot->kind == PACK_SLOT_MIX) {
                    for (t = 0; t < pack->tier_count; t++) dealt |= pack->tiers[t].pool.count > 0;
                }
            }
            if (!dealt) {
                Mods_Note(mod, "%s: none of its cards are here; the pack is left out", where);
                free_pack(pack);
                return;
            }
        }
    }
    if (!read_tier_counts(mod, where, "guarantee", Json_Member(entry, "guarantee"), pack, pack->guarantee) ||
        !read_tier_counts(mod, where, "pity", Json_Member(entry, "pity"), pack, pack->pity)) {
        free_pack(pack);
        return;
    }
    for (i = 0; pack->unique && pack->slots && i < pack->count; i++) {
        int k;
        if (pack->slots[i].kind != PACK_SLOT_CARD) continue;
        for (k = i + 1; k < pack->count; k++) {
            if (pack->slots[k].kind == PACK_SLOT_CARD && pack->slots[k].card == pack->slots[i].card) {
                Mods_Note(mod, "%s: \"unique_in_pack\" and card %d fixed in slots %d and %d; the pack is left out",
                          where, pack->slots[i].card, i + 1, k + 1);
                free_pack(pack);
                return;
            }
        }
    }
    if (pack->unique && distinct_cards(pack) < pack->count) {
        Mods_Note(mod, "%s: \"unique_in_pack\" deals %d different cards and the pack has %d to deal from; the pack is "
                       "left out", where, pack->count, distinct_cards(pack));
        free_pack(pack);
        return;
    }
    {
        unsigned odds = 0;
        for (t = 0; t < pack->tier_count; t++) odds += pack->tiers[t].odds;
        if (odds > PACK_WEIGHT_TOTAL_MAX) {
            Mods_Note(mod, "%s: the tiers' odds add up to %u, more than %d; the pack is left out", where, odds,
                      PACK_WEIGHT_TOTAL_MAX);
            free_pack(pack);
            return;
        }
        if (!odds) {
            int needs = !pack->slots;
            for (i = 0; pack->slots && i < pack->count; i++) needs |= pack->slots[i].kind == PACK_SLOT_ODDS;
            if (needs) {
                Mods_Note(mod, "%s: every tier's \"odds\" is 0, so a slot by the odds has no tier to deal from; the "
                               "pack is left out", where);
                free_pack(pack);
                return;
            }
        }
    }

    /* How it looks and sounds. */
    if ((value = Json_Member(entry, "image")) != NULL) {
        const char *image = Json_String(value, "");
        if (!*image || !Paths_Contained(image)) {
            Mods_Note(mod, "%s: \"image\" is a PNG inside the mod; its cover is shown instead", where);
        } else if (snprintf(pack->image, sizeof(pack->image), "%s/%s", directory ? directory : ".", image) >=
                   (int)sizeof(pack->image) || !sign_file(pack->image)) {
            Mods_Note(mod, "%s: \"image\" %s cannot be read; its cover is shown instead", where, image);
            pack->image[0] = '\0';
        }
    }
    pack->image_style = PACK_IMAGE_CARD;
    if ((value = Json_Member(entry, "image_style")) != NULL) {
        const char *style = Json_String(value, "");
        if (!strcmp(style, "full")) pack->image_style = PACK_IMAGE_FULL;
        else if (strcmp(style, "card"))
            Mods_Note(mod, "%s: \"image_style\" is \"card\" or \"full\"; \"card\" is used", where);
        if (pack->image_style == PACK_IMAGE_FULL && !Json_Member(entry, "image"))
            Mods_Note(mod, "%s: \"image_style\" \"full\" shows the \"image\", and there is none; its cover is shown", where);
    }
    pack->cover = 0;
    if ((value = Json_Member(entry, "cover")) != NULL) {
        pack->cover = pool_card(mod, where, value, NULL, 1);
        if (pack->cover < 0) pack->cover = 0;
    }
    if (!pack->cover) {   /* the first card of the highest tier that has one */
        for (t = pack->tier_count - 1; t >= 0 && !pack->cover; t--) {
            if (pack->tiers[t].pool.count) pack->cover = pack->tiers[t].pool.entries[0].card;
        }
        for (i = 0; pack->slots && i < pack->count && !pack->cover; i++) {
            if (pack->slots[i].kind == PACK_SLOT_CARD) pack->cover = pack->slots[i].card;
            if (pack->slots[i].kind == PACK_SLOT_POOL && pack->slots[i].pool.count)
                pack->cover = pack->slots[i].pool.entries[0].card;
        }
    }
    pack->reveal = PACK_REVEAL_FLIP;
    if ((value = Json_Member(entry, "reveal")) != NULL) {
        pack->reveal = reveal_named(Json_String(value, NULL));
        if (pack->reveal < 0) {
            Mods_Note(mod, "%s: \"reveal\" is \"flip\", \"quick\" or \"list\"; \"flip\" is used", where);
            pack->reveal = PACK_REVEAL_FLIP;
        }
    }
    memcpy(pack->sounds, default_sounds, sizeof(pack->sounds));
    if ((value = Json_Member(entry, "sounds")) != NULL && Json_TypeOf(value) != JSON_OBJECT) {
        Mods_Note(mod, "%s: \"sounds\" is {\"move\": id, ...}; the screen's own are used", where);
    } else if (value) {
        check_keys(mod, where, value, sound_keys, NULL);
        for (i = 0; i < PACK_SOUNDS; i++) {
            int wrong = 0;
            pack->sounds[i] = (int)number_in(Json_Member(value, sound_keys[i]), 0, 0xFFFF, default_sounds[i], &wrong);
            if (wrong) Mods_Note(mod, "%s: \"sounds\" \"%s\" is a sound effect id; the screen's own is used", where,
                                 sound_keys[i]);
        }
    }

    pack->when_nothing_left = PACK_NOTHING_SHOPS;
    if ((value = Json_Member(entry, "when_nothing_left")) != NULL) {
        pack->when_nothing_left = nothing_left_named(Json_String(value, ""));
        if (pack->when_nothing_left == PACK_NOTHING_SHOPS)
            Mods_Note(mod, "%s: \"when_nothing_left\" is \"refuse\" or \"sell\"; the shop's is used", where);
    }

    /* Where and when it is sold. */
    pack->stock = (int)number_in(Json_Member(entry, "stock"), 1, 999999, -1, &bad);
    if (bad) {
        Mods_Note(mod, "%s: \"stock\" is 1 to 999999 purchases; no limit is kept", where);
        pack->stock = -1;
        bad = 0;
    }
    pack->has_unlock = read_unlock(mod, where, Json_Member(entry, "unlock"), &pack->unlock);
    if ((value = Json_Member(entry, "locked")) != NULL) {
        const char *text = Json_String(value, "");
        if (!strcmp(text, "shown")) pack->locked_shown = 1;
        else if (strcmp(text, "hidden")) Mods_Note(mod, "%s: \"locked\" is \"hidden\" or \"shown\"; hidden", where);
    }
    if ((value = Json_Member(entry, "password")) != NULL) {
        pack->has_password = read_password(value, &pack->password);
        if (!pack->has_password) Mods_Note(mod, "%s: \"password\" is up to 8 digits; the pack has none", where);
    }
    pack->once = Json_Bool(Json_Member(entry, "once"), 0);
    pack->listed = Json_Bool(Json_Member(entry, "listed"), !pack->has_password);
    shop_names[pack_count][0] = '\0';
    if ((value = Json_Member(entry, "shop")) != NULL) {
        char *names = shop_names[pack_count];
        const JsonValue *item;
        if (Json_TypeOf(value) == JSON_STRING) {
            copy_text(names, PACK_DESCRIPTION_MAX, Json_String(value, ""));
        } else if (Json_TypeOf(value) == JSON_ARRAY) {
            for (item = Json_At(value, 0); item; item = Json_Next(item)) {
                size_t used = strlen(names);
                snprintf(names + used, PACK_DESCRIPTION_MAX - used, "%s%s", used ? "," : "", Json_String(item, ""));
            }
        } else {
            Mods_Note(mod, "%s: \"shop\" is a shop's id, or a list of them; the pack is in every shop", where);
        }
        if (!strcmp(names, "*")) names[0] = '\0';
    }
    pack_count++;
}

/* --- the shop's rules ------------------------------------------------------ */

static const char *const rules_keys[] = {"password", "shops", "rng", "music", "when_nothing_left", "campaign_shop",
                                         "main_menu", "sell_added_cards", "autosave", NULL};
static const char *const rules_reserved[] = {"currency", "earn", NULL};
static const char *const shop_keys[] = {"id", "name", "unlock", "where", NULL};

static int rules_ready;

static void default_rules(void)
{
    rules_ready = 1;
    memset(&rules, 0, sizeof(rules));
    rules.password = PACK_SHOP_BOTH;
    rules.rng = PACK_RNG_GAME;
    rules.music = DEFAULT_MUSIC;
    rules.when_nothing_left = PACK_NOTHING_REFUSE;
}

static void read_rules(const char *mod, const JsonValue *value)
{
    const JsonValue *item;
    int bad = 0, i;
    const char *text;
    if (!value) return;
    if (Json_TypeOf(value) != JSON_OBJECT) {
        Mods_Note(mod, "\"pack_shop\" is an object of the shop's rules; left out");
        return;
    }
    check_keys(mod, "pack_shop", value, rules_keys, rules_reserved);
    if (rules.from[0]) {
        Mods_Note(mod, "pack_shop: %s gave the shop's rules too; this mod's, later in the load order, are used",
                  rules.from);
    }
    copy_text(rules.from, sizeof(rules.from), mod);
    rules.password = PACK_SHOP_BOTH;
    rules.rng = PACK_RNG_GAME;
    rules.music = DEFAULT_MUSIC;
    rules.when_nothing_left = PACK_NOTHING_REFUSE;
    if ((item = Json_Member(value, "password")) != NULL) {
        text = Json_String(item, "");
        if (!strcmp(text, "packs_only")) rules.password = PACK_SHOP_PACKS_ONLY;
        else if (!strcmp(text, "password_only")) rules.password = PACK_SHOP_PASSWORD_ONLY;
        else if (strcmp(text, "both"))
            Mods_Note(mod, "pack_shop: \"password\" is \"both\", \"packs_only\" or \"password_only\"; \"both\" is used");
    }
    if ((item = Json_Member(value, "rng")) != NULL) {
        text = Json_String(item, "");
        if (!strcmp(text, "save")) rules.rng = PACK_RNG_SAVE;
        else if (strcmp(text, "game")) Mods_Note(mod, "pack_shop: \"rng\" is \"game\" or \"save\"; \"game\" is used");
    }
    if ((item = Json_Member(value, "when_nothing_left")) != NULL) {
        int named = nothing_left_named(Json_String(item, ""));
        if (named == PACK_NOTHING_SHOPS)
            Mods_Note(mod, "pack_shop: \"when_nothing_left\" is \"refuse\" or \"sell\"; \"refuse\" is used");
        else rules.when_nothing_left = named;
    }
    rules.music = (int)number_in(Json_Member(value, "music"), 0, 0xFFFF, DEFAULT_MUSIC, &bad);
    if (bad) Mods_Note(mod, "pack_shop: \"music\" is a song id; the screen's own is used");
    /* What the design has and this build does not do yet: said, not done. */
    {
        static const char *const later[] = {"campaign_shop", "main_menu", "sell_added_cards", "autosave"};
        for (i = 0; i < 4; i++) {
            if (Json_Bool(Json_Member(value, later[i]), 0))
                Mods_Note(mod, "pack_shop: \"%s\" is not built yet (notes/card-packs.md); ignored", later[i]);
        }
    }
    item = Json_Member(value, "shops");
    if (item && Json_TypeOf(item) != JSON_ARRAY) Mods_Note(mod, "pack_shop: \"shops\" is a list of shops; left out");
    for (item = Json_TypeOf(item) == JSON_ARRAY ? Json_At(item, 0) : NULL; item; item = Json_Next(item)) {
        const char *id = Json_String(Json_Member(item, "id"), "");
        char where[PACK_KEY_MAX + 32];
        PackShop *shop = NULL;
        if (Json_TypeOf(item) != JSON_OBJECT || !key_valid(id)) {
            Mods_Note(mod, "pack_shop: a shop is {\"id\": ..., \"name\": ...}, its id 1-63 letters, digits, '_' or '-'; "
                           "left out");
            continue;
        }
        snprintf(where, sizeof(where), "pack_shop shop \"%s\"", id);
        check_keys(mod, where, item, shop_keys, NULL);
        if (Json_Member(item, "where") && strcmp(Json_String(Json_Member(item, "where"), ""), "password"))
            Mods_Note(mod, "%s: only \"where\": \"password\" is built yet; it is on the Password screen", where);
        for (i = 0; i < rules.shop_count; i++) {
            if (!strcmp(rules.shops[i].id, id)) shop = &rules.shops[i];
        }
        if (!shop) {
            if (rules.shop_count >= PACK_SHOPS_MAX) {
                Mods_Note(mod, "%s: there are %d shops already, the most there can be; left out", where, PACK_SHOPS_MAX);
                continue;
            }
            shop = &rules.shops[rules.shop_count++];
            memset(shop, 0, sizeof(*shop));
            copy_text(shop->id, sizeof(shop->id), id);
        }
        copy_utf8(shop->name, sizeof(shop->name), Json_String(Json_Member(item, "name"), id));
        shop->has_unlock = read_unlock(mod, where, Json_Member(item, "unlock"), &shop->unlock);
    }
}

/* --- reading every mod ------------------------------------------------------ */

void Packs_Add(const char *mod, const char *directory, const JsonValue *manifest)
{
    const JsonValue *list = Json_Member(manifest, "packs"), *item;
    JsonDocument *file = NULL;
    int i;
    if (!rules_ready) default_rules();
    if (Json_TypeOf(list) == JSON_STRING) {
        /* "packs": "packs.json": a file of the mod, a list of packs or
         * {"packs": [...], "pack_shop": {...}}. */
        const char *name = Json_String(list, "");
        char path[PACK_PATH_MAX], error[160];
        list = NULL;
        if (!*name || !Paths_Contained(name) ||
            snprintf(path, sizeof(path), "%s/%s", directory ? directory : ".", name) >= (int)sizeof(path)) {
            Mods_Note(mod, "\"packs\": %s is not a file inside the mod", name);
        } else if (!(file = Json_ParseFile(path, error, sizeof(error)))) {
            Mods_Note(mod, "\"packs\": %s: %s", name, error);
        } else {
            const JsonValue *root = Json_Root(file);
            sign_file(path);
            if (Json_TypeOf(root) == JSON_OBJECT) {
                list = Json_Member(root, "packs");
                read_rules(mod, Json_Member(root, "pack_shop"));
            } else {
                list = root;
            }
        }
    }
    if (list && Json_TypeOf(list) != JSON_ARRAY) {
        Mods_Note(mod, "\"packs\" is a list of packs, or the name of a file that holds them");
        list = NULL;
    }
    for (i = 0, item = Json_At(list, 0); item; item = Json_Next(item), i++) read_pack(mod, directory, i, item);
    read_rules(mod, Json_Member(manifest, "pack_shop"));
    Json_Free(file);
}

static int by_order(const void *left, const void *right)
{
    const Pack *a = left, *b = right;
    if (a->order != b->order) return a->order < b->order ? -1 : 1;
    return a->declared - b->declared;
}

void Packs_Finish(void)
{
    int i, k, j;
    /* The shops a pack names, now that every mod's are in; a pack that names
     * no shop there is shows in all of them. */
    if (!rules.shop_count) {
        memset(&rules.shops[0], 0, sizeof(rules.shops[0]));
        copy_text(rules.shops[0].id, sizeof(rules.shops[0].id), "main");
        copy_text(rules.shops[0].name, sizeof(rules.shops[0].name), "CARD SHOP");
        rules.shop_count = 1;
    }
    for (i = 0; i < pack_count; i++) {
        char names[PACK_DESCRIPTION_MAX], *name, *next;
        packs[i].shops = 0;
        copy_text(names, sizeof(names), shop_names[i]);
        for (name = names; *name; name = next) {
            int found = 0;
            next = strchr(name, ',');
            if (next) *next++ = '\0';
            else next = name + strlen(name);
            if (!*name) continue;   /* an empty name, or one that is not a string */
            for (k = 0; k < rules.shop_count; k++) {
                if (!strcmp(rules.shops[k].id, name)) { packs[i].shops |= 1u << k; found = 1; }
            }
            if (!found) Mods_Note(packs[i].mod, "pack \"%s\": no shop \"%s\"", packs[i].id, name);
        }
        if (!packs[i].shops) packs[i].shops = (1u << rules.shop_count) - 1u;
    }
    if (pack_count > 1) qsort(packs, (size_t)pack_count, sizeof(*packs), by_order);
    /* "opened" names packs; resolved by the list's order now fixed. */
    for (i = 0; i < pack_count; i++) {
        PackUnlock *unlock = &packs[i].unlock;
        for (k = 0; k < unlock->opened_count; k++) {
            unlock->opened_pack[k] = Packs_Find(unlock->opened_name[k]);
            if (unlock->opened_pack[k] < 0)
                Mods_Note(packs[i].mod, "pack \"%s\": \"unlock\" \"opened\" names no pack \"%s\"; it stays locked",
                          packs[i].id, unlock->opened_name[k]);
        }
    }
    for (k = 0; k < rules.shop_count; k++) {
        PackUnlock *unlock = &rules.shops[k].unlock;
        for (j = 0; j < unlock->opened_count; j++) unlock->opened_pack[j] = Packs_Find(unlock->opened_name[j]);
    }
    /* Two packs with one password: the first in the list is the one sold. */
    for (i = 0; i < pack_count; i++) {
        for (k = 0; k < i && packs[i].has_password; k++) {
            if (packs[k].has_password && packs[k].password == packs[i].password)
                Mods_Note(packs[i].mod, "pack \"%s\": its password is pack \"%s\"'s too; that one is sold", packs[i].id,
                          packs[k].identity);
        }
    }
    if (pack_count) {
        signature = hash_bytes(signature ? signature : 2166136261u, "packs", 5);
        LOG(LOG_MODS, "packs: %d pack%s in %d shop%s%s", pack_count, pack_count == 1 ? "" : "s", rules.shop_count,
            rules.shop_count == 1 ? "" : "s", rules.from[0] ? "" : " (the default rules)");
    } else {
        signature = 0;
    }
}

void Packs_Clear(void)
{
    int i;
    for (i = 0; i < pack_count; i++) free_pack(&packs[i]);
    free(packs);
    packs = NULL;
    pack_count = pack_room = declared = 0;
    signature = 0;
    default_rules();
    memset(shop_names, 0, sizeof(shop_names));
    free(foreign);
    foreign = NULL;
    foreign_size = 0;
}

void Packs_Build(void)
{
    static int built;
    int i;
    if (built) return;
    built = 1;
    default_rules();
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        if (Mods_Active(mod)) Packs_Add(Mods_Id(mod), Mods_Directory(mod), Mods_Manifest(mod));
    }
    Packs_Finish();
}

int Packs_Count(void) { return pack_count; }
const Pack *Packs_At(int index) { return index >= 0 && index < pack_count ? &packs[index] : NULL; }
const PackShopRules *Packs_Rules(void)
{
    if (!rules_ready) default_rules();
    return &rules;
}
unsigned Packs_Signature(void) { return signature; }

int Packs_Find(const char *name)
{
    int i;
    if (!name || !*name) return -1;
    for (i = 0; i < pack_count; i++) if (!strcmp(packs[i].identity, name)) return i;
    for (i = 0; i < pack_count; i++) if (!strcmp(packs[i].id, name)) return i;
    for (i = 0; i < pack_count; i++) if (!strcmp(packs[i].name, name)) return i;
    return -1;
}

int Packs_WithPassword(unsigned password)
{
    int i;
    for (i = 0; i < pack_count; i++) if (packs[i].has_password && packs[i].password == password) return i;
    return -1;
}

/* --- dealing ---------------------------------------------------------------- */

typedef struct {
    const Pack *pack;
    PackHeld held;
    void *held_context;
    int taken_count;
    /* The cards the slots dealt, and one more for each slot redone for a
     * guarantee or the pity (a slot is redone once at most). */
    unsigned short taken_card[2 * PACK_COUNT_MAX];
    unsigned char taken_times[2 * PACK_COUNT_MAX];
} Dealing;

static PackHeld chest_room;
static void *chest_room_context;

void Packs_SetChestRoom(PackHeld room, void *context)
{
    chest_room = room;
    chest_room_context = context;
}

static int taken(const Dealing *d, int card)
{
    int i;
    for (i = 0; i < d->taken_count; i++) if (d->taken_card[i] == card) return d->taken_times[i];
    return 0;
}

static void take(Dealing *d, int card, int step)
{
    int i;
    if (card <= 0) return;
    for (i = 0; i < d->taken_count; i++) {
        if (d->taken_card[i] == card) {
            d->taken_times[i] = (unsigned char)(d->taken_times[i] + step);
            return;
        }
    }
    if (step > 0 && d->taken_count < 2 * PACK_COUNT_MAX) {
        d->taken_card[d->taken_count] = (unsigned short)card;
        d->taken_times[d->taken_count++] = (unsigned char)step;
    }
}

/* A card's weight in a pool now: 0 once "unique_in_pack" dealt it, once
 * the player holds "max_copies" of it with what this pack dealt, or once the
 * chest has no room for another (Packs_SetChestRoom). */
static unsigned weight_now(const Dealing *d, const PackEntry *entry)
{
    int card = entry->card;
    if (!entry->weight) return 0;
    if (d->pack->unique && taken(d, card)) return 0;
    if (d->pack->max_copies) {
        int held = d->held ? d->held(card, d->held_context) : 0;
        if (held + taken(d, card) >= d->pack->max_copies) return 0;
    }
    if (chest_room && taken(d, card) >= chest_room(card, chest_room_context)) return 0;
    return entry->weight;
}

/* The card `roll` picks from a pool as it stands; 0 when it has none. */
static int pick(const Dealing *d, const PackPool *pool, unsigned roll)
{
    unsigned total = 0;
    int i;
    for (i = 0; i < pool->count; i++) total += weight_now(d, &pool->entries[i]);
    if (!total) return 0;
    roll %= total;
    for (i = 0; i < pool->count; i++) {
        unsigned weight = weight_now(d, &pool->entries[i]);
        if (!weight) continue;
        if (roll < weight) return pool->entries[i].card;
        roll -= weight;
    }
    return 0;
}

/* A tier by weights (the tiers' odds, or a slot's mix); -1 for none. */
static int pick_tier(const unsigned *weights, int count, unsigned roll)
{
    unsigned total = 0;
    int t;
    for (t = 0; t < count; t++) total += weights[t];
    if (!total) return -1;
    roll %= total;
    for (t = 0; t < count; t++) {
        if (!weights[t]) continue;
        if (roll < weights[t]) return t;
        roll -= weights[t];
    }
    return -1;
}

/* A card of tier `tier`, or of the one before it when its pool has none
 * left, and so on down; *used is the tier it came from (-1 with no card). */
static int pick_down(const Dealing *d, int tier, unsigned roll, int *used)
{
    for (; tier >= 0; tier--) {
        int card = pick(d, &d->pack->tiers[tier].pool, roll);
        if (card) { *used = tier; return card; }
    }
    *used = -1;
    return 0;
}

static int slot_kind(const Pack *pack, int s)
{
    return pack->slots ? pack->slots[s].kind : PACK_SLOT_ODDS;
}

int Packs_Deal(int index, const PacksProgress *progress, PackHeld held, void *held_context, PackRandom random,
               void *random_context, PackResult *result)
{
    const Pack *pack = Packs_At(index);
    unsigned tier_roll[PACK_COUNT_MAX], card_roll[PACK_COUNT_MAX], odds[PACK_TIERS_MAX];
    int need[PACK_TIERS_MAX];
    Dealing d;
    int s, t, g;

    memset(result, 0, sizeof(*result));
    if (!pack) return 0;
    /* The numbers first, four a slot, whatever the slot turns out to be. */
    for (s = 0; s < pack->count; s++) {
        unsigned a = (unsigned)random(random_context) & 0x7FFF, b = (unsigned)random(random_context) & 0x7FFF;
        unsigned c = (unsigned)random(random_context) & 0x7FFF, e = (unsigned)random(random_context) & 0x7FFF;
        tier_roll[s] = a << 15 | b;
        card_roll[s] = c << 15 | e;
    }
    memset(&d, 0, sizeof(d));
    d.pack = pack;
    d.held = held;
    d.held_context = held_context;
    for (t = 0; t < pack->tier_count; t++) odds[t] = pack->tiers[t].odds;
    result->count = pack->count;
    /* A fixed card is dealt whatever comes before it: counted from the
       start, so "unique_in_pack" and "max_copies" leave it to its slot. */
    for (s = 0; s < pack->count; s++) {
        if (slot_kind(pack, s) == PACK_SLOT_CARD) take(&d, pack->slots[s].card, 1);
    }
    for (s = 0; s < pack->count; s++) {
        const PackSlot *slot = pack->slots ? &pack->slots[s] : NULL;
        int card = 0, used = -1;
        switch (slot_kind(pack, s)) {
        case PACK_SLOT_CARD:
            card = slot->card;
            break;
        case PACK_SLOT_POOL:
            card = pick(&d, &slot->pool, card_roll[s]);
            break;
        case PACK_SLOT_TIER:
            card = pick_down(&d, slot->tier, card_roll[s], &used);
            break;
        case PACK_SLOT_MIX:
            t = pick_tier(slot->mix, pack->tier_count, tier_roll[s]);
            if (t >= 0) card = pick_down(&d, t, card_roll[s], &used);
            break;
        default:
            t = pick_tier(odds, pack->tier_count, tier_roll[s]);
            if (t >= 0) card = pick_down(&d, t, card_roll[s], &used);
            break;
        }
        result->cards[s] = (unsigned short)card;
        result->tiers[s] = (signed char)used;
        if (slot_kind(pack, s) != PACK_SLOT_CARD) take(&d, card, 1);
    }
    /* What the guarantee and the pity ask for, the rarest first, so a slot
     * raised for it counts for the ones below. */
    for (t = 0; t < pack->tier_count; t++) {
        need[t] = pack->guarantee[t];
        if (pack->pity[t] && progress && progress->packs[index].pity[t] + 1 >= pack->pity[t] && need[t] < 1) need[t] = 1;
    }
    for (g = pack->tier_count - 1; g >= 0; g--) {
        int have = 0;
        if (!need[g]) continue;
        for (s = 0; s < pack->count; s++) have += result->tiers[s] >= g;
        /* The last slots dealt by tier first: dealt again, with their own
         * card number, from the tier asked for (or a rarer one when it has
         * nothing left). A slot of its own pool or card is left as it is. */
        for (s = pack->count - 1; s >= 0 && have < need[g]; s--) {
            int kind = slot_kind(pack, s), old = result->cards[s], card = 0, used = -1;
            if (kind == PACK_SLOT_CARD || kind == PACK_SLOT_POOL || result->tiers[s] >= g || result->redone[s]) continue;
            take(&d, old, -1);
            for (t = g; t < pack->tier_count && !card; t++) {
                card = pick(&d, &pack->tiers[t].pool, card_roll[s]);
                if (card) used = t;
            }
            if (!card) {   /* nothing of that rarity left to give */
                take(&d, old, 1);
                break;
            }
            result->cards[s] = (unsigned short)card;
            result->tiers[s] = (signed char)used;
            result->redone[s] = 1;
            take(&d, card, 1);
            have++;
        }
    }
    return pack->count;
}

unsigned Packs_SaveSeed(unsigned duelist_code, const char *identity, unsigned opened)
{
    char text[PACK_IDENTITY_MAX + 32];
    int length = snprintf(text, sizeof(text), "%08X:%s:%u", duelist_code, identity ? identity : "", opened);
    return hash_bytes(2166136261u, text, (size_t)(length > 0 ? length : 0));
}

int Packs_LcgNext(void *seed)
{
    unsigned *state = seed;
    *state = *state * 1103515245u + 12345u;
    return (int)((*state >> 16) & 0x7FFF);
}

void Packs_Record(int index, const PackResult *result, unsigned starchips, PacksProgress *progress)
{
    const Pack *pack = Packs_At(index);
    PackProgress *mine;
    int t, s;
    if (!pack || !progress) return;
    mine = &progress->packs[index];
    mine->bought++;
    mine->opened++;
    if (pack->once) mine->used = 1;
    progress->packs_opened++;
    progress->starchips_spent += starchips;
    for (t = 0; t < pack->tier_count; t++) {
        int had = 0;
        if (!pack->pity[t]) continue;
        for (s = 0; s < result->count; s++) had |= result->tiers[s] >= t;
        if (had) mine->pity[t] = 0;
        else if (mine->pity[t] < 0xFFFF) mine->pity[t]++;
    }
}

int Packs_UnlockMet(const PackUnlock *unlock, const PacksProgress *progress, PackSaveCondition save, void *context)
{
    static const PacksProgress none;
    int k;
    if (!progress) progress = &none;
    if (unlock->never) return 0;
    if (progress->starchips_spent < unlock->starchips_spent) return 0;
    if (progress->packs_opened < unlock->packs_opened) return 0;
    for (k = 0; k < unlock->opened_count; k++) {
        int pack = unlock->opened_pack[k];
        if (pack < 0 || progress->packs[pack].opened < unlock->opened_times[k]) return 0;
    }
    if (unlock->beat[0] || unlock->card[0] || unlock->wins > 0 || unlock->story >= 0) {
        if (!save || !save(unlock, context)) return 0;
    }
    return 1;
}

int Packs_Unlocked(int index, const PacksProgress *progress, PackSaveCondition save, void *context)
{
    const Pack *pack = Packs_At(index);
    if (!pack) return 0;
    return !pack->has_unlock || Packs_UnlockMet(&pack->unlock, progress, save, context);
}

int Packs_StockLeft(int index, const PacksProgress *progress)
{
    const Pack *pack = Packs_At(index);
    unsigned bought;
    if (!pack || pack->stock < 0) return -1;
    bought = progress ? progress->packs[index].bought : 0;
    return bought >= (unsigned)pack->stock ? 0 : pack->stock - (int)bought;
}

int Packs_NothingLeft(int index, PackHeld held, void *held_context)
{
    const Pack *pack = Packs_At(index);
    const PackPool *pools[PACK_TIERS_MAX + PACK_COUNT_MAX];
    int count = 0, i, k;
    if (!pack || (!pack->max_copies && !chest_room)) return 0;
    for (i = 0; i < pack->tier_count; i++) pools[count++] = &pack->tiers[i].pool;
    for (i = 0; pack->slots && i < pack->count; i++) {
        if (pack->slots[i].kind == PACK_SLOT_CARD) return 0;   /* dealt whatever the player holds */
        if (pack->slots[i].kind == PACK_SLOT_POOL) pools[count++] = &pack->slots[i].pool;
    }
    for (i = 0; i < count; i++) {
        for (k = 0; k < pools[i]->count; k++) {
            const PackEntry *entry = &pools[i]->entries[k];
            if (!entry->weight) continue;
            if (pack->max_copies && (held ? held(entry->card, held_context) : 0) >= pack->max_copies) continue;
            if (chest_room && chest_room(entry->card, chest_room_context) <= 0) continue;
            return 0;
        }
    }
    return 1;
}

int Packs_FixedCardsFit(int index)
{
    const Pack *pack = Packs_At(index);
    int i, k;
    if (!pack || !pack->slots || !chest_room) return 1;
    for (i = 0; i < pack->count; i++) {
        int card = pack->slots[i].card, copies = 0;
        if (pack->slots[i].kind != PACK_SLOT_CARD) continue;
        for (k = 0; k < pack->count; k++) copies += pack->slots[k].kind == PACK_SLOT_CARD && pack->slots[k].card == card;
        if (copies > chest_room(card, chest_room_context)) return 0;
    }
    return 1;
}

int Packs_RefusesWhenNothingLeft(int index)
{
    const Pack *pack = Packs_At(index);
    int rule;
    if (!pack) return 0;
    rule = pack->when_nothing_left != PACK_NOTHING_SHOPS ? pack->when_nothing_left : Packs_Rules()->when_nothing_left;
    return rule == PACK_NOTHING_REFUSE;
}

unsigned Packs_TierChance(int index, int tier)
{
    const Pack *pack = Packs_At(index);
    unsigned total = 0;
    int t;
    if (!pack || tier < 0 || tier >= pack->tier_count) return 0;
    for (t = 0; t < pack->tier_count; t++) total += pack->tiers[t].odds;
    return total ? (unsigned)((unsigned long long)pack->tiers[tier].odds * 1000000u / total) : 0;
}

/* --- beside the save ----------------------------------------------------------
 *
 *     spent <starchips>
 *     opened <packs>
 *     pack <identity> bought <n> opened <n> used <0|1> pity <tier>=<n> ...
 */

void Packs_ForgetProgress(PacksProgress *progress)
{
    memset(progress, 0, sizeof(*progress));
    free(foreign);
    foreign = NULL;
    foreign_size = 0;
}

int Packs_ProgressEmpty(const PacksProgress *progress)
{
    static const PacksProgress none;
    return !foreign && !memcmp(progress, &none, sizeof(none));
}

const char *Packs_ForeignLines(size_t *size)
{
    *size = foreign_size;
    return foreign ? foreign : "";
}

void Packs_SetForeignLines(const char *text, size_t size)
{
    char *copy = size ? malloc(size + 1) : NULL;
    if (size && !copy) return;
    if (copy) {
        memcpy(copy, text, size);
        copy[size] = '\0';
    }
    free(foreign);
    foreign = copy;
    foreign_size = copy ? size : 0;
}

static void keep_foreign(const char *line)
{
    size_t length = strlen(line);
    char *bigger = realloc(foreign, foreign_size + length + 2);
    if (!bigger) return;
    foreign = bigger;
    memcpy(foreign + foreign_size, line, length);
    foreign_size += length;
    if (!length || line[length - 1] != '\n') foreign[foreign_size++] = '\n';
    foreign[foreign_size] = '\0';
}

void Packs_ReadProgress(FILE *file, PacksProgress *progress)
{
    char line[1024];
    Packs_ForgetProgress(progress);
    while (file && fgets(line, sizeof(line), file)) {
        char identity[PACK_IDENTITY_MAX], *at;
        unsigned value;
        int index, used = 0, skip = 0;
        const Pack *pack;
        if (sscanf(line, "spent %u", &value) == 1) { progress->starchips_spent = value; continue; }
        if (sscanf(line, "opened %u", &value) == 1) { progress->packs_opened = value; continue; }
        if (sscanf(line, "pack %129s %n", identity, &skip) < 1 || !skip) continue;
        index = Packs_Find(identity);
        pack = Packs_At(index);
        if (!pack || strcmp(pack->identity, identity)) {
            keep_foreign(line);   /* a pack another run had */
            continue;
        }
        at = line + skip;
        while (*at) {
            char word[PACK_KEY_MAX + 16];
            int length = 0;
            if (sscanf(at, "%79s %n", word, &length) < 1 || !length) break;
            at += length;
            if (!strcmp(word, "bought") && sscanf(at, "%u %n", &value, &length) >= 1) {
                progress->packs[index].bought = value;
                at += length;
            } else if (!strcmp(word, "opened") && sscanf(at, "%u %n", &value, &length) >= 1) {
                progress->packs[index].opened = value;
                at += length;
            } else if (!strcmp(word, "used") && sscanf(at, "%d %n", &used, &length) >= 1) {
                progress->packs[index].used = (unsigned char)(used != 0);
                at += length;
            } else if (!strcmp(word, "pity")) {
                continue;
            } else {
                char *equals = strchr(word, '=');
                int t;
                if (!equals) continue;
                *equals = '\0';
                t = tier_named(pack, word);
                if (t >= 0) {
                    unsigned long n = strtoul(equals + 1, NULL, 10);
                    progress->packs[index].pity[t] = (unsigned short)(n > 0xFFFF ? 0xFFFF : n);
                }
            }
        }
    }
}

void Packs_WriteProgress(FILE *file, const PacksProgress *progress)
{
    int i, t;
    fprintf(file, "# The card packs this save bought (notes/card-packs.md).\n");
    fprintf(file, "spent %u\nopened %u\n", progress->starchips_spent, progress->packs_opened);
    for (i = 0; i < pack_count; i++) {
        const PackProgress *mine = &progress->packs[i];
        int any = mine->bought || mine->opened || mine->used;
        for (t = 0; t < packs[i].tier_count; t++) any |= mine->pity[t] != 0;
        if (!any) continue;
        fprintf(file, "pack %s bought %u opened %u used %d", packs[i].identity, mine->bought, mine->opened, mine->used);
        for (t = 0, any = 0; t < packs[i].tier_count; t++) {
            if (!packs[i].pity[t]) continue;
            fprintf(file, "%s %s=%u", any++ ? "" : " pity", packs[i].tiers[t].name, mine->pity[t]);
        }
        fputc('\n', file);
    }
    if (foreign) fputs(foreign, file);
}
