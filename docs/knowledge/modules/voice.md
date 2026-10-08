---
title: 语音 Provider 与桌宠交互
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - plugins/desktop_pet/background/voice/
  - plugins/desktop_pet/backend/voice_preferences.py
  - plugins/desktop_pet/backend/voice_rpc.py
  - plugins/desktop_pet/ui/VoiceSettings.tsx
  - apps/desktop/src/native/
  - apps/desktop/src/voice/
  - apps/desktop/src/assets/filePickerContract.ts
  - apps/desktop/renderer/src/voice/
  - apps/backend/agent/plugin_host/services.py
  - apps/backend/agent/plugin_host/communication.py
  - packages/sdk/python/shiori_sdk/voice.py
  - packages/sdk/src/contract/native.ts
  - apps/desktop/renderer/src/plugins/PluginRoleUiSlot.tsx
  - plugins/sensevoice_asr/
  - plugins/gpt_sovits_tts/
  - packages/sdk/python/shiori_sdk/files/audio.py
  - packages/sdk/python/shiori_sdk/local_http.py
  - scripts/build-plugin.mjs
  - scripts/plugin-distribution.mjs
  - apps/desktop/scripts/runtime-plugin-modules.mjs
  - apps/desktop/scripts/runtime-pyinstaller.mjs
  - packages/sdk/src/hooks/usePrivateDraft.ts
  - packages/sdk/src/hooks/usePrivateAutosave.ts
  - apps/desktop/scripts/test-sdk-runtime.mjs
  - packages/sdk/python/shiori_sdk/managed/
  - packages/sdk/src/managed/
related:
  - desktop-and-bridge.md
  - roles.md
  - conversations-and-sessions.md
---

# 语音 Provider 与桌宠交互

## 所有权与主链路

桌宠插件拥有语音业务。`background/voice/input.ts` 处理按住说话、按键来源和录音时限；`controller.ts` 协调 ASR、通用聊天与当前轮次；`sentences.ts` 和 `replyAudio.ts` 负责切句、合成与播放队列。插件按当前可见角色绑定输入；关闭语音或未启用 provider 不妨碍显示、拖动和文字气泡。

宿主 `apps/desktop/src/native/` 只负责原生录音、设备枚举、单音频播放停止和全局按键 down/up 注册。隐藏音频 renderer（`renderer/src/voice/`，窗口由 `src/voice/window.ts` 创建）执行采集与播放，其回执经 `src/voice/ipc.ts` 交回录音器与播放器。原生资源绑定真实调用窗口、插件通信上下文和活动实例，停用、换代、窗口重载或退出时释放。surface 使用插件自有消息传递手势，宿主不解释“按住说话”或选择 provider。

录音经选定的 ASR 服务识别，再调用现有 `chat.send` 进入角色 Session 和 Agent Loop。宿主聊天只发布 `chat.delta`、`chat.done`、`chat.error`、`chat.cancelled` 等通用事件；桌宠收到本轮的 `chat.cancelled` 立即结束朗读并让出语音队列，15 秒无增量的空闲超时只作兜底，超时后同一回复的后续句子作为新任务重新排队。桌宠按自己生成的 `turn_id`、实际 `session_key` 及事件中存在的角色标识匹配回复，键盘聊天或其他轮次不能启动本轮朗读。`voice.context.get` 是桌宠自己的 RPC，通过已授予的角色/会话接口读取真实 session 与 mood。

## Provider 调用与存储

通用 `PluginServiceRegistry` 只维护插件明确公开的服务方法和生命周期。provider 通过 SDK `services` 能力注册；消费插件按 contract 动态发现，并使用精确 `{plugin_id, service_id}` 引用调用。通信层验证 owner、generation 和注册实例，不自动启用服务，也不跨 provider fallback。

SDK 的 `shiori.asr.v1` 定义 `transcribe({audio_base64, format}) -> {text}`；`shiori.tts.v1` 定义 `synthesize({text, role_id, mood}) -> {audio_base64, format}`。SDK 不保存音色、参考素材、选型策略或语音状态机。`sensevoice_asr` 发布 `asr/transcribe`，`gpt_sovits_tts` 发布 `tts/synthesize`；两个插件均可独立配置和测试，不依赖桌宠。

