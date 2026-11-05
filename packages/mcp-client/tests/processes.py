"""Real pipe fixture; operating-system Job behavior remains a host integration test."""

import asyncio
from shiori_sdk.testing.processes import FakeProcesses


class RecordingOwner:
    def __init__(self):
        self.fail = False

    def close(self):
        if self.fail:
            raise RuntimeError("owner failure")


class RecordingProcesses(FakeProcesses):
    def __init__(self):
        self.process = None
        self.owner = RecordingOwner()

    async def spawn(
        self, *command, env, cwd, stdin, stdout, stderr, own_process_tree=True
    ):
        self.process = await asyncio.create_subprocess_exec(
            *command, env=env, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr
        )
        return self.process, self.owner
