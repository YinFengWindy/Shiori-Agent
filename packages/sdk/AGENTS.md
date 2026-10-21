# SDK

Python 包 `shiori_sdk` 在 `python/shiori_sdk/`，npm 包 `@yinfengwindy/shiori-sdk` 在 `src/`。版本只有 `python/shiori_sdk/_version.py`，用 `node scripts/sync_sdk_version.mjs` 同步。契约变更写进 `docs/_handbook/plugin-runtime-contract.md` 的 Unreleased 区。

- `shiori_sdk.testing` 是插件 fake，不启动宿主。真实 `AppRuntime` 在 `packages/shiori-host-testing`。
- `external_turns.py` 里的 `FakeExternalTurns` 只记录提交。宿主真实回合在 `tests/support/host_external_turns.py`。
- Python 测试在 `tests/`，镜像 `python/shiori_sdk/`。默认根目录 `pytest` 不收集它们；本包用 `pytest packages/sdk/tests`。CI 在仓库外跑 `python -m scripts.verify_sdk`。改 SDK 时 `scripts/select_tests.py` 还会在默认宿主契约之外收集 SDK 测试和各插件测试。
- **NEVER** 为覆盖率加测试。只补能单独失败的行为契约。**NEVER** 加 mock 接线、提示词子串、构造回声或同义矩阵；优先改已有文件。
- 前端单测与 `src/` 并列，由 `pnpm test` 收集。
