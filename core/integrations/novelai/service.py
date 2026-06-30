from __future__ import annotations

import base64
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agent.tools.filesystem import _detect_supported_image_mime_from_header, _resolve_path
from core.integrations.novelai.client import NovelAIClient
from core.integrations.novelai.models import (
    GenerateImageRequest,
    GenerateImageResult,
    GeneratedImageRecord,
    NovelAISettings,
)
from core.integrations.novelai.store import NovelAIStore
from core.roles.store import RoleStore

_SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "square": (1024, 1024),
    "landscape": (1216, 832),
    "portrait": (832, 1216),
}
_DEFAULT_IMG2IMG_STRENGTH = 0.7
_DEFAULT_IMG2IMG_NOISE = 0.2
_SUPPORTED_OUTPUT_SUFFIX = {
    "image/png": ".png",
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
}


class NovelAIService:
    """Business service for validating, executing, and persisting NovelAI generations."""

    def __init__(
        self,
        *,
        settings: NovelAISettings,
        client: NovelAIClient,
        store: NovelAIStore,
        role_store: RoleStore,
        workspace: Path,
    ) -> None:
        self._settings = settings
        self._client = client
        self._store = store
        self._role_store = role_store
        self._workspace = workspace

    async def generate(self, request: GenerateImageRequest) -> GenerateImageResult:
        """Execute a validated NovelAI generation request end-to-end."""

        self._validate_enabled()
        prompt = request.prompt.strip()
        if not prompt:
            raise ValueError("prompt 不能为空")
        width, height = self._resolve_dimensions(request)
        steps = self._resolve_steps(request)
        model = self._resolve_model(request)
        action = self._resolve_action(request.mode)
        base_image_path = ""
        base_image_b64 = ""
        if request.mode == "img2img":
            base_image_path, base_image_b64 = self._load_base_image(
                request.base_image_path
            )

        parameters = self._build_parameters(
            request=request,
            width=width,
            height=height,
            steps=steps,
            model=model,
        )
        if request.seed is not None:
            parameters["seed"] = request.seed
        if base_image_b64:
            parameters["image"] = base_image_b64
            parameters["strength"] = _DEFAULT_IMG2IMG_STRENGTH
            parameters["noise"] = _DEFAULT_IMG2IMG_NOISE

        try:
            response = await self._client.generate_image(
                action=action,
                prompt=prompt,
                model=model,
                parameters=parameters,
            )
            output_bytes, suffix = self._extract_primary_image(response)
        except httpx.HTTPStatusError as exc:
            raise await self._rewrite_http_error(exc, model=model) from exc
        created_at = datetime.now(timezone.utc)
        record_id = self._store.new_record_id()
        record_dir = self._store.build_record_dir(
            created_at=created_at,
            record_id=record_id,
        )
        output_path = record_dir / f"output-1{suffix}"
        request_path = record_dir / "request.json"
        meta_path = record_dir / "meta.json"
        self._store.write_bytes(output_path, output_bytes)
        self._store.write_json(
            request_path,
            {
                "action": action,
                "input": prompt,
                "model": model,
                "parameters": parameters,
            },
        )

        wrote_back_to_role = False
        role_asset_paths: list[str] = []
        clean_role_id = request.role_id.strip()
        if self._settings.auto_writeback_role_assets and clean_role_id:
            role = self._role_store.get_role(clean_role_id)
            if role is None:
                raise KeyError(f"role 不存在: {clean_role_id}")
            updated_with_asset = self._role_store.update_role(
                clean_role_id,
                illustration_sources=[output_path],
            )
            role_asset_path = updated_with_asset.illustrations[-1]
            updated = self._role_store.update_role(
                clean_role_id,
                featured_image=role_asset_path,
            )
            role_asset_paths = [role_asset_path]
            wrote_back_to_role = role_asset_path in updated.illustrations

        record = GeneratedImageRecord(
            id=record_id,
            created_at=created_at.isoformat(),
            role_id=clean_role_id,
            session_key=request.session_key.strip(),
            mode=request.mode,
            prompt=prompt,
            negative_prompt=request.negative_prompt,
            model=model,
            sampler=parameters["sampler"],
            steps=steps,
            seed=request.seed,
            width=width,
            height=height,
            base_image_path=base_image_path,
            output_paths=[str(output_path)],
            wrote_back_to_role=wrote_back_to_role,
            role_asset_paths=role_asset_paths,
        )
        self._store.write_json(meta_path, record.to_dict())
        self._store.append_record(record)
        return GenerateImageResult(
            record_id=record_id,
            created_at=record.created_at,
            mode=request.mode,
            model=model,
            seed=request.seed,
            width=width,
            height=height,
            output_paths=[str(output_path)],
            request_path=str(request_path),
            meta_path=str(meta_path),
            wrote_back_to_role=wrote_back_to_role,
            role_asset_paths=role_asset_paths,
        )

    def _validate_enabled(self) -> None:
        if not self._settings.enabled:
            raise ValueError("NovelAI 未启用")
        if not self._settings.token.strip():
            raise ValueError("NovelAI token 未配置")

    def _resolve_action(self, mode: str) -> str:
        if mode == "txt2img":
            if not self._settings.allow_txt2img:
                raise ValueError("当前未启用文生图")
            return "generate"
        if mode == "img2img":
            if not self._settings.allow_img2img:
                raise ValueError("当前未启用图生图")
            return "img2img"
        raise ValueError(f"不支持的生图模式: {mode}")

    def _resolve_dimensions(self, request: GenerateImageRequest) -> tuple[int, int]:
        if request.size_preset == "custom":
            width = int(request.custom_width or 0)
            height = int(request.custom_height or 0)
            if width <= 0 or height <= 0:
                raise ValueError("custom_width/custom_height 必须为正整数")
            if width > 1024 or height > 1024:
                raise ValueError("自定义尺寸单边不能超过 1024")
        else:
            preset = _SIZE_PRESETS.get(request.size_preset)
            if preset is None:
                raise ValueError(f"不支持的尺寸预设: {request.size_preset}")
            width, height = preset
        if width * height > self._settings.max_pixels:
            raise ValueError(f"当前仅允许总像素不超过 {self._settings.max_pixels}")
        return width, height

    def _resolve_steps(self, request: GenerateImageRequest) -> int:
        steps = int(request.steps or self._settings.max_steps)
        if steps <= 0:
            raise ValueError("steps 必须大于 0")
        if steps > self._settings.max_steps:
            raise ValueError(f"当前仅允许 steps 不超过 {self._settings.max_steps}")
        return steps

    def _resolve_model(self, request: GenerateImageRequest) -> str:
        requested_model = request.model.strip()
        allowed_models = {
            self._settings.default_model.strip(),
            self._settings.nsfw_model.strip(),
        }
        if requested_model:
            if requested_model not in allowed_models:
                raise ValueError(
                    f"当前仅允许模型 {self._settings.default_model} 或 {self._settings.nsfw_model}"
                )
            return requested_model
        return (
            self._settings.nsfw_model
            if self._settings.nsfw_enabled
            else self._settings.default_model
        )

    def _build_parameters(
        self,
        *,
        request: GenerateImageRequest,
        width: int,
        height: int,
        steps: int,
        model: str,
    ) -> dict[str, Any]:
        sampler = request.sampler.strip() or "k_euler_ancestral"
        parameters: dict[str, Any] = {
            "width": width,
            "height": height,
            "steps": steps,
            "sampler": sampler,
            "n_samples": self._settings.default_samples,
            "negative_prompt": request.negative_prompt,
            "scale": 5,
        }
        if self._is_v45_model(model):
            parameters.update(
                {
                    "params_version": 3,
                    "noise_schedule": "native",
                    "cfg_rescale": 0,
                    "ucPreset": 0,
                    "qualityToggle": False,
                    "dynamic_thresholding": False,
                    "characterPrompts": [],
                    "controlnet_strength": 1,
                    "deliberate_euler_ancestral_bug": False,
                    "prefer_brownian": True,
                    "reference_image_multiple": [],
                    "reference_information_extracted_multiple": [],
                    "reference_strength_multiple": [],
                    "skip_cfg_above_sigma": None,
                    "use_coords": False,
                    "v4_prompt": {
                        "caption": {
                            "base_caption": request.prompt,
                            "char_captions": [],
                        },
                        "use_coords": False,
                        "use_order": True,
                    },
                    "v4_negative_prompt": {
                        "caption": {
                            "base_caption": request.negative_prompt,
                            "char_captions": [],
                        },
                    },
                }
            )
        return parameters

    def _load_base_image(self, raw_path: str) -> tuple[str, str]:
        clean_path = raw_path.strip()
        if not clean_path:
            raise ValueError("img2img 请求缺少 base_image_path")
        file_path = _resolve_path(clean_path, self._workspace)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"输入图片不存在: {clean_path}")
        raw = file_path.read_bytes()
        mime = _detect_supported_image_mime_from_header(raw[:4096])
        if mime is None:
            raise ValueError("输入图片格式非法，仅支持 PNG、JPEG、GIF、BMP、WebP")
        return str(file_path), base64.b64encode(raw).decode("utf-8")

    def _extract_primary_image(self, response: Any) -> tuple[bytes, str]:
        response.raise_for_status()
        content_type = str(response.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("上游未返回可用图片")
            raw_images = payload.get("images")
            if not isinstance(raw_images, list) or not raw_images:
                raise ValueError("上游未返回可用图片")
            first = raw_images[0]
            if not isinstance(first, str) or not first.strip():
                raise ValueError("上游未返回可用图片")
            body = base64.b64decode(first)
            return body, self._detect_output_suffix(body)
        body = bytes(response.content)
        if "application/zip" in content_type or body.startswith(b"PK\x03\x04"):
            return self._extract_first_image_from_zip(body)
        return body, self._detect_output_suffix(body)

    def _extract_first_image_from_zip(self, body: bytes) -> tuple[bytes, str]:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            for name in archive.namelist():
                content = archive.read(name)
                try:
                    suffix = self._detect_output_suffix(content)
                except ValueError:
                    continue
                return content, suffix
        raise ValueError("上游未返回可用图片")

    def _detect_output_suffix(self, body: bytes) -> str:
        mime = _detect_supported_image_mime_from_header(body[:4096])
        if mime is None:
            raise ValueError("上游响应不是支持的图片格式")
        suffix = _SUPPORTED_OUTPUT_SUFFIX.get(mime)
        if suffix is None:
            raise ValueError("上游响应不是支持的图片格式")
        return suffix

    def _is_v45_model(self, model: str) -> bool:
        return model.startswith("nai-diffusion-4-5")

    async def _rewrite_http_error(
        self,
        exc: httpx.HTTPStatusError,
        *,
        model: str,
    ) -> ValueError:
        response = exc.response
        if response is None:
            return ValueError(f"NovelAI 请求失败: {exc}")
        detail = response.text.strip()
        if response.status_code != 500 or model != self._settings.default_model:
            return ValueError(
                f"NovelAI 请求失败: HTTP {response.status_code}"
                + (f" - {detail}" if detail else "")
            )
        user_data = await self._safe_fetch_user_data()
        if not user_data:
            return ValueError("NovelAI 上游返回 500，且未能读取账号状态信息。")
        subscription = user_data.get("subscription")
        information = user_data.get("information")
        if not isinstance(subscription, dict) or not isinstance(information, dict):
            return ValueError("NovelAI 上游返回 500，且账号状态信息结构异常。")
        active = bool(subscription.get("active"))
        perks = subscription.get("perks")
        image_generation = (
            bool(perks.get("imageGeneration"))
            if isinstance(perks, dict)
            else False
        )
        trial_images_left = int(information.get("trialImagesLeft") or 0)
        return ValueError(
            f"NovelAI 上游对模型 {model} 返回 500：{detail or 'Internal Server Error'}。"
            " 诊断信息："
            f"subscription.active={active}, "
            f"perks.imageGeneration={image_generation}, "
            f"trialImagesLeft={trial_images_left}。"
        )

    async def _safe_fetch_user_data(self) -> dict[str, Any]:
        try:
            return await self._client.fetch_user_data()
        except Exception:
            return {}
