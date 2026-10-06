---
title: 语音 Provider 与桌宠交互
kind: 领域说明
status: 当前有效
last_verified_commit: b42c7d18
source_paths:
  - plugins/desktop_pet/background/voice/
  - plugins/desktop_pet/backend/voice_preferences.py
  - plugins/desktop_pet/backend/voice_rpc.py
  - plugins/desktop_pet/ui/VoiceSettings.tsx
  - apps/desktop/src/native/
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
related:
  - desktop-and-bridge.md
  - roles.md
  - conversations-and-sessions.md
---

# 语音 Provider 与桌宠交互

## 所有权与主链路

桌宠插件拥有语音业务。`background/voice/input.ts` 处理按住说话、按键来源和录音时限；`controller.ts` 协调 ASR、通用聊天与当前轮次；`sentences.ts` 和 `replyAudio.ts` 负责切句、合成与播放队列。插件按当前可见角色绑定输入；关闭语音或未安装 provider 不妨碍显示、拖动和文字气泡。

宿主 `apps/desktop/src/native/` 只负责原生录音、设备枚举、单音频播放停止和全局按键 down/up 注册。隐藏音频 renderer 执行采集与播放。原生资源绑定真实调用窗口、插件通信上下文和活动实例，停用、换代、窗口重载或退出时释放。surface 使用插件自有消息传递手势，宿主不解释“按住说话”或选择 provider。

录音经选定的 ASR 服务识别，再调用现有 `chat.send` 进入角色 Session 和 Agent Loop。宿主聊天只发布 `chat.delta`、`chat.done`、`chat.error` 等通用事件。桌宠按自己生成的 `turn_id`、实际 `session_key` 及事件中存在的角色标识匹配回复，键盘聊天或其他轮次不能启动本轮朗读。`voice.context.get` 是桌宠自己的 RPC，通过已授予的角色/会话接口读取真实 session 与 mood。

## Provider 调用与存储

通用 `PluginServiceRegistry` 只维护插件明确公开的服务方法和生命周期。provider 通过 SDK `services` 能力注册；消费插件按 contract 动态发现，并使用精确 `{plugin_id, service_id}` 引用调用。通信层验证 owner、generation 和注册实例，不自动启用服务，也不跨 provider fallback。

SDK 的 `shiori.asr.v1` 定义 `transcribe({audio_base64, format}) -> {text}`；`shiori.tts.v1` 定义 `synthesize({text, role_id, mood}) -> {audio_base64, format}`。SDK 不保存音色、参考素材、选型策略或语音状态机。`sensevoice_asr` 发布 `asr/transcribe`，`gpt_sovits_tts` 发布 `tts/synthesize`；两个插件均可独立安装、配置和测试，不依赖桌宠。

SenseVoiceSmall 使用明确的 CPU / `sensevoice` 配置连接本地 FunASR HTTP 服务，设置页支持 WAV 文件转写。GPT-SoVITS 连接本机 `api_v2.py` 服务，当前支持 v2ProPlus；连接检查仅证明 API 可达，不能验证已加载模型或音质。两者只接受 loopback HTTP 地址，不携带推理环境、模型或大型依赖。环境托管和真实声学验收另行实施。

GPT-SoVITS 私有 `voices.json` 保存服务设置、默认参考、按角色 mood 映射的参考、语言和语速，`references/` 保存不可变 WAV 副本。每次导入先校验同一份音频字节，再原子写入独立 UUID 文件；同内容的新草稿不会复用旧实例正在回收的身份，旧哈希文件名仍可读取。默认参考须在合成前保存，未映射 mood 使用该角色保存的默认参考。角色编辑器在自管面板里独立保存；试听由 UI 调用同一公共合成服务，只有当前角色/epoch 的结果才交自己的 background 播放。停止不会取消真实推理，迟到结果不得启动播放。

GPT-SoVITS 的实例租约覆盖权重切换、参考文件 pin 和完整 HTTP 响应。连接中断无法确认推理结束时，`inference.json` 保留隔离状态并跨重载拒绝新推理；用户必须先重启外部服务，再在设置中明确确认恢复。正常返回的错误、静音或无效音频也会报错，不自动重试或切换 provider。SDK 4.1 提供通用 WAV 校验、暂存文件和 loopback HTTP 工具，业务锁与恢复策略仍属于 provider。

桌宠后端 `VoicePreferencesStore` 自主读写 `plugin-data/desktop_pet/voice-preferences.json`，保存启用状态、快捷键、麦克风和 ASR/TTS 选择；UI 由桌宠 `VoiceSettings.tsx` 注入。新语音数据不进入宿主 `[voice]`、`[plugins.desktop_pet]` 或 `roles.json` 的 `runtime_config.tts` / `plugin_data`。provider 的角色声音配置由 provider 自身私有存储管理。

`PluginRoleUiSlot` 承载 `roleUi` 的 `mode: "self-managed"` 面板，提供只读角色上下文、真实 roleId、所属插件的 scoped client 与 `PluginHostServicesProvider`。插件自主读取、保存及报告 dirty，并通过所属插件的文件选择器导入参考音频；新角色无真实 ID 时不能持久化。该模式不参与宿主角色原子保存，不把跨存储成功或失败包装成单一事务。原有 `roleSettings` 的合法角色草稿模式继续保留。

