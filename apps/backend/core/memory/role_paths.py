"""角色记忆目录与其中按键命名的文件路径，供各记忆层共用。

``core.roles`` 的 ``RoleMemoryService.memory_root`` 也经由这里定位，记忆层不反向
依赖 ``core.roles``（导入它会拉起整个角色服务，并与记忆模块循环导入）。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_UNSAFE_FILENAME_CHARS = re.compile(r"[^0-9A-Za-z._-]+")


def role_memory_dir(workspace: Path, role_id: str) -> Path:
    """角色的记忆目录 ``roles/<role_id>/memory``；``role_id`` 为空时抛 ``ValueError``。"""
    clean_role_id = str(role_id).strip()
    if not clean_role_id:
        raise ValueError("role_id 不能为空")
    return workspace / "roles" / clean_role_id / "memory"


def keyed_markdown_name(key: str) -> str:
    """按任意文本键命名的 Markdown 文件名：键转成安全字符后加 8 位 sha1 短哈希。

    安全化会把不同的键变成同一串字符，短哈希保证它们仍落在不同文件。
    """
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    stem = _UNSAFE_FILENAME_CHARS.sub("_", key).strip("_")
    return f"{stem}-{digest}.md"
