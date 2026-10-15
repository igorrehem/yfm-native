#!/usr/bin/env python3
"""Stage an ad-hoc signed Apple Silicon .app and ZIP without retail inputs."""

import argparse
import hashlib
import json
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

from build_config import MACOS_MINIMUM

ROOT = Path(__file__).resolve().parents[2]
APP = "YFM Re-Decomp.app"
EXECUTABLE = "memories-arm64"
MINIMUM = MACOS_MINIMUM


def within_root(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError("package paths must stay below the repository root")
    return path


def inspect_binary(path):
    data = path.read_bytes()
    magic, cpu, _, kind, count, commands, _, _ = struct.unpack_from("<8I", data)
    if (magic, cpu, kind) != (0xFEEDFACF, 0x0100000C, 2):
        raise ValueError("expected a native ARM64 Mach-O executable")
    end, offset, minimum = 32 + commands, 32, None
    if end > len(data):
        raise ValueError("truncated Mach-O load commands")
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > end:
            raise ValueError("invalid Mach-O load command")
        if command == 0x32:  # LC_BUILD_VERSION
            platform, version = struct.unpack_from("<II", data, offset + 8)
            if platform != 1:
                raise ValueError("expected a macOS executable")
            minimum = (version >> 16, (version >> 8) & 255, version & 255)
        if command in (0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023):
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            name = (
                data[offset + name_offset : offset + size].split(b"\0", 1)[0].decode()
            )
            if not name.startswith(("/usr/lib/", "/System/Library/")):
                raise ValueError(
                    f"non-system runtime dependency cannot be shipped: {name}"
                )
        offset += size
    if minimum != tuple(map(int, MINIMUM.split("."))) + (0,):
        raise ValueError(f"build must explicitly target macOS {MINIMUM}, got {minimum}")
    return data


def binary_uuid(data):
    count = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, offset)
        if command == 0x1B:
            return str(uuid.UUID(bytes=data[offset + 8 : offset + 24]))
        offset += size
    raise ValueError("executable has no Mach-O UUID")


def inspect_icon(data):
    """Validate an ICNS container before sealing it into the application."""
    if (
        len(data) < 8
        or data[:4] != b"icns"
        or struct.unpack_from(">I", data, 4)[0] != len(data)
    ):
        raise ValueError("icon must be a complete .icns file")
    offset, images = 8, 0
    image_types = {
        b"icp4",
        b"icp5",
        b"icp6",
        b"ic07",
        b"ic08",
        b"ic09",
        b"ic10",
        b"ic11",
        b"ic12",
        b"ic13",
        b"ic14",
        b"is32",
        b"il32",
        b"ih32",
        b"it32",
    }
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError("truncated ICNS entry")
        kind, size = struct.unpack_from(">4sI", data, offset)
        if size <= 8 or size > len(data) - offset:
            raise ValueError("invalid ICNS entry size")
        images += kind in image_types
        offset += size
    if not images:
        raise ValueError("ICNS file contains no application icon images")


