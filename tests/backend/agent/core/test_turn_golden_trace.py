"""Golden trace of a passive turn with the real plugin kernel (#902 P3-0).

P3 moves lifecycle phases and tool hooks onto typed kernel events. These
scenarios record what a turn does today with the real system plugins loaded,
seen only from outside: the reply and stored messages, tool executions with
their final arguments and results, the order of prompt sections and
attachments, command replies and recorded citation IDs. They never name a
phase, slot or hook, so the event implementation must pass them unchanged.

The file also carries the core-only smoke test of §5.3: ``test_core_only_turn``
runs the same host with no plugin generation bound, and the core alone must
reply (including a multi-message finish_reply) and leave no citation or
protocol marker behind. Like the scenarios, it is a host contract every CI run
keeps.

Allowed edits during P3: the assembly in ``golden_host`` (P3-4 added the
core-only mode, ``plugin_root=None``) and ``observe_steps`` (the wiring itself
changes), and the attachment order of ``scenario_meme_and_novelai_attachments``,
which P3-4 flipped on purpose. Scenario assertions and the core-only
assertions stay as they are.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from agent.lifecycle.facade import TurnLifecycle
from agent.looping.core import AgentLoop
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)
from agent.plugin_host import PluginGenerationSettings, PluginKernel
from agent.prompting.input_budget import InputBudget
from agent.provider import LLMProvider, LLMResponse, ToolCall
from agent.retrieval.protocol import (
    MemoryRetrievalPipeline,
    RetrievalRequest,
    RetrievalResult,
)
from agent.tools.registry import ToolRegistry
from bootstrap.wiring import wire_turn_lifecycle
from bus.event_bus import EventBus
from conversation.service import desktop_thread_id
from core.common.channel_directory import ChannelDirectory
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from prompts.natural_chat import FINISH_REPLY_TOOL_NAME, NATURAL_CHAT_PROMPT
from session.manager import SessionManager
from shiori_sdk.core.conversation import StepFinished
from shiori_sdk.memory.engine import MemoryQueryResult
from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package
from shiori_sdk.tools import Tool
from tests.support.plugin_kernel import host_kernel

# Every system plugin with a phase module or tool hook today, plus novelai
# (default off) for its pre-tool guard and reply attachments. Citation is
# core since P3-4 (D9).
PLUGINS = (
    "context_pressure",
    "meme",
    "novelai",
    "plugin_undo",
    "shell_restore",
    "shell_safety",
    "status_commands",
    "tool_loop_guard",
)
CG_IMAGE = "https://example.test/cg.png"
# Tool results carrying this text push the next request to the hard input limit.
PRESSURE_MARK = "PRESSURE-MARK"
MOOD_REPLY = '{"mood":"平静","thought":"我想想。"}'


class ScriptedProvider(LLMProvider):
    """Answers reply requests from ``script`` in order and records them.

    Role mood follow-ups (``response_format``) get a fixed valid mood. When a
    request about to carry tools contains ``PRESSURE_MARK``, its hard input
    limit is its own size, as if that tool result had filled the window.
    """

    def __init__(self) -> None:
        super().__init__(
            api_key="test", model_context_window=128000, default_max_tokens=512
        )
        self.script: list[LLMResponse] = []
        self.requests: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> LLMResponse:  # type: ignore[override]
        if kwargs.get("response_format"):
            return LLMResponse(content=MOOD_REPLY)
        self.requests.append(kwargs)
        return self.script.pop(0)

    def input_budget(self, **request: Any) -> InputBudget | None:
        budget = super().input_budget(**request)
        messages = json.dumps(request.get("messages"), ensure_ascii=False)
        if budget is None or not request.get("tools") or PRESSURE_MARK not in messages:
            return budget
        return replace(budget, input_limit_tokens=budget.estimate.tokens)


class RecordingTool(Tool):
    """A tool that records the arguments it ran with and returns ``result``."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.result = "ok"
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._name

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"command": {"type": "string"}, "q": {"type": "string"}},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.result


class _ModelRuntime:
    @contextmanager
    def activate(self, role_id: str, purpose: str):
        yield SimpleNamespace(model="role-model")


class _MemoryEngine:
    """An engine without stored memories; retrieval is ``RecordingRetrieval``."""

    def read_self(self) -> str:
        return ""

    def read_recent_context(self) -> str:
        return ""

    def get_memory_context(self) -> str:
        return ""

    def read_profile(self) -> str:
        return ""

    def has_long_term_memory(self) -> bool:
        return False

    async def query(self, request: object) -> MemoryQueryResult:
        return MemoryQueryResult(text_block="", records=[], raw={})

    async def refresh_recent_turns(self, request: object) -> None:
        return None

    async def consolidate(self, request: object) -> None:
        return None


