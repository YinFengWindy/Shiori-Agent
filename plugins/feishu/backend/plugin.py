from __future__ import annotations

from typing import TYPE_CHECKING

from .channel import FeishuChannel
from .config import FeishuAppConfig, FeishuConfigModel
from .identity import verify_app

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Register each configured bot and its independently addressed channel."""
    config = FeishuConfigModel.model_validate(ctx.config.as_dict())
    from desktop_bridge.method_policy import Concurrency

    async def profile(payload: dict[str, object]) -> dict[str, object]:
        ref = str(payload.get("ref") or "")
        if ref not in {app.ref for app in config.applications}:
            raise KeyError("飞书账号不存在")
        identity = ctx.kv.get(f"profile:{ref}", {})
        targets = ctx.kv.get(f"targets:{ref}", {})
        return {
            "identity": identity,
            "targets": [
                {"chat_id": chat, "open_id": sender, "id_scope": "app"}
                for chat, sender in sorted(targets.items())
            ],
            "coverage": "observed_private_chats",
        }

    ctx.rpc.register("accounts.profile", profile, concurrency=Concurrency.READ_ONLY)

    async def verify(payload: dict[str, object]) -> dict[str, object]:
        app = FeishuAppConfig.model_validate(payload)
        identity = await verify_app(app)
        known = ctx.kv.get(f"profile:{app.ref}", {})
        known_id = str(known.get("open_id") or "")
        if known_id and known_id != identity["open_id"]:
            raise ValueError("应用凭据指向不同的机器人，请新建账号")
        return {"name": identity["name"], "open_id": identity["open_id"]}

    ctx.rpc.register("accounts.verify", verify, concurrency=Concurrency.INTEGRATION)
    for app in config.applications:
        profile = ctx.kv.get(f"profile:{app.ref}", {})
        snapshot = ctx.accounts.register(
            platform="feishu",
            platform_account_id=app.ref,
            config_ref=app.ref,
            display_name=str(profile.get("name") or ""),
            avatar_url=str(profile.get("avatar_url") or ""),
        )
        account_id = snapshot.record.id
        if not app.connection_enabled:
            ctx.accounts.report(account_id, connection="offline")
            continue
        if not app.app_secret:
            ctx.accounts.report(
                account_id,
                connection="login_required",
                error="App Secret 未配置或环境变量未解析",
            )
            continue
        ctx.accounts.report(account_id, connection="connecting")
        ctx.channels.add(
            FeishuChannel(
                app_id=app.app_id,
                app_secret=app.app_secret,
                domain=app.base_url,
                name=(
                    "feishu"
                    if app.ref == config.channel_alias_ref
                    else f"feishu:{app.ref}"
                ),
                account_id=account_id,
                accounts=ctx.accounts,
                profile_store=ctx.kv,
                profile_ref=app.ref,
                connection_revision=app.connection_revision,
                chat_types=ctx.manifest.channel_chat_types("feishu"),
            )
        )
