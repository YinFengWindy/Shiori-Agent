from __future__ import annotations

import logging
import math
import random as _random_module
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from agent.prompting import is_context_frame
from core.roles.services import RoleBindingService
from proactive_v2.energy import compute_energy, d_recent
from proactive_v2.presence import PresenceStore
from proactive_v2.state import ProactiveStateStore
from session.manager import SessionManager

if TYPE_CHECKING:
    from core.memory.markdown import MemoryProfileApi

logger = logging.getLogger(__name__)


@dataclass
class RecentProactiveMessage:
    content: str
    timestamp: datetime | None = None
    state_summary_tag: str = "none"
    source_refs: list[Any] = field(default_factory=list)


class Sensor:
    def __init__(
        self,
        *,
        cfg: Any,
        sessions: SessionManager,
        state: ProactiveStateStore,
        memory: "MemoryProfileApi | None",
        presence: PresenceStore | None,
        rng: Any,
        role_bindings: RoleBindingService | None = None,
    ) -> None:
        self._cfg = cfg
        self._sessions = sessions
        self._state = state
        self._memory = memory
        self._presence = presence
        self._rng = rng
        self._role_bindings = role_bindings

    def target_session_key(self) -> str:
        default_role_id = str(getattr(self._cfg, "default_role_id", "") or "").strip()
        if default_role_id:
            return f"role:{default_role_id}"
        channel = (self._cfg.default_channel or "").strip()
        chat_id = self._cfg.default_chat_id.strip()
        return f"{channel}:{chat_id}" if channel and chat_id else ""

    def target_transport(self) -> tuple[str, str]:
        default_role_id = str(getattr(self._cfg, "default_role_id", "") or "").strip()
        if default_role_id:
            preferred_channel = str(getattr(self._cfg, "default_channel", "") or "").strip()
            preferred_chat_id = str(getattr(self._cfg, "default_chat_id", "") or "").strip()
            if preferred_channel == "desktop":
                return preferred_channel, preferred_chat_id or f"role:{default_role_id}"
            if self._role_bindings is None:
                raise RuntimeError(f"default_role_id 缺少 binding 服务: {default_role_id}")
            role_bindings = [
                binding
                for binding in self._role_bindings.list_bindings()
                if binding.role_id == default_role_id
            ]
            if not role_bindings:
                raise KeyError(f"default_role_id 未绑定 transport: {default_role_id}")
            if preferred_channel and preferred_chat_id:
                for binding in role_bindings:
                    if (
                        binding.channel == preferred_channel
                        and binding.chat_id == preferred_chat_id
                    ):
                        return binding.channel, binding.chat_id
                raise KeyError(
                    "default_role_id 配置的 target 未绑定到该角色: "
                    f"{default_role_id} -> {preferred_channel}:{preferred_chat_id}"
                )
            if len(role_bindings) == 1:
                binding = role_bindings[0]
                return binding.channel, binding.chat_id
            raise RuntimeError(
                f"default_role_id 存在多个 transport 绑定，必须显式配置 target.channel/chat_id: {default_role_id}"
            )
        return (
            (self._cfg.default_channel or "").strip(),
            self._cfg.default_chat_id.strip(),
        )

    def read_memory_text(self) -> str:
        if not self._memory:
            return ""
        default_role_id = str(getattr(self._cfg, "default_role_id", "") or "").strip()
        if not default_role_id:
            raise RuntimeError("default_role_id required for proactive memory access")
        bind_session_metadata = getattr(self._memory, "bind_session_metadata", None)
        if callable(bind_session_metadata):
            bind_session_metadata({"role_id": default_role_id})
        return str(self._memory.read_long_term() or "").strip()

    def has_role_memory(self) -> bool:
        return bool(self.read_memory_text())

    def last_user_at(self) -> datetime | None:
        if not self._presence:
            return None
        return self._presence.get_last_user_at(self.target_session_key())

    def compute_energy(self) -> float:
        presence = self._presence
        if presence is None:
            return 0.0
        session_key = self.target_session_key()
        last_target = presence.get_last_user_at(session_key)
        last_global = presence.most_recent_user_at()
        energy_target = compute_energy(last_target)
        energy_global = compute_energy(last_global) * 0.6
        return max(energy_target, energy_global)

    def collect_recent(self) -> list[dict]:
        session_key = self.target_session_key()
        if not session_key:
            return []
        try:
            session = self._sessions.get_or_create(session_key)
        except Exception:
            return []
        messages = session.messages[-self._cfg.recent_chat_messages :]
        results: list[dict] = []
        for message in messages:
            if message.get("role") not in ("user", "assistant"):
                continue
            if not message.get("content"):
                continue
            content = str(message.get("content", ""))
            if is_context_frame(content):
                continue
            results.append(
                {
                    "role": message["role"],
                    "content": content[:200],
                    "timestamp": str(message.get("timestamp", "")),
                }
            )
        return results

    def compute_interruptibility(
        self,
        *,
        now_hour: int,
        now_utc: datetime,
        recent_msg_count: int,
    ) -> tuple[float, dict[str, float]]:
        session_key = self.target_session_key()
        presence = self._presence
        if presence is None or not session_key:
            return 1.0, self._default_interrupt_detail()
        # 1. 先计算 reply/activity/fatigue 三个确定性分量。
        f_reply = self._reply_factor(session_key, now_utc)
        f_activity = self._activity_factor(session_key, now_utc, recent_msg_count)
        f_fatigue = self._fatigue_factor(session_key, now_utc)
        # 2. 再按配置权重聚合，并追加一小段随机探索。
        raw = self._weighted_interruptibility(f_reply, f_activity, f_fatigue)
        random_delta = (self._rng or _random_module).uniform(
            -self._cfg.interrupt_random_strength,
            self._cfg.interrupt_random_strength,
        )
        score = max(self._cfg.interrupt_min_floor, min(1.0, raw + random_delta))
        return score, {
            "f_reply": f_reply,
            "f_activity": f_activity,
            "f_fatigue": f_fatigue,
            "random_delta": random_delta,
        }

    def collect_recent_proactive(self, n: int = 5) -> list[RecentProactiveMessage]:
        session_key = self.target_session_key()
        if not session_key:
            return []
        try:
            session = self._sessions.get_or_create(session_key)
        except Exception:
            return []
        results: list[RecentProactiveMessage] = []
        for message in reversed(session.messages):
            if message.get("role") != "assistant":
                continue
            if not message.get("proactive") or not message.get("content"):
                continue
            results.append(
                RecentProactiveMessage(
                    content=str(message["content"]),
                    timestamp=self._parse_timestamp(message.get("timestamp")),
                    state_summary_tag=str(
                        message.get("state_summary_tag", "none") or "none"
                    ),
                    source_refs=list(message.get("source_refs") or []),
                )
            )
            if len(results) >= n:
                break
        return list(reversed(results))

    @staticmethod
    def _default_interrupt_detail() -> dict[str, float]:
        return {
            "f_reply": 1.0,
            "f_activity": 1.0,
            "f_fatigue": 1.0,
            "random_delta": 0.0,
        }

    def _reply_factor(self, session_key: str, now_utc: datetime) -> float:
        presence = self._presence
        if presence is None:
            return 0.6
        last_user = presence.get_last_user_at(session_key)
        last_proactive = presence.get_last_proactive_at(session_key)
        if last_proactive is None:
            return 0.6
        if last_user is not None and last_user > last_proactive:
            lag_min = max(0.0, (last_user - last_proactive).total_seconds() / 60.0)
            decay = max(self._cfg.interrupt_reply_decay_minutes, 1.0)
            return math.exp(-lag_min / decay)
        silence_min = max(0.0, (now_utc - last_proactive).total_seconds() / 60.0)
        decay = max(self._cfg.interrupt_no_reply_decay_minutes, 1.0)
        return 0.15 + 0.35 * math.exp(-silence_min / decay)

    def _activity_factor(
        self,
        session_key: str,
        now_utc: datetime,
        recent_msg_count: int,
    ) -> float:
        presence = self._presence
        if presence is None:
            return 0.2
        last_global_user = presence.most_recent_user_at()
        if last_global_user is None:
            f_live = 0.2
        else:
            idle_min = max(0.0, (now_utc - last_global_user).total_seconds() / 60.0)
            decay = max(self._cfg.interrupt_activity_decay_minutes, 1.0)
            f_live = math.exp(-idle_min / decay)
        f_recent = d_recent(recent_msg_count, self._cfg.score_recent_scale)
        return 0.5 * f_live + 0.5 * f_recent

    def _fatigue_factor(self, session_key: str, now_utc: datetime) -> float:
        sent_24h = self._state.count_deliveries_in_window(
            session_key,
            self._cfg.interrupt_fatigue_window_hours,
            now=now_utc,
        )
        soft_cap = max(self._cfg.interrupt_fatigue_soft_cap, 0.1)
        return 1.0 / (1.0 + sent_24h / soft_cap)

    def _weighted_interruptibility(
        self,
        f_reply: float,
        f_activity: float,
        f_fatigue: float,
    ) -> float:
        w_sum = (
            self._cfg.interrupt_weight_reply
            + self._cfg.interrupt_weight_activity
            + self._cfg.interrupt_weight_fatigue
        )
        if w_sum <= 0:
            return 0.0
        return (
            self._cfg.interrupt_weight_reply * f_reply
            + self._cfg.interrupt_weight_activity * f_activity
            + self._cfg.interrupt_weight_fatigue * f_fatigue
        ) / w_sum

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            ts = datetime.fromisoformat(text)
        except Exception:
            return None
        if ts.tzinfo is None:
            return ts.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return ts
