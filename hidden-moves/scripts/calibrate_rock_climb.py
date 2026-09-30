#!/usr/bin/env python3
"""Transfer a tuned cliff contact point across Rock Climb model placements."""
import argparse
import copy
import json
from pathlib import Path

from debug_mount import atomic_write
from model_geometry import tilt

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=int, default=75)
    parser.add_argument('--geometry', type=Path,
                        default=Path('/tmp/hidden-moves-rock-climb-analysis/analysis.json'))
    parser.add_argument('--output', type=Path,
                        default=Path('/tmp/hidden-moves-rock-climb-calibration'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = PROJECT / 'placements.json'
    profiles = json.loads(path.read_text())
    inventory_path = PROJECT / 'rock-climb-candidates.json'
    inventory = json.loads(inventory_path.read_text())
    geometry = json.loads(args.geometry.read_text())
    records = {r['species']: copy.deepcopy(r) for r in geometry['records']}
    if set(records) != {r['species'] for r in inventory['candidates']}:
        raise ValueError('Geometry must cover every Rock Climb candidate')
    water_before = copy.deepcopy(profiles['species'])
    current = profiles.get('rock_climb', profiles['species'])
    calibration = current[str(args.reference)]
    contact = tilt(records[args.reference]['seat'], calibration['rotation'][0])
    target = [calibration['offset'][i] + calibration['scale'][0] * contact[i]
              for i in range(3)]
    protected = set(profiles.get('rock_climb_manual_species', [74, 75])) | {args.reference}
    rock, models = {}, {}
    for species, record in records.items():
        if 'error' in record:
            raise ValueError(f"Missing geometry: {species}")
        profile = copy.deepcopy(current.get(str(species), profiles['species'][str(species)]))
        record['water_placement'] = profiles['species'][str(species)]
        if species in protected:
            record['source'] = 'preserved manually tuned Rock Climb profile'
        else:
            seat = tilt(record['seat'], profile['rotation'][0])
            profile['offset'] = [round(target[i] - profile['scale'][0] * seat[i], 2)
                                 for i in range(3)]
            record['source'] = 'Graveler-calibrated geometry estimate'
        record['placement'] = profile
        rock[str(species)] = profile
        models[record['model']] = profile
    # Preserve separately tuned appearance variants.
    for model, profile in profiles.get('rock_climb_models', {}).items():
        if not model.endswith('_00_00'):
            models[model] = profile
    result = {'reference_species': args.reference, 'reference_placement': calibration,
              'target_contact': target, 'preserved_species': sorted(protected),
              'runtime_verified': False, 'records': list(records.values())}
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_write(args.output / 'analysis.json', json.dumps(result, indent=2) + '\n')
    lines = ['Rock Climb wall-clearance calibration', '',
             f'Reference: {args.reference}; profile: {calibration}',
             f'Contact point relative to moving mount anchor: {target}',
             f'{len(rock) - len(protected & set(records))} recalibrated profiles; '
             f'{len(protected & set(records))} manually tuned profiles retained.',
             'Only Rock Climb offsets are recalibrated. Scales, tilts and water profiles remain unchanged.',
             'Body contact is computed from the skinned torso surface and the saved tilt/scale.',
             'These remain estimates; ascent and descent still require in-game verification.', '']
    for species, r in sorted(records.items()):
        p = r['placement']
        lines.append(f"{species:03} {r['name']}: offset {p['offset']}; scale {p['scale'][0]}; "
                     f"pitch {p['rotation'][0]}; {r['source']}")
    atomic_write(args.output / 'report.txt', '\n'.join(lines) + '\n')
    if args.apply:
        profiles['rock_climb'] = rock
        profiles['rock_climb_models'] = models
        profiles['rock_climb_manual_species'] = sorted(protected)
        assert profiles['species'] == water_before
        for candidate in inventory['candidates']:
            species = candidate['species']
            candidate['placement_status'] = records[species]['source'] + '; cliff fit needs live verification'
        inventory['placement_analysis']['calibration_species'] = args.reference
        inventory['placement_analysis']['calibrated_species'] = sorted(set(records) - protected)
        inventory['placement_analysis']['calibration_report'] = str(args.output / 'report.txt')
        atomic_write(path, json.dumps(profiles, indent=2) + '\n')
        atomic_write(inventory_path, json.dumps(inventory, indent=2) + '\n')
    print(f"Calibrated {len(rock)} Rock Climb profiles; report: {args.output / 'report.txt'}")


if __name__ == '__main__':
    main()
