#!/usr/bin/env python3
"""Estimate missing Rock Climb placements from the owned field meshes and rigs."""
import argparse
import csv
import json
import math
from pathlib import Path

import UnityPy

from debug_mount import atomic_write
from model_geometry import inspect, tilt

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Save only missing profiles')
    parser.add_argument('--refresh-estimates', action='store_true',
                        help='Recalculate unchanged generated estimates; preserve later manual edits')
    parser.add_argument('--output', type=Path, default=Path('/tmp/hidden-moves-rock-climb-analysis'))
    parser.add_argument('--romfs', type=Path, default=PROJECT.parent / 'extracted/romfs')
    args = parser.parse_args()
    assets = args.romfs / 'Data/StreamingAssets/AssetAssistant'
    profiles_path = PROJECT / 'placements.json'
    inventory_path = PROJECT / 'rock-climb-candidates.json'
    profiles = json.loads(profiles_path.read_text())
    inventory = json.loads(inventory_path.read_text())
    species_table = 'rock_climb' if 'rock_climb' in profiles else 'species'
    model_table = 'rock_climb_models' if species_table == 'rock_climb' else 'models'
    saved = {int(k): v for k, v in profiles[species_table].items()}
    previous_estimates = {}
    if args.refresh_estimates:
        previous = json.loads((args.output / 'analysis.json').read_text())
        previous_estimates = {r['species']: r['placement'] for r in previous['records']
                              if r.get('source') == 'geometry estimate'
                              and saved.get(r['species']) == r['placement']}
        saved = {k: v for k, v in saved.items() if k not in previous_estimates}
    families = {i: {i} for i in range(1, 494)}
    for obj in UnityPy.load(str(assets / 'Pml/personal_masterdatas')).objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        table = obj.read_typetree()
        if table['m_Name'] != 'EvolveTable':
            continue
        for row in table['Evolve']:
            for start in range(0, len(row['ar']), 5):
                source, target = row['id'], row['ar'][start + 2]
                if source in families and target in families:
                    group = families[source] | families[target]
                    for member in group:
                        families[member] = group

    records = []
    for index, candidate in enumerate(inventory['candidates']):
        species = candidate['species']
        try:
            record = inspect(species, assets / 'Pokemon Database/pokemons')
        except Exception as error:
            record = {'species': species, 'error': str(error)}
        record['name'] = candidate['name']
        records.append(record)
        if index % 15 == 0:
            print(f"Inspected {index + 1}/{len(inventory['candidates'])}", flush=True)

    references = [r for r in records if 'error' not in r and r['species'] in saved]
    calibration_species = inventory.get('placement_analysis', {}).get('calibration_species', 74)
    reference_model = next(r for r in references if r['species'] == calibration_species)
    calibration = saved[calibration_species]
    contact = tilt(reference_model['seat'], calibration['rotation'][0])
    target_contact = [calibration['offset'][i] + calibration['scale'][0] * contact[i]
                      for i in range(3)]

    def skeleton(record):
        return {k for k in record['bone_positions']
                if not k.startswith(('pm', 'tr', 'Cus', 'Vri'))}

    def distance(record, reference):
        dimensions = sum(math.log(record['core_dimensions'][i] /
                                  reference['core_dimensions'][i]) ** 2 for i in range(3))
        anatomy = 8 if record['anatomy'] != reference['anatomy'] else 0
        posture = 4 if record['posture'] != reference['posture'] else 0
        angle = ((record['body_axis_degrees'] - reference['body_axis_degrees']) / 45) ** 2
        a, b = skeleton(record), skeleton(reference)
        topology = 5 * (1 - len(a & b) / max(1, len(a | b)))
        family = -100 if reference['species'] in families[record['species']] else 0
        return dimensions + anatomy + posture + angle + topology + family

    estimates = []
    for record in records:
        species = record['species']
        if 'error' in record:
            continue
        if species in saved:
            record.update(placement=saved[species], source='preserved existing profile')
            continue
        reference = min(references, key=lambda r: distance(record, r))
        profile = saved[reference['species']]
        pitch = record['suggested_pitch']
        if record['posture'] == reference['posture']:
            pitch = profile['rotation'][0]
        # Keep low bodies level, even if an evolutionary relative stands up.
        if record['posture'] == 'horizontal body' or record['anatomy'] == 'multi-legged':
            pitch = max(-10, min(10, pitch))
        else:
            pitch = max(-20, min(55, pitch))
        ratio = math.exp(sum(weight * math.log(reference['core_dimensions'][i] /
                                              record['core_dimensions'][i])
                             for i, weight in enumerate((0.4, 0.25, 0.35))))
        scale = max(0.15, min(3.5, profile['scale'][0] * ratio))
        notes = []
        # A head-only core on segmented rigs must not enlarge the whole snake.
        if max(record['dimensions']) * scale > 4.0:
            scale = 4.0 / max(record['dimensions'])
            notes.append('Scale limited by full silhouette to avoid oversized tails/limbs.')
        scale = round(scale, 2)
        seat = tilt(record['seat'], pitch)
        offset = [round(target_contact[i] - scale * seat[i], 2) for i in range(3)]
        placement = {'offset': offset, 'rotation': [pitch, 0.0, 0.0], 'scale': [scale] * 3}
        low_confidence = (record['core_source'] == 'whole mesh fallback'
                          or record['anatomy'] != reference['anatomy']
                          or max(record['dimensions']) / min(record['dimensions']) > 4
                          or record['anatomy'] == 'serpentine')
        notes.append('Prefab rest pose; idle animation and actual rider contact need a live check.')
        record.update(placement=placement, source='geometry estimate',
                      reference_species=reference['species'], reference=reference['name'],
                      confidence='low' if low_confidence else 'starting estimate', notes=notes)
        estimates.append(record)

    args.output.mkdir(parents=True, exist_ok=True)
    errors = [r for r in records if 'error' in r]
    result = {'source': inventory['source'], 'species_count': len(records),
              'estimated_count': len(estimates), 'preserved_count': len(saved),
              'calibration': {'species': calibration_species, 'placement': calibration,
                              'target_contact': target_contact, 'verified': False},
              'records': records}
    atomic_write(args.output / 'analysis.json', json.dumps(result, indent=2) + '\n')
    lines = ['Rock Climb initial model placements', '',
             f"{len(estimates)} new estimates; {len(references)} existing candidate profiles preserved.",
             f"Source: {inventory['source']}", '',
             'Method: resolve field skeletons, common meshes and inverse bind poses. Skin vertices',
             'into prefab coordinates; isolate vertices weighted to torso bones so tails, arms,',
             'flowers and horns do not dominate scale. Use torso direction and front/rear limb',
             'heights to distinguish horizontal bodies from upright bodies. Prefer evolutionary',
             'relatives, then similar skeletons/postures, for scale and pitch. Match a torso/back',
             'surface contact point to the current Geodude placement. Clamp long silhouettes.',
             'Only missing profiles are saved; all existing Surf placements are preserved.', '',
             'These are estimates. Geodude is still being tuned; its calibration is provisional.',
             'No new pose, animation, bobbing, or variant-specific fit is implied.', '',
             'New placements:']
    for r in estimates:
        p = r['placement']
        lines.append(f"{r['species']:03} {r['name']}: {r['posture']}; scale {p['scale'][0]}; "
                     f"offset {p['offset']}; pitch {p['rotation'][0]}; reference {r['reference']}; "
                     f"confidence {r['confidence']}")
    if errors:
        lines += ['', 'Errors:'] + [f"{r['species']:03} {r['name']}: {r['error']}" for r in errors]
    atomic_write(args.output / 'report.txt', '\n'.join(lines) + '\n')
    with (args.output / 'placements.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['species', 'name', 'model', 'posture', 'scale', 'x', 'y', 'z',
                         'pitch', 'reference', 'confidence'])
        for r in estimates:
            p = r['placement']
            writer.writerow([r['species'], r['name'], r['model'], r['posture'], p['scale'][0],
                             *p['offset'], p['rotation'][0], r['reference'], r['confidence']])
    if args.apply:
        if errors:
            raise SystemExit('Geometry errors: report saved; profiles were not changed.')
        for r in estimates:
            profiles[species_table][str(r['species'])] = r['placement']
            models = profiles.setdefault(model_table, {})
            if r['model'] not in models or models[r['model']] == previous_estimates.get(r['species']):
                models[r['model']] = r['placement']
        for candidate in inventory['candidates']:
            if candidate['species'] not in {r['species'] for r in estimates}:
                continue
            candidate['has_saved_placement'] = True
            candidate['placement_status'] = 'Rock Climb geometry estimate; needs live verification'
        inventory['placement_analysis'] = {'report': str(args.output / 'report.txt'),
                                            'estimated_species': [r['species'] for r in estimates],
                                            'calibration_species': calibration_species, 'runtime_verified': False}
        atomic_write(profiles_path, json.dumps(profiles, indent=2) + '\n')
        atomic_write(inventory_path, json.dumps(inventory, indent=2) + '\n')
    print(f"Estimated {len(estimates)} missing models; errors: {len(errors)}; report: {args.output / 'report.txt'}")


if __name__ == '__main__':
    main()
