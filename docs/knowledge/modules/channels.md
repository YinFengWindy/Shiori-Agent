---
title: 渠道系统
kind: 领域说明
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - infra/channels/
  - core/channels/hub.py
  - plugins/qqbot/
  - bootstrap/channels.py
related:
  - conversations-and-sessions.md
  - desktop-and-bridge.md
---

# 渠道系统

## 统一边界

`infra/channels/contract.py` 定义 Channel 合约与上下文，`core/channels/hub.py` 汇总渠道，bootstrap 负责按配置启动。渠道适配器把外部消息转换为统一入站事件，并把统一出站消息渲染为平台格式。

Telegram 实现在 `infra/channels/telegram_channel/`，拆分 lifecycle、inbound、outbound、media、streaming、commands 等职责。QQ 相关适配位于 `infra/channels/qq_channel.py` 与 `plugins/qqbot/`。

## 标识与投递

`session_key.py`、`reply_context.py` 和公共 channel identifier helper 负责稳定定位账号、聊天、线程与回复上下文。群聊过滤和成员隔离必须在入站边界明确处理。typing、流式编辑等辅助动作允许独立失败，但最终消息投递和权威会话写入必须可观测。

## 修改影响

- 修改 Channel 合约：检查所有渠道实现、bootstrap host、消息总线和测试替身。
- 修改聊天标识：检查角色绑定、Session/Conversation 键、群聊记忆域和推送目标。
- 修改附件模型：检查 Telegram 媒体、QQ 适配、桌面桥接、自动 CG 和历史消息展示。
- 新增渠道：复用统一合约、会话解析和输出端口，不复制 Agent 回合逻辑。
