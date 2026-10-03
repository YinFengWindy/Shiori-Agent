"""Observe host-owned native daemons without changing their commands or lifetime."""

from pathlib import Path

from agent.plugin_host.processes import HostProcesses
from scripts.browser_acceptance import BrowserAcceptanceEvidence
from shiori_sdk.processes import ProcessOwner


class _RecordedOwner:
    def __init__(
        self, owner: ProcessOwner, evidence: BrowserAcceptanceEvidence, session: str
    ) -> None:
        self._owner, self._evidence, self._session = owner, evidence, session

    def close(self) -> None:
        try:
            self._owner.close()
        finally:
            self._evidence.daemon_stopped(self._session)


def record_native_daemons(monkeypatch, evidence: BrowserAcceptanceEvidence) -> None:
    """Copy each generation's daemon log after its owned processes have exited."""
    spawn = HostProcesses.spawn

    async def observed_spawn(self, *command, **options):
        process, owner = await spawn(self, *command, **options)
        environment = options["env"]
        if environment.get("AGENT_BROWSER_DAEMON") != "1":
            return process, owner
        session = environment["AGENT_BROWSER_SESSION"]
        try:
            evidence.daemon_started(session, process.pid, Path(options["stdout"].name))
            evidence.report["generations"][-1]["headed"] = environment[
                "AGENT_BROWSER_HEADED"
            ]
        except BaseException:
            # The caller cannot own the process until this adapter returns it.
            owner.close()
            await process.wait()
            raise
        return process, _RecordedOwner(owner, evidence, session)

    monkeypatch.setattr(HostProcesses, "spawn", observed_spawn)
