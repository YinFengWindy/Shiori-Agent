# Shiori

Shiori 是一个以角色为核心的本地 Agent 应用，当前以 **Windows 桌面端 + Python Agent Runtime** 为主要形态。

它关注角色如何在长期相处中保持一致：每个角色有自己的设定、素材、会话、记忆和渠道绑定，也可以在合适的时候主动联系你、延续同一个场景，或把对话转化成图片。

## 每个角色都有自己的生活

### 角色彼此独立

你可以创建多个角色，并分别维护名称、简介、系统提示词、头像和立绘。每个角色拥有独立的记忆空间与会话，不会因为切换角色而混淆身份和经历。

角色还可以绑定不同的聊天渠道和允许对象。同一个 Shiori 实例可以让不同角色面向不同联系人，也可以让同一个角色从桌面延伸到 Telegram 或 QQ。

### 对话会留下记忆

Shiori 会把会话、近期上下文和长期记忆分开管理。角色可以在后续对话中重新取回与你有关的信息，而不是只依赖当前窗口里有限的聊天记录。

记忆整理在后台完成，并保存在本地工作区。你可以直接查看和维护这些内容，不需要把角色经历锁在不可见的云端账号里。

### 角色可以主动联系你

主动能力会结合角色关系、距离上次互动的时间和当前场景，决定是否发起新消息或继续刚才的话题。用户回复、场景切换和会话结束都会影响后续主动行为，避免把主动消息退化成固定间隔的提醒。

Drift 则用于角色空闲时的后台活动，让信息搜集、记忆整理或其他可扩展任务不必占用当前对话。

### 对话可以变成画面

接入 NovelAI 后，角色可以手动生成图片，也可以根据最新一轮对话判断是否需要生成场景 CG。场景判断会区分延续、切换与结束，并避免在冷却期或同一回合中重复生成。

图片会作为会话内容保存并同步到桌面端。外部渠道主动推送的图片也会回到同一会话中，不会成为游离在聊天记录之外的附件。

## 可以怎样使用

| 场景 | 体验 |
| --- | --- |
| 桌面陪伴 | 在本地桌面端创建角色、聊天、管理素材与查看历史会话 |
| 长期角色扮演 | 让角色通过独立记忆延续关系、设定和共同经历 |
| 跨渠道联系 | 将角色绑定到 Telegram 或 QQ，在离开电脑后继续收发消息 |
| 主动互动 | 让角色根据关系与场景主动问候、追问或分享内容 |
| 场景视觉化 | 在对话中手动生图，或让 NovelAI 自动生成合适的场景 CG |
| 多角色共存 | 为不同角色配置独立人设、素材、记忆和联系人 |

## 产品能力

### 桌面端

- 角色创建、编辑、删除与切换
- 多会话聊天、历史记录与消息上下文操作
- 头像、立绘、聊天图片与本地素材管理
- 图片生成、提示词标签与图片预览
- 模型、记忆、渠道、主动能力、Drift 与 NovelAI 设置
- 关闭窗口后驻留系统托盘，继续保持已配置渠道在线

### Agent Runtime

- 被动回复与流式输出
- 近期上下文、长期记忆检索与记忆整理
- Proactive 主动推送与同场景后续互动
- Drift 空闲任务
- 工具调用、插件扩展与生命周期拦截
- 桌面端、Telegram 与 QQ 的统一会话同步

### 角色与渠道

- 每个角色独立保存人设、素材、记忆与会话
- 按角色配置渠道账号、允许对象和默认路由
- 桌面端与外部渠道共享角色状态和消息记录
- 外部推送的文本、图片和媒体元数据同步回桌面会话

## 当前边界

- 桌面端目前优先支持 Windows。
- 模型请求会发送到你配置的模型服务；角色、会话和记忆默认保存在本地。
- Telegram 和 QQ 是当前保留的外部消息渠道，需要分别提供可用凭据。
- 自动 CG 与图片生成需要额外配置 NovelAI。
- `fast`、视觉和 Embedding 模型不是启动桌面端的硬性条件，但会影响改写、视觉理解和语义记忆能力。