class RecordingRetrieval(MemoryRetrievalPipeline):
    """Memory retrieval that records every request and finds nothing."""

    def __init__(self) -> None:
        self.requests: list[RetrievalRequest] = []

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        self.requests.append(request)
        return RetrievalResult(block="")


@dataclass(frozen=True)
class StepSeen:
    """What a core step listener sees of one finished tool step."""

    early_stop: bool
    early_stop_reason: str
    telemetry: dict[str, object]


@dataclass
class GoldenHost:
    """One role ``mira`` turn host; the scenarios read only these fields."""

    workspace: Path
    provider: ScriptedProvider
    shell: RecordingTool
    lookup: RecordingTool
    retrieval: RecordingRetrieval
    manager: SessionManager
    loop: AgentLoop
    steps: list[StepSeen] = field(default_factory=list[StepSeen])

    async def turn(self, text: str, **metadata: object) -> str:
        """Runs one desktop turn of ``mira`` and returns the reply text."""
        return await self.loop.process_direct(
            text,
            channel="desktop",
            chat_id="role:mira",
            metadata={
                "role_id": "mira",
                "thread_id": desktop_thread_id("mira"),
                "transport_channel": "desktop",
                "transport_chat_id": "role:mira",
                **metadata,
            },
        )

    def stored(self) -> list[dict[str, Any]]:
        """The role session's messages as reloaded from disk."""
        return SessionManager(self.workspace).get_or_create("role:mira").messages

    def assistant(self) -> dict[str, Any]:
        """The last stored message, which a scenario expects from the role."""
        message = self.stored()[-1]
        assert message["role"] == "assistant"
        return message

    def tool_calls(self) -> list[dict[str, Any]]:
        """The persisted tool calls of the last reply, across all steps."""
        groups = self.assistant()["metadata"]["tool_chain"]
        return [call for group in groups for call in group["calls"]]

    def tool_results(self, request: int) -> list[tuple[str, str]]:
        """(call id, content) of the tool results the model saw in ``request``."""
        return [
            (str(message["tool_call_id"]), str(message["content"]))
            for message in self.provider.requests[request]["messages"]
            if message["role"] == "tool"
        ]

    def system_prompt(self, request: int = 0) -> str:
        """The system message of reply request ``request``."""
        return str(self.provider.requests[request]["messages"][0]["content"])


def observe_steps(bus: EventBus, steps: list[StepSeen]) -> None:
    """Listens to finished tool steps as a core listener does (progress reporting)."""

    def seen(event: StepFinished) -> None:
        steps.append(
            StepSeen(
                early_stop=event.early_stop,
                early_stop_reason=event.early_stop_reason,
                telemetry=dict(event.extra_metadata),
            )
        )

    TurnLifecycle(bus).on_step_finished(seen)


@pytest.fixture(scope="module")
def plugin_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("golden-plugins")
    for plugin_id in PLUGINS:
        _ = stage_plugin_package(plugin_directory(plugin_id), root / plugin_id)
    return root


def _seed_workspace(workspace: Path, *, natural_chat: bool) -> None:
    """Role ``mira``, its session, one shared emoji and one meme picture."""
    runtime_config = {"natural_chat_enabled": natural_chat}
    _ = RoleStore(workspace).create_role(
        role_id="mira", name="Mira", system_prompt="test", runtime_config=runtime_config
    )
    _ = SessionManager(workspace).open_role_session(
        "mira", role_name="Mira", role_runtime_config=runtime_config
    )
    emojis = workspace / "apps/desktop/renderer/src/chat/common_emojis.json"
    emojis.parent.mkdir(parents=True)
    _ = emojis.write_text(json.dumps([{"name": "smile", "value": "😊"}]), "utf-8")
    library = plugin_data_dir(workspace, "meme") / "library"
    (library / "happy").mkdir(parents=True)
    _ = (library / "happy/happy.png").write_bytes(b"png")
    _ = (library / "manifest.json").write_text(
        json.dumps({"categories": {"happy": {"desc": "开心"}}}), "utf-8"
    )


