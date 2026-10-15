#ifndef MEMORIES_CONTROLS_RUNTIME_H
#define MEMORIES_CONTROLS_RUNTIME_H
#include "controls.h"
#define CONTROLS_DEVICES 32
/* Registry slots are session handles, never serialized. */
typedef struct {
    int connected, ambiguous;
    char identity[CTRL_IDENTITY_MAX], name[160];
    CtrlIconStyle style;
    ControllerSnapshot snapshot;
    float threshold;
} ControllerDevice;
void ControlsRuntime_Init(void);
uint64_t ControlsRuntime_Now(void);
const ControlsConfig *ControlsRuntime_Config(void);
int ControlsRuntime_Apply(const ControlsConfig *cfg, char *error, unsigned size);
const char *ControlsRuntime_Error(void);
ControllerDevice *ControlsRuntime_Device(int index);
int ControlsRuntime_Assigned(const ControlsConfig *cfg, int port);
void ControlsRuntime_Reconcile(void);
ControlsProfile *ControlsRuntime_Profile(ControlsConfig *cfg, int port, int create);
CtrlIconStyle *ControlsRuntime_Style(ControlsConfig *cfg, int port, int create);
void ControlsRuntime_Key(int key, int down);
void ControlsRuntime_ResetKeys(void);
int ControlsRuntime_Keys(ControlSource *out);
void ControlsRuntime_Block(int block);
void ControlsRuntime_Gate(void);
int ControlsRuntime_Blocked(void);
/* Keep the game's input at rest (the menu's notice has it) without touching
 * the Controls window's block; releasing waits for neutral, like a block. */
void ControlsRuntime_Hold(int hold);
/* Pad buttons newly pressed on either controller since the last call, also
 * while input is held: what answers a notice from a controller. */
uint16_t ControlsRuntime_TakePadPresses(void);
/* Host actions pressed since the last call, bit 1 << CTRL_HOST_*: one per
 * press (and, for repeating ones, again while held), none while input is
 * blocked. */
uint32_t ControlsRuntime_TakeHost(void);
/* Host actions held at the last update, 0 while input is blocked:
 * what a hold action (Turbo) follows. */
uint32_t ControlsRuntime_HostHeld(void);
/* The physical key is down (CTRL_KEY_*), whatever it is bound to. */
int ControlsRuntime_KeyDown(int key);
uint16_t ControlsRuntime_Keyboard(void);
uint16_t ControlsRuntime_Pad(int port);
int ControlsRuntime_Connected(int port);
void ControlsRuntime_Update(void);
/* Snapshot source enumeration uses release threshold for neutral gating. */
int ControlsRuntime_Sources(const ControllerDevice *device, ControlSource *out, int capacity, int neutral);
#endif
