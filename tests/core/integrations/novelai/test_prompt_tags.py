from pathlib import Path

import pytest

from core.integrations.novelai.prompt_tags import PromptTagStore


def _entry(**overrides: object) -> dict[str, object]:
    return {
        "id": "rain",
        "name": "雨景",
        "enabled": True,
        "category": "atmosphere",
        "match_terms": ["雨", "rain"],
        "positive_tags": ["rainy atmosphere", "wet street"],
        "negative_tags": ["flat lighting"],
        "rating": "general",
        **overrides,
    }


def test_prompt_tag_store_upserts_and_retrieves_ranked_tags(tmp_path: Path) -> None:
    store = PromptTagStore(tmp_path)
    store.upsert(_entry())
    store.upsert(
        _entry(
            id="night",
            name="夜景",
            match_terms=["雨", "夜"],
            positive_tags=["night lighting"],
            negative_tags=[],
        )
    )

    expansion = store.expand(
        "1girl, standing, rainy atmosphere, night",
        "blurry",
        match_text="Mira 站在雨夜里",
        allow_adult=False,
    )

    assert expansion.matched_entry_ids == ["night", "rain"]
    assert "night lighting" in expansion.prompt
    assert "rainy atmosphere" in expansion.prompt
    assert "flat lighting" in expansion.negative_prompt


def test_prompt_tag_store_filters_adult_entries_without_nsfw_mode(
    tmp_path: Path,
) -> None:
    store = PromptTagStore(tmp_path)
    store.upsert(
        _entry(
            id="adult",
            name="成人",
            rating="adult",
            match_terms=["adult"],
            positive_tags=["adult tag"],
            negative_tags=[],
        )
    )

    assert store.expand(
        "1girl", "", match_text="adult scene", allow_adult=False
    ).matched_entry_ids == []
    assert store.expand(
        "1girl", "", match_text="adult scene", allow_adult=True
    ).matched_entry_ids == ["adult"]


def test_prompt_tag_store_rejects_invalid_entries(tmp_path: Path) -> None:
    store = PromptTagStore(tmp_path)

    with pytest.raises(ValueError, match="positive_tags"):
        store.upsert(_entry(positive_tags=[]))
