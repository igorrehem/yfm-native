/* The game's effect group of a few retail effect ids (src/game/
 * duel_effect_tables.c), for the tests that read cards' "monster_effects"
 * without the game: Dark Hole (index 35) and Raigeki (36) do something,
 * Ultimate Dragon's ritual (675, index 74) is a ritual, the rest none. */
unsigned char gDuelEffect_abGroupByEffectId[104] = {[35] = 4, [36] = 7, [74] = 12};
