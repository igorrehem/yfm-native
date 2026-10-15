/* Tower mode's state (src/pc/tower/tower_state.h): the save's progress in
 * the tower, the tower screen's place and the text its boxes show.
 *
 * A game unit, like drops.c, so it is in the game's data: at a fixed
 * address the game's text boxes can point into, and inside every save
 * state, so a state saved in the tower, or in a tower duel, comes back to
 * the same floor and the same rules. Game units link in name order, and the
 * "zz_" keeps this one after every other, as drops.c sorts after
 * card_storage.c: no existing variable moves. Its zeros still make the
 * game's bss longer, and state.c restores a bss chunk only of this build's
 * size, so a state from a build before tower mode loads without the game's
 * zeroed variables (as after drops.c or free_duel_storage.c came in). */
#include "types.h"
#include "pc/tower/tower_state.h"
#include "game/func_8003B6AC.h"
#include "game/text_box_lifecycle.h"
#include "game/file_transfer.h"
#include "game/main_services.h"
#include "game/menu_record_reset.h"
#include "overlays/main_menu/frontend.h"
#include "game/scene_script.h"
#include "game/campaign_scene_package.h"
#include "game/script_image_objects.h"
#include "game/script_image_rebuild.h"
#include "game/display_object_core.h"
#include "game/menu_record.h"
#include "game/display_effect_lifecycle.h"
#include "game/func_8003A560.h"
#include "game/high_memory_addresses.h"
#include "game/graphics_frame.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"

TowerState gTower = {{0}};

static const u8 pool_ids[TOWER_POOL_SIZE] = TOWER_POOL_IDS;

/* A story's stage, as the campaign sets one: its scene package (the stone
 * frame's texture and its display object D_8009B2A0, the portraits, the
 * scene slots), then the scene by its image id (ScriptImage_RequestTransfer,
 * as Script_OpLoadImageScene loads one) and its display objects. Off: the
 * characters and the portrait gone at once (F6 id 82, func_80039FD4), the
 * scene's objects and the frame released, the title's wall back. The
 * caller fades around it. */
void Tower_Scene(s32 on, s32 image)   /* off: `image` 1 brings the wall back */
{
    s32 i;
    if (on) {
        Tower_Background(0);
        Campaign_LoadScenePackage(0);
        for (i = 0; i < (s32)sizeof(gTower.pool); i++) gTower.pool[i] = 0;   /* the story gives them */
        gTower.scene_on = 1;
        gTower.scene = (s16)image;
        ScriptImage_RequestTransfer((ScriptImageObjectSet *)D_800EAE98, image);
        File_WaitForTransfers();
        ScriptImage_RebuildObjects((ScriptImageObjectSet *)D_800EAE98, -1);
    } else {
        for (i = 0; i < 3; i++) {
            D_800EB010[i].display_effect_step = 0;
            func_80039FD4(&D_800EB010[i]);
        }
        ScriptImage_ReleaseObjects((ScriptImageObjectSet *)D_800EAE98);
        DisplayObject_ReleaseIfPresent(D_8009B2A0);
        D_8009B2A0 = 0;
        gGraphics_sViewportX = 0;
        gGraphics_sViewportY = 0;
        gTower.scene_on = 0;
        for (i = 0; i < (s32)sizeof(gTower.pool); i++) gTower.pool[i] = 0;
        if (image) Tower_Background(1);
    }
}

/* Whether a character is still coming in or going out (its display effect
 * step running). */
s32 Tower_SceneBusy(void)
{
    return D_800EB010[0].display_effect_step | D_800EB010[1].display_effect_step;
}

void Tower_SceneFrame(void)
{
    s32 side, k;
    SceneScript_UpdateSlots(D_800EAE98);
    /* "dim": a character that is not speaking (F6 id 21, the bit
     * DisplayEffect_UpdateMenuRecord keeps its mouth still by) drawn
     * darker, its objects' color as the game's grey (0x808080) is the
     * usual one. */
    for (side = 0; gTower.dim && side < 2; side++) {
        MenuRecord *record = &D_800EB010[side];
        u32 color = (record->field_32 & 0x10) ? 0x505050 : 0x808080;
        for (k = 0; k < 3; k++) {
            DisplayObject *object = (DisplayObject *G32)record->grid[0][k];
            if (object) object->field_0C = (object->field_0C & 0xFF000000u) | color;
        }
    }
}

/* ScriptImage_RequestTransfer: a mod's scene (TOWER_SCENE_ART up, ids that
 * are not BCD) put where a mode-0 record streams (VRAM words 0-127, rows
 * 256-511) in that record's layout -- the picture's left 256 texels in rows
 * 256-415, its right 64 in words 64-95 (rows 0-79) and 96-127 (rows 80-159)
 * of rows 416-495 -- and its colors in palette row 0 at (0, 240). Three
 * uploads of exactly the rectangles tower_art.c gave the texture pack. */
/* The uploads' sources are the game's memory, as the disc's are, so the
 * texture pack's tags of the words they replace are cleared or found by
 * their bytes (texture_dump.c), never left over from what was there. */
