---
title: 会话与对话
kind: 领域说明
status: 当前有效
last_verified_commit: 5ed016f2
source_paths:
  - apps/backend/session/
  - apps/backend/conversation/store.py
  - apps/backend/conversation/service.py
  - apps/backend/conversation/projector.py
  - apps/backend/conversation/push_sync.py
  - apps/backend/conversation/context_scope.py
related:
  - roles.md
  - memory.md
  - desktop-and-bridge.md
---

# 会话与对话

## 两层职责

`apps/backend/session/` 管理 Agent 运行所需的会话状态，包括消息、presence、搜索、角色会话和连接。`apps/backend/conversation/` 管理可持久化的线程模型、存储、投影和推送同步。

可以把 Session 理解为“当前如何运行”，把 Conversation 理解为“对话如何长期存在和被不同入口一致地看见”。两者相关但不能混为一个数据结构。

## 消息连续性

渠道和桌面输入都应解析到稳定的会话/线程标识。消息先进入权威服务，再由 projector 或 presenter 形成不同界面的读取模型。`push_sync.py` 处理主动推送与线程状态同步，避免自动消息只出现在渠道而没有进入权威角色会话。

## 修改影响

- 修改消息模型：检查 bus 事件、Session store、Conversation projector、桌面 presenter、渠道格式化与记忆采样。
- 修改会话键规则：检查 `apps/backend/infra/channels/session_key.py`、角色绑定、群聊成员隔离和历史迁移。
- 修改线程删除或归档：检查 Session 缓存、搜索索引、桌面导航和后台任务引用。
- 修改主动消息写入：确保消息同时完成投递与 Conversation/Session 同步。

## 不变量

- 同一逻辑会话在渠道、桌面和主动投递路径中应得到同一权威标识。
- 投影可以重建，权威消息不能只存在于 UI 状态。
- 迁移失败必须可见，不能静默创建一条看似正常但丢失历史的新线程。
- 模型历史按会话分为用户上下文（桌面、已绑定用户的私聊）与外部上下文（群聊、陌生私聊）并双向隔离；归属在读取时按当前身份绑定计算，规则只在 `conversation/context_scope.py`。没有 `thread_id` 的旧消息和没有来源会话的计划任务归入用户上下文；新写入角色会话的消息必须带 `thread_id`。角色会话读取历史必须给出筛选（上下文视图，或记忆整理用的 `whole_session`），漏传直接报错；`search_messages` / `fetch_messages` 在角色回合里同样按回合上下文筛选。
- 群笔记和群摘要可通过 `lookup_group_context` 按需跨群、跨渠道查询，再用 `update_group_context` 编辑。两个工具都不进入外部工具白名单，普通群友触发的受限回合不可发现或调用，已绑定用户本人在群里触发的回合仍可使用。查询无参数或按群名查找时分页返回候选，指定 `group_thread_id` 后返回笔记、最新摘要及摘要更新时间；缺失字段为空字符串。更新必须指定群 ID，笔记与摘要至少提供一项：省略字段保持原样，空字符串清空，内容未变化不写入，摘要变更（包括清空）才刷新摘要更新时间。成功后返回当前内容，后续查询与自动注入读取新值；旧整理草稿不能覆盖期间编辑过的群环境。
- 群环境工具只覆盖当前角色仍所属的群，排除归档、私聊、桌面和计划任务会话，不返回或修改聊天、旁听原文。它们不受自动注入最近动态的三天、五条限制，也不改变自动注入或历史消息工具的隔离规则。
- 工具与小手机的群笔记保存共用手动编辑边界。每次实际改动都会推进持久编辑版本，整理提交时核对该版本；即使正文被改回原值或笔记被清空，编辑前的草稿仍不能提交。无变化的保存与查询都不推进版本，摘要更新时间仍只随摘要内容变化。
