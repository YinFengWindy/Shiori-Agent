"""Role tools over the session's agents: inputs, outputs, recorded source, errors."""

from pathlib import Path
import json

import pytest

from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.plugin import setup
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext

PACKAGE_DIR = Path(__file__).resolve().parents[1]

AGENT = {
    "agent": "claude",
    "agent_status": "idle",
    "cwd": "D:\\Coding\\Shiori",
    "pane_id": "wR:p2",
    "terminal_title_stripped": "herdr插件问题",
    "workspace_id": "wR",
}


class Herdr:
    """Answers like the Herdr CLI for one agent; records the commands it is given."""

    def __init__(self):
        self.sent: list[list[str]] = []
        self.running = True
        self.answer: CommandError | None = None

    async def command(self, argv, **_kwargs):
        if argv[1:] == ["--version"]:
            return "herdr 0.9.5"
        if argv[-3:] == ["status", "server", "--json"]:
            return json.dumps(
                {
                    "running": self.running,
                    "version": "0.9.5",
                    "compatible": True,
                    "endpoint_compatible": True,
                }
            )
        if not self.running:
            raise CommandError("no herdr server", code="server_not_running")
        action = argv[3:5]
        if action == ["agent", "list"]:
            return json.dumps({"result": {"agents": [AGENT]}})
        if action == ["workspace", "list"]:
            return json.dumps(
                {"result": {"workspaces": [{"workspace_id": "wR", "label": "Shiori"}]}}
            )
        if action == ["agent", "get"]:
            if argv[5] != "wR:p2":
                return json.dumps(
                    {"error": {"code": "agent_not_found", "message": "x"}}
                )
            return json.dumps({"result": {"agent": AGENT}})
        if action == ["agent", "read"]:
            return "y" * 5000 + "最后一行"
        self.sent.append(argv[3:])
        if self.answer:
            raise self.answer
        return json.dumps({"result": {"agent": {**AGENT, "agent_status": "working"}}})


@pytest.fixture
async def plugin(tmp_path, monkeypatch):
    ctx = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    herdr = Herdr()
    monkeypatch.setattr(
        HerdrCli, "command", lambda _cli, argv, **kwargs: herdr.command(argv, **kwargs)
    )
    ctx.fake_roles.create_role(role_id="role-a", name="Mira", system_prompt="")
    ctx.fake_tools.context = {"role_id": "role-a"}
    ctx.fake_background_results.target = FakeBackgroundResultTarget(
        "role-a", "thread-a"
    )
    await setup(ctx)

    async def call(name: str, **kwargs):
        return json.loads(await ctx.fake_tools.tools[name].execute(**kwargs))

    yield ctx, herdr, call
    await ctx.aclose()


async def test_list_and_read_show_the_agent_and_its_handling_role(plugin):
    _ctx, _herdr, call = plugin
    listed = await call("herdr_list_agents")
    assert listed["ok"] is True
    [group] = listed["workspaces"]
    assert group["label"] == "Shiori"
    assert [(item["pane_id"], item["handler"]) for item in group["agents"]] == [
        ("wR:p2", None)
    ]

    await call("herdr_prompt_agent", pane_id="wR:p2", text="修滚动")
    mira = {"role_id": "role-a", "role_name": "Mira"}
    listed = await call("herdr_list_agents")
    assert listed["workspaces"][0]["agents"][0]["handler"] == mira
    read = await call("herdr_read_agent", pane_id="wR:p2")
    assert read["ok"] is True
    assert read["agent"]["title"] == "herdr插件问题"
    assert read["handler"] == mira
    assert len(read["output"]) == 4000 and read["output"].endswith("最后一行")
    [command] = read["commands"]
    assert (command["content"], command["report"]) == ("修滚动", "pending")

    gone = await call("herdr_read_agent", pane_id="wR:p9")
    assert gone["ok"] is False and gone["error"]["code"] == "agent_not_found"


async def test_prompt_and_keys_are_sent_as_from_the_calling_role(plugin):
    ctx, herdr, call = plugin
    prompted = await call(
        "herdr_prompt_agent", pane_id="wR:p2", text="修滚动", role_id="forged"
    )
    pressed = await call("herdr_send_keys", pane_id="wR:p2", keys=["esc", "enter"])

    assert herdr.sent[0][:3] == ["agent", "prompt", "wR:p2"]
    assert herdr.sent[0][3] == "修滚动"
    assert herdr.sent[1] == ["agent", "send-keys", "wR:p2", "esc", "enter"]
    for result, kind, content in (
        (prompted, "prompt", "修滚动"),
        (pressed, "keys", "esc enter"),
    ):
        assert result["ok"] is True
        assert "回报" in result["note"]
        command = result["command"]
        assert (command["kind"], command["content"], command["status"]) == (
            kind,
            content,
            "sent",
        )
        assert command["source"] == {
            "kind": "role",
            "role_id": "role-a",
            "role_name": "Mira",
        }


@pytest.mark.parametrize(
    ("setup_failure", "code", "sent"),
    [
        ("stopped", "server_unavailable", 0),
        ("gone", "agent_not_found", 1),
        ("timeout", "timeout", 1),
        ("no_target", "not_permitted", 0),
        ("empty", "invalid_request", 0),
    ],
)
async def test_failures_are_structured_and_never_resent(
    plugin, setup_failure, code, sent
):
    ctx, herdr, call = plugin
    text = "修滚动"
    if setup_failure == "stopped":
        herdr.running = False
    elif setup_failure == "gone":
        herdr.answer = CommandError("no agent", code="agent_not_found")
    elif setup_failure == "timeout":
        herdr.answer = CommandError("slow", code="timeout")
    elif setup_failure == "no_target":
        ctx.fake_background_results.target = None
    else:
        text = " "

    result = await call("herdr_prompt_agent", pane_id="wR:p2", text=text)

    assert result["ok"] is False
    assert result["error"]["code"] == code
    assert result["error"]["message"]
    assert len(herdr.sent) == sent
    if code == "timeout":
        assert "未自动重发" in result["error"]["message"]
        assert "回报" in result["note"]


async def test_the_handling_role_answers_a_report_without_a_new_capture(plugin):
    ctx, herdr, call = plugin
    await call("herdr_prompt_agent", pane_id="wR:p2", text="修滚动")
    # The turn reporting on the agent: the host refuses another capture.
    ctx.fake_background_results.target = None

    answered = await call("herdr_send_keys", pane_id="wR:p2", keys=["enter"])
    assert answered["ok"] is True
    assert answered["command"]["report"] == "pending"
    assert herdr.sent[-1] == ["agent", "send-keys", "wR:p2", "enter"]

    # Another role never borrows the handling role's destination.
    ctx.fake_tools.context = {"role_id": "role-b"}
    refused = await call("herdr_send_keys", pane_id="wR:p2", keys=["enter"])
    assert refused["ok"] is False
    assert refused["error"]["code"] == "not_permitted"
    assert len(herdr.sent) == 2
