# Herdr

需要 Herdr 0.9.4 或以上版本。插件默认连接 Herdr 的 `default` session；启用后可在插件设置页
填写 Herdr 可执行文件，并从本机 `herdr session list` 列出的 session（带运行中 / 已停止状态）
中选择，修改自动保存。当前配置的 session 不在列表中时仍显示并保留；Herdr 不可用、命令失败
或插件未启用时设置页显示读取错误，其余设置照常可改。Herdr 和选定的
Codex / Claude Code 必须已安装、登录，并在该 session 可使用；插件不安装 CLI、
修改全局设置，也不依赖 Herdr 当前聚焦的 pane。首版只提供 Full Access。

聊天工具 `herdr_start_task` 接收仓库根目录、完整需求及可选的 `codex` / `claude`，
立即返回任务编号，在独立 worktree 中修改、验证、提交并创建 Draft PR。
结果回到原角色与原聊天。角色或用户绑定失效时不会向另一个目标投递。

`herdr_list_tasks` / `herdr_get_task` 只显示当前角色的任务；查询会刷新终端状态和
最近输出。`herdr_continue_task` 接收追加要求，在同一 agent/worktree 创建新回合，
执行中拒绝并发提交。`herdr_cancel_task` 先返回 cancelling，发送指定 agent 的
Ctrl+C 并确认就绪后才标记 cancelled；无法确认则为 unknown，保留产物。
初次登录、目录信任或原生交互提示需先在 Herdr 处理，随后可继续原任务。

导航栏的 Herdr 页面以 agent 为单位：宿主二级栏按 Herdr workspace 分组列出所配置
session 的全部 agent，包括用户在 Herdr 中手动打开的 CLI（终端标题、类型与 Herdr
状态、工作目录）。承载插件任务的 agent 只出现一次，显示为该任务（发起角色头像、
需求首行、状态与阶段、最近报告时间）并附带 agent 的 Herdr 状态。没有被列出的 agent 承载的插件任务（启动中、agent 已
离开 session、属于其他 session，或 session 不可用时的全部任务）放在最后的「插件
任务」组，未结束的在前，交付信息不会因此丢失。

主区顶部是选中 agent 的头部（终端标题、Herdr 状态、类型与工作目录），其下为最近
终端输出；关联插件任务时，在头部下方、终端外围显示阶段条与最新进展、
折叠的活动记录 / 验证结果 / 完整需求，交付后突出修改摘要与 Draft PR，底部输入框
提交追加要求。继续和取消（需确认）复用聊天工具的任务服务，是否可用由服务端判定；
打开 PR 通过宿主校验的外部链接能力完成。选中的 agent 从 Herdr 消失后保持选中，主区
提示其已不存在。插件不判定手动打开的 agent 的交付是否完成。

底部输入框把文字作为 prompt 直接发给选中的 agent（`herdr agent prompt`），旁边的中断
按钮发送一次 Ctrl+C（`herdr agent send-keys <pane> ctrl+c`），不经过角色、不需确认。
prompt 在 agent 开始工作或提出确认时即算送达，Herdr 最多等 10 秒（CLI 进程超时不短于此）；agent 已关闭、正在等待
确认（`agent_blocked`，不发送任何输入）、session 不可用等失败会显示原因并保留输入；
超时或 Herdr 未观察到 agent 开始工作（`agent_prompt_stalled`）记为「未确认送达」，消息
可能已经送达，插件不自动重发，输入同样保留由用户决定。断线、session 不可用或 agent
消失时禁用输入和中断。关联插件任务的 agent：任务回合进行中不提供直接发送和 Ctrl+C
（服务端同样拒绝，以免插进受监控的回合），要停下它用任务的「取消」，取消有追踪和确认；
底部的「追加要求」在回合结束后才可用（Enter 发送，开启新的受核验回合），同时出现
「直接发送」（同一段文字原样发给 agent，不属于任务、不做交付核验）与中断。直接输入在
发送期间持有该任务的操作锁，并在最后一刻再判断，任务的继续 / 取消不会与之交错。

每个 agent 的指令记录（来源、时间、内容、结果：发送中 / 已发送 / 未确认送达 / 未发送）
保存在插件进程内，按 session 与 pane ID 区分，每个 agent 保留最近 100 条，配置重载
保留、关闭 Shiori 后不恢复；主区以折叠的「指令记录」显示，面板发出的来源标为「你」。

阶段来自每回合独立的 `<run_id>.progress.jsonl`。Agent 按任务指令追加完整 JSON
行，字段为 `task_id`、`run_id`、递增 `sequence`、`stage` 和 `detail`。仅当前
任务/回合且序号更新的报告会被接收，允许验证返回实现；终端回显不算进度证据。
准备、分析、实现、验证、创建 PR 与任务生命周期状态分别展示。没有新报告时
保留最后阶段及报告时间，监控同步时间不会冒充活动时间，不显示估算完成比例。
单文件读取上限 256 KiB、单条 detail 2000 字符、时间线保留最近 100 条；无效或
暂不可读的报告作为诊断保留，不中断任务执行与交付校验。

桌面端 RPC：`tasks.list`（任务摘要）与 `tasks.get`（单任务详情）是只读并发请求，
`tasks.continue` / `tasks.cancel` 返回与 `tasks.get` 相同的详情；`tasks.changed`
事件仅携带任务 ID 和修订号。页面先订阅事件再读取，同一插件进程内较旧的修订不会
覆盖较新的。`sessions.list`（只读）调用 `herdr session list --json`，
返回 `{sessions: [{name, status: "running" | "stopped"}]}`，不限定配置的 session。
`agents.list` 返回当前配置 session 的 agent，按 workspace 分组并带
workspace 名称，每项含 pane ID（agent 标识）、类型、Herdr 状态、终端标题、cwd 及
关联插件任务 ID；`agents.get`（参数 `pane_id`）返回该 agent 的状态、最近终端输出
与关联任务详情，以及该 agent 的指令记录 `commands` 和能否直接输入 `can_prompt`（插件
任务回合进行中为 false），Herdr 已不认识该 agent 时返回 `agent: null`。两者都是只读并发
请求。`agents.prompt`（参数 `pane_id`、`text`）与 `agents.keys`（参数 `pane_id`、
`keys`，Herdr 逻辑按键名如 `ctrl+c`、`esc`）以参数数组调用 Herdr、不经 shell，走有界的
外部调用通道，返回记录的指令 `{command}`。交给 Herdr 的指令都会记录，失败时留下失败或
未确认状态；参数无效、被拒绝或 session 检查未通过的请求不记录。
所有 Herdr 调用显式带配置的 session；插件任务按其自身 session 与 pane ID 关联
（Herdr 不复用 pane ID）。Herdr 版本与 session 运行检查在首次读取前执行；读取
失败时立即重新检查，检查不通过就返回其明确原因（如 session 未运行、版本不兼容），
否则返回读取本身的错误（发送超时、agent 已关闭或正等待确认时不重查）。正常轮询不重复执行 `--version`。

agent 状态没有推送事件，页面打开期间每 2.5 秒轮询列表与选中 agent，上一次读取
结束后才排下一次，离开页面即停止。断线或配置重载时保留最后内容并禁用操作，连接
恢复后重新读取。离开页面只退订视图，后台任务照常运行。后台刷新不会切走当前选择；
终端停在底部时跟随新输出，上翻后保持阅读内容并提示「有新输出」，切换 agent 或
进入新回合会重置。

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
