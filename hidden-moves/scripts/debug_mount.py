#!/usr/bin/env python3
"""Edit the live Surf debug configuration in Eden's emulated SD card."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = Path.home() / '.local/share/eden/sdmc/hidden-moves-debug.cfg'
PLACEMENT_KEYS = ('offset', 'rotation', 'scale')


def profile(config):
    result = {}
    for key in PLACEMENT_KEYS:
        values = [float(value) for value in config[key].split(',')]
        if len(values) != 3 or any(not math.isfinite(v) for v in values):
            raise ValueError(f'{key} needs three finite numbers')
        if (any(v < 0.01 or v > 10 for v in values) if key == 'scale'
                else any(abs(v) > 1000 for v in values)):
            raise ValueError(f'{key} is outside the supported range')
        result[key] = values
    return result


def save_profile(placements, config, move='surf'):
    if config['enabled'] != '1':
        return
    model = config['model']
    match = re.fullmatch(r'pm(\d{4})_(\d{2})_(\d{2})', model)
    if model != 'party' and (not match or not 1 <= int(match[1]) <= 493):
        raise ValueError(f'Invalid model in debug file: {model}')
    saved = profile(config)
    model_table = 'rock_climb_models' if move == 'rock-climb' else 'models'
    species_table = 'rock_climb' if move == 'rock-climb' else 'species'
    placements.setdefault(model_table, {})[model] = saved
    # The native placement table currently selects by species. Preserve variant
    # tweaks separately; only the base model updates the compiled species table.
    if match and match[2] == '00' and match[3] == '00':
        placements.setdefault(species_table, {})[str(int(match[1]))] = saved


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.hidden-moves-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def catalog():
    folder = PROJECT.parent / 'extracted/romfs/Data/StreamingAssets/AssetAssistant/Pokemon Database/pokemons/field'
    if folder.is_dir():
        return sorted(p.name for p in folder.iterdir() if p.is_file())
    path = PROJECT / 'dist/model_catalog.txt'
    return path.read_text().splitlines() if path.exists() else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, default=DEFAULT_FILE)
    parser.add_argument('--placements', type=Path, default=PROJECT / 'placements.json',
                        help='Saved profiles (defaults to the project placement table)')
    parser.add_argument('--move', choices=('surf', 'rock-climb'),
                        help='Placement table to tune (otherwise retained from the debug file)')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    commands.add_parser('off')
    commands.add_parser('show')
    listing = commands.add_parser('list')
    listing.add_argument('filter', nargs='?', default='')
    setting = commands.add_parser('set')
    setting.add_argument('--model', help='Pokédex number, field asset name, or party')
    setting.add_argument('--offset', type=float, nargs=3)
    setting.add_argument('--rotation', type=float, nargs=3)
    setting.add_argument('--scale', type=float, nargs='+')
    args = parser.parse_args()
    args.file = args.file.expanduser()
    args.placements = args.placements.expanduser()
    if args.command == 'list':
        query = f'pm{int(args.filter):04d}_' if args.filter.isdigit() else args.filter
        print('\n'.join(name for name in catalog() if query in name))
        return
    defaults = dict(enabled='0', model='pm0130_00_00', offset='0,-0.3,0.1', rotation='0,0,0', scale='0.7,0.7,0.7')
    previous_move = 'surf'
    if args.file.exists():
        for line in args.file.read_text().splitlines():
            if line.strip() == '# placement_scope=rock-climb':
                previous_move = 'rock-climb'
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                key, value = line.split('=', 1)
                if key.strip() in defaults:
                    defaults[key.strip()] = value.strip()
    if args.command == 'show':
        print(args.file.read_text() if args.file.exists() else f'No debug file: {args.file}')
        return
    if args.command == 'init' and args.file.exists():
        print(f'Preserved {args.file}')
        return
    previous = defaults.copy()
    move = args.move or previous_move
    placements = None
    if args.command in ('set', 'off'):
        try:
            placements = json.loads(args.placements.read_text())
            save_profile(placements, previous, previous_move)
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f'Cannot save model settings: {error}')
    if args.command == 'off':
        defaults['enabled'] = '0'
    if args.command == 'set':
        defaults['enabled'] = '1'
        if args.model:
            model = f'pm{int(args.model):04d}_00_00' if args.model.isdigit() else args.model
            if model != 'party' and model not in catalog():
                parser.error(f'Unknown field model: {model}; use list to inspect available variants')
            if model != previous['model'] or move != previous_move:
                model_table = 'rock_climb_models' if move == 'rock-climb' else 'models'
                species_table = 'rock_climb' if move == 'rock-climb' else 'species'
                saved = placements.get(model_table, {}).get(model)
                if saved is None and model != 'party':
                    saved = placements.get(species_table, {}).get(str(int(model[2:6])))
                if saved is None and model != 'party':
                    saved = placements['species'].get(str(int(model[2:6])))
                if saved is None:
                    saved = placements['default']
                for key in PLACEMENT_KEYS:
                    defaults[key] = ','.join(str(v) for v in saved[key])
            defaults['model'] = model
        for key in ('offset', 'rotation', 'scale'):
            values = getattr(args, key)
            if values is None:
                continue
            if key == 'scale' and len(values) == 1:
                values *= 3
            if len(values) != 3 or any(not math.isfinite(v) for v in values):
                parser.error(f'{key} needs three finite numbers (scale also accepts one)')
            if any(v < 0.01 or v > 10 for v in values) if key == 'scale' else any(abs(v) > 1000 for v in values):
                parser.error(f'{key} is outside the supported range')
            defaults[key] = ','.join(str(v) for v in values)
    if placements is not None:
        try:
            save_profile(placements, defaults, move)
        except (ValueError, KeyError, TypeError) as error:
            parser.error(f'Cannot save model settings: {error}')
        if move == 'rock-climb' and args.command == 'set' and any(
                getattr(args, key) is not None for key in PLACEMENT_KEYS):
            match = re.fullmatch(r'pm(\d{4})_00_00', defaults['model'])
            if match:
                manual = set(placements.get('rock_climb_manual_species', []))
                manual.add(int(match[1]))
                placements['rock_climb_manual_species'] = sorted(manual)
        atomic_write(args.placements, json.dumps(placements, indent=2) + '\n')
    text = '# Live hidden move preview; enabled=0 restores normal party selection.\n'
    text += f'# placement_scope={move}\n'
    text += ''.join(f'{key}={value}\n' for key, value in defaults.items())
    atomic_write(args.file, text)
    print(f'Updated {args.file}\n{text}', end='')


if __name__ == '__main__':
    main()
