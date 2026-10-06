"""Desktop-pet preference RPCs; no speech policy or configuration lives in the host."""

from pathlib import Path

from shiori_sdk.rpc import Concurrency, RpcCapability
from shiori_sdk.roles import Roles
from shiori_sdk.sessions import PluginSessions

from .voice_preferences import VoicePreferencesStore


def register_voice_preferences(rpc: RpcCapability, workspace: Path) -> None:
    """Expose this plugin's private settings and report changes to its background."""
    store = VoicePreferencesStore(workspace)

    async def get(_payload: dict[str, object]) -> dict[str, object]:
        return store.read().model_dump(mode="json")

    async def save(payload: dict[str, object]) -> dict[str, object]:
        result = store.write(payload).model_dump(mode="json")
        await rpc.emit("voice.preferences.changed", result)
        return result

    rpc.register("voice.preferences.get", get, concurrency=Concurrency.READ_ONLY)
    rpc.register("voice.preferences.set", save)


def register_voice_context(
    rpc: RpcCapability, roles: Roles, sessions: PluginSessions
) -> None:
    """Resolve real role/session context without storing sound configuration in roles."""

    async def get(payload: dict[str, object]) -> dict[str, object]:
        role_id = str(payload.get("role_id") or "").strip()
        if not role_id or roles.get_role(role_id) is None:
            raise ValueError("桌宠角色不存在")
        session_key = sessions.role_session_key(role_id)
        metadata = sessions.get_or_create(session_key).metadata
        return {
            "role_id": role_id,
            "session_key": session_key,
            "mood": str(metadata.get("current_mood") or ""),
        }

    rpc.register("voice.context.get", get, concurrency=Concurrency.READ_ONLY)
