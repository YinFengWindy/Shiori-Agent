from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from desktop_bridge.observation_safety import safe_observation_text

MAX_IMAGE_BASE64_CHARS = 12 * 1024 * 1024


@dataclass(frozen=True)
class ObservationFrame:
    """Validated ephemeral primary-display frame received from the desktop host."""

    role_id: str
    frame_id: str
    captured_at: str
    width: int
    height: int
    scale_factor: float
    image_base64: str


def parse_observation_frame(payload: dict[str, Any]) -> ObservationFrame:
    """Validates an ephemeral PNG frame and its primary-display metadata."""

    image_base64 = str(payload.get("image_base64") or "").strip()
    if not image_base64 or len(image_base64) > MAX_IMAGE_BASE64_CHARS:
        raise ValueError("观察帧为空或超过大小上限")
    try:
        image = base64.b64decode(image_base64, validate=True)
        width = int(payload.get("width") or 0)
        height = int(payload.get("height") or 0)
        scale_factor = float(payload.get("scale_factor") or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("观察帧格式无效") from exc
    if not image.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("观察帧必须是 PNG 图像")
    if width <= 0 or height <= 0 or scale_factor <= 0:
        raise ValueError("观察帧尺寸无效")
    role_id = str(payload.get("role_id") or "").strip()[:128]
    frame_id = str(payload.get("frame_id") or "").strip()[:128]
    captured_at = str(payload.get("captured_at") or "").strip()
    if not role_id or not frame_id or not captured_at:
        raise ValueError("观察帧元数据不完整")
    try:
        datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("观察帧时间无效") from exc
    return ObservationFrame(
        role_id=role_id,
        frame_id=frame_id,
        captured_at=captured_at,
        width=width,
        height=height,
        scale_factor=scale_factor,
        image_base64=image_base64,
    )


def normalize_observation_result(
    frame: ObservationFrame,
    value: dict[str, Any],
) -> dict[str, Any]:
    """Validates one model result and removes all unsafe output candidates."""

    risks = _normalize_risks(value.get("risks"))
    targets = _parse_targets(frame, value.get("targets"))
    interface_summary = safe_observation_text(
        value.get("interface_summary"), limit=400
    )
    activity_key = safe_observation_text(value.get("activity_key"), limit=80)
    return {
        "frame_id": frame.frame_id,
        "captured_at": frame.captured_at,
        "width": frame.width,
        "height": frame.height,
        "scale_factor": frame.scale_factor,
        "interface_summary": interface_summary or "当前桌面活动",
        "activity_key": activity_key or "desktop-activity",
        "targets": targets,
        "risks": risks,
        "bubble": safe_observation_text(value.get("bubble"), limit=120),
        "experience_candidate": safe_observation_text(
            value.get("experience_candidate"), limit=280
        ),
    }


def _normalize_risks(value: object) -> list[str]:
    """Keeps model diagnostics optional so they cannot block screen observation."""

    if not isinstance(value, list):
        return []
    risks: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        risk = " ".join(item.split()).strip()
        if not risk:
            continue
        if risk not in risks:
            risks.append(risk)
    return risks


def _parse_targets(
    frame: ObservationFrame,
    value: object,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("观察目标结构无效")
    targets: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("观察目标结构无效")
        raw_label = item.get("label")
        label = safe_observation_text(raw_label, limit=80)
        try:
            x = float(item["x"])
            y = float(item["y"])
            confidence = float(item["confidence"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("观察目标结构无效") from exc
        if (
            not label
            or not math.isfinite(x)
            or not math.isfinite(y)
            or not math.isfinite(confidence)
            or not 0 <= x <= frame.width
            or not 0 <= y <= frame.height
            or not 0 <= confidence <= 1
        ):
            raise ValueError("观察目标结构无效")
        targets.append(
            {"label": label, "x": x, "y": y, "confidence": confidence}
        )
        if len(targets) > 30:
            raise ValueError("观察目标数量超过限制")
    return targets
