"""Session 模型与管理器的稳定公共入口。"""

from .helpers import (
    _PROACTIVE_HISTORY_CHAR_BUDGET,
    _PROACTIVE_META_HISTORY_CHAR_BUDGET,
    _ROLE_SESSION_PREFIX,
    _TOOL_RESULT_CHAR_BUDGET,
    _align_to_user_boundary,
    _append_proactive_meta,
    _build_proactive_history_messages,
    _rebuild_user_content,
    _safe_filename,
    _truncate_text,
    _truncate_tool_result,
    logger,
)
from .manager import (
    ConversationStateProjector,
    ConversationStore,
    SessionStore,
    _ManagerCoreMixin,
)
from .models import Session
from .persistence import _PersistenceMixin
from .projection import _ProjectionMixin
from .role_sessions import _RoleSessionsMixin

Session.__module__ = __name__


class SessionManager(
    _ManagerCoreMixin,
    _RoleSessionsMixin,
    _PersistenceMixin,
    _ProjectionMixin,
):
    """Manage cached sessions and their durable SQLite representation."""
