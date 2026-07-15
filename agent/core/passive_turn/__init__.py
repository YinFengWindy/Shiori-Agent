"""被动消息处理的稳定公共入口。

具体实现按 pipeline、context、reasoner 与辅助逻辑拆分；本模块保留原有导入路径。
"""

from .context import ContextStore, DefaultContextStore
from .helpers import (
    build_deferred_tools_hint,
    build_turn_injection_prompt,
    extract_model_facing_turn,
    get_history_since_consolidated,
    get_session_metadata,
)
from .pipeline import AgentCore, AgentCoreDeps, PassiveTurnPipeline
from .reasoner import DefaultReasoner, Reasoner

__all__ = [
    "AgentCore",
    "AgentCoreDeps",
    "ContextStore",
    "DefaultContextStore",
    "DefaultReasoner",
    "PassiveTurnPipeline",
    "Reasoner",
    "build_deferred_tools_hint",
    "build_turn_injection_prompt",
    "extract_model_facing_turn",
    "get_history_since_consolidated",
    "get_session_metadata",
]
