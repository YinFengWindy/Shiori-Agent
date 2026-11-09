"""Static allocation admission matching the renderer's final scene plan."""

import json
import math
from pathlib import Path
from typing import Any

GEOMETRY_LIMITS: dict[str, int] = json.loads(
    (Path(__file__).resolve().parents[1] / "geometry-limits.json").read_text(
        encoding="utf-8"
    )
)


def validate_geometry(bake: dict[str, Any]) -> None:
    """Reject excessive final meshes and generated textures before publishing a model.

    Called after structural validation. Count every allocated mesh, including
    invisible layers, but exclude original mouth meshes replaced by the scene
    planner before allocation. Component layers inherit their owner's fade.
    """
    layers = bake["prepared"]["layers"]
    mouth = bake["mouth"]
    pins = {entry["layer"]: entry for entry in bake["hair"]["layers"]}
    lids = {entry["side"]: entry for entry in bake["lids"]["eyes"]}
    total = 0

    def add(count: int, label: str) -> None:
        nonlocal total
        if count > GEOMETRY_LIMITS["maxMeshVertices"]:
            raise ValueError(f"{label} 网格超出顶点预算")
        total += count
        if total > GEOMETRY_LIMITS["maxTotalVertices"]:
            raise ValueError("形象场景超出总顶点预算")

    for index, layer in enumerate(layers):
        if index != mouth["closed"] and layer.get("fade") not in {
            "mouthClose",
            "mouthOpen",
        }:
            hair = pins.get(index)
            count = (
                (hair["nx"] + 1) * (hair["ny"] + 1)
                if hair is not None
                else _image_vertices(layer)
            )
            add(count, f"图层 {index}")

        if layer["name"] == "face":
            for lid in lids.values():
                skin = lid.get("skin")
                if skin is not None:
                    add(
                        _component_vertices(layer, skin, f"eye_skin_{lid['side']}"),
                        "眼睑皮肤",
                    )

        if index == mouth["closed"]:
            parametric = mouth["parametric"]
            add(
                _image_vertices(
                    {
                        **layer,
                        **parametric,
                        "name": "parametric_mouth",
                        "fade": None,
                    }
                ),
                "参数嘴",
            )
            scale = GEOMETRY_LIMITS["mouthTextureScale"]
            _generated_texture(
                parametric["w"] * scale, parametric["h"] * scale, "参数嘴"
            )

        lid = lids.get(layer.get("side"))
        lash = (
            next((item for item in lid["lashes"] if item["layer"] == index), None)
            if lid is not None
            else None
        )
        if lid is not None and lash is not None:
            add(
                _component_vertices(layer, lash["rest"], layer["name"] + ":rest"),
                "睫毛残余",
            )
            columns = max(2, math.ceil(lid["shape"]["high"] - lid["shape"]["low"]) + 1)
            add(columns * 4, "眼睑轮廓")
            _generated_texture(columns, 2, "眼睑轮廓")
            ink = lash.get("ink")
            if ink is not None:
                add(
                    _component_vertices(layer, ink, layer["name"] + ":ink"),
                    "睫毛墨线",
                )


def _component_vertices(
    owner: dict[str, Any], rectangle: dict[str, Any], name: str
) -> int:
    # TS imageRect projects only geometry; unrelated source fields cannot override owner fade.
    return _image_vertices(
        {
            "w": rectangle["w"],
            "h": rectangle["h"],
            "name": name,
            "fade": owner.get("fade"),
        }
    )


def _image_vertices(layer: dict[str, Any]) -> int:
    detailed = layer.get("fade") == "eyeOpen" or layer["name"].startswith("eye_skin")
    stride = 5 if detailed else 42
    # Python round uses ties-to-even; the JS renderer uses Math.round for positive sizes.
    nx = max(1, math.floor(layer["w"] / stride + 0.5))
    ny = max(1, math.floor(layer["h"] / stride + 0.5))
    return (nx + 1) * (ny + 1)


def _generated_texture(width: int, height: int, label: str) -> None:
    if (
        width > GEOMETRY_LIMITS["maxGeneratedTextureSide"]
        or height > GEOMETRY_LIMITS["maxGeneratedTextureSide"]
        or width * height > GEOMETRY_LIMITS["maxGeneratedTexturePixels"]
    ):
        raise ValueError(f"{label} 生成纹理超出尺寸预算")
