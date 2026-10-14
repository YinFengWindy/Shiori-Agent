# Herdr

需要 Herdr 0.9.4 或以上版本。启用后在插件设置填写 Herdr 可执行文件与明确的本机 session。Herdr 和选定的
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

导航栏的 Herdr 看板汇总全部角色任务，可按角色、仓库和状态筛选；详情展示当前
阶段、活动时间线、最近终端输出、验证结果及已验证的 Draft PR。继续和取消复用
聊天工具的任务服务，打开 PR 通过宿主校验的外部链接能力完成。

阶段来自每回合独立的 `<run_id>.progress.jsonl`。Agent 按任务指令追加完整 JSON
行，字段为 `task_id`、`run_id`、递增 `sequence`、`stage` 和 `detail`。仅当前
任务/回合且序号更新的报告会被接收，允许验证返回实现；终端回显不算进度证据。
准备、分析、实现、验证、创建 PR 与任务生命周期状态分别展示。没有新报告时
保留最后阶段及报告时间，监控同步时间不会冒充活动时间，不显示估算完成比例。
单文件读取上限 256 KiB、单条 detail 2000 字符、时间线保留最近 100 条；无效或
暂不可读的报告作为诊断保留，不中断任务执行与交付校验。

页面先订阅任务失效事件，再取权威快照；事件仅携带任务 ID 和修订号。重新进入、
连接恢复及周期核对会重新取快照，重复/较旧事件与快照不回退任务状态。离开看板
只退订视图，后台任务照常运行；日志更新不自动滚动，用户可选择查看最新输出。

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
