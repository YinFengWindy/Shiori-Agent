"""Director contract and the provider-backed implementation."""

from __future__ import annotations

import json
from typing import Any, Protocol

from .errors import StoryInvalidOutputError, StoryProviderUnavailableError
from .models import DirectorDraft, StoryBeatDraft, StoryContext, StoryScene, has_chinese_text


class StoryDirector(Protocol):
    """Generate an uncommitted Story draft from a constrained context."""

    async def generate(
        self, *, context: StoryContext, input_text: str, opening: bool
    ) -> DirectorDraft:
        """Return no more than the configured Story beat budget."""


class ProviderStoryDirector:
    """Use the existing LLM provider without coupling Story to AgentLoop sessions."""

    def __init__(self, *, provider: Any | None, model: str) -> None:
        self._provider = provider
        self._model = model.strip()

    async def generate(
        self, *, context: StoryContext, input_text: str, opening: bool
    ) -> DirectorDraft:
        """Request one strict JSON draft from the configured LLM provider."""

        if self._provider is None or not self._model:
            raise StoryProviderUnavailableError("Story Director 尚未配置 provider")
        response = await self._provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": self._system_prompt(),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        self._request_payload(context, input_text, opening),
                        ensure_ascii=False,
                    ),
                },
            ],
            tools=[],
            model=self._model,
            max_tokens=1600,
            disable_thinking=True,
        )
        return self._parse(response.content)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是视觉小说 Story Director。只输出 JSON，不要 Markdown。"
            "输出格式为 {\"beats\":[{\"text\":string,\"kind\":\"dialogue|action|narration\","
            "\"speaker\":string|null,\"time_band\":\"清晨|上午|下午|夜晚|深夜\"|null,"
            "\"fact_changes\":[]}],\"stop_reason\":\"awaiting_player\","
            "\"current_scene\":{\"key\":string,\"name\":string,\"character_ids\":[string]},"
            "\"visual_type\":\"scene|character\",\"visual_prompt\":string}。"
            "一次最多 3 个 beat，所有 text 合计最多 1200 个中文字符，单个 beat 最多 400 字符。"
            "故事日期由 story.story_date 提供且不能修改；剧情时间只使用清晨、上午、下午、夜晚、深夜五档。"
            "只有剧情明确进入另一个时段时才填写 time_band，否则必须填写 null。"
            "每个 dialogue 都是正式角色的台词，speaker 必须精确填写 role.name；"
            "绝不能写角色、正式角色、女主等泛称，也不生成玩家的 dialogue。"
            "current_scene 必须描述这次剧情提交后的当前场景。key 使用稳定简短标识，name 使用简洁中文场景名；"
            "场景未变化时沿用 current_scene.key 和 current_scene.name，切换场景时生成新 key 和中文 name。"
            "character_ids 只填写当前场景实际在场者；正式角色使用 role.id，玩家使用 player。"
            "不在当前场景的角色绝不能加入 character_ids。"
            "opening 模式的 visual_type 必须是 scene；普通场景视觉使用 scene，"
            "scene 只描述环境空镜，绝对不能出现人物；需要人物出现在画面中的重要视觉节点使用 character。"
            "character 可以包含正式角色和玩家：如果剧情明确描述玩家，visual_prompt 必须同时描述正式角色与玩家，"
            "且只能出现这两个明确人物；如果剧情没有玩家，才只描述正式角色。不得凭空增加人物、复制角色或群像。"
            "只有需要视觉演出的节点才填写 visual_prompt；visual_prompt 必须是可以直接提交给 NovelAI 的完整正向提示词，"
            "使用逗号分隔的 NovelAI V4.5 标签，不要中文、自然语言句子、文字或 logo；只描述当前视觉场景，不添加无关背景要求。"
            "双人画面使用 1girl, 1boy, duo 等人数标签；强调只用 {tag}，不能使用 :1.2 数字权重。"
            "玩家出镜时，必须把 player_profile.appearance 转换为对应的英文 V4.5 外观标签写入 visual_prompt，"
            "不能用玩家昵称或身份代替外观。"
            "正式角色对玩家执行动作时，角色必须是动作主语、玩家必须是接受者；例如角色喂玩家使用 "
            "{girl feeding boy}, {girl holding spoon}, boy receiving food，禁止写成玩家喂角色。"
            "普通非视觉节点填写空字符串。"
            "只描述当前角色可知的内容，不能泄露隐藏连续性或来源。"
        )

    @staticmethod
    def _request_payload(
        context: StoryContext, input_text: str, opening: bool
    ) -> dict[str, Any]:
        role = context.role_snapshot
        runtime_snapshot = context.segment.get("runtimeSnapshot") or {}
        return {
            "mode": "opening" if opening else "player_input",
            "story": {
                "title": context.story["title"],
                "background": context.story["background"],
                "story_date": context.segment["storyDate"],
                "time_band": context.segment["timeBand"],
                "current_scene": runtime_snapshot.get("current_scene"),
            },
            "role": {
                "id": role.get("id"),
                "name": role.get("name"),
                "description": role.get("description"),
                "system_prompt": role.get("system_prompt"),
                "background": role.get("background"),
            },
            "player_profile": context.player_profile,
            "recent_turns": list(context.recent_turns),
            "recent_beats": list(context.recent_beats),
            "context_summary": context.context_summary,
            "input": input_text,
        }

    @staticmethod
    def _parse(content: object) -> DirectorDraft:
        raw = str(content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise StoryInvalidOutputError("Director 返回的不是 JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("beats"), list):
            raise StoryInvalidOutputError("Director 缺少 beats")
        beats: list[StoryBeatDraft] = []
        for item in payload["beats"]:
            if not isinstance(item, dict):
                raise StoryInvalidOutputError("Director beat 格式无效")
            fact_changes = item.get("fact_changes") or []
            if not isinstance(fact_changes, list):
                raise StoryInvalidOutputError("fact_changes 必须是数组")
            raw_time_band = item.get("time_band")
            time_band = str(raw_time_band).strip() if raw_time_band is not None else None
            beats.append(
                StoryBeatDraft(
                    text=str(item.get("text") or ""),
                    kind=str(item.get("kind") or "narration"),
                    speaker=(
                        str(item["speaker"]).strip()
                        if item.get("speaker") is not None
                        else None
                    ),
                    time_band=time_band or None,
                    fact_changes=tuple(
                        change for change in fact_changes if isinstance(change, dict)
                    ),
                )
            )
        raw_visual_type = str(payload.get("visual_type") or "scene").strip()
        if raw_visual_type not in {"scene", "character"}:
            raise StoryInvalidOutputError("Director visual_type 无效")
        raw_current_scene = payload.get("current_scene")
        if not isinstance(raw_current_scene, dict):
            raise StoryInvalidOutputError("Director 缺少 current_scene")
        scene_key = str(raw_current_scene.get("key") or "").strip()
        scene_name = str(raw_current_scene.get("name") or "").strip()
        raw_character_ids = raw_current_scene.get("character_ids")
        if not scene_key or not scene_name or not has_chinese_text(scene_name) or not isinstance(raw_character_ids, list):
            raise StoryInvalidOutputError("Director current_scene 格式无效")
        character_ids = tuple(
            str(character_id).strip()
            for character_id in raw_character_ids
            if str(character_id).strip()
        )
        current_scene = StoryScene(key=scene_key, name=scene_name, character_ids=character_ids)
        try:
            current_scene.validate()
        except ValueError as exc:
            raise StoryInvalidOutputError(str(exc)) from exc
        return DirectorDraft(
            beats=tuple(beats),
            stop_reason=str(payload.get("stop_reason") or "awaiting_player"),
            visual_prompt=str(payload.get("visual_prompt") or "").strip(),
            visual_type=raw_visual_type,  # type: ignore[arg-type]
            current_scene=current_scene,
        )
