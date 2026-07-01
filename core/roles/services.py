from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from infra.persistence.json_store import atomic_save_json, load_json
from session.manager import Session, SessionManager

from .store import RoleRecord, RoleStore

_BINDINGS_VERSION = 1


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _clean_role_id(role_id: str) -> str:
    clean = str(role_id).strip()
    if not clean:
        raise ValueError("role_id 不能为空")
    return clean


def _binding_key(channel: str, chat_id: str) -> str:
    clean_channel = str(channel).strip()
    clean_chat_id = str(chat_id).strip()
    if not clean_channel:
        raise ValueError("channel 不能为空")
    if not clean_chat_id:
        raise ValueError("chat_id 不能为空")
    return f"{clean_channel}:{clean_chat_id}"


class RoleSelfSeedGenerator(Protocol):
    def generate(self, role: "RoleRecord") -> str: ...


@dataclass(frozen=True)
class RoleAggregate:
    """角色聚合入口返回的完整业务上下文。"""

    role: RoleRecord
    session: Session
    memory_root: Path


@dataclass(frozen=True)
class RoleRequest:
    """业务层角色请求模型，入口必须显式携带 role_id。"""

    request_id: str
    role_id: str
    source: str
    channel: str
    chat_id: str
    sender_id: str = ""
    action: str = ""
    payload: dict[str, Any] | None = None
    runtime_flags: dict[str, Any] | None = None
    request_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class RoleChannelBinding:
    """旧渠道到角色的绑定关系。"""

    channel: str
    chat_id: str
    role_id: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "role_id": self.role_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoleChannelBinding":
        return cls(
            channel=str(payload.get("channel") or "").strip(),
            chat_id=str(payload.get("chat_id") or "").strip(),
            role_id=str(payload.get("role_id") or "").strip(),
            created_at=str(payload.get("created_at") or _now_iso()),
            updated_at=str(payload.get("updated_at") or _now_iso()),
        )


class RoleRepository:
    """角色资料、运行配置与初始化状态的 owning repository。"""

    def __init__(self, store: RoleStore) -> None:
        self._store = store

    @property
    def store(self) -> RoleStore:
        return self._store

    def list_roles(self) -> list[RoleRecord]:
        return self._store.list_roles()

    def get_required(self, role_id: str) -> RoleRecord:
        clean_role_id = _clean_role_id(role_id)
        role = self._store.get_role(clean_role_id)
        if role is None:
            raise KeyError(f"role 不存在: {clean_role_id}")
        return role

    def create_role(
        self,
        *,
        role_id: str | None = None,
        name: str,
        system_prompt: str,
        description: str = "",
        background: str = "",
        runtime_config: dict[str, Any] | None = None,
        avatar_source: str | Path | None = None,
        illustration_sources: list[str | Path] | None = None,
    ) -> RoleRecord:
        return self._store.create_role(
            name=name,
            description=description,
            system_prompt=system_prompt,
            background=background,
            runtime_config=runtime_config,
            role_id=role_id,
            avatar_source=avatar_source,
            illustration_sources=illustration_sources,
        )

    def update_role(
        self,
        role_id: str,
        **updates: Any,
    ) -> RoleRecord:
        _ = self.get_required(role_id)
        return self._store.update_role(role_id, **updates)

    def delete_role(self, role_id: str) -> bool:
        _ = self.get_required(role_id)
        return self._store.delete_role(role_id)


class RoleSessionService:
    """角色唯一长期会话服务。"""

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    def derive_session_key(self, role_id: str) -> str:
        return self._session_manager.role_session_key(_clean_role_id(role_id))

    def open_by_role(self, role: RoleRecord) -> Session:
        return self._session_manager.sync_role_session_metadata(
            role.id,
            role_name=role.name,
            role_prompt=role.system_prompt,
            role_runtime_config=role.runtime_config,
            valid_illustrations=list(role.illustrations),
        )

    def load_history(self, role_id: str) -> list[dict[str, Any]]:
        session = self._session_manager.get_or_create(self.derive_session_key(role_id))
        return list(session.messages)

    def clear(self, role_id: str) -> Session:
        session = self._session_manager.get_or_create(self.derive_session_key(role_id))
        session.clear()
        self._session_manager.save(session)
        return session

    def update_display_state(
        self,
        role: RoleRecord,
        *,
        active_illustration: str | None,
    ) -> Session:
        session = self._session_manager.update_role_session_display_state(
            role.id,
            active_illustration=active_illustration,
        )
        return self.open_by_role(role) if session.metadata.get("role_name") != role.name else session

    def delete(self, role_id: str) -> bool:
        return self._session_manager.delete_role_session(_clean_role_id(role_id))


