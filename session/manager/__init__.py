"""Session 模型与管理器的稳定公共入口。"""

import sys
from types import ModuleType

from . import helpers as _helpers_module
from . import manager as _manager_module
from . import models as _models_module
from . import persistence as _persistence_module
from . import projection as _projection_module
from . import role_sessions as _role_sessions_module
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
    _timestamp_at_or_before,
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


_PATCH_TARGETS: dict[str, tuple[ModuleType, ...]] = {
    "ConversationStateProjector": (_manager_module,),
    "ConversationStore": (_manager_module,),
    "SessionStore": (_manager_module,),
    "Session": (
        _manager_module,
        _persistence_module,
        _projection_module,
        _role_sessions_module,
    ),
    "_ROLE_SESSION_PREFIX": (_helpers_module, _role_sessions_module),
    "_TOOL_RESULT_CHAR_BUDGET": (_helpers_module,),
    "_PROACTIVE_HISTORY_CHAR_BUDGET": (_helpers_module,),
    "_PROACTIVE_META_HISTORY_CHAR_BUDGET": (_helpers_module,),
    "_align_to_user_boundary": (_helpers_module, _models_module),
    "_append_proactive_meta": (_helpers_module, _models_module),
    "_build_proactive_history_messages": (_helpers_module, _models_module),
    "_rebuild_user_content": (_helpers_module, _models_module),
    "_safe_filename": (_helpers_module,),
    "_timestamp_at_or_before": (_helpers_module, _role_sessions_module),
    "_truncate_text": (_helpers_module,),
    "_truncate_tool_result": (_helpers_module, _models_module),
}


class _ManagerFacadeModule(ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        for target in _PATCH_TARGETS.get(name, ()):
            setattr(target, name, value)


sys.modules[__name__].__class__ = _ManagerFacadeModule
