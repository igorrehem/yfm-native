/* ROM-free translated storage fixture for the Darwin object loader. */
#include "pc/mods/modapi.h"

static int value = 7;

int MemoriesModInit(const MemoriesModHost *host, MemoriesMod *mod)
{
    (void)host;
    (void)mod;
    return value;
}