def shipped_mod_files():
    """Only repository-owned resources, never locally installed mods or objects."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "mods"], cwd=ROOT, text=True
    ).split("\0")
    return [Path(name) for name in tracked if name and
            Path(name).suffix not in (".c", ".h", ".o", ".dylib")]


def stage_mods(resources, game):
    from build_mod_arm64 import build

    files = shipped_mod_files()
    libraries = []
    for relative in files:
        destination = resources / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    for relative in files:
        if relative.name != "mod.json":
            continue
        manifest = json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))
        if manifest.get("library"):
            library = build(ROOT / relative.parent, resources / relative.parent, game=game)
            subprocess.run(["codesign", "--force", "--sign", "-", str(library)], check=True)
            libraries.append(library)
    return files, libraries


def package(binary, out, label, *, icon=None):
    if sys.platform != "darwin":
        raise ValueError("macOS packaging requires codesign on a Mac")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise ValueError("version must be a filename-safe release label")
    binary, out = within_root(binary), within_root(out)
    inspect_binary(binary)
    identity = json.loads((binary.parent / "build-identity.json").read_text())
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if identity["binary_sha256"] != digest:
        raise ValueError(
            "executable differs from its build identity; rebuild before packaging"
        )
    from build_game32 import VERSION_PATTERN

    game_version = label if re.fullmatch(VERSION_PATTERN, label) else ""
    if identity["version"] != game_version:
        raise ValueError(
            "package version differs from executable; rebuild with MEMORIES_VERSION"
        )
    icon_data = icon.read_bytes() if icon is not None else None
    if icon_data is not None:
        inspect_icon(icon_data)
    stage = out / "stage"
    # Remove only our previous staging directory, never a caller's output tree.
    if stage.is_symlink():
        raise ValueError("staging directory must not be a symlink")
    shutil.rmtree(stage, ignore_errors=True)
    app = stage / APP
    executable = app / "Contents/MacOS" / EXECUTABLE
    resources = app / "Contents/Resources"
    executable.parent.mkdir(parents=True)
    resources.mkdir()
    shutil.copy2(binary, executable)
    executable.chmod(0o755)
    # Only the upstream tracked language packs; never export private discs.
    languages = resources / "languages"
    languages.mkdir()
    for name in ("en-eu", "fr", "de", "it", "es"):
        shutil.copyfile(ROOT / f"languages/{name}.txt", languages / f"{name}.txt")
    mod_files, mod_libraries = stage_mods(resources, binary.parent)
    revision = identity["revision"]
    build_number = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"], cwd=ROOT, text=True
    ).strip()
    release = re.match(r"^v?(\d+\.\d+\.\d+)(?:[-.].*)?$", label)
    info = dict(
        CFBundleName="YFM Re-Decomp",
        CFBundleDisplayName="YFM Re-Decomp",
        CFBundleIdentifier="org.yfm-redecomp.memories",
        CFBundleExecutable=EXECUTABLE,
        CFBundlePackageType="APPL",
        CFBundleVersion=build_number,
        CFBundleShortVersionString=release.group(1) if release else "0.0.0",
        LSMinimumSystemVersion=MINIMUM,
        LSArchitecturePriority=["arm64"],
        NSHighResolutionCapable=True,
        PackageVersion=label,
        SourceRevision=revision,
    )
    if icon_data is not None:
        info["CFBundleIconFile"] = "Memories.icns"
        (resources / "Memories.icns").write_bytes(icon_data)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    (app / "Contents/PkgInfo").write_bytes(b"APPL????")
    shutil.copyfile(ROOT / "LICENSE", resources / "LICENSE.txt")
    licenses = resources / "licenses"
    licenses.mkdir()
    dependency_licenses = {
        "SDL3.txt": "sdl-source/LICENSE.txt",
        "libpng.txt": "libpng/LICENSE",
        "zlib.txt": "zlib/LICENSE",
        "FreeType.txt": "freetype/docs/FTL.TXT",
    }
    for name, source in dependency_licenses.items():
        shutil.copyfile(ROOT / "tmp/pc/macos-deps/src" / source, licenses / name)
    readme = """YFM Re-Decomp — macOS Apple Silicon

Drag YFM Re-Decomp.app to Applications, then open it. The welcome screen
asks for your own Forbidden Memories USA (SLUS-01411) raw .bin disc image.
No game disc or HD texture pack is included. Python, LLVM and Homebrew are
not needed to run this application. Intel Macs are not supported.

This development application is ad-hoc signed, not Developer ID signed or
notarized. A downloaded copy may be blocked by Gatekeeper. For a build you
trust, use System Settings > Privacy & Security > Open Anyway after trying
to open it. Do not disable Gatekeeper globally.

Saves, settings and your mods use ~/Library/Application Support/YFM Re-Decomp.
Keep ordinary .sav files to move progress between versions. Native .state
files require the same executable and mod profile. Data mods use the existing
format; code mods require an ARM64 dylib, not an i386 .o.
Included mods: 3D Monsters, Hand Camera, AI Hard Mode, Yamyi Mods and
Drop Missing Cards. 3D Monsters and Hand Camera are enabled by default.
Open Game > Mods to enable or disable mods and adjust their settings.
The included code mods are compiled for this build. Additional user mods go
in ~/Library/Application Support/YFM Re-Decomp/mods. No mod SDK is bundled;
see notes/modding.md in the source repository for the ARM64 build commands.

Static dependencies: SDL3, libpng, zlib and FreeType; licenses are inside
Contents/Resources/licenses. Portions of this software are copyright
(c) The FreeType Project (www.freetype.org). All rights reserved.
"""
    (stage / "README.txt").write_text(readme, encoding="utf-8")
    shutil.copyfile(ROOT / "LICENSE", stage / "LICENSE.txt")
    manifest = dict(
        version=label,
        game_version=game_version,
        revision=revision,
        build_fingerprint=identity["fingerprint"],
        architecture="arm64",
        minimum_macos=MINIMUM,
        signing="ad-hoc",
        notarized=False,
        icon_sha256=hashlib.sha256(icon_data).hexdigest()
        if icon_data is not None
        else None,
        source_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        source_uuid=binary_uuid(binary.read_bytes()),
        mod_files={str(path): hashlib.sha256((resources / path).read_bytes()).hexdigest()
                   for path in mod_files} | {
                       str(path.relative_to(resources)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in mod_libraries},
    )
    (resources / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
    archive = out / f"yfm-redecomp-{label}-macos-arm64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(stage))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
    print(archive)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "tmp/pc-release/macos-arm64")
    parser.add_argument("--version", default=None)
    parser.add_argument(
        "--icon",
        type=Path,
        help="explicit ICNS app icon; omitted in public builds by default",
    )
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT:
        parser.error("run from the repository root")
    label = (
        args.version
        or "dev-"
        + subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, text=True
        ).strip()
    )
    package(args.binary, args.out, label, icon=args.icon)


if __name__ == "__main__":
    main()
