#!/usr/bin/env python3
"""Exercise the ARM64 mod import guard against real Mach-O libraries."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from build_mod_arm64 import SYSTEM_MATH_IMPORTS, link_library
from build_config import MACOS_MINIMUM
from llvm_guest import toolchain
from macos_deps import sdk_path


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = str(toolchain() / "bin/clang")
        cls.sdk = str(sdk_path())

    def link(self, source, exported=()):
        with tempfile.TemporaryDirectory(prefix="mod-imports-") as directory:
            folder = Path(directory)
            c = folder / "fixture.c"
            c.write_text(source)
            obj = folder / "fixture.o"
            subprocess.run([
                self.compiler, "-isysroot", self.sdk, "-fno-builtin",
                f"-mmacosx-version-min={MACOS_MINIMUM}",
                "-c", str(c), "-o", str(obj),
            ], check=True)
            library = link_library(folder, "fixture.dylib", [str(obj)], [],
                                   self.compiler, self.sdk, set(exported))
            return subprocess.check_output(["nm", "-u", "-m", str(library)], text=True)

    def test_pointer_free_math(self):
        binary = {"atan2", "atan2f", "fmod", "fmodf", "pow", "powf"}
        declarations, calls = [], []
        for name in sorted(SYSTEM_MATH_IMPORTS):
            scalar = "float" if name.endswith("f") else "double"
            arguments = f"{scalar}, {scalar}" if name in binary else scalar
            declarations.append(f"extern {scalar} {name}({arguments});")
            calls.append(f"{name}(x, x)" if name in binary else f"{name}(x)")
        rows = self.link("\n".join(declarations)
                         + "\ndouble fixture(double x) { return "
                         + " + ".join(calls) + "; }")
        for name in SYSTEM_MATH_IMPORTS:
            self.assertIn(f"_{name} (from libSystem)", rows)

    def test_pointer_taking_system_functions_rejected(self):
        cases = {
            "atoi": '#include <stdlib.h>\nint fixture(char *p) { return atoi(p); }',
            "strtol": '#include <stdlib.h>\nlong fixture(char *p) { return strtol(p, 0, 10); }',
            "strtod": '#include <stdlib.h>\ndouble fixture(char *p) { return strtod(p, 0); }',
            "fopen": '#include <stdio.h>\nFILE *fixture(char *p) { return fopen(p, "r"); }',
            "bsearch": '#include <stdlib.h>\nvoid *fixture(void *p, int (*cmp)(const void *, const void *)) { return bsearch(p, p, 1, 1, cmp); }',
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                # Even a same-named game export cannot intercept a dyld import.
                with self.assertRaisesRegex(SystemExit, f"cannot import from libSystem: {name}"):
                    self.link(source, exported={name})

    def test_scalar_character_classification(self):
        with self.assertRaisesRegex(SystemExit, "cannot import from libSystem: isdigit"):
            self.link("extern int isdigit(int);\n"
                      "int fixture(int value) { return isdigit(value); }")
        rows = self.link("extern int GuestRuntime_isdigit(int);\n"
                         "int fixture(int value) { return GuestRuntime_isdigit(value); }",
                         exported={"GuestRuntime_isdigit"})
        self.assertIn("_GuestRuntime_isdigit (dynamically looked up)", rows)

    def test_missing_game_import_rejected(self):
        with self.assertRaisesRegex(SystemExit, "game does not provide: missing_game_function"):
            self.link("extern void missing_game_function(void);\n"
                      "void fixture(void) { missing_game_function(); }")

    def test_translated_wrapper_and_runtime_helpers(self):
        rows = self.link("extern void *GuestRuntime_memcpy(void *, const void *, unsigned long);\n"
                         "extern void abort(void);\n"
                         "void fixture(void *p) { GuestRuntime_memcpy(p, p, 4); abort(); }",
                         exported={"GuestRuntime_memcpy"})
        self.assertIn("_GuestRuntime_memcpy (dynamically looked up)", rows)
        self.assertIn("_abort (from libSystem)", rows)


if __name__ == "__main__":
    unittest.main()
