# Herdr

需要 Herdr 0.9.4 或以上版本。插件默认连接 Herdr 的 `default` session；启用后可在插件设置页
填写 Herdr 可执行文件，并从本机 `herdr session list` 列出的 session（带运行中 / 已停止状态）
中选择，修改自动保存。当前配置的 session 不在列表中时仍显示并保留；Herdr 不可用、命令失败
或插件未启用时设置页显示读取错误，其余设置照常可改。Herdr 和选定的
Codex / Claude Code 必须已安装、登录，并在该 session 可使用；插件不安装 CLI、
修改全局设置或连接用户当前聚焦的 session。首版只提供 Full Access。

聊天工具 `herdr_start_task` 接收仓库根目录、完整需求及可选的 `codex` / `claude`，
立即返回任务编号，在独立 worktree 中修改、验证、提交并创建 Draft PR。
结果回到原角色与原聊天。角色或用户绑定失效时不会向另一个目标投递。

`herdr_list_tasks` / `herdr_get_task` 只显示当前角色的任务；查询会刷新终端状态和
最近输出。`herdr_continue_task` 接收追加要求，在同一 agent/worktree 创建新回合，
执行中拒绝并发提交。`herdr_cancel_task` 先返回 cancelling，发送指定 agent 的
Ctrl+C 并确认就绪后才标记 cancelled；无法确认则为 unknown，保留产物。
初次登录、目录信任或原生交互提示需先在 Herdr 处理，随后可继续原任务。

导航栏的 Herdr 页面在宿主二级栏按「进行中 / 已结束」列出全部角色的任务（发起角色
头像、需求首行、状态与阶段、最近报告时间），主区展示选中任务：阶段条与最新进展、
终端输出、折叠的活动记录 / 验证结果 / 完整需求，交付后突出修改摘要与 Draft PR，
底部输入框提交追加要求。继续和取消（需确认）复用聊天工具的任务服务，是否可用由
服务端判定；打开 PR 通过宿主校验的外部链接能力完成。

阶段来自每回合独立的 `<run_id>.progress.jsonl`。Agent 按任务指令追加完整 JSON
行，字段为 `task_id`、`run_id`、递增 `sequence`、`stage` 和 `detail`。仅当前
任务/回合且序号更新的报告会被接收，允许验证返回实现；终端回显不算进度证据。
准备、分析、实现、验证、创建 PR 与任务生命周期状态分别展示。没有新报告时
保留最后阶段及报告时间，监控同步时间不会冒充活动时间，不显示估算完成比例。
单文件读取上限 256 KiB、单条 detail 2000 字符、时间线保留最近 100 条；无效或
暂不可读的报告作为诊断保留，不中断任务执行与交付校验。

桌面端 RPC：`tasks.list`（任务摘要）与 `tasks.get`（单任务详情）是只读并发请求，
`tasks.continue` / `tasks.cancel` 返回与 `tasks.get` 相同的详情；`tasks.changed`
事件仅携带任务 ID 和修订号。`sessions.list`（只读）调用 `herdr session list --json`，
返回 `{sessions: [{name, status: "running" | "stopped"}]}`，不限定配置的 session。页面先订阅事件再读取，同一插件进程内较旧的修订不会
覆盖较新的；断线时保留最后内容并禁用操作，连接恢复后重新读取。离开页面只退订
视图，后台任务照常运行。后台新增任务不会切走当前选择；终端停在底部时跟随新输出，
上翻后保持阅读内容并提示「有新输出」，切换任务或进入新回合会重置。

Herdr 的终端状态和交付状态独立：idle/done 不代表完成，CLI 超时也不代表停止。
插件核验本回合结果文件、代码提交、实际执行验证命令和开放 Draft PR 的 head SHA。
不会自动重发可能已经接收的任务，不会合并 PR 或删除 worktree。

Windows 验证命令先按 PATH/PATHEXT 解析可执行程序，普通 `pnpm test`、
`pnpm --filter ... typecheck` 和含空格的参数可以使用。`.cmd` / `.bat` 会经过
cmd 解析；如果程序路径或参数含 `& | < > ^ % !`、双引号、括号或控制字符，
插件会在启动前以 `unsafe_windows_batch_argument` 拒绝并将任务报告为阻塞。
请在交付结果的 `validation[].argv` 中改用原生可执行程序，或 Node/Python
可执行程序加脚本路径及参数。插件不拼接 shell、不自动改写或重试这些命令。
该限制只针对 Windows 批处理；传给 `herdr.exe` 的完整需求不受影响。

任务由应用进程级资源管理，配置重载保留任务和监控。新任务使用新配置，旧任务的
查询、继续和取消保留原 Herdr session；完成回报使用当前 runtime 的角色模型与渠道。
停用插件或关闭应用停止监控，不发送全局 Herdr 停止指令，也不删除 worktree。

仅当前 Shiori 运行期间追踪。关闭 Shiori 后 Herdr 任务可能继续运行，插件不恢复
旧追踪记录；初始化、登录或交互请求会作为 blocked 回报，并保留终端和产物。
任务文件与 worktree 位于插件私有数据目录，完整需求保存在 UTF-8 文件中。

此插件依赖当前开发批次 Unreleased 的 `background_results` / `process_resources` / `host.openExternal` SDK 契约；正式发布前
需按仓库统一定版流程更新 SDK/Runtime API 最低版本。
