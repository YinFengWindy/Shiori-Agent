# mcp

```bash
uv run python -m pytest plugins/mcp/tests -q
uv run python -m pytest packages/mcp-client/tests -q
uv run python -m pytest tests/backend/agent/plugin_host/test_mcp_setup.py -q
uv run python -m scripts.verify_plugin_tests --plugins mcp --jobs 1
pnpm exec tsc -p plugins/tsconfig.json --noEmit
pnpm exec eslint plugins/mcp
pnpm --filter shiori-desktop build
pnpm exec tsx apps/desktop/tests/plugin-ui/mcpManagement.e2e.ts
```

插件测试验证持久化、失败保留、筛选/停用、一次 transport 重试和取消竞态。宿主测试通过真实 stdio peer 验证聊天/主动源共用工具与重载门。Electron 流程使用独立 workspace/profile，证据位于 `.test-tmp-root/mcp-management-*`；不访问用户服务器。

## 开发与冻结依赖检查

安装仓库 development requirements 或执行 `uv sync --dev --locked`；两条入口均安装本插件，运行依赖以插件 `pyproject.toml` 为准。内部 `shiori-mcp-client` 0.1.0（`packages/mcp-client/src/shiori_mcp_client`）统一提供 stdio/HTTP 会话与 decoder；MCP 插件要求 SDK 4.1.0。仓库外测试的私有 wheelhouse 必须包含这次构建的 SDK、客户端库与插件 wheel，不能从公共索引隐式取得同名内部包，也不能用单独安装 `mcp` 代替正式依赖装配验证。

`node apps/desktop/scripts/test-mcp-runtime.mjs` 通过正式运行时参数生成器冻结 MCP 后端，再从生成的可执行程序发现并调用 loopback HTTP 工具，同时检查依赖元数据。它不启动其他插件的运行时。`--python` 可指定全新开发环境解释器，`--output` 指定构建与验收证据目录。Windows CI 保留此回归。
