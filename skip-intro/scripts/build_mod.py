#!/usr/bin/env python3
"""Build the startup skip patch for Brilliant Diamond 1.3.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

import lz4.block

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from staging import staged_directory


PROJECT = Path(__file__).resolve().parents[1]
BUILD_ID = "94CEAE325C205C4B9D6F7235552F28FD"
TITLE_ID = "0100000011D90000"
# Title.Initialize's non-ending tail call: PlayOpeningSequence -> EndTitle.
# x0 already holds Title*, and its stack frame has been restored at this point.
PATCH_RVA = 0x2CB5BB4
ORIGINAL_TARGET = 0x2CB5CD0
LOAD_TARGET = 0x2CB6140
NSO_HEADER_SHIFT = 0x100


def branch(source: int, target: int) -> bytes:
    displacement = target - source
    if displacement % 4 or not -(1 << 27) <= displacement < (1 << 27):
        raise ValueError("AArch64 branch target is unaligned or out of range")
    return struct.pack("<I", 0x14000000 | ((displacement // 4) & 0x3FFFFFF))


def executable_text(path: Path) -> bytes:
    data = path.read_bytes()
    if (len(data) < NSO_HEADER_SHIFT or data[:4] != b"NSO0"
            or data[0x40:0x50].hex().upper() != BUILD_ID):
        raise ValueError(f"Expected Brilliant Diamond 1.3.0 build {BUILD_ID}: {path}")
    flags = struct.unpack_from("<I", data, 0xC)[0]
    offset, address, size = struct.unpack_from("<III", data, 0x10)
    if address != 0 or offset < NSO_HEADER_SHIFT:
        raise ValueError("Unexpected NSO text segment layout")
    stored_size = struct.unpack_from("<I", data, 0x60)[0] if flags & 1 else size
    if offset + stored_size > len(data):
        raise ValueError("Truncated NSO text segment")
    text = data[offset:offset + stored_size]
    if flags & 1:
        text = lz4.block.decompress(text, uncompressed_size=size)
    if len(text) != size:
        raise ValueError("Unexpected NSO text segment size")
    return text


def build(exefs: Path, output: Path) -> None:
    text = executable_text(exefs / "main")
    if text[PATCH_RVA:PATCH_RVA + 4] != branch(PATCH_RVA, ORIGINAL_TARGET):
        raise ValueError("Title.Initialize does not contain the expected opening branch")
    if len(text) <= LOAD_TARGET:
        raise ValueError("Missing Title.EndTitle loading routine")
    replacement = branch(PATCH_RVA, LOAD_TARGET)
    patch = (
        f"@nsobid-{BUILD_ID}\n\n"
        "# Skip Intro and Title v1.3.0\n"
        f"@flag offset_shift {NSO_HEADER_SHIFT:#x}\n\n"
        "@enabled\n"
        "// Title.Initialize: load normally after initialization, preserving the ending path.\n"
        f"{PATCH_RVA:08X} {replacement.hex().upper()}\n"
        "@stop\n"
    )
    with staged_directory(output) as staged:
        (staged / "exefs").mkdir()
        patch_path = staged / "exefs/skip-intro-v1.3.0.pchtxt"
        patch_path.write_text(patch)
        shutil.copy2(PROJECT / "README.md", staged / "README.md")
        shutil.copy2(PROJECT.parent / "LICENSE", staged / "LICENSE")
        manifest = {
            "title_id": TITLE_ID,
            "version": "1.3.0",
            "build_id": BUILD_ID,
            "patch_rva": f"0x{PATCH_RVA:x}",
            "original_target": "Title.PlayOpeningSequence",
            "replacement_target": "Title.EndTitle",
            "patch_sha256": hashlib.sha256(patch_path.read_bytes()).hexdigest(),
            "runtime_tested": True,
            "runtime_validation": {
                "startup_skip": "User confirmed working in local Eden on 2026-10-01",
                "first_time_setup": "unverified",
                "save_error_handling": "unverified",
                "hall_of_fame_ending": "unverified",
                "combined_mods": "unverified",
            },
        }
        (staged / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Built startup skip mod: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exefs", type=Path, default=PROJECT.parent / "extracted/exefs")
    parser.add_argument("--output", type=Path,
                        default=PROJECT.parent / "dist/Skip Intro and Title v1.3.0")
    args = parser.parse_args()
    build(args.exefs, args.output)


if __name__ == "__main__":
    main()
