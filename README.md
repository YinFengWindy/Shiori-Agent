<div align="center">
  <img src="./assets/shiori-app-icon.png" alt="Shiori icon" width="96" />
  <h1>Shiori</h1>
  <p><strong>让角色拥有自己的生活</strong></p>
  <p>一个本地优先的 AI 角色生活空间。创建角色、延续记忆，<br />让 TA 在桌面和日常对话里继续陪伴你。</p>
  <p>
    <a href="https://github.com/YinFengWindy/Shiori-Agent/releases/latest"><strong>下载 Windows 版</strong></a>
    ·
    <a href="https://github.com/YinFengWindy/Shiori-Agent/releases">查看全部版本</a>
    ·
    <a href="https://github.com/YinFengWindy/Shiori-Agent/issues">反馈问题</a>
    ·
    <a href="https://github.com/YinFengWindy/Shiori-Agent">查看源码</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/platform-Windows%20x64-2563eb?style=flat-square" alt="Windows x64" />
    <img src="https://img.shields.io/badge/version-v0.1.0-7c3aed?style=flat-square" alt="v0.1.0" />
    <img src="https://img.shields.io/badge/license-MIT-16a34a?style=flat-square" alt="MIT license" />
  </p>
</div>

## 这不只是一次聊天

Shiori 不把角色锁在一段提示词里，而是给 TA 一套可以持续生活的空间：人设、记忆、会话、素材和关系彼此独立，并在桌面、渠道之间延续。

你可以创建多个角色，让每个角色拥有不同的性格、经历和相处方式。对话会留下记忆，角色可以在合适的时候主动联系你，你也可以给他们安排任务。

## 角色会记得，也会继续生活

| 体验 | Shiori 如何实现 |
| --- | --- |
| **每个角色都有自己的身份** | 独立的人设、头像、立绘、素材、会话和记忆，不会因为切换角色而混淆经历。 |
| **关系不会停在当前窗口** | 分开管理近期上下文与长期记忆，让角色在后续对话中重新取回共同经历。 |
| **角色可以主动联系你** | 根据关系、场景和上次互动决定是否发起消息，而不是简单地按固定间隔提醒。 |
| **桌面上也有 TA 的位置** | 透明桌宠窗口支持拖拽、位置记忆、动作播放和系统托盘常驻。 |
| **对话可以变成画面** | 接入 NovelAI，让合适的对话回合自然产生CG。 |
| **关系可以进入故事** | 将角色放进可暂停、可恢复、可分支的视觉小说式经历，保存剧情、场景和 CG。 |
| **一个角色，多个入口** | 桌面端、Telegram 和 QQ 可以共享角色状态与会话记录。 |

## 先看看 Shiori

<table>
  <tr>
    <th>和角色聊天</th>
    <th>编辑角色资料与设定</th>
  </tr>
  <tr>
    <td><img src="./assets/readme/chat.png" alt="Chat with a role" width="100%" /></td>
    <td><img src="./assets/readme/role-settings.png" alt="Role settings" width="100%" /></td>
  </tr>
</table>

<table>
  <tr>
    <th>故事入口</th>
    <th>故事化场景</th>
  </tr>
  <tr>
    <td><img src="./assets/readme/story-menu.png" alt="Story menu" width="100%" /></td>
    <td><img src="./assets/readme/story-scene.png" alt="Story scene" width="100%" /></td>
  </tr>
</table>



## 产品能力

### 桌面端

- 创建、编辑、删除和切换角色
- 多会话聊天、历史记录
- 头像、立绘、聊天图片和本地素材管理
- 图片生成、提示词标签和图片预览
- 模型、记忆、渠道、主动能力、Drift 和 NovelAI 设置
- 沉浸式视觉小说模式

### Agent Runtime

- 被动回复与流式输出
- 近期上下文、长期记忆检索与记忆整理
- Proactive 主动推送与同场景后续互动
- Drift 空闲任务
- 工具调用、插件扩展与生命周期拦截
- 桌面端、Telegram 与 QQ 的统一会话同步

### 故事模式

- 创建独立的故事经历，使用角色快照、背景、剧情记录和场景状态
- 支持剧情推进、自由对话、暂停、恢复、保存和分支
- 重要剧情节点可以关联 CG、语音和其他演出资源

### 桌宠

- 每个角色可以独立启用桌宠并绑定自己的素材包
- 桌宠为codex桌宠格式，支持 ZIP 导入、安全校验、动作映射、原生拖拽和位置持久化
- 桌宠可根据移动方向播放动作，停止后恢复 idle
- 在明确授权后，观察伴侣可以把屏幕观察结果交给角色，并在桌宠附近展示回复气泡

## 3 分钟开始

### 直接体验

1. 打开 [最新 Release](https://github.com/YinFengWindy/Shiori-Agent/releases/latest)。
2. 下载 Windows x64 安装程序并完成安装。
3. 首次启动后，在设置界面中注册API KEY，并创建自己的角色，为其绑定对应的LLM。

### 可选连接

| 服务 | 用途 | 是否必需 |
| --- | --- | --- |
| 模型服务 | 角色回复与 Agent 运行 | 必需 |
| Embedding 服务 | 语义记忆检索 | 需要长期记忆时配置 |
| Telegram / QQ | 从外部聊天渠道联系角色 | 可选 |
| NovelAI | 图片生成与自动场景 CG | 可选 |
| ASR / TTS 服务 | 桌宠语音交互 | 可选 |

## 开发者

### 环境

- Windows x64
- Node.js 22+
- pnpm 10.33.0
- Python 3.12+

### 本地运行

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r apps/backend/requirements/production.txt -r apps/backend/requirements/development.txt
pnpm install
pnpm dev
```

开发环境中的 Python bridge 会使用项目 `.venv` 内的解释器。常用检查命令：

```powershell
pnpm test
pnpm lint
pnpm typecheck
pnpm build
.venv\Scripts\pytest.exe -q tests\
```

### 运行结构

```text
桌面端 / Telegram / QQ
            │
            ▼
      Agent Runtime
       ├── 角色与关系
       ├── 会话与记忆
       ├── 工具与插件
       ├── Proactive / Drift
       └── 图片与语音能力
            │
            ▼
       本地工作区
```

## 本地数据与当前边界

- 角色、会话和记忆默认保存在本地工作区：`%USERPROFILE%\.shiori\workspace\`。
- 模型请求会发送到你配置的模型服务；启用 NovelAI、Telegram、QQ 或语音服务后，相应内容也会发送到对应服务。
- 外部渠道、NovelAI、语音和桌宠素材都需要单独配置；没有有效配置时，桌面端仍可只使用已启用的本地能力。
- 修改或删除工作区内容前，请先退出 Shiori 并备份对应文件。

## License

[MIT](./LICENSE)
