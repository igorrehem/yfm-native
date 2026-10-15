#ifndef FIELD_ART_H
#define FIELD_ART_H
/* field_art.c's own entry points, called from field_models.c: this file is
 * the 3D Monsters mod's "Card art" style, not a mod of its own, so it takes
 * its host and its calls from field_models.c's single MemoriesModInit
 * instead of registering one of its own. */
#include "pc/mods/modapi.h"

void FieldArt_Init(const MemoriesModHost *host);
void FieldArt_DrawFrame(void);
void FieldArt_Reset(void);

#endif