static u8 scene_tile[256 * 160];
static u8 scene_strip[64 * 80];
static u16 scene_clut[256];

s32 Tower_UploadScene(s32 id)
{
    u8 *tile = scene_tile, *strip = scene_strip;
    const u16 *clut;
    const u8 *texels;
    RECT rect;
    s32 y;
    if (!gTower.scene_on || id < TOWER_SCENE_ART || id >= TOWER_SCENE_ART + TOWER_SCENE_ARTS) return 0;
    texels = Tower_ArtScene(id - TOWER_SCENE_ART, &clut);
    if (!texels) return 1;   /* never the disc: these ids are no record of its */
    {
        for (y = 0; y < 160; y++) {
            s32 x;
            for (x = 0; x < 256; x++) tile[y * 256 + x] = texels[y * 320 + x];
        }
        rect.x = 0; rect.y = 256; rect.w = 128; rect.h = 160;
        LoadImage(&rect, (u32 *)tile);
        DrawSync(0);
    }
    for (y = 0; y < 2; y++) {
        s32 row, x;
        for (row = 0; row < 80; row++) {
            for (x = 0; x < 64; x++) strip[row * 64 + x] = texels[(row + y * 80) * 320 + 256 + x];
        }
        rect.x = (s16)(64 + y * 32); rect.y = 416; rect.w = 32; rect.h = 80;
        LoadImage(&rect, (u32 *)strip);
        DrawSync(0);
    }
    for (y = 0; y < 256; y++) scene_clut[y] = clut[y];
    rect.x = 0; rect.y = 240; rect.w = 256; rect.h = 1;
    LoadImage(&rect, (u32 *)scene_clut);
    DrawSync(0);
    return 1;
}

/* func_8003A560, before it reads character `id` off the disc: one the disc
 * keeps empty that a story gave a mod's picture (gTower.pool) is put in a
 * cache slot of D_80010000's, as the disc's are kept once read (the image,
 * the two palette rows, the parts bank), so the game finds it there and
 * draws it as it draws its own. A slot of a character on neither side is
 * the one taken. */
void Tower_FillCharacter(s32 id)
{
    DisplayEffectVramSlot *slots;
    const u16 *clut;
    const u8 *texels, *bank;
    s32 k, i, chosen = -1;
    if (!gTower.scene_on) return;
    for (k = 0; k < TOWER_POOL_SIZE && pool_ids[k] != id; k++) {}
    if (k == TOWER_POOL_SIZE || !gTower.pool[k]) return;
    texels = Tower_ArtCharacter(gTower.pool[k] - 1, &clut, &bank);
    if (!texels) return;
    for (i = 0; i < DISPLAY_EFFECT_VRAM_SLOT_COUNT; i++) {
        if (D_8015C410[i] == id) return;                     /* there already */
    }
    for (i = 0; i < DISPLAY_EFFECT_VRAM_SLOT_COUNT && chosen < 0; i++) {
        if (D_8015C410[i] < 0) chosen = i;
    }
    for (i = 0; i < DISPLAY_EFFECT_VRAM_SLOT_COUNT && chosen < 0; i++) {
        if (D_8015C410[i] != D_800EB010[0].field_30 && D_8015C410[i] != D_800EB010[1].field_30) chosen = i;
    }
    if (chosen < 0) return;
    slots = (DisplayEffectVramSlot *)D_80010000;
    for (i = 0; i < (s32)sizeof(slots[chosen].image); i++) slots[chosen].image[i] = texels[i];
    for (i = 0; i < (s32)sizeof(slots[chosen].clut); i++) slots[chosen].clut[i] = ((const u8 *)clut)[i];
    for (i = 0; i < (s32)sizeof(slots[chosen].extra); i++) slots[chosen].extra[i] = bank[i];
    D_8015C410[chosen] = (s8)id;
}

/* A box on text channel 0, its entries' layout reset first as the
 * campaign's dialogue does (Script_OpShowDialog): here because that reset
 * (func_8003B6AC) is still the game's own code, which only game code
 * reaches, as pack_shop_box.c says. */
void *Tower_CreateBox(s32 id, s32 x, s32 y, s32 width, s32 height, s32 flags)
{
    func_8003B6AC(0, 2);
    return TextBox_CreateFlagged(0, id, x, y, width, height, flags);
}

/* The title's wall behind the tower's screen: the main menu's own package
 * and background (MainMenu_DrawFrontendBackground in the frame services'
 * slot 0, where the title puts it), dimmed as behind the title's menus;
 * gone with the screen. The portraits' records are reset after the load, as
 * Main_RunMenu resets them after the same one. Game code, so the callback is
 * stored as the game stores one in every build. */
void Tower_Background(s32 on)
{
    if (on) {
        File_RequestMainMenuPackage();
        File_WaitForTransfers();
        func_80039E9C();
        D_80184597 = 0x80;
        D_800E9DB0[0] = MainMenu_DrawFrontendBackground;
    } else if (D_800E9DB0[0] == MainMenu_DrawFrontendBackground) {
        D_800E9DB0[0] = 0;
    }
}
