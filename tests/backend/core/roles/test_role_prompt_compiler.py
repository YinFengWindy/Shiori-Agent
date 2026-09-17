from core.roles.profile_models import (
    RoleCharacterDefinition,
    RoleKnowledgeEntry,
    RoleProfile,
)
from core.roles.role_prompt_compiler import RolePromptCompiler
from core.roles import RoleStore


def test_compiler_uses_stable_profile_order_and_mood_contract() -> None:
    profile = RoleProfile(
        character=RoleCharacterDefinition(
            profile="资料",
            personality="性格",
            behavior_rules="规则",
            response_constraints="回复约束",
        )
    )
    entry = RoleKnowledgeEntry(content="知识")
    result = RolePromptCompiler().compile(
        profile,
        [entry],
        {"mood_catalog": ["平静"], "default_mood": "平静"},
    )

    assert result.content.index("[role_profile]") < result.content.index(
        "[role_personality]"
    )
    assert result.content.index("[role_personality]") < result.content.index(
        "[role_behavior_rules]"
    )
    assert result.content.index("[role_behavior_rules]") < result.content.index(
        "[role_knowledge]"
    )
    assert result.content.index("[role_knowledge]") < result.content.index(
        "[role_response_constraints]"
    )
    assert result.content.index("[role_response_constraints]") < result.content.index(
        "Mood Output Contract"
    )
    assert "Mood Output Contract" in result.content


def test_compiler_expands_identity_in_all_runtime_blocks_without_source_metadata() -> (
    None
):
    profile = RoleProfile.from_dict(
        {
            "character": {
                "nickname": "小栞",
                "profile": "{{char}}的资料",
                "personality": "{{char}}的性格",
                "behavior_rules": "尊重{{user}}",
                "response_constraints": "回应{{user}}",
            },
            "import_provenance": {"format": "json", "creator": "不应注入的作者"},
        }
    )
    result = RolePromptCompiler().compile(
        profile,
        [
            RoleKnowledgeEntry(
                content="{{char}}认识{{user}}",
                raw_source={"extension": "不应注入的原始数据"},
            )
        ],
        role_name="Shiori",
        user_name="小明",
    )

    assert "小栞的资料" in result.content
    assert "小栞的性格" in result.content
    assert "尊重小明" in result.content
    assert "回应小明" in result.content
    assert "小栞认识小明" in result.content
    assert "不应注入" not in result.content


def test_sparse_named_role_has_runtime_identity_and_identity_updates(tmp_path):
    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira", role_id="mira", system_prompt="旧兼容字段", profile={}
    )

    assert RolePromptCompiler().compile(role).content == "[role_identity]\nMira"
    renamed = store.update_role(
        "mira",
        name="Shiori",
        profile={"character": {"nickname": "小栞", "profile": "{{char}}的资料"}},
    )
    content = RolePromptCompiler().compile(renamed).content
    assert content.startswith("[role_identity]\nShiori\n\n[role_profile]")
    assert "小栞的资料" in content
    assert "Mira" not in content


def test_formal_reply_contract_requires_explicit_runtime_context():
    profile = RoleProfile(character=RoleCharacterDefinition(profile="角色资料"))
    assert "Mood Output Contract" not in RolePromptCompiler().compile(profile).content
    content = RolePromptCompiler().compile(profile, runtime_context={}).content
    assert "Mood Output Contract" in content
    # Content is plain dialogue now, not JSON: the contract must say so instead
    # of documenting a `{content, mood, thought}` JSON structure (issue #303).
    assert "JSON" in content
    assert '"content"' not in content
    assert "平静" in content
