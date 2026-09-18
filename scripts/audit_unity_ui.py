#!/usr/bin/env python3
"""Inventory RectTransforms in Unity UI asset bundles.

The report deliberately contains metadata only: bundle names, hierarchy paths,
anchors, pivots, positions, sizes, and scales. Asset payloads are not exported.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import re
from collections import Counter
from pathlib import Path

import UnityPy


BACKGROUND_RE = re.compile(
    r"(^|[_ /])(bg|back|background|mask|fade|gradation|wallpaper|base)([_ /]|$)",
    re.IGNORECASE,
)


def vector(value, *names: str) -> list[float]:
    return [float(getattr(value, name)) for name in names]


def near(a: float, b: float, tolerance: float = 0.01) -> bool:
    return abs(a - b) <= tolerance


def inspect_bundle(bundle: Path, root: Path) -> tuple[list[dict], Counter]:
    env = UnityPy.load(str(bundle))
    readers = {obj.path_id: obj for obj in env.objects}
    rects = {}
    game_object_names = {}
    errors = Counter()

    for obj in env.objects:
        if obj.type.name != "RectTransform":
            continue
        try:
            rects[obj.path_id] = obj.read()
        except Exception:
            errors["rect_read"] += 1

    def game_object_name(pointer) -> str:
        path_id = pointer.path_id
        if not path_id:
            return "<none>"
        if path_id in game_object_names:
            return game_object_names[path_id]
        try:
            name = pointer.read().m_Name
        except Exception:
            reader = readers.get(path_id)
            try:
                name = reader.read().m_Name if reader else f"<external:{path_id}>"
            except Exception:
                name = f"<unreadable:{path_id}>"
                errors["game_object_read"] += 1
        game_object_names[path_id] = name
        return name

    def hierarchy(rect) -> tuple[str, int]:
        names = [game_object_name(rect.m_GameObject)]
        parent = rect.m_Father
        seen = set()
        while parent.path_id and parent.path_id not in seen and len(names) < 128:
            seen.add(parent.path_id)
            try:
                parent_obj = parent.read()
            except Exception:
                errors["parent_read"] += 1
                names.append(f"<external:{parent.path_id}>")
                break
            names.append(game_object_name(parent_obj.m_GameObject))
            parent = parent_obj.m_Father
        names.reverse()
        return "/".join(names), len(names) - 1

    records = []
    for path_id, rect in rects.items():
        try:
            anchor_min = vector(rect.m_AnchorMin, "x", "y")
            anchor_max = vector(rect.m_AnchorMax, "x", "y")
            pivot = vector(rect.m_Pivot, "x", "y")
            position = vector(rect.m_AnchoredPosition, "x", "y")
            size = vector(rect.m_SizeDelta, "x", "y")
            scale = vector(rect.m_LocalScale, "x", "y", "z")
            object_path, depth = hierarchy(rect)
            name = object_path.rsplit("/", 1)[-1]

            fixed_anchor = anchor_min == anchor_max
            stretch_x = near(anchor_min[0], 0) and near(anchor_max[0], 1)
            stretch_y = near(anchor_min[1], 0) and near(anchor_max[1], 1)
            size_1280x720 = near(abs(size[0]), 1280) and near(abs(size[1]), 720)
            fixed_1280_width = near(abs(size[0]), 1280) and not stretch_x
            likely_background = bool(BACKGROUND_RE.search(name))
            suspect = (
                size_1280x720
                or fixed_1280_width
                or (likely_background and not (stretch_x and stretch_y))
                or (depth <= 2 and fixed_anchor and abs(size[0]) >= 1200)
            )

            records.append(
                {
                    "bundle": str(bundle.relative_to(root)),
                    "path_id": path_id,
                    "path": object_path,
                    "depth": depth,
                    "anchor_min_x": anchor_min[0],
                    "anchor_min_y": anchor_min[1],
                    "anchor_max_x": anchor_max[0],
                    "anchor_max_y": anchor_max[1],
                    "pivot_x": pivot[0],
                    "pivot_y": pivot[1],
                    "anchored_x": position[0],
                    "anchored_y": position[1],
                    "size_x": size[0],
                    "size_y": size[1],
                    "scale_x": scale[0],
                    "scale_y": scale[1],
                    "scale_z": scale[2],
                    "stretch_x": stretch_x,
                    "stretch_y": stretch_y,
                    "likely_background": likely_background,
                    "suspect_16_9": suspect,
                }
            )
        except Exception:
            errors["record_build"] += 1

    del env
    gc.collect()
    return records, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ui_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    root = args.ui_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    errors = Counter()
    bundles = sorted(path for path in root.rglob("*") if path.is_file())
    for index, bundle in enumerate(bundles, 1):
        try:
            found, bundle_errors = inspect_bundle(bundle, root)
            records.extend(found)
            errors.update(bundle_errors)
        except Exception:
            errors["bundle_load"] += 1
        if index % 100 == 0:
            print(f"scanned {index}/{len(bundles)} bundles; {len(records)} RectTransforms")

    fieldnames = list(records[0]) if records else []
    with (output / "rect_transforms.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    suspects = [record for record in records if record["suspect_16_9"]]
    summary = {
        "ui_root": str(root),
        "bundle_count": len(bundles),
        "rect_transform_count": len(records),
        "suspect_16_9_count": len(suspects),
        "fixed_1280x720_count": sum(
            near(abs(record["size_x"]), 1280) and near(abs(record["size_y"]), 720)
            for record in records
        ),
        "background_not_fully_stretched_count": sum(
            record["likely_background"]
            and not (record["stretch_x"] and record["stretch_y"])
            for record in records
        ),
        "errors": dict(errors),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "suspect_16_9.json").write_text(
        json.dumps(suspects, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
