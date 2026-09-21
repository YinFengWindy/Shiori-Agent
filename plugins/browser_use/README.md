# Browser Use

Windows x64 原生 v2 插件，使用 agent-browser 0.38.1 与 Chrome for Testing 153.0.8010.52。版本、固定下载地址、SHA256 与许可来源记录于 `native-runtime.json`；发行资源同时包含 Apache 许可和 Chrome 原版 ABOUT，Chrome 的第三方许可可在 `chrome://credits` 查看。

开发环境在仓库根执行 `pnpm prepare:browser-use`，使用根目录 `.venv` 解压固定浏览器，无需全局 npm 或系统 Python。Windows 发行版构建会执行同一准备流程，并收集到 PyInstaller `native/browser-use/`。缺失资源和非 Windows 平台在首次调用时明确报错；普通单测不下载也不启动原生程序。

插件管理中可单独启停，配置项为“显示浏览器窗口”和单次操作超时。启用只注册可发现工具，第一次操作时才启动浏览器。没有第二个 Agent：网页操作由当前角色决策，MCP 原图通过 ToolResult 进入当前模型下一次请求。

每个角色使用 `workspace/plugin-data/browser_use/profiles/<角色身份SHA256>/`；不同角色有独立浏览器。对同一角色的动作串行执行，配置目录以操作系统文件锁跨进程独占。正常关闭保存站点状态；取消或超时会立即终止该运行代，已排队动作不再执行。截图保存于同一插件数据目录下的 `screenshots/`（每运行代一张最新图，保留至用户清理插件数据）。模型不能指定 session、namespace、启动参数或输出路径，也不能接管日常浏览器。

原生进程以挂起状态创建，加入专用 Windows Job 后再运行；宿主异常退出时系统关闭 Job，回收 MCP、CLI、daemon 与 Chrome。正常退出先由当前会话关闭浏览器，再回收两个 Job，最后释放 profile 锁。IPC 文件在插件 `run/` 目录，daemon 日志在角色 profile；namespace 由 Shiori workspace 身份派生，运行代 session 随机且不采用历史会话。

固定版 Windows CLI 自动启动的 daemon 依赖一次性父进程的输出句柄（[#1407](https://github.com/vercel-labs/agent-browser/issues/1407)）。实测 `tab close` 已关闭页面，却在 Windows stderr 失效后丢失首个响应，CLI 重试又报告目标不存在。插件改为直接启动该固定 binary 的官方 daemon 入口，持续持有有效日志文件，MCP 冷启动和关闭标签页均通过真实验证。`daemon.py` 记录固定版本启动指纹及其字段；原生版本升级必须重新验收该契约。图像响应的 stdio 行上限为 20 MiB，覆盖上游 10 MiB 原图的 Base64 和 JSON 元数据。

工具 schema 来自固定版真实 `mcp --tools core` 的 tools/list，移除宿主管理字段及纯诊断 profiles 工具。页面交互先 snapshot 获取引用，导航和引用失效后重新观察；标签页先 list 获取实际身份。
