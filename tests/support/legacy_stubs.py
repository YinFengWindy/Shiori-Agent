"""Legacy host tests model optional SDK boundaries without network calls."""

import sys
import types

# Provide a lightweight openai stub in test env so imports do not fail
# when optional runtime dependency is absent.
if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _DummyChatCompletions:
        async def create(self, *args, **kwargs):
            raise RuntimeError(
                "openai stub: AsyncOpenAI.chat.completions.create not mocked"
            )

    class _DummyChat:
        def __init__(self):
            self.completions = _DummyChatCompletions()

    class AsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _DummyChat()
            self.closed = False

        async def close(self):
            self.closed = True

    openai_stub.AsyncOpenAI = AsyncOpenAI
    sys.modules["openai"] = openai_stub

if "json_repair" not in sys.modules:
    json_repair_stub = types.ModuleType("json_repair")

    def loads(text, *args, **kwargs):
        import json

        return json.loads(text)

    def repair_json(text, *args, **kwargs):
        return text

    json_repair_stub.loads = loads
    json_repair_stub.repair_json = repair_json
    sys.modules["json_repair"] = json_repair_stub

if "uvicorn" not in sys.modules:
    uvicorn_stub = types.ModuleType("uvicorn")

    def run(*args, **kwargs):
        raise RuntimeError("uvicorn stub: run() not expected in tests")

    uvicorn_stub.run = run
    sys.modules["uvicorn"] = uvicorn_stub
