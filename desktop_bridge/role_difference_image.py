from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image


class RoleDifferenceImageError(ValueError):
    """Raised when a generated role difference cannot be converted to a cutout."""


def remove_edge_connected_background(source: Path, destination: Path) -> None:
    """Remove a light, edge-connected background and write a transparent PNG.

    Role-difference prompts request a plain background. The flood-fill mask keeps
    this step deterministic and dependency-free while avoiding a prompt-only
    claim that the generated asset is already transparent.
    """

    try:
        with Image.open(source) as loaded:
            image = loaded.convert("RGBA")
    except Exception as exc:
        raise RoleDifferenceImageError(f"无法读取生成图片: {source}") from exc

    width, height = image.size
    if width <= 0 or height <= 0:
        raise RoleDifferenceImageError("生成图片尺寸无效")

    pixels = image.load()
    samples = _border_samples(pixels, width, height)
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(1, height - 1):
        queue.append((0, y))
        queue.append((width - 1, y))

    removed_pixels = 0
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if visited[index]:
            continue
        visited[index] = 1
        pixel = pixels[x, y]
        if not _looks_like_background(pixel, samples):
            continue
        if pixel[3] != 0:
            pixels[x, y] = (pixel[0], pixel[1], pixel[2], 0)
            removed_pixels += 1
        if x > 0:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))

    opaque_pixels = sum(image.getchannel("A").histogram()[13:])
    if removed_pixels == 0:
        raise RoleDifferenceImageError("无法识别角色背景，未写入差分图")
    if opaque_pixels < max(32, width * height // 200):
        raise RoleDifferenceImageError("生成结果的角色主体过小，未写入差分图")

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def _border_samples(pixels, width: int, height: int) -> list[tuple[int, int, int]]:
    points = {
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (width // 2, 0),
        (width // 2, height - 1),
        (0, height // 2),
        (width - 1, height // 2),
    }
    return [pixels[x, y][:3] for x, y in points]


def _looks_like_background(
    pixel: tuple[int, int, int, int],
    samples: list[tuple[int, int, int]],
) -> bool:
    if pixel[3] <= 12:
        return True
    return any(
        sum((int(pixel[channel]) - int(sample[channel])) ** 2 for channel in range(3))
        <= 58**2
        for sample in samples
    )
