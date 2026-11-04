# mcp

```bash
uv run python -m pytest plugins/mcp/tests -q
uv run python -m pytest tests/backend/agent/plugin_host/test_mcp_setup.py tests/backend/infra/process/test_mcp_client.py -q
uv run python -m scripts.verify_plugin_tests --plugins mcp --jobs 1
pnpm exec tsc -p plugins/tsconfig.json --noEmit
pnpm exec eslint plugins/mcp
pnpm --filter shiori-desktop build
pnpm exec tsx apps/desktop/tests/plugin-ui/mcpManagement.e2e.ts
pnpm exec tsx apps/desktop/tests/plugin-ui/mcpHttpManagement.e2e.ts
pnpm exec tsx apps/desktop/tests/plugin-ui/mcpOAuthManagement.e2e.ts
```

插件测试验证持久化、失败保留、筛选/停用、一次 transport 重试和取消竞态。宿主测试通过真实 stdio peer 验证聊天/主动源共用工具与重载门。Electron 流程使用独立 workspace/profile，证据位于 `.test-tmp-root/mcp-management-*`；不访问用户服务器。

OAuth 测试使用真实 TCP 的独立 MCP/授权服务器，验证 DCR、预注册 Basic/Post、PKCE/state/issuer 拒绝、绝对过期时间、刷新轮换、外部 token endpoint、取消/退出/endpoint 修改竞态与凭据脱敏。Electron OAuth 验收使用独立 workspace/profile，真实登录、取消、刷新、重启与退出按钮；`shell.openExternal` 由 fixture HTTP 浏览器替代，证据在 `.test-tmp-root/mcp-oauth-management-*`。这些结果不等于真实第三方账号或系统浏览器手工验收。

## 开发与冻结依赖检查

安装仓库 development requirements 或执行 `uv sync --dev --locked`；两条入口均安装本插件，运行依赖以插件 `pyproject.toml` 为准。不要用单独安装 `mcp` 代替正式依赖装配验证。

`node apps/desktop/scripts/test-mcp-runtime.mjs` 通过正式运行时参数生成器冻结 MCP 后端，再从生成的可执行程序发现并调用 loopback HTTP 工具，同时检查依赖元数据。它不启动其他插件的运行时。`--python` 可指定全新开发环境解释器，`--output` 指定构建与验收证据目录。Windows CI 保留此回归。
