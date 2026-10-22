# 插件边界规则对照表：check_sdk_imports → import-linter

> 对应四层重构 P0（#899），见 [`2026-10-22-plugin-system-four-layer-refactor.md`](2026-10-22-plugin-system-four-layer-refactor.md) §4 P0、§5.4、§5.11。基线 `main` @ `13442bd`。

P0 只新增 import-linter 分层报告（`pyproject.toml` 的 `[tool.importlinter]`，CI 步骤 `Report layer contracts`，不阻塞），**不删除也不修改**现有检查：`python -m scripts.check_sdk_imports` 继续阻塞 CI。本表把现有检查的每条规则归为三类之一，供以后替换时直接执行：

- **覆盖**：由 import-linter 契约覆盖，替换时可删。
- **放弃**：主动放弃，写明理由。
- **保留**：import-linter 做不到，替换后单独保留（可简化，但不能丢）。

## 现有检查的范围

`scripts/check_sdk_imports.py` 扫描 `packages/sdk/python`、`packages/sdk/tests` 和 `plugins/<id>/` 下全部 `.py` / `.pyi`（含插件测试和任意子包），跳过 `.venv`、各类缓存、`node_modules`、`*.egg-info`，以及插件根目录下的 `build/`、`dist/`。禁止集合来自 `scripts/sdk_boundaries.py::host_roots`。路径规则由 `sdk_resource_edges.py` 组合 `sdk_path_values` / `sdk_path_sinks` / `sdk_layout_literals` / `sdk_repository_layout` / `sdk_module_names` / `sdk_strings` 实现。

## 对照表

### A. import 边

| # | 规则 | 位置 | 结论 | 说明 |
|---|---|---|---|---|
| A1 | SDK 和插件不得 `import` / `from … import` 宿主包，含函数内、类内和 `TYPE_CHECKING` 块里的 import | `host_imports` | **覆盖** | 契约「SDK 和插件不 import 宿主」。grimp 收集所有作用域的 import，默认也计入 `TYPE_CHECKING` 块。插件测试（`plugins.<id>.tests`）在图里。旧检查也扫描 `.pyi`，grimp 不分析 stub；目前仓库里没有 `.pyi`，以后引入 stub 时要另行覆盖。 |
| A2 | SDK 不得 import `plugins` | `scan` 对 SDK 加 `plugins` | **覆盖** | 契约「SDK 不 import 插件」。 |
| A3 | 禁止集合按 `apps/backend` 下含 `.py` 的目录和模块动态发现，新增宿主包自动受约束 | `host_roots` | **保留** | import-linter 的 `root_packages` 是静态列表，新增宿主包必须手工加入。替换时保留 `host_roots`（`isolation_probe` / `verify_plugin_tests` 本来也在用），加一个小检查：`root_packages` 必须包含 `host_roots` 里的全部包。`main.py` 是入口模块，不会被 import，不进图。 |
| A4 | 禁止 `memory2`、`shiori_plugin_testkit` | `host_roots` 附加项 | **放弃** | 两者都已删除，无法安装也无法 import；如果有人在 `apps/backend` 下重建同名包，A3 的动态发现会自动纳入。 |
| A5 | 禁止 `shiori_host_testing`、`tests` | `host_roots` 附加项 | **覆盖** | 两者已作为 root package 加入，并列在「SDK 和插件不 import 宿主」的禁止集合里。 |
| A6 | 字面量动态 import：`importlib.import_module`、`__import__` / `builtins.__import__`、`pkgutil.resolve_name`（含 `mod:attr`），跟踪别名链、`getattr(importlib, "import_module")`，以及字符串常量折叠（拼接、f-string、变量） | `_scope_imports`、`sdk_strings` | **保留** | import-linter 只看静态 import 语句。插件在宿主进程里运行，宿主模块在生产环境可以 import，所以动态 import 是真实的绕过路径；`isolation_probe` 只能拦截测试实际执行到的那部分。 |
| A7 | 以宿主包为锚点的资源读取：`importlib.resources.files` / `read_text` / `read_binary` / `open_text` / `open_binary`、`pkgutil.get_data` | `_scope_imports` | **保留** | 理由同 A6：import 图看不到，生产环境能读到。 |
| A8 | 测试里 `unittest.mock.patch` / `patch.multiple`、`monkeypatch.setattr` / `delattr` / `setitem` 的点号字符串目标指向宿主 | `_scope_imports` | **放弃** | 这类写法只出现在测试里。插件测试只在 plugin-isolation 跑，SDK 测试只在 `verify_sdk` 跑，两者都在检出目录外的环境运行，`isolation_probe` 断言宿主根不可 import，所以 patch 目标在执行时就会失败；不执行的 patch 是死代码。 |
| A9 | `packages/sdk/tests` 也在扫描范围内 | `scan` | **放弃** | SDK 测试目录不是可 import 的包，进不了 import 图。它只在 `verify_sdk` 的无宿主环境里运行，静态 import 宿主会在收集阶段失败。 |
| A10 | 没有白名单，也不能按迁移豁免 | `violations` | **保留（约定）** | 契约转为阻塞后，不得使用 `ignore_imports`；该约定写进替换 PR 的配置注释。 |
| A11 | 相对 import（`from . import x`）不检查 | `node.level == 0` | — | 现有检查的盲区。import-linter 会解析相对 import，替换后更严格，不需要保留。 |

### B. 路径与资源（path-sink 类）

import-linter 只分析 import 图，下面这些规则全部看不到。它们约束 SDK 和插件不依赖仓库布局，否则装成 wheel 或打进冻结应用后就会失效。P0 全部**保留**；P8 如果要删，需要逐条证明「检出目录外的隔离运行能覆盖」，并在本表里改写结论。

