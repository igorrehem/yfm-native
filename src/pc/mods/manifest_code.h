#ifndef MEMORIES_PC_MODS_MANIFEST_CODE_H
#define MEMORIES_PC_MODS_MANIFEST_CODE_H
/* Whether a mod.json makes a code mod, the one test the loader (mods.c
 * read_manifest, Mods_HasCode) and the import (import.c) share: a
 * "library", or a "libraries" object with any entry (one without this
 * game's target still looks for <id>.<target>.o). */
#include "json.h"

static inline int Manifest_HasCode(const JsonValue *root)
{
    const char *library = Json_String(Json_Member(root, "library"), NULL);
    const JsonValue *libraries = Json_Member(root, "libraries");
    return (library && *library) || (Json_TypeOf(libraries) == JSON_OBJECT && Json_Count(libraries));
}

#endif
