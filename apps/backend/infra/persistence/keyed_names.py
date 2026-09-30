"""按任意文本键命名的文件名，供需要「一个键一份文件」的存储共用。"""

from __future__ import annotations

import hashlib
import re

_UNSAFE_FILENAME_CHARS = re.compile(r"[^0-9A-Za-z._-]+")


def keyed_file_name(key: str, suffix: str) -> str:
    """键转成安全字符后加 8 位 sha1 短哈希，再接上 ``suffix``（如 ``.md``）。

    安全化会把不同的键变成同一串字符，短哈希保证它们仍落在不同文件。
    """
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    stem = _UNSAFE_FILENAME_CHARS.sub("_", key).strip("_")
    return f"{stem}-{digest}{suffix}"
