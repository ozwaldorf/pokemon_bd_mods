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
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import UnityPy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from staging import staged_directory


REFERENCE_WIDTH = 1280.0
REFERENCE_HEIGHT = 720.0
HALF_REFERENCE_WIDTH = REFERENCE_WIDTH / 2.0
# Every target renders 1440 pixels high. The patched CanvasScaler matches
# height, so all height-derived 2x factors are shared between targets.
OUTPUT_HEIGHT = 1440
CANVAS_SCALE = OUTPUT_HEIGHT / REFERENCE_HEIGHT
ENCOUNTER_BAND_NAMES = {"top_high", "top_low", "under_high", "under_low"}

# Keep the authored list camera: its reversed horizontal viewing direction
# makes a positive camera-root offset move the capsule right. The widened
# viewport already places this composition over the relocated tray.
CAPSULE_LIST_CAMERA_ROOT_X = -0.6

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
    # This screen-space camera canvas is copied into the capsule texture.
    # Keep its top-left pivot and cover the doubled render target completely.
    "Capsule3DView/Canvas/BgRoot": (2.0, 2.0),
    "Poketch/Window/Poketch": (POKETCH_SMALL_SCALE, POKETCH_SMALL_SCALE),
    # Compensate for the 2x trainer-card RenderTexture supersampling hook.
    "CardModelView/ModelRoot/BadgeCase/Canvas/BgRoot": (2.0, 2.0),
    # Fill the full 720-unit height from the panel's bottom-left pivot.
    "Map/Window/FacilityInfo": (720.0 / 630.0, 720.0 / 630.0),
    "MapWall/Window/FacilityInfo": (720.0 / 630.0, 720.0 / 630.0),
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
    # The texture patch moves the printed slots alongside the party cards:
    # 24 units left and 65 down, centering the six decorated rows vertically.
    "LevelUp/Window/Content": (30.0, -82.0),
}

CAMERA_LENS_SHIFT_X = {}

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
    "Seal/Window/Scene_CupsuleList/CupsuleList": "right",
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


@dataclass(frozen=True)
class Target:
    ratio: str
    width: int

    @property
    def name(self) -> str:
        return f"True Ultrawide UI {self.width}x{OUTPUT_HEIGHT} {self.ratio}"


TARGETS = {
    target.ratio: target
    for target in (Target("21:9", 3440), Target("20.1:9", 3216))
}


