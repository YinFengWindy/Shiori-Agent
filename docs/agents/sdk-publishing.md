# SDK 发布

SDK 使用同一个版本号发布 `@yinfengwindy/shiori-sdk`（npm）与 `shiori-sdk`（PyPI）。
**3.1.2 已于 2026-10-16 发布**到 [npm](https://www.npmjs.com/package/@yinfengwindy/shiori-sdk)
与 [PyPI](https://pypi.org/project/shiori-sdk/)。[正式发布 run](https://github.com/YinFengWindy/Shiori-Agent/actions/runs/38855118971)
的 build、npm 和 PyPI job 均成功，注册表产物校验和与该次 CI 归档一致。
README 的 3.1.2 安装命令可直接使用。
本批包括后台结果回报、跨代进程资源、外部链接、二级侧栏样式以及 #847 的渠道
push-sender 删除与 `message_push` 异常语义，补丁编号不代表兼容；迁移说明见
[SDK README](../../packages/sdk/README.md#compatibility)。

桌面 v0.5.5 已将 #820/#821/#822/#827 的新增契约以旧版本号 3.1.1 分发，
内容与注册表 3.1.1 不同。3.1.2 统一修正后续分发；不得重写 v0.5.5 / sdk-v3.1.1
标签或覆盖旧注册表产物。`ChannelContext.push_tool` 注册及 `PushSenders` /
`FakePushSenders` 必须移除；角色向渠道发送使用 `account_send`。`message_push` 失败会
抛异常，调用方不再匹配返回文本来判断失败，正常返回表示已发送或已加入当前回合队列。

SDK 大版本是破坏性变更。manifest 写 `api: 4` 和 `sdk` 最低约束。4.x 内不给已有
Key 加方法。没有 Unreleased 批次，也没有 `runtime_api`。正式发布 SDK 前，源版本、
npm 包、宿主和 host-testing 的精确 pin 必须一致。桌面包内置的 SDK 也是已分发契约，
不能因为注册表尚未发布，就继续用已随桌面发出的版本号承载不同源码。4.0.0 尚未发布。

版本唯一来源是 `packages/sdk/python/shiori_sdk/_version.py`。改版本时直接改 npm 包、
`setup.py` 和 host-testing 的 pin，用 `node scripts/check_sdk_release.mjs --align` 核对。
插件的 `shiori-sdk` 依赖要承认这个版本。改了插座契约就运行
`python -m scripts.gen_plugin_api`。已发布历史的最低约束保持不变。

本批插件以最近正式桌面 v0.5.5 为基线，只给有包内容或兼容声明变化的插件升一次 patch：

| 插件 | 本批插件版本 | SDK / Runtime API 最低版本与依据 |
| --- | --- | --- |
| herdr | 0.1.1 | 3.1.2：四项新增接口；0.1.0 已随 v0.5.5 发布 |
| novelai | 0.1.2 | 3.1.2：二级侧栏与 `message_push` 异常迁移 |
| feishu / qq / qqbot / telegram | 各 0.1.2 | 3.1.2：移除渠道 push-sender 注册，并包含本批渠道改动 |
| story | 0.1.2 | 自身 SDK 最低仍为 3.1.0；精确依赖 novelai==0.1.2 |

其他插件未变，不升版本；herdr 的根开发依赖及 uv.lock 同步更新。

工作流为 `.github/workflows/sdk-release.yml`：

- `sdk-vX.Y.Z` 标签触发正式发布，标签版本必须与两个包一致，提交必须在
  `origin/main` 历史中。目前只支持稳定版 `X.Y.Z`。正式 tag 构建前还必须通过
  `node scripts/check_sdk_release.mjs` 的契约定版检查。
- 相关 PR 与手动 `workflow_dispatch` 仅构建验证，不发布。手动运行即使选择标签
  也不会发布。SDK 标签不会匹配桌面安装包的 `v*` 标签。
- build job 使用仓库固定的 pnpm `10.33.0` 打包，确保 `publishConfig.exports`
  把源码入口改为 `dist`。Python 先生成 sdist，再从该 sdist 构建 wheel。
- 现有 smoke 在仓库外安装这次构建的确切产物，验证所有 npm 入口、DOM 测试工具、
  TypeScript 类型和 Python SDK 独立测试。归档校验检查版本、README、MIT 许可证、
  编译入口，并将提交和 SHA-256 写入 `manifest.json`。
- npm 与 PyPI 各有独立发布 job，只有它们拥有 `id-token: write`。它们按 build job
  输出的 artifact ID 下载同一批文件、复核校验和，再通过 OIDC 发布；发布时不重建。

## 契约定版检查

`node scripts/check_sdk_release.mjs` 要求完整 Git 历史与标签，以及 SDK/npm/宿主/host-testing
版本一致。所有稳定 `sdk-vX.Y.Z` 和桌面 `vX.Y.Z` 标签都是不可复用的分发证据，
包括桌面先于注册表发布的情况；历史上尚无统一 SDK 目录的桌面标签明确跳过。
检查拒绝 SDK 版本回退，或与任一同版本标签不同的 SDK 源码。当前 HEAD 上的新标签
可通过，也会继续检查所有旧标签，不能借它掩盖历史冲突。

指纹覆盖 `packages/sdk` 的 Python、renderer、公开 testing helpers、构建脚本和元数据，
排除实际测试、说明文档、缓存和生成目录。只改 README/测试而运行时源码未变可继续
使用已发布 SDK 版本。检查不推断语义兼容性，也不查询注册表，不自动升号。
`node scripts/check_sdk_release.mjs --align` 只核对版本 pin，不读 Git 历史，供 lint 使用。

Windows 的 schedule、tag、manual 三个入口都会在构建前执行；SDK 工作流仅 tag push
执行完整检查。PR 与 workflow_dispatch 仍构建验证，不发布。
Windows 在上传 artifact / 创建或公开 Release 前还会刷新远端标签并重新检查，
防止构建期间另一发布冻结了同版本不同源码；刷新不会改变本次固定的 checkout SHA。
CI checkout 必须保留 `fetch-depth: 0`；本地检查前先获取完整 tags。

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
2. 在已合入的提交上创建并推送 `sdk-v<version>`，将下方占位替换为下一批已定版的新版本：

   ```powershell
   git tag sdk-v<version> <已验证的-main-提交-SHA>
   git push origin sdk-v<version>
   ```

   这是正式发布操作，需要维护者有意执行；`sdk-v3.1.2` 已发布，不要重复创建、挪动或覆盖已发布标签。
3. 两个发布 job 均成功，才算双端发布完成。build artifact 名为
   `sdk-release-<run-id>-<build-attempt>`，保存 30 天，包含 `.tgz`、`.whl`、`.tar.gz`
   和 `manifest.json`。需要长期恢复证据时及时下载保存整份 artifact。
4. **仅首次 npm 包尚不存在时**：npm job 会因尚无 Trusted Publisher 配置而失败。
   从此 tag 的成功 build 下载原始 artifact，切到同一提交并校验，然后交互式发布
   其中的 `.tgz`；不要重新 `pnpm pack`。示例（替换 run、attempt、SHA）：

   ```powershell
   gh run download <run-id> --name sdk-release-<run-id>-<build-attempt> --dir sdk-first-release
   uv run python -m scripts.sdk_release verify sdk-first-release --ref refs/tags/sdk-v3.1.2 --commit <标签提交-SHA>
   npm login
   npm publish ./sdk-first-release/yinfengwindy-shiori-sdk-3.1.2.tgz --access public
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
