"""NovelAI configuration through the real plugin settings channel."""


def test_config_schema_labels_every_field_for_the_settings_form():
    from plugins.novelai.backend.config import NovelAIConfig

    properties = NovelAIConfig.model_json_schema()["properties"]
    for key, item in properties.items():
        # pydantic's generated fallback title ("Nsfw Model") must never surface.
        assert item["title"] != key.replace("_", " ").title(), key
    assert properties["max_steps"]["unit"] == "步"
