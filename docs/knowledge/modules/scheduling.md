---
title: 调度与角色任务
kind: 领域说明
status: 当前有效
last_verified_commit: 3955470b
source_paths:
  - agent/scheduler.py
  - agent/scheduler_cron.py
  - agent/tools/schedule.py
  - bootstrap/toolsets/schedule.py
  - desktop_bridge/schedule_role_task_service.py
  - desktop_bridge/role_task_service.py
related:
  - proactive-and-drift.md
  - desktop-and-bridge.md
---

# 调度与角色任务

`agent/scheduler.py` 负责计算触发时间和调度执行，`agent/tools/schedule.py` 将创建、查询、更新和取消能力暴露给 Agent，bootstrap 将工具注册进 ToolRegistry。桌面桥接分别提供通用调度角色任务与角色任务服务，并由 presenter 形成 UI 数据。

任务触发后应进入统一的角色、会话和主动投递路径，而不是直接绕过 Agent/Conversation 写一条平台消息。一次性任务完成后应终止；周期任务应根据上次计划时间稳定计算下一次触发，避免进程延迟造成连续补发。

新建与更新任务默认固定为 `Asia/Shanghai`，不读取宿主系统时区；调用方仍可显式传入其他 IANA 时区。cron 星期字段遵循 POSIX 语义：`0` 和 `7` 都表示周日。无论安装了 APScheduler 还是走内置 fallback，都会得到相同的星期解释。

## 修改影响

- 修改任务 schema：检查工具参数、持久化、bridge models、presenter 和桌面表单。
- 修改触发计算：检查时区、夏令时、错过执行、重复执行和重启恢复。
- 修改角色任务：检查角色删除、会话选择、工具权限和主动投递目标。
- 修改取消/暂停：确认 scheduler runtime 与持久化状态同时更新。

## 验收重点

覆盖一次性与周期任务、时区、重启恢复、暂停/恢复、取消、角色删除后的悬空任务、重复触发保护、失败可见性以及桌面状态刷新。
