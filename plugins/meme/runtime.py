from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from core.roles import RoleStore

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _empty_aliases() -> list[str]:
    return []


def _empty_media() -> list[str]:
    return []


@dataclass
class MemeCategory:
    name: str
    desc: str
    aliases: list[str] = field(default_factory=_empty_aliases)
    enabled: bool = True


@dataclass
class DecorateResult:
    content: str
    media: list[str] = field(default_factory=_empty_media)
    tag: str | None = None


class MemeCatalog:
    def __init__(self, memes_dir: Path) -> None:
        self._dir = memes_dir
        self._categories: dict[str, MemeCategory] = {}
        self._manifest_mtime: float = -1.0

    def _load(self) -> None:
        manifest = self._dir / "manifest.json"
        if not manifest.exists():
            self._categories = {}
            self._manifest_mtime = -1.0
            return
        mtime = manifest.stat().st_mtime
        if mtime == self._manifest_mtime:
            return
        self._manifest_mtime = mtime
        self._categories = {}
        try:
            raw: object = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        data = cast(dict[str, object], raw)
        categories = data.get("categories")
        if not isinstance(categories, dict):
            return
        categories_map = cast(dict[object, object], categories)
        for raw_name, raw_info in categories_map.items():
            if not isinstance(raw_name, str) or not isinstance(raw_info, dict):
                continue
            info = cast(dict[str, object], raw_info)
            aliases = info.get("aliases", [])
            alias_items = cast(list[object], aliases) if isinstance(aliases, list) else []
            self._categories[raw_name] = MemeCategory(
                name=raw_name,
                desc=str(info.get("desc", "") or ""),
                aliases=[str(item) for item in alias_items],
                enabled=bool(info.get("enabled", True)),
            )

    def get_enabled_categories(self) -> list[MemeCategory]:
        self._load()
        return [c for c in self._categories.values() if c.enabled]

    def pick_image(self, tag: str) -> str | None:
        self._load()
        tag = tag.lower()
        cat = self._categories.get(tag)
        if cat is None or not cat.enabled:
            return None
        cat_dir = self._dir / tag
        if not cat_dir.is_dir():
            return None
        images = [f for f in cat_dir.iterdir() if f.suffix.lower() in _IMAGE_SUFFIXES]
        if not images:
            return None
        return str(random.choice(images))

    def build_prompt_block(self) -> str | None:
        cats = self.get_enabled_categories()
        if not cats:
            return None
        lines = [
            '【表情协议】`<meme:tag>` 是系统内置回复格式标记，不是 emoji（Unicode 表情符号），不受【禁止 emoji】规则限制。',
            "",
            "可用表情类别：",
        ]
        for cat in cats:
            lines.append(f"- {cat.name}: {cat.desc}")
        lines += [
            "",
            "这是内置表情协议，不是工具能力。",
            '需要发表情时，直接在回复末尾插入 <meme:category>；不要调用任何工具去"生成表情""搜索表情包""发送图片"。',
            "每条回复最多 1 个 <meme:category>，放在整条回复的最末尾（颜文字之后也算末尾，可以紧跟颜文字后面加）。",
            '用户明确说"发个表情""用表情表达你的心情""来个表情包""给我一个表情"时，优先使用 <meme:category> 响应。',
            "用户直球表达喜欢、夸你、气氛暧昧或明显害羞时，也优先在结尾加 <meme:category>，即使已经用了颜文字也要加。",
            "严肃任务、代码解释、工具结果、查资料、执行指令时不使用。",
            "注意：历史会话中助手未使用 <meme:> 不代表本轮不需要用，以上规则优先于历史回复模式。",
            "",
            "<example>",
            "对方说：最喜欢你了 → 回复结尾加 <meme:shy>",
            "对方说：我好喜欢你 → 回复结尾加 <meme:shy>",
            "对方说：akashic你真好 → 回复结尾加 <meme:shy>",
            "对方说：你真好 → 回复结尾加 <meme:shy>",
            "对方说：你今天好棒 → 回复结尾加 <meme:shy>",
            "对方说：谢谢你今天帮了我好多 → 回复结尾加 <meme:shy> 或 <meme:happy>",
            "对方说：你好可爱 → 回复结尾加 <meme:shy>",
            "已经用了颜文字、对方直球说喜欢 → 还是加 <meme:shy>",
            "对方说：给我发个表情表达你的心情 → 正文后直接加 <meme:shy>",
            "对方说：来个表情包 → 不找工具，直接回复并加 <meme:happy> 或 <meme:shy>",
            "任务完成、对方说谢谢 → 回复结尾加 <meme:happy>",
            "轻松聊天、说了个小笑话 → 回复结尾加 <meme:clever>",
            "被夸、被顺毛、被直球关心 → 回复结尾加 <meme:shy>",
            "被戳穿、说错话后 → 回复结尾加 <meme:awkward>",
            "帮忙查资料、执行了指令 → 不加",
            "用户要表情 → 不调用 tool_search，不调用任何工具",
            "</example>",
        ]
        return "\n".join(lines)


