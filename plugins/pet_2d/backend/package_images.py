"""Decode bounded raster payloads once and validate every runtime image reference."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import warnings

from PIL import Image

from .package_archive import PackageManifest, regular_path
from .validation import digest, object_value, package_path, vector

MAX_IMAGE_PIXELS = 16 * 1024 * 1024
MAX_TOTAL_PIXELS = 64 * 1024 * 1024


@dataclass(frozen=True)
class ImageInfo:
    """Decoded dimensions and exact RGBA digest, without retaining decoded pixels."""

    width: int
    height: int
    rgba_sha256: str


def validate_images(root: Path, manifest: PackageManifest) -> dict[str, ImageInfo]:
    """Bound aggregate decoded memory and verify PNG/WebP metadata against pixels."""
    images = {}
    total = 0
    for relative, entry in manifest.files.items():
        suffix = Path(relative).suffix.lower()
        if suffix not in {".png", ".webp"}:
            continue
        path = regular_path(root, relative)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    width, height = image.size
                    pixels = width * height
                    total += pixels
                    if (
                        max(width, height) > 16384
                        or pixels > MAX_IMAGE_PIXELS
                        or total > MAX_TOTAL_PIXELS
                    ):
                        raise ValueError("形象包图片解码尺寸超过限制")
                    if (
                        image.format != {".png": "PNG", ".webp": "WEBP"}[suffix]
                        or getattr(image, "n_frames", 1) != 1
                    ):
                        raise ValueError("形象包图片格式无效")
                    declared = vector(
                        entry.get("dimensions"),
                        2,
                        relative,
                        low=1,
                        high=16384,
                        integer=True,
                    )
                    if declared != [width, height] or entry.get("mode") != image.mode:
                        raise ValueError(f"形象包图片尺寸或模式不一致: {relative}")
                    rgba = hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
                    images[relative] = ImageInfo(width, height, rgba)
        except (
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            raise ValueError(f"形象包图片无法解码: {relative}") from error
    return images


def image_reference(
    value: object, images: dict[str, ImageInfo], width: int, height: int
) -> None:
    """Check a rig-relative reference, decoded dimensions and exact RGBA identity."""
    ref = object_value(value, "image")
    relative = package_path(ref.get("file"))
    if not relative.startswith(("layers/", "baked/")) or not relative.endswith(".webp"):
        raise ValueError("rig 图片引用无效")
    image = images.get("rig/" + relative)
    if image is None or (image.width, image.height) != (width, height):
        raise ValueError(f"rig 图片缺失或尺寸不一致: {relative}")
    if digest(ref.get("rgbaSha256"), relative) != image.rgba_sha256:
        raise ValueError(f"rig 图片 RGBA 校验失败: {relative}")


def declared_image(relative: object, images: dict[str, ImageInfo]) -> ImageInfo:
    """Require a package-relative raster reference declared by the manifest."""
    name = package_path(relative)
    if name not in images:
        raise ValueError(f"形象包图片引用缺失: {name}")
    return images[name]
