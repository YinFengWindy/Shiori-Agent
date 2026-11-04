# proactive

系统插件。按每个角色 `proactive` 设置里的开关跑主动循环和 Drift。循环是进程资源：每个插件代只重新绑定宿主端口，每个角色一个循环，在该代发布后才启动；循环至少每 60 秒重读角色设置，开关关闭后约 60 秒内停止 tick 并释放 MCP 会话与 feed 轮询。场景追问通过 `SCENE.request` 登记。

`[plugins.proactive]` 的 `scene_followup` 与 `relationship` 默认开启。没有主模型注册时不跑循环。关掉本插件后普通聊天和计划任务照常。

角色能力面板由本插件的 `roleSettings` 提供，沿用原有卡片和参数对话框。编辑参与角色页的保存/重置；保存经 `settings_set` RPC 写回原角色 JSON 的 `proactive`，不迁移数据。核心角色先保存，主动设置失败会保留草稿并提示部分成功；重试只写编辑过的参数。停用插件隐藏面板并保留原设置。

配置与频率诊断日志分别写入 `<workspace>/plugin-data/proactive/logs/proactive_config_trace.jsonl` 和 `proactive_rate_trace.jsonl`。冷启动迁入旧 `memory/` 下的同名文件；已有新目标优先，旧文件核对后归档，详见[存储决策](../../docs/decisions/2026-11-04-plugin-storage-paths.md)。角色自己的 `proactive.db`、Drift 和记忆文件仍在角色目录，信息源声明仍在工作区根目录的 `proactive_sources.json`。MCP 启动命令从 `plugin-data/mcp/mcp_servers.json` 读取。