## Shiori 如何工作

```text
Windows 桌面端 ─┐
Telegram / QQ ──┼── Agent Runtime
                 │      ├── 角色与关系
                 │      ├── 会话与记忆
                 │      ├── 工具与插件
                 │      ├── Proactive / Drift
                 │      └── 图片生成
                 └── 本地工作区
```

Electron 桌面端负责交互与本地资源访问，Python Runtime 负责角色推理、记忆、工具、主动任务和渠道连接。桌面桥接层连接两者，并在 Runtime 重启后恢复角色与会话状态。

## 安装与启动

### 环境要求

- Windows
- Python `3.12+`
- Node.js `20+`
- npm
- [uv](https://docs.astral.sh/uv/)

### 1. 安装依赖

```bash
git clone https://github.com/YinFengWindy/Shiori-Agent.git
cd Shiori-Agent
uv venv
uv pip install -r requirements.txt
npm install
npm --prefix desktop install
```

如果尚未安装 `uv`：

```bash
pip install uv
```

### 2. 初始化配置

推荐使用交互式向导创建配置与本地工作区：

```bash
uv run python main.py setup
```

也可以只生成默认文件，再手动编辑 `config.toml`：

```bash
uv run python main.py init
```

至少需要配置一个可用的主模型。其他能力可以按需启用：

| 配置 | 用途 | 是否必需 |
| --- | --- | --- |
| `llm.main` | 角色主要推理与回复 | 是 |
| `llm.fast` | 改写、门控和轻量判断 | 推荐 |
| `llm.vl` | 图片理解 | 可选 |
| `memory.embedding` | 语义记忆检索 | 推荐 |
| `channels.telegram` / `channels.qq` | 外部消息渠道 | 可选 |
| `integrations.novelai` | 图片生成与自动 CG | 可选 |

`config.example.toml` 提供了完整配置结构。Shiori 使用 OpenAI 兼容接口，可为不同能力分别设置模型、API Key 和 Base URL。

### 3. 启动桌面端

开发模式：

```bash
npm run dev
```

生产构建：

```bash
npm run build
npm run start
```

桌面端会自动启动 Python bridge。关闭主窗口后，应用会进入系统托盘；如果已配置外部渠道，角色仍可继续收发消息。

## 开发者入口

### 常用命令

```bash
uv run python main.py                    # 启动完整 Runtime
uv run python main.py bridge             # 只启动桌面桥接层
uv run python main.py --inspect-modules  # 检查模块装配
uv run python main.py --help             # 查看命令行帮助

pytest tests/                            # Python 测试
npm test                                # 桌面端单元测试
npm run lint                            # ESLint
npm run typecheck                       # TypeScript 类型检查
npm run desktop:smoke                   # 桌面主链 smoke
```

默认只需运行与当前改动范围直接相关的测试；改动影响多个边界时，再补充更大范围回归。

### 主要目录

| 目录 | 职责 |
| --- | --- |
| `desktop/` | Electron 主进程、preload 与 React 渲染端 |
| `desktop_bridge/` | 桌面端与 Python Runtime 的 RPC 边界 |
| `agent/` | 回合编排、推理循环与工具执行 |
| `core/roles/` | 角色、关系状态与角色服务 |
| `session/` | 会话、消息、在线状态与搜索 |
| `memory2/`、`core/memory/` | 语义记忆与 Markdown 记忆 |
| `proactive_v2/` | 主动任务调度与执行 |
| `plugins/` | NovelAI、渠道与其他可扩展能力 |
| `bootstrap/` | Runtime 依赖装配与启动配置 |

### 本地数据

默认工作区位于：

```text
~/.shiori/workspace/
```

其中包含：

- `roles/`：角色定义、素材与角色记忆
- `memory/`：长期记忆与近期上下文
- `sessions.db`：会话与消息
- `proactive_sources.json`：主动推送数据源
- `mcp_servers.json`：MCP 服务定义

修改或删除工作区内容前，建议先退出桌面端并备份对应文件。

## License

[MIT](./LICENSE)
