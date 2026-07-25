from __future__ import annotations

import re


def split_tts_sentences(text: str, *, max_length: int = 80) -> list[str]:
    """Removes non-spoken markup and creates bounded sentence-sized TTS jobs."""

    cleaned = _strip_tts_markup(text)
    if not cleaned:
        return []
    chunks = [
        part.strip()
        for part in re.split(r"(?<=[。！？；!?;])\s*|\n+", cleaned)
        if part.strip()
    ]
    result: list[str] = []
    for chunk in chunks:
        while len(chunk) > max_length:
            split_at = max(
                chunk.rfind("，", 0, max_length + 1),
                chunk.rfind(",", 0, max_length + 1),
            )
            if split_at <= 0:
                split_at = max_length
            comma_at = split_at < len(chunk) and chunk[split_at] in {"，", ","}
            result.append(chunk[: split_at + (1 if comma_at else 0)].strip())
            chunk = chunk[split_at + (1 if comma_at else 0) :].strip()
        if chunk:
            result.append(chunk)
    return result


class TtsSentenceBuffer:
    """Buffers streamed reply text into bounded, spoken sentence units."""

    def __init__(self, *, max_length: int = 80) -> None:
        self._max_length = max_length
        self._buffer = ""

    def push(self, content_delta: str) -> list[str]:
        """Returns only sentences made complete by this content delta."""

        if content_delta:
            self._buffer += content_delta
        return self._drain(final=False)

    def finish(self) -> list[str]:
        """Flushes the final sentence after the assistant turn commits."""

        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[str]:
        result: list[str] = []
        while self._buffer:
            visible = _strip_unclosed_code_block(self._buffer)
            if not visible:
                break
            boundary = _find_sentence_boundary(visible)
            if boundary is None:
                normalized = _strip_tts_markup(visible)
                if len(normalized) <= self._max_length and not final:
                    break
                cut = _find_bounded_cut(visible, self._max_length)
                if cut is None:
                    if not final:
                        break
                    result.extend(
                        split_tts_sentences(
                            self._buffer,
                            max_length=self._max_length,
                        )
                    )
                    self._buffer = ""
                    break
                candidate = self._buffer[:cut]
                self._buffer = self._buffer[cut:]
                result.extend(
                    split_tts_sentences(candidate, max_length=self._max_length)
                )
                continue

            end = boundary + 1
            candidate = self._buffer[:end]
            self._buffer = self._buffer[end:]
            result.extend(split_tts_sentences(candidate, max_length=self._max_length))
        return result


def _strip_tts_markup(text: str) -> str:
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"!\[[^]]*\]\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"(^|\n)\s{0,3}#+\s*", r"\1", cleaned)
    cleaned = re.sub(r"[*_~]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _strip_unclosed_code_block(text: str) -> str:
    fences = list(re.finditer(r"```", text))
    if len(fences) % 2 == 0:
        return text
    return text[: fences[-1].start()]


def _find_sentence_boundary(text: str) -> int | None:
    fences = [match.start() for match in re.finditer(r"```", text)]
    code_ranges = list(zip(fences[0::2], fences[1::2]))
    for match in re.finditer(r"[。！？；!?;.\n]", text):
        if any(start < match.start() < end for start, end in code_ranges):
            continue
        return match.start()
    return None


def _find_bounded_cut(text: str, max_length: int) -> int | None:
    normalized = _strip_tts_markup(text)
    if len(normalized) <= max_length:
        return None
    prefix = text[:max_length]
    comma = max(prefix.rfind("，"), prefix.rfind(","))
    return (comma + 1) if comma >= 0 else max_length
