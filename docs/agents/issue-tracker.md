# Issue Tracker：GitHub

本仓库的任务与 PRD 使用 GitHub Issues 管理。所有操作均使用 `gh` CLI。

## 操作约定

- **创建 Issue**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **读取 Issue**：`gh issue view <number> --comments`，使用 `jq` 过滤评论并同时获取标签。
- **列出 Issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需使用 `--label` 和 `--state` 过滤。
- **评论 Issue**：`gh issue comment <number> --body "..."`
- **添加或移除标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭 Issue**：`gh issue close <number> --comment "..."`

通过 `git remote -v` 推断仓库；在仓库克隆目录内运行时，`gh` 会自动完成此操作。

## 是否将 Pull Request 纳入分诊

**PRs as a request surface: no.** _（如果本仓库将外部 PR 视为功能请求，可改为 `yes`；`/triage` 会读取此标记。）_

设为 `yes` 时，PR 使用与 Issue 相同的标签和状态，并改用对应的 `gh pr` 命令：

- **读取 PR**：`gh pr view <number> --comments`，并用 `gh pr diff <number>` 查看差异。
- **列出待分诊的外部 PR**：运行 `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，仅保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的条目，排除 `OWNER`、`MEMBER` 和 `COLLABORATOR`。
- **评论、修改标签或关闭**：使用 `gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 的 Issue 与 PR 共用编号空间，因此单独的 `#42` 可能指向任意一种。先运行 `gh pr view 42`，失败后再运行 `gh issue view 42`。

## Skill 要求“发布到 issue tracker”时

创建一个 GitHub Issue。

## Skill 要求“获取相关 ticket”时

运行 `gh issue view <number> --comments`。

## Wayfinder 操作约定

供 `/wayfinder` 使用。**地图**是一个单独的 Issue，**子 Issue** 作为具体 ticket。

- **地图**：单独的 Issue，使用 `wayfinder:map` 标签，正文保存 Notes、Decisions-so-far 与 Fog。创建命令为 `gh issue create --label wayfinder:map`。
- **子 ticket**：通过 GitHub 子 Issue 接口（使用 `gh api` 调用 sub-issues endpoint）关联到地图。若仓库未启用子 Issue，则把子 ticket 加入地图正文的任务列表，并在子 ticket 正文顶部写入 `Part of #<map>`。标签使用 `wayfinder:<type>`，其中类型为 `research`、`prototype`、`grilling` 或 `task`。认领后，将 ticket 指派给当前负责开发者。
- **阻塞关系**：优先使用 GitHub 原生 Issue dependencies，以获得规范且界面可见的依赖关系。使用 `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 添加依赖，其中 `<blocker-db-id>` 是阻塞 Issue 的数字 **database id**，通过 `gh api repos/<owner>/<repo>/issues/<n> --jq .id` 获取，不能使用 `#number` 或 `node_id`。GitHub 通过 `issue_dependencies_summary.blocked_by` 报告仍开启的阻塞项。若依赖功能不可用，则在子 ticket 正文顶部使用 `Blocked by: #<n>, #<n>`。所有阻塞项关闭后，ticket 才视为解除阻塞。
- **查询可执行前沿**：列出地图下所有开启的子 Issue（`gh issue list --state open`，范围限制在地图的子 Issue 或任务列表），排除仍有开启阻塞项（`issue_dependencies_summary.blocked_by > 0`，或 `Blocked by` 行中存在未关闭 Issue）或已有负责人者，按地图顺序选择第一个。
- **认领**：运行 `gh issue edit <n> --add-assignee @me`，这是会话中的首次写操作。
- **解决**：依次运行 `gh issue comment <n> --body "<answer>"` 和 `gh issue close <n>`，再把上下文指针（gist 与链接）追加到地图的 Decisions-so-far。
