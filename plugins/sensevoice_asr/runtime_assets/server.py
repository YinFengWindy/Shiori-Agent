"""Private CPU service; dependencies live only in its fixed standalone interpreter."""

# pyright: reportMissingImports=false

from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
from threading import Lock


def main():
    """Load both local models before publishing readiness or generation identity."""
    import soundfile
    import torch
    import torchaudio
    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess

    port, token = sys.argv[1:]
    root = Path(__file__).resolve().parent
    torch.set_num_threads(4)
    model = AutoModel(
        model=str(root / "model"),
        vad_model=str(root / "vad"),
        vad_kwargs={"max_single_segment_time": 30000},
        device="cpu",
        ncpu=4,
        disable_update=True,
        trust_remote_code=False,
        disable_pbar=True,
    )
    inference = Lock()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/shiori-runtime":
                self.respond(200, {"token": token})
            elif self.path == "/health":
                self.respond(
                    200,
                    {"status": "ok", "device": "cpu", "models_loaded": ["sensevoice"]},
                )
            else:
                self.respond(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if self.path != "/v1/audio/transcriptions":
                self.respond(404, {"error": "Unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32 * 1024 * 1024 + 65536:
                    raise ValueError("录音超过大小限制")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("录音上传中断")
                message = BytesParser(policy=policy.default).parsebytes(
                    b"Content-Type: "
                    + self.headers.get("Content-Type", "").encode("ascii")
                    + b"\r\nMIME-Version: 1.0\r\n\r\n"
                    + body
                )
                parts = {
                    part.get_param(
                        "name", header="content-disposition"
                    ): part.get_payload(decode=True)
                    for part in message.iter_parts()
                }
                recording = parts.get("file")
                if parts.get("model") != b"sensevoice" or not isinstance(
                    recording, bytes
                ):
                    raise ValueError("需要 sensevoice 模型和 WAV 文件")
                audio, sample_rate = soundfile.read(
                    io.BytesIO(recording), dtype="float32"
                )
                if audio.ndim == 2:
                    audio = audio.mean(axis=1)
                if sample_rate != 16000:
                    audio = torchaudio.functional.resample(
                        torch.from_numpy(audio), sample_rate, 16000
                    ).numpy()
                with inference:
                    result = model.generate(
                        input=audio,
                        fs=16000,
                        language="auto",
                        use_itn=True,
                        batch_size_s=60,
                        merge_vad=True,
                        merge_length_s=15,
                    )
                text = "".join(
                    rich_transcription_postprocess(item["text"]) for item in result
                )
                self.respond(200, {"text": text})
            except Exception as error:
                # The HTTP boundary reports inference failures to the owning plugin.
                self.respond(400, {"error": str(error)})

    ThreadingHTTPServer(("127.0.0.1", int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
