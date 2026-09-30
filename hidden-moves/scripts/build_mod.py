#!/usr/bin/env python3
"""Build a pinned ExLaunch module against the owned Brilliant Diamond executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

import lz4.block
from npdm import validate_process_descriptor


PROJECT = Path(__file__).resolve().parents[1]
FRAMEWORK_URL = "https://github.com/TeamLumi/Luminescent_ExLaunch.git"
FRAMEWORK_REV = "0d457adae65e5e56de35463b910aabc02903e7fd"
BUILD_ID = "94CEAE325C205C4B9D6F7235552F28FD"
HOOKS = {
    "AppearSwim": 0x1DB4000,
    "ChangeSwim": 0x1DB2640,
    "PlayerLateUpdate": 0x1DA3FD0,
    "CharacterDisable": 0x1788540,
    "RendererEnabled": 0x269A090,
    "CutInCommand": 0x2C6DC40,
    "CutInLoad": 0x2CC74B0,
    "WaterfallCommand": 0x2C6CD40,
    "RockClimbCommand": 0x2C6B1F0,
    "TraversalMessage": 0x1F96E90,
}


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def executable_text(path: Path) -> bytes:
    data = path.read_bytes()
    if data[:4] != b"NSO0" or data[0x40:0x50].hex().upper() != BUILD_ID:
        raise ValueError(f"Expected Brilliant Diamond 1.3.0 build {BUILD_ID}: {path}")
    flags = struct.unpack_from("<I", data, 0xC)[0]
    offset, address, size = struct.unpack_from("<III", data, 0x10)
    if address != 0:
        raise ValueError("Unexpected text segment RVA")
    compressed_size = struct.unpack_from("<I", data, 0x60)[0]
    text = data[offset:offset + (compressed_size if flags & 1 else size)]
    return lz4.block.decompress(text, uncompressed_size=size) if flags & 1 else text


def prepare_framework(build: Path) -> Path:
    checkout = build / "framework"
    if not checkout.exists():
        run("git", "clone", "--no-checkout", FRAMEWORK_URL, str(checkout))
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout,
                              text=True, capture_output=True)
    if revision.returncode or revision.stdout.strip() != FRAMEWORK_REV:
        run("git", "fetch", "--depth", "1", "origin", FRAMEWORK_REV, cwd=checkout)
        run("git", "checkout", "--detach", FRAMEWORK_REV, cwd=checkout)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
    ).strip()
    if revision != FRAMEWORK_REV:
        raise ValueError("Unexpected framework revision")
    return checkout


def signatures(text: bytes, target: Path) -> dict:
    # Include the hardcoded move mapping as a distinctive version sentinel.
    checks = {**HOOKS, "HiddenSpeciesSelector": 0x2C6E630}
    lines = ["#pragma once", "#include <cstdint>",
             "inline bool supported_game() {"]
    manifest = {}
    for name, address in checks.items():
        count = 64 if name == "HiddenSpeciesSelector" else 16
        data = text[address:address + count]
        if len(data) != count:
            raise ValueError(f"Missing executable range for {name}")
        words = struct.unpack(f"<{count // 4}I", data)
        lines.append(f"    const auto* {name} = reinterpret_cast<const uint32_t*>("
                     f"exl::util::modules::GetTargetOffset(0x{address:x}));")
        for index, word in enumerate(words):
            lines.append(f"    if ({name}[{index}] != 0x{word:08x}u) return false;")
        manifest[name] = {"rva": address, "expected_bytes": data.hex()}
    lines.extend(["    return true;", "}", ""])
    target.write_text("\n".join(lines))
    return manifest


def hook_offsets(target: Path) -> None:
    lines = ["#pragma once", "#include <cstdint>", "namespace hooks {"]
    lines += [f"constexpr uintptr_t {name} = 0x{address:x};" for name, address in HOOKS.items()]
    lines.extend(["}", ""])
    target.write_text("\n".join(lines))


def placements(source: Path, target: Path) -> None:
    data = json.loads(source.read_text())

    def literal(profile: dict) -> str:
        vectors = []
        for key in ("offset", "rotation", "scale"):
            values = profile[key]
            if len(values) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) for v in values
            ):
                raise ValueError(f"{key} must contain three finite numbers")
            if key == "scale" and any(v <= 0 for v in values):
                raise ValueError("Scale must be positive")
            vectors.append("{" + ", ".join(f"{float(v)}f" for v in values) + "}")
        return "{" + ", ".join(vectors) + "}"

    lines = ["#pragma once", "#include \"game.hpp\"",
             "struct Placement { game::Vector3 offset, rotation, scale; };",
             "inline Placement placement_for(int species, int move = 57) {"]
    if data.get('rock_climb'):
        lines.extend(["    if (move == 431) {", "        switch (species) {"])
        for species, profile in data['rock_climb'].items():
            if not species.isdigit() or not 1 <= int(species) <= 493:
                raise ValueError(f"Invalid Rock Climb species: {species}")
            lines.append(f"        case {int(species)}: return {literal(profile)};")
        lines.extend(["        }", "    }"])
    lines.append("    switch (species) {")
    for species, profile in data["species"].items():
        if not species.isdigit() or not 1 <= int(species) <= 493:
            raise ValueError(f"Invalid species: {species}")
        lines.append(f"    case {int(species)}: return {literal(profile)};")
    lines.extend([f"    default: return {literal(data['default'])};", "    }", "}", ""])
    target.write_text("\n".join(lines))


def check_ultrawide_overlap(hooks: dict) -> None:
    patches = PROJECT.parent / "dist/3440x1440 21.9 Complete UI v1.3.0/exefs"
    if not patches.exists():
        return
    def check_range(path: Path, offset: int, length: int) -> None:
        for name, check in hooks.items():
            start = check["rva"] + 0x100
            end = start + len(bytes.fromhex(check["expected_bytes"]))
            if offset < end and start < offset + length:
                raise ValueError(f"Ultrawide patch overlaps {name}: {path}")

    for path in patches.glob("*.pchtxt"):
        enabled = False
        shift = 0
        for line in path.read_text().splitlines():
            line = line.strip()
            if line == "@enabled":
                enabled = True
            elif line in ("@disabled", "@stop"):
                enabled = False
            elif line.startswith("@flag offset_shift "):
                shift = int(line.split()[-1], 0)
            elif enabled:
                match = re.match(r"^([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)(?:\s|$)", line)
                if match:
                    check_range(path, int(match[1], 16) + shift,
                                len(bytes.fromhex(match[2])))
    for path in patches.glob("*.ips"):
        patch = path.read_bytes()
        if patch[:5] != b"PATCH":
            raise ValueError(f"Unsupported patch format: {path}")
        cursor = 5
        while patch[cursor:cursor + 3] != b"EOF":
            offset = int.from_bytes(patch[cursor:cursor + 3], "big")
            length = int.from_bytes(patch[cursor + 3:cursor + 5], "big")
            cursor += 5
            if length:
                cursor += length
            else:
                length = int.from_bytes(patch[cursor:cursor + 2], "big")
                cursor += 3
            # IPS code addresses include the 0x100 NSO header shift.
            check_range(path, offset, length)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exefs", type=Path, default=PROJECT.parent / "extracted/exefs")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()
    devkitpro = Path(os.environ.get("DEVKITPRO", ""))
    compiler = devkitpro / "devkitA64/bin/aarch64-none-elf-g++"
    if not (args.prepare_only or args.test_only) and not compiler.is_file():
        parser.error("Switch toolchain missing; enter the repository's `nix develop` shell")
    text = executable_text(args.exefs / "main")
    build = PROJECT / "build"
    build.mkdir(exist_ok=True)
    framework = prepare_framework(build)
    work = build / "work"
    work.mkdir(exist_ok=True)
    for directory in ("include", "cmake", "module"):
        shutil.copytree(framework / directory, work / directory, dirs_exist_ok=True)
    modules = work / "cmake/modules.cmake"
    content = modules.read_text()
    embed = "    target_embed_binaries(${variant} ${ALL_EMBED_BINARIES} ${PARENT_EMBED_BINARIES})"
    if content.count(embed) != 1:
        raise ValueError("Framework embed helper changed unexpectedly")
    modules.write_text(content.replace(embed,
        "    if(ALL_EMBED_BINARIES OR PARENT_EMBED_BINARIES)\n" + embed + "\n    endif()"))
    # The pinned framework's descriptor predates the toolchain JSON names.
    descriptor = work / "module/npdm.json.template"
    content = descriptor.read_text()
    for old, new in (("title_id", "program_id"),
                     ("title_id_range_min", "program_id_range_min"),
                     ("title_id_range_max", "program_id_range_max")):
        content = content.replace(f'"{old}"', f'"{new}"')
    content = content.replace('"is_64_bit": true,',
        '"is_64_bit": true,\n'
        '    "optimize_memory_allocation": false,\n'
        '    "disable_device_address_space_merge": false,\n'
        '    "enable_alias_region_extra_size": false,\n'
        '    "prevent_code_reads": false,\n'
        '    "signature_key_generation": 0,')
    # Modern npdmtool encodes force_debug at bit 19, which Eden 0.2.1 treats
    # as reserved. allow_debug uses the compatible bit 17 and permits hooks.
    content = content.replace('"allow_debug": false', '"allow_debug": true')
    content = content.replace('"force_debug": true',
                              '"force_debug": false, "force_debug_prod": false')
    descriptor.write_text(content)
    shutil.copytree(framework / "src/common/exlaunch", work / "src/common/exlaunch",
                    dirs_exist_ok=True)
    shutil.copytree(framework / "src/common/memory", work / "src/common/memory",
                    dirs_exist_ok=True)
    shutil.copytree(PROJECT / "native", work / "src/mod", dirs_exist_ok=True)
    shutil.copy2(framework / "CMakeLists.txt", work / "CMakeLists.txt")
    shutil.copy2(PROJECT / "native/config.cmake", work / "config.cmake")
    hooks = signatures(text, work / "src/mod/signatures.hpp")
    hook_offsets(work / "src/mod/hooks.hpp")
    placements(PROJECT / "placements.json", work / "src/mod/placements.hpp")
    check_ultrawide_overlap(hooks)
    run(sys.executable, "-m", "unittest", "discover",
        "-s", str(PROJECT / "tests"), "-p", "test_*.py")
    if args.prepare_only:
        print(work)
        return
    host_test = build / "surf_lifecycle_test"
    run("g++", "-std=c++23", "-Wall", "-Wextra",
        f"-I{PROJECT / 'tests/stubs'}", f"-I{work / 'src/mod'}",
        str(PROJECT / "tests/surf_lifecycle.cpp"), "-o", str(host_test))
    run(str(host_test))
    if args.test_only:
        return
    # Keep the previous container's CMake cache separate. Refresh configuration
    # when Nix changes store paths while retaining compiled object files.
    output = work / "out-nix"
    run("cmake", "--fresh", "-S", str(work), "-B", str(output),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_TOOLCHAIN_FILE={work / 'cmake/toolchain.cmake'}")
    run("cmake", "--build", str(output), "--target", "HiddenMoves_Diamond_all",
        "--parallel", "4")
    artifacts = output / "HiddenMoves_Diamond_out"
    npdm = (artifacts / "main.npdm").read_bytes()
    validate_process_descriptor(npdm)
    if (artifacts / "subsdk9").read_bytes()[:4] != b"NSO0":
        raise ValueError("Native module is not an NSO")
    dist = PROJECT.parent / "dist/Party Hidden Moves v1.3.0"
    (dist / "exefs").mkdir(parents=True, exist_ok=True)
    for name in ("subsdk9", "main.npdm"):
        shutil.copy2(artifacts / name, dist / "exefs" / name)
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(framework / name, dist / name)
    shutil.copy2(PROJECT / "README.md", dist / "README.md")
    model_directory = PROJECT.parent / "extracted/romfs/Data/StreamingAssets/AssetAssistant/Pokemon Database/pokemons/field"
    if model_directory.is_dir():
        (dist / "model_catalog.txt").write_text("\n".join(sorted(p.name for p in model_directory.iterdir() if p.is_file())) + "\n")
    # Include the complete built framework and authored source for review and
    # redistribution. The archive contains no extracted game data.
    with tarfile.open(dist / "source.tar.gz", "w:gz") as archive:
        for name in ("include", "cmake", "module", "src", "CMakeLists.txt", "config.cmake"):
            archive.add(work / name, arcname=f"HiddenMoves/{name}")
        for name in ("LICENSE", "NOTICE"):
            archive.add(framework / name, arcname=f"HiddenMoves/{name}")
    manifest = {
        "title_id": "0100000011D90000", "version": "1.3.0", "build_id": BUILD_ID,
        "framework": {"url": FRAMEWORK_URL, "revision": FRAMEWORK_REV},
        "toolchain": {
            "devkitpro": str(devkitpro),
            "compiler": subprocess.check_output([str(compiler), "--version"],
                                                text=True).splitlines()[0],
            "flake_lock_sha256": hashlib.sha256(
                (PROJECT.parent / "flake.lock").read_bytes()).hexdigest(),
        },
        "hooks": hooks,
        "placements": json.loads((PROJECT / "placements.json").read_text()),
        "native_lifecycle_tests_passed": True,
        "eden_0_2_1_metadata_validated": True,
        "runtime_tested": False,
        "sha256": {name: hashlib.sha256((dist / "exefs" / name).read_bytes()).hexdigest()
                   for name in ("subsdk9", "main.npdm")},
    }
    (dist / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Built hidden moves prototype: {dist}")


if __name__ == "__main__":
    main()
