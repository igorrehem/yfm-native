/* What src/game/duel_result_runtime.c refers to besides Duel_CalcRankScore's
 * own records (rank_test.c defines those). The rank test never runs these:
 * the linker only needs the names, so no game header is included here. */
#include <stdlib.h>

#define STUB(name) void name(void); void name(void) { abort(); }

/* These two the unit really calls, so they answer rather than abort: no
 * duelist mod, which is what the cases compare the game's own arithmetic
 * against (pc/free_duel/duelists.h, pc/cards/tables.h). */
int Duelists_BaseId(int duelist);
int Duelists_BaseId(int duelist) { return duelist; }
const short *Tables_Rank(int rule);
const short *Tables_Rank(int rule) { (void)rule; return 0; }   /* the disc's own row stands */
long Tables_Value(int which, long retail);
long Tables_Value(int which, long retail) { (void)which; return retail; }   /* no mod's "limits" */
int Tables_RankAdjustment(int tag);
int Tables_RankAdjustment(int tag) { return tag; }

STUB(CardDrops_ComposePage) STUB(Cards_ChestSlot) STUB(Cards_PickVariant) STUB(Cards_Valid)
STUB(DisplayObject_AcquireSlot) STUB(DisplayObject_ConfigureSpriteAtPositionWithResource)
STUB(DisplayObject_FadeBrightnessAndRelease) STUB(DisplayObject_FindAllocatedByTag)
STUB(DisplayObject_FindFreeGeneralSlot) STUB(DisplayObject_MarkInitialized) STUB(DisplayObject_ReleaseIfPresent)
STUB(DisplayObject_SelectOrderingTable1) STUB(DisplayObject_SetDepthOffset) STUB(DisplayObject_SetResourceVariant)
STUB(File_RequestAsyncTransfer) STUB(Mods_Dispatch) STUB(Rand_GetInterval) STUB(SD_BGMFadeOut) STUB(SD_BGMPlay)
STUB(SD_GetStatusFlags) STUB(StarchipPrize_Counted) STUB(Tables_ChestFull) STUB(Tables_ChestLimit) STUB(Tables_ChestOverflow) STUB(Tables_ChestRoom) STUB(Tables_Pool) STUB(TextBox_Create) STUB(TextBox_Destroy) STUB(func_8001EC70) STUB(func_80020BE4)
STUB(func_80039A14) STUB(func_800472A8) STUB(rcos) STUB(rsin)

/* Sized generously: only their names are used. */
#define DATA(name) unsigned char name[0x1000];
DATA(D_80090928) DATA(D_80090960) DATA(D_800EB0F8) DATA(D_8009B0CC) DATA(D_8009B0F4_abs) DATA(D_8009B134_abs) DATA(D_8009B162)
DATA(D_8009B174) DATA(D_8009B1D0) DATA(D_8009B1E0) DATA(D_8009B214) DATA(D_8009B21C) DATA(D_8009B238)
DATA(D_8009B362) DATA(D_801AF000) DATA(gCard_nCount) DATA(gDuel_awPlayerDeck) DATA(gDuel_awRitualData)
DATA(gDuel_awSaPowCardDrops) DATA(gDuel_bOpponentID) DATA(gDuel_wSceneStateFlags) DATA(gFade_State)
DATA(gInput_wPad1Pressed)