@dataclass
class Layout:
    """Width-dependent UI policies for one target, in 720-unit canvas space."""

    target: Target
    width: float = field(init=False)
    x_scale: float = field(init=False)
    # Half of the canvas width added beyond 1280 units.
    half_extra: float = field(init=False)
    encounter_band_width: float = field(init=False)
    fixed_rect_size_overrides: dict = field(init=False)
    battle_intro_ball_x_offsets: dict = field(init=False)
    anchored_position_x_offsets: dict = field(init=False)
    animation_x_offsets_by_path_hash: dict = field(init=False)
    size_x_overrides: dict = field(init=False)
    position_x_multipliers: dict = field(init=False)

    def __post_init__(self) -> None:
        width = self.width = self.target.width / CANVAS_SCALE
        self.x_scale = width / REFERENCE_WIDTH
        half = self.half_extra = (width - REFERENCE_WIDTH) / 2.0
        extra = 2.0 * half
        # The top/under encounter textures contain about 16.2% horizontal
        # visual padding. A pure aspect-ratio scale leaves their visible
        # streaks and rock silhouettes inset by roughly 166 display pixels on
        # each side at 21:9, where 5.775 was tuned; follow the canvas width.
        self.encounter_band_width = 5.775 * width / 1720.0

        # Nested canvases with RectMask2D do not reliably refresh a
        # stretch-anchored rect after the top-level window is widened. Give
        # those clipping frames an explicit size so their children cannot be
        # cut off at 1280 units.
        self.fixed_rect_size_overrides = {
            "Seal/Window/BGRoot": (width, REFERENCE_HEIGHT),
            "Seal/Window/BGRoot/BG/Image": (width, REFERENCE_HEIGHT),
        }

        # Move all trainer-intro artwork together inside the runtime-animated
        # plate. Keep the plate's authored rect and tween endpoints: shifting
        # its two visual children moves the complete arrow and all balls
        # without resizing the line.
        self.battle_intro_ball_x_offsets = {
            "BattleViewUISystem/BallPlate/BUIBallPlate_Near/Image_Arrow": half,
            "BattleViewUISystem/BallPlate/BUIBallPlate_Near/BallIcons": half,
            "BattleViewUISystem/BallPlate/BUIBallPlate_Far/Image_Arrow": -half,
            "BattleViewUISystem/BallPlate/BUIBallPlate_Far/BallIcons": -half,
        }

        self.anchored_position_x_offsets = {
            **self.battle_intro_ball_x_offsets,
            # PokeParty retains its animated 1280-wide coordinate frame. Its
            # cards start at physical X=half+29. Move the static content and
            # backing group together to retain the authored 29-unit inset.
            "Bag/Window/PokeParty/Content": -half,
            "Bag/Window/PokeParty/Base": -half,
            "Pokemon/Window/PokeParty/Content": -half,
            "Pokemon/Window/PokeParty/Base": -half,
            # UISeal resets the tray parent's position when entering edit mode.
            # Its nested canvas retains the 1280-unit center, so move all
            # artwork within that runtime-controlled parent by the missing
            # half-width.
            **{
                f"Seal/Window/BGRoot/BG/CupsuleBase/{child}": half
                for child in (
                    "Image_line", "Image_base_center", "Image_base_left", "Image_base_right",
                    "Image_arrow_00_eff", "Image_arrow_01", "Image_arrow_02",
                    "Image_arrow_03", "Image_arrow_04",
                )
            },
            # Center the unknown-habitat banner in the space beside the left
            # panel.
            "ZukanHabitat/Window/Map/Body/HabitatMap/NotFound": -6.0,
            # This top-right-pivoted window is positioned by its entrance/exit
            # clips. Preserve that fixed coordinate frame and move its pivot to
            # the new canvas right edge; stretching it makes the clips push it
            # off-screen.
            "Poketch/Window": half,
            # This widened image is centered by a nested 1280-wide canvas.
            # Shift it by half the added canvas width so it covers physical
            # X=0..width instead of extending from X=-half.
            "Seal/Window/BGRoot/BG/Image": half,
            # Keep the complete Pokédex preview and footprint with their
            # widened left/right page groups.
            "Zukan/Window/ZukanDescriptionPanel/ModelViewParent": half,
            "ZukanRegister/Window/ZukanDescriptionPanel/ModelViewParent": half,
            "Zukan/Window/ZukanDescriptionPanel/FootPrint": half,
            "ZukanRegister/Window/ZukanDescriptionPanel/FootPrint": half,
            # Match the final positions written by the corrected map
            # animations.
            "Map/Window/FacilityInfo": -half,
            "MapWall/Window/FacilityInfo": -half,
            # Grow the ocean backing leftward without moving interactive map
            # content.
            "Map/Window/Map/Object_Map/Body/Image_Base": -(half - 2.0) / 2.0,
            # This icon is left-anchored while its containing Bag panel is
            # aligned to the widened right edge. Follow the full canvas
            # expansion.
            "Bag/Window/BagItemPanel/BagIconImage": extra,
            # Keep the battle party details panel's 16:9 placement relative to
            # the physical right edge. Its BattlePokemon animation curves
            # receive the same offset so transitions cannot restore the
            # centered position.
            "PokemonBattle/Window/StatusWindow": half,
        }

        # Unity animation binding paths use CRC32. These elements are animated
        # back to their authored positions on every transition, so every curve
        # representation must be offset along with its serialized rest pose.
        # Values are (offset, clip-name prefixes). The hashes are reused by
        # unrelated clips, so the resident bundle, component type, and clip
        # names are constrained.
        self.animation_x_offsets_by_path_hash = {
            # GoToBox is right-anchored by the layout patch. Its party-screen
            # clips still use center-relative X values, which otherwise hide
            # the hint.
            2215735440: (-HALF_REFERENCE_WIDTH, ("Pokemon__",)),  # GoToBox
            # Convert the capsule selector's center-anchored entrance positions
            # to the same right-anchored frame as its serialized rect.
            2592220292: (-HALF_REFERENCE_WIDTH, ("Seal__",)),  # Scene_CupsuleList/CupsuleList
            1210394069: (-half, ("Map__", "MapWall__")),  # FacilityInfo
            159791602: (extra, ("Bag__",)),  # BagItemPanel/BagIconImage
            3910900351: (half, ("BattlePokemon__",)),  # StatusWindow
        }

        self.size_x_overrides = {
            "Poketch/Window": width,
            # The description's brown panel grows with the status-page
            # background. Expand its striped paper and sliced frame together
            # around the existing preview center so the 42-unit sliced frame
            # matches the left panel. Widen the RawImage too:
            # PokemonModelView uses its rect to set RenderTexture dimensions
            # and camera aspect. Keeping its height preserves the Pokemon's
            # proportions and vertical framing while revealing the paper
            # across the entire wider output instead of clipping it square.
            **{
                f"{window}/Window/ZukanDescriptionPanel/ModelViewParent/ModelView{child}": (
                    590.0 + extra - 4.0
                )
                for window in ("Zukan", "ZukanRegister")
                for child in ("", "/Offset", "/Offset/BG", "/RawImageParent/RawImage")
            },
            # Extend only the ocean backing; keep map tiles and habitat
            # coordinates at their authored scale inside the wider clipping
            # frame.
            "ZukanHabitat/Window/Map/Body/HabitatMap/Body/Image_Base": 1500.0 + extra,
            "ZukanHabitat/Window/Map/Body/HabitatMap/NotFound": width - 396.0,
            # Battle code animates these parents to anchored X=0 at runtime.
            # Keep their centered anchors and widen the coordinate frames so
            # right-anchored command controls land on the physical screen edge.
            "BattleViewUISystem/BUIActionList": width,
            "BattleViewUISystem/BUIWazaList": width,
            # The Pokédex details body is a centered 1280-wide coordinate
            # group. Its right-anchored fields otherwise lag behind the
            # widened header.
            "Zukan/Window/ZukanDescriptionPanel/FixedObjects/StatusPanel": width,
            "ZukanRegister/Window/ZukanDescriptionPanel/FixedObjects/StatusPanel": width,
            # Match the party screen's backing width, leaving the same margin
            # beyond the cards while keeping their authored left inset.
            "Bag/Window/Image_PartyPlate": 532.0,
            # Battle party details still need the widened backing panel.
            "PokemonBattle/Window/BG/Image_plate": 481.0 + half,
            # Keep the original right edge; grow leftward with the canvas.
            "Map/Window/Map/Object_Map/Body/Image_Base": 1500.0 + half - 2.0,
        }

        # The Pokédex header art stretches with the widened window. Its
        # centered labels must follow the same horizontal ratio to stay on the
        # printed pills.
        self.position_x_multipliers = {
            path: self.x_scale
            for path in (
                "Zukan/Window/Header/Image_Title",
                "Zukan/Window/Header/GetPokeCountText",
                "Zukan/Window/Header/FoundPokeCountText",
                "Zukan/Window/Header/SortNameText",
            )
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


def mov_w(register: int, value: int) -> str:
    """Encode movz wN,#value as a little-endian pchtxt word."""
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"movz immediate out of range: {value}")
    return struct.pack("<I", 0x52800000 | (value << 5) | register).hex().upper()


