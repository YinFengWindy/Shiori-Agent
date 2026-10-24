from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from shiori_sdk.core.conversation import PromptRendering, ReasoningFinished
from shiori_sdk.prompting import PromptSectionRender
from shiori_sdk.storage import plugin_data_dir
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

_MEME_RE = re.compile(r"<meme:([a-zA-Z0-9_-]+)>", re.IGNORECASE)
_MEME_PROTOCOL_RE = re.compile(r"<meme:[^>]*>", re.IGNORECASE)
_EMOJI_PROTOCOL_RE = re.compile(r"<emoji:([a-zA-Z0-9_-]+)>", re.IGNORECASE)


class _MemeReactions:
    def __init__(
        self,
        workspace: Path,
        session_manager: "PluginSessions",
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

    async def append_prompt(self, event: PromptRendering) -> PromptRendering:
        """Lists the current role's available reactions at the prompt's bottom."""
        role_id = str(event.session_metadata.get("role_id") or "").strip()
        block = self.build_prompt_block(role_id)
        if not block:
            return event
        section = PromptSectionRender(
            name="memes", content=f"# Memes\n\n{block}", is_static=False
        )
        return replace(
            event, system_sections_bottom=(*event.system_sections_bottom, section)
        )

    async def decorate_meme(self, event: ReasoningFinished) -> ReasoningFinished:
        """Resolve image and emoji protocols on each bubble before the core cleanup."""
        role_id = self._role_id_for_session(event.session_key)
        resolve = self._role_decorator.resolve_emoji if role_id else lambda _name: ""
        texts = event.reply_messages or (event.reply,)
        rewritten: list[str] = []
        media = list(event.media)
        meme_tag: str | None = None
        attached = False
        for text in texts:
            cleaned, tag = _extract_meme_tag(text)
            cleaned = _resolve_emoji_protocols(cleaned, resolve)
            use_tag = tag if tag and not attached else None
            decorated = self._role_decorator.decorate(
                cleaned, role_id=role_id, meme_tag=use_tag
            )
            if use_tag:
                attached = True
                media.extend(decorated.media)
                meme_tag = decorated.tag
            rewritten.append(decorated.content)
        if event.reply_messages:
            return replace(
                event,
                reply_messages=tuple(rewritten),
                reply="\n\n".join(rewritten),
                media=tuple(media),
                meme_tag=meme_tag,
            )
        return replace(event, reply=rewritten[0], media=tuple(media), meme_tag=meme_tag)

    def build_prompt_block(self, role_id: str) -> str | None:
        """Render the available role images and shared emoji catalog."""
        return self._role_catalog.build_prompt_block(
            role_id=role_id,
            emojis=(load_common_emojis(self._emoji_paths) if role_id else {}),
        )

    def _role_id_for_session(self, session_key: str) -> str:
        session = self._session_manager.get_or_create(session_key)
        metadata = session.metadata if isinstance(session.metadata, dict) else {}
        return str(metadata.get("role_id") or "").strip()


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Register prompt and reply contributions within the plugin effect scope."""
    reactions = _MemeReactions(
        ctx.workspace,
        ctx.sessions,
        ctx.roles,
        ctx.resources,
        plugin_data_dir(ctx.workspace, "meme") / "library",
    )
    ctx.on(PromptRendering, reactions.append_prompt)
    # Runs on ReasoningFinished, before the core's post-chain check removes
    # unconsumed protocol tags.
    ctx.on(ReasoningFinished, reactions.decorate_meme)


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
