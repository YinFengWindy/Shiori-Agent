# Windows 发版

每日自动发版已暂停。`.github/workflows/windows-release.yml` 的 `schedule`
（每天北京时间 12:00 / UTC 04:00 检查 `main`）在插件系统重构 P1–P8 期间关掉
（D26，见
[`docs/decisions/2026-10-22-plugin-system-four-layer-refactor.md`](../decisions/2026-10-22-plugin-system-four-layer-refactor.md)）。
`workflow_dispatch` 和推送 `v*` 标签仍然会构建。恢复自动发版前不要重新打开这段
cron。GitHub 定时任务只在默认分支生效，排队可能延迟。

## 自动发布规则

- 初始基线是 `v0.5.0` 标签实际指向的提交；已有同名草稿保留，不自动公开。
- 之后以版本号最高的正式桌面 Release 对应标签为成功基线。SDK 标签、预发布
  Release 和预发布标签不参与成功基线选择；草稿或单独标签不会推进基线。
- 完整历史中的 `git rev-list --count <基线SHA>..<本次SHA>` 统计所有新增可达
  commit，包括 merge commit。0–4 个跳过，累计到 5 个或以上才发布。
- 自动版本十进位递增：`0.5.0 → 0.5.1`、`0.5.9 → 0.6.0`、`0.9.9 → 1.0.0`。
  minor、patch 已超过 9 的人工版本会明确报错，需维护者解决版本规则冲突。
- 同一固定 SHA 用于构建、tag 和 Release；构建时传入 `SHIORI_RELEASE_VERSION`，
  不修改 `main` 的 `package.json`。构建期间 main 新增的提交留给下一版。

所有 schedule、tag 与 manual 入口在构建前运行 `node scripts/check_sdk_release.mjs`：
要求 SDK 版本同步且 Unreleased 已清空，拒绝复用任何 SDK/桌面稳定标签已分发的
同版本不同 SDK 源码或回退版本。新契约必须先人工定版；不会自动升 SDK 号。
README/实际测试变化不算 SDK 源码变化，宿主侧契约由 Unreleased 记录保护；
上传 artifact / 创建或公开 Release 前刷新标签再检查一次，固定构建 SHA 不变，
防止构建期间出现新的同版本分发冲突。
详细规则见 [SDK 发布](sdk-publishing.md#契约定版检查)。

后端 release 检查、桌面类型检查及单测、打包测试、Windows 构建、布局校验、
更新元数据和 SHA256SUMS 校验全部保留。上传 Actions artifact 后，自动流程创建
私有草稿、上传所有顶层制品，并核对 GitHub 返回的大小和 SHA256。发布前再次
检查正式基线、草稿归属和 tag SHA，最后公开为 stable / latest Release。

Release 说明由 `daily-release-notes.mjs` 把 GitHub `generate-notes` 的 PR 列表
转成中文：按 PR 标题类型分为「新增」（feat）、「修复」（fix）、「改进」
（style / refactor / perf），每条只保留描述与 PR 编号；`site` scope、其他类型和
无 Conventional Commit 前缀的标题不列出，没有可列条目时写一句内部维护说明。
隐藏来源标记始终位于说明开头。

Windows installer 使用 `${productName}-Setup-${version}.${ext}` 命名，例如
`Shiori-Setup-0.5.1.exe`；blockmap、更新元数据和校验清单沿用同一个名称。
自动发布在上传前拒绝含空格或其他不安全字符的文件名，避免 GitHub 重命名
制品后导致下载路径或校验清单失配。

## 失败恢复与冲突

所有 Windows 发版入口共用 concurrency 队列，不取消进行中的发版。检查和构建
失败不会创建新版本；上传失败只留下带隐藏来源标记的自动草稿。下一次定时检查
恢复这个草稿固定的 SHA，重新构建并替换其未公开制品（包含中断上传）；即使
main 已前进，也不会改变草稿来源。重跑同一 SHA 可能产生不同字节，因此允许
替换自动草稿制品，正式版始终不覆盖。

tag 在全部上传核验成功后才创建。若创建 tag 后公开失败，该 tag 和自动草稿可
继续恢复，成功基线仍不变。公开请求已成功但客户端没有收到响应时，重试识别
同一来源的正式版本并跳过。手动草稿、来源不匹配的 tag、基线变化和 GitHub API
错误会停止任务并保留现场；不要移动已有正式版本 tag 来消除冲突。

计划 job 与发布 job 的日志 / Summary 显示版本、固定 SHA、累计数量与跳过原因。
可在 Actions 重跑失败的定时任务；也可以等待下一次检查。定时任务使用仓库的
`GITHUB_TOKEN` 和 `contents: write` 权限，不需要 PAT，也不依赖推 tag 再触发工作流。

## 手动入口与验证

- `workflow_dispatch` 保持已有行为：从分支执行只构建并上传 Actions artifact；
  从 `v*` 标签执行仍生成草稿。
- 推送 `v*` 标签仍按标签版本构建并创建草稿，不自动公开。SDK 的正式标签发布也使用同一契约检查，SDK PR/手动构建仅验证产物。
- `pnpm --filter shiori-desktop run test:package` 包含调度、Git 历史、GitHub 边界、
  上传恢复和版本进位测试，在 PR CI 与 Windows release 中均执行。测试不发布
  真实 tag / Release。构建和布局通过不等同于真实 Windows 安装、升级、卸载验收。
