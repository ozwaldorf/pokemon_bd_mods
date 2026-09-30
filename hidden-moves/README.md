# Party Pokémon for Hidden Moves

For Pokémon Brilliant Diamond 1.3.0, tested locally in Eden.

## Implemented

- **Surf, Waterfall, and Rock Climb:** replace Bibarel with the first non-egg
  party Pokémon that knows the move. Fainted Pokémon remain eligible.
- Party appearance is preserved, including form, sex, and shiny state.
- Summoning previews use the selected Pokémon. English success messages use
  its name or nickname.
- Waterfall switches back to the Surf user after ascent. Rock Climb supports
  ascent and descent, then removes the mount on dismount.
- Bibarel remains the fallback when no eligible Pokémon is available or a
  replacement fails to load.
- Saved position, rotation, and scale profiles. Rock Climb has its own table,
  separate from Surf and Waterfall.
- Live model and placement overrides, with settings saved automatically.
- Placement coverage for 127 Surf candidates and 93 Rock Climb candidates.
  Most Rock Climb placements are geometry estimates.

## Remaining

- Fly, Cut, Rock Smash, Strength, and Defog replacements and previews.
- Refine Rock Climb placements and check wall clearance in both directions.
- Verify movement, full animation cycles, battles, area changes, and save reloads
  across the supported models. Surf checks so far mainly cover stationary fit.
- Make the player follow the mount's idle bobbing.
- Replace helper names in dialogue outside English.

## Development

### Install the dumps and keys

Use the shared [development setup](../README.md#development). You need Nix
with flakes enabled, your own Brilliant Diamond base-game NSP and v1.3.0 update
NSP, and your own keys capable of decrypting both dumps. Place them at the
repository root with these exact filenames:

```text
dumps/
├── base.nsp
├── update.nsp
└── prod.keys
```

From the repository root, enter the development shell and create the merged
extraction:

```sh
nix develop
just setup
just extract
```

The build and live tuning tools use `extracted/exefs/main` and
`extracted/romfs/Data/`. This extraction is shared with ultrawide; if you
already created it, reuse it. Keep these original files untouched. Private
dumps, keys, extracted files, and generated output are Git-ignored.

### Build and install

Run these commands from the repository root, inside the development shell:

```sh
just build-hidden-moves
just install-hidden-moves
```

The build fetches the pinned ExLaunch framework and uses the Switch toolchain
provided by Nix, then writes the generated mod to `hidden-moves/dist/`. Installation
copies it to
`~/.local/share/eden/load/0100000011D90000/Party Hidden Moves v1.3.0/` and
initializes the live debug configuration. Restart the game after installing.

Use `just check` to syntax-check the Python scripts and `just test-hidden-moves` to run the
native lifecycle checks with a mocked engine boundary.
