#ifndef MEMORIES_PC_TOWER_STATE_H
#define MEMORIES_PC_TOWER_STATE_H
/* What the tower keeps with the game's own variables (gTower,
 * src/pc/game/zz_tower_storage.c): the save's progress, the screen's place
 * in what it shows, the duel it armed, and the text its boxes show. A game
 * unit's data is in every save state and at a fixed address the game's text
 * boxes can point into, which is why this is not a host struct; plain
 * numbers and bytes only (no pointers: G32). */
#include "types.h"

#define TOWER_MAX_FLOORS 99
#define TOWER_TEXT_SIZE 16384             /* the box's text, in the game's codes: a whole story */

/* What a save holds of the tower, kept beside it as tower/<slot token>.txt. */
typedef struct {
    u32 owner;                            /* the duelist code of the save it is of */
    u32 tower;                            /* Tower_Identity of the tower it is of; 0 none yet */
    u16 floor;                            /* the next floor to fight, 0 the first */
    u16 checkpoint;                       /* where a loss sends the player back to */
    u16 completions;                      /* times the whole tower was won */
    u16 flags;                            /* TOWER_PROGRESS_* */
    u8 cleared[(TOWER_MAX_FLOORS + 7) / 8]; /* floors ever won: rewards are given once */
    u8 pad[3];
} TowerProgress;

typedef struct {
    TowerProgress progress;
    s16 step;                             /* the screen's state (tower_screen.c) */
    s16 phase;                            /* within it */
    s16 armed;                            /* 1 + the floor whose duel is armed; 0 none */
    s16 rules;                            /* that duel's TOWER_RULE_* */
    s16 story;                            /* the story being told (TOWER_STORY_*) */
    s16 line;                             /* its line on the box */
    s16 then;                             /* the step after the story */
    s16 choice;                           /* the answer the box gave */
    s16 outcome;                          /* what the last duel did (TOWER_OUTCOME_*) */
    s16 floor;                            /* the floor the last duel was on */
    s16 portrait;                         /* the cell the box's portrait is in, -1 none */
    s16 pad;
    /* The stage a story is told on (Tower_Scene): a scene is up, its id,
     * and the mod's pictures the characters the disc keeps empty stand
     * for (1 + the art, 0 none), in TOWER_POOL_IDS' order. */
    s16 scene_on;
    s16 scene;
    s16 dim;                              /* a character not speaking is drawn darker */
    s16 faded;                            /* the screen is black: the next step fades in */
    u8 pool[8];
    u8 text[TOWER_TEXT_SIZE];
} TowerState;

/* A mod's scenes are image ids from here on, which are not BCD and so no
 * record of the disc's (tower.h). */
#define TOWER_SCENE_ART 0x0A0
#define TOWER_SCENE_ARTS 0x60         /* 0x0A0-0x0FF */

/* The characters the disc keeps empty, which carry a mod's pictures. */
#define TOWER_POOL_SIZE 5
#define TOWER_POOL_IDS {0x27, 0x28, 0x29, 0x0B, 0x05}

extern TowerState gTower;

/* Text channel 0's box, and the title's wall behind the screen (1 on, 0
 * off): game code (zz_tower_storage.c). */
void *Tower_CreateBox(s32 id, s32 x, s32 y, s32 width, s32 height, s32 flags);
void Tower_Background(s32 on);
/* The stage of a story (zz_tower_storage.c): on, the campaign's scene
 * package (its stone-framed box, its portraits), then scene `image` with
 * the title's wall gone; off, the characters, the scene and the box's frame
 * released, and with `image` 1 the wall back (0: a duel comes next). */
void Tower_Scene(s32 on, s32 image);
/* Once a frame while a scene is up: the scene's flicker (the campaign's
 * SceneScript_UpdateSlots), and with gTower.dim the characters not
 * speaking drawn darker. */
void Tower_SceneFrame(void);
/* Whether a character is still coming in or going out. */
s32 Tower_SceneBusy(void);
/* The game's hooks (#ifdef MEMORIES_PC): ScriptImage_RequestTransfer asks
 * whether `id` is a mod's scene and puts it in VRAM itself when it is (1);
 * func_8003A560 asks for character `id`'s cache slot to be filled from a
 * mod's picture before it would read the disc. Both do nothing without a
 * tower's story on the screen. */
s32 Tower_UploadScene(s32 id);
void Tower_FillCharacter(s32 id);
/* The host side of those (tower_art.c): art `art`'s scene picture (320 x
 * 160 texels, 8 bits, and its 256 colors), or its character's cache slot
 * (texels 384 x 256, 2 x 256 colors, the parts bank); NULL when it was not
 * made. */
const u8 *Tower_ArtScene(s32 art, const u16 **clut);
const u8 *Tower_ArtCharacter(s32 art, const u16 **clut, const u8 **bank);

#endif
