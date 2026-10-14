# Herdr

需要 Herdr 0.9.4 或以上版本。启用后在插件设置填写 Herdr 可执行文件与明确的本机 session。Herdr 和选定的
Codex / Claude Code 必须已安装、登录，并在该 session 可使用；插件不安装 CLI、
修改全局设置或连接用户当前聚焦的 session。首版只提供 Full Access。

聊天工具 `herdr_start_task` 接收仓库根目录、完整需求及可选的 `codex` / `claude`，
立即返回任务编号，在独立 worktree 中修改、验证、提交并创建 Draft PR。
结果回到原角色与原聊天。角色或用户绑定失效时不会向另一个目标投递。

Herdr 的终端状态和交付状态独立：idle/done 不代表完成，CLI 超时也不代表停止。
插件核验本回合结果文件、代码提交、实际执行验证命令和开放 Draft PR 的 head SHA。
不会自动重发可能已经接收的任务，不会合并 PR 或删除 worktree。

仅当前 Shiori 运行期间追踪。关闭 Shiori 后 Herdr 任务可能继续运行，插件不恢复
旧追踪记录；初始化、登录或交互请求会作为 blocked 回报，并保留终端和产物。
任务文件与 worktree 位于插件私有数据目录，完整需求保存在 UTF-8 文件中。

此插件依赖当前开发批次 Unreleased 的 `background_results` SDK 契约；正式发布前
需按仓库统一定版流程更新 SDK/Runtime API 最低版本。
