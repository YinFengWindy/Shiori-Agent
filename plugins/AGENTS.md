# 插件

插件代码在 `plugins/<id>/`，不放进 `apps/desktop/src/`。

- Python 测试在 `plugins/<id>/tests/`，只通过 `shiori_sdk.testing` 造假。不要导入 `tests.support`、`shiori_host_testing` 或 `apps/backend`。
- **NEVER** 为覆盖率加测试。只补能单独失败的行为契约。**NEVER** 加 mock 接线、提示词子串、构造回声或同义矩阵；优先改已有文件。宿主默认集是 `tests/support/default_suite.py`；CI 如何加宽见 `scripts/select_tests.py`。
- 真实宿主装配留在 `tests/backend/`。默认根目录 `pytest` 不收集插件测试；本目录用 `pytest plugins/<id>/tests`。仓库外验收是 `python -m scripts.verify_plugin_tests`。
- UI / surface / background 的 `*.test.ts` 由根目录 `pnpm test`（`desktop:test`）收集。
- 契约与版本见 `docs/_handbook/plugin-runtime-contract.md` 和 `docs/agents/plugin-testing.md`。