SenseVoiceSmall 使用明确的 CPU / `sensevoice` 配置连接本地 FunASR HTTP 服务，设置页支持 WAV 文件转写。GPT-SoVITS 连接本机 `api_v2.py` 服务，当前支持 v2ProPlus；连接检查仅证明 API 可达，不能验证已加载模型或音质。两者只接受 loopback HTTP 地址。用户可明确选择外部服务或插件托管，模式和外部连接设置均由 provider 保存；托管失败不回退到外部地址。插件本身不携带大型环境或模型，固定资源在各插件内单独下载/导入。

GPT-SoVITS 私有 `voices.json` 保存服务设置、默认参考、按角色 mood 映射的参考、语言和语速，`references/` 保存不可变 WAV 副本。每次导入先校验同一份音频字节，再原子写入独立 UUID 文件；同内容的新草稿不会复用旧实例正在回收的身份，旧哈希文件名仍可读取。默认参考须在合成前保存，未映射 mood 使用该角色保存的默认参考。角色编辑器在自管面板里独立保存；试听由 UI 调用同一公共合成服务，只有当前角色/epoch 的结果才交自己的 background 播放。停止不会取消真实推理，迟到结果不得启动播放。

GPT-SoVITS 的实例租约覆盖权重切换、参考文件 pin 和完整 HTTP 响应。连接中断无法确认推理结束时，`inference.json` 保留隔离状态并跨重载拒绝新推理；外部服务须由用户重启后明确确认恢复；托管记录包含所属 generation 和私有 runtime 根身份，只有所属原生进程退出且取得同一服务/推理租约后才能自动恢复，不能因此清除外部标记。正常返回的错误、静音或无效音频也会报错，不自动重试或切换 provider。SDK 3.1.2 提供通用 WAV 校验、暂存文件和 loopback HTTP 工具，业务锁与恢复策略仍属于 provider。

桌宠后端 `VoicePreferencesStore` 自主读写 `plugin-data/desktop_pet/voice-preferences.json`（RPC `voice.preferences.get` / `voice.preferences.set`），保存启用状态、快捷键、麦克风和 ASR/TTS 选择；UI 由桌宠 `VoiceSettings.tsx` 注入，经 `usePrivateAutosave` 自动保存。新语音数据不进入宿主 `[voice]`、`[plugins.desktop_pet]` 或 `roles.json` 的 `runtime_config.tts` / `plugin_data`。provider 的角色声音配置由 provider 自身私有存储管理。

`PluginRoleUiSlot` 承载 `roleUi` 的 `mode: "self-managed"` 面板，提供只读角色上下文、真实 roleId、所属插件的 scoped client 与 `PluginHostServicesProvider`。插件自主读取、保存及报告 dirty；新角色无真实 ID 时不能持久化。该模式不参与宿主角色原子保存，不把跨存储成功或失败包装成单一事务。内置插件目前都不再使用它：GPT-SoVITS 的角色声音自 #720 起改为 `roleSettings`（`storage: "plugin"`、`read: () => ({})`，不进角色草稿）贡献「运行能力」里的「GPT-SoVITS 声音」卡片，编辑器在卡片 ⚙ 对话框内，通过所属插件的文件选择器导入参考音频，角色情绪目录经 `PluginRoleSettingsProps.moodCatalog`（Runtime API 3.1.14）传入。

私有文档的加载、dirty、保存及错误处理复用 SDK hook：两个 provider 的插件设置页与桌宠 `VoiceSettings` 使用 SDK 3.1.4 的 `usePrivateAutosave`（在宿主串行草稿队列上自动保存）；GPT-SoVITS 的角色声音（卡片的 `useRoleVoice`，编辑器 `RoleVoiceEditor`）自 #720 起同样用 `usePrivateAutosave`，关闭卡片对话框（`RoleCapabilityCard.onSettingsOpenChange`，Runtime API 3.1.14）或切换角色时立即提交最后改动，试听在有待保存改动时先提交保存。迟到结果按 scoped client 和文档身份隔离；读取失败不生成可保存的空文档，保存失败保留草稿。具体健康检查、音频测试和持久化 RPC 仍由各插件拥有。

