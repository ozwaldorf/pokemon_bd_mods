# Pokémon Brilliant Diamond Mods

Various mod projects targeting Brilliant Diamond v1.3.0

## AI assistance disclaimer

This project was developed with AI assistance, including code, patches, and
documentation. AI-assisted work can contain mistakes, and testing does not cover
every game state. These mods are experimental; keep backups of your saves.

## Projects

| Directory | Project |
| --- | --- |
| [ultrawide/](ultrawide/README.md) | True Ultrawide UI 3440x1440 21:9 mod and build tools |
| [hidden-moves/](hidden-moves/README.md) | Party Pokémon hidden-move previews and dialogue, plus Surf, Waterfall, Rock Climb, and Fly mounts |
| [skip-intro/](skip-intro/README.md) | Skip the startup intro movie and title screen, then load automatically |
| `dumps/` | Shared private base/update NSPs and `prod.keys` |
| `extracted/` | Shared untouched merged ExeFS and RomFS |

## Development

### Requirements

- x86_64 Linux with Nix and flakes enabled (the provided shell targets this platform).
- Your own Pokémon Brilliant Diamond base-game NSP and v1.3.0 update NSP.
- Your own `prod.keys` that can decrypt both NSPs.
- Disk space for the dumps, intermediate extraction, and merged game files.

All projects target title `0100000011D90000`, version `1.3.0`, build `94CEAE325C205C4B9D6F7235552F28FD`.

### Install the dumps and keys

From the repository root, copy your existing dumps and keys into a new folder `./dumps/`.
The destination filenames must match exactly:

```text
dumps/
├── base.nsp      # Brilliant Diamond base game
├── update.nsp    # Brilliant Diamond v1.3.0 update
└── prod.keys     # Keys for decrypting your dumps
```

### Create the shared extraction

The root `flake.nix` and `flake.lock` provide the shared development tools,
including the pinned devkitA64 compiler, libnx, and Switch packaging tools.
From the repository root, run:

```sh
nix develop
just setup
just extract
```

The shared [extraction script](scripts/extract_game.py) merges the base game and
update into the directories expected by the projects:

```text
extracted/
├── exefs/
│   └── main
└── romfs/
    └── Data/
```

### Build a project

Stay in the development shell at the repository root and choose one project:

```sh
just build-ultrawide
just build-hidden-moves
just build-skip-intro
```

All commands run from the repository root; `just --list` shows them all.
Generated mods are written to `dist/`, one directory per mod named as Eden
expects, so each can be copied directly into the load directory.
See the [ultrawide instructions](ultrawide/README.md#development) or
[hidden-moves instructions](hidden-moves/README.md#development) for checks,
installation, and in-game testing. The [startup skip instructions](skip-intro/README.md)
cover its build, installation, and validation.

`just install-ultrawide`, `just install-hidden-moves`, and `just install-skip-intro` install into local Eden at
`~/.local/share/eden/load/0100000011D90000/`.

Private game files, keys, virtual environments, and generated output are
Git-ignored. Do not commit or distribute game dumps or keys.

## License

[MIT](LICENSE), except `ultrawide/ultrawide-v1.3.0.pchtxt`, which is
third-party work; see [its attribution](ultrawide/ATTRIBUTION.md).
