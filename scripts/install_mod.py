#!/usr/bin/env python3
"""Install one built project into the local Eden mod directory."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--load-dir", type=Path,
                        default=Path.home() / ".local/share/eden/load/0100000011D90000")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not any((source / directory).is_dir() and any((source / directory).rglob("*"))
               for directory in ("exefs", "romfs")):
        parser.error(f"No built mod files under {source}; build the project first")
    load = args.load_dir.expanduser().resolve()
    destination = load / source.name
    if source == destination or source in destination.parents or destination in source.parents:
        parser.error("Source and installation paths must be separate")
    if destination.is_symlink():
        parser.error("Refusing to replace a symlinked mod directory")
    load.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{source.name}-install-", dir=load))
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix="pokemon-bd-mod-backup-"))
            shutil.copytree(destination, backup / source.name)
            print(f"Previous installation backed up to {backup / source.name}")
            shutil.rmtree(destination)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"Installed {destination}")


if __name__ == "__main__":
    main()
