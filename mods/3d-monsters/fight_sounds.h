#ifndef FIGHT_SOUNDS_H
#define FIGHT_SOUNDS_H
/* fight_sounds.c's own entry points, called from field_models.c, as
 * field_art.c's are: the fighters' own sounds, as the 3D arena plays them. */
#include "types.h"
#include "game/model.h"
#include "pc/mods/modapi.h"

void FightSounds_Init(const MemoriesModHost *host);
/* Side `side`'s fighter (0 the attacker, 1 the defender) is the MODEL.MRG
 * record at `record_lba`, and `entries` are its slot's sound_entries: the
 * sounds they name in the rows of `rows` (bit n for row n), the rows the
 * fight can play, are read and made ready, and what the side had before is
 * let go. Nothing when the host plays no sounds of a mod's (before API 12). */
void FightSounds_Load(int side, int record_lba, const ModelSlotSoundEntry *entries, unsigned rows);
/* Once a frame for each fighter, with its slot as it is about to be drawn:
 * the entries for the row it is in whose times it has passed since the last
 * call play. `playing` says the row is one the fight started; while it is
 * not, nothing plays, and the next row starts from its beginning. */
void FightSounds_Update(int side, const ModelSlot *slot, int playing);
/* Every side's sounds go. */
void FightSounds_Release(void);
#endif