class MemeDecorator:
    def __init__(self, catalog: MemeCatalog) -> None:
        self._catalog = catalog

    def decorate(self, content: str, *, meme_tag: str | None = None) -> DecorateResult:
        cleaned = content.strip()
        if meme_tag is None:
            return DecorateResult(content=cleaned)
        tag = meme_tag.lower()
        image = self._catalog.pick_image(tag)
        media = [image] if image else []
        return DecorateResult(content=cleaned, media=media, tag=tag)


class RoleReactionCatalog:
    """Resolves role-owned sendable assets while retaining the legacy meme catalog."""

    def __init__(self, workspace: Path, legacy_catalog: MemeCatalog) -> None:
        self._roles = RoleStore(workspace)
        self._legacy = legacy_catalog

    def build_prompt_block(
        self,
        *,
        role_id: str,
        emojis: dict[str, str],
    ) -> str | None:
        role_categories = self._sendable_categories(role_id)
        if not role_categories and not emojis:
            return self._legacy.build_prompt_block()

        lines = [
            "【角色表情协议】以下协议是系统内部输出格式，不是工具调用。",
            "普通聊天中可以根据场景自主使用；严肃任务、代码解释和工具结果中不要主动使用。",
        ]
        if role_categories:
            lines.extend(
                [
                    "",
                    "当前角色可发送的图片分类：",
                    *[
                        f"- {category_id}: {category_name}"
                        for category_id, category_name in role_categories
                    ],
                    "需要发送图片时，在回复最末尾添加 `<meme:分类ID>`。每次回复最多一个图片协议。",
                    "图片会在文字消息之后单独发送，不要描述发送过程。",
                ]
            )
        if emojis:
            lines.extend(
                [
                    "",
                    "全局允许的 emoji：",
                    *[f"- {name}: {value}" for name, value in emojis.items()],
                    "需要使用 emoji 时输出 `<emoji:名称>`，系统会替换成对应字符。",
                    "这里只允许使用上方协议列出的 emoji；该内部协议优先于其他禁止 Unicode emoji 的规则。",
                ]
            )
        lines.extend(
            [
                "",
                '用户明确要求表情、表情包或用表情表达心情时，优先选择合适的已有协议。',
                "历史回复没有使用表情不代表本轮不能使用。",
            ]
        )
        return "\n".join(lines)

    def pick_image(self, *, role_id: str, tag: str) -> str | None:
        role = self._roles.get_role(role_id) if role_id else None
        if role is not None:
            category = next(
                (
                    item
                    for item in role.asset_categories
                    if item.id.lower() == tag.lower()
                ),
                None,
            )
            if category is not None and not category.allow_role_send:
                return None
            if category is not None:
                candidates = [
                    self._roles.roles_dir / path
                    for path in role.illustrations
                    if role.asset_category_bindings.get(path) == category.id
                    and (self._roles.roles_dir / path).is_file()
                    and (self._roles.roles_dir / path).suffix.lower() in _IMAGE_SUFFIXES
                ]
                return str(random.choice(candidates)) if candidates else None
        return self._legacy.pick_image(tag)

    def _sendable_categories(self, role_id: str) -> list[tuple[str, str]]:
        role = self._roles.get_role(role_id) if role_id else None
        if role is None:
            return []
        available_category_ids = {
            role.asset_category_bindings.get(path)
            for path in role.illustrations
            if (self._roles.roles_dir / path).is_file()
        }
        return [
            (category.id, category.name)
            for category in role.asset_categories
            if category.allow_role_send and category.id in available_category_ids
        ]


class RoleReactionDecorator:
    """Decorates one role reply with validated emoji and at most one image."""

    def __init__(self, catalog: RoleReactionCatalog, emojis: dict[str, str]) -> None:
        self._catalog = catalog
        self._emojis = dict(emojis)

    def decorate(
        self,
        content: str,
        *,
        role_id: str,
        meme_tag: str | None,
    ) -> DecorateResult:
        tag = meme_tag.lower() if meme_tag else None
        image = self._catalog.pick_image(role_id=role_id, tag=tag) if tag else None
        return DecorateResult(
            content=content.strip(),
            media=[image] if image else [],
            tag=tag,
        )

    def resolve_emoji(self, name: str) -> str:
        return self._emojis.get(name.lower(), "")
