"""Cancellation-safe single-instance ownership shared by preview and public TTS."""

import asyncio
import base64
from collections.abc import Callable

import httpx
from shiori_sdk.extensions import BackgroundTasks
from shiori_sdk.roles import Roles

from .client import SovitsClient
from .instance import InferenceUncertain, InstanceState
from .references import References
from .settings import Settings, VoiceStore


class SynthesisEngine:
    """Keep the real HTTP job alive after its caller abandons the result."""

    def __init__(
        self,
        store: VoiceStore,
        references: References,
        client: SovitsClient,
        background: BackgroundTasks,
        roles: Roles,
        settings: Callable[[], Settings] | None = None,
        managed_identity: Callable[[], dict[str, str] | None] | None = None,
    ):
        self.store, self.references, self.client = store, references, client
        self.background, self.roles = background, roles
        self.lock = asyncio.Lock()
        self.instance = InstanceState(store.root)
        self.tasks: set[asyncio.Task[dict[str, object]]] = set()
        self.closed = False
        self.settings = settings or (lambda: self.store.read().settings)
        self.managed_identity = managed_identity or (lambda: None)

    async def synthesize(self, params: dict[str, object]) -> dict[str, object]:
        """A cancelled caller discards audio; the retained runtime task keeps ownership."""
        if self.closed:
            raise RuntimeError("GPT-SoVITS 插件正在停用")
        task = self.background.spawn_runtime(self._run(dict(params)), name="synthesize")
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return await asyncio.shield(task)

    def _finished(self, task: asyncio.Task[dict[str, object]]) -> None:
        self.tasks.discard(task)
        # Consume failures even if the caller already abandoned this retained task.
        if not task.cancelled():
            task.exception()

    async def _run(self, params: dict[str, object]) -> dict[str, object]:
        async with self.lock:
            async with self.instance.wait():
                return await self._synthesize_owned(params)

    async def _synthesize_owned(self, params: dict[str, object]) -> dict[str, object]:
        if self.instance.marker.exists():
            raise RuntimeError(
                "上次推理完成状态未知；请重建外部服务后在插件设置中确认重连"
            )
        role_id, text, mood = (params.get(key) for key in ("role_id", "text", "mood"))
        if not isinstance(role_id, str) or self.roles.get_role(role_id) is None:
            raise ValueError("角色不存在")
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError("合成文本必须为 1–10000 字符")
        if not isinstance(mood, str):
            raise ValueError("情绪必须是字符串")
        document = self.store.read()
        settings = self.settings()
        voice = document.roles.get(role_id)
        if voice is None or voice.default is None:
            raise ValueError("请先保存角色的默认参考音频")
        reference = voice.moods.get(mood, voice.default)
        with self.references.pin(reference.asset) as path:
            payload = {
                "text": text,
                "text_lang": voice.text_lang,
                "ref_audio_path": str(path),
                "prompt_lang": reference.prompt_lang,
                "prompt_text": reference.prompt_text,
                "speed_factor": voice.speed,
                "streaming_mode": False,
                "media_type": "wav",
            }
            operation = self.instance.begin(settings.url, self.managed_identity())
            try:
                audio = await self.client.synthesize(settings, payload)
            except (httpx.TransportError, asyncio.CancelledError) as error:
                # A broken connection cannot prove that GPU work has stopped. Persist quarantine across reloads.
                self.instance.finish(operation, unknown=True)
                if isinstance(error, httpx.TransportError):
                    raise InferenceUncertain() from error
                raise
            except BaseException:
                self.instance.finish(operation)
                raise
            self.instance.finish(operation)
            return {
                "audio_base64": base64.b64encode(audio).decode(),
                "format": "wav",
            }

    async def reconnect(self, params: dict[str, object]) -> dict[str, object]:
        """Clear quarantine only after explicit external-instance restart attestation."""
        if params.get("service_restarted") is not True:
            raise ValueError("请先重启外部 GPT-SoVITS 服务")
        if self.lock.locked():
            raise RuntimeError("上一请求仍在等待服务响应，请先完成外部服务重启")
        async with self.lock:
            with self.instance.lease():
                result = await self.client.health(self.settings())
                self.instance.recover()
                self.references.collect()
                return result

    async def managed_stopped(self, url: str) -> None:
        """Recover only the matching endpoint after its native-owned child has exited."""
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        with self.instance.lease():
            self.instance.recover_owned(url=url)
            self.references.collect()

    async def recover_managed(self, runtime: str) -> None:
        """Recover a former owned generation only after its service lease is acquired."""
        async with self.instance.wait():
            self.instance.recover_owned(runtime=runtime)
            if self.instance.marker.exists():
                raise RuntimeError(
                    "外部推理状态仍未知；请切回外部服务模式，重启该服务并确认重连"
                )
            self.references.collect()

    async def close(self) -> None:
        """Drain retained operations before releasing the transport."""
        self.closed = True
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.client.close()
