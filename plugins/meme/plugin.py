from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from agent.lifecycle.types import AfterReasoningCtx, PromptRenderCtx
from agent.plugins import Plugin, on_after_reasoning
from agent.prompting import PromptSectionRender
from .runtime import (
    MemeCatalog,
    MemeDecorator,
    RoleReactionCatalog,
    RoleReactionDecorator,
    load_common_emojis,
)

_CTX_SLOT = "prompt:ctx"
_MEME_RE = re.compile(r"<meme:([a-zA-Z0-9_-]+)>", re.IGNORECASE)
_MEME_PROTOCOL_RE = re.compile(r"<meme:[^>]*>", re.IGNORECASE)
_EMOJI_PROTOCOL_RE = re.compile(r"<emoji:([a-zA-Z0-9_-]+)>", re.IGNORECASE)


class MemePromptModule:
    slot = "meme.prompt"
    requires = ("prompt_render.emit", "citation.prompt", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, plugin: "MemePlugin") -> None:
        self._plugin = plugin

    async def run(self, frame: Any) -> Any:
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


class MemePlugin(Plugin):
    name = "meme"
    _catalog: Any = None
    _decorator: Any = None
    _role_catalog: Any = None
    _role_decorator: Any = None

    async def initialize(self) -> None:
        memes_dir = _workspace(self.context.plugin_dir, self.context.workspace) / "memes"
        self._catalog = MemeCatalog(memes_dir)
        self._decorator = MemeDecorator(self._catalog)
        workspace = _workspace(self.context.plugin_dir, self.context.workspace)
        self._role_catalog = RoleReactionCatalog(workspace, self._catalog)
        self._role_decorator = RoleReactionDecorator(
            self._role_catalog,
            load_common_emojis(workspace),
        )

    def prompt_render_modules(self) -> list[object]:
        return [MemePromptModule(self)]

    @on_after_reasoning()
    async def decorate_meme(self, ctx: AfterReasoningCtx) -> AfterReasoningCtx:
        role_id = self._role_id_for_session(ctx.session_key)
        cleaned, tag = _extract_meme_tag(ctx.reply)
        cleaned = _resolve_emoji_protocols(
            cleaned,
            self.role_decorator.resolve_emoji if role_id else lambda _name: "",
        )
        decorated = self.role_decorator.decorate(
            cleaned,
            role_id=role_id,
            meme_tag=tag,
        )
        ctx.reply = decorated.content
        ctx.media.extend(decorated.media)
        ctx.meme_tag = decorated.tag
        return ctx

    @property
    def catalog(self) -> Any:
        if self._catalog is None:
            raise RuntimeError("meme 插件尚未初始化")
        return self._catalog

    @property
    def decorator(self) -> Any:
        if self._decorator is None:
            raise RuntimeError("meme 插件尚未初始化")
        return self._decorator

    @property
    def role_decorator(self) -> Any:
        if self._role_decorator is None:
            raise RuntimeError("meme 插件尚未初始化")
        return self._role_decorator

    def build_prompt_block(self, role_id: str) -> str | None:
        if self._role_catalog is None:
            raise RuntimeError("meme 插件尚未初始化")
        return self._role_catalog.build_prompt_block(
            role_id=role_id,
            emojis=(
                load_common_emojis(_workspace(self.context.plugin_dir, self.context.workspace))
                if role_id
                else {}
            ),
        )

    def _role_id_for_session(self, session_key: str) -> str:
        manager = self.context.session_manager
        if manager is None:
            return ""
        session = manager.get_or_create(session_key)
        metadata = session.metadata if isinstance(session.metadata, dict) else {}
        return str(metadata.get("role_id") or "").strip()


def _extract_meme_tag(response: str) -> tuple[str, str | None]:
    first = _MEME_RE.search(response)
    cleaned = _MEME_PROTOCOL_RE.sub("", response).strip()
    if first is None:
        return cleaned, None
    return cleaned, first.group(1).lower()


def _resolve_emoji_protocols(response: str, resolver: Any) -> str:
    return _EMOJI_PROTOCOL_RE.sub(
        lambda match: str(resolver(match.group(1)) or ""),
        response,
    ).strip()


def _workspace(plugin_dir: Path, configured: Path | None) -> Path:
    if configured is not None:
        return configured
    return cast(Path, plugin_dir.parent.parent)
