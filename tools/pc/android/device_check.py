#!/usr/bin/env python3
"""List the Android devices on adb and what matters for the port.

For each device: model, Android version and API level, the 64-bit and
32-bit ABI lists (many new phones are arm64-only, with an empty 32-bit
list), the kernel's bitness, the screen size and density, and the free
space in /data.

adb comes from --adb, $ADB, $ANDROID_HOME/platform-tools, D:/Android/sdk
or PATH, in that order.

    python tools/pc/android/device_check.py
"""
import argparse
import os
import shutil
import subprocess
import sys


def find_adb(explicit):
    candidates = [explicit, os.environ.get("ADB")]
    for root in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"), "D:/Android/sdk"):
        if root:
            candidates.append(os.path.join(root, "platform-tools", "adb.exe" if os.name == "nt" else "adb"))
    candidates.append(shutil.which("adb"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    sys.exit("adb not found: pass --adb or set ANDROID_HOME")


def run(adb, serial, *args):
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def shell(adb, serial, command):
    return run(adb, serial, "shell", command)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adb")
    args = ap.parse_args()
    adb = find_adb(args.adb)
    print(f"adb: {adb}")
    lines = run(adb, None, "devices", "-l").splitlines()[1:]
    devices = [l.split() for l in lines if l.strip()]
    if not devices:
        print("No device. Check the cable, USB debugging and the phone's RSA prompt.")
        return 1
    for d in devices:
        serial, state = d[0], d[1]
        print(f"\n== {serial} ({state})")
        if state != "device":
            if state == "unauthorized":
                print("  Accept the 'Allow USB debugging?' prompt on the phone, then run this again.")
            continue
        prop = lambda k: shell(adb, serial, f"getprop {k}")
        abi64 = prop("ro.product.cpu.abilist64")
        abi32 = prop("ro.product.cpu.abilist32")
        print(f"  model:        {prop('ro.product.manufacturer')} {prop('ro.product.model')} ({prop('ro.product.device')})")
        print(f"  android:      {prop('ro.build.version.release')} (API {prop('ro.build.version.sdk')})")
        print(f"  abilist:      {prop('ro.product.cpu.abilist')}")
        print(f"  abilist64:    {abi64 or '(none)'}")
        print(f"  abilist32:    {abi32 or '(none)'}")
        print(f"  kernel:       {shell(adb, serial, 'uname -m')} {shell(adb, serial, 'uname -r')}")
        print(f"  soc:          {prop('ro.soc.model') or prop('ro.board.platform')}")
        print(f"  screen:       {shell(adb, serial, 'wm size').replace(chr(10), '; ')}")
        print(f"  density:      {shell(adb, serial, 'wm density').replace(chr(10), '; ')}")
        print(f"  page size:    {shell(adb, serial, 'getconf PAGE_SIZE')}")
        df = shell(adb, serial, "df -h /data").splitlines()
        print(f"  /data:        {df[-1] if df else '?'}")
        verdict = []
        if "arm64-v8a" in abi64:
            verdict.append("arm64-v8a APK: yes")
        print(f"  verdict:      {'; '.join(verdict) or 'no arm64-v8a: the APK cannot run here'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
