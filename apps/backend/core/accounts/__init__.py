"""Communication account index and runtime contract; records live in plugins."""

from .avatar import MAX_AVATAR_BYTES, avatar_data_uri, validate_avatar
from .models import (
    AccountAccess,
    AccountDeleteHandler,
    AccountDeletingError,
    AccountDeletionPlan,
    AccountNotFoundError,
    AccountRecord,
    AccountResponseRules,
    AccountRulesHandler,
    AccountSnapshot,
    ConnectionState,
    account_id_for,
)
from .registry import AccountRegistry
from .rules import (
    response_rules_from_dict,
    response_rules_to_dict,
    stored_response_rules,
)

__all__ = [
    "AccountAccess",
    "AccountDeleteHandler",
    "AccountDeletingError",
    "AccountDeletionPlan",
    "AccountNotFoundError",
    "AccountRecord",
    "AccountRegistry",
    "AccountResponseRules",
    "AccountRulesHandler",
    "AccountSnapshot",
    "ConnectionState",
    "MAX_AVATAR_BYTES",
    "account_id_for",
    "avatar_data_uri",
    "response_rules_from_dict",
    "response_rules_to_dict",
    "stored_response_rules",
    "validate_avatar",
]
