/* What the game asks of the tower (src/pc/tower/tower.c), with the game's
 * bytes as plain variables: whether the tower is open ("unlock": always,
 * after_ending by the save's byte 0x3DE, the duelists' conditions), the
 * floor's rules only while its duel is the one being fought, its LP and
 * deck, the duelists' "tower" conditions and tower-only duelists, and the
 * progress beside the save: written, read back by a new save's load, kept
 * apart by duelist code, the other towers' sections kept, and carried by a
 * save state. */
#define _POSIX_C_SOURCE 200809L /* scratch.h: mkdtemp, lstat, kill */
#include "scratch.h"
#include "pc/tower/tower.h"
#include "pc/mods/json.h"
#include "pc/guest/state.h"
#include "pc/saves/save_slots.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#ifndef _WIN32
#include <unistd.h>
#endif
#include "pc/compat/fs.h"

/* --- the game's bytes and the port's services, as tower.c reaches them --- */

TowerState gTower;
unsigned char D_8009B26C, D_8009B368, gDuel_bOpponentID;
unsigned short gDuel_awPlayerDeck[0x340];     /* the running save, SaveDataState */
static unsigned char *save = (unsigned char *)gDuel_awPlayerDeck;

void Mods_Note(const char *id, const char *format, ...) { (void)id; (void)format; }
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { return index; }
int Mods_Active(int mod) { (void)mod; return 1; }
const char *Mods_Id(int mod) { (void)mod; return "t"; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

int Duelists_Valid(int duelist) { return duelist >= 1 && duelist <= 41; }
int Duelists_Named(const char *text) { return atoi(text) > 0 ? atoi(text) : -1; }
int Cards_Valid(int id) { return id >= 1 && id <= 722; }
int Cards_Named(const char *text) { return atoi(text); }
int Tables_TerrainNamed(const char *text) { return atoi(text) >= 1 && atoi(text) <= 6 ? atoi(text) : -1; }
/* The stage's leanings (tower_config.c): no folder, no pictures made. */
const char *Mods_Directory(int mod) { (void)mod; return NULL; }
int Paths_Contained(const char *relative) { return relative && relative[0] != '/' && !strstr(relative, ".."); }
int Duelists_BaseId(int duelist) { return duelist > 39 ? 1 : duelist; }
const char *Duelists_Name(int duelist) { (void)duelist; return "a duelist"; }
void Tower_MakeArt(TowerConfig *config) { (void)config; }
/* The duelists' conditions: "beat" is met by the save's first byte. */
int Duelists_ConditionsMet(const void *state, const char *beat, int wins, int story, const char *card, int copies)
{
    (void)wins; (void)story; (void)card; (void)copies;
    return !beat[0] || ((const unsigned char *)state)[0] != 0;
}
static unsigned char flags[256];
void Library_UpdateCardUsedFlag(int flag) { flags[(flag & 0x7FF) >> 3] |= (unsigned char)(0x80 >> (flag & 7)); }

int Log_Wanted(int channel) { (void)channel; return 0; }
void Log_Printf(int channel, const char *format, ...) { (void)channel; (void)format; }
static int notices;
void Menu_ShowNotice(const char *title, const char *text, const char *const *buttons, int count, int focus,
                     void (*done)(int, int *))
{
    (void)title; (void)text; (void)buttons; (void)count; (void)focus; (void)done;
    notices++;
}

static char user[SCRATCH_MAX];  /* scratch_dir(): removed again at exit */
static int slot = 0;
static unsigned tokens[SAVE_SLOT_COUNT] = {0x11111111, 0x22222222, 0x33333333};
int SaveMenu_CurrentSlot(void) { return slot; }
unsigned SaveSlots_Token(int at) { return at >= 0 && at < SAVE_SLOT_COUNT ? tokens[at] : 0; }
int SaveSlots_ReadToken(int at, unsigned *token) { *token = SaveSlots_Token(at); return 0; }
int Paths_User(char *out, size_t size, const char *relative)
{
    return snprintf(out, size, "%s/%s", user, relative) >= (int)size;
}
int Paths_MakeDirs(const char *path)
{
    return mkdir(path, 0755);
}

/* A save state's chunks, kept in memory: one at a time is enough here. */
struct MemoriesState { int loading; char tag[4][32]; unsigned char data[4][4096]; size_t size[4]; int count; };
int Memories_StateLoading(const MemoriesState *state) { return state->loading; }
int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count)
{
    int i;
    size_t at = 0, k;
    if (!state->loading) {
        i = state->count++;
        snprintf(state->tag[i], sizeof(state->tag[i]), "%s", tag);
        for (k = 0; k < count; k++) {
            memcpy(state->data[i] + at, fields[k].data, fields[k].size);
            at += fields[k].size;
        }
        state->size[i] = at;
        return 1;
    }
    for (i = 0; i < state->count; i++) {
        if (strcmp(state->tag[i], tag)) continue;
        for (k = 0; k < count; k++) {
            memcpy(fields[k].data, state->data[i] + at, fields[k].size);
            at += fields[k].size;
        }
        return 1;
    }
    return 0;
}

