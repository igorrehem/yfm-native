/* pc_scratch_sweep: CTest runs it after the other tests (a FIXTURES_CLEANUP
 * in CMakeLists.txt), when none of their processes holds a file open any
 * more, and it removes the scratch folders they could not (scratch.h). */
#define _POSIX_C_SOURCE 200809L
#include "scratch.h"

int main(void)
{
    int removed = scratch_sweep(NULL, stdout);
    printf("scratch sweep: removed %d in %s\n", removed, scratch_base());
    return 0;
}
