"""Plugin wire names and the desktop namespaces a plugin cannot claim."""

HOST_RPC_NAMESPACES = frozenset(
    {
        "accounts",
        "bridge",
        "channels",
        "chat",
        "desktop",
        "health",
        "identities",
        "memory",
        "models",
        "phone",
        "plugin",
        "plugins",
        "roles",
        "runtime",
        "session",
        "window",
    }
)
"""Reserved roots for host RPCs and events, including plugin management."""


def plugin_method_owner(method: str) -> str | None:
    """Return the plugin namespace, or None for host or unqualified methods."""
    owner, separator, name = method.partition(".")
    if not owner or not separator or not name or owner in HOST_RPC_NAMESPACES:
        return None
    return owner