/* --- the cases ------------------------------------------------------------------ */

static JsonDocument *documents[32];
static int document_count;

static void tower_of(const char *text)
{
    char error[256];
    JsonDocument *document = Json_Parse(text, error, sizeof(error));
    assert(document);
    assert(document_count < 32);
    documents[document_count++] = document;
    Tower_Reset();
    Tower_Read("t", NULL, Json_Root(document));
    assert(Tower_Config());
}

static void set_code(unsigned code) { memcpy(save + 0x334, &code, sizeof(code)); }

static void unlocks(void)
{
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 1}]}}");
    memset(save, 0, sizeof(gDuel_awPlayerDeck));
    assert(Tower_Unlocked());
    tower_of("{\"tower\": {\"unlock\": \"after_ending\", \"floors\": [{\"duelist\": 1}]}}");
    assert(!Tower_EndingSeen(save) && !Tower_Unlocked());
    save[0x3DE] = 1;   /* Main_RunCredits: field_3DE |= 3 */
    assert(Tower_EndingSeen(save) && Tower_Unlocked());
    save[0x3DE] = 0;
    tower_of("{\"tower\": {\"unlock\": {\"beat\": \"7\", \"after_ending\": true}, \"floors\": [{\"duelist\": 1}]}}");
    assert(!Tower_Unlocked());
    save[0] = 1;                         /* beaten */
    assert(!Tower_Unlocked());           /* the ending too */
    save[0x3DE] = 2;
    assert(Tower_Unlocked());
    tower_of("{\"tower\": {\"unlock\": \"later\", \"floors\": [{\"duelist\": 1}]}}");
    assert(!Tower_Unlocked());
    Tower_Reset();
    assert(!Tower_Unlocked());
}

static void rules(void)
{
    unsigned short deck[TOWER_DECK];
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 1}, {\"duelist\": 2, \"no_fusions\": true, \"no_equips\": true,"
             " \"life_points\": {\"opponent\": 300}, \"deck\": {\"5\": 40}}]}}");
    memset(&gTower, 0, sizeof(gTower));
    D_8009B26C = 3 | 0xC0;
    D_8009B368 = TOWER_MODE;
    /* Not armed: nothing. */
    assert(!Tower_DuelRules() && Tower_StartingLifePoints(1, 8000) == 8000 && !Tower_OpponentDeck(deck));
    gTower.armed = 2;
    gTower.rules = TOWER_RULE_NO_FUSIONS | TOWER_RULE_NO_EQUIPS;
    gDuel_bOpponentID = 9;                /* another opponent: another duel (a 2P one, say) */
    assert(!Tower_DuelRules());
    gDuel_bOpponentID = 2;
    assert(Tower_DuelRules() == (TOWER_RULE_NO_FUSIONS | TOWER_RULE_NO_EQUIPS));
    assert(Tower_Refuses(TOWER_RULE_NO_FUSIONS, 1, 2, 3) && Tower_Refuses(TOWER_RULE_NO_EQUIPS, 4, 5, 5));
    assert(Tower_StartingLifePoints(0, 8000) == 8000 && Tower_StartingLifePoints(1, 8000) == 300);
    assert(Tower_OpponentDeck(deck) && deck[0] == 5 && deck[39] == 5);
    /* In its 3D battle (mode 1) too. */
    D_8009B26C = 1 | 0xC0;
    assert(Tower_DuelRules());
    /* A duel someone else armed (its own way back), or another screen: no
     * rule, though `armed` was left (a jump out of the tower's duel). */
    D_8009B368 = 6;
    assert(!Tower_DuelRules() && !Tower_Refuses(TOWER_RULE_NO_FUSIONS, 1, 2, 3));
    assert(Tower_StartingLifePoints(1, 8000) == 8000 && !Tower_OpponentDeck(deck));
    D_8009B368 = TOWER_MODE;
    D_8009B26C = 6 | 0xC0;
    assert(!Tower_DuelRules());
    /* Floor 1 has no rules, LP or deck of its own. */
    D_8009B26C = 3 | 0xC0;
    gTower.armed = 1;
    gDuel_bOpponentID = 1;
    gTower.rules = 0;
    assert(!Tower_DuelRules() && Tower_StartingLifePoints(0, 7000) == 7000 && !Tower_OpponentDeck(deck));
    gTower.armed = 0;
}

