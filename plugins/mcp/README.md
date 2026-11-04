# MCP

连接工作区统一配置的 stdio 与 Streamable HTTP MCP 服务器，工具名称保持 `mcp_<server>__<tool>`。所有角色与主动信息源共享连接和工具选择，stdio 进程由宿主拉起和回收。

## 管理服务器

在「设置 → 插件」启用 MCP，打开「MCP 设置」。服务器可以添加、编辑、启停、测试连接、重连和删除。服务器 ID 不随显示名变化；保存后异步连接，失败记录仍可编辑和删除。测试仅初始化和发现工具，不调用业务工具。

启动命令使用 JSON 字符串数组，例如 `["python", "/path/to/server.py"]`；环境变量使用 JSON 字符串对象。已保存的 argv/env 不回显，修改时明确选择保留、替换或清空。工作目录可选。

HTTP 服务器填写完整 http(s) 地址，支持匿名、Bearer 或自定义请求头认证。请求头使用 JSON 字符串对象。完整地址（包括 query）、token 和请求头值均不从读取接口回显，编辑时选择保留或替换；请求头可清空。地址不接受 userinfo/fragment，请求头拒绝换行、重复名称及协议保留头；自定义 Authorization 只能选择「自定义请求头」认证，不能与 Bearer 混用。连接失败保留配置，401/403 显示对应状态码。

HTTP 使用官方 `mcp==2.3.0`，支持分页发现、JSON/SSE、文本、图片和对象 structuredContent，并与 stdio 共用 SDK 结果转换。现代协议的数组、标量或显式 null structuredContent 以 JSON 文本呈现，已有等价文本不重复追加；`ToolResult.structured_content` 仍只保存对象。工具调用不自动处理 elicitation、扩展结果或重发，OAuth 尚未交付。

OAuth 在服务器行提供登录、取消、刷新授权和退出登录。只有当前页面点击登录才通过宿主打开系统浏览器；启动或后台刷新需要交互时显示「需要登录」。支持自动客户端注册（DCR）和预注册 Client ID，客户端认证可选 none、client_secret_basic、client_secret_post。预注册配置输入 Client secret 与固定回调端口，默认回调地址为 `http://127.0.0.1:43819/callback`；端口被占用时登录失败，可在「配置客户端」里修改并同步更新授权服务器注册。回调只绑定本机 loopback，登录最长等待 180 秒。退出只清除本地令牌，不退出浏览器中的第三方账号。

工具默认全部允许，也可勾选指定工具；空选择表示全部禁止。停用、删除或取消工具选择立即阻止后续调用，包括旧工具引用。取消不会撤销远端已经发生的副作用。

| 工具 | 作用 |
|---|---|
| `mcp_add` | 保存 stdio 服务器并尝试连接；连接失败仍保留配置 |
| `mcp_remove` | 删除已连接或离线服务器并回收连接 |
| `mcp_list` | 列出保存的服务器、状态和当前可用工具 |

## 存储与升级

配置保存在 `<workspace>/plugin-data/mcp/mcp_servers.json`，schema v2 记录稳定 ID、修订、启用意图、工具选择和凭据引用。argv/env、完整 HTTP 地址、Bearer 和请求头保存在同目录的 `credentials/` 私有文件。它们是本机明文，不是系统密钥库加密；POSIX 使用私有权限，Windows 继承用户目录权限。OAuth 的 token、客户端注册、绝对过期时间及已验证授权服务器元数据保存在 `credentials/oauth/`；重启保留实际剩余寿命，外部授权服务器刷新使用原 token endpoint。连接和测试共享同一 provider 的刷新锁；取消、退出、停用或 endpoint 修改使旧认证版本失效，迟到结果不能恢复授权。配置及凭据采用原子写入，读取接口、工具错误与日志不输出秘密值。

旧 `{servers: {name: {command, env, cwd}}}` 自动迁为 stdio、启用和全部工具，保留 ID、argv、env、cwd，迁移不依赖连接成功；损坏文件保留并报告。旧工作区根目录文件仍由启动迁移搬入插件目录。已有服务器且 `[plugins.mcp]` 未显式配置 enabled 时，启动迁移启用插件；显式设置不变。

proactive 不再读取 MCP 私有文件或自行建立会话，只经声明的可选依赖获取当前 MCP 导出。get 可以在明确传输失败后重试一次，poll/ack 不自动重放，poll 保留 180 秒。关闭一个角色的主动循环不会关闭其他角色使用的共享连接。

## 插件关闭

动态工具和管理工具移除，连接与待完成操作关闭，配置保留。重载等待已接受的工具调用；有界排空超时则保留旧实例。HTTP session 的 context 由同一个 task 进入和退出，清理会话不会重放业务调用。
