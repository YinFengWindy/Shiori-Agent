from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shiori_sdk.lifecycle import AfterReasoningCtx, PromptRenderCtx
from shiori_sdk.prompting import PromptSectionRender
from .runtime import (
    MemeCatalog,
    RoleReactionCatalog,
    RoleReactionDecorator,
    load_common_emojis,
)

if TYPE_CHECKING:
    from shiori_sdk.plugin_services import ServicePluginContext as PluginRuntimeContext
    from shiori_sdk.sessions import PluginSessions
    from shiori_sdk.roles import Roles
    from shiori_sdk.processes import Resources

_CTX_SLOT = "prompt:ctx"
_MEME_RE = re.compile(r"<meme:([a-zA-Z0-9_-]+)>", re.IGNORECASE)
_MEME_PROTOCOL_RE = re.compile(r"<meme:[^>]*>", re.IGNORECASE)
_EMOJI_PROTOCOL_RE = re.compile(r"<emoji:([a-zA-Z0-9_-]+)>", re.IGNORECASE)


class MemePromptModule:
    """Append available role reactions after prompt context emission."""

    slot = "meme.prompt"
    requires = ("prompt_render.emit", _CTX_SLOT)
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


class _MemeReactions:
    def __init__(
        self,
        workspace: Path,
        session_manager: "PluginSessions | None",
        roles: "Roles",
        resources: "Resources",
        catalog: Path,
    ) -> None:
        self._emoji_paths = resources.common_emojis(workspace)
        self._session_manager = session_manager
        self._role_catalog = RoleReactionCatalog(roles, MemeCatalog(catalog))
        self._role_decorator = RoleReactionDecorator(
            self._role_catalog,
            load_common_emojis(self._emoji_paths),
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
            emojis=(load_common_emojis(self._emoji_paths) if role_id else {}),
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
    reactions = _MemeReactions(
        ctx.workspace,
        ctx.sessions,
        ctx.roles,
        ctx.resources,
        ctx.storage.migrate_data(
            ctx.workspace, "meme", "library", ctx.workspace / "memes"
        ),
    )
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
