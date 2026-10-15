/* What the mods' "ui" key asks of the duel's pictures (ui_config.h), read
 * from every applied mod's manifest in load order, a later mod's value
 * winning key by key. Only the reading is here, with none of the game's
 * structures, so tests/pc/ui_config_test.c checks it at the host's own
 * width; pc/cards/duel_ui.c draws what it says. */
#include "ui_config.h"
#include "pc/mods/json.h"
#include "pc/mods/mods.h"
#include "paths.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *const UiConfig_ElementNames[UI_ELEMENTS] = {"lp_opponent", "lp_player",   "field",
                                                         "card_bar",    "hand_cursor", "field_cursor"};
const char *const UiConfig_PartNames[UI_PARTS] = {"name", "atk", "def", "type", "stars", "kind"};

/* What each element takes. The LP halves and the FIELD box are slid off
 * the screen sideways by the game (to x 408 and -116 for a battle and the
 * duel's end, 384 and -64 for Exodia: duel_scene_battle.c,
 * duel_result_runtime.c, func_80018FEC.c), so they are moved up or down
 * only, where they slide with the game's and leave the screen when it
 * does; the card bar, which the hand's cards slide in and out with,
 * takes only its colors, a picture of its own or none, while the parts of
 * its text (its "name", "atk", ...: read_part) move about on it; only the
 * LP halves have digits and words. */
enum { TAKES_X = 1, TAKES_Y = 2, TAKES_SCALE = 4, TAKES_LABEL = 8 };
static const unsigned takes[UI_ELEMENTS] = {TAKES_Y | TAKES_SCALE | TAKES_LABEL, TAKES_Y | TAKES_SCALE | TAKES_LABEL,
                                            TAKES_Y | TAKES_SCALE, 0, TAKES_X | TAKES_Y | TAKES_SCALE,
                                            TAKES_X | TAKES_Y | TAKES_SCALE};

/* How far a sliding element may reach from its middle towards the side it
 * leaves by and still be off the screen at the nearest place the game
 * slides it to: the panel's middle (280) to 384 leaves 64 of the screen
 * on its left; the FIELD box's (40, its parts 12 to 68) to -36 leaves 36
 * on its right. The game's own pieces reach 32 (and 8 more for a fifth
 * LP digit) and 28. 0: it does not slide. */
static const int slide_reach[UI_ELEMENTS] = {64, 64, 36, 0, 0, 0};
static const int own_reach[UI_ELEMENTS] = {32 + 8, 32 + 8, 28, 0, 0, 0};
static const int own_size[UI_ELEMENTS][2] = {{64, 20}, {64, 20}, {56, 24}, {320, 72}, {16, 16}, {64, 64}};

/* The card bar's parts where the game draws them in its text box (strings
 * 0x50 to 0x55, func_80023144; duel_effect_command.c lays them out): the
 * name's 8 x 12 letters from 0 (drawn 2 down), at most 28 of them (24 for
 * a monster's); the sword, then the four ATK digits from 203 (8 x 8), the
 * shield and DEF a row down; the type's icon at 237; the stars' at 255 and
 * 273 (the field's one star at 263); a magic card's word, 32 wide, at 255. */
enum { NAME_LETTERS = 28, LETTER = 8 };
static const int part_home[UI_PARTS][4] = {{0, 2, NAME_LETTERS * LETTER, 12}, {195, 0, 40, 8}, {195, 8, 40, 8},
                                           {237, 0, 16, 16},  {255, 0, 34, 16}, {255, 0, 32, 16}};

static UiConfig config;
static int ready;

static void defaults(void)
{
    int i;
    ready = 1;
    memset(&config, 0, sizeof(config));
    for (i = 0; i < UI_ELEMENTS; i++) {
        config.element[i].scale = 100;
        config.element[i].tint = 0xFFFFFF;
        config.element[i].digits = 0xFFFFFF;
    }
    for (i = 0; i < UI_PARTS; i++) config.part[i].tint = 0xFFFFFF;
}

void UiConfig_PartHome(int part, int spacing, int *x, int *y, int *w, int *h)
{
    if (part < 0 || part >= UI_PARTS) part = UI_PART_NAME;
    *x = part_home[part][0];
    *y = part_home[part][1];
    *w = part_home[part][2] + (part == UI_PART_NAME ? (NAME_LETTERS - 1) * spacing : 0);
    *h = part_home[part][3];
}

