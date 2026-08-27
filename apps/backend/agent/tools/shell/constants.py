"""Shell 工具共享常量。"""

import os

_DEFAULT_TIMEOUT = 60  # 秒（OpenCode 默认 1 分钟）
_FG_THRESHOLD = 15    # 前台最长等待秒数；超时自动转后台
_MAX_TIMEOUT = 600  # 秒（OpenCode 最大 10 分钟）
_BLOCKING_TIMEOUT = 21_600  # 秒（auto_promote=False 时默认 6 小时）
_MAX_OUTPUT = 30_000  # 字符（与 OpenCode MaxOutputLength 一致）
_STREAM_CHUNK_SIZE = 4096
_STREAM_DRAIN_GRACE_S = 0.2
_BLOCK_DEFAULT_MS = 30_000  # task_output block 默认单次等待
_BLOCK_MAX_MS = 30_000  # task_output block 单次硬上限：超过按上限，迫使长任务走轮询而非一次死等
_BG_TTL_S = 4 * 3600  # 后台任务最长存活时间：4 小时
_BG_EVICT_DELAY_S = 300  # 任务完成后延迟 5 分钟清理注册表和日志
_IS_WINDOWS = os.name == "nt"

# 禁止命令（对应 OpenCode bannedCommands）
_BANNED = frozenset(
    {
        "curlie",
        "axel",
        "aria2c",
        "nc",
        "telnet",
        "lynx",
        "w3m",
        "links",
        "http-prompt",
        "chrome",
        "firefox",
        "safari",
    }
)

# 对网络命令启用额外安全限制
_NETWORK_CMDS = frozenset({"curl", "wget", "http", "httpie", "xh"})
_NET_WRITE_FLAGS = frozenset(
    {
        # curl
        "-o",
        "--output",
        "-O",
        "--remote-name",
        "-T",
        "--upload-file",
        "-F",
        "--form",
        "--form-string",
        # wget
        "-O",
        "--output-document",
        "--post-file",
        # httpie/xh
        "--download",
        "--output",
        "--offline",
        "@",
    }
)
_RESTRICTED_META_CHARS = ("|", ";", "&", ">", "<", "`", "$(")
_RESTRICTED_SHELL_RUNNERS = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "fish",
        "python",
        "python3",
        "node",
        "perl",
        "ruby",
        "php",
        "lua",
    }
)
