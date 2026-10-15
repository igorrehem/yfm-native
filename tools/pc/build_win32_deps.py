#!/usr/bin/env python3
"""Fetch and build the Windows game executable's libraries (llvm-mingw).

The Linux build takes its libraries from Debian 11 and builds SDL3 from source
(tools/pc/build_linux_sysroot.py). On Windows this script provides them under
tmp/pc/win32-deps: static zlib, libpng and FreeType built from pinned release
archives, and SDL3's official MinGW development release (SDL3.dll, shipped
beside the executable). Needs cmake, ninja and llvm-mingw's
i686-w64-mingw32-clang: each from PATH when installed, else fetched
(tools/pc/fetch_tools.py on Windows; on Linux this script fetches llvm-mingw's
Linux release into tmp/pc/llvm-mingw, which build_game32.py then
cross-compiles with). Nothing needs installing by hand (notes/pc-build.md,
"Windows").

--arch x86_64 builds the same libraries for the 64-bit executable
(build_game32.py --target windows-x64) into tmp/pc/win64-deps, from the same
downloads."""
import hashlib, os, shutil, subprocess, sys, tarfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tmp", "pc", "win32-deps")
# The pinned archives, shared by both architectures' builds.
DOWNLOADS = os.path.join(ROOT, "tmp", "pc", "win32-deps", "downloads")
TRIPLE = "i686-w64-mingw32"
from dependency_archives import ARCHIVES
CC = TRIPLE + "-clang"
# llvm-mingw for Linux hosts: the same toolchain the Windows build uses, so
# a Linux checkout builds the Windows executable without a Windows machine.
TOOLCHAIN = os.path.join(ROOT, "tmp", "pc", "llvm-mingw")
TOOLCHAIN_ARCHIVE = ("https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/"
                     "llvm-mingw-20260922-ucrt-ubuntu-22.04-x86_64.tar.xz",
                     "bb7bb7654b33d5aa8712acb837c963b2e0c56352560c76105270a3268c665c21")


def use_toolchain():
    """Put llvm-mingw first on PATH: on Windows the installed one, else the
    pinned release (tools/pc/fetch_tools.py); elsewhere the one fetched here."""
    if sys.platform == "win32":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fetch_tools
        fetch_tools.ensure("llvm-mingw")
        return
    bin_dir = os.path.join(TOOLCHAIN, "bin")
    if os.path.isdir(bin_dir) and bin_dir not in os.environ["PATH"].split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]


def fetch(name):
    url, digest = TOOLCHAIN_ARCHIVE if name == "llvm-mingw" else ARCHIVES[name]
    path = os.path.join(DOWNLOADS, os.path.basename(url))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"fetch {url}")
        with urllib.request.urlopen(url) as response, open(path + ".part", "wb") as handle:
            shutil.copyfileobj(response, handle)
        os.replace(path + ".part", path)
    with open(path, "rb") as handle:
        actual = hashlib.sha256(handle.read()).hexdigest()
    if actual != digest:
        sys.exit(f"{path}: SHA-256 {actual}, expected {digest}")
    source = os.path.join(OUT, "src", name)
    if not os.path.isdir(source):
        with tarfile.open(path) as archive:
            top = archive.getnames()[0].split("/")[0]
            # The data filter exists from Python 3.12 (and the 3.8-3.11 point
            # releases that backported it); older ones take the plain call.
            if hasattr(tarfile, "data_filter"):
                archive.extractall(os.path.join(OUT, "src"), filter="data")
            else:
                archive.extractall(os.path.join(OUT, "src"))
        os.replace(os.path.join(OUT, "src", top), source)
    return source


def cmake(name, source, *options):
    build = os.path.join(OUT, "build", name)
    subprocess.run(["cmake", "-S", source, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_SYSTEM_NAME=Windows", f"-DCMAKE_C_COMPILER={CC}", "-DCMAKE_RC_COMPILER=llvm-windres",
                    f"-DCMAKE_INSTALL_PREFIX={OUT}", "-DCMAKE_PREFIX_PATH=" + OUT,
                    "-DCMAKE_POLICY_VERSION_MINIMUM=3.5", *options], check=True)
    subprocess.run(["cmake", "--build", build, "--target", "install"], check=True)


def configure(arch):
    """Build for `arch`: "i686" (the 32-bit game, tmp/pc/win32-deps) or
    "x86_64" (the 64-bit game, tmp/pc/win64-deps)."""
    global OUT, TRIPLE, CC
    TRIPLE = f"{arch}-w64-mingw32"
    CC = TRIPLE + "-clang"
    OUT = os.path.join(ROOT, "tmp", "pc", "win32-deps" if arch == "i686" else "win64-deps")


def main():
    if sys.platform != "win32" and not os.path.isdir(TOOLCHAIN):
        os.replace(fetch("llvm-mingw"), TOOLCHAIN)
    use_toolchain()
    if shutil.which(CC) is None:
        sys.exit(f"{CC} is not on PATH (llvm-mingw)")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fetch_tools
    fetch_tools.ensure("cmake")
    fetch_tools.ensure("ninja")
    cmake("zlib", fetch("zlib"), "-DZLIB_BUILD_SHARED=OFF", "-DZLIB_BUILD_TESTING=OFF", "-DBUILD_SHARED_LIBS=OFF")
    # zlib's static library is libzs.a, which FindZLIB does not look for.
    cmake("libpng", fetch("libpng"), "-DPNG_SHARED=OFF", "-DPNG_STATIC=ON", "-DPNG_TESTS=OFF", "-DPNG_TOOLS=OFF",
          "-DPNG_FRAMEWORK=OFF", f"-DZLIB_LIBRARY={OUT}/lib/libzs.a", f"-DZLIB_INCLUDE_DIR={OUT}/include")
    cmake("freetype", fetch("freetype"), "-DBUILD_SHARED_LIBS=OFF", "-DFT_DISABLE_ZLIB=ON", "-DFT_DISABLE_BZIP2=ON",
          "-DFT_DISABLE_PNG=ON", "-DFT_DISABLE_HARFBUZZ=ON", "-DFT_DISABLE_BROTLI=ON")
    sdl = fetch("sdl")
    shutil.copytree(os.path.join(sdl, TRIPLE), os.path.join(OUT, "sdl"), dirs_exist_ok=True)
    print(f"{TRIPLE} deps: {OUT}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("i686", "x86_64"), default="i686")
    configure(parser.parse_args().arch)
    main()
