#include "pc/render/soft_gpu.h"
#include "pc/render/texture_dump.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
/* Texture-pack subsystem is disabled in this isolated raster test. */
int TextureDump_Enabled;
uint32_t *TextureDump_Tags;
uint16_t *TextureDump_Shadow;
int (*TextureDump_Prepare)(int,int,int,int,int,int,int);
int (*TextureDump_Sample)(int,int,int,int,int,uint32_t *);
void TextureDump_Init(void) {}
void TextureDump_Loaded(int x,int y,int w,int h,const uint16_t *p) {(void)x;(void)y;(void)w;(void)h;(void)p;abort();}
void TextureDump_Moved(int x,int y,int dx,int dy,int w,int h) {(void)x;(void)y;(void)dx;(void)dy;(void)w;(void)h;abort();}
void TextureDump_Cleared(int x,int y,int w,int h) {(void)x;(void)y;(void)w;(void)h;abort();}
void TextureDump_Primitive(const uint16_t *p,int a,int b,int c,int d,int e,int f,int g,int h,int i) {(void)p;(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;abort();}
#ifndef EXISTING_RASTER_TEST
int main(void) {
 MemoriesMemory *memory=calloc(1,sizeof(*memory)); assert(memory && !GuestRuntime_Bind(memory));
 uint16_t pixels[]={0x1234,0x5678,0x7abc,0x4321}, readback[4];
 for(unsigned bank=0;bank<3;bank++) {
  uint32_t address=(uint32_t[]){0x00020000,0x80020000,0xa0020000}[bank];
  void *upload=Memories_Resolve(memory,address,sizeof(pixels),2); assert(upload); memcpy(upload,pixels,sizeof(pixels));
  SoftGpu_Reset(); SoftGpu_Load(10,12,2,2,(const uint16_t *)(uintptr_t)address);
  SoftGpu_Store(10,12,2,2,readback); assert(!memcmp(readback,pixels,sizeof(pixels)));
  memset(upload,0,sizeof(pixels)); SoftGpu_Store(10,12,2,2,(uint16_t *)(uintptr_t)address); assert(!memcmp(upload,pixels,sizeof(pixels)));
  uint32_t *commands=Memories_Resolve(memory,address,12,4); assert(commands);
  commands[0]=0x020000ff; commands[1]=20u|(20u<<16); commands[2]=16u|(1u<<16);
  assert(SoftGpu_Gp0((const uint32_t *)(uintptr_t)address,3)==3);
  assert(SoftGpu_Vram()[20*1024+20]==31);
  SoftGpu_StateWords((uint32_t *)(uintptr_t)address); assert((commands[0]>>24)==0xe1);
 }
 /* Deterministic mixed textured sprites, blended rectangles, triangles,
    clipping and mask writes. Hash every VRAM pixel for differential runs. */
 SoftGpu_Reset();
 uint32_t setup[]={0xe3000000u,0xe4000000u|1023u|(511u<<10),0xe1000100u};
 SoftGpu_Gp0(setup,3);
 uint16_t texture[32*32]; unsigned random=0x19a723u;
 for(unsigned i=0;i<32*32;i++){random=random*1664525u+1013904223u;texture[i]=(uint16_t)(random>>16);}
 SoftGpu_Load(0,0,32,32,texture);
 for(unsigned i=0;i<512;i++) {
  random=random*1664525u+1013904223u; uint32_t x=64+(random&511), y=64+((random>>10)&255);
  uint32_t xy=x|(y<<16), color=random&0xffffffu;
  uint32_t packet[4];
  if(i%3==0){packet[0]=0x64808080u;packet[1]=xy;packet[2]=(random&15u)|(((random>>8)&15u)<<8);packet[3]=16u|(16u<<16);}
  else if(i%3==1){packet[0]=0x62000000u|color;packet[1]=xy;packet[2]=24u|(12u<<16);}
  else{packet[0]=0x20000000u|color;packet[1]=xy;packet[2]=(x+20)|((y+2)<<16);packet[3]=(x+7)|((y+17)<<16);}
  if(i%17==0){uint32_t mask=0xe6000000u|((i>>4)&3);SoftGpu_Gp0(&mask,1);}
  SoftGpu_Gp0(packet,i%3==1?3:4);
 }
 uint64_t hash=1469598103934665603ULL;
 for(unsigned i=0;i<1024*512;i++){hash^=SoftGpu_Vram()[i];hash*=1099511628211ULL;}
 printf("Seeded full VRAM hash: %016llx\n",(unsigned long long)hash);
 GuestRuntime_Reset(); free(memory); puts("Native raster boundary: three guest aliases upload/readback/GP0/state words passed"); return 0;
}
#endif
