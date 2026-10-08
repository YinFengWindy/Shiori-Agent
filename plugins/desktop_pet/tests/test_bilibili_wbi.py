"""WBI signing reproduces the published bilibili-API-collect example."""

import pytest

from plugins.desktop_pet.backend.bilibili_wbi import sign_wbi, wbi_mixin_key

IMG = "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png"
SUB = "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"


def test_documented_vector_signs_identically():
    key = wbi_mixin_key(IMG, SUB)
    assert key == "ea1db124af3c7062474693fa704f4ff8"
    signed = sign_wbi({"foo": "114", "bar": "514", "zab": 1919810}, key, 1702204169)
    assert signed["wts"] == "1702204169"
    assert signed["w_rid"] == "8f6f2b5b3d485fe1886cec6a0be8c5d4"


def test_reserved_characters_are_removed_before_signing():
    key = wbi_mixin_key(IMG, SUB)
    assert sign_wbi({"q": "a!'()*b"}, key, 1) == sign_wbi({"q": "ab"}, key, 1)


def test_malformed_keys_are_rejected():
    with pytest.raises(ValueError, match="WBI"):
        wbi_mixin_key("https://x/short.png", SUB)
