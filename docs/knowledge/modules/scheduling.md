---
title: 调度与角色任务
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - apps/backend/agent/scheduler.py
  - apps/backend/agent/scheduler_cron.py
  - apps/backend/agent/tools/schedule.py
  - apps/backend/bootstrap/toolsets/schedule.py
  - apps/backend/desktop_bridge/schedule_role_task_service.py
  - apps/backend/desktop_bridge/schedule_role_task_presenter.py
  - apps/backend/desktop_bridge/role_task_service.py
related:
  - proactive-and-drift.md
  - desktop-and-bridge.md
---

# 调度与角色任务

`apps/backend/agent/scheduler.py` 的 `SchedulerService` 负责计算触发时间和调度执行（asyncio tick 循环），任务由 `JobStore` 持久化到工作区的 `schedules.json`。`apps/backend/agent/tools/schedule.py` 向 Agent 暴露 `schedule`（创建）、`list_schedules`（查询）和 `cancel_schedule`（按 ID 前缀或名称取消）三个工具；`bootstrap/toolsets/schedule.py` 构造 scheduler 并把工具注册进 ToolRegistry，其中只有 `list_schedules` 声明外部可用，外部上下文的受限回合不能增删计划（#489）。更新任务只走桌面：`desktop_bridge/schedule_role_task_service.py` 提供按角色的列出、创建、更新和取消，`schedule_role_task_presenter.py` 形成 UI 数据，`role_task_service.py` 再把计划任务与 subagent 后台任务、记忆整理任务合成角色任务视图。

触发类型有 `at`（指定时刻）、`after`（延时，以用户消息到达时间为基准补偿推理延迟）和 `every`（固定间隔或 cron）；投递层级有 `instant`（到点直接推送固定文本）和 `soft`（按 `LatencyTracker` 的 P90 推理耗时提前触发，由 Agent 以计划任务专属会话生成内容后再推送，生成期间禁用 `message_push` 与记忆工具，跳过记忆召回和响应后记忆写入）。

任务触发后应进入统一的角色、会话和主动投递路径，而不是直接绕过 Agent/Conversation 写一条平台消息：执行经 `run_role_operation` 绑定角色上下文，推送经 `message_push` 记入角色会话，线程默认为该任务的计划任务线程（`scheduler_thread_id`），每次触发带基于名义触发时间的 `delivery_key` 以便重试和重启时去重。一次性任务执行完即移除；周期任务从「当前时间与名义触发时间的较晚者」之后计算下一次触发，固定间隔从上次名义时间按步长推进，避免进程延迟造成连续补发或 soft 提前触发时重复命中同一次。启动恢复时，已错过的周期任务直接推进到下一个未来时间，一次性任务在 5 分钟宽限期内仍执行、超出则丢弃。执行失败只记日志，任务照常按上述规则推进或移除。

新建与更新任务默认固定为 `Asia/Shanghai`，不读取宿主系统时区；调用方仍可显式传入其他 IANA 时区。cron 星期字段遵循 POSIX 语义：`0` 和 `7` 都表示周日。无论安装了 APScheduler 还是走内置 fallback，都会得到相同的星期解释。

角色删除通过 `RoleAggregateService` 的同步删除前监听清理该角色的所有计划；调度器先持久化移除，再取消等待或运行中的任务，清理失败时角色保留以便重试。任务完成时检查自身是否仍在调度器中，已取消任务不能恢复周期排程，软任务即使在下游吞掉取消后返回内容也不会继续推送。启动恢复通过真实角色仓库清理历史孤儿（包括禁用任务），保留正常角色的禁用任务；角色读取或清理写盘失败直接报错，不发布部分恢复状态。

## 修改影响

- 修改任务 schema：检查工具参数、`schedules.json` 持久化、bridge models、presenter 和桌面表单。
- 修改触发计算：检查时区、夏令时、错过执行、重复执行和重启恢复。
- 修改角色任务：检查角色删除、会话选择、工具权限和主动投递目标。
- 修改取消/暂停：确认 scheduler runtime 与持久化状态同时更新。

## 验收重点

覆盖一次性与周期任务、时区、重启恢复、暂停/恢复、取消、角色删除后的悬空任务、重复触发保护、失败可见性以及桌面状态刷新。
