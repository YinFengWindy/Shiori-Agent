"""Session SQLite 存储的稳定公共入口。"""

from .connection import _SessionConnection
from .messages import _MessageMixin
from .presence import _PresenceMixin
from .search import _SearchMixin
from .sessions import _SessionMixin


class SessionStore(
    _SessionMixin,
    _PresenceMixin,
    _MessageMixin,
    _SearchMixin,
    _SessionConnection,
):
    """SQLite-backed store for session metadata and messages."""
