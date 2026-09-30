#!/usr/bin/env python3
"""Build a LayeredFS UI bundle patch for Brilliant Diamond v1.3.0.

Source bundles are never modified. The generated patch adjusts selected UI
transforms, cameras, and animation curves while preserving the original
1280x720 behavior inside a wider canvas.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
from collections import defaultdict
from pathlib import Path

import UnityPy


REFERENCE_WIDTH = 1280.0
REFERENCE_HEIGHT = 720.0
HALF_REFERENCE_WIDTH = REFERENCE_WIDTH / 2.0
ULTRAWIDE_WIDTH = 1720.0
ULTRAWIDE_X_SCALE = ULTRAWIDE_WIDTH / REFERENCE_WIDTH
# The top/under encounter textures contain about 16.2% horizontal visual
# padding. A pure aspect-ratio scale leaves their visible streaks and rock
# silhouettes inset by roughly 166 display pixels on each side at 21:9.
ENCOUNTER_BAND_WIDTH = 5.775
ENCOUNTER_BAND_NAMES = {"top_high", "top_low", "under_high", "under_low"}

# In list mode the 3D capsule is composed for the left quarter of a 1280-wide
# orthographic viewport. Widening the RawImage moves that composition 220 UI
# units right of its still-16:9 pedestal. At an orthographic size of 0.75,
# 220/720 of the screen height is 0.458333 world units.
CAPSULE_LIST_CAMERA_ROOT_X = -0.6 + (220.0 / REFERENCE_HEIGHT * 1.5)

# The display is 640x480, but its bezel is 940x962. Fit the entire expanded
# watch within the 720-unit canvas. Its bezel extends 4 units right and 12
# units above the root pivot; compensate at each scale to meet both edges.
POKETCH_LARGE_SCALE = 0.7
POKETCH_SMALL_SCALE = 0.4
# The reduced bezel can expose a thin filtered edge at fractional pixels.
# Let it overlap the top/right edges by four UI units in collapsed mode;
# two units still leave a 1–2 pixel seam in the game's filtered output.
POKETCH_SMALL_EDGE_OVERLAP = 4.0


def poketch_position(scale: float) -> tuple[float, float]:
    overlap = POKETCH_SMALL_EDGE_OVERLAP if abs(scale - POKETCH_SMALL_SCALE) < 0.01 else 0.0
    return -4.0 * scale + overlap, -12.0 * scale + overlap

BACKGROUND_NAMES = re.compile(
    r"^(BG|BGBorder|Image_BG|WhiteFade|DarkScreen|FadeImage|Frash[1-7])$",
    re.IGNORECASE,
)

# Screens whose coordinate systems are actively managed by game code or by
# the ExeFS patch. Widening only their serialized roots desynchronizes visuals,
# navigation, masks, and hit tests, so leave the entire prefab untouched.
SKIP_AUTO_PREFIXES = (
    "ContCapsuleSelect/Window",
    # ContextMenuWindow.Param positions are calculated at runtime in the
    # authored 1280x720 coordinate space. Widening either Window changes the
    # anchor frame beneath those calculated positions, which can move choices
    # off-screen (including field yes/no prompts and party action menus).
    "ContextMenu/Window",
    "ContextMenu_Scroll/Window",
    "Map/Window",
    "MapWall/Window",
)

# Fixed 1280x720 layers which must follow an already-widened parent. These are
# deliberately explicit: treating every reference-sized child as a backdrop
# also catches input and animation coordinate spaces.
STRETCH_PATHS = {
    # Model/background render output behind the party screen.
    "Pokemon/Window/BG/RawImageModel",
    # Trainer-card scene output and its backing layers.
    "Card/Window/ModelViewRawImage",
    "Card/Window/Sub_BG",
    "Card/Window/Sub_BG/Image_BG",
    "Card/Window/Card/Image_BG",
    # Widen both the map viewport and its RectMask2D.  The map art itself
    # remains at its authored 1472x720 size, avoiding horizontal distortion.
    "Map/Window",
    "Map/Window/Map",
    "MapWall/Window",
    "MapWall/Window/Map",
    # Habitat has its own viewport and mask, separate from the town map.
    "ZukanHabitat/Window/Map",
    "ZukanHabitat/Window/Map/Body",
}

# Local scales needed inside off-screen render scenes.  These transforms are
# not screen layout roots, so stretching their anchors would be incorrect.
LOCAL_SCALE_POLICIES = {
    "Poketch/Window/Poketch": (POKETCH_SMALL_SCALE, POKETCH_SMALL_SCALE),
    # Compensate for the 2x trainer-card RenderTexture supersampling hook.
    "CardModelView/ModelRoot/BadgeCase/Canvas/BgRoot": (2.0, 2.0),
    # Fill the full 720-unit height from the panel's bottom-left pivot.
    "Map/Window/FacilityInfo": (720.0 / 630.0, 720.0 / 630.0),
    "MapWall/Window/FacilityInfo": (720.0 / 630.0, 720.0 / 630.0),
}

# Nested canvases with RectMask2D do not reliably refresh a stretch-anchored
# rect after the top-level window is widened. Give those clipping frames an
# explicit ultrawide size so their children cannot be cut off at 1280 units.
FIXED_RECT_SIZE_OVERRIDES = {
    "Seal/Window/BGRoot": (ULTRAWIDE_WIDTH, REFERENCE_HEIGHT),
    "Seal/Window/BGRoot/BG/Image": (ULTRAWIDE_WIDTH, REFERENCE_HEIGHT),
}

# Non-UI scene anchors which host runtime-instantiated models.
LOCAL_POSITION_X_OVERRIDES = {
    # The player model is parented here after loading. Move only that model;
    # changing the shared camera also displaces the badge case and card scene.
    "CardModelView/ModelRoot/BadgeCase/Character": -1.1,
}

PIVOT_POLICIES = {
    # The 2x card canvas must grow around the RenderTexture center, not the
    # authored top-left pivot.
    "CardModelView/ModelRoot/BadgeCase/Canvas/BgRoot": (0.5, 0.5),
}

ANCHORED_POSITION_OVERRIDES = {
    "Poketch/Window/Poketch": poketch_position(POKETCH_SMALL_SCALE),
}

# Move all trainer-intro artwork together inside the runtime-animated plate.
# Keep the plate's authored rect and tween endpoints: shifting its two visual
# children moves the complete arrow and all balls without resizing the line.
BATTLE_INTRO_BALL_X_OFFSETS = {
    "BattleViewUISystem/BallPlate/BUIBallPlate_Near/Image_Arrow": 220.0,
    "BattleViewUISystem/BallPlate/BUIBallPlate_Near/BallIcons": 220.0,
    "BattleViewUISystem/BallPlate/BUIBallPlate_Far/Image_Arrow": -220.0,
    "BattleViewUISystem/BallPlate/BUIBallPlate_Far/BallIcons": -220.0,
}

ANCHORED_POSITION_X_OFFSETS = {
    **BATTLE_INTRO_BALL_X_OFFSETS,
    # Center the unknown-habitat banner in the space beside the left panel.
    "ZukanHabitat/Window/Map/Body/HabitatMap/NotFound": -6.0,
    # This top-right-pivoted window is positioned by its entrance/exit clips.
    # Preserve that fixed coordinate frame and move its pivot to the new
    # canvas right edge; stretching it makes the clips push it off-screen.
    "Poketch/Window": (ULTRAWIDE_WIDTH - REFERENCE_WIDTH) / 2.0,
    # This widened image is centered by a nested 1280-wide canvas. Shift it by
    # half the added canvas width so it covers physical X=0..1720 instead of
    # extending from X=-220..1500.
    "Seal/Window/BGRoot/BG/Image": 220.0,
    # Keep the complete Pokédex preview and footprint with their widened
    # left/right page groups.
    "Zukan/Window/ZukanDescriptionPanel/ModelViewParent": 220.0,
    "ZukanRegister/Window/ZukanDescriptionPanel/ModelViewParent": 220.0,
    "Zukan/Window/ZukanDescriptionPanel/FootPrint": 220.0,
    "ZukanRegister/Window/ZukanDescriptionPanel/FootPrint": 220.0,
    # Match the final positions written by the corrected map animations.
    "Map/Window/FacilityInfo": -220.0,
    "MapWall/Window/FacilityInfo": -220.0,
    # Grow the ocean backing leftward without moving interactive map content.
    "Map/Window/Map/Object_Map/Body/Image_Base": -109.0,
    # This icon is left-anchored while its containing Bag panel is aligned to
    # the widened right edge. Follow the full 1720-1280 canvas expansion.
    "Bag/Window/BagItemPanel/BagIconImage": 440.0,
    # Keep the battle party details panel's 16:9 placement relative to the
    # physical right edge.  Its BattlePokemon animation curves receive the
    # same offset below so transitions cannot restore the centered position.
    "PokemonBattle/Window/StatusWindow": 220.0,
}

# Unity animation binding paths use CRC32. These elements are animated back to
# their authored positions on every transition, so every curve representation
# must be offset along with its serialized rest pose.
ANIMATION_X_OFFSETS_BY_PATH_HASH = {
    # (offset, clip-name prefixes). The hashes are reused by unrelated clips,
    # so the resident bundle, component type, and clip names are constrained.
    1210394069: (-220.0, ("Map__", "MapWall__")),  # FacilityInfo
    159791602: (440.0, ("Bag__",)),  # BagItemPanel/BagIconImage
    3910900351: (220.0, ("BattlePokemon__",)),  # StatusWindow
}

SIZE_X_OVERRIDES = {
    "Poketch/Window": ULTRAWIDE_WIDTH,
    # The description's brown panel grows with the status-page background.
    # Expand its striped paper and sliced frame together around the existing
    # preview center. Leave a narrow brown border and the square model output
    # at its original size, so the Pokemon itself is not stretched.
    **{
        f"{window}/Window/ZukanDescriptionPanel/ModelViewParent/ModelView{child}": 990.0
        for window in ("Zukan", "ZukanRegister")
        for child in ("", "/Offset", "/Offset/BG")
    },
    # Extend only the ocean backing; keep map tiles and habitat coordinates
    # at their authored scale inside the wider clipping frame.
    "ZukanHabitat/Window/Map/Body/HabitatMap/Body/Image_Base": 1940.0,
    "ZukanHabitat/Window/Map/Body/HabitatMap/NotFound": ULTRAWIDE_WIDTH - 396.0,
    # Battle code animates these parents to anchored X=0 at runtime. Keep
    # their centered anchors and widen the coordinate frames so right-anchored
    # command controls land on the physical screen edge.
    "BattleViewUISystem/BUIActionList": ULTRAWIDE_WIDTH,
    "BattleViewUISystem/BUIWazaList": ULTRAWIDE_WIDTH,
    # The Pokédex details body is a centered 1280-wide coordinate group.  Its
    # right-anchored fields otherwise lag 220 units behind the widened header.
    "Zukan/Window/ZukanDescriptionPanel/FixedObjects/StatusPanel": 1720.0,
    "ZukanRegister/Window/ZukanDescriptionPanel/FixedObjects/StatusPanel": 1720.0,
    # Preserve each plate's corrected right edge while restoring its decorated
    # left border to the physical screen edge.
    "Pokemon/Window/BG/Image_plate": 752.0,
    "Bag/Window/Image_PartyPlate": 708.0,
    "PokemonBattle/Window/BG/Image_plate": 701.0,
    # Its original right edge is already at X=1718 on the ultrawide canvas.
    "Map/Window/Map/Object_Map/Body/Image_Base": 1718.0,
}

CAMERA_LENS_SHIFT_X = {}

# The Pokédex header art stretches with the ultrawide window.  Its centered
# labels must follow the same horizontal ratio to stay on the printed pills.
POSITION_X_MULTIPLIERS = {
    "Zukan/Window/Header/Image_Title": 1720.0 / REFERENCE_WIDTH,
    "Zukan/Window/Header/GetPokeCountText": 1720.0 / REFERENCE_WIDTH,
    "Zukan/Window/Header/FoundPokeCountText": 1720.0 / REFERENCE_WIDTH,
    "Zukan/Window/Header/SortNameText": 1720.0 / REFERENCE_WIDTH,
}

# resources.assets contains the global UI manager rather than a window bundle.
# This RawImage is the captured/blurred field scene shown behind the X menu.
RESOURCE_STRETCH_PATHS = {
    "UIManager/BlurBg/Canvas/Bg",
}

# These are center-anchored in the original prefabs but semantically form the
# left or right side of a full-screen layout. Re-anchoring preserves their
# exact 16:9 position and moves them with the corresponding edge in ultrawide.
EDGE_POLICIES = {
    # Standalone prefab windows.
    "ContPokeSelect/Window/TransModel": "right",
    "ContWazaSelect/Window/PokeStatusSelectPanel": "right",
    "FureaiPokeSelect/Window/PokeTransform": "right",
    "ShopUg/Window/SubWindow": "left",
    # Resident windows.
    "Zukan/Window/InfoButtonPosition": "right",
    "FieldTvRanking/Window/Right": "right",
    "FieldTvRanking/Window/Left": "left",
    "Kinomi/Window/RaderChart": "right",
    "Kinomi/Window/Img": "left",
    "PokeStatus/Window/TransModel": "right",
    "PokeStatus/Window/PokeStatusSelectPanel": "right",
    "Training/Window/TrainingSelect": "right",
    "PokemonSelect/Window/MessageWindowRoot": "right",
    "PokemonSelect/Window/GoToBox": "right",
    "Report/Window/MainWindow": "left",
    "SealTemplate/Window/SealList": "right",
    # The capsule pedestal and its orange direction markers remain authored
    # in the original left-side frame. Keep the 2D capsule preview over that
    # assembly instead of letting its center anchor move 220 units right when
    # the window widens.
    "Seal/Window/Scene_CupsuleList/Capsule/2D": "left",
    "ShopFlower/Window/SubWindow": "left",
    "LevelUp/Window/StatusPanel": "right",
    "RotomSelect/Window/MessageWindowRoot": "right",
    "RotomSelect/Window/GoToBox": "right",
    "Pokemon/Window/MessageWindowRoot": "right",
    "Pokemon/Window/GoToBox": "right",
    # The map overlay panels belong to screen edges; the map art stays fixed.
    "Map/Window/Navi": "left",
    "Map/Window/Info": "right",
    "MapWall/Window/Navi": "left",
    "MapWall/Window/Info": "right",
}


def near(a: float, b: float, tolerance: float = 0.01) -> bool:
    return abs(a - b) <= tolerance


def is_reference_frame(rect) -> bool:
    return near(abs(float(rect.m_SizeDelta.x)), REFERENCE_WIDTH) and near(
        abs(float(rect.m_SizeDelta.y)), REFERENCE_HEIGHT
    )


def build_hierarchy(rect) -> tuple[str, int]:
    names = [rect.m_GameObject.read().m_Name]
    parent = rect.m_Father
    seen = set()
    while parent.path_id and parent.path_id not in seen and len(names) < 128:
        seen.add(parent.path_id)
        try:
            parent_rect = parent.read()
            names.append(parent_rect.m_GameObject.read().m_Name)
            parent = parent_rect.m_Father
        except Exception:
            break
    names.reverse()
    return "/".join(names), len(names) - 1


def stretch(rect) -> None:
    rect.m_AnchorMin.x = 0.0
    rect.m_AnchorMin.y = 0.0
    rect.m_AnchorMax.x = 1.0
    rect.m_AnchorMax.y = 1.0
    rect.m_AnchoredPosition.x = 0.0
    rect.m_AnchoredPosition.y = 0.0
    rect.m_SizeDelta.x = 0.0
    rect.m_SizeDelta.y = 0.0


def anchor_to_edge(rect, side: str) -> None:
    if side == "left":
        rect.m_AnchorMin.x = 0.0
        rect.m_AnchorMax.x = 0.0
        rect.m_AnchoredPosition.x += HALF_REFERENCE_WIDTH
    elif side == "right":
        rect.m_AnchorMin.x = 1.0
        rect.m_AnchorMax.x = 1.0
        rect.m_AnchoredPosition.x -= HALF_REFERENCE_WIDTH
    else:
        raise ValueError(f"Unknown edge policy: {side}")


def set_fixed_centered_size(rect, width: float, height: float) -> None:
    rect.m_AnchorMin.x = 0.5
    rect.m_AnchorMin.y = 0.5
    rect.m_AnchorMax.x = 0.5
    rect.m_AnchorMax.y = 0.5
    rect.m_AnchoredPosition.x = 0.0
    rect.m_AnchoredPosition.y = 0.0
    rect.m_SizeDelta.x = width
    rect.m_SizeDelta.y = height


def uint32_to_float(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value))[0]


def float_to_uint32(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def offset_animation_curve(clip, curve_index: int, offset: float) -> None:
    """Offset one scalar curve in all Unity 2019 storage representations."""
    muscle_clip = clip.m_MuscleClip
    muscle_clip.m_ValueArrayDelta[curve_index].m_Start += offset
    muscle_clip.m_ValueArrayDelta[curve_index].m_Stop += offset

    clip_data = muscle_clip.m_Clip.data
    streamed = clip_data.m_StreamedClip
    cursor = 0
    while cursor < len(streamed.data):
        key_count = streamed.data[cursor + 1]
        cursor += 2
        for _ in range(key_count):
            index = streamed.data[cursor]
            if index == curve_index:
                value_index = cursor + 4
                value = uint32_to_float(streamed.data[value_index])
                streamed.data[value_index] = float_to_uint32(value + offset)
            cursor += 5

    dense = clip_data.m_DenseClip
    dense_index = curve_index - streamed.curveCount
    if 0 <= dense_index < dense.m_CurveCount:
        for frame in range(dense.m_FrameCount):
            sample_index = frame * dense.m_CurveCount + dense_index
            dense.m_SampleArray[sample_index] += offset

    constant_index = curve_index - streamed.curveCount - dense.m_CurveCount
    constant = clip_data.m_ConstantClip.data
    if 0 <= constant_index < len(constant):
        constant[constant_index] += offset


def is_skipped(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in SKIP_AUTO_PREFIXES)


def patch_bundle(source: Path, destination: Path) -> list[dict]:
    env = UnityPy.load(str(source))
    changes = []

    for obj in env.objects:
        if obj.type.name != "RectTransform":
            continue
        rect = obj.read()
        path, depth = build_hierarchy(rect)
        name = path.rsplit("/", 1)[-1]
        action = None

        # Full-screen prefab/window roots. Their children can then respond to
        # left/right/stretch anchors against the actual canvas width.
        if path in STRETCH_PATHS:
            action = "stretch_explicit"
            stretch(rect)
        elif path in FIXED_RECT_SIZE_OVERRIDES:
            width, height = FIXED_RECT_SIZE_OVERRIDES[path]
            set_fixed_centered_size(rect, width, height)
            action = f"fixed_centered_size_{width:g}x{height:g}"
            if path in ANCHORED_POSITION_X_OFFSETS:
                offset = ANCHORED_POSITION_X_OFFSETS[path]
                rect.m_AnchoredPosition.x += offset
                action += f"_position_x_plus_{offset:g}"
        elif path in LOCAL_SCALE_POLICIES:
            sx, sy = LOCAL_SCALE_POLICIES[path]
            rect.m_LocalScale.x = sx
            rect.m_LocalScale.y = sy
            if path in PIVOT_POLICIES:
                rect.m_Pivot.x, rect.m_Pivot.y = PIVOT_POLICIES[path]
            if path in ANCHORED_POSITION_OVERRIDES:
                rect.m_AnchoredPosition.x, rect.m_AnchoredPosition.y = (
                    ANCHORED_POSITION_OVERRIDES[path]
                )
            if path in ANCHORED_POSITION_X_OFFSETS:
                rect.m_AnchoredPosition.x += ANCHORED_POSITION_X_OFFSETS[path]
            action = f"local_scale_{sx:g}x{sy:g}"
        elif path in SIZE_X_OVERRIDES:
            rect.m_SizeDelta.x = SIZE_X_OVERRIDES[path]
            action = f"size_x_{SIZE_X_OVERRIDES[path]:g}"
            if path in ANCHORED_POSITION_X_OFFSETS:
                offset = ANCHORED_POSITION_X_OFFSETS[path]
                rect.m_AnchoredPosition.x += offset
                action += f"_position_x_plus_{offset:g}"
        elif path in ANCHORED_POSITION_X_OFFSETS:
            offset = ANCHORED_POSITION_X_OFFSETS[path]
            rect.m_AnchoredPosition.x += offset
            if path in BATTLE_INTRO_BALL_X_OFFSETS:
                # Keep the serialized transform position consistent with the
                # rect position before battle startup caches local transforms.
                rect.m_LocalPosition.x += offset
            action = f"position_x_plus_{offset:g}"
        elif path in POSITION_X_MULTIPLIERS:
            multiplier = POSITION_X_MULTIPLIERS[path]
            rect.m_AnchoredPosition.x *= multiplier
            action = f"position_x_times_{multiplier:g}"
        elif path in EDGE_POLICIES:
            action = f"anchor_{EDGE_POLICIES[path]}"
            anchor_to_edge(rect, EDGE_POLICIES[path])
        elif is_skipped(path):
            continue
        elif is_reference_frame(rect) and (depth == 0 or path.endswith("/Window")):
            action = "stretch_root"
            stretch(rect)
        # Fixed full-screen visual layers nested below a window.
        elif is_reference_frame(rect) and BACKGROUND_NAMES.match(name):
            action = "stretch_background"
            stretch(rect)

        if action:
            rect.save()
            changes.append(
                {
                    "bundle": str(source),
                    "path": path,
                    "path_id": obj.path_id,
                    "action": action,
                }
            )

    # Runtime-loaded scene models inherit these non-UI anchor transforms.
    for obj in env.objects:
        if obj.type.name != "Transform":
            continue
        transform = obj.read()
        path, _ = build_hierarchy(transform)
        if path not in LOCAL_POSITION_X_OVERRIDES:
            continue
        transform.m_LocalPosition.x = LOCAL_POSITION_X_OVERRIDES[path]
        transform.save()
        changes.append(
            {
                "bundle": str(source),
                "path": path,
                "path_id": obj.path_id,
                "action": f"local_position_x_{LOCAL_POSITION_X_OVERRIDES[path]:g}",
            }
        )

    # Camera-space content cannot be corrected with RectTransforms.  Keep this
    # narrowly path-scoped so unrelated model-view cameras are untouched.
    for obj in env.objects:
        if obj.type.name != "Camera":
            continue
        camera = obj.read()
        game_object = camera.m_GameObject.read()
        transform = None
        for component_pair in game_object.m_Component:
            component = component_pair.component.read()
            if type(component).__name__ in ("Transform", "RectTransform"):
                transform = component
                break
        if transform is None:
            continue
        path, _ = build_hierarchy(transform)
        if path not in CAMERA_LENS_SHIFT_X:
            continue
        camera.m_LensShift.x = CAMERA_LENS_SHIFT_X[path]
        camera.save()
        changes.append(
            {
                "bundle": str(source),
                "path": path,
                "path_id": obj.path_id,
                "action": f"camera_lens_shift_x_{CAMERA_LENS_SHIFT_X[path]:g}",
            }
        )

    # CapsuleViewController instantiates this prefab and reapplies its list
    # camera defaults at runtime, after all UI RectTransforms are loaded.
    # Patch that winning value so the 3D capsule remains over the authored
    # pedestal and orange direction markers on an ultrawide viewport.
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        component = obj.read()
        try:
            game_object = component.m_GameObject.read()
        except Exception:
            continue
        if game_object.m_Name == "Poketch" and hasattr(component, "_largeScale"):
            component._smallScale = POKETCH_SMALL_SCALE
            component._largeScale = POKETCH_LARGE_SCALE
            for position, scale in (
                (component._smallPos, component._smallScale),
                (component._largePos, component._largeScale),
            ):
                position.x, position.y = poketch_position(scale)
            component.save()
            changes.append(
                {
                    "bundle": str(source),
                    "path": "Poketch/resizeDefaults",
                    "path_id": obj.path_id,
                    "action": "large_scale_0.7_align_bezel_top_right",
                }
            )
            continue
        if game_object.m_Name != "Capsule3DView" or not hasattr(
            component, "listModeDefault"
        ):
            continue
        component.listModeDefault.modelCameraRootPosition.x = (
            CAPSULE_LIST_CAMERA_ROOT_X
        )
        component.save()
        changes.append(
            {
                "bundle": str(source),
                "path": "Capsule3DView/listModeDefault/modelCameraRootPosition",
                "path_id": obj.path_id,
                "action": f"position_x_{CAPSULE_LIST_CAMERA_ROOT_X:g}",
            }
        )

    for obj in env.objects:
        if obj.type.name != "AnimationClip":
            continue
        # These corrections belong only to the resident Pokémon and Bag
        # windows. Other bundles contain clips with the same binding hashes.
        if source.name != "uiresidentwindow":
            continue
        clip = obj.read()
        binding_constant = clip.m_ClipBindingConstant
        if binding_constant is None:
            continue
        bindings = binding_constant.genericBindings
        values = clip.m_MuscleClip.m_ValueArrayDelta
        if clip.m_Name.startswith("Poketch__"):
            # Transform scale bindings occupy three scalar curves, unlike
            # RectTransform property bindings. Account for them before finding
            # the Window's anchored X curve in these packed clips.
            widths = [
                3 if binding.typeID == 4 and binding.attribute == 3 else 1
                for binding in bindings
            ]
            if sum(widths) != len(values):
                raise ValueError(
                    f"Unsupported Poketch animation layout in {clip.m_Name}"
                )
            curve_index = 0
            for binding, width in zip(bindings, widths):
                if (
                    binding.path == 0
                    and binding.typeID == 224
                    and binding.attribute == 1460864421  # m_AnchoredPosition.x
                ):
                    offset = ANCHORED_POSITION_X_OFFSETS["Poketch/Window"]
                    offset_animation_curve(clip, curve_index, offset)
                    changes.append(
                        {
                            "bundle": str(source),
                            "path": f"AnimationClip/{clip.m_Name}",
                            "path_id": obj.path_id,
                            "action": f"window_position_x_plus_{offset:g}",
                        }
                    )
                curve_index += width
            clip.save()
            continue
        target_indices = [
            index
            for index, binding in enumerate(bindings)
            if binding.path in ANIMATION_X_OFFSETS_BY_PATH_HASH
            and binding.typeID == 224
            and clip.m_Name.startswith(
                ANIMATION_X_OFFSETS_BY_PATH_HASH[binding.path][1]
            )
        ]
        if not target_indices:
            continue
        if len(bindings) != len(values):
            raise ValueError(
                f"Unsupported packed animation layout in {clip.m_Name}: "
                f"{len(bindings)} bindings, {len(values)} values"
            )
        for index in target_indices:
            offset = ANIMATION_X_OFFSETS_BY_PATH_HASH[bindings[index].path][0]
            offset_animation_curve(clip, index, offset)
            changes.append(
                {
                    "bundle": str(source),
                    "path": f"AnimationClip/{clip.m_Name}",
                    "path_id": obj.path_id,
                    "action": (
                        f"curve_{bindings[index].path}_x_plus_{offset:g}"
                    ),
                }
            )
        clip.save()

    if changes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Preserve each bundle's original compression flags. This keeps the
        # LayeredFS payload close to retail size and avoids needless I/O.
        destination.write_bytes(env.file.save(packer="original"))
    return changes


def patch_resources(source: Path, destination: Path) -> list[dict]:
    env = UnityPy.load(str(source))
    changes = []
    for obj in env.objects:
        if obj.type.name != "RectTransform":
            continue
        rect = obj.read()
        path, _ = build_hierarchy(rect)
        if path not in RESOURCE_STRETCH_PATHS:
            continue
        stretch(rect)
        rect.save()
        changes.append(
            {
                "bundle": str(source),
                "path": path,
                "path_id": obj.path_id,
                "action": "stretch_global_blur",
            }
        )
    if changes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(env.file.save(packer="original"))
    return changes


def patch_encounter_effect(source: Path, destination: Path) -> list[dict]:
    """Widen fixed-width encounter and Hidden Move screen layers.

    Field transitions and battle setup effects use size3D billboards exactly
    3.6 units wide for full-screen color bands, fades, flashes, and overlays.
    Some ``back`` layers have the same effective width through a parent scale
    instead. Widen those screen layers only; smaller streaks, characters,
    debris, and ordinary effects retain their authored proportions.
    """
    env = UnityPy.load(str(source))
    changes = []
    for obj in env.objects:
        if obj.type.name != "ParticleSystem":
            continue
        particle = obj.read()
        initial = particle.InitialModule
        if not initial.size3D:
            continue
        name = particle.m_GameObject.read().m_Name
        old_size_x = float(initial.startSize.scalar)
        if name != "back" and not near(old_size_x, 3.6):
            continue
        if name in ENCOUNTER_BAND_NAMES and near(old_size_x, 3.6):
            initial.startSize.scalar = ENCOUNTER_BAND_WIDTH
            action = f"start_size_x_{ENCOUNTER_BAND_WIDTH:g}"
        else:
            initial.startSize.scalar = old_size_x * ULTRAWIDE_X_SCALE
            action = f"start_size_x_times_{ULTRAWIDE_X_SCALE:g}"
        particle.save()
        changes.append(
            {
                "bundle": str(source),
                "path": f"ParticleSystem/{name}",
                "path_id": obj.path_id,
                "action": action,
            }
        )

    if changes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(env.file.save(packer="original"))
    return changes


def write_exefs_patch(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    marker = "@stop"
    if marker not in text:
        raise ValueError(f"Missing {marker} in {source}")
    old_model_bg = "0137E5B8 0010201E // background root X = 2"
    new_model_bg = "0137E5B8 00D0201E // background root X = 2.75 (ultrawide coverage)"
    if old_model_bg not in text:
        raise ValueError("Missing expected Pokémon model-background scale patch")
    text = text.replace(old_model_bg, new_model_bg, 1)
    # The Motion/Cry background already follows the widened model viewport.
    # SetupKeyguide can run repeatedly, so adding 220 to its local X there
    # both displaces the rendered backdrop and accumulates on later calls.
    moving_bg_hook = "01BBCF0C 8905DF97 // Chorus/Filter background centering helper"
    if moving_bg_hook not in text:
        raise ValueError("Missing expected Motion/Cry background hook")
    text = text.replace(
        moving_bg_hook,
        "01BBCF0C F40300AA // original mov x20,x0; keep Motion/Cry background centered",
        1,
    )
    # Cursor control is active only in expanded mode. Its bounds and button
    # reach are in physical pixels: authored units * 2x CanvasScaler * scale.
    # The upstream patch assumes scale=1, leaving a much larger clamp box
    # than the visible display after shrinking the complete watch to fit.
    def mov_float_w8(value: float) -> str:
        bits = float_to_uint32(value)
        if bits & 0xFFFF:
            raise ValueError(f"Poketch bound needs a two-instruction float: {value}")
        return struct.pack("<I", 0x52A00008 | ((bits >> 16) << 5)).hex().upper()

    replacements = (
        ("01E698B0 1F2003D5", f"01E698B0 {mov_float_w8(640 * POKETCH_LARGE_SCALE)}"),
        ("01E698C8 1F2003D5", f"01E698C8 {mov_float_w8(480 * POKETCH_LARGE_SCALE)}"),
        ("01E68A98 4880A852", f"01E68A98 {mov_float_w8(520 * POKETCH_LARGE_SCALE)}"),
        ("01E68AC0 8871A852", f"01E68AC0 {mov_float_w8(280 * POKETCH_LARGE_SCALE)}"),
    )
    for old, new in replacements:
        if old not in text:
            raise ValueError(f"Missing expected Poketch patch: {old}")
        text = re.sub(re.escape(old) + r"[^\n]*", new + " // resized Poketch screen-space extent", text, count=1)
    additions = """// Full-width encounter band coverage
