#include "../types.h"
#include "duel_check_ritual.h"
#define D_8009B1D5_IS_ABSOLUTE_SCALAR
#include "duel_side_state.h"
#include "duel_card.h"
#include "card_constants.h"
#include "duel_card_layout.h"
#include "duel_grid.h"
#ifdef MEMORIES_PC
#include "pc/cards/cards.h"
#include "pc/cards/tables.h"
#include "duel_action_lock.h"
#include "duel_scene_card_placement.h"
#include "duel_card_record_lifecycle.h"
#include "duel_screen_tables.h"
#include "display_object.h"
#include "duel_hand.h"
#include <string.h>

s32 Duel_RitualPlayed(void)
{
    /* D_8009B150 is the card the effect scene plays (func_80019608). */
    s32 played = D_8009B150 & CARD_ID_FIELD_MASK;
    return played != gDuel_wEffectCardID && Cards_EffectId(played) == gDuel_wEffectCardID ? played
                                                                                         : gDuel_wEffectCardID;
}

/* Whether the disc's ritual table has a recipe for this card. */
static s32 disc_recipe(s32 id)
{
    u16 *q;
    for (q = gDuel_awRitualData; q[0] != 0; q += DUEL_RITUAL_RECIPE_HALFWORD_COUNT)
        if (q[0] == id) return 1;
    return 0;
}

