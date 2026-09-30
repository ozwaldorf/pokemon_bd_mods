# Party Pokémon for Hidden Moves

A native Surf, Waterfall, and Rock Climb prototype for Pokémon Brilliant Diamond v1.3.0, title
`0100000011D90000`, build `94CEAE325C205C4B9D6F7235552F28FD`.

The mod picks the first non-egg party member that knows **Surf**, loads its
existing field model with its form, sex, and shiny appearance, and parents it
to the game's moving Bibarel transform. It hides the original renderer after
the replacement loads. Bibarel's movement, collision, progression checks,
effect anchors, and traversal rig continue running. No PP is consumed, and
fainted members remain eligible. If nobody knows Surf, the vanilla helper stays.

Waterfall's summoning preview and uphill traversal use the first non-egg party
member that knows Waterfall (move 127). The mount returns to the first Surf user
when the climb ends. If the same member knows both moves, its model stays loaded.
Without a Waterfall user, the vanilla helper is retained for the climb. Automatic
downhill travel retains the Surf mount. Both moves share the saved placements,
movement anchor, and live debug configuration.

Rock Climb's summoning preview and both uphill and downhill traversal use the
first non-egg party member that knows Rock Climb (move 431). The replacement
follows the same Bibarel anchor and visibility, starting on land and releasing
the model when the climb ends. Missing users or failed model loads retain the
vanilla helper. Rock Climb has a separate saved placement table so cliff
corrections do not change Surf or Waterfall. Its fit still needs an in-game check, especially
for species without a saved placement.

