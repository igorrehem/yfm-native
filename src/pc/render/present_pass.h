#ifndef MEMORIES_PC_RENDER_PRESENT_PASS_H
#define MEMORIES_PC_RENDER_PRESENT_PASS_H
/* The present pass: shader effects on the game picture as the window shows
 * it (the OpenGL presenter in sdl.c), under the menu and the HUD. With every
 * effect at its default the pass is not used at all, so the picture is drawn
 * with a plain sampling quad. present_pass.c lists the
 * effects. */

/* Whether any effect is on (the settings are read every frame). Called
 * for every present, so that the flash reduction knows when it was off. */
int PresentPass_Wanted(void);
/* Initialize the macOS core presenter, then draw clip-space quads with the
 * current effect program, or the plain sampler when no effect is bound. */
int PresentPass_InitCore(void);
void PresentPass_Quad(float x, float y, float w, float h, float s0, float t0, float s1, float t1);
/* Around the picture's quad: Begin binds the effect program for a picture
 * source_h texels high that the quad samples from the OpenGL texture
 * between coordinates (s0, t0) and (s1, t1), bound on the active unit or
 * not yet; End goes back to plain presentation. Begin returns 0 (and End is not
 * needed) when the program cannot be built; the quad then draws plainly.
 * textures_smoothed: the OpenGL picture drew its textures through xBR
 * already (gl_picture.c), so xBR is not done again here. */
int PresentPass_Begin(unsigned texture, int source_h, float s0, float t0, float s1, float t1,
                      int textures_smoothed);
void PresentPass_End(void);
#endif
