/* Included first in every native unit of the Android build
 * (tools/pc/build_game32.py): what bionic lacks at the API level the build
 * targets (tools/pc/build_android_deps.py, API). No system header here: the
 * units choose their feature macros (_GNU_SOURCE) before their first one,
 * and bionic leaves out the declarations of what the API level does not
 * have, so these names are free. clang defines __ANDROID_API__ from the
 * target. */
#ifndef MEMORIES_PC_COMPAT_ANDROID_H
#define MEMORIES_PC_COMPAT_ANDROID_H
#if defined(__ANDROID__) && !defined(__ASSEMBLER__) /* also given to the .S units */

#if __ANDROID_API__ < 30
/* memfd_create's wrapper arrived in API 30; the system call is older than
 * every Android the port runs on (Linux 3.17). android.c. */
int memories_memfd_create(const char *name, unsigned flags);
#define memfd_create memories_memfd_create
#endif
/* Where the kernel predates memfd (Linux 3.17: Android 7 and 8 devices, and
 * phones that stayed on a 3.10 kernel), shared memory of `size` bytes from the ashmem
 * device, which takes its size from an ioctl instead of ftruncate. -1 when
 * that fails too. android.c; image.c uses it for guest RAM. */
int memories_ashmem_create(const char *name, unsigned size);

#if __ANDROID_API__ < 28
/* No iconv before API 28, and bionic's has no Shift-JIS anyway: the one user
 * (libapi_krom.c, the kanji ROM) falls back to what it shows without it.
 * iconv_t comes from <iconv.h>, which that unit includes. */
#define iconv_open(to, from) ((iconv_t)-1)
#define iconv(cd, in, in_left, out, out_left) ((size_t)-1)
#define iconv_close(cd) 0
#endif

#endif
#endif
