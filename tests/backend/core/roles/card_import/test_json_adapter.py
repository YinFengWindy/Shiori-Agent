from core.roles.card_import.json_adapter import adapt_json


def test_import_keeps_constraints_attribution_and_discards_lorebook():
    book = {
        "scan_depth": 7,
        "recursive_scanning": True,
        "entries": [
            {
                "content": "secret",
                "keys": ["rain"],
                "use_regex": True,
                "extensions": {"weight": 2},
            }
        ],
    }
    preview = adapt_json(
        {
            "spec": "chara_card_v3",
            "data": {
                "name": "Name",
                "nickname": "Nick",
                "system_prompt": "{{char}} sees {{user}} and {{unknown}}",
                "post_history_instructions": "Stay brief",
                "creator": "Author",
                "tags": ["Fantasy"],
                "source": ["card-id"],
                "creation_date": 1,
                "modification_date": 2,
                "character_book": book,
            },
        }
    )
    assert preview.profile["character"]["nickname"] == "Nick"
    assert (
        preview.profile["character"]["behavior_rules"]
        == "{{char}} sees {{user}} and {{unknown}}"
    )
    assert preview.profile["character"]["response_constraints"] == "Stay brief"
    assert "knowledge_base" not in preview.profile
    assert "character_book" in preview.report.discarded_fields
    assert "character_book" not in preview.report.adapted_fields
    assert preview.report.unsupported_macros == ("{{unknown}}",)
    assert preview.provenance.creator == "Author"
    assert preview.provenance.tags == ["Fantasy"]
    assert preview.provenance.source == ["card-id"]
    assert preview.provenance.created_at == 1
    assert preview.provenance.updated_at == 2
    assert preview.provenance.imported_at