@asynccontextmanager
async def golden_host(
    workspace: Path, plugin_root: Path | None, *, natural_chat: bool = False
) -> AsyncGenerator[GoldenHost]:
    """A real ``AgentLoop`` with every ``PLUGINS`` entry loaded by the kernel.

    Without ``plugin_root`` no plugin generation is bound: the core runs alone.
    """
    _seed_workspace(workspace, natural_chat=natural_chat)
    roles = RoleStore(workspace)
    manager = SessionManager(workspace)
    tools = ToolRegistry()
    shell, lookup = RecordingTool("shell"), RecordingTool("lookup")
    tools.register(shell, always_on=True)
    tools.register(lookup, always_on=True)
    bus = EventBus()
    provider = ScriptedProvider()
    retrieval = RecordingRetrieval()
    loop = AgentLoop(
        AgentLoopDeps(
            bus=MagicMock(),
            provider=cast(Any, provider),
            light_provider=cast(Any, provider),
            tools=tools,
            session_manager=manager,
            workspace=workspace,
            event_bus=bus,
            memory_services=MemoryServices(engine=cast(Any, _MemoryEngine())),
            retrieval_pipeline=retrieval,
            role_runtime_registry=RoleRuntimeRegistry(
                RoleRepository(roles), model_resolver=cast(Any, _ModelRuntime())
            ),
            channel_directory=ChannelDirectory(),
        ),
        AgentLoopConfig(llm=LLMConfig(max_tokens=512)),
    )
    wire_turn_lifecycle(
        lifecycle=TurnLifecycle(bus), active_turn_states=loop.active_turn_states
    )
    host = GoldenHost(workspace, provider, shell, lookup, retrieval, manager, loop)
    observe_steps(bus, host.steps)
    if plugin_root is None:
        try:
            yield host
        finally:
            await bus.aclose()
        return
    kernel: PluginKernel = host_kernel(
        [plugin_root],
        settings=PluginGenerationSettings(
            workspace=workspace,
            plugin_configs={"novelai": {"enabled": True, "token": "novel-token"}},
        ),
        http=FakeHttp(),
        role_store=roles,
        tools=tools,
        session_manager=manager,
        light_provider=provider,
        light_model="light",
        event_bus=bus,
    )
    await kernel.load_all()
    assert sorted(kernel.active_plugin_ids) == sorted(PLUGINS)
    loop.bind_plugin_contributions(kernel)
    generate = tools.get_tool("generate_image")
    assert generate is not None

    async def generated(**_: object) -> str:
        return json.dumps({"output_paths": [CG_IMAGE]})

    generate.execute = generated  # type: ignore[method-assign]
    try:
        yield host
    finally:
        await kernel.terminate_all()
        await bus.aclose()


def _reply(content: str) -> LLMResponse:
    return LLMResponse(content=content)


def _calls(*calls: tuple[str, str, dict[str, Any]]) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(call_id, name, args) for call_id, name, args in calls],
    )


async def scenario_citation_marker_and_emoji(host: GoldenHost) -> None:
    """A trailing citation marker followed by an emoji tag (citation before meme)."""
    host.provider.script = [_reply("好呀 §cited:[mem-1]§ <emoji:smile>")]

    assert await host.turn("你好") == "好呀 😊"
    assistant = host.assistant()
    assert assistant["content"] == "好呀 😊"
    assert assistant["cited_memory_ids"] == ["mem-1"]


async def scenario_meme_and_novelai_attachments(host: GoldenHost) -> None:
    """A generated picture and a meme picture attach to the same reply.

    Until P3-4 novelai's picture came first (meme set up after citation,
    novelai before it). With citation in the core both have depth 0 and set up
    by id, so meme's picture now comes first (#902, accepted).
    """
    host.provider.script = [
        _calls(("g1", "generate_image", {"prompt": "rain"})),
        _reply("看图 <meme:happy>"),
    ]

    assert await host.turn("画一张") == "看图"
    media = host.assistant()["media"]
    assert len(media) == 2
    assert media[1] == CG_IMAGE
    meme_copy = Path(media[0])
    assert meme_copy.suffix == ".png"
    assert meme_copy.is_relative_to(host.workspace / "sessions/media")


