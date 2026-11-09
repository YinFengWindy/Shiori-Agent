"""Cross-document validation of the supported immutable Prelulu avatar package."""

from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Any

from .bake_schema import validate_bake
from .package_archive import PackageManifest, read_manifest, regular_path, verify_files
from .package_images import ImageInfo, declared_image, validate_images
from .rig_schema import anchors, dimensions, layers
from .validation import (
    array,
    digest,
    number,
    object_value,
    package_path,
    read_json,
    text,
    vector,
)


@dataclass(frozen=True)
class ValidatedPackage:
    """Verified metadata plus the unchanged documents sent to the renderer."""

    manifest: PackageManifest
    binding: dict[str, Any]
    rig: dict[str, Any]
    baked: dict[str, Any]
    images: dict[str, ImageInfo]

    @property
    def model_id(self) -> str:
        """Full manifest hash is the local immutable model identity."""
        return self.manifest.sha256

    @property
    def display_name(self) -> str:
        """Use only package-authored titles, falling back to its character identity."""
        document = self.manifest.document
        return next(
            (
                document[key]
                for key in ("display_name", "displayName", "name")
                if key in document
            ),
            document["character"],
        )

    @property
    def body(self) -> dict[str, int]:
        """Scale display bounds without changing the model's source coordinate system."""
        width, height = dimensions(self.rig["rig"]["canvas"], "canvas")
        scale = 280 / max(width, height)
        return {
            "width": max(1, round(width * scale)),
            "height": max(1, round(height * scale)),
        }


def validate_package(
    root: Path, manifest: PackageManifest | None = None
) -> ValidatedPackage:
    """Verify bytes, references and frozen bake structures before exposing a model."""
    manifest = manifest or read_manifest(root)
    verify_files(root, manifest)
    binding = read_json(regular_path(root, "binding.json"))
    rig = read_json(regular_path(root, "rig/rig.json"))
    baked = read_json(regular_path(root, "rig/baked.json"))
    read_json(regular_path(root, "review.json"))
    images = validate_images(root, manifest)
    if (
        binding.get("schema") != "prelulu-avatar-binding/v1"
        or rig.get("schema") != "prelulu-rig-bundle/v1"
    ):
        raise ValueError("不支持的 binding/rig schema")
    _binding(binding, images)
    _rig(rig, manifest, root, images)
    canvas = rig["rig"]["canvas"]
    if [canvas["w"], canvas["h"]] != [
        binding["canvas"]["width"],
        binding["canvas"]["height"],
    ]:
        raise ValueError("binding 与 rig 画布不一致")
    validate_bake(baked, images)
    _inputs(manifest, binding, rig, baked)
    _all_references(binding, manifest.files, "")
    _all_references(rig, manifest.files, "rig/")
    _all_references(baked, manifest.files, "rig/")
    return ValidatedPackage(manifest, binding, rig, baked, images)


def _binding(binding: dict[str, Any], images: dict[str, ImageInfo]) -> None:
    canvas = object_value(binding.get("canvas"), "binding.canvas")
    width = number(canvas.get("width"), "canvas.width", low=2, high=16384, integer=True)
    height = number(
        canvas.get("height"), "canvas.height", low=2, high=16384, integer=True
    )
    if (
        binding.get("coordinates")
        != "canvas top-left pixels; bboxXYXY right/bottom exclusive"
        or binding.get("layerOrder") != "bottom-first"
    ):
        raise ValueError("不支持的 binding 坐标约定")
    seen: set[str] = set()
    orders = []
    for raw in array(binding.get("layers"), "binding.layers", minimum=1):
        item = object_value(raw, "binding.layer")
        identifier = text(item.get("id"), "layer.id")
        if identifier in seen:
            raise ValueError("重复 binding layer id")
        seen.add(identifier)
        text(item.get("displayName"), "layer.displayName")
        text(item.get("role"), "layer.role")
        text(item.get("roleSource"), "layer.roleSource")
        image = declared_image(item.get("file"), images)
        x0, y0, x1, y1 = vector(
            item.get("bboxXYXY"), 4, "layer.bbox", low=0, high=16384, integer=True
        )
        if (
            not x0 < x1 <= width
            or not y0 < y1 <= height
            or (x1 - x0, y1 - y0) != (image.width, image.height)
            or [item.get("width"), item.get("height")] != [image.width, image.height]
        ):
            raise ValueError("binding 图层边界与图片不一致")
        number(item.get("opacity"), "layer.opacity", low=0, high=1)
        if not isinstance(item.get("visible"), bool):
            raise ValueError("binding 图层 visible 无效")
        orders.append(
            int(number(item.get("z"), "layer.z", low=0, high=10000, integer=True))
        )
    if len(set(orders)) != len(orders) or orders != sorted(orders):
        raise ValueError("binding 图层顺序无效")
    registration = object_value(binding.get("sourceRegistration"), "sourceRegistration")
    if registration.get("kind") != "integer-center-square-pad-then-resize":
        raise ValueError("不支持的源图配准")
    source = declared_image("source.png", images)
    source_size = vector(
        registration.get("sourceSize"), 2, "sourceSize", low=1, high=16384, integer=True
    )
    square = vector(
        registration.get("squareSize"), 2, "squareSize", low=1, high=16384, integer=True
    )
    padding = vector(
        registration.get("paddingLTRB"), 4, "padding", low=0, high=16384, integer=True
    )
    matrix = [
        vector(row, 3, "registration matrix")
        for row in array(registration.get("matrix3x3"), "matrix", minimum=3, maximum=3)
    ]
    if (
        source_size != [source.width, source.height]
        or square[0] != square[1]
        or [
            source_size[0] + padding[0] + padding[2],
            source_size[1] + padding[1] + padding[3],
        ]
        != square
    ):
        raise ValueError("源图配准尺寸不一致")
    expected = [
        [width / square[0], 0, padding[0] * width / square[0]],
        [0, height / square[1], padding[1] * height / square[1]],
        [0, 0, 1],
    ]
    if any(
        abs(matrix[y][x] - expected[y][x]) > 1e-8 for y in range(3) for x in range(3)
    ):
        raise ValueError("源图配准矩阵不一致")
    mouth = object_value(binding.get("mouth"), "binding.mouth")
    declared_image(mouth.get("openFile"), images)
    x, y, w, h = vector(mouth.get("rectXYWH"), 4, "mouth.rect")
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
        raise ValueError("嘴部放置范围无效")
    number(mouth.get("maxWidth"), "mouth.maxWidth", low=1e-9)
    if (
        mouth.get("drive") != "amplitude-only"
        or mouth.get("phonemes") is not False
        or mouth.get("visemes") is not False
    ):
        raise ValueError("不支持的口型驱动")
    deformation = object_value(mouth.get("deformation"), "mouth.deformation")
    if deformation.get("schema") != "lip-local/v1":
        raise ValueError("不支持的嘴部变形 schema")
    vector(deformation.get("anchorXY"), 2, "mouth.anchorXY")
    number(deformation.get("angleRadians"), "mouth.angleRadians")


