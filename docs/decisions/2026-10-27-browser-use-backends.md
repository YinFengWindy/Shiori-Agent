# Browser Use 双后端

关联：[#934](https://github.com/YinFengWindy/Shiori-Agent/issues/934)。用户已确认同一插件全局二选一、默认 agent-browser、ego(lite) 由用户自行安装。

## 决策

- 保留 agent-browser 的固定 MCP 运行组件、角色专属持久配置和原生进程所有权。
- ego 使用官方内嵌 Node 的 TaskSpace/Page 接口，但向模型提供结构化网页操作，避免任意 Node 脚本绕过角色 Space 和输出路径归属。每个任务运行代只操作宿主创建并记录的 Space，支持批量动作、截图和人工交接。
- 两个后端分别暴露工具；配置切换通过既有插件生命周期撤销旧工具和资源，不增加 Agent loop 或设置页面。
- ego 的 Space 分离任务目标，复用用户登录环境，不承诺角色间账号隔离。
- ego 的 GUI 和浏览器子进程属于用户。复用已有 `processes` 能力，在 `spawn` 上增加默认保持兼容的 `own_process_tree` 选项；ego CLI 关闭不会连带结束用户浏览器。
- 取消以浏览器端清理确认为完成条件。仅终止 CLI 后，内嵌脚本仍可能执行；实测取消本任务 Space 可以中止等待中的点击和页面定时器。宿主停止标记约束尚未开始的动作，创建中的 Space 必须交回确认，清理失败则保留停止的运行代。

## 边界

首版仍为 Windows x64。ego 需由用户安装并完成首次设置，不自动安装、升级、迁移登录数据或回退其他后端。实际兼容性依据安装版本的接口能力与本地页面验收，不把上游 main 的 API 视为已发布保证。具体版本与复验命令记录在插件 README 和 TESTING。
