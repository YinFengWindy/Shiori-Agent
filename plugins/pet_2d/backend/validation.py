"""Strict JSON values and portable package paths used by the format validators."""

import json
import math
import re
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


def package_path(value: object) -> str:
    """Reject traversal, aliases and Windows special names before filesystem access."""
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError("形象包路径无效")
    if any(ord(c) < 32 or c in '\\:<>"|?*' for c in value):
        raise ValueError("形象包路径不安全")
    parts = value.split("/")
    if any(
        not p or p in {".", ".."} or p.endswith((".", " ")) or _RESERVED.match(p)
        for p in parts
    ):
        raise ValueError("形象包路径不安全")
    return value


def object_value(value: object, label: str) -> dict[str, Any]:
    """Require an object while retaining all producer metadata unchanged."""
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{label} 必须是对象")
    return value


def array(
    value: object, label: str, *, minimum: int = 0, maximum: int = 1000
) -> list[Any]:
    """Bound collection sizes before mesh or image allocation."""
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} 数组长度无效")
    return value


def number(
    value: object,
    label: str,
    *,
    low: float = -1e7,
    high: float = 1e7,
    integer: bool = False,
) -> float:
    """Reject booleans, non-finite values and out-of-contract numeric ranges."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
        or (integer and not isinstance(value, int))
    ):
        raise ValueError(f"{label} 数值无效")
    return value


def text(value: object, label: str, maximum: int = 1024) -> str:
    """Read bounded nonempty producer text."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError(f"{label} 文本无效")
    return value


def digest(value: object, label: str) -> str:
    """Require the lowercase SHA-256 form used by this package format."""
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"{label} SHA-256 无效")
    return value


def choice(value: object, choices: set, label: str) -> None:
    """Reject unknown discriminator values without substituting a fallback."""
    if not isinstance(value, (str, bool, type(None))) or value not in choices:
        raise ValueError(f"{label} 不受支持")


def vector(value: object, length: int, label: str, **limits: Any) -> list[Any]:
    """Require an exact-size finite numeric vector."""
    result = array(value, label, minimum=length, maximum=length)
    for v in result:
        number(v, label, **limits)
    return result


def finite_tree(value: object, depth: int = 0) -> None:
    """Validate unknown diagnostic fields too, rather than transmitting NaN to JS."""
    if depth > 40:
        raise ValueError("形象包 JSON 嵌套过深")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("形象包包含非有限数值")
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item, depth + 1)


def read_json(path: Path, max_bytes: int = 16 * 1024 * 1024) -> dict[str, Any]:
    """Reject duplicate object keys and nonstandard constants in bounded UTF-8 JSON."""
    if path.stat().st_size > max_bytes:
        raise ValueError("形象包 JSON 超过大小限制")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"形象包 JSON 重复字段: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"形象包 JSON 非有限数值: {value}")

    result = object_value(
        json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
        ),
        str(path.name),
    )
    finite_tree(result)
    return result
