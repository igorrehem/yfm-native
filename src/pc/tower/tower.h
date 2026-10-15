#ifndef MEMORIES_PC_TOWER_H
#define MEMORIES_PC_TOWER_H
/* Tower mode: a mod's "tower" key (notes/tower-mode.md).
 *
 * A tower is a run of duels, its floors, that the title's second menu
 * offers once a mod with a "tower" is on: each floor an opponent with a
 * field, a deck, starting LP and rules of its own (no fusions, no equips),
 * a reward, and lines of story before and after it, told as the campaign
 * tells its own (a scene, its large characters, its stone-framed box: the
 * stage below). Progress is the save's: it is
 * kept beside the memory card's block, as the card packs' is, and in every
 * save state.
 *
 * This header is in three parts: the tower as a mod writes it (read once at
 * startup, tower_config.c), the progress a save has in it and the rules it
 * follows (tower_config.c too, so the tests reach both without the game),
 * and what the game asks of it (tower.c, tower_screen.c). */
#include "tower_state.h"
#include <stdint.h>
#include <stdio.h>

struct JsonValue;

#define TOWER_REF 64                  /* a duelist or card as written: an id, a name, an identity */
#define TOWER_NAME 64
#define TOWER_LABEL 32                /* the menu button's words (title_config.h, TITLE_LABEL) */
#define TOWER_DECK 40
#define TOWER_REWARD_CARDS 10
#define TOWER_REWARD_DUELISTS 8
#define TOWER_LINE_TEXT 1024          /* one line of story as written */
#define TOWER_STORY_TEXT 12000        /* a story's letters, all told in one box (TOWER_TEXT_SIZE) */
#define TOWER_LINE_CODES 48           /* what a line's stage may add to them: its codes, at most */
#define TOWER_CAMPAIGN_PORTRAITS 25   /* the campaign's dialogue portraits (campaign_scene_package.h) */

/* The title's second menu returns this for the tower's button
 * (title_menu.c); none of the game's eleven choices nor the debug menu's
 * 11, so Main_ApplyMenuSelection's PC side takes it. */
#define TOWER_MENU_SELECTION 12
/* The tower's own screen: the game's unused developer-mode slot, whose empty
 * runner runs it (main_mode_runners.c). Main_Loop and the mode table are the
 * game's, so save states from before tower mode still load. */
#define TOWER_MODE 13

enum { TOWER_RULE_NO_FUSIONS = 1, TOWER_RULE_NO_EQUIPS = 2 };
enum { TOWER_ON_LOSE_CHECKPOINT, TOWER_ON_LOSE_RESTART };
/* "on_leave": what leaving the tower does to the climb (Tower_Bank). */
enum { TOWER_ON_LEAVE_RESUME, TOWER_ON_LEAVE_CHECKPOINT, TOWER_ON_LEAVE_RESTART };
/* "drops": TOWER_DROPS_PLAYER follows Game > Card drops; else 1-99 cards. */
#define TOWER_DROPS_PLAYER 0
#define TOWER_DROPS_DEFAULT 1
#define TOWER_DROPS_MAX 99
enum { TOWER_UNLOCK_ALWAYS, TOWER_UNLOCK_CONDITIONS, TOWER_UNLOCK_NEVER };
/* A line's speaker: a duelist id (1 up), or one of these. */
enum { TOWER_SPEAKER_NONE = 0, TOWER_SPEAKER_FLOOR = -1, TOWER_SPEAKER_LEFT = -2, TOWER_SPEAKER_RIGHT = -3 };

/* "unlock": "always" (the default), "after_ending", or an object of the
 * duelists' conditions (pc/free_duel/duelists.h) and "after_ending": true.
 * Written wrong, the tower stays locked (NEVER), so nothing opens by
 * mistake. */
typedef struct {
    int kind;                         /* TOWER_UNLOCK_* */
    int after_ending;                 /* the save has seen the ending (Tower_EndingSeen) */
    char beat[TOWER_REF];
    int wins;
    int story;                        /* -1 for none */
    char card[TOWER_REF];
    int copies;
} TowerUnlock;

/* --- the stage a story is told on (notes/tower-mode.md, Story) ----------------
 *
 * The campaign's own: a scene picture (ScriptImage_RequestTransfer's
 * records, or a mod's PNG made into one), up to two of its large characters
 * on the left and the right (the display-effect records F6 01-40 bring in,
 * or a mod's PNG made into one), and its stone-framed box. */

/* A scene: the game's image id (its digits are its decimal digits, BCD:
 * 22 is 0x022, 139 is 0x139), or a mod's picture, TOWER_SCENE_ART up: ids
 * that are not BCD, which no retail script asks for. */
