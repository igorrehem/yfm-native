#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "pc/guest/image.h"
static unsigned calls;
static int16_t SignedSmall(int8_t a, int16_t b) {
    assert(a==-1 && b==-2); calls++; return -3;
}
static void Model_QueueTintRequest(uint32_t slot, uint32_t selection,
                                  uint64_t start, uint64_t end,
                                  uint32_t duration, void *mask) {
    assert(slot==1 && selection==2 && start==0x030201 && end==0x060504);
    assert(duration==17 && (uintptr_t)mask==0x80123456); calls++;
}
static void GsSetAmbient(uint32_t a, uint32_t b, uint32_t c) {
    assert(a==UINT32_MAX && b==0 && c==0x1234); calls++;
}
static uint64_t StartRCnt(uint64_t spec) {
    assert(spec==0xf2000002u); calls++; return 1;
}
static void *PointerResult(void) { return (void *)(uintptr_t)0x123456789abcULL; }
uint32_t GuestRuntime_EncodePointer(void *p) {
    assert(p == (void *)(uintptr_t)0x123456789abcULL); return 0x80123456;
}
static uint32_t TenPointers(void *a, void *b, void *c, void *d, void *e,
                           void *f, void *g, void *h, void *i, void *j) {
    void *p[] = {a,b,c,d,e,f,g,h,i,j};
    for (unsigned k=0;k<10;k++) assert((uintptr_t)p[k] == 0x9ff30000u + k*4);
    calls++; return 0x76543210;
}
static uint32_t Mixed(uint32_t a, void *b, uint8_t c, uint16_t d, void *e,
                      uint32_t f, void *g, uint32_t h, uint32_t i, void *j,
                      uint16_t k, void *l) {
    assert(a==1 && (uintptr_t)b==2 && c==3 && d==4 && (uintptr_t)e==5);
    assert(f==6 && (uintptr_t)g==7 && h==8 && i==9 && (uintptr_t)j==10);
    assert(k==11 && (uintptr_t)l==12); calls++; return 0xfedcba98;
}
const MemoriesGuestFunction Memories_FunctionMap[] = {
    {1,(void (*)(void))TenPointers,0,0},
    {2,(void (*)(void))Mixed,0,0},
    {3,(void (*)(void))PointerResult,0,0},
    {4,(void (*)(void))Model_QueueTintRequest,0,0},
    {5,(void (*)(void))GsSetAmbient,0,0},
    {6,(void (*)(void))StartRCnt,0,0},
    {7,(void (*)(void))SignedSmall,0,0},
};
#include "calls.inc"
int main(void) {
    uint32_t a[12];
    for (unsigned i=0;i<12;i++) a[i]=0x9ff30000u+i*4;
    assert(GuestRuntime_InvokeNative(0,a)==0x76543210);
    for (unsigned i=0;i<12;i++) a[i]=i+1;
    assert(GuestRuntime_InvokeNative(1,a)==0xfedcba98);
    assert(GuestRuntime_InvokeNative(2,a)==0x80123456);
    a[0]=1; a[1]=2; a[2]=0x030201; a[3]=0x060504; a[4]=17; a[5]=0x80123456;
    assert(GuestRuntime_InvokeNative(3,a)==0);
    a[0]=0xffffffff; a[1]=0; a[2]=0x1234;
    assert(GuestRuntime_InvokeNative(4,a)==0);
    a[0]=0xf2000002;
    assert(GuestRuntime_InvokeNative(5,a)==1);
    a[0]=0xff; a[1]=0xfffe;
    assert(GuestRuntime_InvokeNative(6,a)==0xfffffffdu);
    assert(calls==6); puts("Typed native calls: pointer stack, mixed widths, signed small values, colors, longs and pointer return pass");
}
