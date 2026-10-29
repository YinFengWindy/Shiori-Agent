"""Independent plugin setup and configuration contracts."""

from pathlib import Path
import json
import pytest
from shiori_sdk.core.conversation import ReasoningFinished
from shiori_sdk.core.scene import SCENE
from shiori_sdk.core.tools import ToolCalled
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.novelai.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]


class _Scene:
    """Records one demand registration and its disposer."""

    def __init__(self) -> None:
        self.predicates: list[object] = []
        self.released = False

    def request(self, predicate: object):
        self.predicates.append(predicate)

        def dispose() -> None:
            self.released = True
            self.predicates.clear()

        return dispose


@pytest.mark.parametrize("pushed", [False, True])
async def test_setup_tracks_generated_media_and_releases_contributions(
    tmp_path, pushed
):
    context = FakeServiceContext("novelai", tmp_path, package_dir=PACKAGE_DIR)
    scene = _Scene()
    context.serve(SCENE, scene)
    await setup(context)
    assert context.exported is context.fake_tools.get_tool("generate_image")
    assert "regenerateMessageMedia" in context.fake_rpc.handlers
    assert {
        "role_settings.get",
        "role_settings.set",
    } <= context.fake_rpc.handlers.keys()
    assert len(scene.predicates) == 1
    image = str(tmp_path / "output.png")
    await context.emit(
        ToolCalled(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            source="passive",
            call_id="c1",
            tool_name="generate_image",
            arguments={},
            status="success",
            result=json.dumps({"output_paths": [image]}),
        )
    )
    if pushed:
        await context.emit(
            ToolCalled(
                session_key="role:mira",
                channel="desktop",
                chat_id="desktop",
                source="passive",
                call_id="c2",
                tool_name="message_push",
                arguments={"image": image},
                status="success",
                result="图片已发送",
            )
        )
    event = await context.emit(
        ReasoningFinished(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tools_used=(),
            tool_chain=(),
            thinking=None,
            streamed=False,
            reply="已生成",
        )
    )
    assert isinstance(event, ReasoningFinished)
    assert event.media == (() if pushed else (image,))
    await context.aclose()
    assert scene.released
    assert not context.fake_tools.tools and not context.fake_rpc.handlers
