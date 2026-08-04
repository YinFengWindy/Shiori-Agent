from __future__ import annotations

import asyncio
import hashlib
import inspect
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from core.integrations.novelai import GenerateImageRequest, NovelAIService
from core.roles import RoleStore

from .role_difference_image import remove_edge_connected_background

# Progress events are deliberately smaller than the final serialized role snapshot.
RoleDifferenceProgressEmitter = Callable[
    [dict[str, Any]], Awaitable[None] | None
]

DEFAULT_ROLE_DIFFERENCES: tuple[tuple[str, str], ...] = (
    ("neutral", "calm neutral expression"),
    ("happy", "bright happy smile"),
    ("surprised", "surprised expression with widened eyes"),
    ("angry", "angry expression with furrowed brows"),
    ("sad", "sad expression with downcast eyes"),
)


class RoleDifferenceGenerationService:
    """Generates stable role-expression cutouts and persists them atomically."""

    def __init__(
        self,
        *,
        role_store: RoleStore,
        novelai_service: NovelAIService | None,
        workspace: Path,
    ) -> None:
        self._role_store = role_store
        self._novelai_service = novelai_service
        self._workspace = workspace
        self._active_roles: set[str] = set()

    async def generate(
        self,
        *,
        role_id: str,
        base_asset: str,
        emit_progress: RoleDifferenceProgressEmitter,
    ) -> dict[str, Any]:
        """Generate all default differences from one validated base asset."""

        clean_role_id = role_id.strip()
        clean_base_asset = base_asset.strip()
        if not clean_role_id or not clean_base_asset:
            raise ValueError("role_id 和 base_asset 不能为空")
        if clean_role_id in self._active_roles:
            raise ValueError("该角色正在生成差分")
        if self._novelai_service is None:
            raise ValueError("NovelAI 未配置")

        role = self._role_store.get_role(clean_role_id)
        if role is None:
            raise KeyError(f"role 不存在: {clean_role_id}")
        base_path = self._role_store.resolve_role_asset_path(
            clean_role_id,
            clean_base_asset,
        )
        if base_path is None or not base_path.is_file():
            raise ValueError(f"角色基准素材不存在: {clean_base_asset}")

        self._active_roles.add(clean_role_id)
        job_id = f"role-differences-{uuid.uuid4().hex}"
        stages = [
            {"id": difference_id, "status": "pending", "error": ""}
            for difference_id, _prompt in DEFAULT_ROLE_DIFFERENCES
        ]
        try:
            runtime_dir = self._workspace / "private_runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            await self._emit_progress(
                emit_progress,
                job_id=job_id,
                role_id=clean_role_id,
                phase="started",
                current="",
                completed=0,
                stages=stages,
            )
            with tempfile.TemporaryDirectory(
                prefix=f"{job_id}-",
                dir=runtime_dir,
            ) as temp_dir:
                generated_paths: list[Path] = []
                base_hash = _sha256_file(base_path)
                for index, (difference_id, expression_prompt) in enumerate(
                    DEFAULT_ROLE_DIFFERENCES
                ):
                    stages[index]["status"] = "generating"
                    await self._emit_progress(
                        emit_progress,
                        job_id=job_id,
                        role_id=clean_role_id,
                        phase="generating",
                        current=difference_id,
                        completed=index,
                        stages=stages,
                    )
                    result = await self._novelai_service.generate(
                        GenerateImageRequest(
                            prompt=(
                                "same character as the reference image, consistent face, "
                                "hairstyle, hair color, eye color, outfit and body proportions, "
                                "single character, centered upper body, anime illustration, "
                                f"plain white background, {expression_prompt}"
                            ),
                            negative_prompt=(
                                "different character, multiple characters, scenery, complex "
                                "background, cropped head, extra limbs, blurry, low quality"
                            ),
                            mode="img2img",
                            base_image_path=str(base_path),
                            strength=0.38,
                            noise=0.08,
                            size_preset="square",
                            steps=24,
                            seed=_stable_seed(base_hash, difference_id),
                            sampler="k_euler_ancestral",
                        )
                    )
                    generated_path = Path(
                        str(result.output_paths[0] if result.output_paths else "").strip()
                    )
                    if not generated_path.is_file():
                        raise ValueError(f"{difference_id} 未返回有效图片")
                    cutout_path = Path(temp_dir) / f"{difference_id}.png"
                    await asyncio.to_thread(
                        remove_edge_connected_background,
                        generated_path,
                        cutout_path,
                    )
                    generated_paths.append(cutout_path)
                    stages[index]["status"] = "completed"
                    await self._emit_progress(
                        emit_progress,
                        job_id=job_id,
                        role_id=clean_role_id,
                        phase="completed",
                        current=difference_id,
                        completed=index + 1,
                        stages=stages,
                    )

                updated_role = self._persist_generated_assets(
                    clean_role_id,
                    generated_paths,
                )
            category = updated_role.asset_categories[-1]
            await self._emit_progress(
                emit_progress,
                job_id=job_id,
                role_id=clean_role_id,
                phase="finished",
                current="",
                completed=len(DEFAULT_ROLE_DIFFERENCES),
                stages=stages,
                category_id=category.id,
                category_name=category.name,
            )
            return {
                "job_id": job_id,
                "category_id": category.id,
                "category_name": category.name,
                "role": updated_role,
            }
        except Exception as exc:
            failed_stage = next(
                (stage for stage in stages if stage["status"] == "generating"),
                None,
            )
            if failed_stage is not None:
                failed_stage["status"] = "failed"
                failed_stage["error"] = str(exc)
            await self._emit_progress(
                emit_progress,
                job_id=job_id,
                role_id=clean_role_id,
                phase="failed",
                current=failed_stage["id"] if failed_stage else "",
                completed=sum(stage["status"] == "completed" for stage in stages),
                stages=stages,
                error=str(exc),
            )
            raise
        finally:
            self._active_roles.discard(clean_role_id)

    def _persist_generated_assets(
        self,
        role_id: str,
        generated_paths: list[Path],
    ):
        role = self._role_store.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        category_id = f"generated-differences-{uuid.uuid4().hex[:12]}"
        category_name = _next_category_name(
            [category.name for category in role.asset_categories]
        )
        categories = [
            {
                "id": category.id,
                "name": category.name,
                "allow_role_send": category.allow_role_send,
            }
            for category in role.asset_categories
        ]
        categories.append(
            {"id": category_id, "name": category_name, "allow_role_send": False}
        )
        return self._role_store.update_role(
            role_id,
            asset_categories=categories,
            illustration_sources=[str(path) for path in generated_paths],
            illustration_category_id=category_id,
        )

    @staticmethod
    async def _emit_progress(
        emitter: RoleDifferenceProgressEmitter,
        **payload: Any,
    ) -> None:
        result = emitter(payload)
        if inspect.isawaitable(result):
            await result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_seed(base_hash: str, difference_id: str) -> int:
    digest = hashlib.sha256(f"{base_hash}:{difference_id}".encode("ascii")).digest()
    return int.from_bytes(digest[:4], "big")


def _next_category_name(existing_names: list[str]) -> str:
    used = {name.casefold() for name in existing_names}
    base = "AI 差分"
    if base.casefold() not in used:
        return base
    index = 2
    while f"{base} {index}".casefold() in used:
        index += 1
    return f"{base} {index}"
