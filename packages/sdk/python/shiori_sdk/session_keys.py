"""Pure role-session key helpers shared by the host and plugins.

These functions describe the existing stored format; they neither open a
session nor validate role existence. No runtime service injection is needed.
"""

ROLE_SESSION_PREFIX = "role:"
"""Prefix of a role's shared session, which contains all of its threads."""


def role_session_key(role_id: str) -> str:
    """Build the existing key, stripping surrounding role-id whitespace.

    A blank role id raises ``ValueError``. Other characters are preserved;
    role validation remains the caller's responsibility.
    """
    clean_role_id = str(role_id).strip()
    if not clean_role_id:
        raise ValueError("role_id 不能为空")
    return f"{ROLE_SESSION_PREFIX}{clean_role_id}"


def is_role_session_key(key: str) -> bool:
    """Check the stored prefix and a nonempty suffix without normalizing it.

    This is the host's existing classification, not canonical-key validation:
    unlike generation and parsing, it does not strip whitespace.
    """
    return key.startswith(ROLE_SESSION_PREFIX) and len(key) > len(ROLE_SESSION_PREFIX)


def role_id_from_session_key(key: str) -> str:
    """Extract the role id, stripping outer key and role-id whitespace.

    Return an empty string for a non-role key or an empty role suffix. This
    parser does not establish that the role exists or the input is canonical.
    """
    clean_key = str(key or "").strip()
    if not clean_key.startswith(ROLE_SESSION_PREFIX):
        return ""
    return clean_key.removeprefix(ROLE_SESSION_PREFIX).strip()
