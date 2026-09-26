"""Plugin RPC names for account-scoped target discovery and text delivery.

``account.targets`` receives account_id, kind, group_id, and member_id.
``account.send`` receives account_id, target_kind, target_id, message, and
optional message_thread_id. Plugins own target validation and return their
actual message_id; the host owns role authorization and delivery bookkeeping.
"""

ACCOUNT_TARGETS_METHOD = "account.targets"
ACCOUNT_SEND_METHOD = "account.send"


class UncertainDeliveryError(RuntimeError):
    """The platform may have accepted a send but did not confirm a receipt."""
