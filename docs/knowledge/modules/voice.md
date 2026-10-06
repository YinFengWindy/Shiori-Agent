---
title: 桌宠语音交互
kind: 领域说明
status: 当前有效
last_verified_commit: 4d894e09
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
related:
  - desktop-and-bridge.md
  - roles.md
  - conversations-and-sessions.md
---

# 桌宠语音交互

## 所有权与主链路

桌宠插件拥有语音业务。`background/voice/input.ts` 处理按住说话、按键来源和录音时限；`controller.ts` 协调 ASR、通用聊天与当前轮次；`sentences.ts` 和 `replyAudio.ts` 负责切句、合成与播放队列。插件按当前可见角色绑定输入；关闭语音或未安装 provider 不妨碍显示、拖动和文字气泡。

宿主 `apps/desktop/src/native/` 只负责原生录音、设备枚举、单音频播放停止和全局按键 down/up 注册。隐藏音频 renderer 执行采集与播放。原生资源绑定真实调用窗口、插件通信上下文和活动实例，停用、换代、窗口重载或退出时释放。surface 使用插件自有消息传递手势，宿主不解释“按住说话”或选择 provider。

录音经选定的 ASR 服务识别，再调用现有 `chat.send` 进入角色 Session 和 Agent Loop。宿主聊天只发布 `chat.delta`、`chat.done`、`chat.error` 等通用事件。桌宠按自己生成的 `turn_id`、实际 `session_key` 及事件中存在的角色标识匹配回复，键盘聊天或其他轮次不能启动本轮朗读。`voice.context.get` 是桌宠自己的 RPC，通过已授予的角色/会话接口读取真实 session 与 mood。

## Provider 调用与存储

通用 `PluginServiceRegistry` 只维护插件明确公开的服务方法和生命周期。provider 通过 SDK `services` 能力注册；消费插件按 contract 动态发现，并使用精确 `{plugin_id, service_id}` 引用调用。通信层验证 owner、generation 和注册实例，不自动启用服务，也不跨 provider fallback。

SDK 的 `shiori.asr.v1` 定义 `transcribe({audio_base64, format}) -> {text}`；`shiori.tts.v1` 定义 `synthesize({text, role_id, mood}) -> {audio_base64, format}`。SDK 不保存音色、参考素材、选型策略或语音状态机。实际本地 provider 由后续独立插件实现，本轮用中性实现验证契约。

桌宠后端 `VoicePreferencesStore` 自主读写 `plugin-data/desktop_pet/voice-preferences.json`，保存启用状态、快捷键、麦克风和 ASR/TTS 选择；UI 由桌宠 `VoiceSettings.tsx` 注入。新语音数据不进入宿主 `[voice]`、`[plugins.desktop_pet]` 或 `roles.json` 的 `runtime_config.tts` / `plugin_data`。provider 的角色声音配置由 provider 自身私有存储管理。

`PluginRoleUiSlot` 承载 `roleUi` 的 `mode: "self-managed"` 面板，提供只读角色上下文、真实 roleId 和所属插件的 scoped client。插件自主读取、保存及报告 dirty；新角色无真实 ID 时不能持久化。该模式不参与宿主角色原子保存，不把跨存储成功或失败包装成单一事务。原有 `roleSettings` 的合法角色草稿模式继续保留。

## 中断语义

用户手动停止时，桌宠立即停止播放、清空待播句子并废弃当前轮次。录音、ASR、聊天或合成的迟到结果必须经插件自己的 epoch/轮次检查后才能发布；旧结果不得重新播放。聊天取消使用通用 `chat.cancel` 的精确 session/turn 身份。

停止播放不等于底层推理已经停止。provider 自己持有真实推理期间的串行所有权；桌宠只废弃结果，不把取消等待冒充 GPU 推理结束。试听与正常朗读使用 provider 的同一合成入口。

## 兼容性与旧数据

SDK/Runtime API **4.0** 移除了已发布的 `SurfaceHandle.voice`。桌宠要求 4.0；外部包必须明确声明其兼容范围，旧 `<4` 声明不会被静默接受。迁移说明见 [SDK README](../../../packages/sdk/README.md#compatibility)。

腾讯/MiniMax 实现、宿主语音配置与云音色生命周期已删除。升级不删除既有用户文件、密钥或远端音色；旧配置仅作为普通设置表单不拥有的 opaque 数据保留，不映射为本地参考素材。

## 修改影响

- 输入、朗读与中断：先检查桌宠 `background/voice/` 和 SDK-only 测试，再查原生资源接口的调用者归属与撤销。
- 动态 provider：检查通用 services 注册、通信 owner/generation、明确公开的方法及 provider 自己的协议；不要向宿主增加供应商分支。
- 设置与角色面板：检查插件私有 RPC/文件、`VoiceSettings`、`PluginRoleUiSlot` 的身份与 dirty 生命周期；不把新数据写回角色草稿。
- 音频与按键：检查 `src/native/`、隐藏音频 renderer、真实 sender 验证及停用/重载清理，保留 WAV 和播放输入校验。
