/* What the duel's monster effects keep (src/pc/cards/monster_effects_duel.h).
 * A game unit, like card_storage.c, so it is in the game's data and in every
 * save state; it sorts after the other units, so no variable of theirs moves
 * and states of earlier builds still load. */
#include "types.h"
#include "pc/cards/monster_effects_duel.h"

MonsterEffectsState gMonsterEffects = {0};
