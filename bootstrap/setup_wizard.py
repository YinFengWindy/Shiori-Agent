"""
交互式初始化向导

python main.py setup
"""
from __future__ import annotations

import sys
import select
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import click
from plugins.default_memory.config import render_default_memory_config


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class WizardAnswers:
    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    enable_thinking: bool = False
    multimodal: bool = False
    vl_model: str = ""
    vl_api_key: str = ""
    vl_base_url: str = ""
    fast_model: str = ""
    fast_api_key: str = ""
    fast_base_url: str = ""
    tg_token: str = ""
    embed_model: str = ""
    embed_api_key: str = ""
    embed_base_url: str = ""


# ---------------------------------------------------------------------------
# 输出工具
# ---------------------------------------------------------------------------

def _hint(text: str) -> None:
    click.echo(click.style(f"  {text}", dim=True))


def _ok(text: str) -> None:
    click.echo(click.style(f"  ✓ {text}", fg="green"))


def _warn(text: str) -> None:
    click.echo(click.style(f"  ! {text}", fg="yellow"))


def _err(text: str) -> None:
    click.echo(click.style(f"  ✗ {text}", fg="red"))


def _section_header(step: str, title: str) -> None:
    click.echo(f"\n{click.style(f'[{step}]', bold=True)} {title}\n")


def _divider() -> None:
    click.echo(click.style("─" * 40, dim=True))


def _read_escape_sequence(fd: int) -> str:
    ready, _, _ = select.select([fd], [], [], 0.01)
    if not ready:
        return ""

    first = sys.stdin.read(1)
    if first == "[":
        seq = [first]
        while len(seq) < 5:
            ready, _, _ = select.select([fd], [], [], 0.01)
            if not ready:
                break
            ch = sys.stdin.read(1)
            seq.append(ch)
            if ch == "~" or ch.isalpha():
                break
        return "".join(seq)

    if first == "O":
        ready, _, _ = select.select([fd], [], [], 0.01)
        if ready:
            return first + sys.stdin.read(1)
    return first


def _secret_prompt(
    text: str,
    *,
    default: str | None = None,
    show_default: bool = True,
) -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if default is None:
            return _strip_paste_markers(click.prompt(text, hide_input=True))
        return _strip_paste_markers(
            click.prompt(
                text,
                default=default,
                hide_input=True,
                show_default=show_default,
            )
        )

    try:
        import termios
        import tty
    except Exception:
        if default is None:
            return _strip_paste_markers(click.prompt(text, hide_input=True))
        return _strip_paste_markers(
            click.prompt(
                text,
                default=default,
                hide_input=True,
                show_default=show_default,
            )
        )

    suffix = ""
    if show_default and default not in (None, ""):
        suffix = f" [{default}]"
    click.echo(f"{text}{suffix}: ", nl=False)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars: list[str] = []
    try:
        _ = tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = _read_escape_sequence(fd)
                if seq in ("[200~", "[201~"):
                    continue
                if seq.startswith("[") or seq.startswith("O"):
                    continue
                chars.extend(["\x1b", *seq])
                click.echo("*" * (len(seq) + 1), nl=False)
                continue
            if ch in ("\r", "\n"):
                click.echo()
                break
            if ch == "\x03":
                raise KeyboardInterrupt()
            if ch == "\x04":
                raise EOFError()
            if ch in ("\x7f", "\b"):
                if chars:
                    _ = chars.pop()
                    click.echo("\b \b", nl=False)
                continue
            if ch < " ":
                continue
            chars.append(ch)
            click.echo("*", nl=False)
    finally:
        _ = termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    value = "".join(chars)
    if value or default is None:
        return _strip_paste_markers(value)
    return default


def _strip_paste_markers(value: str) -> str:
    return value.replace("\x1b[200~", "").replace("\x1b[201~", "")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run_setup_wizard(config_path: Path, workspace: Path) -> None:
    click.echo(click.style("\n══ akashic 初始化向导 ══\n", bold=True))
    _hint("全程按回车使用括号内的默认值")
    _hint("API key / token 输入时会显示为 *，正常输入后回车即可")

    if config_path.exists():
        click.echo(f"\n已存在配置文件 {config_path}")
        if not click.confirm("覆盖并重新配置？", default=False):
            click.echo("已取消。")
            return

    answers = _collect_answers()

    _divider()
    click.echo("\n正在生成配置并初始化工作区...")

    toml_str = _render_config(answers)
    _ = config_path.write_text(toml_str, encoding="utf-8")
    _ok(f"{config_path} 已生成")
    memory_config_path = _default_memory_local_config_path()
    memory_config_path.parent.mkdir(parents=True, exist_ok=True)
    _ = memory_config_path.write_text(
        _render_default_memory_config(),
        encoding="utf-8",
    )
    _ok(f"{memory_config_path} 已生成")

    _validate_config(config_path)

    from bootstrap.init_workspace import init_workspace
    _ = init_workspace(config_path=config_path, workspace=workspace)
    _ok(f"{workspace} 已初始化")

    _print_completion(answers)


