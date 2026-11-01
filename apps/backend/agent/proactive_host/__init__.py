"""``PROACTIVE_HOST``: the host services a proactive tick calls.

``runner`` pins the generation; ``natural`` owns the tick's natural reply
plan, ``tools`` the checked tool calls and ``reads`` the host facts.
"""

from agent.proactive_host.runner import HostProactiveRunner

__all__ = ["HostProactiveRunner"]