| # | 规则 | 位置 | 结论 | 说明 |
|---|---|---|---|---|
| B1 | 由 `__file__` 推导的完整路径表达式（`Path(__file__).parents[n] / …`、`os.path.dirname` 链等）不得离开所属包（SDK → `packages/sdk`，插件 → `plugins/<id>`） | `_expression_rule` | **保留** | 典型问题是直接引用仓库里的宿主文件。 |
| B2 | 以工作目录为锚点（`Path.cwd()`、`os.getcwd()`、`Path()`，含 `+ "/…"` 拼接）的路径不得指向宿主布局 | `_expression_rule`、`host_layout` | **保留** | 宿主布局指以 `apps/backend`、`apps/desktop`、`tests/backend` 开头的路径，或 `apps/backend` 下真实存在的路径，或宿主包目录里的文件名。 |
| B3 | 相对路径进入文件系统 sink 时不得指向宿主布局。sink 包括 `open`、`os.*` 文件操作、`os.path.exists` / `isfile` / …、`glob`、`shutil.*`、`pathlib.Path` 的读写和遍历方法，以及 `sys.path.insert` / `append` | `sdk_path_sinks`、`_sink_rule` | **保留** | 其中 `sys.path` 改写能在运行时打开 import 宿主的通道，import-linter 同样看不到。 |
| B4 | 字符串字面量以 `apps/backend/`、`apps/desktop/`、`tests/backend/` 开头即违规；docstring 和 `x / "…"` 的运行时拼接除外 | `sdk_layout_literals` | **保留** | 兜底规则：数据流经过属性、容器或调用返回值时，B1–B3 跟踪不到（见 `sdk_path_values` 文档列出的已知限制）。 |
| B5 | 同一违规只在首次出现的表达式处计一次 | `PathValues.origin` | — | 报告方式，不是规则；随 B1–B4 保留。 |

### C. 打包依赖

| # | 规则 | 位置 | 结论 | 说明 |
|---|---|---|---|---|
| C1 | SDK 和插件 `pyproject.toml` 的 `dependencies` 以及全部 optional extras 不得包含宿主发行包（`shiori-agent`、`shiori-host-testing`、`shiori-plugin-testkit`） | `dependency_violations` | **保留** | 这是打包元数据，不是 import。 |
| C2 | SDK 不得依赖任何 `shiori-plugin-*` | `dependency_violations` | **保留** | 同上。 |

### D. 不属于边界规则

| 文件 | 结论 | 说明 |
|---|---|---|
| `scripts/sdk_release.py`、`scripts/sdk_registry.py` | 不在替换范围 | SDK 发布归档校验和注册表上传准备，与 import 边界无关。 |
| `scripts/sdk_boundaries.py` 的发行包命名函数 | 不在替换范围 | `wheelhouse`、`verify_plugin_tests`、`isolation_probe` 在用。 |

## import-linter 新增的规则（旧检查没有）

| 契约 | 规则目标（§5.4） | 映射到当前布局 |
|---|---|---|
| 内核（现 `agent.plugin_host`）不 import 宿主业务模块和插件 | kernel 不 import core / bootstrap / desktop_bridge / plugins | `shiori_sdk.kernel` 在 P1 才建，现在以 `agent.plugin_host` 为内核。目标是内核不懂任何业务，所以禁止集合取全部宿主业务包（`agent` 下除 `plugin_host` 以外的子包、`bootstrap`、`bus`、`conversation`、`core`、`desktop_bridge`、`infra`、`proactive_v2`、`prompts`、`session`、`utils`）加上 `plugins`。 |
| 核心模块不 import 插件 | core 不 import `plugins.*` | 全部宿主包 → `plugins`。宿主通过 `importlib` 动态加载插件，不在静态图里。 |
| 插件只 import manifest 声明的依赖插件 | 插件只能 import SDK 和已声明依赖的插件 | 自定义契约 `scripts/plugin_import_contract.py`：允许集合是插件自身加上 manifest 的 `dependencies` / `optional_dependencies`。「只能 import SDK」中禁止宿主的部分由 A1 的契约覆盖。 |
| `shiori_sdk.kernel` 只 import `shiori_sdk`，且不 import 核心契约模块 | 同左 | **P1（#900）已加入**，取更严的形式：自定义契约 `kernel_isolation`（`scripts/plugin_import_contract.py`）只允许内核 import 自身和标准库，SDK 其他模块（含以后的核心契约）、宿主、插件和第三方包一律不允许。为看到第三方包，`[tool.importlinter]` 打开了 `include_external_packages`。 |
| 前端：eslint `no-restricted-imports`，插件 ui 只能 import `@yinfengwindy/shiori-sdk` 和 react | 同左 | **P0 不实现，延后到 P7（#908，前端入口统一时）**：P0 的 ticket 范围是 import-linter（Python import 图）；前端插件入口的形态（一个 frontend 入口 + 具名导出）要到 P7 才定下来，现在按 renderer 三种 kind 写规则，P7 还得重写。 |

所有契约只检查直接 import（`allow_indirect_imports = true`）。内核搬进 `shiori_sdk.kernel` 后，「只许 import SDK」本身就是传递约束。

## P0 基线报告

在 `13442bd` 上运行 `lint-imports`：5 条契约里 4 条保持，「内核不 import 宿主业务模块和插件」不成立，共 49 条直接 import，涉及 `agent.config`、`agent.core`、`agent.mcp`、`agent.provider`、`agent.tool_hooks`、`agent.tools`、`bootstrap`、`bus`、`conversation`、`core`、`desktop_bridge`、`infra`、`session`。这些正是 P1 / P2 要从内核搬出的部分。核心 → 插件、SDK / 插件 → 宿主、插件间未声明依赖，均为 0。
