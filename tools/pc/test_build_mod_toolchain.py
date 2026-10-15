#!/usr/bin/env python3
"""Test what tools/pc/build_mod.py tells a modder who cannot build the 64-bit
objects (no compiler starts here: the programs are empty files on a PATH of
the test's own).

- The llvm-mingw it points to is the one the repository builds the game
  with (tools/pc/fetch_tools.py on Windows, build_win32_deps.py on Linux).
- It names exactly what is missing of clang, ld.lld and llvm-objcopy.
- Without any of them, and no gcc, it builds nothing and says so; asked for
  a 64-bit target by name without them, it builds nothing either."""
import contextlib, io, os, shutil, stat, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mod, build_win32_deps, fetch_tools

EXE = ".exe" if os.name == "nt" else ""


class Toolchain(unittest.TestCase):
    def setUp(self):
        self.bin = tempfile.mkdtemp(prefix="build-mod-toolchain-")
        self.addCleanup(shutil.rmtree, self.bin, ignore_errors=True)
        environment = {name: value for name, value in os.environ.items() if name != "MEMORIES_MOD_CC"}
        environment["PATH"] = self.bin
        patches = [mock.patch.dict(os.environ, environment, clear=True),
                   mock.patch.object(build_mod, "LLVM_MINGW", os.path.join(self.bin, "no-llvm-mingw"))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        build_mod.find_programs.cache_clear()
        build_mod.find_objcopy.cache_clear()
        self.addCleanup(build_mod.find_programs.cache_clear)
        self.addCleanup(build_mod.find_objcopy.cache_clear)

    def program(self, name):
        path = os.path.join(self.bin, name + EXE)
        with open(path, "w"):
            pass
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def test_pinned_release(self):
        self.assertEqual(build_mod.LLVM_MINGW_DOWNLOADS["windows"], fetch_tools.RELEASES["llvm-mingw"][0])
        self.assertEqual(build_mod.LLVM_MINGW_DOWNLOADS["linux"], build_win32_deps.TOOLCHAIN_ARCHIVE[0])
        for url in build_mod.LLVM_MINGW_DOWNLOADS.values():
            self.assertIn(f"/download/{build_mod.LLVM_MINGW_RELEASE}/llvm-mingw-{build_mod.LLVM_MINGW_RELEASE}-", url)

    def test_names_what_is_missing(self):
        self.assertEqual(build_mod.missing_64bit(), ["clang", "ld.lld", "llvm-objcopy"])
        self.program("clang")
        self.assertEqual(build_mod.missing_64bit(), ["ld.lld", "llvm-objcopy"])
        self.program("ld.lld")
        self.assertEqual(build_mod.missing_64bit(), ["llvm-objcopy"])
        self.program("llvm-objcopy")
        self.assertEqual(build_mod.missing_64bit(), [])
        with mock.patch.dict(os.environ, {"MEMORIES_MOD_CC": self.program("gcc")}):
            self.assertEqual(build_mod.missing_64bit(), ["clang"])
            self.assertIn("MEMORIES_MOD_CC names", build_mod.toolchain_help(["clang"]))

    def test_help(self):
        text = build_mod.toolchain_help(["clang", "ld.lld"], built=os.path.join("my-mod", "rules.o"))
        self.assertIn("only the 32-bit object was built, " + os.path.join("my-mod", "rules.o"), text)
        self.assertIn("Not found: clang, ld.lld.", text)
        self.assertIn(build_mod.LLVM_MINGW_DOWNLOADS["windows" if sys.platform == "win32" else "linux"], text)
        if sys.platform != "win32":
            self.assertIn("sudo apt install clang lld llvm", text)
        self.assertIn("nothing was built", build_mod.toolchain_help(["clang"], wanted=("aarch64",)))

    def run_main(self, *arguments):
        error = io.StringIO()
        with mock.patch.object(sys, "argv", ["build_mod.py", *arguments]), contextlib.redirect_stderr(error), \
                self.assertRaises(SystemExit) as stopped:
            build_mod.main()
        return str(stopped.exception.code) + error.getvalue()

    def mod(self):
        """A code mod (its source is never compiled here)."""
        mod = os.path.join(self.bin, "mod")
        os.makedirs(mod, exist_ok=True)
        with open(os.path.join(mod, "mod.json"), "w") as handle:
            handle.write('{"id": "mod", "library": "mod"}\n')
        with open(os.path.join(mod, "mod.c"), "w") as handle:
            handle.write("int x;\n")
        return mod

    def test_no_compiler(self):
        text = self.run_main(self.mod())
        self.assertIn("nothing was built: no compiler found", text)
        self.assertIn("Not found: clang, ld.lld, llvm-objcopy.", text)

    def test_asked_for_a_64bit_target(self):
        self.program("gcc")   # the 32-bit object could be built; the one asked for cannot
        text = self.run_main(self.mod(), "--target", "aarch64")
        self.assertIn("nothing was built", text)
        self.assertIn("The 64-bit object (aarch64: Android) needs", text)
        self.assertNotIn("x86_64-windows:", text)

    def test_data_only_needs_no_compiler(self):
        data = os.path.join(self.bin, "data")
        os.makedirs(data)
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["build_mod.py", data, "--target", "aarch64"]), \
                contextlib.redirect_stdout(output):
            build_mod.main()
        self.assertIn("a data-only mod needs no build", output.getvalue())

    def test_named_compiler(self):
        with mock.patch.dict(os.environ, {"MEMORIES_MOD_CC": os.path.join(self.bin, "nowhere", "clang" + EXE)}):
            self.assertIn("which is not there", build_mod.toolchain_help(build_mod.missing_64bit()))


if __name__ == "__main__":
    unittest.main()
