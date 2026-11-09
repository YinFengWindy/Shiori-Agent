"""Validate the four frozen bake algorithms and their renderer allocation bounds."""

import base64
import binascii
import math
import struct
from typing import Any

from .geometry import GEOMETRY_LIMITS, validate_geometry
from .package_images import ImageInfo
from .rig_schema import anchors, box, dimensions, layers, mouth_fit
from .validation import array, choice, number, object_value, vector

BAKE_VERSIONS = {
    "prepared": "prepared-v1-78b039a0f17fac16",
    "mouth": "mouth-v1-49795064767624ca",
    "hair": "hair-v1-2de9459fc64e7fc1",
    "lids": "lids-v1-5f0c2e9a71d4b836",
}
MAX_VERTICES = GEOMETRY_LIMITS["maxMeshVertices"]
MAX_TOTAL_VERTICES = GEOMETRY_LIMITS["maxTotalVertices"]


def packed_floats(value: object, count: int, label: str) -> tuple[float, ...]:
    """Read only canonical little-endian Float32 arrays with exact lengths."""
    encoded_length = 4 * ((count * 4 + 2) // 3)
    if (
        not isinstance(value, str)
        or len(value) != encoded_length
        or encoded_length > 16 * 1024 * 1024
    ):
        raise ValueError(f"{label} mesh 数组长度无效")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError(f"{label} base64 无效") from error
    if len(raw) != count * 4 or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError(f"{label} mesh 数组长度无效")
    values = struct.unpack(f"<{count}f", raw)
    if any(not math.isfinite(v) for v in values):
        raise ValueError(f"{label} mesh 包含非有限数值")
    return values


def _layer_index(value: object, rows: list[dict[str, Any]], label: str) -> int:
    return int(number(value, label, low=0, high=len(rows) - 1, integer=True))


def validate_bake(bake: dict[str, Any], images: dict[str, ImageInfo]) -> None:
    """Preserve prepared corrections and reject unsupported algorithm versions."""
    if bake.get("schema") != "prelulu-rig-bake/v1":
        raise ValueError("不支持的 baked schema")
    for field, version in BAKE_VERSIONS.items():
        section = bake.get(field)
        if object_value(section, field).get("version") != version:
            raise ValueError(f"不支持的 {field} 算法版本")
    prepared = bake["prepared"]
    rows = layers(prepared.get("layers"), images, "prepared.layers")
    prepared_anchors = object_value(prepared.get("anchors"), "prepared.anchors")
    # The shipped renderer requires two measured eyes; it does not infer a missing side.
    for side in ("eyeL", "eyeR"):
        object_value(prepared_anchors.get(side), f"prepared.anchors.{side}")
    anchors(prepared_anchors, "prepared.anchors")
    if "eyeAxisAlignment" in prepared:
        alignment = object_value(prepared["eyeAxisAlignment"], "eyeAxisAlignment")
        for value in array(
            alignment.get("results"), "eyeAxisAlignment.results", maximum=2
        ):
            item = object_value(value, "eye alignment")
            choice(item.get("side"), {"L", "R"}, "eye.side")
            choice(item.get("status"), {"unsupported-axis", "aligned"}, "eye.status")
    _hair(bake["hair"], rows)
    _lids(bake["lids"], rows, images)
    _mouth(bake["mouth"], rows)
    validate_geometry(bake)


def _hair(hair: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    seen = set()
    total = 0
    for raw in array(hair.get("layers"), "hair.layers"):
        entry = object_value(raw, "hair layer")
        index = _layer_index(entry.get("layer"), rows, "hair.layer")
        if index in seen or rows[index].get("phys") not in {"hair", "sway"}:
            raise ValueError("hair.layer 引用无效或重复")
        seen.add(index)
        if entry.get("version") != "hair-pins/v3":
            raise ValueError("不支持的 hair-pins 版本")
        choice(entry.get("kind"), {"front", "back", "accessory"}, "hair.kind")
        nx = int(
            number(entry.get("nx"), "hair.nx", low=1, high=MAX_VERTICES, integer=True)
        )
        ny = int(
            number(entry.get("ny"), "hair.ny", low=1, high=MAX_VERTICES, integer=True)
        )
        n = (nx + 1) * (ny + 1)
        total += n
        if n > MAX_VERTICES or total > MAX_TOTAL_VERTICES:
            raise ValueError("hair mesh 顶点数量超过限制")
        strands = array(entry.get("strands"), "hair.strands", minimum=1)
        for raw_strand in strands:
            strand = object_value(raw_strand, "strand")
            for key in ("x", "rootY", "tipY", "attachY"):
                number(strand.get(key), key)
            number(strand.get("hang"), "strand.hang", low=0)
            number(strand.get("freedom"), "strand.freedom", low=0, high=1)
            choice(strand.get("restsOn"), {None, "head", "body"}, "strand.restsOn")
        rest = packed_floats(entry.get("rest"), n * 2, "hair.rest")
        if any(abs(v) > 1e7 for v in rest):
            raise ValueError("hair.rest 坐标越界")
        weights = packed_floats(entry.get("weights"), n * len(strands), "hair.weights")
        if any(not 0 <= v <= 1.000001 for v in weights):
            raise ValueError("hair.weights 权重无效")
        for offset in range(0, len(weights), len(strands)):
            if abs(sum(weights[offset : offset + len(strands)]) - 1) > 1e-4:
                raise ValueError("hair.weights 权重未归一")
        fields = {
            key: packed_floats(entry.get(key), n, "hair." + key)
            for key in ("freedom", "hang", "cap", "lo", "hi")
        }
        if any(not 0 <= v <= 1 for v in fields["freedom"]):
            raise ValueError("hair.freedom 无效")
        if any(
            v < 0 or v > 1e7 for key in ("hang", "cap", "hi") for v in fields[key]
        ) or any(v > 0 or v < -1e7 for v in fields["lo"]):
            raise ValueError("hair 约束范围无效")


def _lids(
    lids: dict[str, Any], rows: list[dict[str, Any]], images: dict[str, ImageInfo]
) -> None:
    seen = set()
    for raw in array(lids.get("eyes"), "lids.eyes", maximum=2):
        eye = object_value(raw, "lid")
        side = eye.get("side")
        choice(side, {"L", "R"}, "lid.side")
        if side in seen:
            raise ValueError("重复眼睑侧别")
        seen.add(side)
        shape = object_value(eye.get("shape"), "lid.shape")
        number(shape.get("scale"), "lid.scale", low=1e-9, high=16384)
        number(shape.get("low"), "lid.low")
        number(shape.get("high"), "lid.high")
        if shape["low"] >= shape["high"]:
            raise ValueError("眼睑横向范围无效")
        for key in ("lower", "edge", "smile"):
            vector(shape.get(key), 3, key)
        number(shape.get("rise"), "lid.rise")
        number(shape.get("opening"), "lid.opening", low=1, high=16384)
        number(shape.get("weight"), "lid.weight", low=1, high=64)
        vector(shape.get("colour"), 3, "lid.colour", low=0, high=255, integer=True)
        for v in array(shape.get("band"), "lid.band", minimum=65, maximum=65):
            number(v, "lid.band", low=0, high=256)
        for raw_lash in array(eye.get("lashes"), "lid.lashes", minimum=1, maximum=8):
            lash = object_value(raw_lash, "lash")
            index = _layer_index(lash.get("layer"), rows, "lash.layer")
            if rows[index].get("side") != side:
                raise ValueError("睫毛图层侧别不匹配")
            box(lash.get("rest"), "lash.rest", images)
            if lash.get("ink") is not None:
                box(lash["ink"], "lash.ink", images)
        if eye.get("skin") is not None:
            box(eye["skin"], "lid.skin", images)


def _mouth(mouth: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    # Accept the branch actually consumed by parseAvatarModel, not all producer branches.
    selected = object_value(mouth.get("choice"), "mouth.choice")
    if selected.get("renderer") != "parametric":
        raise ValueError("不支持的 mouth.choice.renderer，仅支持 parametric")
    if mouth.get("morph") is not False or mouth.get("interior") is not None:
        raise ValueError("不支持的 mouth morph/interior 分支")
    parametric = object_value(mouth.get("parametric"), "mouth.parametric")
    articulation = object_value(mouth.get("articulation"), "mouth.articulation")
    _layer_index(mouth.get("closed"), rows, "mouth.closed")
    fit = mouth.get("fit")
    if fit is not None:
        value = object_value(fit, "mouth.fit")
        if value.get("schema") != "prelulu-mouth-rig/v1":
            raise ValueError("不支持的 mouth fit schema")
        choice(value.get("status"), {"fitted", "rejected"}, "mouth.fit.status")
        if value["status"] == "fitted":
            frame = object_value(value.get("frame"), "mouth.frame")
            vector(frame.get("originXY"), 2, "mouth.originXY")
            number(
                frame.get("angleRadians"),
                "mouth.angle",
                low=-math.pi / 4,
                high=math.pi / 4,
            )
            number(frame.get("halfSpanPx"), "mouth.halfSpan", low=6, high=256)
            for key, names in (
                ("rest", ("parting", "upperOuter", "lowerOuter")),
                ("open", ("upperInner", "lowerInner", "split")),
            ):
                section = object_value(value.get(key), key)
                for name in names:
                    vector(section.get(name), 33, name)
            vector(value["open"].get("spanU"), 2, "mouth.spanU", low=-1.5, high=1.5)
    dimensions(parametric, "mouth.parametric")
    for key in ("x", "y"):
        number(parametric.get(key), key, integer=True)
    mouth_fit(parametric.get("fit"))
    number(articulation.get("openPx"), "mouth.openPx", low=1e-9, high=16384)
    choice(articulation.get("bound"), {"face", "mouth_width"}, "mouth.bound")
    if articulation.get("reach") is not None:
        reach = object_value(articulation["reach"], "mouth.reach")
        for key in ("widenPx", "liftPx"):
            number(reach.get(key), key, low=0)
