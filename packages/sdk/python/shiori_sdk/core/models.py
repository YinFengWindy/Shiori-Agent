"""``MAIN_PROVIDER`` and ``MAIN_MODEL``: the chat model plugins may inject.

These are the generation's main chat provider and its model name, the same
pair a passive turn uses. The light model is ``LIGHT_PROVIDER`` /
``LIGHT_MODEL`` in ``shiori_sdk.core.services``, a different pair. A plugin
lists ``main_provider`` and ``main_model`` in ``inject`` and ``require``s
them; the host provides both before any plugin starts.
"""

from __future__ import annotations

from shiori_sdk.kernel import Key
from shiori_sdk.models import ModelProvider

MAIN_PROVIDER: Key[ModelProvider] = Key("main_provider")
"""The generation's main chat provider."""

MAIN_MODEL: Key[str] = Key("main_model")
"""The model name paired with ``MAIN_PROVIDER``."""
