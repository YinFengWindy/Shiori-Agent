---
title: 调度与角色任务
kind: 领域说明
status: 当前有效
last_verified_commit: d34c196a9
source_paths:
  - plugins/schedule/backend/plugin.py
  - plugins/schedule/backend/scheduler.py
  - plugins/schedule/backend/cron.py
  - plugins/schedule/backend/tools.py
  - plugins/schedule/backend/presenter.py
  - plugins/schedule/ui/
  - packages/sdk/python/shiori_sdk/core/scheduler.py
  - packages/sdk/python/shiori_sdk/core/schedule_host.py
  - apps/backend/agent/schedule_host.py
  - apps/backend/desktop_bridge/role_task_service.py
  - apps/desktop/renderer/src/chat/RoleTasksPanel.tsx
related:
  - proactive-and-drift.md
  - desktop-and-bridge.md
---

# 调度与角色任务

定时任务是系统插件 `plugins/schedule`（#906 P6s，默认启用）。`backend/scheduler.py` 的 `SchedulerService` 负责计算触发时间和调度执行（asyncio tick 循环），任务由 `JobStore` 持久化到工作区的 `schedules.json`（路径和格式与插件化之前一致，经 `WORKSPACE` 定位，不在插件数据目录）。`backend/tools.py` 向 Agent 暴露 `schedule`（创建）、`list_schedules`（查询）和 `cancel_schedule`（按 ID 前缀或名称取消）三个工具，插件 setup 时经 `TOOLS` 注册，其中只有 `list_schedules` 声明外部可用，外部上下文的受限回合不能增删计划（#489）。三个工具的 `role_id`（`schedule` 还有 `role_config_version`、`thread_id`、`delivery_key`）只取自回合的执行上下文（`context_precedence`），模型同名参数不能改写任务归属，也不能查看或取消别的角色的任务。插件 provide `SCHEDULER`（`shiori_sdk.core.scheduler`：创建、列出、取消角色的任务），供主动推送等消费方 `optional_inject`。核心不再注册这些工具；`[agent.wiring] toolsets` 里的 `"schedule"` 只是保留下来、不注册任何东西的名字。

调度器是插件的进程资源（`PROCESS_RESOURCES.acquire("scheduler-v1", ...)`）：进程里只有一份，第一次 setup 时 `start` 读取 `schedules.json`、清理孤儿并开始 tick；之后每一代（换代、代内重载）的 setup 只重新绑定 `SCHEDULE_HOST`、工具、RPC 和事件订阅，不重复读取、不多开 tick 循环。插件停用时宿主关闭这个资源：tick 停止，在途任务取消，`schedules.json` 保留。进程退出时同样关闭。

触发类型有 `at`（指定时刻）、`after`（延时，以用户消息到达时间为基准补偿推理延迟）和 `every`（固定间隔或 cron）；投递层级有 `instant`（到点直接推送固定文本）和 `soft`（按 `LatencyTracker` 的 P90 推理耗时提前触发，由 Agent 以计划任务专属会话生成内容后再推送，生成期间禁用 `message_push` 与记忆工具，跳过记忆召回和响应后记忆写入）。

到期执行走宿主端口 `SCHEDULE_HOST`（`shiori_sdk.core.schedule_host`）：`instant` 调 `deliver`，`soft` 先 `run_turn` 再在有内容时 `deliver(already_persisted=True)`；调度器把任务交成 `ScheduledRun`（任务 ID、名义触发时间、创建时间、角色、线程、投递目标），角色执行 metadata 与 `delivery_key` 由宿主实现 `agent/schedule_host.py` 的 `HostScheduleRunner` 生成。`HostScheduleRunner` 经运行时 dispatcher 落到当前发布代，跨代只有一份，由 `bootstrap/plugin_core.py` 作为 `SCHEDULE_HOST` 提供。计划任务线程格式 `scheduler_thread_id` 也由该 SDK 模块导出，核心 `conversation/service.py` 的 `is_scheduler_thread` 用同一份；`scheduler:` 会话与 `scheduled_job` 工作类型这些字符串约定留在核心。

任务触发后应进入统一的角色、会话和主动投递路径，而不是直接绕过 Agent/Conversation 写一条平台消息：执行经 `run_role_operation` 绑定角色上下文，推送经 `message_push` 发出：带角色身份时运行时的角色目标校验只放行该角色的桌面会话（`desktop` + `role:<角色ID>`），由桌面 sender 写入角色会话，指向外部渠道的任务在发送前被拒绝（角色往外部渠道发消息走 `account_send`）；线程默认为该任务的计划任务线程（`scheduler_thread_id`），每次触发带基于名义触发时间的 `delivery_key` 以便重试和重启时去重。一次性任务执行完即移除；周期任务从「当前时间与名义触发时间的较晚者」之后计算下一次触发，固定间隔从上次名义时间按步长推进，避免进程延迟造成连续补发或 soft 提前触发时重复命中同一次。启动恢复时，已错过的周期任务直接推进到下一个未来时间，一次性任务在 5 分钟宽限期内仍执行、超出则丢弃。执行失败只记日志，任务照常按上述规则推进或移除。

新建与更新任务默认固定为 `Asia/Shanghai`，不读取宿主系统时区；调用方仍可显式传入其他 IANA 时区。cron 星期字段遵循 POSIX 语义：`0` 和 `7` 都表示周日。无论安装了 APScheduler（插件依赖）还是走内置 fallback，都会得到相同的星期解释。

角色删除后清理：插件订阅 `RoleDeleted`，取消该角色的所有计划（先持久化移除，再取消等待或运行中的任务）；核心不再有删除前钩子。进程若在删除与清理之间退出，下次启动时 `load_and_recover` 经 `ROLES` 删除不存在角色的任务（包括禁用任务），保留正常角色的禁用任务；读取或写盘失败直接报错，不发布部分恢复状态。任务完成时检查自身是否仍在调度器中，已取消任务不能恢复周期排程，软任务即使在下游吞掉取消后返回内容也不会继续推送。

桌面「任务」面板（`apps/desktop/renderer/src/chat/RoleTasksPanel.tsx`）的外壳留在核心，`roles.tasks.list` / `cancel` 只列出 subagent 后台任务与记忆整理任务（`desktop_bridge/role_task_service.py`）。计划任务由插件前端经 `roleTasks` 插槽挂入整块（`plugins/schedule/ui/`：列表、详情、新建、编辑），数据走插件 RPC `plugin.schedule.{list,create,update,cancel}`；桌面新建的任务投递到该角色的桌面会话。任务变化、开始或结束运行后插件发 `plugin.schedule.tasks.changed`（`{role_id}`），只由当前发布代发出。`list`、`cancel` 在重载暂停准入时仍可用（`admission_exempt`），它们读写的是进程里唯一的调度器，哪一代应答都一样。

## 修改影响

- 修改任务 schema：检查工具参数、`schedules.json` 持久化、bridge models、presenter 和桌面表单。
- 修改触发计算：检查时区、夏令时、错过执行、重复执行和重启恢复。
- 修改角色任务：检查角色删除、会话选择、工具权限和主动投递目标。
- 修改取消/暂停：确认 scheduler runtime 与持久化状态同时更新。

## 验收重点

覆盖一次性与周期任务、时区、重启恢复、暂停/恢复、取消、角色删除后的悬空任务、重复触发保护、失败可见性以及桌面状态刷新。