static void duelists(void)
{
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 40}, {\"duelist\": 2, \"reward\": {\"unlock_duelist\": [41, 9]}},"
             " {\"duelist\": 3}]}}");
    memset(&gTower, 0, sizeof(gTower));
    memset(save, 0, sizeof(gDuel_awPlayerDeck));
    Tower_Frame();
    assert(!Tower_ConditionMet(1) && !Tower_ConditionMet(0) && !Tower_FreesDuelist(40) && !Tower_FreesDuelist(41));
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 0, 1);
    assert(Tower_ConditionMet(1) && !Tower_ConditionMet(2) && Tower_FreesDuelist(40) && !Tower_FreesDuelist(41));
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 1, 1);
    assert(Tower_ConditionMet(2) && Tower_FreesDuelist(41) && !Tower_FreesDuelist(3));
    /* The reward's disc duelists: their Free Duel flag (0x6E0 + id), not the
     * campaign's 0x1F + id. */
    memset(flags, 0, sizeof(flags));
    Tower_UnlockRetailDuelists(&Tower_Config()->floors[1]);
    assert(flags[(0x6E0 + 9) >> 3] & (0x80 >> ((0x6E0 + 9) & 7)));
    assert(!(flags[(0x1F + 9) >> 3] & (0x80 >> ((0x1F + 9) & 7))));
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 2, 1);
    assert(Tower_ConditionMet(0) && Tower_ConditionMet(3));
    /* No tower (its mod off): nothing is met. */
    Tower_Reset();
    assert(!Tower_ConditionMet(1) && !Tower_FreesDuelist(40));
}

