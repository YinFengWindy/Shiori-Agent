"""Telegram Markdown 预览的安全 HTML 渲染。"""

import html
import re

_THINKING_MIN = 100
_PREVIEW_OVERHEAD = 80
_PARSE_ERR_RE = re.compile(r"can't parse entities|parse entities|find end of the entity", re.I)
_SPOILER_RE = re.compile(r"\|\|(.+?)\|\|", re.S)
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.S)
_FENCE_RE = re.compile(r"^\s*```")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", re.S)
def _is_telegram_html_parse_error(err: Exception) -> bool:
    return bool(_PARSE_ERR_RE.search(str(err)))


def _is_telegram_message_not_modified_error(err: Exception) -> bool:
    return "message is not modified" in str(err).lower()


def render_telegram_preview_html(text: str) -> str:
    prepared = _prepare_preview_markdown(text or "")
    rendered = _render_preview_blocks(prepared)
    return rendered.strip() or html.escape(text or "")


def _prepare_preview_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"(?m)^\s*([-*_])\1{2,}\s*$", "", text)
    return text


def _render_preview_blocks(text: str) -> str:
    lines = text.split("\n")
    parts: list[str] = []
    prev_kind: str | None = None
    pending_blank = False
    in_fence = False
    fence_lines: list[str] = []
    blockquote_lines: list[str] = []

    def flush_blockquote() -> None:
        nonlocal blockquote_lines, prev_kind, pending_blank
        if not blockquote_lines:
            return
        _append_preview_part(
            parts,
            "<blockquote>" + "\n".join(_render_inline(line) for line in blockquote_lines) + "</blockquote>",
            kind="blockquote",
            prev_kind=prev_kind,
            pending_blank=pending_blank,
        )
        prev_kind = "blockquote"
        pending_blank = False
        blockquote_lines = []

    def flush_fence() -> None:
        nonlocal fence_lines, in_fence, prev_kind, pending_blank
        if not in_fence:
            return
        code = "\n".join(fence_lines).strip("\n")
        _append_preview_part(
            parts,
            f"<pre><code>{html.escape(code)}</code></pre>",
            kind="pre",
            prev_kind=prev_kind,
            pending_blank=pending_blank,
        )
        prev_kind = "pre"
        pending_blank = False
        fence_lines = []
        in_fence = False

    for line in lines:
        if _FENCE_RE.match(line):
            flush_blockquote()
            if in_fence:
                flush_fence()
            else:
                in_fence = True
                fence_lines = []
            continue
        if in_fence:
            fence_lines.append(line)
            continue
        blockquote_match = _BLOCKQUOTE_RE.match(line)
        if blockquote_match:
            blockquote_lines.append(blockquote_match.group(1))
            continue

        flush_blockquote()

        stripped = line.strip()
        if not stripped:
            pending_blank = True
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            _append_preview_part(
                parts,
                f"<b>{_render_inline(heading_match.group(1).strip())}</b>",
                kind="heading",
                prev_kind=prev_kind,
                pending_blank=pending_blank,
            )
            prev_kind = "heading"
            pending_blank = False
            continue

        list_match = _LIST_RE.match(line)
        if list_match:
            _append_preview_part(
                parts,
                f"• {_render_inline(list_match.group(1).strip())}",
                kind="list_item",
                prev_kind=prev_kind,
                pending_blank=pending_blank,
            )
            prev_kind = "list_item"
            pending_blank = False
            continue

        _append_preview_part(
            parts,
            _render_inline(stripped),
            kind="paragraph",
            prev_kind=prev_kind,
            pending_blank=pending_blank,
        )
        prev_kind = "paragraph"
        pending_blank = False

    flush_blockquote()
    flush_fence()
    return "\n".join(parts).strip()


def _append_preview_part(
    parts: list[str],
    text: str,
    *,
    kind: str,
    prev_kind: str | None,
    pending_blank: bool,
) -> None:
    if not text:
        return
    if parts and pending_blank and prev_kind in {"paragraph", "blockquote", "pre"} and kind in {"paragraph", "blockquote", "pre"}:
        parts.append("")
    parts.append(text)


def _render_inline(text: str) -> str:
    if not text:
        return ""
    pieces: list[str] = []
    idx = 0
    patterns = [
        ("link", _LINK_RE),
        ("code", _CODE_SPAN_RE),
        ("spoiler", _SPOILER_RE),
        ("strike", _STRIKE_RE),
        ("bold", _BOLD_RE),
        ("italic", _ITALIC_RE),
    ]

    while idx < len(text):
        earliest_kind = None
        earliest_match = None
        for kind, pattern in patterns:
            match = pattern.search(text, idx)
            if match is None:
                continue
            if earliest_match is None or match.start() < earliest_match.start():
                earliest_kind = kind
                earliest_match = match
        if earliest_match is None:
            pieces.append(html.escape(text[idx:]))
            break
        if earliest_match.start() > idx:
            pieces.append(html.escape(text[idx:earliest_match.start()]))
        pieces.append(_render_inline_match(earliest_kind or "", earliest_match))
        idx = earliest_match.end()
    return "".join(pieces)


def _render_inline_match(kind: str, match: re.Match[str]) -> str:
    if kind == "link":
        label = _render_inline(match.group(1))
        href = html.escape(match.group(2), quote=True)
        return f'<a href="{href}">{label}</a>'
    if kind == "code":
        return f"<code>{html.escape(match.group(1))}</code>"
    if kind == "spoiler":
        return f"<tg-spoiler>{_render_inline(match.group(1))}</tg-spoiler>"
    if kind == "strike":
        return f"<s>{_render_inline(match.group(1))}</s>"
    if kind == "bold":
        return f"<b>{_render_inline(match.group(2))}</b>"
    if kind == "italic":
        inner = match.group(1) or match.group(2) or ""
        return f"<i>{_render_inline(inner)}</i>"
    return html.escape(match.group(0))
