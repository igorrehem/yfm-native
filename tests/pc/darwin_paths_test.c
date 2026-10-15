/* Run as separate processes because path roots are intentionally cached. */
#include "pc/platform/paths.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv)
{
    const char *program, *user;
    assert(argc == 3);
    program = Paths_ProgramDir();
    if (strcmp(program, argv[1])) fprintf(stderr, "program dir: got '%s', expected '%s'\n", program, argv[1]);
    assert(!strcmp(program, argv[1]));
    user = Paths_UserDir();
    if (strcmp(user, argv[2])) fprintf(stderr, "user dir: got '%s', expected '%s'\n", user, argv[2]);
    assert(!strcmp(user, argv[2]));
    puts("Darwin executable and user paths passed");
}
