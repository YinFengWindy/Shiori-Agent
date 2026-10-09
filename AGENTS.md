# AGENTS.md

Shiori 是一个以角色为基底进行角色扮演的 Agent 助手：Python 后端 + Electron/React 桌面端，功能大多以插件形式提供。

## 先读什么

| 位置 | 内容 |
|---|---|
| `apps/backend/` | Python 后端：启动装配、Agent 回合、会话、记忆运行时、主动行为、桌面桥接 |
| `apps/desktop/` | Electron 主进程（`src/`，只提供通用原语，不放插件代码）与 React renderer（`renderer/src/`） |
| `plugins/<id>/` | 插件包：`backend/`、`ui/`、`surface/`、`background/`、`manifest.yaml`、`tests/` |
| `packages/sdk/` | 统一 Shiori SDK（Python `shiori_sdk` + npm `@yinfengwindy/shiori-sdk`） |
| `docs/knowledge/` | 架构与领域知识：从 `index.md`、`map.md` 开始定位 owning module |
| `docs/_handbook/` | 设计系统、插件运行时契约、插件教程、渠道/记忆/主动推送等专题手册 |

文档与源码冲突时以源码为准，并顺手修正文档。

## 工作流程

- 需求明确的小改动直接实现。整改、新功能、跨模块改动：先调查，再停下来汇报结论并澄清需求（dev-flow），经确认后再实现。
- `main` 上不直接提交。代码改动在功能分支上进行，一个完整、可验证的改动单元完成后 commit。
- 功能分支默认推送并创建 Draft PR；未经明确要求不推送或合并到 `main`。
- PR 必须关联 Issue（`YinFengWindy/Shiori-Agent`，见 `docs/agents/issue-tracker.md`），写明变更摘要、实际验证结果和已知阻塞项；测试与构建通过、阻塞项清零后才可转 Ready 或合并。
- 普通 SDK / 运行时 API 契约 PR 不逐个升版本，在 `docs/_handbook/plugin-runtime-contract.md` 的 Unreleased 区累积变更与 PR 溯源，破坏性变更标注 **breaking**。正式发布 SDK 或包含新契约的桌面版本前，由维护者对照上次已发布契约统一定版；同一开发批次只定版一次，已发布的版本号不再承载新契约。版本唯一来源 `packages/sdk/python/shiori_sdk/_version.py`（SDK 与 Runtime API 同号），用 `node scripts/sync_sdk_version.mjs` 同步，并统一该批次的插件最低版本约束。
- 插件自身的 `version` 独立于 SDK 和桌面版本。正式发版前对照上次发布批次，有包内容或兼容声明变化的已有插件只升一次 patch；新插件保留其选定的初始版本，未变插件不升号。`manifest.yaml` 与 `pyproject.toml` 的版本必须一致，同时更新消费方依赖约束和锁文件。
- `docs/specs/`、`docs/plan/` 不进 git。
- 搜索前先限定范围，排除 `node_modules`、`dist`、`renderer-dist`、`__pycache__` 与 worktree 副本（`D:/Coding/Shiori.worktrees/`）。

## 验证

有代码改动时，汇报完成前必须跑过与改动范围相匹配的检查；失败先修，修不了就明确记录为阻塞，不能以「没跑」作为完成依据。局部改动跑相关测试及其直接调用者，跨模块或全局配置改动再扩大到全量；CI 要求的检查始终保留。

| 范围 | 命令 |
|---|---|
| Python 格式与 lint | `.venv\Scripts\black.exe --check .`、`.venv\Scripts\ruff.exe check .` |
| Python 测试 | `.venv\Scripts\pytest.exe <路径>`（testpaths：`tests/backend`、`plugins`、`packages/sdk/tests`；开了 `-W error`，任何警告都算失败） |
| Python 类型 | pyright：源码 `pyrightconfig.json`，测试 `--project pyrightconfig.tests.json` |
| 桌面端 / TypeScript | `pnpm lint`、`pnpm typecheck`、`pnpm test`（插件 UI：`pnpm desktop:test:plugin-ui`） |

- Python 一律用仓库 `.venv`（跨平台文档与脚本写 `uv run ...`），不要用 PATH 里的裸 `python` / `pytest` / `ruff` / `pyright`。
- 测试要能证明问题真实存在，不写「会通过但证明不了什么」的测试。

