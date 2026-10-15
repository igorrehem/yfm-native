"""Shared compilation for macOS font and card-title rendering contracts."""

import subprocess
from build_config import MACOS_MINIMUM
from guest_test_compile import host_compiler
from macos_deps import ROOT, ensure, sdk_path


def run_fonts(*, sanitize=False):
    install = ensure(("freetype", "libpng", "zlib"))
    out = ROOT / "tmp/pc/macos-font-tests"
    out.mkdir(parents=True, exist_ok=True)
    flags = [
        "-isysroot",
        str(sdk_path()),
        f"-mmacosx-version-min={MACOS_MINIMUM}",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Isrc",
        "-I" + str(install / "include"),
        "-I" + str(install / "include/freetype2"),
    ]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    common = [
        "src/pc/platform/macos_fonts.c",
        str(install / "lib/libfreetype.a"),
        str(install / "lib/libpng16.a"),
        str(install / "lib/libz.a"),
        "-framework",
        "CoreText",
        "-framework",
        "CoreFoundation",
    ]
    for name, sources in [
        ("fonts", ["tests/pc/macos_fonts_test.c"]),
        ("card-plates", ["tests/pc/card_plate_test.c", "src/pc/cards/art.c"]),
    ]:
        binary = out / name
        subprocess.run(
            [
                host_compiler(sanitize=sanitize),
                *flags,
                *sources,
                *common,
                "-o",
                str(binary),
            ],
            cwd=ROOT,
            check=True,
            timeout=60,
        )
        subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=30)
        print(f"{name}: font contract passed", flush=True)