async def scenario_rm_rewrite_and_interactive_block(host: GoldenHost) -> None:
    """``rm`` runs as a move into the restore directory; ``vim`` is refused.

    shell_safety judges the command shell_restore already rewrote. The rewrite
    drops every rm option, so the editor path inside the ``s3`` option only
    reaches shell_safety if it runs before the rewrite; it is the one input
    that tells the two orders apart (shell_safety matches the basename of any
    token against its editor list).
    """
    host.provider.script = [
        _calls(
            ("s1", "shell", {"command": "rm notes.txt"}),
            ("s2", "shell", {"command": "vim notes.txt"}),
            ("s3", "shell", {"command": "rm --backup=/usr/bin/vim old.txt"}),
        ),
        _reply("处理好了"),
    ]
    restore = str((host.workspace / "recovery/shell_restore").resolve())
    moved = shlex.join(["mv", "--", "notes.txt", restore])
    moved_old = shlex.join(["mv", "--", "old.txt", restore])
    refused = "shell_safety 拦截：vim 会打开交互式界面，请改用非交互命令。"

    assert await host.turn("清理一下") == "处理好了"
    assert [call["command"] for call in host.shell.calls] == [moved, moved_old]
    assert host.tool_results(1) == [("s1", "ok"), ("s2", refused), ("s3", "ok")]
    assert [
        (call["call_id"], call["status"], call["final_arguments"], call["result"])
        for call in host.tool_calls()
    ] == [
        ("s1", "success", {"command": moved}, "ok"),
        ("s2", "denied", {"command": "vim notes.txt"}, refused),
        ("s3", "success", {"command": moved_old}, "ok"),
    ]


async def scenario_repeated_call_finalizes(host: GoldenHost) -> None:
    """The third identical call is refused and the turn closes with a summary."""
    same = ("l", "lookup", {"q": "同一个"})
    host.provider.script = [_calls(same), _calls(same), _calls(same), _reply("先总结")]
    stopped = "连续重复调用工具 3 次，已截断并进入收尾。"

    assert await host.turn("查一下") == "先总结"
    assert [call["q"] for call in host.lookup.calls] == ["同一个", "同一个"]
    # The fourth request is the closing summary: the only one offering no tools.
    # Assumes the summary is a separate request without tools; sending tools with
    # tool_choice=none instead would be a behavior change to update here.
    assert [bool(request.get("tools")) for request in host.provider.requests] == [
        True,
        True,
        True,
        False,
    ]
    assert [(call["status"], call["result"]) for call in host.tool_calls()] == [
        ("success", "ok"),
        ("success", "ok"),
        ("denied", stopped),
    ]


async def scenario_context_pressure_stops_early(host: GoldenHost) -> None:
    """A step that fills the input window closes the turn; step listeners see why."""
    host.lookup.result = f"{PRESSURE_MARK} 很长的资料"
    host.provider.script = [_calls(("l", "lookup", {"q": "大"})), _reply("先说结论")]

    assert await host.turn("查资料") == "先说结论"
    assert len(host.lookup.calls) == 1
    # The second request is the closing summary, offering no tools.
    # Assumes the summary is a separate request without tools; sending tools with
    # tool_choice=none instead would be a behavior change to update here.
    assert [bool(request.get("tools")) for request in host.provider.requests] == [
        True,
        False,
    ]
    [step] = host.steps
    assert (step.early_stop, step.early_stop_reason) == (True, "context_pressure")
    # The telemetry only reaches step listeners (nothing stores or pushes it),
    # so only its meaning is fixed here, not its key names.
    [tokens] = [v for k, v in step.telemetry.items() if k.endswith("tokens")]
    [threshold] = [v for k, v in step.telemetry.items() if k.endswith("threshold")]
    assert isinstance(tokens, int) and isinstance(threshold, int)
    assert tokens >= threshold


async def scenario_commands_bypass_memory_backlog(host: GoldenHost) -> None:
    """With a memory backlog that refuses turns, commands still answer.

    The host here has no markdown memory, so a backlog over the threshold is
    a consolidation failure that stops ordinary turns before retrieval.
    """
    session = host.manager.get_or_create("role:mira")
    thread = desktop_thread_id("mira")
    for index in range(20):
        session.add_message("user", f"u{index}", thread_id=thread)
        session.add_message("assistant", f"a{index}", thread_id=thread)
    host.manager.save(session)

    assert await host.turn("/memorystatus") == (
        "🧠 记忆整理状态：\n当前会话还没有完成过记忆整理。\n\n"
        "尚未整理的用户消息数：20\n当前会话消息数：40"
    )
    assert await host.turn("/undo") == (
        "已撤销上一轮对话。\n删除消息：2 条\n失效记忆：0 条\n恢复旧记忆：0 条"
    )
    with pytest.raises(Exception):
        _ = await host.turn("你好")
    assert host.retrieval.requests == []
    assert host.provider.requests == []
    stored = host.stored()
    assert len(stored) == 38
    assert (stored[-1]["role"], stored[-1]["content"]) == ("assistant", "a18")


