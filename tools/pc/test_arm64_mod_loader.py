#!/usr/bin/env python3
"""ROM-free Darwin loader checks with translated storage and repeated cleanup."""

import argparse
import os
import subprocess

from guest_build import darwin_flags, guest_frontend_flags
from llvm_guest import ROOT, normalize, process, toolchain
from macos_deps import sdk_path


def build_fixture(folder, compiler, sdk):
    raw = folder / "fixture.raw.ll"
    subprocess.run(
        [
            compiler,
            *guest_frontend_flags(sdk),
            "-S",
            "-emit-llvm",
            str(ROOT / "tests/pc/mod_loader_fixture.c"),
            "-o",
            str(raw),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    ir = folder / "fixture.ll"
    ir.write_text(
        process(
            "translate",
            normalize(raw.read_text()),
            mod_unit=True,
            registration="register_fixture",
        )
    )
    registration = folder / "registration.c"
    registration.write_text(
        "extern void register_fixture(void), register_fixture_Unregister(void);\n"
        "void MemoriesModRegisterGlobals(void) { register_fixture(); }\n"
        "void MemoriesModUnregisterGlobals(void) { register_fixture_Unregister(); }\n"
    )
    library = folder / "fixture.dylib"
    subprocess.run(
        [
            compiler,
            *darwin_flags(sdk),
            "-O2",
            "-dynamiclib",
            "-Wl,-undefined,dynamic_lookup",
            str(ir),
            str(registration),
            "-o",
            str(library),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    # An actual ELF object, without libc or retail inputs, exercises the
    # architecture rejection independently of the malformed-file case.
    elf_source = folder / "elf.c"
    elf_source.write_text("int fixture(void) { return 7; }\n")
    elf = folder / "fixture.o"
    subprocess.run(
        [
            compiler,
            "--target=i386-pc-linux-gnu",
            "-ffreestanding",
            "-c",
            str(elf_source),
            "-o",
            str(elf),
        ],
        check=True,
        timeout=60,
    )
    invalid = folder / "invalid.dylib"
    invalid.write_bytes(b"bad")
    return library, elf, invalid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    folder = ROOT / "tmp/arm64-mod-loader"
    folder.mkdir(parents=True, exist_ok=True)
    compiler = str(toolchain() / "bin/clang")
    sdk = sdk_path()
    library, elf, invalid = build_fixture(folder, compiler, sdk)
    # Host-only harness: Apple's runtime avoids LLVM 21's pre-main ASan hang.
    host_compiler = os.environ.get("CC") or (
        "/usr/bin/clang" if args.sanitize else compiler
    )
    exports = [
        "GuestRuntime_ResolveData",
        "GuestRuntime_ResolveFunction",
        "GuestRuntime_EncodePointer",
        "GuestRuntime_RegisterGlobal",
        "GuestRuntime_UnregisterData",
    ]
    binary = folder / "contract"
    flags = (
        ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        if args.sanitize
        else []
    )
    subprocess.run(
        [
            host_compiler,
            *darwin_flags(sdk),
            "-O2",
            *flags,
            "-DMEMORIES_TRANSLATED",
            "-Isrc",
            "tests/pc/mod_loader_test.c",
            "src/pc/mods/object_loader.c",
            "src/pc/guest/translated_runtime.c",
            "src/pc/guest/state_io.c",
            "src/pc/memory.c",
            *["-Wl,-exported_symbol,_" + name for name in exports],
            "-Wl,-dead_strip",
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    subprocess.run(
        [str(binary), str(library), str(elf), str(invalid)], check=True, timeout=30
    )
    print(
        "ARM64 loader: translated storage, entry call, ELF/truncated rejection and repeated cleanup passed"
    )


if __name__ == "__main__":
    main()
