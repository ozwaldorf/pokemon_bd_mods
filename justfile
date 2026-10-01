set shell := ["bash", "-euo", "pipefail", "-c"]

# Built ultrawide mod directories end with their aspect ratio.
ultrawide_glob := '"dist/True Ultrawide UI "*"x1440 "*'
dist_hidden_moves := "dist/Party Hidden Moves v1.3.0"
dist_skip_intro := "dist/Skip Intro and Title v1.3.0"
device_load := "/sdcard/Android/data/dev.eden.eden_emulator.nightly/files/load/0100000011D90000"

# Verify the Python environment supplied by the Nix shell.
setup:
    python -c 'import lz4.block, UnityPy; print("Python dependencies ready")'

# Prepare shared extracted/exefs and extracted/romfs from dumps/.
extract:
    python scripts/extract_game.py

# Syntax-check all Python tools.
check:
    python -c 'from pathlib import Path; [compile(p.read_bytes(), str(p), "exec") for g in ("scripts/*.py", "*/scripts/*.py") for p in Path().glob(g)]'

# Build the ultrawide UI mods from the untouched v1.3.0 extraction; ratios: 21:9 20.1:9 (default: all).
[working-directory: 'ultrawide']
build-ultrawide *ratios:
    python scripts/build_ultrawide_ui.py \
      --romfs ../extracted/romfs \
      --pchtxt ultrawide-v1.3.0.pchtxt \
      --dist ../dist \
      {{ prepend("--target ", ratios) }}

# Audit the generated ultrawide UI bundles for one aspect ratio.
[working-directory: 'ultrawide']
audit-ultrawide ratio="21:9":
    audit_dir="$(mktemp -d -t pokemon-bd-ui-audit.XXXXXX)"; \
    python scripts/audit_unity_ui.py "../dist/True Ultrawide UI "*"x1440 {{ratio}}/romfs/Data/StreamingAssets/AssetAssistant/UIs" "$audit_dir"; \
    echo "Audit written to $audit_dir"

# Install built ultrawide mods into local Eden; ratios default to all built.
install-ultrawide *ratios:
    shopt -s nullglob; found=0; \
    for dir in {{ultrawide_glob}}; do \
      [[ -d "$dir" ]] && [[ -z "{{ratios}}" || " {{ratios}} " == *" ${dir##* } "* ]] || continue; \
      python scripts/install_mod.py --source "$dir"; found=1; \
    done; \
    (( found )) || { echo "No built ultrawide mods matching '{{ratios}}'" >&2; exit 1; }

# Copy built ultrawide mods to the connected Android device; ratios default to all built.
push-ultrawide *ratios:
    shopt -s nullglob; found=0; \
    adb shell 'mkdir -p "{{device_load}}"'; \
    for dir in {{ultrawide_glob}}; do \
      [[ -d "$dir" ]] && [[ -z "{{ratios}}" || " {{ratios}} " == *" ${dir##* } "* ]] || continue; \
      adb shell "rm -rf '{{device_load}}/$(basename "$dir")'"; \
      adb push "$dir" "{{device_load}}/"; found=1; \
    done; \
    (( found )) || { echo "No built ultrawide mods matching '{{ratios}}'" >&2; exit 1; }

# Build the hidden moves native mod with the Nix shell's Switch toolchain.
build-hidden-moves:
    python hidden-moves/scripts/build_mod.py

# Exercise the hidden moves native lifecycle with a mocked engine boundary.
test-hidden-moves:
    python hidden-moves/scripts/build_mod.py --test-only

# Install the hidden moves mod into local Eden.
install-hidden-moves:
    python scripts/install_mod.py --source "{{dist_hidden_moves}}"

# List models or update the live hidden moves debug configuration without rebuilding.
debug-hidden-moves *args:
    python hidden-moves/scripts/debug_mount.py {{args}}

# Build the intro movie and title-screen skip patch.
build-skip-intro:
    python skip-intro/scripts/build_mod.py

# Check startup patch encoding and packaging without game dumps.
test-skip-intro:
    python -m unittest discover -s skip-intro/tests -p 'test_*.py'

# Install the startup skip mod into local Eden.
install-skip-intro:
    python scripts/install_mod.py --source "{{dist_skip_intro}}"

# Copy the startup skip mod to the connected Android device.
push-skip-intro:
    adb shell 'rm -rf "{{device_load}}/{{file_name(dist_skip_intro)}}"'
    adb shell 'mkdir -p "{{device_load}}"'
    adb push "{{dist_skip_intro}}" "{{device_load}}/"

# Take a temporary screenshot from the connected Android device.
capture:
    capture_dir="$(mktemp -d -t pokemon-bd-capture.XXXXXX)"; \
    adb exec-out screencap -p > "$capture_dir/screen.png"; \
    echo "Screenshot written to $capture_dir/screen.png"
