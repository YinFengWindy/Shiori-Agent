"""The role's ``PROACTIVE_CONTEXT.md``: the user's standing rules for proactive messages."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROACTIVE_CONTEXT_FILE = "PROACTIVE_CONTEXT.md"
_TEMPLATE = """# Proactive Context

在这里写用户当前对主动推送的明确要求和规则。

- 主 agent 负责维护这份文件。
- proactive agent 每轮都会读取它,并把它视为需要遵守的规则,不是普通参考建议。
- 这里适合写白名单、黑名单、过滤条件、优先级、必须先验证的步骤。
- 这里不提供新闻事实,不提供候选内容,只定义规则。
- 写结论即可,不要写冗长过程。
"""


class ProactiveContextPanel:
    """Creates the file from its template once and rereads it when it changes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime_ns: int | None = None
        self._text = ""

    def ensure(self) -> None:
        """Writes the template when the file does not exist yet."""
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_TEMPLATE, encoding="utf-8")

    def read(self) -> str:
        """The current rules; the last good text when the file cannot be read."""
        self.ensure()
        try:
            mtime_ns = int(self.path.stat().st_mtime_ns)
            if self._mtime_ns == mtime_ns:
                return self._text
            text = self.path.read_text(encoding="utf-8").strip()
            self._mtime_ns = mtime_ns
            self._text = text
            return text
        except Exception as e:
            logger.warning("[proactive] 读取 workspace proactive context 失败: %s", e)
            return self._text