# ---------------------------------------------------------------------------
# 各阶段问答
# ---------------------------------------------------------------------------

def _collect_answers() -> WizardAnswers:
    a = WizardAnswers()
    _phase_main_llm(a)
    _phase_fast_model(a)
    _phase_telegram(a)
    _phase_memory(a)
    return a


def _phase_main_llm(a: WizardAnswers) -> None:
    _section_header("1/4", "主模型")

    a.model = click.prompt("模型名")
    a.base_url = click.prompt("base_url（OpenAI 兼容格式）")
    a.api_key = _secret_prompt("API key")
    a.provider = "openai"
    a.enable_thinking = click.confirm("开启 thinking 模式？", default=False)
    a.multimodal = click.confirm("主模型原生支持图片输入？", default=False)

    if not a.multimodal:
        if click.confirm("配置独立视觉模型？", default=False):
            a.vl_model = click.prompt("视觉模型名")
            a.vl_base_url = click.prompt(
                "base_url（回车 = 复用主模型 base_url）",
                default="",
                show_default=False,
            ) or a.base_url
            a.vl_api_key = _secret_prompt(
                "API key（回车 = 复用主模型 key）",
                default="",
                show_default=False,
            ) or a.api_key


def _phase_fast_model(a: WizardAnswers) -> None:
    _section_header("2/4", "轻量模型（可跳过）")
    _hint("用于 memory gate / HyDE 等低延迟场景，跳过则退回主模型")

    if not click.confirm("配置独立轻量模型？", default=False):
        return

    a.fast_model = click.prompt("模型名")
    a.fast_base_url = click.prompt(
        "base_url（回车 = 复用主模型 base_url）",
        default="",
        show_default=False,
    ) or a.base_url
    a.fast_api_key = _secret_prompt(
        "API key（回车 = 复用主模型 key）",
        default="",
        show_default=False,
    ) or a.api_key


def _phase_telegram(a: WizardAnswers) -> None:
    _section_header("3/4", "Telegram 频道")

    if not click.confirm("配置 Telegram 频道？", default=True):
        _hint("跳过后不配置 Telegram 渠道")
        return

    # BotFather 引导
    click.echo()
    click.echo(click.style("  还没有 Telegram bot？按以下步骤创建：", dim=True))
    _hint("1. 打开 Telegram，搜索 @BotFather")
    _hint("2. 发送 /newbot，按提示给 bot 起名")
    _hint("3. BotFather 会回复一串 token，格式：123456789:AAFxxx...")
    click.echo()

    while True:
        token = _secret_prompt("Bot token")
        err = _validate_tg_token(token)
        if err is None:
            a.tg_token = token
            break
        _err(f"{err}，请重新输入")

def _phase_memory(a: WizardAnswers) -> None:
    _section_header("4/4", "语义记忆（Embedding）")
    _hint("agent 用 embedding 模型将记忆转为向量，实现语义检索")
    click.echo()

    a.embed_model = click.prompt("Embedding 模型名")
    a.embed_api_key = _secret_prompt("Embedding API key")
    a.embed_base_url = click.prompt("Embedding base_url")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _validate_tg_token(token: str) -> str | None:
    try:
        import httpx
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
        data = resp.json()
        if data.get("ok"):
            bot_name = data["result"].get("username", "")
            _ok(f"bot 验证成功：@{bot_name}")
            return None
        if resp.status_code == 409:
            return "bot 已绑定 webhook，请先调用 deleteWebhook 删除"
        return f"token 无效（{data.get('description', resp.status_code)}）"
    except Exception as e:
        return f"网络错误：{e}"


def _fetch_chat_id_with_spinner(token: str, username: str, timeout_s: int = 60) -> str | None:
    result: list[str | None] = [None]
    done = threading.Event()

    def _poll() -> None:
        result[0] = _fetch_chat_id(token, username, timeout_s, done)
        done.set()

    thread = threading.Thread(target=_poll, daemon=True)
    thread.start()

    # 主线程显示等待动画
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    while not done.wait(timeout=0.1):
        frame = click.style(frames[i % len(frames)], fg="cyan")
        click.echo(f"\r  {frame} 等待消息中...", nl=False)
        i += 1
    click.echo("\r" + " " * 30 + "\r", nl=False)  # 清除等待行

    thread.join()
    return result[0]