def mov_float_w8(value: float, rounded: bool = False) -> str:
    """Encode movz w8,#hi,lsl #16 holding a float's upper 16 bits."""
    bits = float_to_uint32(value)
    if rounded:
        bits = (bits + 0x8000) & 0xFFFF0000
    elif bits & 0xFFFF:
        raise ValueError(f"Float needs a two-instruction load: {value}")
    return struct.pack("<I", 0x52A00008 | ((bits >> 16) << 5)).hex().upper()


def fmov_s0_at_least(value: float) -> tuple[str, float]:
    """Encode fmov s0,#imm with the smallest immediate not below value."""
    def expand(imm8: int) -> float:
        b = (imm8 >> 6) & 1
        exponent = ((b ^ 1) << 7) | (0x7C if b else 0) | ((imm8 >> 4) & 3)
        return (1.0 + (imm8 & 0xF) / 16.0) * 2.0 ** (exponent - 127)

    imm8 = min((i for i in range(128) if expand(i) >= value), key=expand)
    return struct.pack("<I", 0x1E201000 | (imm8 << 13)).hex().upper(), expand(imm8)


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


def patch_exp_backdrop(env) -> list[dict]:
    """Move the printed EXP slots without moving the surrounding paper frame."""
    from UnityPy.export.Texture2DConverter import image_to_texture2d

    sprite = next(
        obj.read() for obj in env.objects
        if obj.type.name == "Sprite" and obj.peek_name() == "cmn_pl_expgain_01"
    )
    atlas = next(
        obj.read() for obj in env.objects
        if obj.type.name == "SpriteAtlas" and obj.peek_name() == "SharedUI"
    )
    data = next(value for key, value in atlas.m_RenderDataMap if key == sprite.m_RenderDataKey)
    texture = data.texture.read()
    if (texture.m_Width, texture.m_Height, texture.m_TextureFormat) != (2048, 2048, 50):
        raise ValueError("Unexpected EXP backdrop atlas dimensions or ASTC format")
    rect = data.textureRect
    if not (near(rect.x, 0) and near(rect.y, 1207.076171875)
            and near(rect.width, 490.92388916015625)
            and near(rect.height, 720.9238891601562)):
        raise ValueError("Unexpected EXP backdrop atlas placement")

    image = texture.image.convert("RGBA")
    paper = image.crop((0, 120, 491, 841))
    moved = paper.copy()

    def clean_pixel(x: int, y: int) -> tuple[int, ...]:
        # The paper and cyan border have a slow vertical gradient. Recover
        # the strip beneath the old slots from the clear gaps above/below.
        for index in range(6):
            # Include antialiased white outlines, not only the gray bodies.
            start, end = 18 + 94 * index, 106 + 94 * index
            if start <= y < end:
                low, high = start - 3, end + 2
                a, b = paper.getpixel((x, low)), paper.getpixel((x, high))
                weight = (y - low) / (high - low)
                return tuple(round(v + (w - v) * weight) for v, w in zip(a, b))
        return paper.getpixel((x, y))

    # Move the printed paper artwork by the same 24 pixels as the cards.
    # Leave the outer top/bottom frame and right-hand cyan border in place.
    moved.paste(paper.crop((25, 4, 448, 717)), (1, 4))
    for y in range(4, 717):
        background = clean_pixel(430, y)
        for x in range(448, 465):
            old, clean = paper.getpixel((x, y)), clean_pixel(x, y)
            # The old slot's end overlaps the cyan border. Carry its shading
            # onto plain paper rather than copying the cyan tint leftward.
            shade = sum(old[:3]) / max(1, sum(clean[:3]))
            moved.putpixel((x - 24, y), tuple(min(255, round(c * shade)) for c in background[:3]) + (255,))
            moved.putpixel((x, y), clean)
        for x in range(441, 448):
            moved.putpixel((x, y), background)
    # Center the printed rows vertically together with their UI cards.
    # Fill the exposed top strip with clean paper; retain the outer frame.
    moved.paste(moved.crop((1, 4, 448, 652)), (1, 69))
    for y in range(4, 69):
        # Continue the original ten-pixel stripe pattern at the translated
        # phase. Sampling the right edge alone loses its faded-out lines.
        source_y = 10 + (y - 65) % 10
        stripe = paper.getpixel((30, source_y))
        plain = paper.getpixel((430, source_y))
        for x in range(1, 448):
            fade = max(0.0, min(1.0, (x - 380) / 50))
            background = tuple(round(a + (b - a) * fade) for a, b in zip(stripe, plain))
            moved.putpixel((x, y), background)
    # Preserve the entire frame and its transparent lower shadow. Restrict
    # re-encoding to whole ASTC blocks inside those untouched border rows.
    moved.paste(paper.crop((0, 0, 491, 8)), (0, 0))
    moved.paste(paper.crop((0, 704, 491, 721)), (0, 704))
    image.paste(moved, (0, 120))

    # Re-encode only the 6x6 ASTC blocks containing the edited paper region.
    # All other atlas blocks retain their original compressed bytes.
    encoded, _ = image_to_texture2d(image.crop((0, 128, 468, 824)), 50)
    original = bytearray(texture.get_image_data())
    full_stride, patch_stride = 342 * 16, 78 * 16
    for row in range(116):
        target = (204 + row) * full_stride
        original[target:target + patch_stride] = encoded[row * patch_stride:(row + 1) * patch_stride]
    texture.image_data = bytes(original)
    texture.m_StreamData.path = ""
    texture.m_StreamData.offset = 0
    texture.m_StreamData.size = 0
    texture.save()
    return [{"path": "SharedUI/cmn_pl_expgain_01", "path_id": data.texture.path_id,
             "action": "texture_printed_slots_left_24_down_65_restore_border"}]


