"""Standalone standard-library callback client, run on the Shiori computer.

Credentials are read from the plugin-created connection file, never passed on
the command line or printed. Messages are JSON on stdin to preserve newlines.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 65536


def submit(config_file: Path, payload: object, *, handshake: bool = False):
    """Send exactly once to the authenticated loopback endpoint in a local file."""
    config = json.loads(config_file.read_text(encoding="utf-8"))
    if handshake:
        payload = {"protocol": "shiori-grok/1", "challenge": config["challenge"]}
    base = str(config["callback_url"])
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("回程配置不是本机入口")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("消息过长")
    request = urllib.request.Request(
        base + ("handshake" if handshake else "messages"),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['token']}",
        },
        method="POST",
    )

    # A local callback must never use system proxy settings or follow redirects
    # that could forward its private credential elsewhere.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("回程响应过长")
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Shiori 拒绝请求（HTTP {error.code}），请检查连接状态"
        ) from None
    except urllib.error.URLError:
        raise RuntimeError(
            "无法确认 Shiori 接收，请保留 message_id 检查状态，不要换 ID 重发"
        ) from None


def main() -> int:
    """Read one message from stdin and print only the non-secret receipt."""
    parser = argparse.ArgumentParser(description="向 Shiori 角色发送消息")
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--handshake", action="store_true")
    args = parser.parse_args()
    try:
        if args.handshake:
            payload = {"protocol": "shiori-grok/1"}
        else:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("消息过长")
            payload = json.loads(raw)
        result = submit(args.connection, payload, handshake=args.handshake)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        # Never include config contents or token-bearing HTTP request details.
        print(f"回程失败：{type(error).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
