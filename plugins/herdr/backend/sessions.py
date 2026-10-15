"""Local Herdr session discovery backing the settings page's session picker."""

import json

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .cli import CommandError, HerdrCli


async def list_sessions(cli: HerdrCli) -> list[dict[str, str]]:
    """Every session Herdr knows locally, named with its running state.

    Listing is not scoped to the configured session, so it also works while
    that session is missing or stopped.
    """
    output = await cli.command([cli.config.executable, "session", "list", "--json"])
    try:
        entries = json.loads(output)["sessions"]
        return [
            {
                "name": str(entry["name"]),
                "status": "running" if entry["running"] is True else "stopped",
            }
            for entry in entries
        ]
    except (ValueError, KeyError, TypeError) as error:
        raise CommandError(
            "Herdr 返回了无法识别的 session 列表", code="invalid_response"
        ) from error


def register_session_rpc(ctx: ServicePluginContext, cli: HerdrCli) -> None:
    """`sessions.list` reads with the current generation's executable and timeout."""

    async def handle(_payload: dict[str, object]) -> dict[str, object]:
        return {"sessions": await list_sessions(cli)}

    ctx.rpc.register("sessions.list", handle, concurrency=Concurrency.READ_ONLY)
