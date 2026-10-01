# Party Pokémon for Hidden Moves

For Pokémon Brilliant Diamond 1.3.0, tested locally in Eden.

## Implemented

- **Surf, Waterfall, and Rock Climb:** replace Bibarel with the first non-egg
  party Pokémon that knows the move. Fainted Pokémon remain eligible.
- Party appearance is preserved, including form, sex, and shiny state.
- Summoning previews use the selected Pokémon. English success messages use
  its name or nickname.
- **Cut, Rock Smash, Strength, and Defog:** party-based slide-in models and
  English helper messages. Strength keeps its follow-up text.
- **Fly:** replace Staraptor during takeoff and landing with the first non-egg
  party Pokémon that knows Fly. The mount follows the original animated body
  bone and uses its own battle idle animation when available.
- Waterfall switches back to the Surf user after ascent. Rock Climb supports
  ascent and descent, then removes the mount on dismount.
- The original helper remains the fallback when no eligible Pokémon is
  available or a replacement fails to load. Fly bounds its loading wait.
- Saved position, rotation, and scale profiles. Rock Climb and Fly have their
  own tables, separate from Surf and Waterfall.
- Live model and placement overrides, with settings saved automatically.
- Placement coverage for 127 Surf candidates and 93 Rock Climb candidates.
  Most Rock Climb placements are geometry estimates.

## Remaining

- Verify Fly takeoff and landing in Eden, then tune placements and animations
  for individual Pokémon. Fly currently uses a shared initial placement.
- Refine Rock Climb placements and check wall clearance in both directions.
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

### Build and install

Run these commands from the repository root, inside the development shell:

```sh
just build-hidden-moves
just install-hidden-moves
```

The build fetches the pinned ExLaunch framework and uses the Switch toolchain
provided by Nix, then writes the generated mod to `dist/Party Hidden Moves v1.3.0/`. Installation
copies it to `~/.local/share/eden/load/0100000011D90000/Party Hidden Moves v1.3.0/`.
Restart the game after installing.

`just debug-hidden-moves set ...` creates the live debug configuration. The
mod reads it at startup and at each traversal cut-in, and polls it while
enabled. Changes made while disabled apply at the next cut-in.
Use `just debug-hidden-moves --move fly set --model 398` to tune Fly.
Overrides apply to their selected move; Surf settings also cover Waterfall.

Use `just check` to syntax-check the Python scripts and `just test-hidden-moves` to run the
native lifecycle checks with a mocked engine boundary.