// Double the RawImage rect dimensions before creating its RenderTexture.
01A30B38 1637E597 // BL 0x0137E790
0137E790 0829281E // fadd s8,s8,s8
0137E794 2929291E // fadd s9,s9,s9
0137E798 0101381E // displaced fcvtzs w1,s8
0137E79C C0035FD6 // ret
// BattlePostProcessFilter creates the DOF/composite texture used during
// trainer and Pokemon entrance sequences. These RenderTextures use physical
// pixels rather than the 1720-unit UI canvas, so request the mod's full 3440
// output width while retaining the runtime-provided 1440 height.
01E4917C 01AE8152 // mov w1,#3440
// BattleMultipleCameraCompositor creates the color, depth, and copied-depth
// inputs consumed by the post-process filter. Widen all three source targets
// to the same physical width. Using the logical width here would stretch a
// half-resolution 3D scene across the physical output.
01F7C5AC 01AE8152 // color target: mov w1,#3440
01F7C60C 01AE8152 // depth target: mov w1,#3440
01F7C670 01AE8152 // copied depth target: mov w1,#3440
// Poketch touch input: Switch touch coordinates remain 1280x720 even when
// the render output is 3440x1440. Scale the GetTouch position only; mouse
// input and gamepad cursor positions already use rendered screen pixels.
01E67858 E35BD497 // Touch.get_position -> scaled touch helper
01E698B4 0801271E // half-width constant: fmov s8,w8
01E698CC 0901271E // half-height constant: fmov s9,w8
// Use the remaining cave after the post-catch helper at 0x0137E7A0;
// end before the next function at 0x0137E824.
0137E7E4 FD7BBFA9 // save LR
0137E7E8 4AB76294 // Touch.get_position
0137E7EC 8805A852 // mov w8,#0x402c0000 (3440/1280 = 2.6875)
0137E7F0 0201271E // fmov s2,w8
0137E7F4 0008221E // touch X *= 2.6875
0137E7F8 2128211E // touch Y *= 2
0137E7FC FD7BC1A8 // restore LR
0137E800 C0035FD6 // ret
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text.replace(marker, additions + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--romfs", required=True, type=Path)
    parser.add_argument("--pchtxt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source_ui = (
        args.romfs
        / "Data"
        / "StreamingAssets"
        / "AssetAssistant"
        / "UIs"
    ).resolve()
    output = args.output.resolve()
    output_ui = (
        output
        / "romfs"
        / "Data"
        / "StreamingAssets"
        / "AssetAssistant"
        / "UIs"
    )

    all_changes = []
    bundle_counts = defaultdict(int)
    for source in sorted(path for path in source_ui.rglob("*") if path.is_file()):
        relative = source.relative_to(source_ui)
        changes = patch_bundle(source, output_ui / relative)
        all_changes.extend(changes)
        if changes:
            bundle_counts[str(relative)] = len(changes)

    resources_source = args.romfs / "Data" / "resources.assets"
    resources_relative = Path("Data/resources.assets")
    resource_changes = patch_resources(
        resources_source,
        output / "romfs" / resources_relative,
    )
    all_changes.extend(resource_changes)
    if resource_changes:
        bundle_counts[str(resources_relative)] = len(resource_changes)

    battle_effects_root = (
        args.romfs
        / "Data"
        / "StreamingAssets"
        / "AssetAssistant"
        / "Effects"
        / "effect"
        / "prefab"
        / "battle"
    )
    output_battle_effects_root = (
        output
        / "romfs"
        / "Data"
        / "StreamingAssets"
        / "AssetAssistant"
        / "Effects"
        / "effect"
        / "prefab"
        / "battle"
    )
    for source in sorted(battle_effects_root.glob("ef_b_encount*")):
        if not source.is_file():
            continue
        changes = patch_encounter_effect(
            source,
            output_battle_effects_root / source.name,
        )
        all_changes.extend(changes)
        if changes:
            relative = source.relative_to(args.romfs)
            bundle_counts[str(relative)] = len(changes)

    # Trainer and wild encounter transitions begin in the field scene. Their
    # white streaks already cover ultrawide, but the independent opaque
    # ``back`` billboard is authored at 16:9 and needs the same X correction.
    field_effects_root = battle_effects_root.parent / "field"
    output_field_effects_root = output_battle_effects_root.parent / "field"
    # Hidden Move cut-ins use the same 3.6-unit opaque ``back`` billboard.
    # Include that effect without widening the other move effects in-world.
    field_screen_effects = [
        *field_effects_root.glob("ef_f_encount*"),
        field_effects_root / "ef_f_waza_hiddenwaza_01",
    ]
    for source in sorted(field_screen_effects):
        if not source.is_file():
            continue
        changes = patch_encounter_effect(
            source,
            output_field_effects_root / source.name,
        )
        all_changes.extend(changes)
        if changes:
            relative = source.relative_to(args.romfs)
            bundle_counts[str(relative)] = len(changes)

    exefs = output / "exefs"
    write_exefs_patch(args.pchtxt, exefs / args.pchtxt.name)

    (output / "README.md").write_text(
        """# Pokémon Brilliant Diamond 21:9 Complete UI

Target: Pokémon Brilliant Diamond v1.3.0  
Title ID: `0100000011D90000`  
Build ID: `94CEAE325C205C4B9D6F7235552F28FD`

This is a self-contained 3440×1440 LayeredFS/ExeFS mod. It includes the
upstream ultrawide ExeFS patch; do not enable that patch separately. Keep the
emulator's **stretch to window** option enabled and use its **8 GB RAM
layout**, as required by the upstream patch.

The exact generated asset changes are listed in `ui_patch_manifest.json`.
""",
        encoding="utf-8",
    )

    manifest = {
        "reference_resolution": [REFERENCE_WIDTH, REFERENCE_HEIGHT],
        "changed_bundle_count": len(bundle_counts),
        "changed_transform_count": len(all_changes),
        "bundle_counts": dict(bundle_counts),
        "changes": all_changes,
    }
    (output / "ui_patch_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "changed_bundle_count": manifest["changed_bundle_count"],
                "changed_transform_count": manifest["changed_transform_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