def patch_bundle(source: Path, destination: Path, layout: Layout) -> list[dict]:
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
        elif path in layout.fixed_rect_size_overrides:
            width, height = layout.fixed_rect_size_overrides[path]
            set_fixed_centered_size(rect, width, height)
            action = f"fixed_centered_size_{width:g}x{height:g}"
            if path in layout.anchored_position_x_offsets:
                offset = layout.anchored_position_x_offsets[path]
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
            if path in layout.anchored_position_x_offsets:
                rect.m_AnchoredPosition.x += layout.anchored_position_x_offsets[path]
            action = f"local_scale_{sx:g}x{sy:g}"
        elif path in ANCHORED_POSITION_OVERRIDES:
            x, y = ANCHORED_POSITION_OVERRIDES[path]
            rect.m_AnchoredPosition.x = x
            rect.m_AnchoredPosition.y = y
            action = f"position_{x:g}_{y:g}"
        elif path in layout.size_x_overrides:
            rect.m_SizeDelta.x = layout.size_x_overrides[path]
            action = f"size_x_{layout.size_x_overrides[path]:g}"
            if path in layout.anchored_position_x_offsets:
                offset = layout.anchored_position_x_offsets[path]
                rect.m_AnchoredPosition.x += offset
                action += f"_position_x_plus_{offset:g}"
        elif path in layout.anchored_position_x_offsets:
            offset = layout.anchored_position_x_offsets[path]
            rect.m_AnchoredPosition.x += offset
            if path in layout.battle_intro_ball_x_offsets:
                # Keep the serialized transform position consistent with the
                # rect position before battle startup caches local transforms.
                rect.m_LocalPosition.x += offset
            action = f"position_x_plus_{offset:g}"
        elif path in layout.position_x_multipliers:
            multiplier = layout.position_x_multipliers[path]
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
                    offset = layout.anchored_position_x_offsets["Poketch/Window"]
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
            if binding.path in layout.animation_x_offsets_by_path_hash
            and binding.typeID == 224
            and clip.m_Name.startswith(
                layout.animation_x_offsets_by_path_hash[binding.path][1]
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
            offset = layout.animation_x_offsets_by_path_hash[bindings[index].path][0]
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

    if source.name == "sharedui" and source.parent.name == "shareduiassets":
        for change in patch_exp_backdrop(env):
            changes.append({"bundle": str(source), **change})

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


def patch_encounter_effect(source: Path, destination: Path, layout: Layout) -> list[dict]:
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
            initial.startSize.scalar = layout.encounter_band_width
            action = f"start_size_x_{layout.encounter_band_width:g}"
        else:
            initial.startSize.scalar = old_size_x * layout.x_scale
            action = f"start_size_x_times_{layout.x_scale:g}"
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


def patch_demo_overlay(source: Path, destination: Path, overlay_name: str) -> list[dict]:
    """Make the demo fade/flash cover the canvas, including during animation."""
    env = UnityPy.load(str(source))
    changes = []
    for obj in env.objects:
        if obj.type.name != "RectTransform":
            continue
        rect = obj.read()
        if rect.m_GameObject.read().m_Name != overlay_name:
            continue
        if not is_reference_frame(rect):
            raise ValueError(f"Unexpected demo overlay dimensions: {source}/{overlay_name}")
        path, _ = build_hierarchy(rect)
        stretch(rect)
        rect.save()
        changes.append({"bundle": str(source), "path": path,
                        "path_id": obj.path_id, "action": "stretch_demo_overlay"})
    if len(changes) != 1:
        raise ValueError(f"Expected one {overlay_name} demo overlay in {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(env.file.save(packer="original"))
    return changes


def write_exefs_patch(source: Path, destination: Path, layout: Layout) -> None:
    text = source.read_text(encoding="utf-8")
    marker = "@stop"
    if marker not in text:
        raise ValueError(f"Missing {marker} in {source}")
    output_width = layout.target.width
    # The upstream patch hardcodes its 3440-pixel output width.
    upstream_width = re.compile(r"^([0-9A-F]{8}) ([0-9A-F]{8}) // mov w(\d+),#0xD70.*$", re.MULTILINE)
    def replace_width(match: re.Match) -> str:
        address, word, register = match[1], match[2], int(match[3])
        if word != mov_w(register, 3440):
            raise ValueError(f"Unexpected upstream output-width patch: {match[0]}")
        return f"{address} {mov_w(register, output_width)} // mov w{register},#{output_width}"

    text, count = upstream_width.subn(replace_width, text)
    if count != 4:
        raise ValueError(f"Expected 4 upstream output-width patches, found {count}")
    old_model_bg = "0137E5B8 0010201E // background root X = 2"
    model_bg, model_bg_scale = fmov_s0_at_least(CANVAS_SCALE * layout.x_scale)
    new_model_bg = f"0137E5B8 {model_bg} // background root X = {model_bg_scale:g} (ultrawide coverage)"
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
    logical_width = layout.width
    bag_dialog_x = 260.0 - layout.half_extra
    # Touch scaling has no spare cave room for a second float instruction;
    # the rounded factor is within 0.2% of the exact ratio.
    touch_scale = output_width / REFERENCE_WIDTH
    additions = f"""// DemoCamera.CreateRenderTex hardcodes 1280x720 for evolution and other
// shared demos. Render at the full output size; the camera's target texture
// supplies the wider aspect while preserving vertical framing.
01AC8A4C {mov_w(1, output_width)} // mov w1,#{output_width} (render texture width)
01AC8A50 {mov_w(2, OUTPUT_HEIGHT)} // mov w2,#{OUTPUT_HEIGHT} (render texture height)
// DemoSceneManager.CommonInit creates a centered RawImage at 1280x720.
// CanvasScaler already matches height through the upstream patch, so use
// {logical_width:g}x720 logical units to display {output_width}x{OUTPUT_HEIGHT} without stretching the Pokemon.
01ACA350 {mov_float_w8(logical_width)} // mov w8,{logical_width:g}f (display width)
// Bag.OpOpen supplies its own shared-message-window anchor (260, 110).
// Shift the complete Bag dialog left by half the added canvas width; keep
// its vertical anchor and all other screens' message windows unchanged.
01BE2DC0 {mov_float_w8(bag_dialog_x)} // mov w8,{bag_dialog_x:g}f; Bag dialog X instead of 260
// Full-width encounter band coverage
// Double the RawImage rect dimensions before creating its RenderTexture.
01A30B38 1637E597 // BL 0x0137E790
0137E790 0829281E // fadd s8,s8,s8
0137E794 2929291E // fadd s9,s9,s9
0137E798 0101381E // displaced fcvtzs w1,s8
0137E79C C0035FD6 // ret
// BattlePostProcessFilter creates the DOF/composite texture used during
// trainer and Pokemon entrance sequences. These RenderTextures use physical
// pixels rather than the {logical_width:g}-unit UI canvas, so request the mod's full
// {output_width} output width while retaining the runtime-provided height.
01E4917C {mov_w(1, output_width)} // mov w1,#{output_width}
// BattleMultipleCameraCompositor creates the color, depth, and copied-depth
// inputs consumed by the post-process filter. Widen all three source targets
// to the same physical width. Using the logical width here would stretch a
// half-resolution 3D scene across the physical output.
01F7C5AC {mov_w(1, output_width)} // color target: mov w1,#{output_width}
01F7C60C {mov_w(1, output_width)} // depth target: mov w1,#{output_width}
01F7C670 {mov_w(1, output_width)} // copied depth target: mov w1,#{output_width}
// Poketch touch input: Switch touch coordinates remain 1280x720 even when
// the render output is {output_width}x{OUTPUT_HEIGHT}. Scale the GetTouch position only; mouse
// input and gamepad cursor positions already use rendered screen pixels.
01E67858 E35BD497 // Touch.get_position -> scaled touch helper
01E698B4 0801271E // half-width constant: fmov s8,w8
01E698CC 0901271E // half-height constant: fmov s9,w8
// Use the remaining cave after the post-catch helper at 0x0137E7A0;
// end before the next function at 0x0137E824.
0137E7E4 FD7BBFA9 // save LR
0137E7E8 4AB76294 // Touch.get_position
0137E7EC {mov_float_w8(touch_scale, rounded=True)} // mov w8,~{touch_scale:g}f ({output_width}/1280)
0137E7F0 0201271E // fmov s2,w8
0137E7F4 0008221E // touch X *= output width / 1280
0137E7F8 2128211E // touch Y *= 2
0137E7FC FD7BC1A8 // restore LR
0137E800 C0035FD6 // ret
// Capsule3DViewController creates its RenderTexture from logical UI units,
// but Raycast and GetScreenPosition use physical screen coordinates. Match
// the 2x CanvasScaler so both camera conversions agree with the visible
// capsule. Double both dimensions to preserve the list/editor camera aspect.
01A28E38 7356E597 // BL 0x0137E804 instead of fcvtzs w1,s8
0137E804 0829281E // fadd s8,s8,s8
0137E808 2929291E // fadd s9,s9,s9
0137E80C 0101381E // displaced fcvtzs w1,s8
0137E810 C0035FD6 // ret; original height conversion consumes doubled s9
// Capsule2D grid indices divide world-space UI distances by cell size.
// Scale the cell spacing once before the loop to match the 2x canvas;
// otherwise adjacent cells get indices two apart and directional moves fail.
01A28244 7459E597 // BL 0x0137E814 instead of mov v9.16b,v1.16b
0137E814 291CA14E // displaced mov v9.16b,v1.16b
0137E818 0829281E // fadd s8,s8,s8 (cell width)
0137E81C 2929291E // fadd s9,s9,s9 (cell height)
0137E820 C0035FD6 // ret; next original function starts at 0x0137E824
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text.replace(marker, additions + marker, 1), encoding="utf-8")


def build(romfs: Path, pchtxt: Path, output: Path, target: Target) -> dict:
    layout = Layout(target)
    source_ui = (
        romfs
        / "Data"
        / "StreamingAssets"
        / "AssetAssistant"
        / "UIs"
    )
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
        changes = patch_bundle(source, output_ui / relative, layout)
        all_changes.extend(changes)
        if changes:
            bundle_counts[str(relative)] = len(changes)

    resources_source = romfs / "Data" / "resources.assets"
    resources_relative = Path("Data/resources.assets")
    resource_changes = patch_resources(
        resources_source,
        output / "romfs" / resources_relative,
    )
    all_changes.extend(resource_changes)
    if resource_changes:
        bundle_counts[str(resources_relative)] = len(resource_changes)

    battle_effects_root = (
        romfs
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
            layout,
        )
        all_changes.extend(changes)
        if changes:
            relative = source.relative_to(romfs)
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
            layout,
        )
        all_changes.extend(changes)
        if changes:
            relative = source.relative_to(romfs)
            bundle_counts[str(relative)] = len(changes)

    # Demo assets live outside UIs. The shared transition fade and evolution's
    # white flash are fixed 1280x720 overlays and must cover the whole canvas.
    demo_root = Path("Data/StreamingAssets/AssetAssistant/FureaiHiroba/demo")
    for relative, overlay_name in (
        (demo_root / "demosceneprefab", "Fade"),
        (demo_root / "timeline/evolve", "Image"),
    ):
        changes = patch_demo_overlay(romfs / relative, output / "romfs" / relative,
                                     overlay_name)
        all_changes.extend(changes)
        bundle_counts[str(relative)] = len(changes)

    exefs = output / "exefs"
    write_exefs_patch(pchtxt, exefs / pchtxt.name, layout)

    attribution = Path(__file__).resolve().parents[1] / "ATTRIBUTION.md"
    (output / "ATTRIBUTION.md").write_bytes(attribution.read_bytes())

    (output / "README.md").write_text(
        f"""# {target.name}

For Pokémon Brilliant Diamond 1.3.0 at {target.width}×{OUTPUT_HEIGHT} ({target.ratio}), for Eden.

## Credits

The original ultrawide ExeFS patch is by
[Fl4sh_#9174 (Fl4sh9174)](https://github.com/Fl4sh9174), from the
[Brilliant Diamond mod archive](https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods/blob/main/Pokemon%20Brilliant%20Diamond%20%5B0100000011D90000%5D%5Bmods%5D.zip).
This project adds UI asset patches, further native fixes, and build tools.
See [source attribution](ATTRIBUTION.md) for the upstream file and revision.

## Installation

Copy this directory into your emulator's mod directory as
`{target.name}`. Restart the game after installing.
Enable **stretch to window** and the **8 GB RAM layout** in Eden.
Enable this mod on its own; the upstream ultrawide ExeFS patch is included.

The mod targets title `0100000011D90000`, build
`94CEAE325C205C4B9D6F7235552F28FD`.

## Changes

UI assets and native patches adapt the game to the wider viewport.
The generated asset changes are listed in `ui_patch_manifest.json`.
""",
        encoding="utf-8",
    )

    # Record bundles relative to RomFS so the manifest has no local paths.
    for change in all_changes:
        change["bundle"] = Path(change["bundle"]).relative_to(romfs).as_posix()
    manifest = {
        "reference_resolution": [REFERENCE_WIDTH, REFERENCE_HEIGHT],
        "output_resolution": [target.width, OUTPUT_HEIGHT],
        "canvas_resolution": [layout.width, REFERENCE_HEIGHT],
        "changed_bundle_count": len(bundle_counts),
        "changed_transform_count": len(all_changes),
        "bundle_counts": dict(bundle_counts),
        "changes": all_changes,
    }
    (output / "ui_patch_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--romfs", required=True, type=Path)
    parser.add_argument("--pchtxt", required=True, type=Path)
    parser.add_argument("--dist", required=True, type=Path,
                        help="directory receiving one mod directory per target")
    parser.add_argument("--target", action="append", choices=TARGETS,
                        help="aspect ratio to build; repeatable (default: all)")
    args = parser.parse_args()
    for ratio in args.target or TARGETS:
        target = TARGETS[ratio]
        output = (args.dist / target.name).resolve()
        # Build into a fresh directory so files from earlier builds never ship.
        with staged_directory(output) as staged:
            manifest = build(args.romfs.resolve(), args.pchtxt, staged, target)
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