#define TOWER_SCENE_KEEP (-1)         /* a line that does not change it */
#define TOWER_SCENE_DEFAULT 0x022     /* "torch corridor": a story that names none */
#define TOWER_SCENE_NAMES 42          /* mode 0's pictures, 0x000-0x041, have names */
/* The campaign's large characters: the display-effect records 0x01-0x40.
 * The ones the disc keeps empty ("no data" sheets) carry a mod's pictures
 * instead (TOWER_CHARACTER_POOL), so a mod cannot name them. */
#define TOWER_CHARACTERS 0x40
#define TOWER_CHARACTER_POOL 5        /* display-effect cache slots (func_8003A560.h) */
#define TOWER_ARTS 96                 /* a tower's PNGs, scenes and characters together */
#define TOWER_ART_PATH 512
#define TOWER_PORTRAIT_SPEAKER 100    /* "portrait": the speaker's own (Free Duel) face */
#define TOWER_PORTRAIT_AUTO (-2)      /* the speaker's face only when it has no character on stage */

enum { TOWER_SIDE_LEFT, TOWER_SIDE_RIGHT, TOWER_SIDES };
/* What stands on a side. */
enum { TOWER_CAST_KEEP, TOWER_CAST_NONE, TOWER_CAST_RETAIL, TOWER_CAST_ART, TOWER_CAST_OPPONENT };
typedef struct {
    int kind;                         /* TOWER_CAST_* */
    int id;                           /* the retail character (1-0x40), or the art's index */
    int expression;                   /* 0-3: the retail sheet's expression (F6 flags 0x10/0x40) */
    int duelist;                      /* the duelist it was named by, 0 none: a speaker finds it */
} TowerCast;

/* A mod's PNG, made into the game's kind of picture when the tower is
 * built (tower_art.c): a scene's 320 x 160 at 8 bits, or a character's
 * sheet (up to 256 x 256, its bottom edge standing on the box). */
enum { TOWER_ART_SCENE, TOWER_ART_CHARACTER };
typedef struct {
    int kind;                         /* TOWER_ART_* */
    int flip;                         /* a character turned to face the other way */
    char path[TOWER_ART_PATH];
    int ready;                        /* made (tower_art.c); 0: it shows nothing */
    int width, height;                /* a character's, in texels */
    unsigned char *texels;            /* scene: 320 x 160; character: the cache slot's 384 x 256 */
    unsigned short clut[256];
    unsigned char *bank;              /* a character's parts (0x800 bytes), as a disc record's */
} TowerArt;

/* One line of story: what one page or more of the box says. */
typedef struct {
    int speaker;                      /* TOWER_SPEAKER_*, or a duelist */
    int portrait;                     /* a campaign portrait 0-24, TOWER_PORTRAIT_SPEAKER, AUTO, or -1 none */
    int scene;                        /* TOWER_SCENE_KEEP, or the scene from this line on */
    TowerCast cast[TOWER_SIDES];      /* KEEP: the side as it was */
    int pan, pan_x, pan_y, pan_frames, pan_wait;   /* "pan": the viewport moved to x, y */
    char *text;                       /* UTF-8, as written */
} TowerLine;

/* A run of lines (TowerConfig.lines). */
typedef struct {
    int first, count;
} TowerStory;

typedef struct {
    int duelist;                      /* the opponent's id */
    int terrain;                      /* 1-6 (Forest ... Yami), 0 none, as Free Duel has it */
    int deck_given;                   /* the opponent plays `deck`, not one dealt from its pool */
    unsigned short deck[TOWER_DECK];
    int life_points[2];               /* the player's and the opponent's; 0 the usual */
    int rules;                        /* TOWER_RULE_* */
    int reward_cards[TOWER_REWARD_CARDS];
    int reward_card_count;
    unsigned reward_starchips;
    int reward_duelists[TOWER_REWARD_DUELISTS];
    int reward_duelist_count;
    int checkpoint;                   /* won, a loss after it comes back to the next floor */
    int unlock_opponent;              /* beaten, the opponent is in Free Duel: 1, 0, or -1 the default
                                       * (a "tower_only" one is, a retail one is not) */
    TowerStory before, after;
} TowerFloor;