def _fetch_chat_id(token: str, username: str, timeout_s: int, stop: threading.Event | None = None) -> str | None:
    try:
        import httpx
        url = f"https://api.telegram.org/bot{token}/getUpdates"

        # 1. 清掉历史 update
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params={"offset": -1, "limit": 1})
            last = resp.json().get("result", [])
            offset = (last[-1]["update_id"] + 1) if last else 0

        # 2. 轮询
        deadline = time.time() + timeout_s
        with httpx.Client(timeout=12) as client:
            while time.time() < deadline:
                if stop and stop.is_set():
                    break
                resp = client.get(url, params={"offset": offset, "timeout": 10})
                for update in resp.json().get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message") or update.get("channel_post")
                    if not msg:
                        continue
                    from_user = msg.get("from", {})
                    if from_user.get("username", "").lower() == username.lower():
                        chat_id = str(msg["chat"]["id"])
                        try:
                            _ = client.get(
                                url,
                                params={"offset": offset, "limit": 1, "timeout": 0},
                            )
                        except Exception as e:
                            _warn(f"chat_id 已获取，但确认 Telegram update 失败：{e}")
                        return chat_id
    except Exception as e:
        _err(f"获取 chat_id 失败：{e}")
    return None
# ---------------------------------------------------------------------------
# Config 验证
# ---------------------------------------------------------------------------

def _validate_config(config_path: Path) -> None:
    try:
        from agent.config import Config
        _ = Config.load(config_path)
        _ok("配置验证通过")
    except KeyError as e:
        _err(f"配置缺少必填字段：{e}")
        raise SystemExit(1)
    except Exception as e:
        _err(f"配置加载失败：{e}")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# TOML 渲染
# ---------------------------------------------------------------------------

def _render_config(a: WizardAnswers) -> str:
    return "\n".join([
        _render_llm(a),
        _render_agent(),
        _render_channels(a),
        _render_memory(a),
        _render_integrations(),
    ])


def _render_llm(a: WizardAnswers) -> str:
    lines: list[str] = [
        "[llm]",
        f'provider = "{a.provider}"',
        "",
        "[llm.main]",
        f'model = "{a.model}"',
        f'api_key = "{a.api_key}"',
        f'base_url = "{a.base_url}"',
    ]
    if a.enable_thinking:
        lines.append("enable_thinking = true")
    lines.append(f"multimodal = {'true' if a.multimodal else 'false'}")
    lines.append("")

    if a.fast_model:
        lines += [
            "[llm.fast]",
            f'model = "{a.fast_model}"',
            f'api_key = "{a.fast_api_key}"',
            f'base_url = "{a.fast_base_url}"',
            "",
        ]
    else:
        lines += [
            "# 轻量模型未配置，memory gate / HyDE 将使用主模型",
            "# [llm.fast]",
            "# model = \"\"",
            "",
        ]

    if a.vl_model:
        lines += [
            "[llm.vl]",
            f'model = "{a.vl_model}"',
            f'api_key = "{a.vl_api_key}"',
            f'base_url = "{a.vl_base_url}"',
            "",
        ]
    else:
        lines += [
            "# 视觉模型未配置",
            "# [llm.vl]",
            "# model = \"\"",
            "",
        ]

    return "\n".join(lines)


def _render_agent() -> str:
    return """\
[agent]
system_prompt = "You are a helpful AI assistant with access to tools. Always respond in the same language the user uses."
max_tokens = 8192
# 设为 0 表示不限制迭代轮数；长任务仍可用 /stop 中断。
max_iterations = 40
dev_mode = false

[agent.context]
memory_window = 40

[agent.tools]
search_enabled = true
"""


def _render_channels(a: WizardAnswers) -> str:
    lines: list[str] = []

    if a.tg_token:
        lines += [
            "[channels.telegram]",
            f'token = "{a.tg_token}"',
            "",
        ]
    else:
        lines += [
            "# [channels.telegram]",
            '# token = ""',
            "",
        ]

    lines += [
        "# QQ 频道（NapCat，如需启用，填写后取消注释）",
        "# [channels.qq]",
        '# bot_uin = ""',
        "",
        "# 官方 QQBot（QQ 开放平台，如需启用，填写后取消注释）",
        "# [plugins.qqbot]",
        '# app_id = ""',
        '# client_secret = ""',
        "",
    ]

    return "\n".join(lines)


def _render_memory(a: WizardAnswers) -> str:
    return "\n".join([
        "[memory]",
        "enabled = true",
        'engine = ""',
        "",
        "[memory.embedding]",
        f'model = "{a.embed_model}"',
        f'api_key = "{a.embed_api_key}"',
        f'base_url = "{a.embed_base_url}"',
        "",
    ])


def _render_default_memory_config() -> str:
    return render_default_memory_config()


def _default_memory_local_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "plugins" / "default_memory" / "config.local.toml"


def _render_integrations() -> str:
    return ""


# ---------------------------------------------------------------------------
# 完成提示
# ---------------------------------------------------------------------------

def _print_completion(a: WizardAnswers) -> None:
    click.echo(click.style("\n══ 配置完成 ══\n", bold=True))
    click.echo("启动 agent：")
    click.echo(click.style("  uv run python main.py", bold=True))

    click.echo()
    _hint("主动推送请在桌面端角色详情中绑定渠道并配置角色策略")
