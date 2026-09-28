"""Host-owned communication account identity and runtime contract."""

from .models import (
    AccountAccess,
    AccountConfigReader,
    AccountDeleteHandler,
    AccountDeletingError,
    AccountDeletionPlan,
    AccountNotFoundError,
    AccountRecord,
    AccountSnapshot,
    ConfiguredAccount,
    ConnectionState,
)
from .registry import AccountRegistry

__all__ = [
    "AccountAccess",
    "AccountConfigReader",
    "AccountDeleteHandler",
    "AccountDeletingError",
    "AccountDeletionPlan",
    "AccountNotFoundError",
    "AccountRecord",
    "AccountRegistry",
    "AccountSnapshot",
    "ConfiguredAccount",
    "ConnectionState",
]