GPT-SoVITS 卡片对话框的参考列表（`ReferenceList`）依次是默认参考、已配置情绪、角色情绪目录中尚未配置音频的情绪；后者为待配置行，点「导入音频」选好文件即建立该情绪参考并立即保存。目录外的情绪输入名称后直接弹出选文件，导入成功才加入，取消或失败不留下空项，因此不再有「已命名未导入」的草稿状态。空白、重复（含待配置的目录情绪）、原型特殊名称和超出 64 个映射的名称被拒绝。各行紧凑显示情绪名、时长、转写摘要及试听、更换、删除，同一时刻只展开一行编辑转写（停顿后自动保存）与参考语言（立即保存）；时长由插件测量，保存时以服务端值为准。删除和保存都只修改 provider 的 `moods`，不写宿主角色。各行试听在有待保存改动时先提交保存、保存完成后合成，保存失败时试听不可用；自动朗读仍按调用者传入的 mood 匹配，未命中使用默认参考。

健康状态的 `instance` 是 `{operation,url,state}` 标记或 `null`，state 为 `in_flight` / `unknown`，不是实例名称字符串。卸载编辑器时试听停止为 best effort，epoch 仍保证迟到合成不播放；仅通信错误中稳定的 `details.reason: context_disposed` 被视为已处置，其他失败通过宿主反馈报告。手动停止失败留在当前编辑器显示。

验证分两层：插件独立测试只依赖 SDK fake 与受控 HTTP；应用级验收在插件页启用两个内置 provider，通过隔离 Electron 生产入口与 Python bridge 测试独立 UI 及桌宠组合链路。后者可以替换原生输入为生成 PCM、替换本机 ASR/LLM/TTS HTTP 服务，但不伪造聊天事件或绕过真实服务调用。两者都不代表真实模型音质、情绪效果或本机性能通过，真实模型验收由 #676 承担。

## 插件托管环境

两个 provider 自己保存资源锁、构建/启动策略和环境状态。SenseVoice 固定独立 CPython、uv 0.12.23、完整离线依赖与 SenseVoiceSmall/fsmn-vad 模型，使用 CPU；GPT-SoVITS 固定官方 Windows 完整包与 7zr，显式验证 v2ProPlus/CUDA。资源默认进入各自 `plugin-data/<id>/runtime/`，用户可在未安装时改到其他目录（状态、锁和日志仍留在插件数据中）；导入包按原路径校验后直接读取，不复制。不进入宿主 `.venv`，不导入彼此或桌宠代码。

SDK 3.1.3 的 `managed/` 只复用固定资源获取、校验、原子版本发布、后台任务和原生进程归属机制。下载以固定大小/SHA-256 校验，断点请求验证 Content-Range；完整离线 ZIP 的所有资源仍逐项校验。准备取消/失败不发布暂存目录，新版本启动失败保留旧指针。私有环境使用紧凑 `s/<id>` / `v/<id>` 布局，版本和资源身份保留在校验记录；受控文件 I/O 支持 Windows 扩展路径，第三方 Python 的运行 prefix 和临时路径保留普通语义。ASR 的固定 uv 使用 offline/no-index/require-hashes 与四个已验证的标准 bdist 目录选项，不修改全局注册表，不把资源移出插件目录。显式 prepare 可以修复损坏的安装记录；start 则明确拒绝损坏记录。准备前按安装根所在卷检查剩余空间（缺失资源字节 + 安装体积 + max(1 GiB, 5%)，原路径导入计 0）；发布成功后删除下载缓存与其他版本目录，失败或取消则保留缓存以便续传。`runtime.remove` 在无任务、无服务运行时后台删除已安装版本、指针、缓存与暂存，锁和日志保留；子进程输出按 UTF-8、否则按 Windows ANSI 代码页增量解码为 UTF-8 日志（SDK 3.1.6）。

启动在普通后台任务中等待同一私有 service 文件租约，不阻塞插件 setup 或同时加载新旧模型。就绪必须同时满足所属子进程存活和健康令牌匹配，模型加载中的进程不可调用。停用、重载、退出先关闭所属原生进程树并等待退出，再释放租约；异常宿主退出由 Windows Job 清理。用户普通停止试听/朗读仍只废弃结果，绝不提前释放正在推理的 GPU 所有权。

