/* A mod's "tower" as read, and a save's progress in it
 * (src/pc/tower/tower_config.c): real manifests through the real JSON
 * reader. What is checked without a game: the defaults, each key landing
 * where the screen looks for it, the notes a mistake raises (and what a
 * mistake leaves of the tower), the last mod's tower winning, a duel's
 * result moving the progress on (checkpoints, restarts, the top), and the
 * progress file keeping the sections of towers that are not this run's. */
#define _POSIX_C_SOURCE 200809L /* scratch.h: mkdtemp, lstat, kill */
#include "scratch.h"
#include "../../src/pc/tower/tower_config.c"
#include <stdarg.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

/* --- what the reader leans on ------------------------------------------- */

static int notes;
static char said[8192];                 /* every note, one a line */
void Mods_Note(const char *id, const char *format, ...)
{
    va_list arguments;
    size_t at = strlen(said);
    notes++;
    at += (size_t)snprintf(said + at, sizeof(said) - at, "[%s] ", id);
    va_start(arguments, format);
    if (at < sizeof(said)) at += (size_t)vsnprintf(said + at, sizeof(said) - at, format, arguments);
    va_end(arguments);
    if (at + 1 < sizeof(said)) strcat(said, "\n");
}
static int heard(const char *words) { return strstr(said, words) != NULL; }
static void forget(void) { notes = 0; said[0] = 0; }

