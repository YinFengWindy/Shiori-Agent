"""Core socket contracts: keys and protocols the host's core modules provide.

Each module holds one core service's ``Key`` and the protocol behind it
(refactor plan §1). Plugins will inject them by key name; the host provides
them before any plugin starts.
"""
