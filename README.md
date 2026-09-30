# Pokémon Brilliant Diamond mods

Separate mod projects targeting Brilliant Diamond v1.3.0:

| Directory | Project |
| --- | --- |
| [ultrawide/](ultrawide/README.md) | Existing 3440×1440 ultrawide UI mod and build tools |
| [hidden-moves/](hidden-moves/README.md) | Native party Pokémon Surf replacement prototype |
| `dumps/` | Shared private base/update NSPs and `prod.keys` |
| `extracted/` | Shared untouched merged ExeFS and RomFS |

The root `flake.nix` and `flake.lock` provide the shared development environment:

```sh
nix develop
cd ultrawide # or hidden-moves
uv sync --frozen
```

Run each project's commands from its own directory. The ultrawide project's
`just extract` prepares the shared extraction used by both projects.
Generated mod output lives in each project's `dist/` directory.

Each project provides `just install` for local Eden at
`/home/oz/.local/share/eden/load/0100000011D90000/`. Restart the game after
installing a new build. The hidden-moves native build also requires Docker.

Private game files, keys, virtual environments, and generated output are
Git-ignored. Do not commit or distribute game dumps or keys.
