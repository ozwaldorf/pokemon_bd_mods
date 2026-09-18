set shell := ["bash", "-euo", "pipefail", "-c"]

romfs := "extracted/romfs"
pchtxt := "ultrawide-v1.3.0.pchtxt"
output := "dist"
device_mod := "/sdcard/Switch/Moda/[3440x1440 21.9 Complete UI v1.3.0]"

# Extract and merge the owned base-game and v1.3.0 update dumps.
extract:
    #!/usr/bin/env bash
    set -euo pipefail

    base_nsp="dumps/base.nsp"
    update_nsp="dumps/update.nsp"
    keys="dumps/prod.keys"

    for input in "$base_nsp" "$update_nsp" "$keys"; do
      if [[ ! -f "$input" ]]; then
        echo "Missing required input: $input" >&2
        exit 1
      fi
    done

    work_dir="$(mktemp -d -t pokemon-bd-extract.XXXXXX)"
    trap 'find "$work_dir" -depth -delete' EXIT

    base_program="$(hactoolnet -t pfs0 --disablekeywarns -k "$keys" \
      --listncas "$base_nsp" | awk '$2 == "Program" { print $1; exit }')"
    update_program="$(hactoolnet -t pfs0 --disablekeywarns -k "$keys" \
      --listncas "$update_nsp" | awk '$2 == "Program" { print $1; exit }')"

    if [[ ! "$base_program" =~ ^[0-9a-f]{32}$ ]]; then
      echo "Could not identify the base-game Program NCA" >&2
      exit 1
    fi
    if [[ ! "$update_program" =~ ^[0-9a-f]{32}$ ]]; then
      echo "Could not identify the update Program NCA" >&2
      exit 1
    fi

    mkdir -p "$work_dir/base" "$work_dir/update"
    hactoolnet -t pfs0 --disablekeywarns -k "$keys" \
      --outdir "$work_dir/base" "$base_nsp" >/dev/null
    hactoolnet -t pfs0 --disablekeywarns -k "$keys" \
      --outdir "$work_dir/update" "$update_nsp" >/dev/null

    mkdir -p "$work_dir/output/romfs" "$work_dir/output/exefs"
    hactoolnet --disablekeywarns -k "$keys" \
      --basenca "$work_dir/base/$base_program.nca" \
      --romfsdir "$work_dir/output/romfs" \
      --exefsdir "$work_dir/output/exefs" \
      "$work_dir/update/$update_program.nca" >/dev/null

    if [[ -e extracted ]]; then
      find extracted -depth -delete
    fi
    mv "$work_dir/output" extracted
    echo "Merged v1.3.0 files written to extracted/"

# Build the mod from the untouched v1.3.0 extraction.
build:
    uv run python scripts/build_ultrawide_ui.py \
      --romfs "{{romfs}}" \
      --pchtxt "{{pchtxt}}" \
      --output "{{output}}"

# Audit the generated UI bundles.
audit:
    #!/usr/bin/env bash
    set -euo pipefail
    audit_dir="$(mktemp -d -t pokemon-bd-ui-audit.XXXXXX)"
    uv run python scripts/audit_unity_ui.py \
      "{{output}}/romfs/Data/StreamingAssets/AssetAssistant/UIs" \
      "$audit_dir"
    echo "Audit written to $audit_dir"

# Take a temporary screenshot from the connected Android device.
capture:
    #!/usr/bin/env bash
    set -euo pipefail
    capture_dir="$(mktemp -d -t pokemon-bd-capture.XXXXXX)"
    adb exec-out screencap -p > "$capture_dir/screen.png"
    echo "Screenshot written to $capture_dir/screen.png"

# Copy the mod to the connected Android device.
push:
    adb shell 'mkdir -p "{{device_mod}}"'
    adb push "{{output}}/." "{{device_mod}}/"

# Compile-check maintained Python sources.
check:
    uv run python -c 'from pathlib import Path; paths = (Path("scripts/build_ultrawide_ui.py"), Path("scripts/audit_unity_ui.py")); [compile(path.read_bytes(), str(path), "exec") for path in paths]'
