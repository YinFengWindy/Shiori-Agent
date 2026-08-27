---
title: 桌宠语音交互
kind: 领域说明
status: 当前有效
last_verified_commit: 277053d5
source_paths:
  - apps/backend/agent/voice_config.py
  - apps/desktop/src/voice/
  - apps/desktop/renderer/src/voice/
  - apps/backend/desktop_bridge/voice/role_tts_settings.py
  - apps/backend/desktop_bridge/voice/tts_text.py
  - apps/backend/desktop_bridge/voice/voice_http.py
  - apps/backend/desktop_bridge/voice/voice_models.py
  - apps/backend/desktop_bridge/voice/voice_service.py
  - apps/backend/desktop_bridge/voice/tts_coordinator.py
  - apps/backend/desktop_bridge/chat_service.py
related:
  - desktop-and-bridge.md
  - roles.md
  - conversations-and-sessions.md
---

# 桌宠语音交互

## 主链路

Electron 主进程的 `DesktopVoiceController` 为每次按住说话生成 `voice_turn_id`。录音经隐藏 renderer 转为 16 kHz 单声道 PCM/WAV，`voice.transcribe` 完成 ASR 后仍通过现有 `chat.send` 和角色 Session 进入 Agent Loop，不存在平行聊天链路。

Python `DesktopChatService` 只为 `input_method=voice` 且角色 provider 与全局 TTS provider 一致的回合创建 `TtsTurnCoordinator`。协调器按完整句子合成，`voice.reply.started`、`voice.tts.audio` 和 `voice.tts.error` 都携带同一个 `voice_turn_id`。Electron 只接收当前 turn 的事件，播放队列按句序号排序。

## 中断语义

新语音输入开始时，本地播放立即切换到新 turn：正在播放的旧句子自然结束，旧 turn 尚未播放的句子全部丢弃，新 turn 音频可以同时排队。主进程通过 `voice.turn.cancel` 精确取消旧 turn；Python 同时中断该 turn 的 Agent 任务、永久关闭协调器并向 provider 流发送线程安全取消信号。晚到的旧 delta、音频和错误事件都被忽略。

## Provider 与声音资产

全局配置决定当前可用的 ASR/TTS provider 和凭据，角色配置保存 provider、`voice_id`、显示名、语速、心情到情绪映射及 ownership。角色 provider 不匹配时不合成，也不自动 fallback。

`ownership=external` 表示用户手动绑定的供应商音色，Shiori 永不自动删除；`ownership=shiori_managed` 只由 Shiori 复刻结果产生。替换或显式移除 managed 音色时，表单先记录待清理资产，角色保存成功后再调用 `voice.delete`。后端仍会同时校验 ownership、provider 和 `Shiori_` ID 前缀。

## 指标与隐私

ASR/TTS 成功和失败都使用同一组非敏感指标：`provider`、`request_id`、`elapsed_ms`、`audio_duration_ms`、`character_count`、`error_code`。ASR 指标进入用户消息元数据，TTS 指标随句子事件返回。原始录音和完整 TTS 音频不进入默认日志，也不写入会话；日志只记录上述指标和用户可读错误。

## 修改影响

- 修改 turn 中断：同步检查 controller、bridge event router、playback、`DesktopChatService` 和 `TtsTurnCoordinator`。
- 修改 provider：同步检查全局配置、角色配置读写、协调器 enabled 判定和 provider 客户端。
- 修改声音资产：保持 external/managed 区分，并验证角色保存成功后清理、失败重试和后端删除保护。
- 修改指标：同步检查 provider 解析、bridge payload、聊天元数据白名单和日志，禁止加入原始音频。