两 provider 通过 SDK 4.1 的 `usePrivateDraft` 共享私有文档加载、dirty、保存及错误处理。迟到结果按 scoped client 和文档身份隔离；读取失败不生成可保存的空文档，保存失败保留草稿。具体健康检查、音频测试和持久化 RPC 仍由各插件拥有。

TTS 的 `EmotionReferences` 允许在空角色情绪目录下新增私有名称和参考，目录仅提供建议。空白、重复、原型特殊名称和超出 64 个映射的输入被拒绝；未完成导入的名称计入 dirty 并阻止保存或试听。删除和保存都只修改 provider 的 `moods`。预览可选择已配置映射，自动朗读仍按调用者传入的 mood 匹配，未命中使用默认参考。

健康状态的 `instance` 是 `{operation,url,state}` 标记或 `null`，state 为 `in_flight` / `unknown`，不是实例名称字符串。卸载编辑器时试听停止为 best effort，epoch 仍保证迟到合成不播放；仅通信错误中稳定的 `details.reason: context_disposed` 被视为已处置，其他失败通过宿主反馈报告。手动停止失败留在当前编辑器显示。

验证分两层：插件独立测试只依赖 SDK fake 与受控 HTTP；应用级验收安装实际两个 ZIP，通过隔离 Electron 生产入口与 Python bridge 测试独立 UI 及桌宠组合链路。后者可以替换原生输入为生成 PCM、替换本机 ASR/LLM/TTS HTTP 服务，但不伪造聊天事件或绕过真实服务调用。两者都不代表真实模型音质、情绪效果或本机性能通过，真实模型验收由 #676 承担。

## 分发与安装

两个 provider 的 manifest 均为 `distribution: external`，要求 SDK / Runtime API 4.1。仓库中的源码不参与内置后端发现、前端 registry 或冻结运行时收集。通用 `scripts/build-plugin.mjs` 将各包构建为独立 ZIP，保留 SDK/React 为宿主提供的 external，并使用已有 ZIP 安装、信任、启用、更新及卸载流程。该分类适用于所有插件，不按 provider id 特判。构建命令与服务准备见 [ASR README](../../../plugins/sensevoice_asr/README.md) 和 [TTS README](../../../plugins/gpt_sovits_tts/README.md)。

冻结宿主同时递归收集 SDK 运行时模块，包括没有 `__init__.py` 的 `files/`，排除 `shiori_sdk.testing` 与缓存；完整 SDK 不依赖当前已安装插件的静态引用。实际 PyInstaller 参数检查 SDK/宿主/内置插件模块是否全部进入 hidden imports。`test-sdk-runtime.mjs` 使用同一 collector 构建小型冻结探针，在仓库外清除 Python 源码路径后动态导入音频、暂存和 loopback HTTP 模块，并确认 testing 不存在。

## 中断语义

用户手动停止时，桌宠立即停止播放、清空待播句子并废弃当前轮次。录音、ASR、聊天或合成的迟到结果必须经插件自己的 epoch/轮次检查后才能发布；旧结果不得重新播放。聊天取消使用通用 `chat.cancel` 的精确 session/turn 身份。

停止播放不等于底层推理已经停止。provider 自己持有真实推理期间的串行所有权；桌宠只废弃结果，不把取消等待冒充 GPU 推理结束。试听与正常朗读使用 provider 的同一合成入口。

## 兼容性与旧数据

SDK/Runtime API **4.0** 移除了已发布的 `SurfaceHandle.voice`。桌宠要求 4.0；外部包必须明确声明其兼容范围，旧 `<4` 声明不会被静默接受。迁移说明见 [SDK README](../../../packages/sdk/README.md#compatibility)。

腾讯/MiniMax 实现、宿主语音配置与云音色生命周期已删除。升级不删除既有用户文件、密钥或远端音色；旧配置仅作为普通设置表单不拥有的 opaque 数据保留，不映射为本地参考素材。

## 修改影响

- 输入、朗读与中断：先检查桌宠 `background/voice/` 和 SDK-only 测试，再查原生资源接口的调用者归属与撤销。
- 动态 provider：检查通用 services 注册、通信 owner/generation、明确公开的方法及 provider 自己的协议；不要向宿主增加供应商分支。
- 本地服务：检查 provider HTTP 客户端、实例租约与隔离状态、私有参考文件生命周期及共享 WAV/loopback 工具；协议替身通过不等于真实模型音质通过。
- 外部包分发：同时检查后端 discovery、前端 builtin entries、冻结运行时 staging 与通用 ZIP builder，不能把源码存在等同于内置插件。
- 设置与角色面板：检查插件私有 RPC/文件、`VoiceSettings`、`PluginRoleUiSlot` 的身份与 dirty 生命周期；不把新数据写回角色草稿。
- 音频与按键：检查 `src/native/`、隐藏音频 renderer、真实 sender 验证及停用/重载清理，保留 WAV 和播放输入校验。
