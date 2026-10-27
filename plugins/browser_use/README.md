# Browser Use

Windows x64 原生 v2 插件，在插件设置中全局选择 `agent-browser`（默认）或 `ego(lite)`。没有后端字段的旧配置继续使用 agent-browser。只注册所选后端的工具，保存配置或停用时撤销旧工具并清理对应任务。

## agent-browser

使用 agent-browser 0.38.2 与 Chrome for Testing 153.0.8010.52。版本、固定下载地址、SHA256 与许可来源记录于 `native-runtime.json`；发行资源同时包含 Apache 许可和 Chrome 原版 ABOUT，Chrome 的第三方许可可在 `chrome://credits` 查看。

开发环境在仓库根执行 `pnpm prepare:browser-use`，使用根目录 `.venv` 解压固定浏览器，无需全局 npm 或系统 Python。Windows 发行版构建会执行同一准备流程，并收集到 PyInstaller `native/browser-use/`。缺失资源和非 Windows 平台在首次调用时明确报错；普通单测不下载也不启动原生程序。

“显示浏览器窗口（agent-browser）”只控制此后端；单次操作超时对两个后端生效。启用只注册可发现工具，第一次操作时才启动浏览器。网页操作由当前角色决策，原图通过 ToolResult 进入当前模型下一次请求。

每个角色使用 `workspace/plugin-data/browser_use/profiles/<角色身份SHA256>/`；不同角色有独立浏览器。对同一角色的动作串行执行，配置目录以操作系统文件锁跨进程独占。正常关闭保存站点状态；取消或超时会立即终止该运行代，已排队动作不再执行。截图保存于同一插件数据目录下的 `screenshots/`（每运行代一张最新图，保留至用户清理插件数据）。模型不能指定 session、namespace、启动参数或输出路径，也不能接管日常浏览器。

原生进程以挂起状态创建，加入专用 Windows Job 后再运行；宿主异常退出时系统关闭 Job，回收 MCP、CLI、daemon 与 Chrome。正常退出先由当前会话关闭浏览器，再回收两个 Job，最后释放 profile 锁。IPC 文件在插件 `run/` 目录，daemon 日志在角色 profile；namespace 由 Shiori workspace 身份派生，运行代 session 随机且不采用历史会话。

固定版 Windows CLI 自动启动的 daemon 依赖一次性父进程的输出句柄（[#1407](https://github.com/vercel-labs/agent-browser/issues/1407)）。实测 `tab close` 已关闭页面，却在 Windows stderr 失效后丢失首个响应，CLI 重试又报告目标不存在。插件改为直接启动该固定 binary 的官方 daemon 入口，持续持有有效日志文件，MCP 冷启动和关闭标签页均通过真实验证。`daemon.py` 记录固定版本启动指纹及其字段；原生版本升级必须重新验收该契约。图像响应的 stdio 行上限为 20 MiB，覆盖上游 10 MiB 原图的 Base64 和 JSON 元数据。

[#636](https://github.com/YinFengWindy/Shiori-Agent/issues/636) 的后续超时来自 agent-browser 0.38.1 未持续读取 Chrome 自身的 stderr 管道；日志填满管道后，Chrome 的同步日志写入会阻塞 CDP 操作。上游 [PR #2003](https://github.com/vercel-labs/agent-browser/pull/2003) 修复了该管道的持续排空，已包含于固定的 0.38.2。升级保留现有 daemon 所有权、超时和取消逻辑；真实 Windows 验收覆盖完整页面交互，以及取消后第三运行代的打开与标签页关闭，详见 `TESTING.md`。

工具 schema 来自固定版真实 `mcp --tools core` 的 tools/list，移除宿主管理字段及纯诊断 profiles 工具。页面交互先 snapshot 获取引用，导航和引用失效后重新观察；标签页先 list 获取实际身份。

## ego(lite)

由用户安装并完成 ego 的首次设置。插件依次使用显式配置的 `ego-browser 路径`、PATH 中的 `ego-browser.exe`，或 Windows 默认的 `~/.local/share/ego/active_version_dir/ego-browser.exe`。显式路径错误直接报错；不会改用另一个后端、自动安装或升级，也不会导入浏览器数据。

实际验收版本：ego-browser / ego 应用 **0.6.1.13**，Chromium **156.0.8078.48**，内嵌 Node **v24.22.1**，`ego-browser skill` 指南 **v2.1.0**。使用其 TaskSpace/Page 接口；旧版本缺少该接口时明确报错。ego 自己的窗口行为不受 agent-browser 的显示开关控制。

每个角色的任务 Space 使用工作区身份、角色身份和随机运行代命名，操作串行执行。Space 分离操作目标，不代表隔离登录账号；ego 模式复用用户在 ego 中的登录环境。页面标签由当前 Space 返回，模型不能选择其他 Space、profile、运行脚本或文件路径。

ego 提供独立的 `ego_browser_open/snapshot/actions/tabs/screenshot/handoff/resume/close` 工具。`actions` 为 1–32 个结构化页面动作，保留批量执行并返回最后的快照；不开放任意 Node 脚本。人工登录或验证时使用 handoff，用户确认完成后使用 resume。PNG 截图进入现有 ToolResult 图片块。

CLI 只负责向浏览器内嵌 Node 提交任务，结束 CLI **不能**停止已提交的脚本。取消和超时先写入运行代停止标记，阻止未开始的动作；随后等待本角色 Space 的关闭确认，最后回收 CLI。启动中的 Space 必须完成创建/取消确认后才能释放运行代。清理失败保留停止状态并报错，不允许新动作绕过失败的清理。用户已接管的任务保留给用户，其他角色和浏览器整体也保留。

0.6.1.13 的 helper 没有统一超时错误码：部分等待返回普通 `Error`，元素等待耗尽返回 `ElementResolutionError(kind="transient")`。插件保留结构化错误字段，仅允许已知的永久元素定位错误、无效参数和用户接管信号继续使用原 Space；其他错误及 `mayHaveLateEffects=true` / `executionStopped=false` 都结束运行代。分类不依赖错误消息文本，过期引用可重新 snapshot 后继续。

执行脚本、确认状态及最新截图位于插件数据目录的 `ego/<角色身份SHA256>/<运行代>/`。已确认完成的单次请求脚本/结果会清理，无法确认的请求保留用于诊断。进程 API 只拥有 CLI，不将用户的 ego 浏览器及其子进程纳入 Windows Job。
