"""Shared diagnostic preview and multimodal text formatting."""

from plugins.status_commands.backend import formatting


def test_multimodal_preview_keeps_text_without_image_payload(backend):
    value = [
        {"type": "text", "text": " first "},
        {"type": "image_url", "image_url": "secret"},
        {"type": "text", "text": "second"},
    ]
    assert formatting.content_to_text(value) == "first\nsecond"
