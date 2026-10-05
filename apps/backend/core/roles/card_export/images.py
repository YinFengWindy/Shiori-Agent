"""Portable image encoding with source metadata removed."""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps, ImageSequence

from ..card_import.safety import validate_image


def _pixels(image: Image.Image):
    pixels = ImageOps.exif_transpose(image).convert("RGBA")
    clean = Image.new("RGBA", pixels.size)
    clean.paste(pixels)
    return clean


def png_image(data: bytes) -> bytes:
    """Normalize the visible frame and strip metadata from a PNG cover."""
    validate_image(data)
    with Image.open(io.BytesIO(data)) as image:
        output = io.BytesIO()
        _pixels(image).save(output, format="PNG")
    result = output.getvalue()
    validate_image(result)
    return result


def preview_image(data: bytes) -> str:
    """Return a bounded thumbnail of the exact exported visual."""
    with Image.open(io.BytesIO(data)) as image:
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
        if image_format == "JPEG":
            # Keep quantization/subsampling unless orientation needs normalization.
            if image.getexif().get(274, 1) == 1:
                image.save(output, format="JPEG", quality="keep", exif=b"", comment=b"")
            else:
                ImageOps.exif_transpose(image).save(output, format="JPEG", quality=95)
        else:
            loop = image.info.get("loop", 0)
            frames: list[Image.Image] = []
            durations: list[int] = []
            for frame in ImageSequence.Iterator(image):
                frames.append(_pixels(frame))
                durations.append(int(frame.info.get("duration", 100)))
            options = {"lossless": True} if image_format == "WEBP" else {}
            if len(frames) > 1:
                frames[0].save(
                    output,
                    format=image_format,
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=loop,
                    **options,
                )
            else:
                frames[0].save(output, format=image_format, **options)
    result = output.getvalue()
    validate_image(result)
    return result, extension
