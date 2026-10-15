#!/usr/bin/env python3
"""ROM-free execution check of typed ARM64 wrappers and hook lifecycle."""

import argparse
import subprocess
import sys

from guest_test_compile import guest_object, host_compiler
from llvm_guest import ROOT, process, toolchain
from macos_deps import sdk_path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sanitize", action="store_true")
args = parser.parse_args()
folder = ROOT / "tmp/arm64-mod-hooks"
folder.mkdir(parents=True, exist_ok=True)
source = folder / "probe.c"
source.write_text(
    "double target(int a, double b, void *p) { return a + b + *(int *)p; }\n"
)
compiler = str(toolchain() / "bin/clang")
raw = folder / "probe.raw.ll"
subprocess.run(
    [compiler, "-O0", "-S", "-emit-llvm", str(source), "-o", str(raw)], check=True
)
ir = folder / "probe.ll"
ir.write_text(
    process("translate", raw.read_text(), hooks=True, registration="register_probe")
)
harness = folder / "harness.c"
harness.write_text(r"""#include "pc/mods/hooks.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdlib.h>
static int active[2] = {1,1};
int Mods_Active(int owner) { return active[owner]; }
extern double target(int, double, void *);
extern void register_probe(void);
static double (*first)(int,double,void *), (*second)(int,double,void *);
static double plus(int a,double b,void *p) { return first(a,b,p)+10; }
static double twice(int a,double b,void *p) { return second(a,b,p)*2; }
int main(void) {
    MemoriesMemory *memory=calloc(1,sizeof(*memory));
    assert(!GuestRuntime_Bind(memory)); register_probe();
    int value=3;
    assert(target(2,0.5,&value)==5.5);
    assert(!Hooks_Add(0,(void *)main,(void *)plus,(void **)&first));
    int token=Hooks_Add(0,(void *)target,(void *)plus,(void **)&first);
    assert(token && target(2,0.5,&value)==15.5);
    assert(Hooks_Add(1,(void *)target,(void *)twice,(void **)&second));
    assert(target(2,0.5,&value)==31);
    active[0]=0; Hooks_Relink(); assert(target(2,0.5,&value)==11);
    active[1]=0; Hooks_Relink(); assert(target(2,0.5,&value)==5.5);
    assert(!Hooks_IsHooked((void *)target));
    active[0]=active[1]=1; Hooks_Relink(); assert(target(2,0.5,&value)==31);
    Hooks_Remove(0,token); assert(target(2,0.5,&value)==11);
    Hooks_Clear(1); assert(target(2,0.5,&value)==5.5);
    GuestRuntime_Reset(); free(memory);
}""")
guest = guest_object(ir, folder / "guest.o", ["-isysroot", str(sdk_path()), "-O2"])
subprocess.run(
    [
        host_compiler(sanitize=args.sanitize),
        "-isysroot",
        str(sdk_path()),
        "-O2",
        *(
            ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            if args.sanitize
            else []
        ),
        "-DMEMORIES_TRANSLATED",
        "-Isrc",
        guest,
        str(harness),
        "src/pc/mods/hooks.c",
        "src/pc/guest/translated_runtime.c",
        "src/pc/guest/state_io.c",
        "src/pc/memory.c",
        "-Wl,-dead_strip",
        "-o",
        str(folder / "contract"),
    ],
    cwd=ROOT,
    check=True,
)
result = subprocess.run(
    [str(folder / "contract")], check=True, timeout=30, capture_output=True, text=True
)
if result.stdout:
    print(result.stdout, end="")
if result.stderr:
    print(result.stderr, end="", file=sys.stderr)
print(
    "ARM64 typed hooks: chaining, originals, disable/reapply, removal and unregistered rejection passed"
)