void UiConfig_PartRange(int part, int spacing, int *x0, int *x1, int *y0, int *y1)
{
    int x, y, w, h;
    UiConfig_PartHome(part, spacing, &x, &y, &w, &h);
    *x0 = UI_BAR_LEFT - x;
    *x1 = UI_BAR_RIGHT - (x + w);
    *y0 = UI_BAR_TOP - y;
    *y1 = UI_BAR_BOTTOM - (y + h);
}

/* "#RRGGBB", "RRGGBB" or a number; -1 when it is none of those. */
static long read_color(const JsonValue *value)
{
    const char *text;
    char *end;
    long color;
    if (Json_TypeOf(value) == JSON_NUMBER) {
        color = Json_Number(value, -1);
        return color >= 0 && color <= 0xFFFFFF ? color : -1;
    }
    text = Json_String(value, NULL);
    if (!text) return -1;
    if (*text == '#') text++;
    if (strlen(text) != 6) return -1;
    color = strtol(text, &end, 16);
    return *end ? -1 : color;
}

static void color_member(const char *mod, const char *name, const JsonValue *object, const char *key, uint32_t *out)
{
    const JsonValue *value = Json_Member(object, key);
    long color;
    if (!value) return;
    color = read_color(value);
    if (color < 0) Mods_Note(mod, "ui: duel %s \"%s\" is a color, \"#RRGGBB\"", name, key);
    else *out = (uint32_t)color;
}

/* A whole number from `low` to `high`, or noted and left as it was. */
static void int_member(const char *mod, const char *name, const JsonValue *object, const char *key, int low, int high,
                       int *out)
{
    const JsonValue *value = Json_Member(object, key);
    long number;
    if (!value) return;
    number = Json_Number(value, (long)low - 1);
    if (Json_TypeOf(value) != JSON_NUMBER || number < low || number > high) {
        Mods_Note(mod, "ui: duel %s \"%s\" is a whole number from %d to %d", name, key, low, high);
        return;
    }
    *out = (int)number;
}

/* d * scale / 100 rounded half away from 0, as duel_ui.c places a point
 * about an element's middle. */
static int scaled(int d, int scale)
{
    int t = d * scale;
    return t >= 0 ? (t + 50) / 100 : -((-t + 50) / 100);
}

/* How wide a picture of the mod's own is drawn before its size: its
 * "width", or its "height" at the element's shape, or the element's. */
static int picture_width(int which, int width, int height)
{
    if (width) return width;
    if (height) return own_size[which][0] * height / own_size[which][1];
    return own_size[which][0];
}

int UiConfig_Reach(int which, int scale, int picture, int width, int height)
{
    if (which < 0 || which >= UI_ELEMENTS) return 0;
    if (picture) {
        /* About the element's middle (duel_ui.c draw_picture): its far
         * side from there is width - width / 2. */
        width = picture_width(which, width, height);
        return scaled(width - width / 2, scale);
    }
    return scaled(own_reach[which], scale);
}

int UiConfig_ScaleMax(int which, int picture, int width, int height)
{
    int scale = UI_SCALE_MAX;
    if (which < 0 || which >= UI_ELEMENTS || !(takes[which] & TAKES_SCALE)) return 100;
    if (!slide_reach[which]) return UI_SCALE_MAX;
    while (scale > UI_SCALE_MIN && UiConfig_Reach(which, scale, picture, width, height) > slide_reach[which]) scale--;
    return scale;
}

/* A sliding element sized past what leaves the screen with the game's: at
 * the most size that does, its picture made narrower if even the least is
 * too wide; noted. */
static void fit(const char *mod, int which)
{
    UiElement *element = &config.element[which];
    UiImage *image = &element->image;
    int picture = image->file[0] != 0, most, width, fitted;
    if (!slide_reach[which]) return;
    most = UiConfig_ScaleMax(which, picture, image->width, image->height);
    if (element->scale > most) {
        Mods_Note(mod, "ui: duel %s at %d%% would not leave the screen with the game's; drawn at %d%%",
                  UiConfig_ElementNames[which], element->scale, most);
        element->scale = most;
    }
    if (UiConfig_Reach(which, element->scale, picture, image->width, image->height) <= slide_reach[which]) return;
    width = picture_width(which, image->width, image->height);
    for (fitted = width - 1; fitted > 1; fitted--) {
        if (UiConfig_Reach(which, element->scale, 1, fitted, 0) <= slide_reach[which]) break;
    }
    /* As tall as before for its new width. */
    if (image->height && !(image->height = image->height * fitted / width)) image->height = 1;
    image->width = fitted;
    Mods_Note(mod, "ui: duel %s \"image\" is too wide to leave the screen with the game's; drawn %d wide",
              UiConfig_ElementNames[which], image->width);
}

