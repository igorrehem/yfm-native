#ifndef MEMORIES_PC_FUSION_H
#define MEMORIES_PC_FUSION_H
/* Pure five-card planner. Slots identify materials, including duplicates.
 * A prefix is the player's actual pick order. No query changes game state. */
#define FUSION_HAND 5
/* modifier goes to ATK and DEF; defense_modifier to DEF beyond it (an equip
 * whose DEF bonus differs, duel_card.h). */
typedef struct { int id, type, attack, defense, modifier, terrain, defense_modifier; } FusionCard;
typedef struct { FusionCard card; int count, slots[FUSION_HAND], failed; } FusionLine;
typedef struct {
    FusionCard (*card)(int id);
    int (*fusion)(int a, int b);
    int (*equip)(int equipment, int monster);
    /* What `equipment` adds to `monster`, which already carries `modifier`.
     * NULL: the disc's +500 (+1000 for Megamorph, 657). */
    int (*bonus)(int equipment, int monster, int modifier);
    /* Both halves, over `bonus` when set: what `equipment` adds to ATK and
     * to DEF of a monster carrying `modifier` and `defense_modifier`. */
    void (*bonuses)(int equipment, int monster, int modifier, int defense_modifier, int *attack, int *defense);
} FusionRules;
int Fusion_Step(const FusionRules *, FusionCard first, FusionCard second, FusionCard *out);
int Fusion_Attack(FusionCard card);
int Fusion_Defense(FusionCard card);
/* The caps Fusion_Attack and Fusion_Defense clamp to (9999 each until set):
 * the duel's, which a mod's "limits" may move (tables.h). */
void Fusion_SetCaps(int attack, int defense);
/* Invalid/duplicate picks fail closed. Best ends in a successful combination;
 * ties consume fewer cards, then use the other stat, then leftmost order. */
void Fusion_Plan(const FusionRules *, const FusionCard hand[FUSION_HAND],
                 const int *prefix, int count, int defense, FusionLine *selected, FusionLine *best);
/* Whether the picks so far head cleanly (no failed step) for `target`, as
 * Fusion_Plan's best: 2 when they make it now, 1 when more picks can (the
 * shortest such line in *route), 0 when they cannot. */
int Fusion_Toward(const FusionRules *, const FusionCard hand[FUSION_HAND],
                  const int *prefix, int count, FusionCard target, FusionLine *route);
#endif
