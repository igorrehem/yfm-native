#include "types.h"
#include "game/sound.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
extern s32 func_80045208(u16,s32);
extern void func_80045334(s32);
static SDCommand captured;
static int enqueues,resets,pans;
void func_800464F0(void) { resets++; }
void SD_ResetCdPan(void) { pans++; }
s32 SD_EnqueueCommand(SDCommand *command) { captured=*command; enqueues++;return 1; }
int main(void) {
 MemoriesMemory *memory=calloc(1,sizeof(*memory));assert(memory && !GuestRuntime_Bind(memory));
 SDValue *state=Memories_Resolve(memory,0x801e1618,sizeof(*state),4);
 u8 *global=Memories_Resolve(memory,0x8009b45c,4,4);assert(state&&global);Memories_WriteLE32(global,0x801e1618);
 state->flags_004A=0xc0;
 for(unsigned alias=0;alias<3;alias++) {
  u32 address=(u32[]){0x001c2000,0x801c2000,0xa01c2000}[alias];
  u8 *table=Memories_Resolve(memory,address,12,4);assert(table);
  Memories_WriteLE32(table,4);Memories_WriteLE32(table+4,0x230002);
  for(unsigned bank=0;bank<3;bank++)state->bank_0518[bank]=(u8 *G32)(uintptr_t)address;
  for(unsigned kind=0;kind<3;kind++) {
   u16 code=(u16)(0x8007+kind*0x1000);
   assert(func_80045208(code,0x80)==1);
   assert(captured.command==0x24 && captured.field_0002==7 && captured.field_0004==4);
   assert((u32)captured.field_000C==address+8 && captured.field_0008==(s32)(0x50+kind*0x10));
   func_80045334(code);assert(captured.command==0x21 && captured.field_0004==4);
   assert((u32)captured.field_000C==address+8 && Memories_ReadLE32(table+4)==0x230002);
  }
 }
 assert(enqueues==18 && resets==18 && pans==9);
 GuestRuntime_Reset();free(memory);puts("Real sound bank commands read four-byte table words across three guest aliases");return 0;
}
