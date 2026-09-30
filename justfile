set shell := ["bash", "-euo", "pipefail", "-c"]

# Prepare shared extracted/exefs and extracted/romfs from dumps/.
extract:
    python scripts/extract_game.py