## 代码原则

- 长期可维护性优先于局部省事；修根因，不做局部补丁式绕过。
- 失败即停：不写不必要的 fallback；业务层不吞错，让异常冒泡到边界层再处理。
- 直接调用 owning module / service，不无意义地加抽象层。
- 先复用现有的共享组件、util 和类型；同一段逻辑要在第二处出现时，抽成共享 helper 或 hook。
- 不建本地重复类型，不为绕过 TypeScript 去 cast 成临时替身类型；返回类型尽量交给推断，公共契约除外。
- 对外暴露的类型、函数、类写注释；关键分支写功能性注释。

## 模块边界

- 入口与顶层容器（`main.tsx`、页面根组件）只做状态装配、依赖拼接与视图分发，业务细节下放到独立 hook / module。
- 一个文件里的职责明显可以分开时就拆，沿天然边界拆（如 `XxxState` / `XxxActions` / `XxxSelectors`）；不要把大文件问题从页面平移到一个「万能 hook」。
- 路过时发现超过 600 行的业务文件，在答复里提一句「这个文件偏大、可能值得拆」即可，是否拆由用户决定，不自行发起大重构。

## React

- 派生值在渲染时直接计算，或抽到 selector / 纯函数（dirty 判断、标题、可见状态等）；不要用 useEffect 把一个状态同步成另一个状态。
- 跨组件共享状态用项目里手写的 store + `useSyncExternalStore`（参考 `renderer/src/plugins/pluginEnabledStateStore.ts`）：没有变化时 snapshot 必须返回同一个引用，否则会无限重渲染。
- 异步回调、订阅、定时器里需要读最新值时，用现成的 `useLatestRef`，不要手写一堆 `ref.current` 镜像；hook 之间用显式参数和返回值协作。

## UI

设计系统全文见 `docs/_handbook/design-system.md`，以下几条是硬约束：

- 页面里不写对功能进行叙述的文字（看板娘台词表是 owner 认可的例外）。
- 控件优先用共享类名：插件可用的在 `@yinfengwindy/shiori-sdk`，宿主专用的在 `renderer/src/shared/styles.ts`。不要另写一套手写 Tailwind 串。
- 颜色、圆角、阴影、动效一律走语义 token 或语义类，不写死值；legacy 别名（`--bg`、`--panel`、`*-primary` 等）新代码不用。
- 焦点样式由 `styles.css` 统一提供，组件里不写 `focus:ring-*` / `focus:border-*`；确实要退出的，在注释里说明原因。
- 新增循环动画或较大位移，必须在 `styles.css` 的 `prefers-reduced-motion` 块里给出降级。
- 功能图标只用 `shared/icons.tsx` 或 `@phosphor-icons/react`，不要自绘；`shared/ui/icons` 只放品牌母题。

## 测试放哪

| 被测代码 | 测试位置 |
|---|---|
| TypeScript 源文件 | 同目录并列（`main.ts` / `main.test.ts`）；e2e 放 `apps/desktop/tests/` |
| `apps/backend/` | `tests/backend/`，目录结构镜像源码 |
| `plugins/<id>/` | `plugins/<id>/tests/`，自包含；测试支持来自 `shiori-sdk[testing]`，不依赖根 conftest（见 `docs/agents/plugin-testing.md`） |
| `packages/sdk/` | `packages/sdk/tests/`，结构镜像 `python/shiori_sdk/` |
| 宿主测试 fixture 包 | 包在 `packages/shiori-host-testing/`，测试在 `tests/backend/shiori_host_testing/` |

每个测试文件只测对应源文件的行为。

## 平台与编码

- 文本文件一律 UTF-8；用脚本写文件时显式指定编码；源码里不用 Unicode 转义来写可见字符。
- Node 依赖只通过根目录的固定版本 pnpm workspace 管理，只维护 `pnpm-lock.yaml`，不要新增 `package-lock.json`。
- `pnpm dev` 的 Python bridge 由 `apps/desktop/src/bridge/bridgeClient.ts` 启动 `.venv` 里的解释器，不改成依赖 PATH。
- Python 风格：ruff（`E4/E7/E9/F`）+ black，line-length 88。

## Agent skills

- Issue tracker：`docs/agents/issue-tracker.md`
- 分诊标签：`docs/agents/triage-labels.md`
