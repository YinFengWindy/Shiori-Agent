"""Reply presentation accepts only a usable, unambiguous separator line."""

import pytest

from shiori_sdk.reply_sequence import ReplySequencePolicy


@pytest.mark.parametrize("separator", ["", " ", " x", "x\ny", "x\ry", "```x"])
def test_rejects_invalid_separator(separator):
    with pytest.raises(ValueError):
        ReplySequencePolicy(separator)
