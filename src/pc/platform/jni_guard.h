#ifndef MEMORIES_PC_PLATFORM_JNI_GUARD_H
#define MEMORIES_PC_PLATFORM_JNI_GUARD_H
/* Android: the SDL calls that may reach Java (JNI), each checked against the
 * game stack before it runs. ART refuses JNI from a native stack it does
 * not know, as the game stack at 0xB0000000 is (a StackOverflowError, the
 * method skipped, or with CheckJNI an abort on the next call), so the
 * platform entry points the game thread calls run their SDL work on the
 * thread's own stack (Memories_OnHostStack, sdl.c's HERE). A call listed
 * here that still runs on the game stack is logged once by name
 * (Memories_JniGuard, state.c: "... which may call Java, ran on the game
 * stack") and counted, so a new path that misses the wrapper shows in
 * logcat and in MEMORIES_TEST_JAVA's report instead of failing on some
 * phones only.
 *
 * Included after <SDL3/SDL.h> by sdl.c and android.c, the units that call
 * SDL functions that may reach Java on Android (gl_picture.c and
 * present_pass.c call SDL_GL_GetProcAddress and SDL_GetTicksNS, which do
 * not). Android arm64 only: the x86 development build has no stack switch
 * (Memories_OnHostStack is a plain call there), so every call it makes
 * from the game thread is on the game stack and the check would only say
 * so. The list: SDL3's Android code (SDL_android.c) and what
 * reaches it: events and joysticks (Android_JNI_PollInputDevices), the
 * window's mode and title, the cursor, the clipboard, message boxes, URLs,
 * text input, gamepads and rumble, audio devices, file dialogs, the app's
 * storage paths and files opened through SDL, SDL's own set-up, and the
 * JNI environment and activity our own Java calls start from (android.c). */
#if defined(SDL_PLATFORM_ANDROID) && defined(__aarch64__)
#include "pc/guest/state.h"

#define MEMORIES_JNI(name, ...) (Memories_JniGuard(#name), name(__VA_ARGS__))
#define SDL_PollEvent(...) MEMORIES_JNI(SDL_PollEvent, __VA_ARGS__)
#define SDL_PumpEvents(...) MEMORIES_JNI(SDL_PumpEvents, __VA_ARGS__)
#define SDL_WaitEvent(...) MEMORIES_JNI(SDL_WaitEvent, __VA_ARGS__)
#define SDL_WaitEventTimeout(...) MEMORIES_JNI(SDL_WaitEventTimeout, __VA_ARGS__)
#define SDL_UpdateJoysticks(...) MEMORIES_JNI(SDL_UpdateJoysticks, __VA_ARGS__)
#define SDL_UpdateGamepads(...) MEMORIES_JNI(SDL_UpdateGamepads, __VA_ARGS__)
#define SDL_SetWindowFullscreen(...) MEMORIES_JNI(SDL_SetWindowFullscreen, __VA_ARGS__)
#define SDL_SetWindowFullscreenMode(...) MEMORIES_JNI(SDL_SetWindowFullscreenMode, __VA_ARGS__)
#define SDL_SetWindowTitle(...) MEMORIES_JNI(SDL_SetWindowTitle, __VA_ARGS__)
#define SDL_SetWindowSize(...) MEMORIES_JNI(SDL_SetWindowSize, __VA_ARGS__)
#define SDL_SetWindowPosition(...) MEMORIES_JNI(SDL_SetWindowPosition, __VA_ARGS__)
#define SDL_SetWindowBordered(...) MEMORIES_JNI(SDL_SetWindowBordered, __VA_ARGS__)
#define SDL_RaiseWindow(...) MEMORIES_JNI(SDL_RaiseWindow, __VA_ARGS__)
#define SDL_MinimizeWindow(...) MEMORIES_JNI(SDL_MinimizeWindow, __VA_ARGS__)
#define SDL_ShowCursor(...) MEMORIES_JNI(SDL_ShowCursor, __VA_ARGS__)
#define SDL_HideCursor(...) MEMORIES_JNI(SDL_HideCursor, __VA_ARGS__)
#define SDL_SetCursor(...) MEMORIES_JNI(SDL_SetCursor, __VA_ARGS__)
#define SDL_SetClipboardText(...) MEMORIES_JNI(SDL_SetClipboardText, __VA_ARGS__)
#define SDL_GetClipboardText(...) MEMORIES_JNI(SDL_GetClipboardText, __VA_ARGS__)
#define SDL_ShowSimpleMessageBox(...) MEMORIES_JNI(SDL_ShowSimpleMessageBox, __VA_ARGS__)
#define SDL_ShowMessageBox(...) MEMORIES_JNI(SDL_ShowMessageBox, __VA_ARGS__)
#define SDL_OpenURL(...) MEMORIES_JNI(SDL_OpenURL, __VA_ARGS__)
#define SDL_StartTextInput(...) MEMORIES_JNI(SDL_StartTextInput, __VA_ARGS__)
#define SDL_StopTextInput(...) MEMORIES_JNI(SDL_StopTextInput, __VA_ARGS__)
#define SDL_OpenGamepad(...) MEMORIES_JNI(SDL_OpenGamepad, __VA_ARGS__)
#define SDL_CloseGamepad(...) MEMORIES_JNI(SDL_CloseGamepad, __VA_ARGS__)
#define SDL_RumbleGamepad(...) MEMORIES_JNI(SDL_RumbleGamepad, __VA_ARGS__)
#define SDL_OpenAudioDeviceStream(...) MEMORIES_JNI(SDL_OpenAudioDeviceStream, __VA_ARGS__)
#define SDL_ShowOpenFileDialog(...) MEMORIES_JNI(SDL_ShowOpenFileDialog, __VA_ARGS__)
#define SDL_GetAndroidInternalStoragePath(...) MEMORIES_JNI(SDL_GetAndroidInternalStoragePath, __VA_ARGS__)
#define SDL_GetAndroidExternalStoragePath(...) MEMORIES_JNI(SDL_GetAndroidExternalStoragePath, __VA_ARGS__)
#define SDL_GetAndroidCachePath(...) MEMORIES_JNI(SDL_GetAndroidCachePath, __VA_ARGS__)
#define SDL_GetAndroidJNIEnv(...) MEMORIES_JNI(SDL_GetAndroidJNIEnv, __VA_ARGS__)
#define SDL_GetAndroidActivity(...) MEMORIES_JNI(SDL_GetAndroidActivity, __VA_ARGS__)
#define SDL_IOFromFile(...) MEMORIES_JNI(SDL_IOFromFile, __VA_ARGS__)
#define SDL_LoadFile(...) MEMORIES_JNI(SDL_LoadFile, __VA_ARGS__)
#define SDL_InitSubSystem(...) MEMORIES_JNI(SDL_InitSubSystem, __VA_ARGS__)
#define SDL_CreateWindow(...) MEMORIES_JNI(SDL_CreateWindow, __VA_ARGS__)
#endif
#endif
