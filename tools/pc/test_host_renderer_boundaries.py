#!/usr/bin/env python3
"""Compare native and translated SoftGpu against the same raster regressions."""

import argparse
import os
import subprocess

from guest_build import darwin_flags
from guest_test_compile import guest_object
from llvm_guest import ROOT, toolchain, translate
from macos_deps import sdk_path

SOFT_GPU = "src/pc/render/soft_gpu.c"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--instrumented", action="store_true")
    parser.add_argument("--differential", action="store_true")
    args = parser.parse_args()
    out = ROOT / "tmp/host-renderer"
    out.mkdir(parents=True, exist_ok=True)
    flags = [
        *darwin_flags(sdk_path()),
        "-O2",
        "-std=c11",
        "-DMEMORIES_PC",
        "-DMEMORIES_TRANSLATED",
        "-fms-extensions",
        "-I" + str(ROOT / "src"),
        "-I" + str(ROOT / "src/pc/render"),
    ]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    native = ROOT / SOFT_GPU
    sources = [native]
    if args.instrumented or args.differential:
        frontend = [flag for flag in flags if not flag.startswith("-fsanitize=")]
        raw = out / "soft_gpu.raw.ll"
        subprocess.run(
            [
                str(toolchain() / "bin/clang"),
                *frontend,
                "-O0",
                "-DMEMORIES_INSTRUMENT_SOFTGPU",
                "-S",
                "-emit-llvm",
                str(native),
                "-o",
                str(raw),
            ],
            check=True,
            timeout=60,
        )
        instrumented = out / "soft_gpu.instrumented.ll"
        instrumented.write_text(translate(raw.read_text()))
        sources = [native, instrumented] if args.differential else [instrumented]
    compiler = os.environ.get("CC") or (
        "/usr/bin/clang" if args.sanitize else str(toolchain() / "bin/clang")
    )
    outputs = []
    for source in sources:
        output = []
        compiled = (
            guest_object(source, out / "soft_gpu.o", flags)
            if source.suffix == ".ll"
            else str(source)
        )
        for existing in (False, True):
            binary = out / ("existing-raster" if existing else "guest-boundaries")
            command = [
                compiler,
                *flags,
                compiled,
                str(ROOT / "tests/pc/host_renderer_boundary_test.c"),
                str(ROOT / "src/pc/memory.c"),
                str(ROOT / "src/pc/guest/translated_runtime.c"),
            ]
            if existing:
                command += [
                    "-DEXISTING_RASTER_TEST",
                    str(ROOT / "tests/pc/soft_gpu_test.c"),
                ]
            subprocess.run([*command, "-o", str(binary)], check=True, timeout=60)
            result = subprocess.run(
                [str(binary)], check=True, capture_output=True, text=True, timeout=30
            )
            print(result.stdout, end="")
            output.append(result.stdout)
        outputs.append(output)
    if args.differential:
        assert outputs[0] == outputs[1], "Host and instrumented raster outputs differ"
        print("Native/instrumented complete VRAM hashes and raster regressions match")


if __name__ == "__main__":
    main()