通用设置控件 `ManagedRuntimePanel` 轮询所属插件的 `runtime.*` RPC，离开页面不取消准备，取消/停止为显式动作；面板显示安装位置、下载/导入所需空间与可用空间，提供「更改位置」（`host.pickDirectory`，仅未安装时）、「恢复默认」和需二次确认的「删除环境」（SDK 3.1.6/3.1.7）。导入走 `host.pickFilePaths` 按原路径选择，不经宿主暂存复制；宿主文件选择器（暂存复制与按原路径两种）共用 `filePickerContract.ts` 的选择策略：单文件上限 16 GiB、最多 16 个文件及扩展名过滤；暂存复制另按流式大小限制，批次上限 32 GiB。原生进程、文件选择和必要 UI 插槽之外的模型业务均不进入宿主。

## 分发

两个 provider 是内置插件，要求 SDK / Runtime API 3.1.7，manifest 声明 `default_enabled: false`：新配置下默认停用，在插件页启用后出现各自设置页并可供桌宠选择。它们不在默认停用升级迁移名单中，因为此前从未作为内置插件缺省启用。源码参与内置后端发现、前端 builtin registry（`ui/index.tsx`，TTS 另有 `background/index.ts`）和冻结运行时 staging；`runtime_assets/server.py` 与锁文件随插件目录作为数据打包，经 `Path(__file__)` 解析，只在插件托管环境中执行，不作为宿主 hidden import 收集。服务准备见 [ASR README](../../../plugins/sensevoice_asr/README.md) 和 [TTS README](../../../plugins/gpt_sovits_tts/README.md)。

冻结宿主同时递归收集 SDK 运行时模块，包括没有 `__init__.py` 的 `files/`，排除 `shiori_sdk.testing` 与缓存；完整 SDK 不依赖当前已安装插件的静态引用。实际 PyInstaller 参数检查 SDK/宿主/内置插件模块是否全部进入 hidden imports。`test-sdk-runtime.mjs` 使用同一 collector 构建小型冻结探针，在仓库外清除 Python 源码路径后动态导入音频、暂存和 loopback HTTP 模块，并确认 testing 不存在。

## 中断语义

用户手动停止时，桌宠立即停止播放、清空待播句子并废弃当前轮次。录音、ASR、聊天或合成的迟到结果必须经插件自己的 epoch/轮次检查后才能发布；旧结果不得重新播放。聊天取消使用通用 `chat.cancel` 的精确 session/turn 身份。

停止播放不等于底层推理已经停止。provider 自己持有真实推理期间的串行所有权；桌宠只废弃结果，不把取消等待冒充 GPU 推理结束。试听与正常朗读使用 provider 的同一合成入口。

## 兼容性与旧数据

SDK/Runtime API **3.1.1** 移除了 3.1.0 已发布的 `SurfaceHandle.voice`。桌宠要求 3.1.4；宿主的范围检查不会拒绝仍使用该接口的 `>=3.1.0 <4.0.0` 外部包，外部作者须自行迁移并声明 `>=3.1.1 <4.0.0`。迁移说明见 [SDK README](../../../packages/sdk/README.md#compatibility)。

腾讯/MiniMax 实现、宿主语音配置与云音色生命周期已删除。升级不删除既有用户文件、密钥或远端音色；旧配置仅作为普通设置表单不拥有的 opaque 数据保留，不映射为本地参考素材。

## 修改影响

- 输入、朗读与中断：先检查桌宠 `background/voice/` 和 SDK-only 测试，再查原生资源接口的调用者归属与撤销。
- 动态 provider：检查通用 services 注册、通信 owner/generation、明确公开的方法及 provider 自己的协议；不要向宿主增加供应商分支。
- 本地服务：检查 provider HTTP 客户端、实例租约与隔离状态、私有参考文件生命周期及共享 WAV/loopback 工具；协议替身通过不等于真实模型音质通过。
- 内置分发：同时检查后端 discovery、前端 builtin entries 与冻结运行时 staging；托管环境资源须作为数据随包且不进入宿主 hidden imports。
- 设置与角色面板：检查插件私有 RPC/文件、`VoiceSettings`、`PluginRoleUiSlot` 的身份与 dirty 生命周期；不把新数据写回角色草稿。
- 音频与按键：检查 `src/native/`、隐藏音频 renderer、真实 sender 验证及停用/重载清理，保留 WAV 和播放输入校验。
