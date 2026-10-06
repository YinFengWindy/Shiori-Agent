"""Private role writes validate imports and preserve the previous voice on failure."""

import httpx
import pytest
from plugins.gpt_sovits_tts.backend.client import SovitsClient
from plugins.gpt_sovits_tts.backend.engine import SynthesisEngine
from plugins.gpt_sovits_tts.backend.rpc import register_rpc
from plugins.gpt_sovits_tts.backend.runtime import create_runtime


async def test_import_is_an_unsaved_draft_until_role_save(
    context, references, tmp_path, wav_bytes
):
    client = SovitsClient(httpx.MockTransport(lambda _: httpx.Response(500)))
    engine = SynthesisEngine(
        references.store, references, client, context.background, context.roles
    )
    register_rpc(context, engine, create_runtime(context, references.store))
    source = tmp_path / "private_runtime/imports/gpt_sovits_tts-audio/clip.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(wav_bytes())
    imported = await context.rpc.handlers["reference.import"](
        {"role_id": "role", "source": str(source)}
    )
    assert references.store.read().roles == {}
    assert not source.exists()
    assert imported["duration"] == 3
    saved = await context.rpc.handlers["role.set"](
        {
            "role_id": "role",
            "voice": {
                "default": {
                    "asset": imported["asset"],
                    "prompt_lang": "en",
                    "prompt_text": "hello",
                }
            },
        }
    )
    assert saved["default"]["prompt_text"] == "hello"
    assert references.store.read().roles["role"].default.asset == imported["asset"]
    assert context.roles.extensions.values == {}
    with pytest.raises(ValueError, match="不存在"):
        await context.rpc.handlers["reference.import"](
            {"role_id": "missing", "source": str(source)}
        )
    await engine.close()
