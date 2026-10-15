#!/usr/bin/env python3
"""Compatibility CLI for the structured LLVM guest-memory compiler."""
import argparse
from pathlib import Path
from llvm_guest import translate, TranslationError

def address_map(path):
    result = {}
    active = False
    for line in Path(path).read_text().splitlines():
        if line.startswith('['): active = line == '[SLUS_014.11]'
        elif active and len(line.split()) == 2:
            name, address = line.split(); result[name] = int(address, 16)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--addresses', type=Path, default=Path('config/pc/guest_addresses.txt'))
    args = parser.parse_args()
    try: args.output.write_text(translate(args.source.read_text(), address_map(args.addresses)))
    except TranslationError as error: parser.error(str(error))

if __name__ == '__main__': main()