typedef struct {
    char mod[64];                     /* whose tower it is */
    char name[TOWER_NAME];
    char label[TOWER_LABEL];
    int music;                        /* the screen's song, -1 the game's (TOWER_DEFAULT_SONG) */
    TowerUnlock unlock;
    int on_lose;                      /* TOWER_ON_LOSE_* */
    int on_leave;                     /* TOWER_ON_LEAVE_* */
    int drops;                        /* a won floor's cards, or TOWER_DROPS_PLAYER */
    int save_states;                  /* 0: no save state saved or loaded in the tower */
    int cheats;                       /* 0: the Cheats menu does nothing in the tower */
    int scene;                        /* a story's scene when it names none (TOWER_SCENE_DEFAULT) */
    int dim;                          /* "dim": a character not speaking is drawn darker */
    TowerStory intro, ending, lose;
    int floor_count;
    TowerFloor floors[TOWER_MAX_FLOORS];
    TowerLine *lines;
    int line_count, line_room;
    TowerArt arts[TOWER_ARTS];
    int art_count;
} TowerConfig;

/* --- the tower as written (tower_config.c) -------------------------------- */

/* Back to no tower. */
void Tower_Reset(void);
/* One mod's manifest: its "tower", if it has one, over the one read before
 * (the last mod in load order to declare a tower has the menu's). Names a
 * duelist and a card are resolved now, so Duelists_Build and Cards_Build
 * have run. `directory` is the mod's folder its PNGs are in (NULL: it has
 * none, and a PNG it names is noted). */
void Tower_Read(const char *mod, const char *directory, const struct JsonValue *manifest);
/* A scene's name (mode 0's, "torch corridor") to its id, -1 for none; and
 * back, NULL for an id without one. */
int Tower_SceneNamed(const char *name);
const char *Tower_SceneName(int id);
/* Whether `id` is a picture of the disc's (mode 0 0x000-0x041, mode 1
 * 0x100-0x141, mode 2 0x200-0x212). */
int Tower_RetailScene(int id);
/* A retail duelist's large character in the campaign (the one its dialogue
 * brings in before its duel), 0 for none. */
int Tower_DuelistCharacter(int duelist);
/* Whether the disc keeps character `id` (0x01-0x40) empty: then it carries
 * a mod's picture instead. */
int Tower_EmptyCharacter(int id);
/* The tower's PNGs made into the game's pictures (tower_art.c), once the
 * tower is read. */
void Tower_MakeArt(TowerConfig *config);
/* Every active mod's, in load order; once, from Cards_Build. */
void Tower_Build(void);
/* The tower this run has, or NULL. */
const TowerConfig *Tower_Config(void);
/* The mod whose tower it is, or NULL: its button is "<mod>:tower" (title_config.c). */
const char *Tower_Mod(void);
/* The button's words: the tower's "label", else "TOWER". */
const char *Tower_Label(void);

/* --- the progress a save has (tower_config.c) ----------------------------- */

/* TowerProgress (tower_state.h): what a save holds of the tower, kept with
 * the game's own variables so a save state has it, and beside the save as
 * tower/<slot token>.txt. */
enum { TOWER_PROGRESS_INTRO_SEEN = 1 };

/* A number standing for the tower: its mod's id and its name. */
uint32_t Tower_Identity(const TowerConfig *config);

int Tower_FloorCleared(const TowerProgress *progress, int floor);
/* A fresh progress, of the save with duelist code `owner`. */
void Tower_ClearProgress(TowerProgress *progress, uint32_t owner, uint32_t tower);

/* What a duel's result did to the progress (Tower_ApplyResult). */
typedef struct {
    int won;
    int first_clear;                  /* won for the first time: the floor's reward */
    int completed;                    /* the last floor won: the ending */
    int checkpoint;                   /* a checkpoint reached: offer a save */
    int back_to;                      /* lost: the floor the player goes back to */
} TowerOutcome;
/* The duel on floor `floor` was won (`won`) or lost: the next floor, a
 * checkpoint, the cleared floors and the completions move on. A lost duel
 * sends the player back to the last checkpoint, or to the first floor with
 * "on_lose": "restart". After the last floor the tower begins again from
 * the first, its floors still cleared. */
TowerOutcome Tower_ApplyResult(const TowerConfig *config, TowerProgress *progress, int floor, int won);

/* The progress file: one section per tower, "tower <mod>" up to "end"
 * (notes/tower-mode.md). Tower_ReadProgress takes the section of
 * `identity` into `progress` (cleared first) and returns 1 if there was
 * one; the others' lines go to `foreign` (NUL-terminated, malloc'd, NULL
 * for none), to be written back with it. */
int Tower_ReadProgress(FILE *file, const char *mod, uint32_t identity, TowerProgress *progress, char **foreign);
void Tower_WriteProgress(FILE *file, const char *mod, const TowerProgress *progress, const char *foreign);

