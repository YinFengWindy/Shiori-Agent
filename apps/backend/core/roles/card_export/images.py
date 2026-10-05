"""Portable image encoding with source metadata removed."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image, ImageOps, ImageSequence

from ..card_import.safety import validate_image

# Retained RGBA animation frames occupy at most 64 MB before encoder overhead.
MAX_DECODED_PIXELS = 16_000_000


def _check_decode_budget(image: Image.Image, *, all_frames: bool = False):
    frames = getattr(image, "n_frames", 1) if all_frames else 1
    if image.width * image.height * frames > MAX_DECODED_PIXELS:
        raise ValueError("角色素材解码总像素超过限制（最多 1600 万像素）")


def _pixels(image: Image.Image):
    pixels = ImageOps.exif_transpose(image).convert("RGBA")
    clean = Image.new("RGBA", pixels.size)
    clean.paste(pixels)
    return clean


def png_image(data: bytes) -> bytes:
    """Normalize the visible frame and strip metadata from a PNG cover."""
    validate_image(data)
    with Image.open(io.BytesIO(data)) as image:
        _check_decode_budget(image)
        output = io.BytesIO()
        _pixels(image).save(output, format="PNG")
    result = output.getvalue()
    validate_image(result)
    return result


def preview_image(data: bytes) -> str:
    """Return a bounded thumbnail of the exact exported visual."""
    with Image.open(io.BytesIO(data)) as image:
        _check_decode_budget(image)
        image = _pixels(image)
        image.thumbnail((480, 480))
        output = io.BytesIO()
        image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(
        "ascii"
    )


def portable_image(data: bytes) -> tuple[bytes, str]:
    """Preserve source format and animation while omitting private metadata."""
    image_format, _ = validate_image(data)
    extension = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}[
        image_format
    ]
    output = io.BytesIO()
    with Image.open(io.BytesIO(data)) as image:
        # Pillow reads frame-count headers without constructing decoded frame copies.
        _check_decode_budget(image, all_frames=True)
        if image_format == "JPEG":
            # Keep quantization/subsampling unless orientation needs normalization.
            if image.getexif().get(274, 1) == 1:
                image.save(output, format="JPEG", quality="keep", exif=b"", comment=b"")
            else:
                normalized = ImageOps.exif_transpose(image)
                normalized.info.clear()
                normalized.save(
                    output, format="JPEG", quality=95, exif=b"", comment=b""
                )
        else:
            default_image = image_format == "PNG" and image.info.get(
                "default_image", False
            )
            options: dict[str, Any] = {}
            # A missing GIF loop extension means play once, not infinite looping.
            if "loop" in image.info:
                options["loop"] = image.info["loop"]
            if image_format == "WEBP":
                options["lossless"] = True
            elif image_format == "GIF":
                # Frames are already composited; clear before drawing the next one.
                options.update(disposal=2, optimize=False)
            elif image_format == "PNG":
                options.update(default_image=default_image, disposal=0, blend=0)
            frames: list[Image.Image] = []
            durations: list[float] = []
            for index, frame in enumerate(ImageSequence.Iterator(image)):
                frames.append(_pixels(frame))
                # An APNG poster has no playback duration and is not an animation frame.
                if not (default_image and index == 0):
                    durations.append(float(frame.info.get("duration", 0)))
            if len(frames) > 1:
                frames[0].save(
                    output,
                    format=image_format,
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    **options,
                )
            else:
                frames[0].save(output, format=image_format, **options)
    result = output.getvalue()
    validate_image(result)
    return result, extension