class RoleMemoryService:
    """角色独立记忆空间服务。"""

    _FILES = (
        "MEMORY.md",
        "SELF.md",
        "HISTORY.md",
        "PENDING.md",
        "RECENT_CONTEXT.md",
    )

    def __init__(
        self,
        workspace: Path,
        *,
        self_seed_generator: RoleSelfSeedGenerator | None = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._self_seed_generator = self_seed_generator

    def memory_root(self, role_id: str) -> Path:
        return self._workspace / "roles" / _clean_role_id(role_id) / "memory"

    def ensure_initialized(self, role: RoleRecord) -> Path:
        root = self.memory_root(role.id)
        root.mkdir(parents=True, exist_ok=True)
        for filename in self._FILES:
            path = root / filename
            if not path.exists():
                path.write_text("", encoding="utf-8")
        return root

    def seed_role_memory(self, role: RoleRecord) -> dict[str, Any]:
        """同步初始化角色记忆，供非事件循环调用方使用。"""
        root = self.ensure_initialized(role)
        state = dict(role.memory_init_state or {})
        changed = False

        self_path = root / "SELF.md"
        self_text = self_path.read_text(encoding="utf-8").strip() if self_path.exists() else ""
        if not self_text and self._self_seed_generator is not None:
            seeded_self = str(self._self_seed_generator.generate(role) or "").strip()
            if seeded_self:
                self_path.write_text(seeded_self + "\n", encoding="utf-8")
                state["seed_self_ready"] = True
                changed = True

        return self._finalize_seed_state(role, root, state, changed)

    async def seed_role_memory_async(self, role: RoleRecord) -> dict[str, Any]:
        """异步初始化角色记忆，避免在运行中的事件循环里再次调用 asyncio.run。"""
        root = self.ensure_initialized(role)
        state = dict(role.memory_init_state or {})
        changed = False

        self_path = root / "SELF.md"
        self_text = self_path.read_text(encoding="utf-8").strip() if self_path.exists() else ""
        if not self_text and self._self_seed_generator is not None:
            seeded_self = str(await self._generate_self_async(role) or "").strip()
            if seeded_self:
                self_path.write_text(seeded_self + "\n", encoding="utf-8")
                state["seed_self_ready"] = True
                changed = True

        return self._finalize_seed_state(role, root, state, changed)

    def _finalize_seed_state(
        self,
        role: RoleRecord,
        root: Path,
        state: dict[str, Any],
        changed: bool,
    ) -> dict[str, Any]:
        background = role.background.strip()
        previous_background = str(state.get("seed_background_value") or "").strip()
        if background and background != previous_background and not state.get("seed_self_ready"):
            self._write_stable_background(root / "SELF.md", background)
            if previous_background:
                self._append_once(
                    root / "HISTORY.md",
                    (
                        "# 角色背景修订\n\n"
                        f"来源: user_edited\n"
                        f"旧版本: {previous_background}\n"
                        f"新版本: {background}\n"
                    ),
                )
            state["seed_background_ready"] = True
            state["seed_background_value"] = background
            changed = True

        if not state.get("seed_first_impression_ready"):
            impression = self._build_first_impression(role)
            state = self.update_relationship_baseline(
                role,
                content=impression,
                source="seed:first_impression",
                current_state=state,
            )
            changed = True

        if changed:
            state["last_memory_initialized_at"] = _now_iso()
        return state

    async def _generate_self_async(self, role: RoleRecord) -> str:
        generator = self._self_seed_generator
        if generator is None:
            return ""
        agenerate = getattr(generator, "agenerate", None)
        if callable(agenerate):
            return str(await agenerate(role) or "")
        return str(await asyncio.to_thread(generator.generate, role) or "")

    def update_relationship_baseline(
        self,
        role: RoleRecord,
        *,
        content: str,
        source: str,
        current_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_content = str(content or "").strip()
        clean_source = str(source or "").strip()
        if not clean_content:
            raise ValueError("relationship baseline 不能为空")
        if not clean_source:
            raise ValueError("relationship baseline source 不能为空")

        state = dict(current_state or role.memory_init_state or {})
        root = self.ensure_initialized(role)
        path = root / "MEMORY.md"
        current_value = str(state.get("relationship_baseline_value") or "").strip()
        current_source = str(state.get("relationship_baseline_source") or "").strip()
        normalized_source = "seed" if clean_source.startswith("seed") else clean_source

        if normalized_source == "system_derived" and current_source == "user_edited":
            self._append_once(
                root / "HISTORY.md",
                (
                    "# 关系记忆演化建议\n\n"
                    f"来源: {clean_source}\n"
                    f"保留当前人工基线: {current_value}\n"
                    f"系统建议: {clean_content}\n"
                ),
            )
            state["relationship_revision_count"] = int(
                state.get("relationship_revision_count") or 0
            ) + 1
            return state

        if clean_content == current_value and clean_source == current_source:
            return state

        if current_value:
            self._append_once(
                root / "HISTORY.md",
                (
                    "# 关系基线修订\n\n"
                    f"来源: {clean_source}\n"
                    f"旧版本来源: {current_source or 'unknown'}\n"
                    f"旧版本内容: {current_value}\n"
                    f"新版本内容: {clean_content}\n"
                ),
            )
            if normalized_source != "seed":
                state["relationship_revision_count"] = int(
                    state.get("relationship_revision_count") or 0
                ) + 1
        else:
            state.setdefault("relationship_revision_count", 0)

        self._write_relationship_baseline(path, clean_content, clean_source)
        state["seed_first_impression_ready"] = True
        state["relationship_baseline_value"] = clean_content
        state["relationship_baseline_source"] = clean_source
        state["last_memory_initialized_at"] = _now_iso()
        return state

    def _append_once(self, path: Path, text: str) -> None:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if text.strip() and text.strip() not in current:
            path.write_text((current.rstrip() + "\n\n" + text.strip() + "\n").lstrip(), encoding="utf-8")

    def _write_stable_background(self, path: Path, background: str) -> None:
        path.write_text(f"# 角色背景\n\n{background.strip()}\n", encoding="utf-8")

    def _write_relationship_baseline(
        self,
        path: Path,
        content: str,
        source: str,
    ) -> None:
        path.write_text(
            (
                "# 关系基线\n\n"
                f"来源: {source}\n\n"
                f"{content.strip()}\n"
            ),
            encoding="utf-8",
        )

    def _build_first_impression(self, role: RoleRecord) -> str:
        pieces = [
            f"来源: seed:first_impression",
            f"角色: {role.name or role.id}",
        ]
        if role.description.strip():
            pieces.append(f"简介: {role.description.strip()}")
        pieces.append("初始关系理解: 尚未与用户形成稳定互动，后续只能在此基线上增量修订。")
        return "\n".join(pieces)


class RoleBindingService:
    """旧渠道 transport 身份到 role_id 的绑定服务。"""

    def __init__(self, workspace: Path, repository: RoleRepository) -> None:
        self._path = Path(workspace) / "roles" / "channel_bindings.json"
        self._repository = repository
        self._lock = threading.RLock()

    def get_binding(self, channel: str, chat_id: str) -> RoleChannelBinding | None:
        key = _binding_key(channel, chat_id)
        with self._lock:
            payload = self._load_payload()
            item = payload["bindings"].get(key)
        if not isinstance(item, dict):
            return None
        return RoleChannelBinding.from_dict(item)

    def resolve_role_id(self, channel: str, chat_id: str) -> str:
        binding = self.get_binding(channel, chat_id)
        if binding is None:
            raise KeyError(f"渠道未绑定角色: {_binding_key(channel, chat_id)}")
        _ = self._repository.get_required(binding.role_id)
        return binding.role_id

    def bind(self, channel: str, chat_id: str, role_id: str) -> RoleChannelBinding:
        role = self._repository.get_required(role_id)
        key = _binding_key(channel, chat_id)
        now = _now_iso()
        with self._lock:
            payload = self._load_payload()
            existing = payload["bindings"].get(key)
            created_at = (
                str(existing.get("created_at"))
                if isinstance(existing, dict) and existing.get("created_at")
                else now
            )
            binding = RoleChannelBinding(
                channel=str(channel).strip(),
                chat_id=str(chat_id).strip(),
                role_id=role.id,
                created_at=created_at,
                updated_at=now,
            )
            payload["bindings"][key] = binding.to_dict()
            self._save_payload(payload)
        return binding

    def unbind(self, channel: str, chat_id: str) -> bool:
        key = _binding_key(channel, chat_id)
        with self._lock:
            payload = self._load_payload()
            existed = key in payload["bindings"]
            payload["bindings"].pop(key, None)
            self._save_payload(payload)
        return existed

    def list_bindings(self) -> list[RoleChannelBinding]:
        with self._lock:
            payload = self._load_payload()
            values = list(payload["bindings"].values())
        return [
            RoleChannelBinding.from_dict(item)
            for item in values
            if isinstance(item, dict)
        ]

    def replace_bindings(
        self,
        bindings: list[RoleChannelBinding | dict[str, Any]],
    ) -> list[RoleChannelBinding]:
        with self._lock:
            payload = self._load_payload()
            existing_bindings = {
                key: value
                for key, value in payload["bindings"].items()
                if isinstance(value, dict)
            }
            next_bindings: dict[str, dict[str, str]] = {}
            now = _now_iso()
            for item in bindings:
                binding = (
                    item
                    if isinstance(item, RoleChannelBinding)
                    else RoleChannelBinding.from_dict(item)
                )
                role = self._repository.get_required(binding.role_id)
                key = _binding_key(binding.channel, binding.chat_id)
                existing = existing_bindings.get(key)
                created_at = (
                    str(existing.get("created_at"))
                    if isinstance(existing, dict) and existing.get("created_at")
                    else now
                )
                next_binding = RoleChannelBinding(
                    channel=binding.channel.strip(),
                    chat_id=binding.chat_id.strip(),
                    role_id=role.id,
                    created_at=created_at,
                    updated_at=now,
                )
                next_bindings[key] = next_binding.to_dict()
            payload["bindings"] = next_bindings
            self._save_payload(payload)
        return self.list_bindings()

    def _load_payload(self) -> dict[str, Any]:
        payload = load_json(
            self._path,
            default={"version": _BINDINGS_VERSION, "bindings": {}},
            domain="role_bindings",
        )
        if not isinstance(payload, dict):
            return {"version": _BINDINGS_VERSION, "bindings": {}}
        bindings = payload.get("bindings")
        if not isinstance(bindings, dict):
            bindings = {}
        return {
            "version": int(payload.get("version") or _BINDINGS_VERSION),
            "bindings": bindings,
        }

    def _save_payload(self, payload: dict[str, Any]) -> None:
        atomic_save_json(
            self._path,
            {
                "version": _BINDINGS_VERSION,
                "bindings": dict(payload.get("bindings") or {}),
            },
            domain="role_bindings",
        )


class RoleAggregateService:
    """角色聚合业务入口，供桌面、旧渠道和主动能力统一调用。"""

    def __init__(
        self,
        *,
        repository: RoleRepository,
        sessions: RoleSessionService,
        memory: RoleMemoryService,
        bindings: RoleBindingService,
    ) -> None:
        self.repository = repository
        self.sessions = sessions
        self.memory = memory
        self.bindings = bindings

    @classmethod
    def from_runtime(
        cls,
        *,
        workspace: Path,
        role_store: RoleStore,
        session_manager: SessionManager,
        self_seed_generator: RoleSelfSeedGenerator | None = None,
    ) -> "RoleAggregateService":
        repository = RoleRepository(role_store)
        memory = RoleMemoryService(workspace, self_seed_generator=self_seed_generator)
        bindings = RoleBindingService(workspace, repository)
        return cls(
            repository=repository,
            sessions=RoleSessionService(session_manager),
            memory=memory,
            bindings=bindings,
        )

    def create_role(
        self,
        *,
        role_id: str | None = None,
        name: str,
        system_prompt: str,
        description: str = "",
        background: str = "",
        runtime_config: dict[str, Any] | None = None,
        avatar_source: str | Path | None = None,
        illustration_sources: list[str | Path] | None = None,
    ) -> RoleAggregate:
        role = self.repository.create_role(
            name=name,
            description=description,
            system_prompt=system_prompt,
            background=background,
            runtime_config=runtime_config,
            role_id=role_id,
            avatar_source=avatar_source,
            illustration_sources=illustration_sources,
        )
        memory_state = self.memory.seed_role_memory(role)
        if memory_state != role.memory_init_state:
            role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    async def create_role_async(
        self,
        *,
        role_id: str | None = None,
        name: str,
        system_prompt: str,
        description: str = "",
        background: str = "",
        runtime_config: dict[str, Any] | None = None,
        avatar_source: str | Path | None = None,
        illustration_sources: list[str | Path] | None = None,
    ) -> RoleAggregate:
        """异步创建角色，供运行中事件循环内的入口调用。"""
        role = self.repository.create_role(
            name=name,
            description=description,
            system_prompt=system_prompt,
            background=background,
            runtime_config=runtime_config,
            role_id=role_id,
            avatar_source=avatar_source,
            illustration_sources=illustration_sources,
        )
        memory_state = await self.memory.seed_role_memory_async(role)
        if memory_state != role.memory_init_state:
            role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    def update_role(self, role_id: str, **updates: Any) -> RoleAggregate:
        role = self.repository.update_role(role_id, **updates)
        memory_state = self.memory.seed_role_memory(role)
        if memory_state != role.memory_init_state:
            role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    async def update_role_async(self, role_id: str, **updates: Any) -> RoleAggregate:
        """异步更新角色，供运行中事件循环内的入口调用。"""
        role = self.repository.update_role(role_id, **updates)
        memory_state = await self.memory.seed_role_memory_async(role)
        if memory_state != role.memory_init_state:
            role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    def delete_role(self, role_id: str) -> tuple[bool, bool]:
        clean_role_id = _clean_role_id(role_id)
        deleted = self.repository.delete_role(clean_role_id)
        session_deleted = self.sessions.delete(clean_role_id) if deleted else False
        return deleted, session_deleted

    def open_role(self, role_id: str) -> RoleAggregate:
        role = self.repository.get_required(role_id)
        memory_state = self.memory.seed_role_memory(role)
        if memory_state != role.memory_init_state:
            role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    async def open_role_async(self, role_id: str) -> RoleAggregate:
        """异步打开角色，供运行中事件循环内的入口调用。"""
        role = self.repository.get_required(role_id)
        memory_state = await self.memory.seed_role_memory_async(role)
        if memory_state != role.memory_init_state:
            role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    def update_relationship_baseline(
        self,
        role_id: str,
        *,
        content: str,
        source: str,
    ) -> RoleAggregate:
        role = self.repository.get_required(role_id)
        memory_state = self.memory.update_relationship_baseline(
            role,
            content=content,
            source=source,
        )
        role = self.repository.update_role(role.id, memory_init_state=memory_state)
        session = self.sessions.open_by_role(role)
        return RoleAggregate(role=role, session=session, memory_root=self.memory.memory_root(role.id))

    def open_bound_channel(self, *, channel: str, chat_id: str) -> RoleAggregate:
        role_id = self.bindings.resolve_role_id(channel, chat_id)
        return self.open_role(role_id)

    def build_role_request(
        self,
        *,
        request_id: str,
        role_id: str,
        source: str,
        channel: str,
        chat_id: str,
        sender_id: str = "",
        action: str = "",
        payload: dict[str, Any] | None = None,
        runtime_flags: dict[str, Any] | None = None,
        request_context: dict[str, Any] | None = None,
    ) -> RoleRequest:
        role = self.repository.get_required(role_id)
        return RoleRequest(
            request_id=str(request_id),
            role_id=role.id,
            source=str(source),
            channel=str(channel),
            chat_id=str(chat_id),
            sender_id=str(sender_id),
            action=str(action),
            payload=dict(payload or {}),
            runtime_flags=dict(runtime_flags or {}),
            request_context=dict(request_context or {}),
        )