async def scenario_finish_reply_cleans_each_message(host: GoldenHost) -> None:
    """Natural chat: every finish_reply message is cleaned on its own.

    The citation IDs found in any message are recorded on every stored row.
    ``[§mem-2]`` is only removed, never recorded: the trailing
    ``§cited:[...]§`` marker (or recall_memory results) is the one citation
    format the core reads (``agent.core.citation``), and no prompt asks the
    model for inline ``[§id]``; the core strips those as leftover markers.
    """
    host.provider.script = [
        _calls(
            (
                "r",
                FINISH_REPLY_TOOL_NAME,
                {
                    "messages": [
                        "早呀[§mem-2]",
                        "一起加油 §cited:[mem-3]§ <emoji:smile> <x:y>",
                    ]
                },
            )
        )
    ]

    assert await host.turn("早", turn_id="t1") == "早呀\n\n一起加油 😊"
    replies = [message for message in host.stored() if message["role"] == "assistant"]
    # Inline [§id] is only stripped; cited IDs come from the trailing line alone
    # (or the recall_memory fallback), so mem-2 is not recorded by design.
    assert [
        (
            message["content"],
            message["metadata"]["reply_sequence_index"],
            message.get("cited_memory_ids"),
        )
        for message in replies
    ] == [("早呀", 0, ["mem-3"]), ("一起加油 😊", 1, ["mem-3"])]


async def scenario_prompt_section_order(host: GoldenHost) -> None:
    """Plugin prompt sections follow the core ones; meme precedes natural chat."""
    host.provider.script = [_calls(("r", FINISH_REPLY_TOOL_NAME, {"messages": ["嗯"]}))]

    _ = await host.turn("在吗", turn_id="t1")
    system = host.system_prompt()
    anchors = ["## Active Role: Mira", "## Current Session", "# Memes"]
    positions = [system.index(anchor) for anchor in anchors]
    positions.append(system.index(NATURAL_CHAT_PROMPT))
    assert positions == sorted(positions)
    assert system.rstrip().endswith(NATURAL_CHAT_PROMPT.rstrip())


Scenario = Callable[[GoldenHost], Awaitable[None]]


@pytest.mark.parametrize(
    ("scenario", "natural_chat"),
    [
        (scenario_citation_marker_and_emoji, False),
        (scenario_meme_and_novelai_attachments, False),
        (scenario_rm_rewrite_and_interactive_block, False),
        (scenario_repeated_call_finalizes, False),
        (scenario_context_pressure_stops_early, False),
        (scenario_commands_bypass_memory_backlog, False),
        (scenario_finish_reply_cleans_each_message, True),
        (scenario_prompt_section_order, True),
    ],
    ids=lambda value: (
        value.__name__.removeprefix("scenario_") if callable(value) else None
    ),
)
async def test_turn_golden_trace(
    tmp_path: Path,
    plugin_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: Scenario,
    natural_chat: bool,
) -> None:
    monkeypatch.delenv("AKASIC_RESTORE_DIR", raising=False)
    async with golden_host(tmp_path, plugin_root, natural_chat=natural_chat) as host:
        await scenario(host)


_FINISH_REPLY = ["早呀[§mem-2]", "一起加油 §cited:[mem-3]§ <emoji:smile> <x:y>"]


@pytest.mark.parametrize(
    ("natural_chat", "answer", "reply", "stored"),
    [
        (
            False,
            _reply("好呀 §cited:[mem-1]§ <emoji:smile>"),
            "好呀",
            [("好呀", ["mem-1"])],
        ),
        (
            True,
            _calls(("r", FINISH_REPLY_TOOL_NAME, {"messages": _FINISH_REPLY})),
            "早呀\n\n一起加油",
            [("早呀", ["mem-3"]), ("一起加油", ["mem-3"])],
        ),
    ],
    ids=["reply", "finish_reply"],
)
async def test_core_only_turn(
    tmp_path: Path,
    natural_chat: bool,
    answer: LLMResponse,
    reply: str,
    stored: list[tuple[str, list[str]]],
) -> None:
    """With every plugin off the core replies and strips every marker (§5.3, D9).

    The citation IDs are still recorded; the emoji and protocol tags no plugin
    consumed are removed, from each finish_reply message.
    """
    async with golden_host(tmp_path, None, natural_chat=natural_chat) as host:
        host.provider.script = [answer]

        assert await host.turn("你好", turn_id="t1") == reply
        assert [
            (message["content"], message.get("cited_memory_ids"))
            for message in host.stored()
            if message["role"] == "assistant"
        ] == stored
