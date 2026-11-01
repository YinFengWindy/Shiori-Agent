# proactive

系统插件。按每个角色 `proactive` 设置里的开关跑主动循环和 Drift。循环是进程资源：每个插件代只重新绑定宿主端口，每个角色一个循环，在该代发布后才启动；循环至少每 60 秒重读角色设置，开关关闭后约 60 秒内停止 tick 并释放 MCP 会话与 feed 轮询。场景追问通过 `SCENE.request` 登记。

`[plugins.proactive]` 的 `scene_followup` 与 `relationship` 默认开启。没有主模型注册时不跑循环。关掉本插件后普通聊天和计划任务照常。
