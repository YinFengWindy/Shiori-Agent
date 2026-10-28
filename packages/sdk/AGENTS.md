# SDK

Python 包 `shiori_sdk` 在 `python/shiori_sdk/`，npm 包 `@yinfengwindy/shiori-sdk` 在 `src/`。版本只有 `python/shiori_sdk/_version.py`。npm 包和宿主 pin 用 `node scripts/check_sdk_release.mjs --align` 核对。插座契约改了就运行 `python -m scripts.gen_plugin_api`，说明在 `docs/_handbook/plugin-guide.md`。

- `shiori_sdk.testing` 是插件 fake，不启动宿主。真实 `AppRuntime` 在 `packages/shiori-host-testing`。
- `external_turns.py` 里的 `FakeExternalTurns` 只记录提交。宿主真实回合在 `tests/support/host_external_turns.py`。
- Python 测试在 `tests/`，镜像 `python/shiori_sdk/`。默认根目录 `pytest` 不收集它们；本包用 `pytest packages/sdk/tests`。CI 在仓库外跑 `python -m scripts.verify_sdk`。改 SDK 时 `scripts/select_tests.py` 还会在默认宿主契约之外收集 `packages/sdk/tests`。各插件测试仍只在 `plugin-isolation` 里跑。
- **NEVER** 为覆盖率加测试。只补能单独失败的行为契约。**NEVER** 加 mock 接线、提示词子串、构造回声或同义矩阵；优先改已有文件。
- 前端单测与 `src/` 并列，由 `pnpm test` 收集。
