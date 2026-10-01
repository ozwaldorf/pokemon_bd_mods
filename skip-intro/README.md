# Skip Intro and Title

For Pokémon Brilliant Diamond 1.3.0, title `0100000011D90000`, build
`94CEAE325C205C4B9D6F7235552F28FD`.

Skips the startup intro movie and the title screen's button prompt, entering
the normal loading sequence automatically. With an existing save, this should
resume gameplay; without a save, the normal language and character setup still
applies. This does not skip the story introduction or in-game menus.

The patch redirects the non-ending tail call in `Title.Initialize` from
`Title.PlayOpeningSequence` to `Title.EndTitle`. Movie-player initialization,
the ending/credits branch, save-error checks, and the game's loading coroutine
remain in place. Mandatory startup initialization and loading still take time.

This is an ExeFS text patch, so it can coexist with Party Hidden Moves without
replacing its `subsdk9` or `main.npdm`. Its address does not overlap the current
Ultrawide patches. Disable this mod to access the title screen's backup-save
button combination.

## Build and install

Use the shared [development setup](../README.md#development), then run from
the repository root:

```sh
just build-skip-intro
just install-skip-intro
```

The builder verifies the executable's build ID and original branch before
writing `dist/Skip Intro and Title v1.3.0/`. Installation copies that folder
into local Eden's mod load directory. Enable it in Eden and restart the game.
Use `just push-skip-intro` to copy the built mod to the connected Android device.

## Validation

`just test-skip-intro` checks branch encoding, executable validation, and
generated packaging without requiring private game files. `just check`
syntax-checks the build tools.

The branch and loading path were inspected in the owned executable. The user
confirmed the startup skip works in local Eden on 2026-10-01.
First-time setup, save-error handling, the Hall of Fame ending, and startup
with both Hidden Moves and Ultrawide enabled still need explicit verification.
