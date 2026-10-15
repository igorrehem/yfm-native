# Build on macOS

The source build targets native Apple Silicon (ARM64) with an explicit macOS
11.0 deployment target. This is the declared minimum version; runtime
compatibility on macOS 11 must be validated on that system. It requires Python 3
and the Xcode command-line tools, including the macOS SDK. The build scripts
fetch pinned dependencies into `tmp/` and verify their checksums; a separate
Homebrew, CMake, Ninja, or LLVM installation is not required.

From the repository root, build the game with:

```sh
python3 tools/pc/build.py --target macos
```

The executable is `tmp/pc/macos/memories-arm64`. To build and launch it through
the normal source launcher, put a legally obtained USA disc image in `game/`
and run:

```sh
./play.sh
```

Building does not require a disc; launching the game does. The first build
downloads and compiles the pinned dependencies under `tmp/`. Later builds reuse
them while their configuration and checksums remain valid. See
[macOS ARM64 architecture and validation](macos-arm64.md) for the runtime
design and focused validation commands.

## Downloadable application

After building, produce the application archive with:

```sh
python3 tools/pc/package_macos.py --version dev-local
```

For a release, build and package with the same upstream version label:

```sh
MEMORIES_VERSION=v0.0.0-preview.1 python3 tools/pc/build.py --target macos
python3 tools/pc/package_macos.py --version v0.0.0-preview.1
```

Replace the example label with the actual release version. Development builds
retain the upstream empty update-check version; the archive and crash report
carry a development label and source revision. The packager checks the binary's
build identity and rejects a release label that differs from its compiled
version. Rebuild if the executable or its identity file has changed.

The ZIP and its SHA-256 checksum are written to `tmp/pc-release/macos-arm64/`.
The ZIP contains `YFM Re-Decomp.app`, a README and license notices. Move the
application to Applications and open it; the upstream welcome screen lets
you choose your own USA raw `.bin` disc. The executable and dependencies are
bundled, so running the app requires neither Python nor LLVM. Saves, settings
and user mods remain in `~/Library/Application Support/YFM Re-Decomp`.
The upstream language packs are included; no private disc or HD texture pack
is copied. The five repository mods are included: 3D Monsters, Hand Camera,
AI Hard Mode, Yamyi Mods and Drop Missing Cards. The packager compiles their
code libraries for this ARM64 build and signs them before signing the app.
3D Monsters and Hand Camera are enabled by default. Open **Game > Mods**
to enable or disable mods and adjust their settings. Additional
code mods must be compiled separately for the ARM64 ABI.

The package is ad-hoc signed and verified locally. It is not Developer ID
signed or notarized; a downloaded copy may require **Open Anyway** in
System Settings > Privacy & Security. Distribution without that prompt
requires Apple signing credentials and notarization, which this workflow
does not provision. See [Apple's distribution guide](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

The release workflow also builds and uploads this ZIP on a macOS ARM64
runner. A manual run on a fork branch provides an Actions artifact; version
tags use the existing draft-release flow. See [release instructions](pc-release.md)
for downloads, retention and the remaining publication checks.

The binary declares macOS 11.0 as its minimum deployment version. Local validation
was performed on macOS 26.6.2; running on macOS 11 and testing a
quarantined download remain separate release checks. The app currently uses
the system's generic application icon unless an explicit icon is supplied.

## Application icon and release signing

Supply a project-owned or otherwise distributable ICNS icon when packaging:

```sh
python3 tools/pc/package_macos.py --version dev-local --icon /path/to/Memories.icns
```

The packager sets `CFBundleIconFile`, includes the icon before signing, and
records its checksum; the package regression verifies the resource and seal.
Without `--icon`, builds keep the generic application icon. Public CI does not
read a private disc or import an installed game's icon. Windows local builds
can extract the memory-card icon from `SLUS_014.11`; upstream's public releases
omit that disc-derived executable icon. The same image may be converted to
ICNS for a private local macOS package, without committing it to the repository.

Official Developer ID signing and notarization belong to the upstream release
owner's Apple identity. This PR's ad-hoc signature requires no credentials
and checks bundle integrity, but does not establish a trusted publisher for
Gatekeeper. A production release pipeline needs Developer ID Application
signing, hardened runtime, notarization and stapling. Validate that configuration
with third-party code mods: their dylibs are loaded into the game process,
so library-validation policy must be chosen deliberately. See
[Apple's notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

## CMake and CTest

The Python driver is the primary game build. CMake on Apple Silicon exposes
`pc_game` and `pc_audit`, and CTest invokes the same ROM-free native runners.
For this optional entry point, put CMake/CTest on `PATH`, or use the pinned
`CMake.app/Contents/bin` under `tmp/pc/tools/macos/cmake/` after the game build:

```sh
cmake -S . -B tmp/pc/macos-tests -DBUILD_TESTING=ON
ctest --test-dir tmp/pc/macos-tests --output-on-failure
```

Use `-DMEMORIES_SANITIZERS=ON` for the supported host sanitizer paths. These
runners own compilation with pinned guest LLVM and compatible host compilers;
they do not attempt to run the Linux/Windows fixed-memory i386 harnesses on
Darwin. Retail gameplay and package linkage remain separate checks.
