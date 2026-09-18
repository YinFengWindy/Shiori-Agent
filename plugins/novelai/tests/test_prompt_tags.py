from pathlib import Path
import json

import pytest

from plugins.novelai.backend.prompt_tags import PromptTagStore


def test_constructor_adopts_legacy_reference_before_first_read(tmp_path):
    source = tmp_path / "private_runtime/imports/image.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reference")
    old = tmp_path / "private_runtime/novelai/prompt_tags.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps([_entry(image_path=str(source))]), encoding="utf-8")
    store = PromptTagStore(tmp_path)
    source.unlink()
    assert Path(store.list_entries()[0].image_path).read_bytes() == b"reference"


def test_missing_historical_reference_keeps_tags_usable_and_valid_images_owned(
    tmp_path, monkeypatch
):
    source = tmp_path / "private_runtime/imports/image.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reference")
    missing = "private_runtime/imports/deleted.png"
    old = tmp_path / "private_runtime/novelai/prompt_tags.json"
    old.parent.mkdir(parents=True)
    old.write_text(
        json.dumps(
            [
                _entry(image_path=missing),
                _entry(id="available", name="有图", image_path=str(source)),
            ]
        ),
        encoding="utf-8",
    )

    store = PromptTagStore(tmp_path)
    source.unlink()

    def unexpected_rewrite(_entries):
        raise AssertionError("unchanged historical references must not rewrite storage")

    def unexpected_copy(*_args):
        raise AssertionError("owned references must not be copied again")

    monkeypatch.setattr(store, "_write", unexpected_rewrite)
    monkeypatch.setattr(
        "plugins.novelai.backend.prompt_tags.copy_owned_asset", unexpected_copy
    )
    entries = {entry.id: entry for entry in store.list_entries()}
    assert entries["rain"].image_path == missing
    assert Path(entries["available"].image_path).read_bytes() == b"reference"
    assert (
        "rain"
        in store.expand(
            "1girl", "", match_text="雨", allow_adult=False
        ).matched_entry_ids
    )


def test_upsert_rejects_explicit_missing_reference_without_changing_catalog(tmp_path):
    store = PromptTagStore(tmp_path)
    saved = store.upsert(_entry())
    with pytest.raises(FileNotFoundError):
        store.upsert(_entry(image_path="private_runtime/imports/deleted.png"))
    assert store.list_entries() == [saved]


def test_historical_reference_copy_failure_is_not_treated_as_missing(
    tmp_path, monkeypatch
):
    source = tmp_path / "reference.png"
    source.write_bytes(b"reference")
    old = tmp_path / "private_runtime/novelai/prompt_tags.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps([_entry(image_path=str(source))]), encoding="utf-8")

    def permission_denied(*_args):
        raise PermissionError("asset directory is read-only")

    monkeypatch.setattr(
        "plugins.novelai.backend.prompt_tags.copy_owned_asset", permission_denied
    )
    with pytest.raises(PermissionError, match="read-only"):
        PromptTagStore(tmp_path)
    assert source.read_bytes() == b"reference"


def test_invalid_catalog_and_upsert_do_not_copy_reference_assets(tmp_path):
    source = tmp_path / "input.png"
    source.write_bytes(b"reference")
    store = PromptTagStore(tmp_path)
    with pytest.raises(ValueError, match="positive_tags"):
        store.upsert(_entry(image_path=str(source), positive_tags=[]))
    assert not (store._root / "references").exists()
    store._path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps([_entry(image_path=str(source))] * 2)
    store._path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="不能重复"):
        PromptTagStore(tmp_path)
    assert store._path.read_text(encoding="utf-8") == content
    assert not (store._root / "references").exists()


def test_reference_image_is_owned_copy_and_shared_import_remains(tmp_path):
    source = tmp_path / "private_runtime/imports/image.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reference")
    store = PromptTagStore(tmp_path)
    entry = store.upsert(_entry(image_path=str(source)))
    assert entry.image_path != str(source)
    assert source.is_file()
    source.unlink()
    assert Path(store.list_entries()[0].image_path).read_bytes() == b"reference"


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

    assert (
        store.expand(
            "1girl", "", match_text="adult scene", allow_adult=False
        ).matched_entry_ids
        == []
    )
    assert store.expand(
        "1girl", "", match_text="adult scene", allow_adult=True
    ).matched_entry_ids == ["adult"]


def test_prompt_tag_store_rejects_invalid_entries(tmp_path: Path) -> None:
    store = PromptTagStore(tmp_path)

    with pytest.raises(ValueError, match="positive_tags"):
        store.upsert(_entry(positive_tags=[]))
