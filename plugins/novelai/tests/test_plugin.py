"""Independent plugin setup and configuration contracts."""

import json
import pytest
from shiori_sdk.lifecycle import ResponseMetadata, AfterReasoningCtx, AfterToolResultCtx
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
    assert len(context.scene_observations.predicates) == 1
    image = str(tmp_path / "output.png")
    await context.events.emit(
        AfterToolResultCtx(
            session_key="role:mira",
            channel="desktop",
            chat_id="desktop",
            tool_name="generate_image",
            arguments={},
            result=json.dumps({"output_paths": [image]}),
            status="success",
        )
    )
    if pushed:
        await context.events.emit(
            AfterToolResultCtx(
                session_key="role:mira",
                channel="desktop",
                chat_id="desktop",
                tool_name="message_push",
                arguments={"image": image},
                result="图片已发送",
                status="success",
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