/* --- what the game asks (tower.c) ------------------------------------------ */

/* Whether the running save has seen the ending: Main_RunCredits sets the
 * low two bits of the save's byte 0x3DE (save_data.h, field_3DE) as the
 * ending begins and the game saves it there; NEW GAME clears the block. */
int Tower_EndingSeen(const void *state);
/* Whether the tower's "unlock" holds for the running save. */
int Tower_Unlocked(void);

/* Whether the floor's duel is the one being fought, and its rules: 0
 * outside a tower duel. Duel_CheckFusion / Duel_CheckEquip and
 * CardRules_Fusion / CardRules_Equip refuse what a rule forbids, for the
 * player, the CPU and the fusion helper alike. */
int Tower_DuelRules(void);
/* Whether the floor's `rule` refuses what `a` with `b` would make
 * (`result`): 1 when it does, which the log says (the first few). */
int Tower_Refuses(int rule, int a, int b, int result);
/* Duel_InitSideStates: the floor's starting LP for `side` (0 the player),
 * or `usual`. */
int Tower_StartingLifePoints(int side, int usual);
/* Duel_ShuffleDeck: the floor's deck for the opponent; 0 when it has none. */
int Tower_OpponentDeck(unsigned short cards[TOWER_DECK]);

/* The "tower" condition of a duelist's "unlock" (duelists.h): floor
 * `floor` (1 the first) won on this save, or the whole tower with 0. */
int Tower_ConditionMet(int floor);
/* A duelist with "tower_only": whether the tower has let it out: a won
 * floor names it as its opponent or in its "reward" "unlock_duelist". */
int Tower_FreesDuelist(int duelist);
/* Whether a won floor unlocks `duelist` outright: it says "unlock_opponent":
 * true against it, or names it in its reward's "unlock_duelist". An added
 * duelist with conditions of its own is then on the grid whatever they say. */
int Tower_OpensDuelist(int duelist);

/* "on_leave": the climb as a save may keep it -- the next floor no further
 * than the checkpoint ("checkpoint") or the first ("restart"). Applied as
 * the tower is left or entered from the title, and to what the save's file
 * is written and read with, so leaving, quitting or a save made outside
 * the tower never keeps a floor past the checkpoint. */
void Tower_Bank(const TowerConfig *config, TowerProgress *progress);

/* In the tower: its screen, a story, or one of its floors' duels. */
int Tower_Active(void);
/* Game > Card drops in a tower duel: the tower's "drops", else `wanted`. */
int Tower_CardDrops(int wanted);
/* What the tower's mod refuses while the player is in it: a save state
 * saved or loaded ("save_states": false), or a cheat of the Cheats menu or
 * a Debug jump ("cheats": false). 1 refused, with why; with `tell` the
 * player is told so in a notice. */
enum { TOWER_GUARD_SAVE_STATE, TOWER_GUARD_LOAD_STATE, TOWER_GUARD_CHEAT, TOWER_GUARD_JUMP };
int Tower_Guard(int what, int tell, char *why, size_t size);
/* Quietly, for the cheats' values read every frame: the tower's mod turns
 * cheats off and the player is in the tower (Starting LP, Show CPU's hand
 * read as the console's). */
int Tower_CheatsOff(void);

/* A won floor's reward: the duelists of the disc it names appear on the
 * Free Duel grid (their 0x6E0 + id flag); an added one is let out by
 * Tower_FreesDuelist. */
void Tower_UnlockRetailDuelists(const TowerFloor *floor);

/* Main_ApplyMenuSelection took TOWER_MENU_SELECTION. */
void Tower_Enter(void);
/* Mode TOWER_MODE's runner, from Main_RunUnusedDeveloperMode (tower_screen.c). */
void Tower_RunMode(void);
/* Text_Resolve: the screen's text by string id, NULL for any other. */
const unsigned char *Tower_Text(int id);
/* Text_Retarget: the screen's choices end its text. NULL for a stream not
 * the screen's. */
unsigned char *Tower_Retarget(const unsigned char *cursor);

/* The running save was loaded (SaveCards_Applied) or written
 * (SaveCards_Saved): its progress, beside it. */
void Tower_SaveLoaded(const void *state);
void Tower_SaveWritten(const void *state);
/* Once a frame: NEW GAME writes a new duelist code without loading, which
 * is a new save with no progress. */
void Tower_Frame(void);
/* The towers other than this run's, which a save's file keeps (a state's
 * chunk "tower-foreign"). */
struct MemoriesState;
void Tower_State(struct MemoriesState *state);

#endif