static s32 printed_attack(s32 id)
{
    return (gDuel_adwCardStats[id - 1] & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
}

static s32 printed_defense(s32 id)
{
    return ((gDuel_adwCardStats[id - 1] >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
}

/* Whether a monster meets one tribute's requirements (all of them). */
static s32 meets(const TablesRitualRequirement *r, s32 id)
{
    s32 attack = printed_attack(id), defense = printed_defense(id);
    if (r->card && id != r->card && Cards_BaseId(id) != r->card) return 0;
    if (r->type >= 0 && Cards_Type(id) != r->type) return 0;
    if (r->fusion_group && !Cards_InFusionGroup(id, r->fusion_group)) return 0;
    if (attack < r->min_attack || defense < r->min_defense) return 0;
    if (r->max_attack >= 0 && attack > r->max_attack) return 0;
    if (r->max_defense >= 0 && defense > r->max_defense) return 0;
    if (r->min_level >= 0 && Cards_Level(id) < r->min_level) return 0;
    if (r->max_level >= 0 && Cards_Level(id) > r->max_level) return 0;
    if (r->defense_gt_attack && defense <= attack) return 0;
    return 1;
}

/* A narrower tribute is placed first: a named card before any rule, then
 * the one with more conditions. */
static s32 specificity(const TablesRitualRequirement *r)
{
    return (r->card ? 100 : 0) + (r->type >= 0) + (r->fusion_group != 0) + (r->min_attack != 0) +
           (r->min_defense != 0) + (r->max_attack >= 0) + (r->max_defense >= 0) + (r->min_level >= 0) +
           (r->max_level >= 0) + (r->defense_gt_attack != 0);
}

static DuelRitualMatch last;     /* the last check's match */
static DuelRitualMatch active;   /* DuelEffect_ApplyRitual's, under way */
/* In the game's own variables: saved in a state, and below 4 GB. */
static DisplayObject stand_in;

/* The tributes of one of the disc's kind of ritual: three on the field. */
static void remember_field(DuelCardRecord *const *found, s32 result)
{
    s32 j;
    memset(&last, 0, sizeof(last));
    last.count = DUEL_RITUAL_TRIBUTE_COUNT;
    for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
        last.record[j] = (s16)(found[j] - D_801A7AD8);
        last.hand_slot[j] = -1;
    }
    last.zone = last.record[1];
    last.result = (s16)result;
}

static s32 field_objects(const DuelRitualMatch *m, void *G32 *objects)
{
    s32 j, n = 0;
    for (j = 0; j < m->count; j++)
        if (m->hand_slot[j] < 0) objects[n++] = D_801A7AD8[m->record[j]].object;
    return n;
}

/* The three display objects the output holds, which the ritual's 3D effect
 * flies into its portal: the field's tributes, again from the first when
 * there are fewer than three. With none (every tribute in the hand) it is
 * an object of the port's own, never drawn, that stands where the effect
 * takes a card to (0, -96, 0) and on the side of the field whose ritual it
 * is, so the effect, interpreted too, goes straight on. */
static void fill_out(const DuelRitualMatch *m, DuelRitualResult *out)
{
    void *G32 objects[DUEL_RITUAL_TRIBUTE_MAX];
    s32 i, n = field_objects(m, objects);
    if (n == 0) {
        s32 zone = m->zone >= 0 ? m->zone : (D_8009B1D5 != 0 ? DUEL_CARD_SIDE_RECORD_COUNT : 0) + 5;
        memset(&stand_in, 0, sizeof(stand_in));
        *(s16 *)&stand_in.field_30.h.field_32 = -96;
        stand_in.field_34.h.field_34 = (s16)D_800908A0[zone * 2 + 1] >= 0 ? 0 : -1;
        objects[n++] = &stand_in;
    }
    for (i = 0; i < DUEL_RITUAL_TRIBUTE_COUNT; i++)
        out->tribute_objects[i] = objects[i % n];
    out->field_0C = 0;
}

/* --- a ritual of one to five tributes, from the field and/or the hand ---
 *
 * The candidates are the side's monsters on the field (records 5-9 of its
 * fifteen) and, as the rule allows, the monsters in its hand (records 0-4,
 * whose slot holds a card). The ritual card is no monster, so it is never
 * its own tribute, in the hand (the CPU's look before it plays it) or not.
 * Every distinct assignment is tried, the narrowest tribute first; among
 * the ones that do, the tribute taken is, slot by slot in that order: the
 * card itself before a copy of it, with "both" one in the hand before one
 * on the field (the hand is dealt again; a field took turns to build), the
 * weakest as the disc-kind rituals with conditions choose it, then the
 * first. The result goes to the middle field tribute's zone (the second of
 * three, as on the disc), or with tributes only from the hand to the first
 * free monster zone; with none free the ritual cannot take place. */
static s32 candidate_id(const RitualSearch *x, s32 c) { return D_801A7AD8[x->record[c]].card_id; }

static s32 better(const RitualSearch *x)
{
    s32 i;
    for (i = 0; i < x->rule.count; i++) {
        s32 slot = x->order[i], a = x->pick[slot], b = x->best[slot];
        s32 card = x->rule.requirements[slot].card;
        s32 a_id = candidate_id(x, a), b_id = candidate_id(x, b);
        if (card && (a_id == card) != (b_id == card)) return a_id == card;
        if (x->rule.from == TABLES_TRIBUTES_BOTH && (x->hand_slot[a] >= 0) != (x->hand_slot[b] >= 0))
            return x->hand_slot[a] >= 0;
        if (x->prefer_defense) {
            if (printed_defense(a_id) != printed_defense(b_id)) return printed_defense(a_id) < printed_defense(b_id);
            if (printed_attack(a_id) != printed_attack(b_id)) return printed_attack(a_id) < printed_attack(b_id);
        } else {
            if (printed_attack(a_id) != printed_attack(b_id)) return printed_attack(a_id) < printed_attack(b_id);
            if (printed_defense(a_id) != printed_defense(b_id)) return printed_defense(a_id) < printed_defense(b_id);
        }
        if (a != b) return a < b;
    }
    return 0;
}

static void search(RitualSearch *x, s32 depth, u32 used)
{
    s32 c, slot;
    if (depth == x->rule.count) {
        s32 j, on_field = 0;
        for (j = 0; j < x->rule.count; j++) on_field += x->hand_slot[x->pick[j]] < 0;
        if (!on_field && x->free_zone < 0) return;
        if (!x->found || better(x)) {
            memcpy(x->best, x->pick, sizeof(x->best));
            x->found = 1;
        }
        return;
    }
    slot = x->order[depth];
    for (c = 0; c < x->candidates; c++) {
        if (used & (1u << c) || !meets(&x->rule.requirements[slot], candidate_id(x, c))) continue;
        x->pick[slot] = c;
        search(x, depth + 1, used | (1u << c));
    }
}

static s32 extended_match(const TablesRitualRule *rule, DuelRitualResult *out)
{
    RitualSearch x;
    s32 side = D_8009B1D5 != 0;
    s32 base = side * DUEL_CARD_SIDE_RECORD_COUNT;
    s32 i, j, fields[DUEL_RITUAL_TRIBUTE_MAX], on_field = 0;

    memset(&x, 0, sizeof(x));
    x.rule = *rule;
    x.free_zone = -1;
    if (rule->from != TABLES_TRIBUTES_HAND)
        for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++)
            if (D_801A7AD8[base + DUEL_FIELD_ROW_SIZE + i].flags & DUEL_CARD_FLAG_OCCUPIED) {
                x.record[x.candidates] = (s16)(base + DUEL_FIELD_ROW_SIZE + i);
                x.hand_slot[x.candidates++] = -1;
            }
    if (rule->from != TABLES_TRIBUTES_FIELD)
        for (i = 0; i < HAND_SIZE; i++) {
            DuelCardRecord *card = &D_801A7AD8[base + i];
            if (D_800E9FF0[side].hand[i] >= 0 && (card->flags & DUEL_CARD_FLAG_OCCUPIED) &&
                Cards_IsMonsterType(Cards_Type(card->card_id))) {
                x.record[x.candidates] = (s16)(base + i);
                x.hand_slot[x.candidates++] = (s8)i;
            }
        }
    /* The first free monster zone, left to right as the side sees its
     * field (its block of the grid: its monsters are the third row). */
    for (i = 0; i < DUEL_FIELD_ROW_SIZE && x.free_zone < 0; i++) {
        s32 record = D_800907D8[side * DUEL_FIELD_SIDE_GRID_SLOT_COUNT + 2 * DUEL_FIELD_ROW_SIZE + i];
        if (!(D_801A7AD8[record].flags & DUEL_CARD_FLAG_OCCUPIED)) x.free_zone = record;
    }
    for (j = 0; j < rule->count; j++) x.order[j] = j;
    for (i = 0; i < rule->count - 1; i++)
        for (j = i + 1; j < rule->count; j++)
            if (specificity(&rule->requirements[x.order[j]]) > specificity(&rule->requirements[x.order[i]])) {
                s32 swap = x.order[i]; x.order[i] = x.order[j]; x.order[j] = swap;
            }
    x.prefer_defense = printed_defense(rule->result) > printed_attack(rule->result);
    search(&x, 0, 0);

    memset(&last, 0, sizeof(last));
    if (!x.found) return 0;
    last.count = rule->count;
    last.extended = 1;
    last.result = (s16)rule->result;
    for (j = 0; j < rule->count; j++) {
        last.record[j] = x.record[x.best[j]];
        last.hand_slot[j] = x.hand_slot[x.best[j]];
        if (last.hand_slot[j] < 0) fields[on_field++] = last.record[j];
    }
    last.zone = (s16)(on_field ? fields[on_field / 2] : x.free_zone);
    if (out != 0) fill_out(&last, out);
    return rule->result;
}

DuelRitualFlight *Duel_RitualFlight(void)
{
    static DuelRitualFlight flight;
    return &flight;
}

void Duel_RitualBegin(void) { active = last; }

const DuelRitualMatch *Duel_RitualActive(void) { return active.count ? &active : 0; }

void Duel_RitualEnd(void) { memset(&active, 0, sizeof(active)); }

s32 Duel_RitualFieldObjects(void *G32 *objects)
{
    return active.count ? field_objects(&active, objects) : -1;
}

s32 Duel_RitualSpend(void)
{
    s32 j, zone = active.zone, side = D_8009B1D5 != 0, hand_record = -1, on_field = 0;
    for (j = 0; j < active.count; j++) {
        DuelCardRecord *card = &D_801A7AD8[active.record[j]];
        if (active.hand_slot[j] < 0) {
            DuelCard_DeactivateRecord(card);
            on_field++;
            continue;
        }
        /* A hand card leaves as a played one does (its slot -1); its
         * record, which keeps the card until the next draw sets the hand
         * up again, is emptied as well, and any picture it still has
         * released with it. */
        if (hand_record < 0) hand_record = active.record[j];
        D_800E9FF0[side].hand[active.hand_slot[j]] = -1;
        if (card->object && D_800EA030[active.hand_slot[j]].object == (u8 *)card->object)
            D_800EA030[active.hand_slot[j]].object = 0;
        DuelCard_DeactivateRecord(card);
    }
    /* With every tribute from the hand the result takes an empty zone, and
     * the deck card of the first of them: the effect writes the result's id
     * into the zone's deck card and sets the zone up from it, as it does
     * with the field tribute whose zone it takes. */
    if (!on_field && hand_record >= 0) D_801A7AD8[zone].data = D_801A7AD8[hand_record].data;
    Duel_RitualEnd();
    return zone;
}
#endif

s32 Duel_CheckRitual(DuelRitualResult *out, s32 ritualId)
{
    DuelCardRecord *found[DUEL_RITUAL_TRIBUTE_COUNT];
    DuelCardRecord *cands[DUEL_FIELD_ROW_SIZE];
    DuelCardRecord *card;
#ifndef MEMORIES_PC
    DuelCardRecord **first;
    DuelCardRecord **dst;
#endif
    DuelCardRecord **w;
    DuelCardRecord *c;
    u16 *p;
#ifndef MEMORIES_PC
    u16 *q;
#endif
    s32 i;
    s32 j;
#ifdef MEMORIES_PC
    TablesRitualRequirement requirements[DUEL_RITUAL_TRIBUTE_COUNT];
    TablesRitualRule rule;
    u16 conditional_result = 0;
    /* The ritual under way answers its 3D effect (Duel_RitualBegin). */
    if (active.count && out != 0) {
        fill_out(&active, out);
        return active.result;
    }
    memset(&last, 0, sizeof(last));
    /* A card played with another's effect (a copy, or "effect"), played or
     * in the AI's hand, without a recipe of its own is that card's ritual. */
    if (ritualId != Cards_EffectId(ritualId) && !Tables_HasRitual(ritualId) && !disc_recipe(ritualId))
        ritualId = Cards_EffectId(ritualId);
    if (Tables_RitualRule(ritualId, &rule)) return extended_match(&rule, out);
    if (Tables_RitualRequirements(ritualId, requirements, &conditional_result)) {
        int match[DUEL_RITUAL_TRIBUTE_COUNT] = {-1, -1, -1};
        int order[DUEL_RITUAL_TRIBUTE_COUNT] = {0, 1, 2};
        int narrowness[DUEL_RITUAL_TRIBUTE_COUNT];
        int a, b, d, x, y;
        i = DUEL_FIELD_ROW_SIZE;
        if (D_8009B1D5 != 0) i = DUEL_CARD_SIDE_RECORD_COUNT + DUEL_FIELD_ROW_SIZE;
        c = &D_801A7AD8[i];
        for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++)
            cands[i] = (c[i].flags & DUEL_CARD_FLAG_OCCUPIED) ? &c[i] : 0;

        /* Decide the tribute slots in specificity order. A named card is
         * always reserved before a broad rule; otherwise the rule with more
         * conditions is narrower. This makes a broad slot unable to consume
         * the only monster a specific slot needs. */
        for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) narrowness[j] = specificity(&requirements[j]);
        for (x = 0; x < DUEL_RITUAL_TRIBUTE_COUNT - 1; x++)
            for (y = x + 1; y < DUEL_RITUAL_TRIBUTE_COUNT; y++)
                if (narrowness[order[y]] > narrowness[order[x]]) {
                    int swap = order[x]; order[x] = order[y]; order[y] = swap;
                }

        /* Try every distinct assignment. Among all valid assignments, compare
         * slots in the specificity order above. The ritual result decides
         * what "weakest" means: a DEF-dominant result spends the lowest DEF
         * first, while an ATK-dominant (or tied) result spends the lowest ATK
         * first. The other printed stat and then field position break ties.
         * Thus a specific-card slot is protected before this economy rule. */
        {
            int result_stats = gDuel_adwCardStats[conditional_result - 1];
            int result_attack = (result_stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
            int result_defense = ((result_stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
            int prefer_defense = result_defense > result_attack;
        for (a = 0; a < DUEL_FIELD_ROW_SIZE; a++) {
            for (b = 0; b < DUEL_FIELD_ROW_SIZE; b++) {
                if (b == a) continue;
                for (d = 0; d < DUEL_FIELD_ROW_SIZE; d++) {
                    int slots[DUEL_RITUAL_TRIBUTE_COUNT] = {a, b, d};
                    int ok = d != a && d != b;
                    if (!ok) continue;
                    for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT && ok; j++) {
                        card = cands[slots[j]];
                        if (!card) { ok = 0; break; }
                        if (!meets(&requirements[j], card->card_id)) ok = 0;
                    }
                    if (ok) {
                        int better = match[0] < 0;
                        for (x = 0; x < DUEL_RITUAL_TRIBUTE_COUNT && !better && match[0] >= 0; x++) {
                            int slot = order[x];
                            int new_id = cands[slots[slot]]->card_id;
                            int old_id = cands[match[slot]]->card_id;
                            int new_stats = gDuel_adwCardStats[new_id - 1];
                            int old_stats = gDuel_adwCardStats[old_id - 1];
                            int new_def = ((new_stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            int old_def = ((old_stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            int new_atk = (new_stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            int old_atk = (old_stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            if (prefer_defense) {
                                if (new_def != old_def) { better = new_def < old_def; break; }
                                if (new_atk != old_atk) { better = new_atk < old_atk; break; }
                            } else {
                                if (new_atk != old_atk) { better = new_atk < old_atk; break; }
                                if (new_def != old_def) { better = new_def < old_def; break; }
                            }
                            if (slots[slot] != match[slot]) { better = slots[slot] < match[slot]; break; }
                        }
                        if (better) {
                            match[0] = a; match[1] = b; match[2] = d;
                        }
                    }
                }
            }
        }
        }
        if (match[0] >= 0) {
            for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) found[j] = cands[match[j]];
            remember_field(found, conditional_result);
            if (out != 0) {
                for (i = 0; i < DUEL_RITUAL_TRIBUTE_COUNT; i++)
                    out->tribute_objects[i] = found[i]->object;
                out->field_0C = 0;
            }
            return conditional_result;
        }
        return 0;
    }
#endif
#ifdef MEMORIES_PC
    /* A mod's recipe, laid out as the disc's table is, comes first. */
    u16 own[DUEL_RITUAL_RECIPE_HALFWORD_COUNT + 1];
    s32 ruled = Tables_Ritual(ritualId, own);

    if (ruled == 0) {
        return 0;
    }
    p = ruled > 0 ? own : gDuel_awRitualData;
#else
    p = gDuel_awRitualData;
#endif
    while (1) {
        if (p[0] == 0) {
            return 0;
        }
        if (p[0] == ritualId) {
            break;
        }
        p += DUEL_RITUAL_RECIPE_HALFWORD_COUNT;
    }

    i = DUEL_FIELD_ROW_SIZE;
    if (D_8009B1D5 != 0) {
        i = DUEL_CARD_SIDE_RECORD_COUNT + DUEL_FIELD_ROW_SIZE;
    }
    c = &D_801A7AD8[i];
    i = 0;
    w = cands;
    for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
        *w = 0;
        if (c->flags & DUEL_CARD_FLAG_OCCUPIED) {
            *w = c;
        }
        w++;
        c++;
    }

    p++;
#ifdef MEMORIES_PC
    /* A copy of a tribute monster counts as it; a mod's recipe may also
       name the copy itself. Every tribute takes a monster that is exactly
       it first, and only then one that is a copy of it: taken in the
       recipe's order, a retail tribute could take the very copy a later
       one names while the retail monster stays on the field. */
    {
        s32 pass;

        for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
            found[j] = 0;
        }
        for (pass = 0; pass < 2; pass++) {
            for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
                if (found[j] != 0) {
                    continue;
                }
                for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
                    card = cands[i];
                    if (card != 0 && (pass == 0 ? card->card_id == p[j] :
                                      Cards_BaseId(card->card_id) == p[j])) {
                        found[j] = card;
                        cands[i] = 0;
                        break;
                    }
                }
            }
        }
        for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
            if (found[j] == 0) {
                return 0;
            }
        }
    }
#else
    j = 0;
    first = cands;
    dst = found;
    q = p;
    for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
        for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
            card = (c = first[i]);
            if (card != 0 && card->card_id == q[0]) {
                goto matched;
            }
        }
        return 0;
matched:
        *dst++ = card;
        first[i] = 0;
        q++;
    }
#endif

#ifdef MEMORIES_PC
    remember_field(found, p[DUEL_RITUAL_TRIBUTE_COUNT]);
#endif
    if (out != 0) {
        for (i = 0; i < DUEL_RITUAL_TRIBUTE_COUNT; i++) {
            out->tribute_objects[i] = found[i]->object;
        }
        out->field_0C = 0;
    }
    return p[DUEL_RITUAL_TRIBUTE_COUNT];
}
