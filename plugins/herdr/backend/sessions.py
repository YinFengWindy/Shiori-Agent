"""Local Herdr session discovery and the configured session's availability check."""

import json
from collections.abc import Awaitable, Callable

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.rpc import Concurrency
from shiori_sdk.core.services import RPC

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

    ctx.require(RPC).register(
        "sessions.list", handle, concurrency=Concurrency.READ_ONLY
    )


class SessionGate:
    """Runs this generation's operations on the configured session.

    The Herdr version and session check runs before the first operation and
    right after any failed one, so polling a healthy session costs only the
    operations themselves, while a session that stops or turns incompatible
    is reported by its actual reason from the first failure on.
    """

    def __init__(self, cli: HerdrCli, resources: PluginProcessResources) -> None:
        self.cli, self.resources = cli, resources
        self._verified = False

    async def run[T](
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        keep: frozenset[str] = frozenset(),
    ) -> T:
        """Check, then run; a failure whose code is in `keep` is raised unexplained.

        `keep` names answers the session check cannot improve on: a live
        server's own verdict, or an uncertain outcome it must not mask.
        """
        if not self.resources.active:
            raise RuntimeError("Herdr 配置已替换，请刷新看板")
        if not self._verified:
            await self.cli.require_supported_version()
            self._verified = True
        try:
            return await operation()
        except CommandError as error:
            if error.code in keep:
                raise
            raise await self._explain(error)

    async def _explain(self, error: CommandError) -> CommandError:
        """The session check's reason when it fails, otherwise the error itself."""
        self._verified = False
        try:
            await self.cli.require_supported_version()
        except CommandError as reason:
            reason.__cause__ = error
            return reason
        self._verified = True
        return error
