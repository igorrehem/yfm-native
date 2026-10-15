#include "card_text_colors.h"
#include "cards.h"
#include "stars.h"
#include "pc/mods/json.h"
#include "pc/mods/mods.h"
#include "game/duel_effect.h"
#include <stdio.h>
#include <string.h>

/* There are eight 4bpp text ramps in the retail font texture. */
#define COLOR_COUNT 8
#define BOX_COUNT 16

typedef struct {
    unsigned char name, description, guardian;
} CardColors;
typedef struct {
    struct DuelEffectChannel *channel;
    unsigned char saved;
    unsigned char active;
} SavedColor;

static CardColors colors[CARD_TABLE_ID_END];
static unsigned char star_colors[STARS_MAX + 1];
static SavedColor saved[BOX_COUNT];
static int built;

static int color(const JsonValue *value)
{
    long n = Json_Number(value, -1);
    return Json_TypeOf(value) == JSON_NUMBER && n >= 0 && n < COLOR_COUNT ? (int)n : -1;
}

static void set_colors(const char *mod, const JsonValue *entry, int card, const char *label)
{
    static const char *const keys[] = {"name", "description", "guardian_star"};
    unsigned char *into[] = {&colors[card].name, &colors[card].description, &colors[card].guardian};
    int i;
    if (!Cards_Valid(card) || Json_TypeOf(entry) != JSON_OBJECT) return;
    for (i = 0; i < 3; i++) {
        const JsonValue *value = Json_Member(entry, keys[i]);
        if (!value) continue;
        if (color(value) < 0)
            Mods_Note(mod, "card_text_colors: card '%s': \"%s\" must be a color from 0 to 7",
                      label, keys[i]);
        else *into[i] = (unsigned char)(color(value) + 1);
    }
}

static void read_cards(const char *mod, const JsonValue *list)
{
    const JsonValue *entry;
    if (Json_TypeOf(list) != JSON_ARRAY && Json_TypeOf(list) != JSON_OBJECT) return;
    for (entry = Json_At(list, 0); entry; entry = Json_Next(entry)) {
        const char *name = Json_Name(entry);
        const JsonValue *card = Json_Member(entry, "card");
        char label[64];
        int id;
        if (Json_TypeOf(entry) != JSON_OBJECT) continue;
        if (card) id = Cards_Reference(card);
        else id = Cards_Named(name);
        if (Json_TypeOf(card) == JSON_NUMBER)
            snprintf(label, sizeof(label), "%ld", Json_Number(card, 0));
        else
            snprintf(label, sizeof(label), "%s", card ? Json_String(card, "") : name ? name : "");
        if (id <= 0) {
            Mods_Note(mod, "card_text_colors: no card called '%s'", label);
            continue;
        }
        set_colors(mod, entry, id, label);
    }
}

static void read_stars(const char *mod, const JsonValue *list)
{
    const JsonValue *entry;
    if (Json_TypeOf(list) != JSON_ARRAY && Json_TypeOf(list) != JSON_OBJECT) return;
    for (entry = Json_At(list, 0); entry; entry = Json_Next(entry)) {
        const JsonValue *star = Json_Member(entry, "star");
        const JsonValue *value = Json_Member(entry, "color");
        int id, tint;
        if (Json_TypeOf(entry) != JSON_OBJECT) continue;
        id = star ? Stars_Value(star) : -1;
        tint = color(value);
        if (id < 1 || id > STARS_MAX) {
            Mods_Note(mod, "card_text_colors: unknown guardian star");
        } else if (tint < 0) {
            Mods_Note(mod, "card_text_colors: guardian star '%s': \"color\" must be from 0 to 7", Stars_Name(id));
        } else {
            star_colors[id] = (unsigned char)(tint + 1);
        }
    }
}

void CardTextColors_Build(void)
{
    int i;
    memset(colors, 0, sizeof(colors));
    memset(star_colors, 0, sizeof(star_colors));
    memset(saved, 0, sizeof(saved));
    built = 1;
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        const JsonValue *section;
        if (!Mods_Active(mod)) continue;
        section = Json_Member(Mods_Manifest(mod), "card_text_colors");
        if (Json_TypeOf(section) != JSON_OBJECT) continue;
        read_cards(Mods_Id(mod), Json_Member(section, "cards"));
        read_stars(Mods_Id(mod), Json_Member(section, "guardian_stars"));
    }
}

static SavedColor *slot(struct DuelEffectChannel *channel, int make)
{
    int i;
    for (i = 0; i < BOX_COUNT; i++) if (saved[i].channel == channel) return &saved[i];
    if (!make) return NULL;
    for (i = 0; i < BOX_COUNT; i++) if (!saved[i].channel) { saved[i].channel = channel; return &saved[i]; }
    return NULL;
}

void CardTextColors_Restore(struct DuelEffectChannel *channel)
{
    SavedColor *state = slot(channel, 0);
    if (state && state->active) channel->field_54 = state->saved;
    if (state) state->active = 0;
}

void CardTextColors_ResetChannel(struct DuelEffectChannel *channel)
{
    SavedColor *state = slot(channel, 0);
    if (state) memset(state, 0, sizeof(*state));
}

void CardTextColors_DestroyChannel(struct DuelEffectChannel *channel)
{
    SavedColor *state;
    CardTextColors_Restore(channel);
    state = slot(channel, 0);
    if (state) memset(state, 0, sizeof(*state));
}

void CardTextColors_Apply(struct DuelEffectChannel *channel, int part, int star)
{
    int id = gDuel_wSelectedCardID;
    unsigned char tint = 0;
    SavedColor *state;
    /* Card tables and mod-added guardian-star names are ready by the first
     * detail-box command. Delaying the manifest pass keeps Cards_Build
     * standalone for focused card-table tests. */
    if (!built) CardTextColors_Build();
    if (!Cards_Valid(id)) return;
    if (part == CARD_TEXT_COLOR_NAME) tint = colors[id].name;
    else if (part == CARD_TEXT_COLOR_DESCRIPTION) tint = colors[id].description;
    else if (part == CARD_TEXT_COLOR_GUARDIAN_STAR) {
        tint = colors[id].guardian;
        if (!tint && star >= 1 && star <= STARS_MAX) tint = star_colors[star];
    }
    if (!tint || !(state = slot(channel, 1))) return;
    state->saved = channel->field_54;
    state->active = 1;
    channel->field_54 = (unsigned char)(tint - 1);
}
