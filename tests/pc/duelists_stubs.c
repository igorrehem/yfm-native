/* The duelist list (src/pc/free_duel/duelists.h) as a run with no duelist mod:
 * the forty the disc lays out, no roster folders, page 0. tables.c asks it what
 * a name reaches and how many duelists there are, and free_duel_progress.c
 * asks which duelist a cell stands for, so every test that links either needs
 * these names. The cases that are about the list itself are pc_duelists, which
 * links the real thing.
 *
 * Tables_DuelistNames comes from tables.c, which each of those tests includes.
 */
#include "pc/cards/tables.h"
#include <stdlib.h>
#include <string.h>

/* Letters and digits only, either case, as the list compares a name. */
static int stub_same_letters(const char *a, const char *b)
{
    while (*a && *b) {
        while (*a && !((*a >= '0' && *a <= '9') || (*a >= 'A' && *a <= 'Z') || (*a >= 'a' && *a <= 'z'))) a++;
        while (*b && !((*b >= '0' && *b <= '9') || (*b >= 'A' && *b <= 'Z') || (*b >= 'a' && *b <= 'z'))) b++;
        if (!*a || !*b) break;
        if ((*a | 0x20) != (*b | 0x20)) return 0;
        a++;
        b++;
    }
    while (*a && !((*a >= '0' && *a <= '9') || (*a >= 'A' && *a <= 'Z') || (*a >= 'a' && *a <= 'z'))) a++;
    while (*b && !((*b >= '0' && *b <= '9') || (*b >= 'A' && *b <= 'Z') || (*b >= 'a' && *b <= 'z'))) b++;
    return !*a && !*b;
}

int Duelists_Count(void) { return TABLES_DUELIST_COUNT; }
int Duelists_Valid(int duelist) { return duelist >= 0 && duelist < TABLES_DUELIST_COUNT; }
int Duelists_BaseId(int duelist) { return Duelists_Valid(duelist) ? duelist : 0; }
int Duelists_AtCell(int cell) { return cell; }                 /* page 0 */
int Duelists_Available(int duelist) { return Duelists_Valid(duelist); }
int Duelists_Find(const char *identity) { (void)identity; return -1; }   /* no mod added one */

const char *Duelists_Name(int duelist)
{
    return Tables_DuelistNames[Duelists_Valid(duelist) ? duelist : 0];
}

int Duelists_Named(const char *text)
{
    int id;
    if (!text || !*text) return -1;
    if (strspn(text, "0123456789") == strlen(text)) return Duelists_Valid(id = atoi(text)) ? id : -1;
    for (id = 0; id < TABLES_DUELIST_COUNT; id++) {
        if (stub_same_letters(text, Tables_DuelistNames[id])) return id;
    }
    return -1;
}

/* No mod has a directory here, so the pool folders are never read. */
const char *Mods_Directory(int mod) { (void)mod; return NULL; }
int Paths_Contained(const char *path) { (void)path; return 1; }
const char *Paths_UserDir(void) { return NULL; }
