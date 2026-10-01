"""CHARX (ZIP) adapter with bounded, read-only extraction."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

from .json_adapter import adapt_json
from .models import RoleCardAsset, RoleCardImportPreview, RoleCardImportReport
from .safety import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_MEMBERS,
    MAX_MEMBER_BYTES,
    MAX_SOURCE_BYTES,
    safe_archive_path,
    validate_image,
)


def adapt_charx(source: str | Path) -> RoleCardImportPreview:
    """Parse a CHARX card and return an in-memory preview without extraction."""
    path = Path(source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"角色卡包不存在: {path}")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError(
            f"角色卡源文件超过大小限制（最多 {MAX_SOURCE_BYTES // (1024 * 1024)} MiB）"
        )
    return adapt_charx_bytes(path.read_bytes())


def adapt_charx_bytes(data: bytes) -> RoleCardImportPreview:
    """Parse a CHARX ZIP from memory with the same limits as the file adapter."""
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError(
            f"角色卡源文件超过大小限制（最多 {MAX_SOURCE_BYTES // (1024 * 1024)} MiB）"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("角色卡包不是有效 ZIP") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"角色卡包内条目过多（最多 {MAX_ARCHIVE_MEMBERS} 个条目）")
        names: dict[str, zipfile.ZipInfo] = {}
        total_size = 0
        for info in infos:
            name = safe_archive_path(info.filename)
            if name in names:
                raise ValueError("角色卡包包含重复路径")
            if info.flag_bits & 0x1:
                raise ValueError("不支持加密角色卡包")
            if ((info.external_attr >> 16) & 0xF000) == 0xA000:
                raise ValueError("角色卡包不允许符号链接")
            if info.is_dir():
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(
                    f"角色卡包单条目超过大小限制（最多 {MAX_MEMBER_BYTES // (1024 * 1024)} MiB）"
                )
            total_size += info.file_size
            if total_size > MAX_ARCHIVE_BYTES:
                raise ValueError(
                    f"角色卡包解压总大小超过限制（最多 {MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB）"
                )
            names[name] = info
        if "card.json" not in names:
            raise ValueError("角色卡包缺少角色信息文件（根目录 card.json）")
        try:
            payload = json.loads(archive.read(names["card.json"]).decode("utf-8"))
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            RuntimeError,
            zipfile.BadZipFile,
        ) as error:
            raise ValueError("角色卡包内角色信息文件无法解析（card.json）") from error
        preview = adapt_json(payload, source_name="card.json", format_name="charx")
        assets: list[RoleCardAsset] = []
        unsupported_resources: list[str] = []
        for candidate in preview.assets:
            info = names.get(candidate.path)
            if info is None:
                unsupported_resources.append(candidate.path)
                continue
            try:
                raw = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise ValueError(f"角色卡素材 {candidate.path} 无法读取") from error
            try:
                _, media_type = validate_image(raw, name=f"角色卡素材 {candidate.path}")
            except ValueError:
                unsupported_resources.append(candidate.path)
                continue
            assets.append(replace(candidate, data=raw, media_type=media_type))
        report = preview.report
        report = RoleCardImportReport(
            adapted_fields=report.adapted_fields,
            discarded_fields=report.discarded_fields,
            unsupported_macros=report.unsupported_macros,
            unsupported_resources=tuple(
                dict.fromkeys((*report.unsupported_resources, *unsupported_resources))
            ),
            unsupported_rules=report.unsupported_rules,
        )
        return RoleCardImportPreview(
            name=preview.name,
            description=preview.description,
            profile=preview.profile,
            assets=tuple(assets),
            report=report,
            provenance=preview.provenance,
        )
