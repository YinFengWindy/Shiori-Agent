"""Core socket contracts: keys and protocols shared across a generation.

Each module holds one service's ``Key`` and the protocol behind it
(refactor plan §1). Plugins inject them by key name. The host provides the
keys it owns before any plugin starts. ``MEMORY_ENGINE`` is the exception:
a plugin provides it.
"""
