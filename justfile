set shell := ["bash", "-euo", "pipefail", "-c"]

dist_ultrawide := "dist/3440x1440 21.9 Complete UI v1.3.0"
dist_hidden_moves := "dist/Party Hidden Moves v1.3.0"
device_load := "/sdcard/Android/data/dev.eden.eden_emulator.nightly/files/load/0100000011D90000"

# Set up the shared Python environment.
setup:
    uv sync --frozen

# Prepare shared extracted/exefs and extracted/romfs from dumps/.
extract:
    uv run python scripts/extract_game.py

# Syntax-check all Python tools.
check:
    uv run python -c 'from pathlib import Path; [compile(p.read_bytes(), str(p), "exec") for g in ("scripts/*.py", "*/scripts/*.py") for p in Path().glob(g)]'

# Build the ultrawide UI mod from the untouched v1.3.0 extraction.
[working-directory: 'ultrawide']
build-ultrawide:
    uv run python scripts/build_ultrawide_ui.py \
      --romfs ../extracted/romfs \
      --pchtxt ultrawide-v1.3.0.pchtxt \
      --output "../{{dist_ultrawide}}"

# Audit the generated ultrawide UI bundles.
[working-directory: 'ultrawide']
audit-ultrawide:
    audit_dir="$(mktemp -d -t pokemon-bd-ui-audit.XXXXXX)"; \
    uv run python scripts/audit_unity_ui.py "../{{dist_ultrawide}}/romfs/Data/StreamingAssets/AssetAssistant/UIs" "$audit_dir"; \
    echo "Audit written to $audit_dir"

# Install the ultrawide mod into local Eden.
install-ultrawide:
    uv run python scripts/install_mod.py --source "{{dist_ultrawide}}"

# Copy the ultrawide mod to the connected Android device.
push-ultrawide:
    adb shell 'rm -rf "{{device_load}}/{{file_name(dist_ultrawide)}}"'
    adb shell 'mkdir -p "{{device_load}}"'
    adb push "{{dist_ultrawide}}" "{{device_load}}/"

# Build the hidden moves native mod with the Nix shell's Switch toolchain.
build-hidden-moves:
    uv run python hidden-moves/scripts/build_mod.py

# Exercise the hidden moves native lifecycle with a mocked engine boundary.
test-hidden-moves:
    uv run python hidden-moves/scripts/build_mod.py --test-only

# Install the hidden moves mod into local Eden.
install-hidden-moves:
    uv run python scripts/install_mod.py --source "{{dist_hidden_moves}}"
    uv run python hidden-moves/scripts/debug_mount.py init

# List models or update the live hidden moves debug configuration without rebuilding.
debug-hidden-moves *args:
    uv run python hidden-moves/scripts/debug_mount.py {{args}}

# Take a temporary screenshot from the connected Android device.
capture:
    capture_dir="$(mktemp -d -t pokemon-bd-capture.XXXXXX)"; \
    adb exec-out screencap -p > "$capture_dir/screen.png"; \
    echo "Screenshot written to $capture_dir/screen.png"