/* One of the card bar's parts: moved no further than keeps it on the bar
 * (the nearest place that does, noted), colored, hidden; the name's
 * letters spread. */
static void read_part(const char *mod, int which, const JsonValue *object)
{
    static const char *const known[] = {"x", "y", "tint", "hide", "spacing"};
    UiPart *part = &config.part[which];
    const JsonValue *member, *value;
    char name[32];
    int x0, x1, y0, y1;
    snprintf(name, sizeof(name), "card_bar %s", UiConfig_PartNames[which]);
    if (Json_TypeOf(object) != JSON_OBJECT) {
        Mods_Note(mod, "ui: duel %s is an object ({\"x\": -180, \"tint\": \"#FFE040\"})", name);
        return;
    }
    part->set = 1;
    config.parts = 1;
    snprintf(part->mod, sizeof(part->mod), "%s", mod);
    for (member = Json_At(object, 0); member; member = Json_Next(member)) {
        const char *key = Json_Name(member);
        size_t k;
        for (k = 0; k < sizeof(known) / sizeof(known[0]); k++) {
            if (!strcmp(key, known[k])) break;
        }
        if (k == sizeof(known) / sizeof(known[0])) Mods_Note(mod, "ui: unknown key \"%s\" in duel %s", key, name);
        else if (!strcmp(key, "spacing") && which != UI_PART_NAME)
            Mods_Note(mod, "ui: duel %s has no \"spacing\" (the name's letters have)", name);
    }
    if (which == UI_PART_NAME)
        int_member(mod, name, object, "spacing", UI_SPACING_MIN, UI_SPACING_MAX, &part->spacing);
    int_member(mod, name, object, "x", -400, 400, &part->x);
    int_member(mod, name, object, "y", -300, 300, &part->y);
    color_member(mod, name, object, "tint", &part->tint);
    if ((value = Json_Member(object, "hide"))) part->hidden = Json_Bool(value, part->hidden);
    UiConfig_PartRange(which, part->spacing, &x0, &x1, &y0, &y1);
    if (part->x < x0 || part->x > x1 || part->y < y0 || part->y > y1) {
        part->x = part->x < x0 ? x0 : part->x > x1 ? x1 : part->x;
        part->y = part->y < y0 ? y0 : part->y > y1 ? y1 : part->y;
        Mods_Note(mod, "ui: duel %s would leave the bar; moved by %d, %d instead", name, part->x, part->y);
    }
}

static int part_named(const char *key)
{
    int i;
    for (i = 0; i < UI_PARTS; i++) {
        if (!strcmp(key, UiConfig_PartNames[i])) return i;
    }
    return -1;
}

