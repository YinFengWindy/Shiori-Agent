# SDK 发布

SDK 使用同一个版本号发布 `@yinfengwindy/shiori-sdk`（npm）与 `shiori-sdk`（PyPI），仓库当前为
`3.1.8`（3.1.1–3.1.8 尚未发布，npm 与 PyPI 最新为 `3.1.0`）。版本来源是 `packages/sdk/python/shiori_sdk/_version.py`；修改后运行
`node scripts/sync_sdk_version.mjs` 同步 npm 元数据。每个修改契约的 PR 只把第三位（patch）升一次，
主版本/次版本只在发布时由维护者决定。

工作流为 `.github/workflows/sdk-release.yml`：

- `sdk-vX.Y.Z` 标签触发正式发布，标签版本必须与两个包一致，提交必须在
  `origin/main` 历史中。目前只支持稳定版 `X.Y.Z`。
- 相关 PR 与手动 `workflow_dispatch` 仅构建验证，不发布。手动运行即使选择标签
  也不会发布。SDK 标签不会匹配桌面安装包的 `v*` 标签。
- build job 使用仓库固定的 pnpm `10.33.0` 打包，确保 `publishConfig.exports`
  把源码入口改为 `dist`。Python 先生成 sdist，再从该 sdist 构建 wheel。
- 现有 smoke 在仓库外安装这次构建的确切产物，验证所有 npm 入口、DOM 测试工具、
  TypeScript 类型和 Python SDK 独立测试。归档校验检查版本、README、MIT 许可证、
  编译入口，并将提交和 SHA-256 写入 `manifest.json`。
- npm 与 PyPI 各有独立发布 job，只有它们拥有 `id-token: write`。它们按 build job
  输出的 artifact ID 下载同一批文件、复核校验和，再通过 OIDC 发布；发布时不重建。

## 首次账号配置

采用 npm 账号 `yinfengwindy` 的个人 scope `@yinfengwindy`，无需创建 npm 组织。
GitHub owner `YinFengWindy` 与 npm scope 分属不同账号系统；Trusted Publisher 的
owner 字段填写 GitHub owner。维护者仍需完成下面的外部设置。

1. 登录 npm 账号 `yinfengwindy`，确认能在个人 scope 公开发布 `@yinfengwindy/shiori-sdk`。
   开启账号要求的 2FA。npm 的 Trusted Publisher 配置要求包已经存在；首次发布
   按下节使用该次 tag 构建的原始 tarball，由拥有者交互式发布。
2. 在 GitHub 仓库创建名为 `npm`、`pypi` 的两个 Environments。若设置部署分支/标签
   规则，允许 **tag** `sdk-v*`；不要只允许分支 `main`。可按团队策略设置审核人。
3. 在 npm 的 `@yinfengwindy/shiori-sdk` 包设置中添加 GitHub Actions Trusted Publisher：

   | 字段 | 值 |
   | --- | --- |
   | Organization or user | `YinFengWindy` |
   | Repository | `Shiori-Agent` |
   | Workflow filename | `sdk-release.yml` |
   | Environment name | `npm` |

   允许该 publisher 直接执行 **`npm publish`**。新 publisher 默认只允许 stage，
   不调整会阻止本工作流直发。包的 `repository.url` 必须保持与此 GitHub 仓库匹配。
   工作流使用 Node `24` 和明确安装的 npm `11.5.1`，满足 OIDC 的 Node `>=22.14`
   与 npm `>=11.5.1` 要求；无需保存 `NPM_TOKEN`。
4. PyPI 首次设置前，完成账号邮箱验证、恢复码确认和两步验证（验证器或安全密钥），才能添加
   publisher；恢复码应保存在个人安全存储中，不写入仓库。在 PyPI 账号的 Publishing
   页面创建 **pending publisher**（包尚不存在时）：

   | 字段 | 值 |
   | --- | --- |
   | PyPI project name | `shiori-sdk` |
   | Owner | `YinFengWindy` |
   | Repository name | `Shiori-Agent` |
   | Workflow name | `sdk-release.yml` |
   | Environment name | `pypi` |

   包已存在时改在项目 Publishing 设置中添加同样的 publisher，并确认账号有该项目权限。
   第一次 OIDC 发布会创建项目；pending publisher 不预留名称。
   工作流使用 `pypa/gh-action-pypi-publish@release/v1`，无需保存 PyPI API token。

