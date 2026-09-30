#!/usr/bin/env python3
"""Read helper/model hierarchies without modifying the source Unity bundles."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import zlib
from pathlib import Path

import UnityPy


HELPERS = ("beadaru", "biidaru", "mukuhawk", "naminori", "sora_", "mcl_")


def inspect_bundle(path: Path) -> dict:
    env = UnityPy.load(str(path))
    records = {}
    for obj in env.objects:
        if obj.type.name in (
            "GameObject", "Transform", "SkinnedMeshRenderer", "AnimationClip"
        ):
            records[(id(obj.assets_file), obj.path_id)] = (
                obj.type.name, obj.read_typetree()
            )

    def resolve(file_id: int, ptr: dict) -> dict:
        # External references are reported as pointers rather than guessed.
        if ptr.get("m_FileID", 0) != 0:
            return {}
        return records.get((file_id, ptr.get("m_PathID", 0)), ("", {}))[1]

    def transform_path(file_id: int, path_id: int) -> str:
        parts = []
        seen = set()
        while path_id and path_id not in seen:
            seen.add(path_id)
            data = records.get((file_id, path_id), ("", {}))[1]
            go = resolve(file_id, data.get("m_GameObject", {}))
            parts.append(go.get("m_Name", f"<unresolved:{path_id}>"))
            parent = data.get("m_Father", {})
            if parent.get("m_FileID", 0) != 0:
                parts.append("<external-parent>")
                break
            path_id = parent.get("m_PathID", 0)
        return "/".join(reversed(parts))

    transforms = []
    go_paths = {}
    hashes = {}
    for (file_id, path_id), (kind, data) in records.items():
        if kind != "Transform":
            continue
        hierarchy = transform_path(file_id, path_id)
        go_paths[(file_id, data["m_GameObject"]["m_PathID"])] = hierarchy
        transforms.append({
            "path_id": path_id,
            "path": hierarchy,
            "local_position": data.get("m_LocalPosition"),
            "local_rotation": data.get("m_LocalRotation"),
            "local_scale": data.get("m_LocalScale"),
            "parent": data.get("m_Father"),
        })
        parts = hierarchy.split("/")
        for start in range(len(parts)):
            relative = "/".join(parts[start:])
            crc = zlib.crc32(relative.encode()) & 0xFFFFFFFF
            hashes.setdefault(crc, set()).add(relative)

    renderers = []
    clips = []
    for (file_id, path_id), (kind, data) in records.items():
        if kind == "SkinnedMeshRenderer":
            go_ptr = data.get("m_GameObject", {})
            go = resolve(file_id, go_ptr)
            renderers.append({
                "path_id": path_id,
                "name": go.get("m_Name"),
                "path": go_paths.get((file_id, go_ptr.get("m_PathID"))),
                "enabled": data.get("m_Enabled"),
                "mesh": data.get("m_Mesh"),
                "root_bone": data.get("m_RootBone"),
                "bone_paths": [
                    transform_path(file_id, ptr["m_PathID"])
                    if ptr.get("m_FileID", 0) == 0 else ptr
                    for ptr in data.get("m_Bones", [])
                ],
            })
        elif kind == "AnimationClip":
            bindings = []
            for binding in data.get("m_ClipBindingConstant", {}).get(
                "genericBindings", []
            ):
                entry = dict(binding)
                entry["possible_paths"] = sorted(hashes.get(binding.get("path"), []))
                bindings.append(entry)
            curves = {
                key: sorted({curve.get("path", "") for curve in data.get(key, [])})
                for key in (
                    "m_RotationCurves", "m_EulerCurves", "m_PositionCurves",
                    "m_ScaleCurves", "m_FloatCurves", "m_PPtrCurves"
                )
            }
            clips.append({
                "name": data.get("m_Name"),
                "bindings": bindings,
                "curve_paths": curves,
            })

    def helper_path(value: str) -> bool:
        return any(token in value.lower() for token in HELPERS)

    return {
        "bundle": str(path.resolve()),
        "transforms": sorted(transforms, key=lambda item: item["path"]),
        "helper_transforms": [item for item in transforms if helper_path(item["path"])],
        "renderers": renderers,
        "animations": clips,
        "notes": [
            "Animation hashes may match multiple relative paths; matches are candidates.",
            "External references and native transform updates require separate inspection.",
            "This report does not establish that helper bones are static at runtime.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--romfs", type=Path, default=Path("../extracted/romfs"))
    parser.add_argument("--player", default="fc0001_00")
    parser.add_argument("--pokemon", default="pm0130_00_00")
    args = parser.parse_args()
    if not re.fullmatch(r"fc\d{4}_\d{2}", args.player):
        parser.error("--player must be a prefab name such as fc0001_00")
    if not re.fullmatch(r"pm\d{4}_\d{2}_\d{2}", args.pokemon):
        parser.error("--pokemon must be a model name such as pm0131_00_00")
    root = args.romfs / "Data/StreamingAssets/AssetAssistant"
    paths = {
        "player": root / "Characters/persons/field" / args.player,
        "pokemon": root / "Pokemon Database/pokemons/field" / args.pokemon,
    }
    for label, path in paths.items():
        if not path.is_file():
            parser.error(f"Missing {label} bundle: {path}")
    report = {label: inspect_bundle(path) for label, path in paths.items()}
    output = Path(tempfile.mkdtemp(prefix="pokemon-bd-hidden-moves-inspect-"))
    target = output / "mount-models.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(target)
    for label, data in report.items():
        print(f"{label}: {len(data['transforms'])} transforms, "
              f"{len(data['renderers'])} renderers, {len(data['animations'])} clips")


if __name__ == "__main__":
    main()