def _rig(
    rig: dict[str, Any],
    manifest: PackageManifest,
    root: Path,
    images: dict[str, ImageInfo],
) -> None:
    if not re.fullmatch(
        r"rig-v1-[0-9a-f]{16}", text(rig.get("version"), "rig.version")
    ):
        raise ValueError("rig.version 无效")
    raw = object_value(rig.get("rig"), "rig")
    canvas = dimensions(raw.get("canvas"), "rig.canvas")
    if canvas[0] * canvas[1] > 16 * 1024 * 1024:
        raise ValueError("rig 画布超过像素限制")
    layers(raw.get("layers"), images, "rig.layers")
    anchors(raw.get("anchors"), "rig.anchors")
    for warning in array(raw.get("warnings"), "rig.warnings", maximum=2000):
        text(warning, "warning", 4096)
    synth = object_value(raw.get("synth"), "rig.synth")
    if any(not isinstance(synth.get(k), bool) for k in ("eye", "mouth")):
        raise ValueError("rig.synth 无效")
    psd = object_value(rig.get("psd"), "rig.psd")
    record = manifest.files["editable/character.psd"]
    if psd.get("sha256") != record["sha256"] or psd.get("bytes") != record["bytes"]:
        raise ValueError("rig PSD 身份不一致")
    with regular_path(root, "editable/character.psd").open("rb") as stream:
        header = stream.read(26)
    if (
        len(header) != 26
        or header[:6] != b"8BPS\x00\x01"
        or struct.unpack(">II", header[14:22]) != (canvas[1], canvas[0])
        or header[22:26] != b"\x00\x08\x00\x03"
    ):
        raise ValueError("PSD 头信息与画布不一致")
    builder = object_value(rig.get("builder"), "rig.builder")
    upstream = object_value(builder.get("upstream"), "rig.upstream")
    if not re.fullmatch(
        r"https://github\.com/[\w.-]+/[\w.-]+",
        text(upstream.get("repository"), "repository"),
    ) or not re.fullmatch(r"[0-9a-f]{40}", text(upstream.get("commit"), "commit")):
        raise ValueError("rig 构建来源无效")
    for value in object_value(builder.get("sources"), "rig.sources").values():
        digest(value, "rig source")


def _inputs(
    manifest: PackageManifest,
    binding: dict[str, Any],
    rig: dict[str, Any],
    bake: dict[str, Any],
) -> None:
    inputs = object_value(bake.get("inputs"), "baked.inputs")
    rig_inputs = object_value(inputs.get("rig"), "baked.inputs.rig")
    if (
        rig_inputs.get("version") != rig["version"]
        or rig_inputs.get("psd") != rig["psd"]["sha256"]
    ):
        raise ValueError("baked 与 rig 版本不一致")
    for key, path in (
        ("binding", "binding.json"),
        ("source", "source.png"),
        ("openMouth", binding["mouth"]["openFile"]),
    ):
        if inputs.get(key) != manifest.files[path]["sha256"]:
            raise ValueError(f"baked {key} 输入哈希不一致")
    profile = object_value(inputs.get("profile"), "baked.profile")
    if any(
        not isinstance(profile.get(k), bool)
        for k in ("eyeAlignment", "headAttachments")
    ):
        raise ValueError("baked.profile 无效")
    for value in object_value(
        manifest.document.get("inputHashes"), "inputHashes"
    ).values():
        digest(value, "inputHashes")
    capabilities = object_value(manifest.document.get("capabilities"), "capabilities")
    if (
        capabilities.get("cubism") is not False
        or capabilities.get("amplitudeOnly") is not True
        or capabilities.get("visemes") is not False
    ):
        raise ValueError("形象包能力不受支持")


def _all_references(value: object, files: dict, prefix: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"file", "openFile"}:
                name = prefix + package_path(item)
                if name not in files:
                    raise ValueError(f"形象包引用缺失: {name}")
            else:
                _all_references(item, files, prefix)
    elif isinstance(value, list):
        for item in value:
            _all_references(item, files, prefix)
