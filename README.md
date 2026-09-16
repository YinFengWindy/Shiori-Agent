<div align="center">
  <img src="./assets/shiori-app-icon.png" alt="Shiori icon" width="96" />
  <h1>Shiori</h1>
  <p><strong>让角色拥有自己的生活</strong></p>
  <p>本地优先的 AI 角色扮演助手。角色有自己的人设和记忆，<br />在桌面、Telegram 和 QQ 上都是同一个人。</p>
  <p>
    <a href="https://github.com/YinFengWindy/Shiori-Agent/releases/latest"><strong>下载 Windows 版</strong></a>
    ·
    <a href="https://github.com/YinFengWindy/Shiori-Agent/releases">历史版本</a>
    ·
    <a href="https://github.com/YinFengWindy/Shiori-Agent/issues">反馈问题</a>
    ·
    <a href="https://github.com/YinFengWindy/Shiori-Agent">源码</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/platform-Windows%20x64-2563eb?style=flat-square" alt="Windows x64" />
    <img src="https://img.shields.io/badge/version-v0.2.0-7c3aed?style=flat-square" alt="v0.2.0" />
    <img src="https://img.shields.io/badge/license-MIT-16a34a?style=flat-square" alt="MIT license" />
  </p>
</div>

## 关于 Shiori

角色不只是一段提示词。Shiori 把角色需要的东西分开存放：人设、记忆、会话、素材和关系各自独立，换一个会话、换一个聊天渠道，角色还是同一个角色。

你可以建任意多个角色，每个角色有自己的性格、经历和相处方式。聊过的内容会沉淀成记忆，角色会在合适的时候主动发消息，也可以接你派的任务，或者陪你走完一段故事模式的剧情。

## 界面

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

## 功能

### 角色与对话

- 创建、编辑、删除和切换角色；头像、立绘、聊天图片和本地素材都按角色分开管理
- 每个角色可以开多个会话，历史记录完整保留，回复流式输出
- 近期上下文和长期记忆分两层管理，需要时检索并定期整理
- 角色会根据关系、场景和上次互动判断要不要主动开口，而不是按固定间隔提醒你
- 空闲时可以跑 Drift 任务
- 支持工具调用、插件扩展和生命周期拦截

### 故事模式

- 每段故事是一次独立的经历，带角色快照、背景、剧情记录和场景状态
- 剧情推进和自由对话可以随时切换，也能暂停、恢复、保存，或者从某个节点开一条分支
- 重要节点可以挂上 CG、语音和其他演出资源

### 桌宠

- 每个角色可以单独启用桌宠，绑定自己的素材包
- 素材包用 `codex-sprite@1` 格式，支持 ZIP 导入、安全校验和动作映射
- 透明窗口原生拖拽，记住上次的位置，托盘常驻；拖动时按方向播动作，停下来回到 idle
- 授权之后可以开启屏幕观察，角色会读屏幕内容并在桌宠旁边弹气泡回你

### 图片生成

- 接入 NovelAI 生成图片，可以用提示词标签控制，生成后直接预览
- 合适的对话回合会自动出场景 CG

### 多端接入

- 桌面端、Telegram 和 QQ 共用同一份角色状态和会话记录

## 开始使用

1. 打开 [最新 Release](https://github.com/YinFengWindy/Shiori-Agent/releases/latest)，下载 Windows x64 安装程序装上。
2. 第一次启动后，在设置里填上模型服务的 API Key。
3. 创建一个角色，给它选好模型，就可以开始聊了。

需要另外配置的服务：

| 服务 | 用来做什么 | 必需 |
| --- | --- | --- |
| 模型服务 | 角色回复和 Agent 运行 | 是 |
| Embedding 服务 | 语义记忆检索 | 想用长期记忆时要配 |
| Telegram / QQ | 从外部聊天软件找角色 | 否 |
| NovelAI | 图片生成和自动场景 CG | 否 |
| ASR / TTS 服务 | 桌宠语音交互 | 否 |

## 开发

环境要求：Windows x64、Node.js 22+、pnpm 10.33.0、Python 3.12+。

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r apps/backend/requirements/production.txt -r apps/backend/requirements/development.txt
pnpm install
pnpm dev
```

开发模式下的 Python bridge 用的是项目 `.venv` 里的解释器，不走系统 PATH。常用检查：

```powershell
pnpm test
pnpm lint
pnpm typecheck
pnpm build
.venv\Scripts\pytest.exe -q tests\
```

局部桌面验证可以按仓库相对路径片段筛选文件，再按测试名称正则筛选用例。重复 `--file` 会合并匹配文件；不传参数仍运行宿主与插件全部单测。`--list` 只列出匹配文件，不执行测试。

```powershell
pnpm test --file RoleDetailPage.test.tsx
pnpm test --file plugins/desktop_pet/surface/ --test-name-pattern "reply bubbles"
pnpm test --file roles/ --file plugins/story/ui/ --list
```

运行结构：

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

## 数据存在哪里

- 角色、会话和记忆默认存在本地：`%USERPROFILE%\.shiori\workspace\`。
- 模型请求会发给你自己配置的模型服务。开了 NovelAI、Telegram、QQ 或语音之后，相应的内容也会发到这些服务。
- 外部渠道、NovelAI、语音和桌宠素材都要单独配置；不配也不影响桌面端本地功能的使用。
- 要改或者删工作区里的文件，先退出 Shiori，动手之前先备份。

## License

[MIT](./LICENSE)
