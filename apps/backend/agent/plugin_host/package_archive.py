"""Read-only zip validation using the same package-root contract as manual folders."""

from __future__ import annotations

import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.package_contract import ValidatedPackage, validate_package
from agent.plugin_host.package_paths import package_path

MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 4096


def validate_package_zip(
    archive: Path, *, host: HostRuntimeContract | None = None
) -> ValidatedPackage:
    """Validate canonical zip members, then inspect a temporary extraction.

    This performs no installation, trust grant, workspace write or code execution.
    A release zip has manifest.yaml at its root (no wrapping plugin-ID directory).
    """
    try:
        with (
            ZipFile(archive) as source,
            TemporaryDirectory(prefix="shiori-contract-") as scratch,
        ):
            members = source.infolist()
            if (
                len(members) > MAX_PACKAGE_MEMBERS
                or sum(item.file_size for item in members) > MAX_PACKAGE_BYTES
            ):
                raise PackageContractError(
                    "package_limit", "zip", "Package exceeds 4096 members or 64 MiB"
                )
            seen: set[str] = set()
            for member in members:
                name = package_path(
                    (
                        member.orig_filename.rstrip("/")
                        if member.is_dir()
                        else member.orig_filename
                    ),
                    "zip.member",
                )
                mode = member.external_attr >> 16
                if (
                    stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or member.flag_bits & 1
                ):
                    raise PackageContractError(
                        "unsupported_member",
                        "zip.member",
                        "Links, special files and encryption are unsupported",
                        path=name,
                    )
                if name.casefold() in seen:
                    raise PackageContractError(
                        "duplicate_path",
                        "zip.member",
                        "Duplicate or case-colliding path",
                        path=name,
                    )
                seen.add(name.casefold())
            if "manifest.yaml" not in {
                member.filename for member in members if not member.is_dir()
            }:
                raise PackageContractError(
                    "invalid_layout", "manifest", "Zip requires root manifest.yaml"
                )
            root = Path(scratch)
            # Names and member types are checked before creating any files.
            for member in members:
                target = root.joinpath(*member.filename.rstrip("/").split("/"))
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _ = target.write_bytes(source.read(member))
            return validate_package(root, host=host)
    except (OSError, BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise PackageContractError(
            "invalid_archive", "zip", str(exc), path=str(archive)
        ) from exc