/* "unlock_opponent", "drops", "save_states" and "cheats" in the game. */
static void guards(void)
{
    char why[256];
    /* A tower-only opponent (40) beaten on a floor that says false stays
     * hidden; a disc opponent (9) on one that says true gets its flag. */
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 40, \"unlock_opponent\": false},"
             " {\"duelist\": 9, \"unlock_opponent\": true}, {\"duelist\": 3}]}}");
    memset(&gTower, 0, sizeof(gTower));
    memset(save, 0, sizeof(gDuel_awPlayerDeck));
    Tower_Frame();
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 0, 1);
    assert(!Tower_FreesDuelist(40));
    memset(flags, 0, sizeof(flags));
    Tower_UnlockRetailDuelists(&Tower_Config()->floors[1]);
    assert(flags[(0x6E0 + 9) >> 3] & (0x80 >> ((0x6E0 + 9) & 7)));
    memset(flags, 0, sizeof(flags));
    Tower_UnlockRetailDuelists(&Tower_Config()->floors[2]);   /* by default a disc opponent is not */
    assert(!(flags[(0x6E0 + 3) >> 3] & (0x80 >> ((0x6E0 + 3) & 7))));

    /* The defaults: drops 1, states and cheats as the player has them. */
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 2}]}}");
    memset(&gTower, 0, sizeof(gTower));
    D_8009B26C = TOWER_MODE | 0xC0;
    D_8009B368 = 0;
    assert(Tower_Active() && !Tower_Guard(TOWER_GUARD_SAVE_STATE, 1, why, sizeof(why)) &&
           !Tower_Guard(TOWER_GUARD_CHEAT, 1, why, sizeof(why)) && !Tower_CheatsOff());
    assert(Tower_CardDrops(99) == 99);   /* the tower's screen is no duel */
    D_8009B26C = 3 | 0xC0;
    D_8009B368 = TOWER_MODE;
    gTower.armed = 1;
    gDuel_bOpponentID = 2;
    assert(Tower_CardDrops(99) == 1);
    tower_of("{\"tower\": {\"drops\": \"player\", \"floors\": [{\"duelist\": 2}]}}");
    assert(Tower_CardDrops(99) == 99);
    tower_of("{\"tower\": {\"drops\": 7, \"floors\": [{\"duelist\": 2}]}}");
    assert(Tower_CardDrops(99) == 7);

    /* Turned off: refused in the tower's duel and on its screen, told once
     * a call; not outside it. */
    tower_of("{\"tower\": {\"save_states\": false, \"cheats\": false, \"floors\": [{\"duelist\": 2}]}}");
    notices = 0;
    assert(Tower_Guard(TOWER_GUARD_SAVE_STATE, 1, why, sizeof(why)) && strstr(why, "save states off"));
    assert(Tower_Guard(TOWER_GUARD_LOAD_STATE, 0, why, sizeof(why)) && notices == 1);
    assert(Tower_Guard(TOWER_GUARD_CHEAT, 1, why, sizeof(why)) && Tower_CheatsOff());
    assert(Tower_Guard(TOWER_GUARD_JUMP, 1, why, sizeof(why)) && strstr(why, "jump or a restart") && notices == 3);
    gTower.armed = 0;
    D_8009B26C = TOWER_MODE | 0xC0;   /* the tower's screen, its stories */
    assert(Tower_Guard(TOWER_GUARD_SAVE_STATE, 0, why, sizeof(why)) && Tower_CheatsOff());
    assert(!Tower_Guard(TOWER_GUARD_JUMP, 0, why, sizeof(why)));   /* a jump from the screen is banked as LEAVE is */
    D_8009B26C = 8 | 0xC0;    /* the title's menus: none of it */
    assert(!Tower_Guard(TOWER_GUARD_SAVE_STATE, 1, why, sizeof(why)) && !Tower_Guard(TOWER_GUARD_JUMP, 1, why, sizeof(why)));
    assert(!Tower_Active() && !Tower_CheatsOff() && notices == 3);
    /* "save_states": false: a state loaded outside the tower brings no other
     * climb back (Tower_Frame keeps it across the load). */
    memset(&gTower, 0, sizeof(gTower));
    Tower_Frame();                    /* this save's climb */
    gTower.progress.floor = 2;
    Tower_Frame();
    {
        MemoriesState state;
        memset(&state, 0, sizeof(state));
        state.loading = 1;
        gTower.progress.floor = 0;    /* the state's older climb */
        Tower_State(&state);
        Tower_Frame();
        assert(gTower.progress.floor == 2);
    }
    Tower_Reset();
    D_8009B26C = TOWER_MODE | 0xC0;
    assert(!Tower_Active() && !Tower_Guard(TOWER_GUARD_SAVE_STATE, 1, why, sizeof(why)));   /* no tower: no mod */
    D_8009B26C = 0;
    D_8009B368 = 0;
    gDuel_bOpponentID = 0;
}

static int exists(const char *relative)
{
    char path[1024];
    FILE *file;
    snprintf(path, sizeof(path), "%s/%s", user, relative);
    file = fopen(path, "r");
    if (file) fclose(file);
    return file != NULL;
}

