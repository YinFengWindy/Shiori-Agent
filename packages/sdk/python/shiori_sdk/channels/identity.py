"""The declared scope of platform user identities."""

from typing import Literal

IdentityScope = Literal["platform", "account"]
IDENTITY_SCOPES: tuple[IdentityScope, ...] = ("platform", "account")


def parse_identity_scope(value: object) -> IdentityScope:
    """Returns ``value`` as an identity scope; raises ValueError otherwise."""
    for scope in IDENTITY_SCOPES:
        if value == scope:
            return scope
    raise ValueError(f"身份作用域必须是 {' / '.join(IDENTITY_SCOPES)} 之一")
