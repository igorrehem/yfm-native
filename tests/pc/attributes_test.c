/* The mod-defined card attribute registry: retail names, renamed names,
 * added values and the two nibbles the original game reserves. */
#include "../../src/pc/cards/attributes.c"
#include <assert.h>
#include <stdarg.h>

static int notes;
static const JsonValue *loaded_manifest;
void Mods_Note(const char *id, const char *format, ...)
{
    va_list args;
    (void)id;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
    notes++;
}
int Mods_LoadedCount(void) { return loaded_manifest ? 1 : 0; }
int Mods_Loaded(int index) { return index == 0 ? 7 : -1; }
int Mods_Active(int mod) { return mod == 7; }
const char *Mods_Id(int mod) { (void)mod; return ""; }
const char *Mods_Directory(int mod) { (void)mod; return "."; }
const JsonValue *Mods_Manifest(int mod) { return mod == 7 ? loaded_manifest : NULL; }
int Paths_Contained(const char *path) { return path && path[0] != '/'; }
void Attributes_IconsClear(void) {}

int main(void)
{
    JsonDocument *first, *second, *invalid, *loaded, *numbers;
    char error[128];
    Attributes_Clear();
    assert(Attributes_Find("light") == 0);
    assert(Attributes_Find("6") == -1 && Attributes_Find("7") == -1);
    assert(Attributes_Find("8") == -1 && !Attributes_Declared(8));
    /* The loaded-mod index is not necessarily the mod's storage index. */
    loaded = Json_Parse("{\"attributes\":{\"attributes\":[{\"id\":8,\"name\":\"Divine\"}]}}", error, sizeof(error));
    assert(loaded);
    loaded_manifest = Json_Root(loaded);
    Attributes_Build();
    assert(Attributes_Find("Divine") == 8 && Attributes_Declared(8));
    Json_Free(loaded);
    loaded_manifest = NULL;
    Attributes_Clear();
    first = Json_Parse("{\"attributes\":{\"attributes\":[{\"id\":0,\"name\":\"Radiant\"},{\"id\":8,\"name\":\"Metal\"},{\"id\":6,\"name\":\"Nope\"}]}}",
                       error, sizeof(error));
    assert(first);
    Attributes_Add("first", Json_Root(first));
    assert(Attributes_Find("Radiant") == 0 && Attributes_Find("Light") == 0);
    assert(Attributes_Find("metal") == 8 && Attributes_Declared(8));
    assert(!strcmp(Attributes_Name(8), "Metal") && notes == 1);
    second = Json_Parse("{\"attributes\":{\"attributes\":[{\"id\":8,\"name\":\"Steel\"},{\"id\":255,\"name\":\"Void\"}]}}",
                        error, sizeof(error));
    assert(second);
    Attributes_Add("second", Json_Root(second));
    assert(Attributes_Find("Metal") == -1 && Attributes_Find("Steel") == 8 && Attributes_Find("Void") == 255);
    invalid = Json_Parse("{\"attributes\":{\"attributes\":[{\"id\":9,\"name\":\"Light\"},{\"id\":10,\"name\":\"8\"},{\"id\":11,\"name\":\"8-\"},{\"id\":12,\"name\":\"!!!\"},{\"id\":\"13\",\"name\":\"Nope\"}]}}",
                         error, sizeof(error));
    assert(invalid);
    Attributes_Add("invalid", Json_Root(invalid));
    assert(!Attributes_Declared(9) && !Attributes_Declared(10) && !Attributes_Declared(11) && !Attributes_Declared(12));
    assert(Attributes_Find("Nope") == -1 && notes == 6);
    numbers = Json_Parse("{\"huge\":256,\"attribute\":8}", error, sizeof(error));
    assert(numbers);
    assert(Attributes_Value(Json_Member(Json_Root(numbers), "huge")) == -1);
    assert(Attributes_Value(Json_Member(Json_Root(numbers), "attribute")) == 8);
    Json_Free(first);
    Json_Free(second);
    Json_Free(invalid);
    Json_Free(numbers);
    Attributes_Clear();
    return 0;
}
