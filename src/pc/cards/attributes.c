/* The mod-defined card-attribute registry (attributes.h).  This deliberately
 * has no game-rule table of its own: attributes are identifiers that cards
 * and the existing equip/effect tables compare. */
#include "attributes.h"
#include "pc/mods/json.h"
#include "pc/mods/mods.h"
#include "pc/platform/paths.h"
#include "pc/compat/fs.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *const retail_names[ATTRIBUTES_RETAIL] = {
    "Light", "Dark", "Earth", "Water", "Fire", "Wind"
};
static char *names[ATTRIBUTES_MAX + 1];
static char *icons[ATTRIBUTES_MAX + 1];
static unsigned char declared[ATTRIBUTES_MAX + 1];
static int built;

static int same_letters(const char *a, const char *b)
{
    for (;;) {
        while (*a && !isalnum((unsigned char)*a) && !((unsigned char)*a & 0x80)) a++;
        while (*b && !isalnum((unsigned char)*b) && !((unsigned char)*b & 0x80)) b++;
        if (!*a || !*b) return !*a && !*b;
        if (tolower((unsigned char)*a++) != tolower((unsigned char)*b++)) return 0;
    }
}

static char *copy(const char *text)
{
    size_t size = strlen(text) + 1;
    char *out = malloc(size);
    if (out) memcpy(out, text, size);
    return out;
}

static int name_has_letters(const char *name)
{
    for (; *name; name++)
        if (isalnum((unsigned char)*name) || ((unsigned char)*name & 0x80)) return 1;
    return 0;
}

/* same_letters ignores punctuation. Do not admit a name whose normalized
 * spelling is only ASCII digits: it would collide with an id lookup (for
 * example, both "8" and "8-" normalize to the numeric id 8). */
static int numeric_name(const char *name)
{
    int digit = 0;
    for (; *name; name++) {
        unsigned char c = (unsigned char)*name;
        if (isdigit(c)) {
            digit = 1;
        } else if (isalnum(c) || (c & 0x80)) {
            return 0;
        }
    }
    return digit;
}

void Attributes_Clear(void)
{
    Attributes_IconsClear();
    for (int i = 0; i <= ATTRIBUTES_MAX; i++) {
        free(names[i]);
        free(icons[i]);
        names[i] = NULL;
        icons[i] = NULL;
        declared[i] = 0;
    }
    built = 0;
}

/* Declarations use names as keys throughout a manifest, so a new name must
 * never shadow one that lookup would otherwise resolve to another id. */
static int name_taken(const char *name, int except)
{
    for (int i = 0; i < ATTRIBUTES_RETAIL; i++)
        if (i != except && (same_letters(name, retail_names[i]) || same_letters(name, Attributes_Name(i)))) return 1;
    for (int i = ATTRIBUTES_RETAIL; i <= ATTRIBUTES_MAX; i++)
        if (i != except && names[i] && same_letters(name, names[i])) return 1;
    return 0;
}

int Attributes_Valid(int attribute)
{
    return attribute >= 0 && attribute <= ATTRIBUTES_MAX && attribute != 6 && attribute != 7;
}

const char *Attributes_Name(int attribute)
{
    if (attribute >= 0 && attribute < ATTRIBUTES_RETAIL)
        return names[attribute] ? names[attribute] : retail_names[attribute];
    return attribute >= 8 && attribute <= ATTRIBUTES_MAX && names[attribute] ? names[attribute] : "";
}

int Attributes_Declared(int attribute)
{
    return Attributes_Valid(attribute) && declared[attribute];
}

const char *Attributes_Icon(int attribute)
{
    return attribute >= 0 && attribute <= ATTRIBUTES_MAX ? icons[attribute] : NULL;
}

int Attributes_Find(const char *name)
{
    char *end;
    long value;
    if (!name || !*name) return -1;
    value = strtol(name, &end, 10);
    if (!*end && value >= 0 && value <= ATTRIBUTES_MAX && Attributes_Valid((int)value) &&
        (value < ATTRIBUTES_RETAIL || declared[(int)value])) return (int)value;
    /* Keep the six original spellings as aliases after a rename, just as
     * guardian-star lookup keeps Mars after a mod calls it Ares. */
    for (int i = 0; i < ATTRIBUTES_RETAIL; i++)
        if (same_letters(name, retail_names[i]) || same_letters(name, Attributes_Name(i))) return i;
    for (int i = 8; i <= ATTRIBUTES_MAX; i++)
        if (names[i] && same_letters(name, names[i])) return i;
    return -1;
}

