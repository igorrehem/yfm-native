/* Compile against generated headers, never change original console sources. */
#include "game/file_names.h"
_Static_assert(sizeof(gFile_apszName[0]) == 4, "retail filename table pointer width");
_Static_assert(sizeof(gFile_apszName) == 32, "eight retail filename pointers");
int main(void) { return 0; }
