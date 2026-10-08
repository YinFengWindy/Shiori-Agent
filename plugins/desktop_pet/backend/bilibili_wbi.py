"""WBI request signing for Bilibili web APIs such as ``getDanmuInfo``.

Algorithm (as implemented by blivedm ``clients/web.py`` ``_WbiSigner`` and
verified 2026-10 against the live ``getDanmuInfo`` endpoint): the nav API's
``data.wbi_img`` gives two image URLs whose file stems, concatenated and
reordered by a fixed 32-entry index table, form the mixin key. A request is
signed by adding ``wts`` (unix seconds), sorting parameters by key, removing
``!'()*`` from values, URL-encoding and appending ``w_rid = md5(query + key)``.
"""

from __future__ import annotations

import hashlib
import urllib.parse

_MIXIN_INDEX = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
)  # fmt: skip
_FILTERED = frozenset("!'()*")


def wbi_mixin_key(img_url: str, sub_url: str) -> str:
    """Derive the signing key from the nav ``wbi_img`` URLs."""
    raw = _stem(img_url) + _stem(sub_url)
    if len(raw) < 64:
        raise ValueError("B 站 WBI 密钥格式无效")
    return "".join(raw[index] for index in _MIXIN_INDEX)


def sign_wbi(params: dict[str, str | int], key: str, now: int) -> dict[str, str]:
    """Return ``params`` with ``wts`` and ``w_rid`` added for unix time ``now``."""
    signed = {name: str(value) for name, value in {**params, "wts": now}.items()}
    ordered = {
        name: "".join(char for char in signed[name] if char not in _FILTERED)
        for name in sorted(signed)
    }
    query = urllib.parse.urlencode(ordered)
    digest = hashlib.md5((query + key).encode("utf-8")).hexdigest()
    return {**ordered, "w_rid": digest}


def _stem(url: str) -> str:
    return url.rpartition("/")[2].partition(".")[0]
