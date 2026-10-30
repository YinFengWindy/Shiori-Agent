"""Core socket contracts: keys and protocols shared across a generation.

Each module holds one service's ``Key`` and the protocol behind it
(refactor plan §1). Plugins inject them by key name. The host provides the
keys it owns before any plugin starts. ``MEMORY_ENGINE`` is the exception
among the memory sockets: a plugin provides it. P6a adds more plugin-provided
keys (``REPLY_POLICY``, ``SCENE``, ``AFFECTION``) and the host ports they
require (``SCENE_HOST``, ``AFFECTION_HOST``, ``MCP_TOOLS``). P6s adds the
host port ``SCHEDULE_HOST`` for the scheduler. ``services`` holds
the keys for the former capability surface (P4-3); ``tools`` holds tool-call
events, not the ``tools`` key.
"""
