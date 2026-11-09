"""Validate the renderer's layer and anchor data without regenerating a rig."""

from typing import Any

from .package_images import ImageInfo, image_reference
from .validation import array, choice, number, object_value, text, vector


def dimensions(value: object, label: str) -> tuple[int, int]:
    """Validate a canvas or integer image rectangle size."""
    raw = object_value(value, label)
    width, height = [
        int(number(raw.get(k), f"{label}.{k}", low=1, high=16384, integer=True))
        for k in ("w", "h")
    ]
    return width, height


def box(value: object, label: str, images: dict[str, ImageInfo]) -> dict[str, Any]:
    """Validate a baked image patch's coordinates and actual raster size."""
    raw = object_value(value, label)
    width, height = dimensions(raw, label)
    for key in ("x", "y"):
        number(raw.get(key), f"{label}.{key}", integer=True)
    image_reference(raw.get("image"), images, width, height)
    return raw


def anchors(value: object, label: str) -> None:
    """Require all anchors used by body/head and local feature deformation."""
    raw = object_value(value, label)
    for key in ("face", "mouth"):
        anchor = object_value(raw.get(key), f"{label}.{key}")
        for field in ("cx", "cy", "x0", "x1", "y0", "y1"):
            number(anchor.get(field), field)
        if anchor["x0"] >= anchor["x1"] or anchor["y0"] >= anchor["y1"]:
            raise ValueError(f"{label}.{key} 范围无效")
    for key in ("neckPivot", "bodyPivot"):
        anchor = object_value(raw.get(key), key)
        number(anchor.get("cx"), key)
        number(anchor.get("cy"), key)
    for key in ("neckTop", "neckBottom", "hairRootY"):
        number(raw.get(key), key)
    if raw["neckBottom"] <= raw["neckTop"]:
        raise ValueError("颈部锚点范围无效")
    number(raw.get("faceScale"), "faceScale", low=1e-9, high=16384)
    for side in ("L", "R"):
        if "eye" + side not in raw:
            continue
        eye = object_value(raw["eye" + side], "eye" + side)
        for field in ("x0", "x1", "y0", "y1", "icx", "icy", "closeY"):
            number(eye.get(field), field)
        if eye["x0"] >= eye["x1"] or eye["y0"] >= eye["y1"]:
            raise ValueError("眼部锚点范围无效")
        for field in ("closeX", "angleRadians"):
            if field in eye:
                number(eye[field], field)
        if "closedLid" in eye:
            lid = object_value(eye["closedLid"], "closedLid")
            for field in ("halfSpan", "tilt", "sag", "smileRise"):
                number(lid.get(field), field)
            number(lid["halfSpan"], "halfSpan", low=1e-9)


def layers(
    value: object, images: dict[str, ImageInfo], label: str
) -> list[dict[str, Any]]:
    """Validate every layer's render discriminators and referenced image."""
    rows = array(value, label, minimum=1)
    orders: set[int] = set()
    for item in rows:
        layer = box(item, label, images)
        text(layer.get("name"), "layer.name")
        if not isinstance(layer.get("source"), str) or len(layer["source"]) > 1024:
            raise ValueError("layer.source 无效")
        z = int(number(layer.get("z"), "layer.z", low=0, high=10000, integer=True))
        if z in orders:
            raise ValueError("重复图层 z")
        orders.add(z)
        number(layer.get("depth"), "layer.depth", low=-10, high=10)
        number(layer.get("opacity", 1), "layer.opacity", low=0, high=1)
        choice(layer.get("group"), {"head", "body"}, "layer.group")
        choice(layer.get("phys"), {None, "hair", "sway"}, "layer.phys")
        choice(
            layer.get("fade"),
            {None, "eyeOpen", "eyeClose", "eyeClose2", "mouthOpen", "mouthClose"},
            "layer.fade",
        )
        choice(layer.get("side"), {None, "L", "R"}, "layer.side")
        for key in ("synthetic", "unknown"):
            if key in layer and not isinstance(layer[key], bool):
                raise ValueError(f"layer.{key} 无效")
        if layer.get("strands") is not None:
            for raw in array(layer["strands"], "layer.strands"):
                strand = object_value(raw, "strand")
                for key in ("x", "tipY", "rootY"):
                    number(strand.get(key), key)
    if [layer["z"] for layer in rows] != sorted(orders):
        raise ValueError("图层顺序必须 bottom-first")
    return rows


def mouth_fit(value: object) -> None:
    """Validate the exact parametric mouth fields consumed by the bundled runtime."""
    fit = object_value(value, "mouth.fit")
    style = object_value(fit.get("style"), "mouth.style")
    for key in ("halfWidth", "lineWidth", "restCurve", "openHeight"):
        number(style.get(key), key)
    for key in ("halfWidth", "lineWidth", "openHeight"):
        number(style[key], key, low=1e-9, high=16384)
    for key in ("ink", "cavity", "tongue", "teeth"):
        vector(style.get(key), 3, key, low=0, high=255)
    origin = object_value(fit.get("origin"), "mouth.origin")
    number(origin.get("x"), "mouth.origin.x")
    number(origin.get("y"), "mouth.origin.y")
    number(fit.get("angle"), "mouth.angle")
