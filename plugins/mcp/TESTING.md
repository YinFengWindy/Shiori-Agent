# mcp

```bash
uv run python -m pytest plugins/mcp/tests -q
uv run python -m pytest tests/backend/agent/plugin_host/test_mcp_setup.py tests/backend/infra/process/test_mcp_client.py -q
uv run python -m scripts.verify_plugin_tests --plugins mcp --jobs 1
pnpm exec tsc -p plugins/tsconfig.json --noEmit
pnpm exec eslint plugins/mcp
pnpm --filter shiori-desktop build
pnpm exec tsx apps/desktop/tests/plugin-ui/mcpManagement.e2e.ts
```

插件测试验证持久化、失败保留、筛选/停用、一次 transport 重试和取消竞态。宿主测试通过真实 stdio peer 验证聊天/主动源共用工具与重载门。Electron 流程使用独立 workspace/profile，证据位于 `.test-tmp-root/mcp-management-*`；不访问用户服务器。
