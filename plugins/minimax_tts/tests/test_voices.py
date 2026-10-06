from shiori_sdk.testing.voice import FakeVoiceHttp
import base64
import json
from plugins.minimax_tts.backend.voices import MiniMaxVoices
from plugins.minimax_tts.backend.config import MiniMaxTtsConfig


def test_minimax_voice_clone_uploads_transient_audio_and_returns_preview() -> None:
    uploads: list[dict[str, object]] = []
    requests: list[dict] = []

    def upload(
        url: str,
        headers: dict[str, str],
        fields: dict[str, str],
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> dict:
        uploads.append(
            {
                "url": url,
                "headers": headers,
                "fields": fields,
                "file_name": file_name,
                "content_type": content_type,
                "content": content,
            }
        )
        return {"base_resp": {"status_code": 0}, "file": {"file_id": 123}}

    def requester(url: str, _headers: dict[str, str], body: bytes) -> dict:
        assert url == "https://api.minimaxi.com/v1/voice_clone"
        requests.append(json.loads(body))
        return {
            "base_resp": {"status_code": 0},
            "demo_audio": "https://demo.example/audio.mp3",
        }

    client = MiniMaxVoices(
        MiniMaxTtsConfig(api_key="key"),
        FakeVoiceHttp(
            requester=requester,
            upload_requester=upload,
            binary_requester=lambda url: (
                b"preview" if url.endswith("audio.mp3") else b""
            ),
        ),
    )
    result = client.clone_voice(b"wav-bytes", file_name="sample.wav")
    assert uploads[0]["url"] == "https://api.minimaxi.com/v1/files/upload"
    assert uploads[0]["fields"] == {"purpose": "voice_clone"}
    assert uploads[0]["content_type"] == "audio/wav"
    assert requests[0]["file_id"] == 123
    assert requests[0]["voice_id"].startswith("Shiori_")
    assert result["audio_base64"] == base64.b64encode(b"preview").decode("ascii")


def test_minimax_voice_clone_keeps_voice_when_preview_download_fails() -> None:
    client = MiniMaxVoices(
        MiniMaxTtsConfig(api_key="key"),
        FakeVoiceHttp(
            requester=lambda *_args: (
                {"base_resp": {"status_code": 0}, "file": {"file_id": 123}}
                if _args[0].endswith("files/upload")
                else {
                    "base_resp": {"status_code": 0},
                    "demo_audio": "https://api.minimaxi.com/demo.mp3",
                }
            ),
            upload_requester=lambda *_args: {
                "base_resp": {"status_code": 0},
                "file": {"file_id": 123},
            },
            binary_requester=lambda _url: (_ for _ in ()).throw(
                RuntimeError("preview down")
            ),
        ),
    )
    result = client.clone_voice(b"wav-bytes")
    assert result["voice_id"].startswith("Shiori_")
    assert result["audio_base64"] == ""


def test_minimax_deletes_one_cloned_voice_by_id() -> None:
    calls: list[tuple[str, dict]] = []

    def requester(url: str, _headers: dict[str, str], body: bytes) -> dict:
        calls.append((url, json.loads(body)))
        return {"base_resp": {"status_code": 0}}

    client = MiniMaxVoices(
        MiniMaxTtsConfig(api_key="key"), FakeVoiceHttp(requester=requester)
    )
    client.delete_voice("Shiori_voice123")
    assert calls == [
        (
            "https://api.minimaxi.com/v1/delete_voice",
            {"voice_type": "voice_cloning", "voice_id": "Shiori_voice123"},
        )
    ]