官方配置说明：[npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/)、
[PyPI 首次 OIDC 发布](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)、
[PyPI 现有项目配置](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)。

## 常规发版与首次 npm 发布

1. 在功能分支更新 `_version.py`，同步 npm 版本，按需更新 Python 消费方的版本约束，
   运行 `uv lock` 刷新 `uv.lock` 并确认 `uv sync --dev --locked` 可用，按变更更新 README，
   走 PR/CI 后合入 `main`。版本、功能和许可证校验通过后再打标签。可在 Actions 中手动运行 SDK release
   检查构建流程；这只验证产物，不证明外部账号已配置。
2. 在已合入的提交上创建并推送 `sdk-v<version>`。例如发布仓库当前版本：

   ```powershell
   git tag sdk-v3.1.8 <已验证的-main-提交-SHA>
   git push origin sdk-v3.1.8
   ```

   这是正式发布操作，需要维护者有意执行；不要挪动或覆盖已发布标签。
3. 两个发布 job 均成功，才算双端发布完成。build artifact 名为
   `sdk-release-<run-id>-<build-attempt>`，保存 30 天，包含 `.tgz`、`.whl`、`.tar.gz`
   和 `manifest.json`。需要长期恢复证据时及时下载保存整份 artifact。
4. **仅首次 npm 包尚不存在时**：npm job 会因尚无 Trusted Publisher 配置而失败。
   从此 tag 的成功 build 下载原始 artifact，切到同一提交并校验，然后交互式发布
   其中的 `.tgz`；不要重新 `pnpm pack`。示例（替换 run、attempt、SHA）：

   ```powershell
   gh run download <run-id> --name sdk-release-<run-id>-<build-attempt> --dir sdk-first-release
   uv run python -m scripts.sdk_release verify sdk-first-release --ref refs/tags/sdk-v3.1.8 --commit <标签提交-SHA>
   npm login
   npm publish ./sdk-first-release/yinfengwindy-shiori-sdk-3.1.8.tgz --access public
   ```

   手动首次发布使用账号 2FA；本地不加 `--provenance`，后续 GitHub OIDC 发布自动生成
   provenance。随后配置上述 npm Trusted Publisher，重跑原 run 的失败 job；它会校验
   npm 已有版本的内容相同并跳过上传。PyPI 无需手工首次发布。

## 失败恢复

优先使用 GitHub 的 **Re-run failed jobs** 或：

```powershell
gh run rerun <run-id> --failed
```

先修复实际失败原因（账号权限、环境名称、网络或审批），然后重跑原 run。
重跑失败发布 job 会复用成功 build 的 artifact ID，不受新的 `run_attempt` 影响。
不要选择 Re-run all jobs 来修复单边上传失败：重新构建可能因归档时间戳或构建依赖变化
产生不同字节，即使版本号一样也会被拒绝。

- npm 已有相同版本时比较注册表的 SHA-512 integrity；相同则跳过，不同则失败。
- PyPI 比较每个同名文件的 SHA-256；相同文件跳过，只上传缺失的 wheel/sdist。
  同名但不同内容立即失败，不使用 `skip-existing` 掩盖冲突。
- 只有注册表返回 404 才视为版本尚未发布；鉴权、限流和服务器错误直接失败。
- 不同内容冲突需调查来源，不能覆盖远端版本。原 artifact 过期且无法找回原始文件，
  或必须修改已发布代码时，修复后发布新版本，不能对同一版本重新生成包。
- 全 run 重跑是全新的构建尝试，有独立 artifact 名称；若已有部分发布，新的产物
  必须仍与已发布文件完全相同，否则上述冲突保护会停止它。

## 本地验证

现有无参数入口仍可用于本地构建并验证：

```powershell
pnpm run sdk:smoke
uv run python -m scripts.verify_sdk
```

验证现成文件时使用 `pnpm run sdk:smoke --tarball <绝对路径.tgz>` 和
`uv run python -m scripts.verify_sdk --wheel <路径.whl>`。它们不会重建指定产物。
`sdk_release seal/verify` 负责归档与来源校验；`sdk_registry` 只查询注册表并准备待上传
文件，不执行上传。发布 job 无需安装整个宿主或任何插件。
