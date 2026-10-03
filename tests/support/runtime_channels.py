"""A real plugin runtime with observable, scope-dependent channel connections."""

import sys
from types import ModuleType

import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore


class RuntimeChannelHarness:
    """Builds a neutral channel plugin whose stop still needs its account scope."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.channels = []
        self.events = []
        self.reuse = False
        self.fail_stop = False
        self.app = None

    def channel(self, accounts):
        harness = self

        class Connection:
            name = "lifecycle"
            configuration_key = "shared" if harness.reuse else None

            def __init__(self):
                self.accounts = accounts
                self.account_id = accounts.register(
                    platform="lifecycle",
                    platform_account_id="one",
                    config_ref="one",
                    role_id="mira",
                ).record.id
                self.context = None
                self.stopped = False
                self.stop_calls = 0

            async def start(self, context):
                self.context = context
                context.bus.subscribe_outbound(self.name, self.receive)
                context.push_tool.register_channel(self.name, text=self.send)
                self.accounts.report(self.account_id, connection="online")

            async def stop(self):
                self.stop_calls += 1
                self.accounts.report(self.account_id, connection="offline")
                if self.context is not None:
                    self.context.bus.unsubscribe_outbound(self.name, self.receive)
                    self.context.push_tool.unregister_channel(self.name, text=self.send)
                self.stopped = True
                harness.events.append("stop")
                if harness.fail_stop:
                    raise RuntimeError("connection cleanup failed")

            async def send(self, chat_id, content):
                assert not self.stopped
                # Sending also requires the generation's live account capability.
                self.accounts.report(self.account_id, connection="online")
                harness.events.append(content)

            async def receive(self, message):
                await self.send(message.chat_id, message.content)

            def pause_intake(self):
                pass

            def resume_intake(self):
                pass

            def adopt_runtime(self, candidate):
                self.accounts = candidate.accounts

        connection = Connection()
        self.channels.append(connection)
        return connection

    async def start(self):
        """Starts the real host with the installed neutral plugin."""
        config = Config(
            provider="",
            model="",
            api_key="",
            model_registrations=[],
            memory_optimizer_enabled=False,
        )
        self.app = AppRuntime(
            config, self.workspace, features=RuntimeFeatures(enable_proactive=False)
        )
        await self.app.start()
        return self.app


@pytest.fixture
def runtime_channels(tmp_path, monkeypatch):
    """Installs a real plugin with a test-controlled channel at the host boundary."""
    harness = RuntimeChannelHarness(tmp_path)
    module_name = "_runtime_channel_harness"
    module = ModuleType(module_name)
    module.build_channel = harness.channel
    monkeypatch.setitem(sys.modules, module_name, module)
    root = tmp_path / "plugin_dirs"
    package = root / "lifecycle"
    (package / "backend").mkdir(parents=True)
    (package / "backend" / "plugin.py").write_text(
        f"import sys\n\nasync def setup(ctx):\n"
        f'    ctx.channels.add(sys.modules["{module_name}"].build_channel(ctx.accounts))\n',
        encoding="utf-8",
    )
    (package / "manifest.yaml").write_text(
        "api: 2\nid: lifecycle\ncapabilities: [channels, accounts]\n"
        "channels:\n  - name: lifecycle\n    label: Lifecycle\n"
        "    chat_types: [{type: private, label: Private, chat_id_label: ID}]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
    RoleStore(tmp_path).create_role(
        role_id="mira", name="Mira", system_prompt="A test role."
    )
    return harness
