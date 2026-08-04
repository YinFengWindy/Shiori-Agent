from pathlib import Path

from PIL import Image

from desktop_bridge.role_difference_image import remove_edge_connected_background


def test_remove_edge_connected_background_keeps_subject_opaque(tmp_path: Path) -> None:
    source = tmp_path / "generated.png"
    destination = tmp_path / "cutout.png"
    image = Image.new("RGB", (20, 20), "white")
    for x in range(6, 14):
        for y in range(4, 17):
            image.putpixel((x, y), (210, 80, 110))
    image.save(source)

    remove_edge_connected_background(source, destination)

    with Image.open(destination) as cutout:
        assert cutout.mode == "RGBA"
        assert cutout.getpixel((0, 0))[3] == 0
        assert cutout.getpixel((10, 10))[3] == 255
