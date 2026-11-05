# MCP 通用接入

状态：需求与三步交付已确认，实施中。总需求 #994；基线 `d8271da8b`。

## 用户行为

MCP 在工作区统一配置，所有角色共享同一份服务器、登录与工具选择。设置的 MCP 插件页管理 stdio 和 Streamable HTTP 服务器，提供增删改、启停、测试、重连、状态诊断、工具筛选与 OAuth 登录/退出。现有 stdio 数据、服务器 ID、工具名保持兼容。

持久配置和连接状态分开：用户保存的服务器即使离线也保留，可继续编辑和删除。界面分别表示启用意图、连接结果、认证状态和异步操作。默认允许全部工具，也可选明确工具集合；空选择集合表示不允许任何工具。显示名可改，服务器 ID 不随之改变。

HTTP 支持匿名、Bearer、自定义请求头和 OAuth。授权在重启后保留；需要人工登录时显示状态，只有用户点击登录才打开系统浏览器。退出清除 Shiori 本地授权，不承诺退出第三方网站的浏览器会话。

范围不包括按角色分配或独立账号、Resources、Prompts、elicitation、按需连接、MCP Tasks、新增逐次审批。Mika 是通用兼容验证场景，不增加专用分支。

## 归属与接口

MCP 插件是服务器配置、认证、连接和执行准入的唯一 owner。用户确认按 [SDK 5 客户端归属修订](2026-11-05-mcp-sdk5-boundary.md) 删除 PROCESSES.mcp，协议客户端进入共享内部库，宿主只托管通用进程；普通插件在进程内运行，不新增 worker。

connect/call/disconnect 的调用行为保持，MCP 专用类型、stdio/HTTP 和结果转换统一归内部客户端库。SDK 5 移除这批协议专用接口及实现，通用 ToolResult、进程启动与工具注册保留；不新增宿主 capability、phase 或层。

UI 通过现有插件 RPC 和状态变化事件操作 registry；管理工具也进入同一 registry。异步连接、测试和登录不占据全局 RPC mutation lane 等待网络，写操作返回可跟踪的 operation。页面保存携带配置修订，防止旧表单覆盖新配置。

配置驱动的 proactive get/poll/ack 通过已有 `DEPENDENCIES` 与 `optional_dependencies: [mcp]` 调用插件导出。每次调用重新获取导出，不缓存跨代对象，不再读取 MCP 私有配置或创建自己的 session。插件自有的公开 API 接受 server、tool、arguments、timeout 和明确的 transport-only retry 选项，返回原有 `str | ToolResult` 并保留异常。主动源自身的 JSON/event 解码仍归 proactive。

不直接用 `PROACTIVE_HOST.run_host_tool` 代替固定信息源调用：它文本化异常且没有 timeout 参数，会丢失来源错误和 poll 语义。模型主动工具与 Drift 仍使用现有宿主工具执行链。

所有实际调用共同经过 registry 的启停、工具筛选、连接修订与准入检查。动态 wrapper 不永久持有裸 session。公开 API 和动态工具都必须加入有效的在途统计与重载准入；`active` 标志不是 drain 期间的完整调用门。优先复用现有已登记工具的调用门，补齐现有 MCP 登记入口的 owner 关联如确有必要，不另造一套宿主生命周期。

## 配置、凭据与迁移

保留 `plugin-data/mcp/mcp_servers.json`，增加明确 schema 版本。配置记录服务器稳定键、显示名、enabled、transport、工具选择、凭据引用和修订；连接对象和错误不作为持久配置来源。

旧 `{servers: {name: {command, env, cwd}}}` 幂等迁为 stdio、enabled、all-tools，保留 ID/argv/cwd，不依赖连接成功。损坏 JSON 或迁移写入失败保留原数据并报告错误，不按空配置覆盖。不生成带明文凭据的普通备份。

初版沿用项目已有的插件私有凭据文件模式：原子写入、POSIX 私有权限、Windows 用户目录权限。它是本机明文持久化，不是系统密钥库加密。普通配置只持有引用，读取 RPC 只报告已配置状态。凭据编辑明确区分 keep/replace/delete，空输入不隐式清除旧值。

新凭据先写入新记录，再原子提交配置引用；失败时旧配置和凭据仍有效。OAuth 保存 token、client registration 和绝对过期时间，重启不得重置 token 剩余寿命。每个服务器串行刷新，退出或修改 endpoint 后旧认证版本的回调/刷新结果不得写入。

界面、模型错误和日志不回显秘密。stdio 命令、stderr、HTTP body 与 SDK 异常链不能未经处理进入诊断。复用已有脱敏工具并覆盖已知凭据的实际出口，不只依赖凭据名称正则。保留旧 command/env 的输入兼容，敏感内容通过替换操作编辑。

## 操作与生命周期

保存先持久化意图，再异步连接。连接参数变化后旧连接不再接收新调用；新连接失败保持新配置与错误，不自动退回旧 endpoint 或身份。只改标签或工具筛选无需重连。

连接、测试与认证结果绑定服务器修订、连接版本和认证版本。全部工具发现完成后再发布注册；失败撤销本批工具并清理候选 session。停用/删除先关闭调用准入，再取消插件拥有的操作与连接，迟到结果不能复活服务器。取消不代表远端副作用回滚，不自动重放写调用。

启动/启用仍主动连接。测试只执行 initialize/tools/list，不执行工具、不改变启用状态、不注册临时工具。正常调用不偷偷变成首次懒连接。

固定 source 的 get 保留明确 transport failure 后的一次重连重试；poll/ack 不重放，poll 保留 180 秒。每次重试重新验证服务器和工具准入。

setup 先装配，使用已有发布通知启动连接，候选代不得提前打开进程/浏览器或写入配置。`RUNTIME.on_drain` 只等待已接受工作，可重复调用；清理放 `ctx.effect`。不得为了重载缩短正常 poll；若宿主有界 drain 超时，保留旧实例并报告。日常服务器管理不触发整插件重载。

HTTP SDK 的 context manager 由同一个 supervisor task 进入和退出，避免 AnyIO 跨任务退出。OAuth callback 仅绑定 loopback，有期限并随取消关闭；验证 state/issuer、PKCE、令牌刷新由官方 provider 负责。后台授权缺失只返回需要登录。

## 分步交付与验证

1. stdio 管理页、配置迁移、工具筛选、诊断及聊天/主动源统一调用。
2. HTTP、Bearer/headers、共用 decoder、协议兼容与依赖打包。
3. OAuth 登录、刷新、退出与持久化。

每步都是可独立验收的用户行为，分别形成关联总需求的 Issue 和 PR。需求及拆分已经确认；尚未授权合并。

使用 focused 行为回归：离线配置保留、权限/筛选、旧引用失效、取消和资源清理、正常与失败重载；真实本地 stdio/HTTP/OAuth fixture 验证分页、JSON/SSE、图片/结构化结果、PKCE/state、刷新轮换和退出竞态。UI 做操作、焦点与状态验证，运行相关类型/lint/构建检查，不为覆盖率添加测试或自动跑全仓本地测试。必需 CI 保留。

Mika 实机和真实第三方 OAuth 与 fixture 验收分别记录；没有设备或账户时明确未验证，不声称通过。

相似 Issue 检索一次完成：#905 插件化与 #339 stdio/多模态均为已完成基础；未找到同范围远程接入/OAuth/管理任务。
