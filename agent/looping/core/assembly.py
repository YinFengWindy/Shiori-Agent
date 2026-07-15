"""AgentLoop 依赖装配与兼容配置属性。"""

from __future__ import annotations

import asyncio
from typing import cast
from agent.context import ContextBuilder
from agent.core.passive_turn import (
    AgentCore,
    AgentCoreDeps,
    DefaultContextStore,
    DefaultReasoner,
)
from agent.core.runner import (
    CoreRunner,
    CoreRunnerDeps,
)
from agent.core.runtime_support import ToolDiscoveryState
from ..interrupt import (
    TurnInterruptState,
)
from ..ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMServices,
    MemoryServices,
    SessionServices,
)
from agent.retrieval.default_pipeline import DefaultMemoryRetrievalPipeline
from agent.turns.outbound import BusOutboundPort
from bus.event_bus import EventBus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.engine import MemoryEngine
    from core.memory.markdown import MemoryProfileApi

class _AssemblyMixin:
    def __init__(
        self,
        deps: AgentLoopDeps,
        config: AgentLoopConfig,
    ) -> None:
        # 1. 先挂基础运行时对象和配置。
        self._llm_config = config.llm
        self.bus = deps.bus
        self.tools = deps.tools
        self.memory_window = config.memory.window
        self._running = False
        self._processing_state = deps.processing_state
        self._event_bus = deps.event_bus or EventBus()
        self._role_world_registry = deps.role_world_registry

        # ── 中断控制面（纯内存态） ──
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._active_turn_states: dict[str, TurnInterruptState] = {}
        self._interrupt_states: dict[str, TurnInterruptState] = {}

        # 2. 再解析 memory runtime 入口。
        memory_engine = self._resolve_memory_runtime(deps)
        markdown_memory = self._resolve_markdown_runtime(deps)
        self._tool_search_enabled = bool(config.llm.tool_search_enabled)
        self._memory_engine = memory_engine
        self._markdown_memory = markdown_memory
        memory_profile = (
            markdown_memory.store
            if markdown_memory is not None
            else cast("MemoryProfileApi", self._memory_engine)
        )
        self._context = deps.context or ContextBuilder(
            deps.workspace,
            memory=memory_profile,
            multimodal=config.llm.multimodal,
            vl_available=config.llm.vl_available,
        )
        self._llm_services = deps.llm_services or LLMServices(
            provider=deps.provider,
            light_provider=deps.light_provider or deps.provider,
        )
        self._session_services = deps.session_services or SessionServices(
            session_manager=deps.session_manager,
            presence=deps.presence,
        )

        # 3. 最后把 passive chain 装起来。
        self._assemble_passive_runtime(
            deps=deps,
            config=config,
        )
        self._configure_stream_events()

    def _resolve_memory_runtime(
        self,
        deps: AgentLoopDeps,
    ) -> "MemoryEngine":
        if deps.memory_runtime is not None:
            return deps.memory_runtime.engine
        if deps.memory_services is not None and deps.memory_services.engine is not None:
            return deps.memory_services.engine
        raise ValueError("AgentLoop requires memory_runtime.engine")

    def _resolve_markdown_runtime(
        self,
        deps: AgentLoopDeps,
    ):
        if deps.memory_runtime is not None:
            return deps.memory_runtime.markdown
        return None

    def _assemble_passive_runtime(
        self,
        *,
        deps: AgentLoopDeps,
        config: AgentLoopConfig,
    ) -> None:
        # 1. 先组基础 service ports。
        llm_svc = self._llm_services
        memory_svc = deps.memory_services or MemoryServices(
            engine=getattr(deps.memory_runtime, "engine", None),
        )
        session_svc = self._session_services
        # 2. 组执行层。
        self._tool_discovery = deps.tool_discovery or ToolDiscoveryState()
        self._reasoner = deps.reasoner or DefaultReasoner(
            llm=llm_svc,
            llm_config=config.llm,
            tools=deps.tools,
            discovery=self._tool_discovery,
            tool_search_enabled=self._tool_search_enabled,
            memory_window=config.memory.keep_count,
            context=self._context,
            session_manager=self.session_manager,
            event_bus=self._event_bus,
        )

        # 3. 最后串 passive prepare / execute / commit 主链。
        retrieval_pipeline = deps.retrieval_pipeline or DefaultMemoryRetrievalPipeline(
            memory=memory_svc,
        )
        self._retrieval_pipeline = retrieval_pipeline
        passive_context_store = DefaultContextStore(
            retrieval=retrieval_pipeline,
            context=self._context,
            history_window=config.memory.keep_count,
        )
        agent_core = AgentCore(
            AgentCoreDeps(
                session=session_svc,
                context_store=passive_context_store,
                context=self._context,
                tools=deps.tools,
                reasoner=self._reasoner,
                llm=llm_svc,
                llm_config=config.llm,
                event_bus=self._event_bus,
                outbound_port=BusOutboundPort(self.bus),
                history_window=config.memory.keep_count,
                memory_consolidator=self,
            )
        )
        self._agent_core = agent_core
        self._core_runner = deps.core_runner or CoreRunner(
            CoreRunnerDeps(
                agent_core=agent_core,
                session=session_svc,
                context=self._context,
                tools=deps.tools,
                memory_window=config.memory.keep_count,
                run_agent_loop_fn=self._run_agent_loop,
                prompt_render_fn=self._reasoner.render_prompt,
            )
        )

    @property
    def light_model(self) -> str:
        # 1. 兼容外部读取 loop.light_model，真实值统一来自 llm 配置。
        return self._llm_config.light_model or self._llm_config.model

    @property
    def context(self) -> ContextBuilder:
        # 1. 兼容外部读取 loop.context，真实值统一来自私有 context 依赖。
        return self._context

    @property
    def light_provider(self):
        # 1. 兼容外部读取 loop.light_provider，真实值统一来自 llm services。
        return self._llm_services.light_provider

    @property
    def session_manager(self):
        # 1. 兼容外部读取 loop.session_manager，真实值统一来自 session services。
        return self._session_services.session_manager

    @light_model.setter
    def light_model(self, value: str) -> None:
        # 1. 兼容初始化期和少量外部覆写，统一回写到 llm 配置。
        self._llm_config.light_model = value

    @property
    def max_iterations(self) -> int:
        # 1. 兼容外部读取 loop.max_iterations，真实值统一来自 llm 配置。
        return int(self._llm_config.max_iterations)

    @max_iterations.setter
    def max_iterations(self, value: int) -> None:
        # 1. 兼容测试或外部直接改 loop.max_iterations，真实执行也同步生效。
        self._llm_config.max_iterations = int(value)