int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { (void)index; return 0; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return "test"; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

/* Duelists: the disc's 1-39 by number, a few by name, and one a mod added
 * ("tower-mod:ghost", 40). Cards: 1-722 by number, two by name. */
int Duelists_Valid(int duelist) { return duelist >= 1 && duelist <= 40; }
int Duelists_Named(const char *text)
{
    char *end;
    long id = strtol(text, &end, 10);
    if (*text && !*end) return id >= 0 && id <= 40 ? (int)id : -1;
    if (!strcmp(text, "Seto")) return 7;
    if (!strcmp(text, "Simon Muran")) return 1;
    if (!strcmp(text, "Teana")) return 2;
    if (!strcmp(text, "Ghost") || !strcmp(text, "tower-mod:ghost")) return 40;
    return -1;
}
int Cards_Valid(int id) { return id >= 1 && id <= 722; }
int Cards_Named(const char *text)
{
    char *end;
    long id = strtol(text, &end, 10);
    if (*text && !*end) return (int)id;
    if (!strcmp(text, "Blue-eyes White Dragon")) return 1;
    if (!strcmp(text, "Kuriboh")) return 40;
    return 0;
}
/* The stage's leanings: a folder's paths, an added duelist's base, its name;
 * no picture is made without a game (tower_art.c). */
const char *Mods_Directory(int mod) { (void)mod; return "folder"; }
int Paths_Contained(const char *relative) { return relative && relative[0] != '/' && !strstr(relative, ".."); }
int Duelists_BaseId(int duelist) { return duelist == 40 ? 1 : duelist; }
const char *Duelists_Name(int duelist) { return duelist == 7 ? "Seto" : "a duelist"; }
void Tower_MakeArt(TowerConfig *config) { (void)config; }

int Tables_TerrainNamed(const char *text)
{
    if (!strcmp(text, "Forest")) return 1;
    if (!strcmp(text, "Yami") || !strcmp(text, "Dark")) return 6;
    if (!strcmp(text, "3")) return 3;
    return -1;
}

static JsonDocument *documents[32];
static int document_count;

static void read_as(const char *mod, const char *text)
{
    char error[256];
    JsonDocument *document = Json_Parse(text, error, sizeof(error));
    if (!document) fprintf(stderr, "%s\n", error);
    CHECK(document != NULL);
    CHECK(document_count < 32);
    documents[document_count++] = document;
    Tower_Read(mod, "folder", Json_Root(document));
}

static const TowerLine *line_of(TowerStory story, int index)
{
    CHECK(index < story.count);
    return &Tower_Config()->lines[story.first + index];
}

/* --- the tower as written -------------------------------------------------- */

static void defaults(void)
{
    const TowerConfig *tower;
    Tower_Reset();
    forget();
    CHECK(Tower_Config() == NULL && Tower_Mod() == NULL);
    CHECK(!strcmp(Tower_Label(), "TOWER"));
    read_as("plain", "{\"tower\": {\"floors\": [{\"duelist\": \"Seto\"}]}}");
    tower = Tower_Config();
    CHECK(tower != NULL && notes == 0);
    CHECK(!strcmp(Tower_Mod(), "plain") && !strcmp(tower->name, "plain"));
    CHECK(!strcmp(Tower_Label(), "TOWER"));
    CHECK(tower->unlock.kind == TOWER_UNLOCK_ALWAYS && !tower->unlock.after_ending && tower->unlock.story == -1);
    CHECK(tower->on_lose == TOWER_ON_LOSE_CHECKPOINT && tower->music == -1);
    CHECK(tower->floor_count == 1);
    CHECK(tower->floors[0].duelist == 7 && tower->floors[0].terrain == 0 && !tower->floors[0].deck_given);
    CHECK(tower->floors[0].life_points[0] == 0 && tower->floors[0].life_points[1] == 0);
    CHECK(tower->floors[0].rules == 0 && !tower->floors[0].checkpoint);
    CHECK(tower->floors[0].reward_card_count == 0 && tower->floors[0].reward_starchips == 0);
    CHECK(tower->intro.count == 0 && tower->ending.count == 0 && tower->floors[0].before.count == 0);
    /* A manifest without one leaves the tower as it was. */
    read_as("other", "{\"cards\": []}");
    CHECK(Tower_Config() == tower && !strcmp(Tower_Mod(), "plain"));
}

static void every_key(void)
{
    const TowerConfig *tower;
    const TowerFloor *floor;
    Tower_Reset();
    forget();
    read_as("tower-mod",
            "{\"tower\": {\"name\": \"The Shadow Tower\", \"label\": \"SHADOW TOWER\", \"music\": 42,"
            " \"unlock\": \"after_ending\", \"on_lose\": \"restart\","
            " \"intro\": \"Climb.\", \"ending\": [\"The top.\", {\"text\": \"Well done.\", \"speaker\": \"Simon Muran\"}],"
            " \"lose\": {\"text\": \"Again.\", \"portrait\": 8},"
            " \"floors\": ["
            "  {\"duelist\": \"Simon Muran\", \"field\": \"Forest\", \"checkpoint\": true,"
            "   \"life_points\": {\"player\": 100}, \"reward\": {\"cards\": [\"Kuriboh\", 2], \"starchips\": 50},"
            "   \"before\": [\"Welcome.\", {\"text\": \"Narrated.\", \"speaker\": \"none\"}], \"after\": \"Well fought.\"},"
            "  {\"duelist\": 7, \"field\": \"Dark\", \"no_fusions\": true, \"no_equips\": true, \"life_points\": 4000,"
            "   \"deck\": {\"Blue-eyes White Dragon\": 3, \"Kuriboh\": 37}},"
            "  {\"duelist\": \"tower-mod:ghost\", \"field\": 3, \"reward\": {\"unlock_duelist\": \"Ghost\", \"card\": 5},"
            "   \"deck\": [1,1,1,1,1,1,1,1,1,1,2,2,2,2,2,2,2,2,2,2,3,3,3,3,3,3,3,3,3,3,4,4,4,4,4,4,4,4,4,4]}"
            " ]}}");
    tower = Tower_Config();
    if (notes) fprintf(stderr, "%s", said);
    CHECK(tower != NULL && notes == 0);
    CHECK(!strcmp(tower->name, "The Shadow Tower") && !strcmp(Tower_Label(), "SHADOW TOWER"));
    CHECK(tower->music == 42 && tower->on_lose == TOWER_ON_LOSE_RESTART);
    CHECK(tower->unlock.kind == TOWER_UNLOCK_CONDITIONS && tower->unlock.after_ending);
    CHECK(tower->intro.count == 1 && !strcmp(line_of(tower->intro, 0)->text, "Climb."));
    CHECK(line_of(tower->intro, 0)->speaker == TOWER_SPEAKER_NONE &&
          line_of(tower->intro, 0)->portrait == TOWER_PORTRAIT_AUTO);
    CHECK(tower->ending.count == 2 && line_of(tower->ending, 1)->speaker == 1);
    CHECK(tower->lose.count == 1 && line_of(tower->lose, 0)->portrait == 8);
    CHECK(tower->floor_count == 3);
    floor = &tower->floors[0];
    CHECK(floor->duelist == 1 && floor->terrain == 1 && floor->checkpoint);
    CHECK(floor->life_points[0] == 100 && floor->life_points[1] == 0);
    CHECK(floor->reward_card_count == 2 && floor->reward_cards[0] == 40 && floor->reward_cards[1] == 2);
    CHECK(floor->reward_starchips == 50 && floor->reward_duelist_count == 0);
    CHECK(floor->before.count == 2 && line_of(floor->before, 0)->speaker == TOWER_SPEAKER_FLOOR);
    CHECK(line_of(floor->before, 1)->speaker == TOWER_SPEAKER_NONE);
    CHECK(floor->after.count == 1 && !strcmp(line_of(floor->after, 0)->text, "Well fought."));
    floor = &tower->floors[1];
    CHECK(floor->duelist == 7 && floor->terrain == 6 && !floor->checkpoint);
    CHECK(floor->rules == (TOWER_RULE_NO_FUSIONS | TOWER_RULE_NO_EQUIPS));
    CHECK(floor->life_points[0] == 4000 && floor->life_points[1] == 4000);
    CHECK(floor->deck_given && floor->deck[0] == 1 && floor->deck[2] == 1 && floor->deck[3] == 40 && floor->deck[39] == 40);
    floor = &tower->floors[2];
    CHECK(floor->duelist == 40 && floor->terrain == 3);
    CHECK(floor->reward_duelist_count == 1 && floor->reward_duelists[0] == 40);
    CHECK(floor->reward_card_count == 1 && floor->reward_cards[0] == 5);
    CHECK(floor->deck_given && floor->deck[9] == 1 && floor->deck[10] == 2 && floor->deck[39] == 4);
    /* An object of conditions, and {} which asks for nothing. */
    read_as("cond", "{\"tower\": {\"unlock\": {\"beat\": \"Seto\", \"wins\": 3, \"story\": 69, \"after_ending\": true},"
                    " \"floors\": [{\"duelist\": 1}]}}");
    tower = Tower_Config();
    CHECK(tower->unlock.kind == TOWER_UNLOCK_CONDITIONS && tower->unlock.after_ending);
    CHECK(!strcmp(tower->unlock.beat, "Seto") && tower->unlock.wins == 3 && tower->unlock.story == 69);
    read_as("empty", "{\"tower\": {\"unlock\": {}, \"floors\": [{\"duelist\": 1}]}}");
    CHECK(Tower_Config()->unlock.kind == TOWER_UNLOCK_ALWAYS);
    read_as("always", "{\"tower\": {\"unlock\": \"always\", \"floors\": [{\"duelist\": 1}]}}");
    CHECK(Tower_Config()->unlock.kind == TOWER_UNLOCK_ALWAYS);
}

/* The last mod in load order has the menu's tower; the one it replaced is
 * told so. */
static void last_wins(void)
{
    Tower_Reset();
    forget();
    read_as("first", "{\"tower\": {\"name\": \"One\", \"floors\": [{\"duelist\": 1}]}}");
    read_as("second", "{\"tower\": {\"name\": \"Two\", \"floors\": [{\"duelist\": 7}, {\"duelist\": 1}]}}");
    CHECK(!strcmp(Tower_Mod(), "second") && !strcmp(Tower_Config()->name, "Two"));
    CHECK(Tower_Config()->floor_count == 2 && Tower_Config()->floors[0].duelist == 7);
    CHECK(notes == 1 && heard("[first] tower: second's tower"));
    /* A later tower with no floor that can be fought leaves this one. */
    forget();
    read_as("third", "{\"tower\": {\"name\": \"Three\", \"floors\": [{\"duelist\": \"Nobody\"}]}}");
    CHECK(!strcmp(Tower_Mod(), "second") && !strcmp(Tower_Config()->name, "Two"));
    CHECK(Tower_Config()->floor_count == 2 && Tower_Config()->floors[0].duelist == 7);
    CHECK(heard("[third] tower: no floor can be fought; second's tower stays") &&
          !heard("[second] tower: third's tower"));
}

static void mistakes(void)
{
    const TowerConfig *tower;
    /* What makes no tower at all. */
    Tower_Reset();
    forget();
    read_as("m", "{\"tower\": [1]}");
    CHECK(Tower_Config() == NULL && heard("\"tower\" is an object"));
    read_as("m", "{\"tower\": {\"name\": \"x\"}}");
    CHECK(Tower_Config() == NULL && heard("\"floors\" is a list of at least one floor"));
    read_as("m", "{\"tower\": {\"floors\": []}}");
    CHECK(Tower_Config() == NULL);
    forget();
    read_as("m", "{\"tower\": {\"floors\": [{\"duelist\": \"Nobody\"}, {\"field\": \"Forest\"}, 7]}}");
    CHECK(Tower_Config() == NULL);
    CHECK(heard("tower floors[0]: no duelist \"Nobody\""));
    CHECK(heard("tower floors[1]: a floor needs a \"duelist\"; left out"));
    CHECK(heard("tower floors[2]: a floor is an object"));
    CHECK(heard("tower: no floor can be fought; no tower"));

    /* What leaves the tower, without the part written wrong. */
    forget();
    read_as("m", "{\"tower\": {\"unlock\": \"after-ending\", \"on_lose\": \"retry\", \"colour\": 1, \"music\": 99999,"
                 " \"label\": \"A LABEL FAR LONGER THAN THIRTY ONE LETTERS\","
                 " \"floors\": [{\"duelist\": \"Nobody\"},"
                 "  {\"duelist\": \"Seto\", \"field\": \"Lava\", \"no_fusions\": \"true\", \"life_points\": 0,"
                 "   \"deck\": {\"Kuriboh\": 39}, \"reward\": {\"cards\": [\"Nothing\"], \"starchips\": -5, \"gold\": 1},"
                 "   \"before\": [{\"text\": \"Hi.\", \"portrait\": 30}, 5], \"checkpoint\": 1, \"boss\": true}]}}");
    tower = Tower_Config();
    CHECK(tower != NULL && tower->floor_count == 1);
    CHECK(tower->unlock.kind == TOWER_UNLOCK_NEVER && heard("the tower stays locked"));
    CHECK(tower->on_lose == TOWER_ON_LOSE_CHECKPOINT && heard("\"on_lose\" is \"checkpoint\" or \"restart\""));
    CHECK(heard("tower: unknown key \"colour\"") && heard("tower floors[1]: unknown key \"boss\""));
    CHECK(tower->music == -1 && heard("\"music\" is a song id"));
    CHECK(strlen(tower->label) == TOWER_LABEL - 1 && heard("\"label\" is longer than 31 letters"));
    CHECK(tower->floors[0].duelist == 7 && tower->floors[0].terrain == 0 && heard("\"field\" is none, Forest"));
    CHECK(tower->floors[0].rules == 0 && heard("\"no_fusions\" is true or false, without quotes"));
    CHECK(tower->floors[0].life_points[0] == 0 && heard("\"life_points\" is 1 to 65535"));
    CHECK(!tower->floors[0].deck_given && heard("a deck is 40 cards, and this one has 39"));
    CHECK(tower->floors[0].reward_card_count == 0 && heard("tower floors[1] reward: no card \"Nothing\""));
    CHECK(tower->floors[0].reward_starchips == 0 && heard("\"starchips\" is 0 to 999999"));
    CHECK(heard("tower floors[1]: unknown key \"gold\""));
    CHECK(!tower->floors[0].checkpoint && heard("\"checkpoint\" is true or false"));
    CHECK(tower->floors[0].before.count == 1 &&
          line_of(tower->floors[0].before, 0)->portrait == TOWER_PORTRAIT_AUTO);
    CHECK(heard("\"portrait\" is one of the campaign's portraits (0 to 24)"));
    CHECK(heard("tower floors[1] before[1]: a line is text"));
    /* A deck naming a card that is not there deals the opponent's own. */
    forget();
    read_as("m", "{\"tower\": {\"floors\": [{\"duelist\": 1, \"deck\": [\"Kuriboh\", \"Nothing\"]},"
                 " {\"duelist\": 1, \"deck\": 5}]}}");
    CHECK(!Tower_Config()->floors[0].deck_given && heard("the opponent's own deck is dealt instead"));
    CHECK(!Tower_Config()->floors[1].deck_given && heard("a deck is {card: copies} or a list of forty cards"));
    /* Conditions written wrong keep it locked too. */
    forget();
    read_as("m", "{\"tower\": {\"unlock\": {\"wins\": \"many\"}, \"floors\": [{\"duelist\": 1}]}}");
    CHECK(Tower_Config()->unlock.kind == TOWER_UNLOCK_NEVER && heard("\"wins\" is 0 to 65535"));
    read_as("m", "{\"tower\": {\"unlock\": 3, \"floors\": [{\"duelist\": 1}]}}");
    CHECK(Tower_Config()->unlock.kind == TOWER_UNLOCK_NEVER);
    /* "after_ending": "yes" is no condition to open it on, not none at all. */
    forget();
    read_as("m", "{\"tower\": {\"unlock\": {\"after_ending\": \"yes\"}, \"floors\": [{\"duelist\": 1}]}}");
    CHECK(Tower_Config()->unlock.kind == TOWER_UNLOCK_NEVER && heard("\"after_ending\" is true or false"));
}

/* --- progress ---------------------------------------------------------------- */

static void results(void)
{
    TowerProgress progress;
    TowerOutcome outcome;
    TowerConfig *tower;
    Tower_Reset();
    forget();
    read_as("p", "{\"tower\": {\"floors\": [{\"duelist\": 1, \"checkpoint\": true}, {\"duelist\": 2},"
                 " {\"duelist\": 3}]}}");
    tower = (TowerConfig *)Tower_Config();
    Tower_ClearProgress(&progress, 0x1234, Tower_Identity(tower));
    CHECK(progress.owner == 0x1234 && progress.floor == 0 && !Tower_FloorCleared(&progress, 0));
    /* Floor 1 won: a checkpoint, its reward the first time. */
    outcome = Tower_ApplyResult(tower, &progress, 0, 1);
    CHECK(outcome.won && outcome.first_clear && outcome.checkpoint && !outcome.completed);
    CHECK(progress.floor == 1 && progress.checkpoint == 1 && Tower_FloorCleared(&progress, 0));
    /* Floor 2 won, floor 3 lost: back to the checkpoint, floor 2. */
    outcome = Tower_ApplyResult(tower, &progress, 1, 1);
    CHECK(outcome.first_clear && !outcome.checkpoint && progress.floor == 2 && progress.checkpoint == 1);
    outcome = Tower_ApplyResult(tower, &progress, 2, 0);
    CHECK(!outcome.won && !outcome.first_clear && outcome.back_to == 1 && progress.floor == 1);
    CHECK(!Tower_FloorCleared(&progress, 2));
    /* Floor 2 again: no reward the second time. */
    outcome = Tower_ApplyResult(tower, &progress, 1, 1);
    CHECK(outcome.won && !outcome.first_clear && progress.floor == 2);
    /* The top: the ending, and the tower from the first floor again. */
    outcome = Tower_ApplyResult(tower, &progress, 2, 1);
    CHECK(outcome.completed && outcome.first_clear && progress.floor == 0 && progress.checkpoint == 0);
    CHECK(progress.completions == 1 && Tower_FloorCleared(&progress, 2));
    /* "restart": a loss goes back to the first floor, checkpoint or not. */
    tower->on_lose = TOWER_ON_LOSE_RESTART;
    Tower_ApplyResult(tower, &progress, 0, 1);
    CHECK(progress.floor == 1 && progress.checkpoint == 1);
    outcome = Tower_ApplyResult(tower, &progress, 1, 0);
    CHECK(outcome.back_to == 0 && progress.floor == 0 && progress.checkpoint == 0);
    /* A floor the tower has not is nothing. */
    outcome = Tower_ApplyResult(tower, &progress, 7, 1);
    CHECK(!outcome.won && progress.floor == 0);
    /* The identity follows the mod and the name. */
    CHECK(Tower_Identity(tower) != 0);
    {
        TowerConfig other = *tower;
        snprintf(other.name, sizeof(other.name), "Another");
        CHECK(Tower_Identity(&other) != Tower_Identity(tower));
    }
}

static void progress_file(void)
{
    TowerProgress progress, back;
    char *foreign = NULL;
    /* tmpfile() makes its file in the drive's root on Windows, which a CI
     * runner may not write to (packs_test.c). */
    char directory[SCRATCH_MAX], path[SCRATCH_MAX + 32];
    FILE *file;
    CHECK(scratch_dir(directory, sizeof(directory), "memories-tower") != NULL);
    snprintf(path, sizeof(path), "%s/progress.txt", directory);
    file = fopen(path, "w+b");
    CHECK(file != NULL);
    Tower_ClearProgress(&progress, 0xABCD1234u, 0x55AA55AAu);
    progress.floor = 2;
    progress.checkpoint = 1;
    progress.completions = 3;
    progress.flags = 1;
    progress.cleared[0] = 0x05;
    progress.cleared[12] = 0x04;                       /* floor 98, the last there can be */
    fputs("tower old-mod\nidentity 00000001\nfloor 4\nend\n", file);
    Tower_WriteProgress(file, "my-mod", &progress, "tower gone-mod\nidentity 00000002\nend\n");
    rewind(file);
    CHECK(Tower_ReadProgress(file, "my-mod", 0x55AA55AAu, &back, &foreign));
    CHECK(back.owner == 0xABCD1234u && back.tower == 0x55AA55AAu && back.floor == 2 && back.checkpoint == 1);
    CHECK(back.completions == 3 && back.flags == 1);
    CHECK(Tower_FloorCleared(&back, 0) && !Tower_FloorCleared(&back, 1) && Tower_FloorCleared(&back, 2));
    CHECK(Tower_FloorCleared(&back, 98));
    /* The other towers' sections, whole, to be written back. */
    CHECK(foreign && strstr(foreign, "tower old-mod\nidentity 00000001\nfloor 4\nend\n"));
    CHECK(strstr(foreign, "tower gone-mod\nidentity 00000002\nend\n") && !strstr(foreign, "my-mod"));
    free(foreign);
    /* The same mod with another tower: none of its progress. */
    rewind(file);
    CHECK(!Tower_ReadProgress(file, "my-mod", 0x11111111u, &back, &foreign));
    CHECK(back.floor == 0 && back.tower == 0x11111111u && !Tower_FloorCleared(&back, 0));
    /* ...and its stale lines are no other tower's, to be written back. */
    CHECK(foreign && !strstr(foreign, "owner ABCD1234") && !strstr(foreign, "floor 2\n"));
    CHECK(strstr(foreign, "tower old-mod") && strstr(foreign, "tower gone-mod"));
    free(foreign);
    /* A stale section after this tower's (a file edited by hand): what was
     * read of this tower stays. */
    fseek(file, 0, SEEK_END);
    fputs("tower my-mod\nidentity 00000003\nfloor 7\nend\n", file);
    rewind(file);
    CHECK(Tower_ReadProgress(file, "my-mod", 0x55AA55AAu, &back, &foreign));
    CHECK(back.owner == 0xABCD1234u && back.floor == 2 && back.checkpoint == 1);
    free(foreign);
    /* A tower the file has not. */
    rewind(file);
    CHECK(!Tower_ReadProgress(file, "new-mod", 7, &back, &foreign));
    CHECK(foreign && strstr(foreign, "tower my-mod"));
    free(foreign);
    fclose(file);
}

/* --- the stage a story is told on ------------------------------------------ */

static void stage(void)
{
    const TowerConfig *tower;
    const TowerLine *line;
    Tower_Reset();
    forget();
    /* Defaults: the torch corridor, nobody on the stage but a floor's
     * opponent (tower_screen.c), a portrait only for a speaker who has no
     * character there, no pan, no dimming. */
    read_as("s", "{\"tower\": {\"intro\": \"Hello.\", \"floors\": [{\"duelist\": \"Seto\", \"before\": \"Hi.\"}]}}");
    tower = Tower_Config();
    CHECK(tower && notes == 0 && tower->scene == TOWER_SCENE_DEFAULT && tower->scene == 0x022 && !tower->dim);
    line = line_of(tower->intro, 0);
    CHECK(line->scene == TOWER_SCENE_KEEP && line->cast[0].kind == TOWER_CAST_KEEP &&
          line->cast[1].kind == TOWER_CAST_KEEP && !line->pan && line->portrait == TOWER_PORTRAIT_AUTO);
    CHECK(line_of(tower->floors[0].before, 0)->speaker == TOWER_SPEAKER_FLOOR);

    /* Every key, right. */
    Tower_Reset();
    forget();
    read_as("s", "{\"tower\": {\"scene\": \"seal shrine\", \"dim\": true,"
                 " \"intro\": {\"scene\": 139, \"characters\": {\"left\": 1, \"right\": \"art/hero.png\"},"
                 "  \"lines\": [\"One.\","
                 "   {\"text\": \"Two.\", \"speaker\": \"right\", \"scene\": \"scenes/sky.png\"},"
                 "   {\"text\": \"Three.\", \"speaker\": \"left\", \"scene\": \"none\", \"portrait\": \"speaker\","
                 "    \"characters\": {\"left\": {\"character\": 4, \"expression\": 2}, \"right\": \"none\"}},"
                 "   {\"text\": \"Four.\", \"speaker\": \"Seto\", \"portrait\": 24, \"pan\": {\"x\": 160, \"y\": 8,"
                 "    \"frames\": 90, \"wait\": true}, \"characters\": {\"right\": {\"image\": \"art/hero.png\","
                 "    \"flip\": true}}},"
                 "   {\"text\": \"Five.\", \"portrait\": \"none\", \"scene\": 205,"
                 "    \"characters\": {\"left\": \"Seto\", \"right\": {\"image\": \"art/ghost.png\", \"duelist\": \"opponent\"}}},"
                 "   {\"text\": \"Six.\", \"characters\": {\"left\": {\"duelist\": 7}, \"right\": \"opponent\"}},"
                 "   {\"text\": \"Seven.\", \"characters\": {\"right\": {\"image\": \"art/hero.png\", \"duelist\": \"none\"}}}]},"
                 " \"floors\": [{\"duelist\": \"Seto\"}]}}");
    tower = Tower_Config();
    CHECK(tower && notes == 0);
    CHECK(tower->scene == 0x018 && tower->dim);
    CHECK(tower->intro.count == 7);
    line = line_of(tower->intro, 0);
    CHECK(line->scene == 0x139 && line->speaker == TOWER_SPEAKER_NONE);
    CHECK(line->cast[0].kind == TOWER_CAST_RETAIL && line->cast[0].id == 1);
    CHECK(line->cast[1].kind == TOWER_CAST_ART && line->cast[1].id == 0);
    CHECK(tower->art_count == 4);   /* hero, sky, hero turned, ghost */
    CHECK(tower->arts[0].kind == TOWER_ART_CHARACTER && !strcmp(tower->arts[0].path, "folder/art/hero.png"));
    line = line_of(tower->intro, 1);
    CHECK(line->speaker == TOWER_SPEAKER_RIGHT && line->scene == TOWER_SCENE_ART + 1);
    CHECK(tower->arts[1].kind == TOWER_ART_SCENE && line->cast[0].kind == TOWER_CAST_KEEP);
    line = line_of(tower->intro, 2);
    CHECK(line->speaker == TOWER_SPEAKER_LEFT && line->scene == 0x000 && line->portrait == TOWER_PORTRAIT_SPEAKER);
    CHECK(line->cast[0].kind == TOWER_CAST_RETAIL && line->cast[0].id == 4 && line->cast[0].expression == 2);
    CHECK(line->cast[1].kind == TOWER_CAST_NONE);
    line = line_of(tower->intro, 3);
    CHECK(line->speaker == 7 && line->portrait == 24 && line->pan && line->pan_x == 160 && line->pan_y == 8 &&
          line->pan_frames == 90 && line->pan_wait);
    CHECK(line->cast[1].kind == TOWER_CAST_ART && line->cast[1].id == 2 && tower->arts[2].flip);
    line = line_of(tower->intro, 4);
    CHECK(line->portrait == -1 && line->scene == 0x205);
    CHECK(line->cast[0].kind == TOWER_CAST_RETAIL && line->cast[0].id == 0x04 && line->cast[0].duelist == 7);
    CHECK(line->cast[1].kind == TOWER_CAST_ART && line->cast[1].id == 3 && line->cast[1].duelist == TOWER_SPEAKER_FLOOR);
    line = line_of(tower->intro, 5);
    CHECK(line->cast[0].kind == TOWER_CAST_RETAIL && line->cast[0].duelist == 7);
    CHECK(line->cast[1].kind == TOWER_CAST_OPPONENT);
    line = line_of(tower->intro, 6);   /* an image whose duelist is "none": the image alone */
    CHECK(line->cast[1].kind == TOWER_CAST_ART && line->cast[1].id == 0 && line->cast[1].duelist == 0);
    CHECK(Tower_SceneNamed("Torch_Corridor") == 0x022 && Tower_SceneNamed("nowhere") == -1);
    CHECK(!strcmp(Tower_SceneName(0x041), "burning pyramid") && Tower_SceneName(0x042) == NULL);
    CHECK(Tower_RetailScene(0x141) && !Tower_RetailScene(0x142) && Tower_RetailScene(0x212) &&
          !Tower_RetailScene(0x213) && !Tower_RetailScene(0x0A0) && !Tower_RetailScene(0x300));
    CHECK(Tower_DuelistCharacter(1) == 0x01 && Tower_DuelistCharacter(7) == 0x04 && Tower_DuelistCharacter(4) == 0);
    CHECK(Tower_DuelistCharacter(40) == 0x01);   /* an added duelist: its base's (Simon Muran's) */

    /* And wrong: each noted, the rest kept. */
    Tower_Reset();
    forget();
    read_as("s", "{\"tower\": {\"scene\": 150, \"dim\": \"yes\", \"floors\": [{\"duelist\": \"Seto\","
                 " \"before\": {\"scene\": \"../out.png\", \"characters\": {\"middle\": 1, \"left\": 39}, \"lines\": ["
                 "  {\"text\": \"A.\", \"characters\": [1], \"pan\": {\"x\": 9999, \"speed\": 1}},"
                 "  {\"text\": \"B.\", \"characters\": {\"left\": {\"character\": \"Seto\"}, \"right\": 4},"
                 "   \"scene\": \"the moon\", \"portrait\": \"face\"},"
                 "  {\"text\": \"C.\", \"characters\": {\"left\": {\"duelist\": 4, \"flip\": true, \"mood\": 1},"
                 "   \"right\": {\"character\": 2, \"expression\": 9}}}]},"
                 " \"after\": {\"lines\": []}}]}}");
    tower = Tower_Config();
    CHECK(tower && tower->scene == TOWER_SCENE_DEFAULT);
    CHECK(heard("tower: \"scene\" 150 is none of the disc's"));
    CHECK(heard("tower: \"dim\" is true or false"));
    CHECK(heard("../out.png is not a path inside the mod"));
    CHECK(heard("tower floors[0] before: unknown key \"middle\""));
    CHECK(heard("character 39 is none of the campaign's"));
    CHECK(heard("before[0]: \"characters\" is {\"left\": ..., \"right\": ...}"));
    CHECK(heard("pan \"x\" is 0 to 576") && heard("before[0]: unknown key \"speed\""));
    CHECK(heard("\"character\" is one of the campaign's, 1 to 64"));
    CHECK(heard("\"scene\" is a scene's name"));
    CHECK(heard("\"portrait\" is one of the campaign's portraits (0 to 24)"));
    CHECK(heard("has no character in the campaign"));
    CHECK(heard("\"flip\" turns a PNG of the mod's") && heard("unknown key \"mood\""));
    CHECK(heard("\"expression\" is 0 to 3"));
    line = line_of(tower->floors[0].before, 0);
    CHECK(line->scene == TOWER_SCENE_KEEP && line->cast[0].kind == TOWER_CAST_NONE && line->pan && line->pan_x == 0);
    line = line_of(tower->floors[0].before, 1);
    CHECK(line->cast[0].kind == TOWER_CAST_NONE && line->cast[1].kind == TOWER_CAST_RETAIL && line->cast[1].id == 4);
    CHECK(line->scene == TOWER_SCENE_KEEP && line->portrait == TOWER_PORTRAIT_AUTO);
    line = line_of(tower->floors[0].before, 2);
    CHECK(line->cast[0].kind == TOWER_CAST_NONE && line->cast[1].kind == TOWER_CAST_RETAIL && line->cast[1].id == 2 &&
          line->cast[1].expression == 0);
    CHECK(tower->floors[0].after.count == 0);

    /* No folder to find a PNG in: noted, the line kept without it. */
    Tower_Reset();
    forget();
    {
        char error[256];
        JsonDocument *document = Json_Parse("{\"tower\": {\"intro\": {\"text\": \"X.\", \"scene\": \"a.png\"},"
                                            " \"floors\": [{\"duelist\": 1}]}}", error, sizeof(error));
        CHECK(document && document_count < 32);
        documents[document_count++] = document;
        Tower_Read("s", NULL, Json_Root(document));
    }
    CHECK(heard("a.png: the mod has no folder to find it in"));
    CHECK(line_of(Tower_Config()->intro, 0)->scene == TOWER_SCENE_KEEP && Tower_Config()->art_count == 0);

    /* A story longer than one box holds: cut, and noted. */
    Tower_Reset();
    forget();
    {
        static char text[40000];
        size_t at = 0;
        int i;
        at += (size_t)snprintf(text + at, sizeof(text) - at, "{\"tower\": {\"intro\": [");
        for (i = 0; i < 40; i++) {
            at += (size_t)snprintf(text + at, sizeof(text) - at, "%s\"", i ? "," : "");
            memset(text + at, 'a', 500);
            at += 500;
            at += (size_t)snprintf(text + at, sizeof(text) - at, "\"");
        }
        snprintf(text + at, sizeof(text) - at, "], \"floors\": [{\"duelist\": 1}]}}");
        read_as("s", text);
    }
    CHECK(heard("a story is at most about 12000 letters; lines 21 on are left out"));
    CHECK(Tower_Config()->intro.count == 21 && Tower_Config()->line_count == 21);
}

/* --- leaving, drops, save states, cheats, a floor's opponent ---------------- */

static void guards_read(void)
{
    const TowerConfig *tower;
    TowerProgress climb;
    Tower_Reset();
    forget();
    read_as("g", "{\"tower\": {\"floors\": [{\"duelist\": \"Seto\"}]}}");
    tower = Tower_Config();
    CHECK(tower && notes == 0);
    CHECK(tower->on_leave == TOWER_ON_LEAVE_RESUME && tower->drops == TOWER_DROPS_DEFAULT && tower->drops == 1);
    CHECK(tower->save_states == 1 && tower->cheats == 1 && tower->floors[0].unlock_opponent == -1);
    Tower_Reset();
    read_as("g", "{\"tower\": {\"on_leave\": \"checkpoint\", \"drops\": \"player\", \"save_states\": false,"
                 " \"cheats\": false, \"floors\": [{\"duelist\": \"Seto\", \"unlock_opponent\": true},"
                 " {\"duelist\": 1, \"unlock_opponent\": false}]}}");
    tower = Tower_Config();
    CHECK(tower && notes == 0 && tower->on_leave == TOWER_ON_LEAVE_CHECKPOINT && tower->drops == TOWER_DROPS_PLAYER);
    CHECK(!tower->save_states && !tower->cheats);
    CHECK(tower->floors[0].unlock_opponent == 1 && tower->floors[1].unlock_opponent == 0);
    /* "checkpoint": a climb past it banked back to it; one behind it kept. */
    memset(&climb, 0, sizeof(climb));
    climb.floor = 3;
    climb.checkpoint = 1;
    Tower_Bank(tower, &climb);
    CHECK(climb.floor == 1 && climb.checkpoint == 1);
    Tower_Reset();
    read_as("g", "{\"tower\": {\"on_leave\": \"restart\", \"drops\": 12, \"floors\": [{\"duelist\": 1}]}}");
    tower = Tower_Config();
    CHECK(tower->on_leave == TOWER_ON_LEAVE_RESTART && tower->drops == 12);
    climb.floor = 3;
    climb.checkpoint = 2;
    climb.cleared[0] = 7;
    Tower_Bank(tower, &climb);
    CHECK(climb.floor == 0 && climb.checkpoint == 0 && climb.cleared[0] == 7);   /* rewards stay given */
    Tower_Reset();
    read_as("g", "{\"tower\": {\"floors\": [{\"duelist\": 1}]}}");
    climb.floor = 3;
    Tower_Bank(Tower_Config(), &climb);   /* "resume": as it was */
    CHECK(climb.floor == 3);
    Tower_Bank(NULL, &climb);
    CHECK(climb.floor == 3);
    /* The FM Editor's example tower (tower.py, example_tower): read without a note. */
    Tower_Reset();
    forget();
    read_as("g",
                 "{\"tower\": {\"name\": \"The Example Tower\", \"label\": \"TOWER\", \"unlock\": \"always\", \"on_los"
                 "e\": \"checkpoint\", \"intro\": {\"scene\": \"seal shrine\", \"characters\": {\"left\": \"Simon Mura"
                 "n\"}, \"lines\": [{\"text\": \"Three floors stand between you and the top, my prince.\", \"speaker\""
                 ": \"left\"}, {\"text\": \"Win them all.\", \"speaker\": \"left\"}]}, \"ending\": {\"scene\": \"thron"
                 "e room\", \"lines\": [\"The tower is yours.\"]}, \"lose\": \"Down you go. Try again.\", \"floors\": "
                 "[{\"duelist\": \"Simon Muran\", \"checkpoint\": true, \"life_points\": {\"opponent\": 4000}, \"rewar"
                 "d\": {\"cards\": [\"Kuriboh\"], \"starchips\": 25}, \"before\": \"Show me what you have learned.\", "
                 "\"after\": \"Well fought. Climb on.\"}, {\"duelist\": \"Teana\", \"field\": \"Forest\", \"no_fusions"
                 "\": true, \"unlock_opponent\": true, \"before\": \"Nobody fuses on this floor.\"}, {\"duelist\": \"S"
                 "eto\", \"no_equips\": true, \"reward\": {\"starchips\": 100}, \"before\": \"No equips here. Only you"
                 "r monsters.\"}]}}");
    CHECK(Tower_Config() && Tower_Config()->floor_count == 3 && notes == 0);
    /* Wrong: noted, the default kept. */
    Tower_Reset();
    forget();
    read_as("g", "{\"tower\": {\"on_leave\": \"never\", \"drops\": 100, \"save_states\": \"no\","
                 " \"floors\": [{\"duelist\": 1, \"unlock_opponent\": 1}]}}");
    tower = Tower_Config();
    CHECK(heard("\"on_leave\" is \"resume\", \"checkpoint\" or \"restart\"; resume it is"));
    CHECK(heard("\"drops\" is 1 to 99 cards a won duel, or \"player\""));
    CHECK(heard("\"save_states\" is true or false, without quotes; left as if not written"));
    CHECK(heard("\"unlock_opponent\" is true or false, without quotes; left as if not written"));
    CHECK(tower->on_leave == TOWER_ON_LEAVE_RESUME && tower->drops == 1 && tower->save_states == 1);
    CHECK(tower->floors[0].unlock_opponent == -1);
}

int main(void)
{
    int i;
    defaults();
    every_key();
    last_wins();
    mistakes();
    stage();
    guards_read();
    results();
    progress_file();
    Tower_Reset();
    for (i = 0; i < document_count; i++) Json_Free(documents[i]);
    printf("tower: ok\n");
    return 0;
}