int Attributes_Value(const JsonValue *value)
{
    if (!value) return -1;
    if (Json_TypeOf(value) == JSON_NUMBER) {
        long raw_attribute = Json_Number(value, -1);
        int attribute;
        if (raw_attribute < 0 || raw_attribute > ATTRIBUTES_MAX) return -1;
        attribute = (int)raw_attribute;
        return Attributes_Valid(attribute) && (attribute < ATTRIBUTES_RETAIL || declared[attribute]) ? attribute : -1;
    }
    return Json_TypeOf(value) == JSON_STRING ? Attributes_Find(Json_String(value, "")) : -1;
}

static void add(const char *mod, const char *directory, const JsonValue *manifest)
{
    const JsonValue *section = Json_Member(manifest, "attributes");
    const JsonValue *list;
    int index = 0;
    if (!section) return;
    list = Json_Member(section, "attributes");
    if (Json_TypeOf(section) != JSON_OBJECT || Json_TypeOf(list) != JSON_ARRAY) {
        Mods_Note(mod, "attributes: an object with an \"attributes\" list of {\"id\", \"name\"}");
        return;
    }
    for (const JsonValue *entry = Json_At(list, 0); entry; entry = Json_Next(entry), index++) {
        const JsonValue *id_value = Json_Member(entry, "id");
        const char *name = Json_String(Json_Member(entry, "name"), NULL);
        const char *icon = Json_String(Json_Member(entry, "icon"), NULL);
        long raw_id = Json_Number(id_value, -1);
        int id;
        if (Json_TypeOf(entry) != JSON_OBJECT || !id_value) {
            Mods_Note(mod, "attributes: attributes[%d]: an object with an \"id\"", index);
        } else if (Json_TypeOf(id_value) != JSON_NUMBER) {
            Mods_Note(mod, "attributes: attributes[%d]: \"id\" is a number", index);
        } else if (raw_id < 0 || raw_id > ATTRIBUTES_MAX) {
            Mods_Note(mod, "attributes: attributes[%d]: an attribute id is 0-5 or 8-255", index);
        } else if ((id = (int)raw_id) == 6 || id == 7) {
            Mods_Note(mod, "attributes: attributes[%d]: 6 and 7 are reserved for the game's magic and trap cards", index);
        } else if (!name || !*name) {
            Mods_Note(mod, "attributes: attributes[%d]: \"name\" is a non-empty string", index);
        } else if (!name_has_letters(name)) {
            Mods_Note(mod, "attributes: attributes[%d]: \"name\" contains a letter or number", index);
        } else if (numeric_name(name)) {
            Mods_Note(mod, "attributes: attributes[%d]: \"name\" is not a numeric attribute id", index);
        } else if (name_taken(name, id)) {
            Mods_Note(mod, "attributes: attributes[%d]: \"name\" duplicates another attribute", index);
        } else {
            char *new_name = copy(name);
            if (!new_name) continue;
            free(names[id]);
            names[id] = new_name;
            declared[id] = 1;
            /* A declaration is a complete visual override. It may opt into a
             * new icon below; omitting one deliberately removes an older
             * mod's icon instead of inheriting it under a new name. */
            free(icons[id]);
            icons[id] = NULL;
            if (icon) {
                char path[1200];
                FILE *probe;
                if (!*icon) {
                    Mods_Note(mod, "attributes: attributes[%d]: \"icon\" names a PNG in the mod", index);
                } else if (!directory || !Paths_Contained(icon) ||
                           snprintf(path, sizeof(path), "%s/%s", directory, icon) >= (int)sizeof(path)) {
                    Mods_Note(mod, "attributes: attributes[%d]: \"icon\" is outside the mod", index);
                } else {
                    probe = fopen(path, "rb");
                    if (!probe) {
                        Mods_Note(mod, "attributes: attributes[%d]: \"icon\": %s is not there", index, icon);
                    } else {
                        fclose(probe);
                        free(icons[id]);
                        icons[id] = copy(path);
                    }
                }
            }
        }
    }
}

void Attributes_Add(const char *mod, const JsonValue *manifest)
{
    add(mod, ".", manifest);
}

void Attributes_Build(void)
{
    if (built) return;
    built = 1;
    for (int i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        if (Mods_Active(mod)) add(Mods_Id(mod), Mods_Directory(mod), Mods_Manifest(mod));
    }
}
