from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.lifecycle.types import AfterReasoningCtx, PromptRenderCtx
from agent.prompting import PromptSectionRender
from .runtime import (
    MemeCatalog,
    RoleReactionCatalog,
    RoleReactionDecorator,
    load_common_emojis,
)

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext
    from session.manager import SessionManager

_CTX_SLOT = "prompt:ctx"
_MEME_RE = re.compile(r"<meme:([a-zA-Z0-9_-]+)>", re.IGNORECASE)
_MEME_PROTOCOL_RE = re.compile(r"<meme:[^>]*>", re.IGNORECASE)
_EMOJI_PROTOCOL_RE = re.compile(r"<emoji:([a-zA-Z0-9_-]+)>", re.IGNORECASE)


class MemePromptModule:
    """Append role reactions after citation's prompt protocol."""

    slot = "meme.prompt"
    requires = ("prompt_render.emit", "citation.prompt", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, plugin: "_MemeReactions") -> None:
        self._plugin = plugin

    async def run(self, frame: Any) -> Any:
        """Contribute the current role's available reactions to the prompt."""
        ctx = frame.slots.get(_CTX_SLOT)
        if not isinstance(ctx, PromptRenderCtx):
            return frame
        role_id = str(ctx.session_metadata.get("role_id") or "").strip()
        block = self._plugin.build_prompt_block(role_id)
        if not block:
            return frame
        ctx.system_sections_bottom.append(
            PromptSectionRender(
                name="memes",
                content=f"# Memes\n\n{block}",
                is_static=False,
            )
        )
        return frame


def _private_catalog(workspace: Path) -> Path:
    from agent.plugin_host.data_migration import migrate_private_data

    return migrate_private_data(workspace, "meme", "library", workspace / "memes")


class _MemeReactions:
    def __init__(
        self, workspace: Path, session_manager: "SessionManager | None"
    ) -> None:
        self._workspace = workspace
        self._session_manager = session_manager
        self._role_catalog = RoleReactionCatalog(
            workspace, MemeCatalog(_private_catalog(workspace))
        )
        self._role_decorator = RoleReactionDecorator(
            self._role_catalog,
            load_common_emojis(workspace),
        )

    async def decorate_meme(self, ctx: AfterReasoningCtx) -> AfterReasoningCtx:
        """Resolve image and emoji protocols before citation cleans leftover tags."""
        role_id = self._role_id_for_session(ctx.session_key)
        cleaned, tag = _extract_meme_tag(ctx.reply)
        cleaned = _resolve_emoji_protocols(
            cleaned,
            self._role_decorator.resolve_emoji if role_id else lambda _name: "",
        )
        decorated = self._role_decorator.decorate(
            cleaned,
            role_id=role_id,
            meme_tag=tag,
        )
        ctx.reply = decorated.content
        ctx.media.extend(decorated.media)
        ctx.meme_tag = decorated.tag
        return ctx

    def build_prompt_block(self, role_id: str) -> str | None:
        """Render the available role images and shared emoji catalog."""
        return self._role_catalog.build_prompt_block(
            role_id=role_id,
            emojis=(load_common_emojis(self._workspace) if role_id else {}),
        )

    def _role_id_for_session(self, session_key: str) -> str:
        manager = self._session_manager
        if manager is None:
            return ""
        session = manager.get_or_create(session_key)
        metadata = session.metadata if isinstance(session.metadata, dict) else {}
        return str(metadata.get("role_id") or "").strip()


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Register prompt and reply contributions within the plugin effect scope."""
    if ctx.workspace is None:
        raise ValueError("meme 插件需要 workspace")
    reactions = _MemeReactions(ctx.workspace, ctx.session_manager)
    ctx.lifecycle.contribute("prompt_render", [MemePromptModule(reactions)])
    # The scoped event runs inside after_reasoning.emit, before citation's
    # protocol_cleanup stage can consume valid meme/emoji tags.
    ctx.events.on(AfterReasoningCtx, reactions.decorate_meme)


def _extract_meme_tag(response: str) -> tuple[str, str | None]:
    first = _MEME_RE.search(response)
    cleaned = _MEME_PROTOCOL_RE.sub("", response).strip()
    if first is None:
        return cleaned, None
    return cleaned, first.group(1).lower()


def _resolve_emoji_protocols(response: str, resolver: Callable[[str], str]) -> str:
    return _EMOJI_PROTOCOL_RE.sub(
        lambda match: str(resolver(match.group(1)) or ""),
        response,
    ).strip()
