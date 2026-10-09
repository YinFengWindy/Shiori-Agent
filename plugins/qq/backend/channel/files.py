"""Receive bounded txt/md attachments from direct and quoted QQ file segments."""

from __future__ import annotations

import html
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from websockets.exceptions import ConnectionClosed

from shiori_sdk.channels.services import AttachmentStore
from shiori_sdk.http import HttpGet, RequestBudget, ResponseTooLarge

from ..onebot import OneBotError

MAX_FILE_BYTES = 2 * 1024 * 1024
"""Maximum downloaded and stored size of one QQ text attachment (2 MiB)."""
TEXT_FILE_SUFFIXES = frozenset({".txt", ".md"})
"""Formats this plugin can expose to its attachment reader."""
_FILE_RE = re.compile(r"\[CQ:file(?:,([^\]]*))?\]")


@dataclass(frozen=True)
class QQFile:
    """Platform file descriptor; it never grants access to a local path."""

    name: str
    url: str = ""
    file_id: str = ""
    size: int | None = None
    busid: int = 0

    @property
    def description(self) -> str:
        """Human-readable file name retained even for listening-only messages."""
        return f"[文件：{self.name}]"


def extract_cq_files(raw: str) -> tuple[str, list[QQFile]]:
    """Replace file codes with descriptions, retaining descriptors for admission."""
    files: list[QQFile] = []

    def describe(match: re.Match[str]) -> str:
        fields = {
            key: html.unescape(value)
            for part in (match.group(1) or "").split(",")
            if "=" in part
            for key, value in [part.split("=", 1)]
        }
        # Both field spellings occur in NapCat messages and get_msg results.
        name = fields.get("name") or fields.get("file") or "未命名文件"
        name = name.replace("\\", "/").rsplit("/", 1)[-1]
        size = fields.get("size") or fields.get("file_size") or ""
        busid = fields.get("busid") or "0"
        file = QQFile(
            name=name,
            url=fields.get("url", ""),
            file_id=fields.get("file_id") or fields.get("id", ""),
            size=int(size) if size.isdecimal() else None,
            busid=int(busid) if busid.isdecimal() else 0,
        )
        files.append(file)
        return file.description

    # Decode only after identifying genuine CQ segments. Decode ordinary text
    # and each parameter once, keeping literal entities in file names intact.
    parts: list[str] = []
    cursor = 0
    for match in _FILE_RE.finditer(raw):
        parts.extend((html.unescape(raw[cursor : match.start()]), describe(match)))
        cursor = match.end()
    parts.append(html.unescape(raw[cursor:]))
    return "".join(parts).strip(), files


def validate_text(data: bytes) -> str:
    """Decode UTF-8 text and reject binary bytes disguised with a text suffix."""
    if any(byte < 32 and byte not in (9, 10, 13) for byte in data):
        raise ValueError("文件包含二进制内容，无法作为文本读取")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("文件不是 UTF-8 文本，请转换编码后重发") from exc


async def receive_files(
    text: str,
    files: list[QQFile],
    requester: HttpGet,
    attachments: AttachmentStore,
    resolve_url: Callable[[QQFile], Awaitable[str]],
) -> tuple[str, list[str]]:
    """Download admitted files and explicitly describe any file not received."""
    paths: list[str] = []
    cursor = 0
    for file in files:
        position = text.find(file.description, cursor)
        cursor = position + len(file.description)
        try:
            suffix = Path(file.name).suffix.lower()
            if suffix not in TEXT_FILE_SUFFIXES:
                raise ValueError("暂不支持此格式，仅支持 txt/md")
            if file.size is not None and file.size > MAX_FILE_BYTES:
                raise ResponseTooLarge(MAX_FILE_BYTES)
            url = file.url or await resolve_url(file)
            if not url.startswith(("https://", "http://")):
                raise ValueError("没有可用的 HTTP 下载地址")
            response = await requester.get(
                url,
                follow_redirects=True,
                timeout_s=15.0,
                budget=RequestBudget(total_timeout_s=20.0),
                max_response_bytes=MAX_FILE_BYTES,
            )
            _ = response.raise_for_status()
            data = response.content
            if len(data) > MAX_FILE_BYTES:
                raise ResponseTooLarge(MAX_FILE_BYTES)
            _ = validate_text(data)
            # The store allocates the random prefix; sanitizing the original
            # basename keeps useful names and suffixes without path traversal.
            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(file.name).stem)[:80]
            path = attachments.write_bytes(
                data, prefix=f"shiori_qq_{stem}_", suffix=suffix
            )
            paths.append(str(path))
        except ResponseTooLarge:
            reason = "文件超过 2 MiB 上限，未接收正文"
        except httpx.HTTPStatusError as exc:
            reason = f"下载失败（HTTP {exc.response.status_code}），未接收正文"
        except (httpx.RequestError, TimeoutError, ConnectionClosed, OneBotError):
            reason = "下载失败或链接已失效，未接收正文"
        except ValueError as exc:
            reason = str(exc)
        else:
            continue
        description = f"[文件：{file.name}；{reason}]"
        text = text[:position] + description + text[cursor:]
        cursor = position + len(description)
    return text, paths
