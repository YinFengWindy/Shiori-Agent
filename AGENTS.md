# AGENTS.md

## 任务完成要求

- 在任务被视为完成之前，默认只运行并要求通过当轮对话实际修改范围内的相关测试；仅在用户明确要求、或改动已影响到更大范围时，再做全量回归。

## 项目概览

- Shiori 是一个以角色为基底进行角色扮演的 Agent 助手，以 Akashic 为 Agent 基座。

## 工作原则

- 长期可维护性优先于局部省事。
- 新增功能前先看能否抽出可复用的共享逻辑。
- 避免在多个文件重复实现同一逻辑。
- 同一段“调用外部接口 -> 刷新本地状态 -> 同步派生状态/提示/导航”的流程，出现第 2 次时就应抽成共享 helper / hook，不要等到第 3 次。
- 不要为了赶进度在局部补丁式绕过问题，优先修正根因。
- 尽量失败即停，不要写不必要的 fallback。
- 业务层不要吞错；让异常尽早冒泡，必要时只在边界层处理。
- 优先直接调用 owning module 或 service，不要无意义地加一层抽象。

## 文件与模块边界

- 页面入口、`main.tsx`、`page.tsx`、顶层容器组件默认只做状态装配、依赖拼接和视图分发，不要继续堆业务细节。
- 桥接事件、会话切换、搜索索引、角色 CRUD、素材管理、图片预览、导航历史这类职责必须分散到独立 hook / module，不能长期共存于同一入口文件。
- 一个文件同时承担 3 类及以上职责时，必须拆分；不要以“还能读”作为不拆的理由。
- 超过 600 行的业务文件视为需要强制评估拆分；超过 800 行时，若不是纯数据/生成文件，默认应继续拆到合理边界。
- 超过 120 行的 hook / service / 组件，如果内部还能明显分出独立子职责，应继续拆分，不要把大文件问题从页面平移到 hook。
- 同目录下若出现 `XxxPage/XxxState/XxxActions/XxxSelectors` 这类天然边界，优先沿边界拆，不要把无关逻辑混在一起。

## 编码约定

- 需要对外暴露的类型、接口、函数、类要补充注释；关键分支逻辑也要有功能性注释。
- 写代码时优先复用现有 common 组件/ util 函数；如果公共逻辑明显可复用，先抽到 common/util 再使用。
- 不要创建本地重复类型，也不要为了绕 TypeScript 问题去 cast 成临时替身类型。
- 尽量不要手写显式返回类型，除非 TypeScript 推断不稳或公共契约需要。
- 同一文件内出现大量 `setX` / `ref.current` / effect 同步胶水代码时，要优先考虑抽成 `useLatestRef`、selector、controller hook 或 state adapter，而不是继续往下堆。
- 视图层中的派生计算（dirty 判断、header title、preview 数据、可见状态等）应优先抽到 selector / pure helper，避免散落在页面主体。
- 单元测试要严格镜像源码目录结构，每个测试文件只测试对应源文件的行为。
- 测试要能证明问题真实存在；不要只写“会通过但证明不了什么”的测试。

## React 与状态管理

- 避免 React 最大更新深度和 useSyncExternalStore 循环；在 useEffect 写回状态前先做相等性判断。
- 对对象和数组比较时，优先按 id、长度或关键字段判断，避免每次 render 都触发 setState。
- 避免 Zustand 选择器返回新对象；需要组合字段时用 shallow，或拆成多个 selector。
- store 的 set 和更新函数在没有变化时应返回旧 state 或 prev，避免订阅者反复触发更新。
- useSearchParamsState 的 defaultValue 必须是稳定引用；默认值会变化时传 shortenUrl=false，避免 URL 和默认值来回写。
- 只有在异步回调、事件订阅、定时器确实需要“最新值”时，才允许引入 `ref.current` 镜像状态；一旦出现 3 个及以上此类镜像，必须评估抽成统一的 `useLatestRef` / controller hook。
- hook 的职责要单一：bridge lifecycle、role management、chat interactions、chat image state、UI effects 这类边界应分开，不要做“万能 hook”。
- hook 之间尽量用明确参数和返回值协作，少用临时 mutable ref 桥接；如果出现 `xxxRef.current?.()` 这类协调方式，默认应继续检查是否能改成显式依赖注入。

## UI 与前端约束

- 前端页面不要产生对功能进行叙述的文字。
- input 样式不要使用 daisy UI，优先使用 transition focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary。
- 默认圆角使用 rounded-md。
- 需要 Icon 时使用 phosophorIcon。

## 代码与平台注意事项

- 严禁在源码中用 Unicode 转义形式书写常见可见符号，必须直接写可读字符。
- 文本文件统一使用 UTF-8 保存。
- 通过脚本或命令写文件时显式指定编码，避免默认 ANSI 或 GBK 造成乱码。
- 发现乱码先检查文件编码与终端解码设置，必要时重存为 UTF-8。
- Python 命令、测试和质量工具必须使用仓库 `.venv`，禁止依赖 PATH 中的系统 Python：Windows 使用 `.venv\\Scripts\\python.exe`、`.venv\\Scripts\\pytest.exe`、`.venv\\Scripts\\ruff.exe` 等；跨平台文档和脚本统一使用 `uv run ...`。
- 不要直接运行裸 `python`、`pytest`、`ruff` 或 `pyright` 来验证 Shiori；先确认 `python -c \"import sys; print(sys.executable)\"` 指向仓库 `.venv`，否则使用 `.venv` 的绝对/相对路径。
- `pnpm dev` 的 Python bridge 必须继续由 `apps/desktop/src/bridge/bridgeClient.ts` 启动项目 `.venv` 中的解释器，不得改成依赖系统 PATH 的 `python`。

## 仓库特定约束

- Node 依赖统一通过根目录的固定版本 pnpm workspace 管理；只维护 `pnpm-lock.yaml`，不要新增根目录或 `apps/desktop/` 的 `package-lock.json`。
- 每完成一轮答复（实现、修改、修复）后，对当轮对话变更的代码立即进行 git commit。
- 涉及代码变更的功能分支，默认先推送远端并创建 Draft PR；未经用户明确要求，不得直接推送或合并到 `main`。
- PR 必须关联对应 Issue，并写明变更摘要、实际验证结果和已知阻塞项；相关测试与构建通过且阻塞项清零后，才可转为 Ready 或合并。
- 没有特定要求时不要调用方案设计。
- PowerShell不要用&&
- `docs/specs/` 和 `docs/plan/` 不进 git 仓库
- 搜索前必须先明确搜索范围；默认限制在当前主仓库相关目录内，避免全局命中无关文档、.worktrees 或其他代理工作区。

## Agent skills

### Issue tracker

本仓库使用 `YinFengWindy/Shiori-Agent` 的 GitHub Issues 跟踪任务。详见 `docs/agents/issue-tracker.md`。

### Triage labels

使用 mattpocock/skills 的默认分诊标签词汇。详见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库采用单上下文领域文档布局。详见 `docs/agents/domain.md`。

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
