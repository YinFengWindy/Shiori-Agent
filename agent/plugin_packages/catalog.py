from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from agent.plugin_packages.contracts import (
    HOST_PLUGIN_API_VERSION,
    PLUGIN_REPOSITORY_MANIFEST_PATH,
    PluginCatalogEntry,
    PluginManifest,
    PluginManifestError,
    PluginRelease,
    current_host_platform,
)


class HttpGetter(Protocol):
    """Minimal asynchronous HTTP contract required by the GitHub catalog."""

    async def get(self, url: str, **kwargs: Any) -> httpx.Response: ...


class GitHubPluginCatalog:
    """Discovers installable plugin releases from one GitHub Organization."""

    def __init__(
        self,
        requester: HttpGetter,
        *,
        organization: str,
        api_version: int = HOST_PLUGIN_API_VERSION,
        os_name: str | None = None,
        arch: str | None = None,
        token: str | None = None,
    ) -> None:
        clean_organization = organization.strip()
        if not clean_organization:
            raise ValueError("plugin organization is required")
        host_os, host_arch = current_host_platform()
        self._requester = requester
        self._organization = clean_organization
        self._api_version = api_version
        self._os_name = os_name or host_os
        self._arch = arch or host_arch
        self._token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    async def list_plugins(self) -> list[PluginCatalogEntry]:
        """Returns repositories containing a valid plugin manifest."""

        repositories = await self._list_repositories()
        entries: list[PluginCatalogEntry] = []
        for repository in repositories:
            entry = await self._load_repository(repository)
            if entry is not None:
                entries.append(entry)
        return sorted(
            entries, key=lambda item: (item.manifest.name.lower(), item.repository)
        )

    async def get_plugin(self, repository: str) -> PluginCatalogEntry:
        """Loads one named repository and fails when it is not a valid plugin."""

        clean_repository = repository.strip()
        expected_prefix = f"{self._organization}/"
        full_name = (
            clean_repository
            if "/" in clean_repository
            else f"{self._organization}/{clean_repository}"
        )
        if not full_name.startswith(expected_prefix) or full_name.count("/") != 1:
            raise ValueError(
                "plugin repository must belong to the configured organization"
            )
        response = await self._get(f"https://api.github.com/repos/{full_name}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("GitHub repository response must be an object")
        entry = await self._load_repository(payload, require_manifest=True)
        if entry is None:
            raise ValueError(f"repository is not a valid plugin: {full_name}")
        return entry

    async def _list_repositories(self) -> list[Mapping[str, Any]]:
        repositories: list[Mapping[str, Any]] = []
        page = 1
        while True:
            response = await self._get(
                f"https://api.github.com/orgs/{quote(self._organization, safe='')}/repos",
                params={"type": "public", "per_page": 100, "page": page},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("GitHub Organization repositories must be an array")
            batch = [item for item in payload if isinstance(item, Mapping)]
            repositories.extend(batch)
            if len(payload) < 100:
                return repositories
            page += 1

    async def _load_repository(
        self,
        repository: Mapping[str, Any],
        *,
        require_manifest: bool = False,
    ) -> PluginCatalogEntry | None:
        full_name = str(repository.get("full_name") or "").strip()
        repository_url = str(repository.get("html_url") or "").strip()
        if not full_name:
            return None
        manifest_response = await self._get(
            f"https://api.github.com/repos/{full_name}/contents/"
            f"{quote(PLUGIN_REPOSITORY_MANIFEST_PATH, safe='/')}"
        )
        if manifest_response.status_code == 404 and not require_manifest:
            return None
        manifest_response.raise_for_status()
        manifest = self._decode_manifest(manifest_response, repository=full_name)
        if not manifest.supports_host(
            os_name=self._os_name,
            arch=self._arch,
            api_version=self._api_version,
        ):
            return PluginCatalogEntry(
                repository=full_name,
                repository_url=repository_url,
                manifest=manifest,
                release=None,
                unavailable_reason="incompatible_host",
            )
        release, reason = await self._latest_release(full_name, manifest)
        return PluginCatalogEntry(
            repository=full_name,
            repository_url=repository_url,
            manifest=manifest,
            release=release,
            unavailable_reason=reason,
        )

    def _decode_manifest(
        self,
        response: httpx.Response,
        *,
        repository: str,
    ) -> PluginManifest:
        payload = response.json()
        if not isinstance(payload, Mapping) or payload.get("encoding") != "base64":
            raise PluginManifestError(
                f"GitHub manifest response is not base64 content: {repository}"
            )
        encoded = payload.get("content")
        if not isinstance(encoded, str):
            raise PluginManifestError(
                f"GitHub manifest content is missing: {repository}"
            )
        try:
            raw = base64.b64decode(encoded, validate=False)
        except ValueError as exc:
            raise PluginManifestError(
                f"GitHub manifest content is invalid base64: {repository}"
            ) from exc
        return PluginManifest.from_json_bytes(
            raw,
            source=f"{repository}/{PLUGIN_REPOSITORY_MANIFEST_PATH}",
        )

    async def _latest_release(
        self,
        repository: str,
        manifest: PluginManifest,
    ) -> tuple[PluginRelease | None, str | None]:
        response = await self._get(
            f"https://api.github.com/repos/{repository}/releases/latest"
        )
        if response.status_code == 404:
            return None, "release_not_found"
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("GitHub release response must be an object")
        tag = str(payload.get("tag_name") or "").strip()
        if tag.lstrip("v") != manifest.version:
            return None, "release_version_mismatch"
        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list):
            return None, "release_assets_missing"
        assets = {
            str(item.get("name") or ""): str(item.get("browser_download_url") or "")
            for item in raw_assets
            if isinstance(item, Mapping)
        }
        package_url = assets.get(manifest.release.asset, "")
        checksums_url = assets.get(manifest.release.checksums_asset, "")
        if not package_url or not checksums_url:
            return None, "release_assets_missing"
        return (
            PluginRelease(
                tag=tag,
                package_url=package_url,
                checksums_url=checksums_url,
            ),
            None,
        )

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Shiori-Desktop-Plugin-Installer",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return await self._requester.get(url, headers=headers, **kwargs)
