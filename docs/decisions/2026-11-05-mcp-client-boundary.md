# SDK 4.1：MCP 客户端归属

状态：2026-11-05 用户确认移除 PROCESSES.mcp，按用户新确认的 A.B.C 规则作为 SDK 4.1 兼容线迁移。承接 #994 / #996 和现有 Draft PR #999；OAuth #997 / #1000 随后迁移。未授权合并或发布 SDK。

## 决策

MCP 是普通进程内插件能力。删除已发布的 PROCESSES.mcp()，SDK 源版本升为 4.1.0。manifest API 仍为 4；SDK 自定义兼容线与 manifest 格式版本分别管理（见 [版本规则](2026-11-05-sdk-version-policy.md)）。此轮不新增 capability、Key、phase 或运行时层。

packages/mcp-client 提供内部 Python 包 shiori-mcp-client：stdio/HTTP 会话、工具发现、协议错误、结果转换与取消/超时归于该库。它依赖固定的官方 MCP Python SDK，不要求公开 PyPI 发布；本地 wheelhouse 与冻结程序消费本次构建的确切产物。

MCP、Browser Use、Computer Use 直接构造库中的会话，并注入现有 PROCESSES.spawn 接口。宿主只提供进程/管道/Windows Job 生命周期；删除宿主 MCP 协议实现及 mcp 工厂，不留转发兼容壳。SDK 中的 MCP 会话/工具信息/错误类型和结果 decoder 迁到该库，相关测试及 test doubles 跟随实现 owner；通用 ToolResult 和进程接口保留在 SDK。

用户 MCP 插件继续独占服务器配置、凭据、OAuth 操作、工具筛选、RPC/UI 和执行准入。Browser/Computer 保留各自的角色、profile、driver 和回合生命周期，不进入用户服务器列表，不依赖用户 MCP 插件开关。proactive 每次解析当前 MCP 插件导出并共用其配置与授权。

工具注册已有 MCP_TOOLS 与调用门继续使用；这次不顺手重做工具注册接口。SDK 兼容线迁移只改变已确认的 MCP 客户端/进程职责，不扩展其他业务范围。

## 会话接口与协议

库暴露 stdio/HTTP 工厂或明确会话类型，均提供 connect/call/disconnect。会话自持 readiness、call deadline 和清理；库不自行重放业务调用。HTTP 注入 URL、headers、可选 auth provider，不依赖 plugins.mcp 的配置模型或 OAuth 存储类。

stdio 管道通过现有 PROCESSES.spawn 创建，官方 Client 管协议协商和请求关联。官方 stdio_client 的自行 spawn 路径不能绕过宿主所有权。管道 adapter 分块读取并保留约 20 MiB 帧预算，无需给通用 spawn 新增协议专用参数。Windows 保留 Job 的子孙进程回收；其他平台使用既有 terminate/wait/kill 路径。

同一个 supervisor task 进入/退出官方 SDK context。保留现有默认调用期限、主动源 poll 180 秒、get 的明确一次 transport retry、poll/ack 不重放；停止后旧调用/迟到连接不得恢复工具。文本、图片、结构化结果及业务 opaque token 语义保持，已知凭据继续在插件边界脱敏。

## SDK 与依赖装配

同步 SDK 4.1.0 的 Python/npm/宿主/host-testing 精确 pin；生成的 API 参考与迁移说明同步更新。三个 MCP 调用者与内部客户端声明 `>=4.1.0,<4.2.0`，其余已核对插件声明 `>=4.0.0,<4.2.0`；manifest 使用空格区间。SDK 变更兼容线不统一提升插件 patch。既有 SDK 4.0 发布物与标签不可改写。此轮只准备源码与构建产物，不推发布标签。

三个客户端插件声明 shiori-mcp-client 依赖。根开发环境、私有 wheelhouse、独立插件验证、宿主分发验证、PyInstaller 收集闭包接入该本地包。不要从公共索引隐式取得同名内部包，不把整套 MCP 插件作为宿主 Python 依赖。

本次不做通用插件依赖安装器，不更换 Python 发行方式、不新增 worker。当前冻结桌面的依赖更新仍随桌面构建；旧桌面独立更新任意 Python 依赖是另项交付能力。

## 验证

先完成真实 stdio + 官方 Client + 宿主 spawn 的最小可行性验证，再迁移调用者；检查握手、分页、大图片、并发关联、取消、断管和进程树清理。将旧 decoder/stdio 行为测试移到拥有实现的包，宿主保留真实装配与进程原语验证。

对 MCP/Browser/Computer、主动源及受影响宿主调用者做定向回归，验证关闭用户 MCP 不影响另外两个插件。HTTP/OAuth 已建立的错误、期限、持久化、重连竞态与撤销失败回归继续守住。

内部库和三个插件在仓库外用确切 wheel 及声明依赖运行；冻结程序实际调用 stdio/HTTP。检查 SDK pins/API、相关类型与 import boundaries。完整本地套件不运行；外部 CI 全部保留。修改后的 PR 需新 CI 与独立审查。
