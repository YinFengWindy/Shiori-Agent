# 定时任务（schedule）

系统插件，默认启用。角色或用户事先约好的定时提醒与定时回合：provide `SCHEDULER`，注册 `schedule`、`list_schedules`、`cancel_schedule` 三个工具，并在聊天右栏的「任务」面板挂入定时任务区块（列表、详情、新建、编辑）。

## 数据

任务存于 `<workspace>/schedules.json`（根数组），路径和格式与插件化之前一致。插件启用后，已有任务继续执行；超过 5 分钟宽限期的单次任务在启动时丢弃，循环任务推进到下一次。

## 运行

调度器是插件的进程资源：进程里只有一份，第一次 setup 时读取任务并开始每秒检查；换代和代内重载只重新绑定工具、RPC 和事件订阅，调度不中断、不重复读取。到期任务经宿主的 `SCHEDULE_HOST` 在当前发布代上执行：`instant` 直接投递固定消息，`soft` 跑一次定时回合再投递回复。

角色删除后，插件收到 `RoleDeleted` 取消该角色的任务；进程若在两者之间退出，下次启动时删除不存在角色的任务。

## 界面

聊天右栏「任务」面板里的「计划任务」区块。插件经自己的 `plugin.schedule.{list,create,update,cancel}` RPC 读写，任务变化或开始、结束运行后发 `plugin.schedule.tasks.changed`（`{role_id}`）。桌面新建的任务投递到该角色的桌面会话，时区为 Asia/Shanghai。

## 插件关闭时

调度停止，在途任务取消；三个工具不注册，任务面板不显示计划任务区块，聊天与其他后台任务照常。`schedules.json` 保留，重新启用后继续执行。