`rock-climb-candidates.json` records the 92 BDSP TM100 learners, plus Smeargle
through Sketch. The TM list matches the owned game's compatibility data and
[Serebii's BDSP-specific table](https://www.serebii.net/attackdex-swsh/rockclimb.shtml)
exactly. All 93 have field models; 62 lacked a saved Surf placement when checked.
Geodude now has a larger geometry-based starting placement, which still needs
an in-game check. Rock Climb diagnostics log the selected species, requested
visibility, hierarchy visibility, world position, and inherited scale when
the model attaches or its visibility changes.

The 61 remaining species now have geometry-based starting placements in
`placements.json`. Run `.venv/bin/python scripts/analyze_rock_climb.py` to inspect
the meshes and skeletons again; add `--apply` to save missing profiles, or
`--apply --refresh-estimates` to recalculate generated profiles that have not
been manually changed. Existing user adjustments are preserved. Reports go to
`/tmp/hidden-moves-rock-climb-analysis/`. Estimates account for torso skin
weights, body posture, evolutionary relatives, and rider contact relative to
the selected calibration model. All estimates still need live verification; unusual rigs and
long silhouettes are flagged in the report.

Graveler's later wall-clearance adjustments are applied to the Rock Climb
contact point for 91 other models; Geodude and Graveler retain their manual
settings. The calibration changes offsets using each model's torso surface,
saved scale and tilt. It preserves the water placement table. The report is
`/tmp/hidden-moves-rock-climb-calibration/report.txt`. To recalibrate from another
tuned model, run `.venv/bin/python scripts/calibrate_rock_climb.py --reference 75 --apply`.
Models manually adjusted in Rock Climb debug mode are protected from recalibration.

Use `scripts/debug_mount.py --move rock-climb set --model 75` to tune cliff
placements, or `--move surf` for Surf/Waterfall. The debug file retains that
scope for subsequent `set` commands, and the native parser ignores its scope
comment. The current debug override applies live; compiled party selection
chooses the appropriate placement table for each move.

English Surf, Waterfall, and Rock Climb success messages name the selected party Pokémon
(including its nickname) instead of a wild Bibarel. Messages are cloned per use;
without an eligible user, the vanilla wording remains. Other languages and fixed
debug model overrides retain their original wording.

The initial placement profile is for **Gyarados (#130)**. Put your Gyarados
before any other Surf users in the party and make sure it actually knows Surf.
The generic profile also allows other field models, but their placement needs
in-game tuning. Selection is held for the session, so reordering your party
while surfing does not replace the live mount.

## Status

The AArch64 module builds, and tests exercise the actual native session code
against a mocked engine. They cover first eligible party selection, egg
exclusion, delayed loading, helper visibility, party reordering, canceled
loads, asset failure, cleanup, and loading a save while already surfing.
Stationary Surf placements have been checked in Eden for 90 additional models,
with 37 earlier profiles retained. Movement and full animation cycles still
need verification.

This version replaces the Surf/Waterfall/Rock Climb mount and redirects their summoning
cut-ins to the first party user of the corresponding move. Fly,
the other helpers, and dialogue in other languages
remain future work. The replacement follows the helper's visibility during
boarding and swimming. Bibarel is suppressed while the boarding model loads,
and restored if loading fails. There are no new riding
poses: the replacement keeps its own skeleton, and its field movement component
is disabled so it cannot overwrite the parented transform or join collision.
The mod rebuilds and advances the visual animation graph after disabling that
component, since its `OnDisable` destroys the graph. It checks for drawable
meshes before hiding Bibarel. Gyarados's size and
position are starting values, not a visually verified fit.

## Build and install

Use the shared development shell from this directory:

```sh
nix develop ..
just setup
just build
just install
```

The native build uses Docker and a pinned devkitPro image. The builder fetches
a pinned ExLaunch framework into ignored `build/`, validates the owned game
executable's build ID, checks for overlap with the ultrawide ExeFS patches,
runs the lifecycle tests, and cross-compiles the module. It handles both normal
and rootless Docker. `just test` runs the lifecycle tests separately.

The generated `dist/` contains `exefs/subsdk9`, `exefs/main.npdm`, a build
manifest, licenses, and a complete source archive. No owned game dumps or keys
are included. The module checks native signatures before installing hooks.
The ExLaunch process descriptor enables the permissions needed for native
hooks; packaging validates its program ID and kernel capabilities against
Eden 0.2.1's rules. Debug permissions use the compatible `allow_debug` flag;
the toolchain's newer `force_debug` flag sets a bit this Eden version rejects.

`just install` installs into:

```text
/home/oz/.local/share/eden/load/0100000011D90000/Party Hidden Moves v1.3.0/
```

An existing installation of that same mod is backed up under `/tmp` before
replacement. Other mod directories are preserved. Restart the game after
installation, and enable this mod in Eden's game properties. The ultrawide
project has its own `just install` command for the same local Eden directory.
Avoid another mod that supplies `subsdk9` or a conflicting process descriptor.

## Gyarados tuning and verification

`placements.json` specifies local offsets, Euler rotations, and scales. Its
`species.130` entry controls Gyarados; `default` applies to other species.
Offsets are relative to the Surf anchor (`mcl_00`), whose prefab position is
one unit below the player. The initial vertical offset compensates for that.
Edit those numbers, then run `just build` and `just install` again. The player
riding pose stays the original game's pose.

The first in-game check should cover boarding, turning, traveling, fishing,
and dismounting. Then check battles, area changes, saving/reloading on water,
and outfit changes. Also confirm that a party without Surf retains Bibarel.
Waterfall tests cover different Surf/Waterfall users, a shared user without
reloading, egg exclusion, missing users, pending-load cancellation, preview
selection and returning to Surf. The user confirmed uphill traversal and
party-member slide-ins and English dialogue in Eden. Rock Climb tests cover
starting on land, egg exclusion, repeated command frames, boarding visibility,
completion on land, canceled loads, failed assets, missing users, preview
selection, area-change cleanup, and English dialogue. Rock Climb still needs
in-game verification of ascent, descent, and placement.
Native diagnostics appear as `HiddenMoves:` messages through the emulator's
debug output when that logging is enabled.

## Live model and placement testing

After installing this version, restart the game once. Subsequent debug edits
are read every half-second while the player updates; there is no rebuild or
game restart for changing models, offsets, rotations, or scales.

The editable file is:

```text
/home/oz/.local/share/eden/sdmc/hidden-moves-debug.cfg
```

Its initial contents have debugging disabled, retaining ordinary party selection:

```ini
enabled=0
model=pm0130_00_00
offset=0,-0.3,0.1
rotation=0,0,0
scale=0.7,0.7,0.7
```

Set `enabled=1` to force that field model while surfing, including Pokémon
outside the party. `model=party` retains party selection but uses the explicit
placement values. `enabled=0` or removing the file restores compiled placement
profiles and party selection. Pausing the game pauses polling.

From `hidden-moves/`, these commands edit the file atomically:

```sh
just debug list             # Available field asset names
just debug list 131         # Lapras variants
just debug set --model 130 --offset 0 -0.3 0.1 --scale 0.7
just debug set --model 131 --offset 0 0.5 0 --scale 0.7
just debug set --offset 0 -0.8 0.1
just debug set --rotation 0 90 0
just debug set --model party
just debug off
```

The helper automatically saves settings to `placements.json` on each `set`
and before switching models or turning debug mode off. Selecting a model again
restores its saved settings; explicit placement arguments override them. New
models start with the project default. Base model settings also update the
species table used by the next build; variants have separate saved profiles.
Edits made directly to the SD card file are saved the next time the helper runs
`set` or `off`. Use `--placements PATH` to isolate profiles when testing with
an alternate `--file`.

Changing only placement updates the current instance immediately. Changing the
model restores Bibarel during asynchronous swaps while already swimming, then
hides it once a drawable replacement is ready. Initial boarding suppresses
Bibarel while loading. Pending requests retire before a newer swap starts.
Invalid or incomplete file contents retain the last valid configuration; the
file is bounded to 1 KiB. Scale must be between 0.01 and 10 per axis.

The SD card is mounted as `hmsd:` through the game's SDK, rather than reading
the immutable ExeFS module. If that mount fails, normal party mode remains
available. The debug cut-in resolves a valid base appearance, including
genderless and male-only species, and retains the vanilla preview if catalog
or framing data is unavailable. Normal
party mode preserves the selected Pokémon's form, sex, and shiny state through
the game's `Load(PokemonParam)` cut-in method. Preview framing and the new live
controls still need verification in Eden.

## Asset inspection

```sh
just inspect
just inspect pm0419_00_00 fc0002_00
just check
```

The read-only inspector writes a fresh JSON report under `/tmp`. It lists
helper hierarchies, renderer bones, animation bindings, and replacement model
transforms. Its defaults are Gyarados (`pm0130_00_00`) and player `fc0001_00`.
Shared untouched game files remain in `../extracted/`.

## Framework provenance

The native loader/hook framework comes from
[TeamLumi/Luminescent_ExLaunch](https://github.com/TeamLumi/Luminescent_ExLaunch)
at commit `0d457adae65e5e56de35463b910aabc02903e7fd`. This project supplies a
separate Surf module and adapts the framework's CMake helper to allow no
embedded shaders and its descriptor template to the pinned toolchain's JSON
field names. It does not include Luminescent's gameplay features. The generated
package preserves the upstream `LICENSE` and `NOTICE`, including their
references to the original ExLaunch projects, and includes complete build source.
