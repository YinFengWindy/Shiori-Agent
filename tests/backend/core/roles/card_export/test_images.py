import io

import pytest
from PIL import Image, ImageOps

from core.roles.card_export import images


def _moving_gif(*, loop=None):
    frames = []
    for position in (0, 8):
        frame = Image.new("P", (16, 8), 0)
        frame.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        frame.paste(1, (position, 0, position + 8, 8))
        frames.append(frame)
    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[120, 240],
        disposal=2,
        transparency=0,
        optimize=False,
        **({"loop": loop} if loop is not None else {}),
    )
    return output.getvalue()


def _decoded_frames(data):
    with Image.open(io.BytesIO(data)) as image:
        result = []
        for index in range(image.n_frames):
            image.seek(index)
            result.append((image.convert("RGBA").tobytes(), image.info.get("duration")))
        return result


def test_gif_clears_previous_transparent_frames_instead_of_leaving_trails():
    source = _moving_gif(loop=3)
    exported, extension = images.portable_image(source)
    assert extension == "gif"
    assert _decoded_frames(exported) == _decoded_frames(source)
    with Image.open(io.BytesIO(exported)) as image:
        assert image.info["loop"] == 3
        image.seek(1)
        assert image.convert("RGBA").getpixel((0, 0)) == (0, 0, 0, 0)
        assert image.convert("RGBA").getpixel((8, 0)) == (255, 0, 0, 255)


def test_gif_without_loop_extension_remains_a_single_play_animation():
    source = _moving_gif()
    exported, _ = images.portable_image(source)
    with Image.open(io.BytesIO(exported)) as image:
        assert image.n_frames == 2
        assert "loop" not in image.info


@pytest.mark.parametrize("orientation", [1, 6])
def test_jpeg_removes_private_metadata_and_applies_orientation(orientation):
    source = Image.new("RGB", (32, 16), "red")
    source.paste("blue", (16, 0, 32, 16))
    exif = Image.Exif()
    exif[274] = orientation
    exif[270] = "Private description"
    encoded = io.BytesIO()
    source.save(
        encoded,
        format="JPEG",
        quality=95,
        exif=exif,
        comment=b"PRIVATE local path C:/Users/user/secret",
    )
    exported, extension = images.portable_image(encoded.getvalue())
    assert extension == "jpg"
    with Image.open(io.BytesIO(exported)) as image:
        assert not image.getexif()
        assert not image.info.get("comment")
        assert image.size == ((16, 32) if orientation == 6 else (32, 16))
        with Image.open(io.BytesIO(encoded.getvalue())) as original:
            expected = ImageOps.exif_transpose(original)
            for point in ((4, 4), (image.width - 5, image.height - 5)):
                actual_pixel = image.convert("RGB").getpixel(point)
                expected_pixel = expected.convert("RGB").getpixel(point)
                assert all(
                    abs(a - b) <= 8 for a, b in zip(actual_pixel, expected_pixel)
                )


def test_apng_keeps_its_static_poster_out_of_animation_timing():
    poster, red, blue = [
        Image.new("RGBA", (12, 8), color) for color in ("green", "red", "blue")
    ]
    source = io.BytesIO()
    poster.save(
        source,
        format="PNG",
        save_all=True,
        default_image=True,
        append_images=[red, blue],
        duration=[120, 240],
        loop=4,
    )
    exported, extension = images.portable_image(source.getvalue())
    assert extension == "png"
    assert _decoded_frames(exported) == _decoded_frames(source.getvalue())
    with Image.open(io.BytesIO(exported)) as image:
        assert image.n_frames == 3
        assert image.info["default_image"] is True
        assert "duration" not in image.info
        assert image.info["loop"] == 4
        image.seek(1)
        assert image.info["duration"] == 120
        image.seek(2)
        assert image.info["duration"] == 240


def test_oversized_animation_fails_before_pixel_decoding(monkeypatch):
    source = _moving_gif()
    monkeypatch.setattr(images, "MAX_DECODED_PIXELS", 200, raising=False)

    def forbidden_decode(*_args, **_kwargs):
        pytest.fail("pixel decoding must not begin before the resource check")

    monkeypatch.setattr(Image.Image, "load", forbidden_decode)
    with pytest.raises(ValueError, match="解码.*限制"):
        images.portable_image(source)
