#include "pc/guest/function_map.h"
#include <assert.h>
#include <stdio.h>

static unsigned resident;
static void first(void) { }
static void second(void) { }
const MemoriesGuestFunction Memories_FunctionMap[] = {
    {0x80010000u, first, 0, 0},
    {0x80100000u, first, 1, 7},
    {0x80100000u, second, 1, 9},
    {0x80100000u, first, 2, 3},
    {0x80110000u, second, 0, 0},
};
const unsigned Memories_FunctionMapCount = 5;
int Memories_ModuleIsResident(unsigned bank, unsigned identifier)
{
    return !bank || (bank == 1 && identifier == resident);
}
int main(void)
{
    assert(Memories_FindResidentFunction(0x80010000u)->host == first);
    assert(Memories_FindResidentFunction(0x80110000u)->host == second);
    assert(!Memories_FindResidentFunction(0x80000000u));
    assert(!Memories_FindResidentFunction(0x80010004u));
    assert(!Memories_FindResidentFunction(0xffffffffu));
    assert(!Memories_FindResidentFunction(0x80100000u));
    for (unsigned i = 0; i < 8; ++i) {
        resident = 7;
        assert(Memories_FindResidentFunction(0x80100000u) == &Memories_FunctionMap[1]);
        resident = 9;
        assert(Memories_FindResidentFunction(0x80100000u) == &Memories_FunctionMap[2]);
        resident = 0;
        assert(!Memories_FindResidentFunction(0x80100000u));
    }
    puts("Translated function map: exact bounds and shared-address overlay switches passed");
    return 0;
}