static void read_element(const char *mod, const char *directory, int which, const JsonValue *part)
{
    static const char *const known[] = {"x", "y", "scale", "tint", "hide", "image", "width", "height", "label",
                                        "digits"};
    UiElement *element = &config.element[which];
    const char *name = UiConfig_ElementNames[which];
    const JsonValue *value, *member;
    if (Json_TypeOf(part) != JSON_OBJECT) {
        Mods_Note(mod, "ui: duel \"%s\" is an object ({\"x\": -40, \"tint\": \"#80C0FF\"})", name);
        return;
    }
    element->set = 1;
    config.any = 1;
    snprintf(element->mod, sizeof(element->mod), "%s", mod);
    for (member = Json_At(part, 0); member; member = Json_Next(member)) {
        const char *key = Json_Name(member);
        size_t k;
        for (k = 0; k < sizeof(known) / sizeof(known[0]); k++) {
            if (!strcmp(key, known[k])) break;
        }
        if (k == sizeof(known) / sizeof(known[0]) && which == UI_CARD_BAR && part_named(key) >= 0) {
            read_part(mod, part_named(key), member);
        } else if (k == sizeof(known) / sizeof(known[0])) {
            Mods_Note(mod, "ui: unknown key \"%s\" in duel %s", key, name);
        } else if (!takes[which] && (!strcmp(key, "x") || !strcmp(key, "y") || !strcmp(key, "scale"))) {
            Mods_Note(mod, "ui: duel %s stays where the game has it (the hand's cards slide with it); \"%s\" is left "
                           "out (its \"name\", \"atk\", \"def\", \"type\", \"stars\" and \"kind\" move)", name, key);
        } else if (!(takes[which] & TAKES_X) && !strcmp(key, "x")) {
            Mods_Note(mod, "ui: duel %s is slid off the screen sideways by the game, so it keeps its place across; "
                           "\"x\" is left out (\"y\" moves it)", name);
        } else if (!(takes[which] & TAKES_LABEL) && (!strcmp(key, "label") || !strcmp(key, "digits"))) {
            Mods_Note(mod, "ui: duel %s has no \"%s\"", name, key);
        }
    }
    if (takes[which] & TAKES_X) int_member(mod, name, part, "x", -400, 400, &element->x);
    if (takes[which] & TAKES_Y) int_member(mod, name, part, "y", -300, 300, &element->y);
    if (takes[which] & TAKES_SCALE) int_member(mod, name, part, "scale", UI_SCALE_MIN, UI_SCALE_MAX, &element->scale);
    color_member(mod, name, part, "tint", &element->tint);
    if ((value = Json_Member(part, "hide"))) element->hidden = Json_Bool(value, element->hidden);
    if ((value = Json_Member(part, "image"))) {
        const char *file = Json_String(value, NULL);
        snprintf(element->image.mod, sizeof(element->image.mod), "%s", mod);
        if (!file || !*file) {
            element->image.file[0] = 0;   /* "" or null: the game's own again */
        } else if (!Paths_Contained(file) || snprintf(element->image.file, sizeof(element->image.file), "%s/%s",
                                                      directory, file) >= (int)sizeof(element->image.file)) {
            Mods_Note(mod, "ui: duel %s \"image\": %s is outside the mod", name, file);
            element->image.file[0] = 0;
        }
    }
    int_member(mod, name, part, "width", 0, 320, &element->image.width);
    int_member(mod, name, part, "height", 0, 240, &element->image.height);
    if (takes[which] & TAKES_LABEL) {
        color_member(mod, name, part, "digits", &element->digits);
        if ((value = Json_Member(part, "label"))) {
            const char *label = Json_String(value, NULL);
            if (!label) Mods_Note(mod, "ui: duel %s \"label\" is text", name);
            else if (strlen(label) >= sizeof(element->label))
                Mods_Note(mod, "ui: duel %s \"label\" is longer than %d letters", name, UI_LABEL - 1);
            snprintf(element->label, sizeof(element->label), "%s", label ? label : "");
        }
    }
    fit(mod, which);
}

void UiConfig_Read(const char *mod, const char *directory, const JsonValue *manifest)
{
    const JsonValue *ui = Json_Member(manifest, "ui"), *duel, *member;
    if (!ui) return;
    if (Json_TypeOf(ui) != JSON_OBJECT) {
        Mods_Note(mod, "\"ui\" is an object (notes/modding.md, \"The duel's pictures\")");
        return;
    }
    for (member = Json_At(ui, 0); member; member = Json_Next(member)) {
        if (strcmp(Json_Name(member), "duel")) Mods_Note(mod, "ui: unknown key \"%s\" (\"duel\")", Json_Name(member));
    }
    if (!(duel = Json_Member(ui, "duel"))) return;
    if (Json_TypeOf(duel) != JSON_OBJECT) {
        Mods_Note(mod, "ui: \"duel\" is an object of the duel's pictures by name (\"lp_player\": {\"x\": -200})");
        return;
    }
    for (member = Json_At(duel, 0); member; member = Json_Next(member)) {
        int i;
        for (i = 0; i < UI_ELEMENTS; i++) {
            if (!strcmp(Json_Name(member), UiConfig_ElementNames[i])) break;
        }
        if (i == UI_ELEMENTS) {
            Mods_Note(mod, "ui: no duel picture \"%s\" (lp_opponent, lp_player, field, card_bar, hand_cursor, "
                           "field_cursor)", Json_Name(member));
            continue;
        }
        read_element(mod, directory, i, member);
    }
}

void UiConfig_Reset(void)
{
    defaults();
}

const UiConfig *UiConfig_Load(void)
{
    int i;
    defaults();
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        if (Mods_Active(mod)) UiConfig_Read(Mods_Id(mod), Mods_Directory(mod), Mods_Manifest(mod));
    }
    return &config;
}

const UiConfig *UiConfig_Get(void)
{
    if (!ready) defaults();
    return &config;
}
