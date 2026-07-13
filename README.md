# Shiori

Shiori 是一个基于 Akashic Agent 基座演进出来的角色扮演 Agent 助手。当前仓库的主形态已经是 **Windows 桌面端 + Python Agent Runtime**：你可以创建和维护多个角色，让不同角色承接聊天、记忆、主动推送、图片生成和外部渠道绑定。

---

## 当前形态

- **桌面端优先**：Electron 桌面端是当前推荐入口，内置角色管理、聊天、设置、渠道绑定和基础 smoke 验证链路。
- **角色驱动**：角色有独立名称、简介、系统提示词、头像、立绘和角色记忆空间。
- **多渠道接入**：当前保留的外部渠道为 Telegram、QQ。
- **主动能力保留**：支持 proactive 推送与 Drift 空闲任务。
- **Akashic 基座仍在**：Phase、插件、记忆系统、工具编排和旧渠道兼容路径仍然保留。

如果你第一次接触这个仓库，建议直接把它理解成：**一个以角色为核心、桌面端优先的本地 Agent 应用**。

---

## Quickstart

需要：

- Python `3.12+`
- Node.js `20+`
- npm

先安装 Python 依赖：

```bash
git clone <this-repo>
cd Shiori
uv venv
uv pip install -r requirements.txt
```

没有 `uv` 的话先执行：

```bash
pip install uv
```

再安装前端与桌面端依赖：

```bash
npm install
npm --prefix desktop install
```

### 1. 初始化配置与工作区

推荐先跑交互式初始化：

```bash
uv run python main.py setup
```

如果你只想生成默认文件，不走交互向导：

```bash
uv run python main.py init
```

初始化后，默认会准备这些内容：

- `config.toml`
- `~/.shiori/workspace/memory/*`
- `~/.shiori/workspace/roles/roles.json`
- `~/.shiori/workspace/roles/assets`
- `~/.shiori/workspace/proactive_sources.json`
- `~/.shiori/workspace/mcp_servers.json`

### 2. 填写 `config.toml`

`config.example.toml` 已经是当前仓库的最新模板。默认推荐组合仍然是：

- `llm.main` 使用 DeepSeek 主模型
- `llm.fast` 使用轻量模型做改写 / gate / HyDE
- `llm.vl` 单独承接视觉
- `memory.embedding` 提供向量检索

一个最小可用示例：

```toml
[llm]
provider = "deepseek"

[llm.main]
model = "deepseek-v4-flash"
api_key = "sk-..."
base_url = "https://api.deepseek.com/v1"
enable_thinking = true
multimodal = false

[llm.fast]
model = "qwen-flash"
api_key = "sk-..."
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

[llm.vl]
model = "qwen-vl-plus"
api_key = "sk-..."
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

[memory]
enabled = true
engine = ""

[memory.embedding]
model = "text-embedding-v3"
api_key = "sk-..."
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

[channels.telegram]
token = ""
allow_from = ["your_username"]
```

补充说明：

- 至少配置一个可用渠道后，被动消息链路才有实际入口。
- `integrations.novelai` 已经进入当前配置模型。
- 如果你主要体验桌面端，本地聊天与角色编辑本身不依赖 Telegram，但模型配置仍然是必需的。

### 3. 启动桌面端

开发态：

```bash
npm run dev
```

生产构建后启动：

```bash
npm run build
npm run start
```

其中：

- `npm run dev` 会先构建桌面主进程与 preload，再启动 Electron 开发态
- 桌面端会自动拉起 `python main.py bridge`
- `npm run start` 实际对应 `npm run desktop:start`

如果你只想单独启动桌面桥接层：

```bash
uv run python main.py bridge
```

---

## 主要能力

### 角色工作流

- 创建、编辑、删除角色
- 为角色维护系统提示词、头像、立绘和描述
- 为不同聊天渠道绑定默认角色
- 让角色拥有各自隔离的记忆目录

### 桌面端设置面

当前桌面设置页已经覆盖：

- 模型配置：`main` / `fast` / `vl`
- 渠道配置：Telegram、QQ
- Memory 与 Embedding 配置
- Proactive 与 Drift 配置
- NovelAI 集成配置
- 原始插件 / wiring / TOML 片段编辑能力

### Agent Runtime

- 被动回复链路
- 长短期记忆注入与 consolidation
- proactive 主动推送
- drift 空闲任务执行
- 插件扩展与工具拦截

---

## 运行入口

```bash
uv run python main.py               # 启动主 runtime
uv run python main.py setup         # 交互式初始化
uv run python main.py init          # 生成默认配置与工作区
uv run python main.py bridge        # 启动桌面端 bridge
uv run python main.py --help        # 查看全部命令
```

兼容入口说明：

- `uv run python main.py desktop` 仍可用，但已经进入兼容维护模式

---

## 桌面端验证

桌面端相关常用命令：

```bash
npm run lint
npm run typecheck
npm run desktop:typecheck
npm run desktop:smoke
npm run desktop:smoke:all
npm run desktop:smoke:ui
npm run desktop:smoke:restart
```

如果你想直接看更底层的桌面脚本，也可以使用：

```bash
npm --prefix desktop run typecheck
npm --prefix desktop run build
npm --prefix desktop run smoke
npm --prefix desktop run smoke:bridge
npm --prefix desktop run smoke:host
npm --prefix desktop run smoke:desktop
npm --prefix desktop run smoke:desktop-ui
npm --prefix desktop run smoke:restart
```

几个 smoke 的含义：

- `smoke:bridge`：验证 Python bridge 的角色 / 会话生命周期
- `smoke:host`：验证 Electron host 到 bridge 的 RPC 主链
- `smoke:desktop`：验证 renderer -> preload -> host -> bridge 的完整调用链
- `smoke:desktop-ui`：验证 UI 层角色创建、切换、编辑与素材选择
- `smoke:restart`：验证 bridge 重启后的恢复路径

---

## 测试

默认只跑与你当轮修改范围直接相关的测试即可。

常用命令：

```bash
pytest tests/
npm run desktop:typecheck
npm run desktop:smoke
```

如果你需要更大范围验证，再按需补充回归。

---

## 系统全景

```text
桌面端 / 消息渠道
        ↓
   Agent Runtime
        ├── 角色系统
        ├── 记忆系统
        ├── 工具与插件系统
        ├── Proactive 主动推送
        └── Drift 空闲任务
```

保留的 Akashic 核心能力包括：

- 多 Phase 生命周期
- 插件注册与工具拦截
- 语义记忆与 markdown 记忆共存
- 主动轮询与后台任务

---

## 相关文档

| 想看什么 | 文档 |
|---------|------|
| 主动推送与数据源配置 | [docs/_handbook/proactive-guide.md](./docs/_handbook/proactive-guide.md) |
| Drift 空闲任务 | [docs/_handbook/drift-guide.md](./docs/_handbook/drift-guide.md) |
| 记忆文件与流转机制 | [docs/_handbook/memory-markdown.md](./docs/_handbook/memory-markdown.md) |
| 插件生命周期与工具注册 | [docs/_handbook/plugins-tutorial.md](./docs/_handbook/plugins-tutorial.md) |

---

## 工作区

默认运行时工作区位于：

```text
~/.shiori/workspace/
```

其中常见内容包括：

- `memory/`：长期记忆与近期上下文
- `roles/`：角色定义、素材与角色记忆
- `sessions.db`：会话存储
- `proactive_sources.json`：主动推送数据源
- `mcp_servers.json`：MCP 服务定义

