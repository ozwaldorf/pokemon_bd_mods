#!/usr/bin/env python3
"""Merge the owned base NSP and v1.3.0 update into shared ExeFS and RomFS."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from staging import replace_directory

PROJECT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dumps", type=Path, default=PROJECT / "dumps")
    parser.add_argument("--output", type=Path, default=PROJECT / "extracted")
    args = parser.parse_args()
    dumps = args.dumps.expanduser().resolve()
    output = args.output.expanduser().absolute()
    inputs = [dumps / name for name in ("base.nsp", "update.nsp", "prod.keys")]
    for path in inputs:
        if not path.is_file():
            parser.error(f"Missing required input: {path}")
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        parser.error("--output must be a directory, not a file or symlink")
    if any(path == output or output in path.parents for path in inputs):
        parser.error("--output must not contain the input dumps or keys")
    tool = shutil.which("hactoolnet")
    if tool is None:
        parser.error("hactoolnet is required; run this command inside nix develop")
    base, update, keys = inputs

    def run(*arguments: str, capture: bool = False):
        return subprocess.run(
            [tool, "--disablekeywarns", "-k", str(keys), *arguments],
            check=True, text=True,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        )

    def program_nca(nsp: Path) -> str:
        listing = run("-t", "pfs0", "--listncas", str(nsp), capture=True).stdout
        matches = re.findall(r"^\s*([0-9a-fA-F]{32})\s+Program\b", listing, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"Expected one Program NCA in {nsp.name}; found {len(matches)}")
        return matches[0].lower()

    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem so publishing uses directory renames.
    # Keep the current extraction intact until both extraction and validation pass.
    with tempfile.TemporaryDirectory(prefix=".pokemon-bd-extract-", dir=output.parent) as temporary:
        work = Path(temporary)
        base_id, update_id = program_nca(base), program_nca(update)
        for label, nsp in (("base", base), ("update", update)):
            folder = work / label
            folder.mkdir()
            run("-t", "pfs0", "--outdir", str(folder), str(nsp))
        merged = work / "output"
        (merged / "romfs").mkdir(parents=True)
        (merged / "exefs").mkdir()
        run("--basenca", str(work / "base" / f"{base_id}.nca"),
            "--romfsdir", str(merged / "romfs"),
            "--exefsdir", str(merged / "exefs"),
            str(work / "update" / f"{update_id}.nca"))
        if not (merged / "exefs/main").is_file() or not any((merged / "romfs").iterdir()):
            raise ValueError("Extraction did not produce ExeFS main and RomFS data")
        replace_directory(merged, output)
    print(f"Merged game files written to {output}")


if __name__ == "__main__":
    main()
