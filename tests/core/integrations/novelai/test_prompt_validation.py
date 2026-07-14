import pytest

from core.integrations.novelai.prompt_validation import validate_novelai_prompt


@pytest.mark.parametrize(
    "prompt",
    [
        "",
        "1girl, silver hair, blue eyes",
        "1girl, {silver hair}, [blurry], artist:name::1.2",
    ],
)
def test_validate_novelai_prompt_accepts_ascii_tag_syntax(prompt: str) -> None:
    validate_novelai_prompt(prompt, field_name="prompt")


@pytest.mark.parametrize("prompt", ["月光下的少女", "1girl, 青い目"])
def test_validate_novelai_prompt_rejects_non_ascii_tags(prompt: str) -> None:
    with pytest.raises(ValueError, match="prompt 仅支持英文 NovelAI tags"):
        validate_novelai_prompt(prompt, field_name="prompt")
