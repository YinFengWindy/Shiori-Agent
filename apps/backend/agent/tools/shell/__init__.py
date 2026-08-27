"""Shell 工具的稳定公共入口。"""

import asyncio
import json
import logging
import os
import time

from .background import (
    ShellTaskOutputTool,
    ShellTaskStopTool,
    _arm_background_timeout,
    _BackgroundTask,
    _BG_REGISTRY,
    _bg_kill,
    _bg_pump,
    _bg_timeout,
    _is_background_timeout,
    _on_background_task_done,
    _schedule_eviction,
)
from .constants import (
    _BANNED,
    _BG_EVICT_DELAY_S,
    _BG_TTL_S,
    _BLOCK_DEFAULT_MS,
    _BLOCK_MAX_MS,
    _BLOCKING_TIMEOUT,
    _DEFAULT_TIMEOUT,
    _FG_THRESHOLD,
    _IS_WINDOWS,
    _MAX_OUTPUT,
    _MAX_TIMEOUT,
    _NETWORK_CMDS,
    _NET_WRITE_FLAGS,
    _RESTRICTED_META_CHARS,
    _RESTRICTED_SHELL_RUNNERS,
    _STREAM_CHUNK_SIZE,
    _STREAM_DRAIN_GRACE_S,
)
from .environment import (
    _discover_nvm_node_bins,
    _discover_user_path_entries,
    _node_version_key,
    _prepend_existing_path_entries,
    _shell_env,
)
from .output import _err, _truncate, _write_full_output
from .runner import _kill_process_tree, _run, _subprocess_options
from .tools import ShellTool
from .validation import (
    _looks_like_path,
    _split_command,
    _strip_shell_quotes,
    _validate_command,
    _validate_network_command,
    _validate_restricted_absolute_path,
    _validate_restricted_command,
    _validate_restricted_cwd,
    _validate_restricted_token,
    _validate_url_target,
)

logger = logging.getLogger("agent.tools.shell")
