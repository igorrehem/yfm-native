#!/usr/bin/env python3
"""Verify narrow guest stores survive LLVM translation at O0 and O2.

The raw compiler assembly is inspected as a diagnostic only: some Clang
versions emit a 32-bit str/stur for a 1- or 2-byte G32 field. The build
contract is that translated IR routes those stores through resolved native
memory and retains the original i8/i16 width, regardless of whether the raw
compiler currently exhibits the bug.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from llvm_guest import ROOT, translate, toolchain

SOURCE = r"""
typedef struct StoreCanary {
    unsigned char padding;
    unsigned short half;
    unsigned char byte;
} StoreCanary;
extern StoreCanary *__ptr32 __uptr guest_canary;
void canary_store16(unsigned short value) { guest_canary->half = value; }
void canary_store8(unsigned char value) { guest_canary->byte = value; }
"""
WIDE_STORE = re.compile(r"^\s*(?:str|stur)\s+w\d+,\s*\[x\d+(?:,|\])", re.MULTILINE)


def function_body(assembly, name):
    """Extract an assembly function, accepting Mach-O's leading underscore."""
    labels = re.findall(r"^(_?" + re.escape(name) + r"):.*$", assembly, re.MULTILINE)
    if not labels:
        raise AssertionError(f"assembly has no label for {name}")
    start = re.search(r"^" + re.escape(labels[0]) + r":.*$", assembly, re.MULTILINE).end()
    next_label = re.search(r"^_?[A-Za-z][A-Za-z0-9_.$]*:\s*$", assembly[start:], re.MULTILINE)
    return assembly[start:start + next_label.start()] if next_label else assembly[start:]


def main():
    cc = toolchain() / "bin/clang"
    failures = []
    raw_bug_reports = []
    temp_root = ROOT / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temporary:
        folder = Path(temporary)
        source = folder / "store_canary.c"
        source.write_text(SOURCE)
        for level, narrow_function, width in (("-O0", "canary_store16", 16),
                                               ("-O2", "canary_store8", 8)):
            raw = folder / f"raw-{level[1:]}.ll"
            subprocess.run([str(cc), "-fms-extensions", level, "-S", "-emit-llvm",
                            str(source), "-o", str(raw)], check=True, capture_output=True, text=True)
            raw_ir = raw.read_text()
            if not re.search(rf"store i{width} .*ptr addrspace\(271\)", raw_ir):
                raise AssertionError(f"raw {level} IR did not contain the expected i{width} guest store")
            raw_assembly = subprocess.run([str(cc), "-fms-extensions", level, "-S", str(source),
                                           "-o", "-"], check=True, capture_output=True, text=True).stdout
            if WIDE_STORE.search(function_body(raw_assembly, narrow_function)):
                raw_bug_reports.append(f"{narrow_function} {level}")

            adapted = translate(raw_ir)
            if not re.search(r"call ptr @GuestRuntime_ResolveData", adapted):
                failures.append(f"{narrow_function} {level}: guest store was not resolved")
            if re.search(rf"store i{width} .*ptr addrspace\(271\)", adapted):
                failures.append(f"{narrow_function} {level}: narrow store still targets guest address space")
            if not re.search(rf"store i{width} .*ptr %[-A-Za-z$._0-9]+", adapted):
                failures.append(f"{narrow_function} {level}: translated i{width} store was not preserved")

            translated_ir = folder / f"translated-{level[1:]}.ll"
            translated_ir.write_text(adapted)
            translated_assembly = subprocess.run([str(cc), level, "-S", str(translated_ir), "-o", "-"],
                                                 check=True, capture_output=True, text=True).stdout
            if WIDE_STORE.search(function_body(translated_assembly, narrow_function)):
                failures.append(f"{narrow_function} {level}: translated code still has a wide store")

    if failures:
        raise SystemExit("guest-store canary failed:\n" + "\n".join(failures))
    if raw_bug_reports:
        print("Raw compiler wide-store canary observed (translated pass removed it): " +
              ", ".join(raw_bug_reports))
    else:
        print("Raw compiler and translated narrow-store canaries passed")


if __name__ == "__main__":
    main()
