from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from plugins.qq.backend.channel.files import (
    MAX_FILE_BYTES,
    QQFile,
    extract_cq_files,
    receive_files,
)
from shiori_sdk.testing.channel_services import FakeAttachmentStore
from shiori_sdk.testing.http import FakeHttp


def test_file_segments_preserve_escaped_name_url_id_and_description():
    text, files = extract_cq_files(
        "看[CQ:file,name=论述&#44;新版.md,file_id=abc,size=123,busid=102,"
        "url=https://x.test/file?a=1&amp;b=2]"
    )
    assert text == "看[文件：论述,新版.md]"
    assert files == [
        QQFile("论述,新版.md", "https://x.test/file?a=1&b=2", "abc", 123, 102)
    ]


@pytest.mark.asyncio
async def test_cq_entities_decode_once_and_literal_codes_never_download(tmp_path):
    text, files = extract_cq_files(
        "&#91;CQ:file,name=literal.txt,url=https://x/secret&#93; "
        "[CQ:file,name=a&amp;copy;.txt,url=https://x/missing]"
    )
    assert [file.name for file in files] == ["a&copy;.txt"]
    http = FakeHttp(lambda _: httpx.Response(404))
    text, paths = await receive_files(
        text, files, http, FakeAttachmentStore(tmp_path), AsyncMock()
    )
    assert "a&copy;.txt；下载失败（HTTP 404）" in text and "©" not in text
    assert "[CQ:file,name=literal.txt" in text and not paths
    assert [request.url.path for request in http.requests] == ["/missing"]


@pytest.mark.asyncio
async def test_octet_stream_file_keeps_its_name_suffix_and_chinese_bytes(tmp_path):
    content = "明日香的心情\n第二段".encode()
    http = FakeHttp(
        lambda _: httpx.Response(
            200, content=content, headers={"content-type": "application/octet-stream"}
        )
    )
    resolve = AsyncMock(return_value="https://x.test/file")
    text, paths = await receive_files(
        "[文件：故事.md]",
        [QQFile("故事.md", file_id="id")],
        http,
        FakeAttachmentStore(tmp_path),
        resolve,
    )
    assert text == "[文件：故事.md]"
    [path] = map(Path, paths)
    assert "故事" in path.stem and path.suffix == ".md"
    assert path.read_bytes() == content
    resolve.assert_awaited_once_with(QQFile("故事.md", file_id="id"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file", "response", "error"),
    [
        (QQFile("a.pdf"), httpx.Response(200), "仅支持 txt/md"),
        (QQFile("a.txt", size=MAX_FILE_BYTES + 1), httpx.Response(200), "2 MiB"),
        (QQFile("a.txt"), httpx.Response(404), "HTTP 404"),
        (QQFile("a.txt"), httpx.Response(200, content=b"binary\x00"), "二进制"),
        (QQFile("a.md"), httpx.Response(200, content=b"\xff\xfe"), "UTF-8"),
        (
            QQFile("a.md"),
            httpx.Response(200, content=b"x" * (MAX_FILE_BYTES + 1)),
            "2 MiB",
        ),
    ],
)
async def test_unreceived_files_are_explicit_and_not_stored(
    tmp_path, file, response, error
):
    http = FakeHttp(lambda _: response)
    resolve = AsyncMock(return_value="https://x.test/file")
    text, paths = await receive_files(
        file.description,
        [file],
        http,
        FakeAttachmentStore(tmp_path),
        resolve,
    )
    assert paths == [] and error in text
    assert list(tmp_path.iterdir()) == []
    if file.name.endswith(".pdf") or file.size:
        resolve.assert_not_awaited()
        assert not http.requests


@pytest.mark.asyncio
async def test_download_timeout_reports_failure_without_exposing_signed_url(tmp_path):
    def fail(request):
        raise httpx.ReadTimeout("secret signed URL", request=request)

    file = QQFile("a.txt", "https://x.test/file?token=secret")
    text, paths = await receive_files(
        file.description,
        [file],
        FakeHttp(fail),
        FakeAttachmentStore(tmp_path),
        AsyncMock(),
    )
    assert "未接收正文" in text and "secret" not in text and paths == []


@pytest.mark.asyncio
async def test_duplicate_names_keep_failure_on_the_correct_file(tmp_path):
    files = [QQFile("a.txt", "https://x/ok"), QQFile("a.txt", "https://x/missing")]
    http = FakeHttp(
        lambda request: httpx.Response(
            200 if request.url.path == "/ok" else 404,
            content=b"text",
        )
    )
    text, paths = await receive_files(
        "[文件：a.txt] 和 [文件：a.txt]",
        files,
        http,
        FakeAttachmentStore(tmp_path),
        AsyncMock(),
    )
    assert text.startswith("[文件：a.txt] 和 [文件：a.txt；下载失败")
    assert len(paths) == 1
