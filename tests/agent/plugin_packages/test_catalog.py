from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from agent.plugin_packages.catalog import GitHubPluginCatalog


def _manifest(*, api_version: int = 1) -> dict[str, object]:
    return {
        "schema_version": 1,
        "plugin_id": "desktop-pet",
        "name": "Desktop Pet",
        "description": "Desktop overlay pet",
        "version": "1.0.0",
        "plugin_api_version": api_version,
        "platforms": [{"os": "win32", "arch": "x64"}],
        "entrypoints": {"backend": "backend/main.py"},
        "capabilities": ["agent.tool"],
        "permissions": [],
        "tools": [
            {
                "remote_name": "pet_action",
                "name": "pet_action",
                "always_on": True,
            }
        ],
        "release": {
            "asset": "desktop-pet.zip",
            "checksums_asset": "checksums.json",
        },
    }


def _response(url: str, status: int, payload: object) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("GET", url),
    )


class FakeRequester:
    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        self.responses = responses

    async def get(self, url: str, **_: Any) -> httpx.Response:
        return self.responses[url]


def _content_response(url: str, manifest: dict[str, object]) -> httpx.Response:
    encoded = base64.b64encode(json.dumps(manifest).encode("utf-8")).decode("ascii")
    return _response(url, 200, {"encoding": "base64", "content": encoded})


async def test_catalog_ignores_non_plugins_and_resolves_release_assets() -> None:
    repos_url = "https://api.github.com/orgs/Shiori-Plugins/repos"
    pet_manifest_url = (
        "https://api.github.com/repos/Shiori-Plugins/desktop-pet/contents/"
        ".akashic-plugin/plugin.json"
    )
    notes_manifest_url = (
        "https://api.github.com/repos/Shiori-Plugins/notes/contents/"
        ".akashic-plugin/plugin.json"
    )
    release_url = (
        "https://api.github.com/repos/Shiori-Plugins/desktop-pet/releases/latest"
    )
    requester = FakeRequester(
        {
            repos_url: _response(
                repos_url,
                200,
                [
                    {
                        "full_name": "Shiori-Plugins/desktop-pet",
                        "html_url": "https://github.com/Shiori-Plugins/desktop-pet",
                    },
                    {
                        "full_name": "Shiori-Plugins/notes",
                        "html_url": "https://github.com/Shiori-Plugins/notes",
                    },
                ],
            ),
            pet_manifest_url: _content_response(pet_manifest_url, _manifest()),
            notes_manifest_url: _response(notes_manifest_url, 404, {}),
            release_url: _response(
                release_url,
                200,
                {
                    "tag_name": "v1.0.0",
                    "assets": [
                        {
                            "name": "desktop-pet.zip",
                            "browser_download_url": "https://download/pet.zip",
                        },
                        {
                            "name": "checksums.json",
                            "browser_download_url": "https://download/checksums.json",
                        },
                    ],
                },
            ),
        }
    )
    catalog = GitHubPluginCatalog(
        requester,
        organization="Shiori-Plugins",
        os_name="win32",
        arch="x64",
    )

    entries = await catalog.list_plugins()

    assert len(entries) == 1
    assert entries[0].repository == "Shiori-Plugins/desktop-pet"
    assert entries[0].installable is True
    assert entries[0].release is not None
    assert entries[0].release.package_url == "https://download/pet.zip"


async def test_catalog_marks_incompatible_manifest_without_querying_release() -> None:
    repos_url = "https://api.github.com/orgs/Shiori-Plugins/repos"
    manifest_url = (
        "https://api.github.com/repos/Shiori-Plugins/desktop-pet/contents/"
        ".akashic-plugin/plugin.json"
    )
    requester = FakeRequester(
        {
            repos_url: _response(
                repos_url,
                200,
                [{"full_name": "Shiori-Plugins/desktop-pet", "html_url": "repo"}],
            ),
            manifest_url: _content_response(
                manifest_url,
                _manifest(api_version=2),
            ),
        }
    )
    catalog = GitHubPluginCatalog(
        requester,
        organization="Shiori-Plugins",
        os_name="win32",
        arch="x64",
    )

    entries = await catalog.list_plugins()

    assert entries[0].installable is False
    assert entries[0].unavailable_reason == "incompatible_host"
