"""Outbound delivery failures with transport-level recovery constraints."""


class NonRetryableDeliveryError(RuntimeError):
    """A delivery must not be replayed or replaced with a generic error notice.

    Channels raise this after exhausting safe recovery, including when a remote
    write may already be visible or a multipart delivery only partly succeeded.
    """
