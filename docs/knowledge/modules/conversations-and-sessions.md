---
title: 会话与对话
kind: 领域说明
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - session/
  - conversation/store.py
  - conversation/service.py
  - conversation/projector.py
  - conversation/push_sync.py
related:
  - roles.md
  - memory.md
  - desktop-and-bridge.md
---

# 会话与对话

## 两层职责

`session/` 管理 Agent 运行所需的会话状态，包括消息、presence、搜索、角色会话和连接。`conversation/` 管理可持久化的线程模型、存储、投影、推送同步与旧数据迁移。

可以把 Session 理解为“当前如何运行”，把 Conversation 理解为“对话如何长期存在和被不同入口一致地看见”。两者相关但不能混为一个数据结构。

## 消息连续性

渠道和桌面输入都应解析到稳定的会话/线程标识。消息先进入权威服务，再由 projector 或 presenter 形成不同界面的读取模型。`push_sync.py` 处理主动推送与线程状态同步，避免自动消息只出现在渠道而没有进入权威角色会话。

## 修改影响

- 修改消息模型：检查 bus 事件、Session store、Conversation projector、桌面 presenter、渠道格式化与记忆采样。
- 修改会话键规则：检查 `infra/channels/session_key.py`、角色绑定、群聊成员隔离和历史迁移。
- 修改线程删除或归档：检查 Session 缓存、搜索索引、桌面导航和后台任务引用。
- 修改主动消息写入：确保消息同时完成投递与 Conversation/Session 同步。

## 不变量

- 同一逻辑会话在渠道、桌面和主动投递路径中应得到同一权威标识。
- 投影可以重建，权威消息不能只存在于 UI 状态。
- 迁移失败必须可见，不能静默创建一条看似正常但丢失历史的新线程。