static void beside_the_save(void)
{
    MemoriesState state;
    char path[1024];
    FILE *file;
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 1, \"checkpoint\": true}, {\"duelist\": 2}, {\"duelist\": 3}]}}");
    memset(&gTower, 0, sizeof(gTower));
    memset(save, 0, sizeof(gDuel_awPlayerDeck));
    set_code(0xC0DE);
    Tower_Frame();
    assert(gTower.progress.owner == 0xC0DE && gTower.progress.tower == Tower_Identity(Tower_Config()));
    /* Nothing climbed: no file. */
    slot = 0;
    Tower_SaveWritten(save);
    assert(!exists("tower/11111111.txt"));
    /* Floor 1 won, saved to slot 0; another tower's section already there
     * (its mod off this run) is kept. */
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 0, 1);
    snprintf(path, sizeof(path), "%s/tower", user);
    Paths_MakeDirs(path);
    snprintf(path, sizeof(path), "%s/tower/11111111.txt", user);
    file = fopen(path, "w");
    fputs("tower other\nidentity 00000009\nfloor 2\nend\n", file);
    fclose(file);
    gTower.progress.floor = 1;
    {   /* loaded first, so its foreign section is known */
        TowerProgress kept = gTower.progress;
        Tower_SaveLoaded(save);       /* the file has no section of ours: a fresh climb */
        assert(gTower.progress.floor == 0);
        gTower.progress = kept;
    }
    Tower_SaveWritten(save);
    assert(exists("tower/11111111.txt"));
    /* NEW GAME: another code, nothing climbed. */
    set_code(0xBEEF);
    Tower_Frame();
    assert(gTower.progress.floor == 0 && !Tower_FloorCleared(&gTower.progress, 0));
    /* The save loaded again: its floor and checkpoint back. */
    set_code(0xC0DE);
    Tower_SaveLoaded(save);
    assert(gTower.progress.floor == 1 && gTower.progress.checkpoint == 1 && Tower_FloorCleared(&gTower.progress, 0));
    /* A save state carries the other towers' lines, the rest is game data. */
    memset(&state, 0, sizeof(state));
    Tower_State(&state);
    assert(state.count == 3 && !strcmp(state.tag[0], "tower-loaded") &&
           strstr((const char *)state.data[2], "tower other"));
    state.loading = 1;
    Tower_SaveLoaded(save);
    Tower_State(&state);
    /* Saved again: both sections. */
    Tower_SaveWritten(save);
    file = fopen(path, "r");
    {
        char text[1024];
        size_t n = fread(text, 1, sizeof(text) - 1, file);
        text[n] = 0;
        assert(strstr(text, "tower t\n") && strstr(text, "tower other\nidentity 00000009\nfloor 2\nend\n"));
        assert(strstr(text, "floor 1\ncheckpoint 1\n"));
    }
    fclose(file);
    /* The slot's file is of the save it held before (another code): none of
     * its progress, and a slot no save goes with any more loses its file. */
    set_code(0xF00D);
    Tower_SaveLoaded(save);
    assert(gTower.progress.floor == 0);
    tokens[0] = 0x44444444;
    slot = 0;
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 0, 1);
    Tower_SaveWritten(save);
    assert(exists("tower/44444444.txt") && !exists("tower/11111111.txt"));
    /* Saved once while the tower's mod is off (a new token, as every write
     * has): the climb goes with it, and is back with the mod. */
    Tower_Reset();
    tokens[0] = 0x55555555;
    Tower_SaveWritten(save);
    assert(exists("tower/55555555.txt") && !exists("tower/44444444.txt"));
    tower_of("{\"tower\": {\"floors\": [{\"duelist\": 1, \"checkpoint\": true}, {\"duelist\": 2}, {\"duelist\": 3}]}}");
    Tower_SaveLoaded(save);
    assert(gTower.progress.floor == 1 && Tower_FloorCleared(&gTower.progress, 0));
    /* A state knows the save loaded last, the mod off too: loaded, a save
     * carries that save's climb over. */
    Tower_Reset();
    memset(&state, 0, sizeof(state));
    Tower_State(&state);
    assert(state.count == 1 && !strcmp(state.tag[0], "tower-loaded"));
    state.loading = 1;
    Tower_State(&state);
    tokens[0] = 0x66666666;
    Tower_SaveWritten(save);
    assert(exists("tower/66666666.txt") && !exists("tower/55555555.txt"));
    /* A state from before that (no such chunk): nothing is carried over. */
    memset(&state, 0, sizeof(state));
    state.loading = 1;
    Tower_State(&state);
    tokens[0] = 0x77777777;
    Tower_SaveWritten(save);
    assert(!exists("tower/77777777.txt"));
    /* "on_leave": "checkpoint": a save written mid-climb (the title's SAVE
     * after a jump out, say) keeps the climb at the checkpoint, while the
     * climb in memory goes on; loaded, that is where it is. */
    tower_of("{\"tower\": {\"on_leave\": \"checkpoint\", \"floors\": [{\"duelist\": 1, \"checkpoint\": true},"
             " {\"duelist\": 2}, {\"duelist\": 3}, {\"duelist\": 4}]}}");
    memset(&gTower, 0, sizeof(gTower));
    set_code(0xF00D);
    Tower_Frame();
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 0, 1);
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 1, 1);
    Tower_ApplyResult(Tower_Config(), &gTower.progress, 2, 1);
    assert(gTower.progress.floor == 3 && gTower.progress.checkpoint == 1);
    tokens[0] = 0x88888888;
    Tower_SaveWritten(save);
    assert(gTower.progress.floor == 3);
    Tower_SaveLoaded(save);
    assert(gTower.progress.floor == 1 && gTower.progress.checkpoint == 1 && Tower_FloorCleared(&gTower.progress, 2));
}

int main(void)
{
    int i;
    if (!scratch_dir(user, sizeof(user), "memories-tower")) {
        fprintf(stderr, "tower game: no scratch folder\n");
        return 1;
    }
    unlocks();
    rules();
    duelists();
    guards();
    beside_the_save();
    Tower_Reset();
    for (i = 0; i < document_count; i++) Json_Free(documents[i]);
    printf("tower game: ok\n");
    return 0;
}
