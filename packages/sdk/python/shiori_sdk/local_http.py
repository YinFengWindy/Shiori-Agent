"""Validation for plugin-owned HTTP connections to local native services."""

from ipaddress import ip_address
from urllib.parse import urlsplit


def loopback_http_url(value: str) -> str:
    """Accept an explicit HTTP loopback origin, without credentials or redirects."""
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    local = host == "localhost"
    if not local:
        try:
            local = ip_address(host).is_loopback
        except ValueError:
            local = False
    if (
        parsed.scheme != "http"
        or not local
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("服务地址必须是本机 HTTP 地址，如 http://127.0.0.1:9880")
    # Accessing port also rejects malformed port strings before any network call.
    _ = parsed.port
    return value.rstrip("/")
