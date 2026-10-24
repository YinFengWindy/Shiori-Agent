"""Independent plugin setup and configuration contracts."""

import json
import pytest
from shiori_sdk.core.tools import ToolCalled
from shiori_sdk.lifecycle import ResponseMetadata, AfterReasoningCtx
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.novelai.backend.plugin import setup


@pytest.mark.parametrize("pushed", [False, True])
async def test_setup_tracks_generated_media_and_releases_contributions(
    tmp_path, pushed
):
    context = FakeServiceContext("novelai", tmp_path)
    await setup(context.as_capability())
    assert context.exported is context.tools.get_tool("generate_image")
    assert "regenerateMessageMedia" in context.rpc.handlers
    assert {"role_settings.get", "role_settings.set"} <= context.rpc.handlers.keys()
    assert len(context.scene_observations.predicates) == 1
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
    event = AfterReasoningCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="desktop",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="test"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="已生成",
    )
    await context.events.emit(event)
    assert event.media == ([] if pushed else [image])
    await context.aclose()
    assert not context.tools.tools and not context.rpc.handlers
