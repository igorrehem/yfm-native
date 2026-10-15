#!/usr/bin/env python3
"""Test the mod object cache of tools/pc/build_mod.py (notes/pc-build.md,
"Mod objects"), in a cache of its own under tmp/pc/mod-cache-test.

- A header edited while the mod builds (between the preprocessor, which the
  key comes from, and the compiler) must not leave an object of the new
  header under the key of the old one: the cache would hand it to every
  checkout that has the old header.
- Two checkouts with other headers get other objects; two with the same
  sources and headers share one.
- An unchanged checkout finds its key in the memo without the preprocessor,
  and a new header in the mod's directory, which the preprocessor never
  read, still sends it back to the preprocessor."""
import os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mod

SOURCE = '#include "probe.h"\nconst char *Probe_Text(void) { return PROBE_TEXT; }\n'


def header(text):
    return f'#define PROBE_TEXT "{text}"\n'


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as handle:
        handle.write(text)


def checkout(base, name, text):
    """A copy of the probe mod as another checkout would have it."""
    directory = os.path.join(base, name, "probe")
    write(os.path.join(directory, "mod.json"), '{"id": "probe", "library": "probe"}\n')
    write(os.path.join(directory, "probe.c"), SOURCE)
    write(os.path.join(directory, "probe.h"), header(text))
    return os.path.join(base, name)


def built(tree, out):
    """Build the probe mod of `tree` (from inside it, as build_mods does
    from the checkout's root) and return the object's bytes."""
    here = os.getcwd()
    os.chdir(tree)
    try:
        build_mod.build("probe", out_dir=out, games=[], quiet=True)
    finally:
        os.chdir(here)
    with open(os.path.join(out, "probe.o"), "rb") as handle:
        return handle.read()


def main():
    os.makedirs(os.path.join(ROOT, "tmp/pc"), exist_ok=True)
    base = tempfile.mkdtemp(prefix="mod-cache-test-", dir=os.path.join(ROOT, "tmp/pc"))
    build_mod.CACHE = os.path.join(base, "cache")
    failures = []

    def expect(condition, what):
        print(("ok: " if condition else "FAILED: ") + what)
        if not condition:
            failures.append(what)

    try:
        # The race: the header changes after the preprocessor has run.
        a = checkout(base, "a", "RVRACE_ONE")
        compile_object = build_mod.compile_object

        def edit_then_compile(*arguments, **options):
            write(os.path.join(a, "probe", "probe.h"), header("RVRACE_TWO"))
            return compile_object(*arguments, **options)

        build_mod.compile_object = edit_then_compile
        try:
            first = built(a, os.path.join(base, "out-a"))
        finally:
            build_mod.compile_object = compile_object
        expect(b"RVRACE_ONE" in first and b"RVRACE_TWO" not in first,
               "an object built while its header changed is the header the key was taken from")
        write(os.path.join(a, "probe", "probe.h"), header("RVRACE_ONE"))
        again = built(a, os.path.join(base, "out-a"))
        expect(b"RVRACE_ONE" in again and b"RVRACE_TWO" not in again,
               "the old header's key holds the old header's object")
        write(os.path.join(a, "probe", "probe.h"), header("RVRACE_TWO"))
        second = built(a, os.path.join(base, "out-a"))
        expect(b"RVRACE_TWO" in second and b"RVRACE_ONE" not in second, "the new header builds its own object")
        write(os.path.join(a, "probe", "probe.h"), header("RVRACE_ONE"))

        # Other checkouts: other headers, other objects; the same, one.
        b = checkout(base, "b", "OTHER_CHECKOUT")
        c = checkout(base, "c", "RVRACE_ONE")
        other = built(b, os.path.join(base, "out-b"))
        expect(b"OTHER_CHECKOUT" in other and b"RVRACE_ONE" not in other,
               "a checkout with another header gets its own object")
        same = built(c, os.path.join(base, "out-c"))
        expect(same == again, "a checkout with the same sources and headers shares the object")
        entries = [name for name in os.listdir(build_mod.CACHE) if name.startswith("probe-")]
        expect(len(entries) == 3, f"three objects in the cache (one per content): {sorted(entries)}")

        # The memo: no preprocessor while nothing changed; a new header in
        # the mod's directory sends the build back to it.
        run, calls = build_mod.run, []

        def counting(command):
            calls.append(command)
            return run(command)

        build_mod.run = counting
        try:
            built(a, os.path.join(base, "out-a"))
            expect(not any("-E" in command for command in calls), "an unchanged checkout starts no preprocessor")
            write(os.path.join(a, "probe", "unused.h"), "/* never included */\n")
            unchanged = built(a, os.path.join(base, "out-a"))
            expect(any("-E" in command for command in calls) and unchanged == again,
                   "a new header misses the memo and finds the same object")
        finally:
            build_mod.run = run
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if failures:
        sys.exit(f"test_mod_cache: {len(failures)} failed")
    print("test_mod_cache: all passed")


if __name__ == "__main__":
    main()
