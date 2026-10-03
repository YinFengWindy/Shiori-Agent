# 插件测试

插件的 Python 测试随 `plugins/<id>/tests/` 保存。每个 `pyproject.toml` 显式声明 `shiori-sdk`、兄弟插件和第三方依赖、`test` extra 与 pytest 配置。所有插件单测只通过 `shiori-sdk[testing]` 使用独立 fake；真实宿主装配测试在 `tests/backend/`。

## 仓库开发

在仓库根目录运行：

```sh
uv sync --dev --locked
uv run pytest plugins/example/tests
```

`uv.lock` 安装真实宿主、默认记忆及 `shiori-host-testing`，用于宿主开发和集成验证。requirements 入口为 `apps/backend/requirements/development.txt`，其本地相对路径从仓库根目录解析。Python 验证统一使用仓库虚拟环境。

`tests/conftest.py` 与 `tests/support/` 只提供宿主 fixture；插件不得导入宿主测试树，也不得从源文件父目录推导原仓库资源。插件自己的资源可相对 `__file__` 定位；已声明兄弟插件通过 `shiori_sdk.testing.packages.plugin_directory()` 定位。整包暂存统一调用 `stage_plugin_package(source, target)`，排除虚拟环境、构建缓存和运行状态。SDK 支持测试位于 `packages/sdk/tests/testing/`；真实 AppRuntime fixture 和 workspace-backed memory fake 位于 `packages/shiori-host-testing/src/shiori_host_testing/`，对应测试位于 `tests/backend/shiori_host_testing/`。

`shiori-host-testing` 的 pytest 入口仅在明确安装此私有宿主包时注册。SDK 自己的 pytest 入口允许仅安装基础 SDK 的消费者正常收集、运行无关测试；需要 fake 时会提示安装 testing extra。测试 TLS 上下文按参数和证书环境变量缓存，测试不得修改共享 SSL 上下文。

## 可安装边界

- `shiori-sdk[testing]` 提供契约 fake、包定位、bridge helper 与 pytest 支持，不安装或实例化宿主。
- `shiori-agent` 是真实生产模块组成的私有 runtime wheel，明确依赖默认记忆；不包含宿主测试、其他插件或用户状态。
- `shiori-host-testing` 提供真实宿主集成能力，只安装在宿主开发环境。
- 插件 wheel 只包含本包后端、明确打包的 testing helper 与资源。Story→NovelAI、Meme→citation 为公开运行时依赖；status_commands 的 test extra→Observe 是显式测试依赖。没有声明的兄弟插件不会被注入。

公开 SDK 的 npm 包为 `@yinfengwindy/shiori-sdk`，PyPI 包为 `shiori-sdk`；SDK 与 Runtime API 当前版本均为 3.1.0，注册表安装与 testing extra 用法见 [SDK README](../../packages/sdk/README.md)。`shiori-agent`、`shiori-host-testing` 和插件 wheel 仍只构建为本地/CI 产物，不随 SDK 发布到 npm 或 PyPI。

## 插件副本运行

每个插件的 `TESTING.md` 随包提供安装命令。取得插件副本及私有 wheelhouse 后，在副本目录执行：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

uv 会缓存 `--find-links` 中同名同版本的 wheel，重新构建后不加 `--refresh-package` 会装回缓存里的旧构建；wheelhouse 提供的兄弟插件 wheel（如 meme 依赖的 citation）也各加一个 `--refresh-package <分发名>`，各插件 `TESTING.md` 已列全。

不要使用 editable 安装、设置指向原仓库的 `PYTHONPATH` 或复制宿主 conftest。私有 wheel 缺失时补齐产物，不改为从原仓库导入。

## 仓库外验收

```sh
uv run python -m scripts.verify_plugin_tests --output /absolute/path/outside-repository/plugin-isolation
```

输出必须是仓库外的新目录；省略时创建系统临时目录。`--plugins novelai story` 选择目标，省略时发现所有有 Python 测试的插件；`--jobs N` 控制并发，默认 CPU 数。不存在迁移豁免、白名单或宿主安装分支。基准 20 插件为 browser_use、citation、computer_use、context_pressure、default_memory、desktop_pet、feishu、meme、novelai、observe、plugin_undo、qq、qqbot、screen_perception、shell_restore、shell_safety、status_commands、story、telegram、tool_loop_guard；新增插件自动纳入发现。

脚本在仓库外暂存插件并构建普通 wheel，每个目标使用独立 venv，只安装目标 `[test]`、SDK/testing 与显式依赖。所有 `shiori-*` 包（SDK、目标与兄弟插件）以 `--no-index --no-deps` 从本地 wheelhouse 的 wheel 文件安装，闭包中缺少本地 wheel 即失败，不会回退到公网同名包；这一步同时加 `--no-cache --reinstall`，uv 缓存或环境中同名同版本的旧构建不能顶替刚构建的 wheel；其余第三方依赖单独从索引解析，最后以 `uv pip check` 校验整体依赖，来源探针还要求每个 `shiori-*` 分发记录的来源是 wheelhouse 内的 wheel 文件，且已安装文件与该 wheel 内容逐字节一致、不含 wheel 之外的包文件。`verify_sdk`、`verify_host_distribution` 使用同一安装方式。闭包合并运行时和目标 test extra，传递兄弟依赖只启用依赖边显式请求的 extra，marker 按执行解释器求值。不会默认加入 default_memory 或宿主；任何选中的宿主依赖直接失败。静态守护还检查所有未选中的 optional extra。

每套 pytest 的开始与结束均审计实际宿主顶层包不可导入、已安装分发来自本环境、没有 editable 或仓库路径注入、插件闭包精确、目标代码与副本相同、SDK 版本与 Runtime API 一致。执行探针在初始 conftest 加载前启用，覆盖全部已暂存目标及兄弟依赖的 backend/testing，并拒绝执行仓库内 SDK/宿主源码；临时模块别名即使随后从 sys.modules 删除也不能绕过。已安装入口的来源与哈希覆盖当前目标声明的完整插件依赖闭包，测试本身仍从副本 tests 运行。独立 suite/probe basetemp 避免并行清理彼此证据。全部单测以 `-W error` 真实执行；另开解释器运行故意在 await 后失败的异步用例，要求退出码 1 和执行标记。

`results.json`、各包 `pytest.log`、`provenance.json`、`async-failure.log` 记录实际结果、包版本/来源和无宿主证明。异步探针预期失败不算插件失败。单插件失败会保留日志并继续其余目标，最终以非零退出；结果每完成一包原子写入。构建失败立即停止。

## 守护与 CI

```sh
uv run python -m scripts.check_sdk_imports
uv run python -m scripts.verify_sdk
uv run python -m scripts.verify_host_distribution
pnpm run sdk:smoke
```

Python 守护检查 SDK、所有插件 Python 源码/测试/打包辅助目录和 .pyi，包含 TYPE_CHECKING、动态导入别名、可求值字符串拼接、字符串 patch、宿主资源包（`importlib.resources`、`pkgutil.get_data`/`resolve_name`，含 `import pkgutil` 属性写法与 `getattr(模块, "字面量")`）和资源路径越界：`Path`/`pathlib.Path(__file__)` 的 `parent`/`parents[n]`/`joinpath`/`/`，`os.path.dirname`/`split(...)[0]`/`join`/`abspath` 组合（含 `*[...]` 字面量展开与 `os.pardir`）、`p /= ...` 增量拼接，路径片段中的字符串拼接与 f-string 同样折叠求值；工作目录规则基于文件系统访问点（sink）：显式以工作目录为根的路径（`Path.cwd()`、`os.getcwd()`、`Path()` 起头，含 `os.getcwd() + "/apps/backend"` 字符串拼接）指向宿主布局即违规；相对路径只有直接到达文件系统 sink 时才按工作目录解析——内置 `open`、`io.open`、`os.listdir`/`scandir`/`stat`/`walk`/`chdir`/`remove`/`makedirs` 等、`os.path.exists` 等、`glob.glob`/`iglob`、`shutil.*`、`sys.path.insert`/`append`，以及具体 pathlib 路径的 `open`/`read_text`/`write_text`/`iterdir`/`glob`/`exists`/`is_file` 等方法（清单集中在 `scripts/sdk_path_sinks.py`）。宿主布局（单一定义在 `scripts/sdk_repository_layout.py`）指以 `apps/backend`、`apps/desktop`、`tests/backend` 开头（这三个目录开头的路径或字面量在任何位置都拦，字面量允许前导 `./`；URL、说明文字或 `plugins/x/tests/backend/...` 这类只是包含这些词的字符串不拦），或在 `apps/backend/` 下真实存在，或是已存在宿主包目录中的文件名（如 `bootstrap/x.yaml`）。普通函数调用（`asset_path`、`ctx.resolve`、`storage.write`、`zip.read` 等）的参数不是 sink；`PurePath` 系列、`str()`、`posixpath.join` 不视为文件系统路径；`os.path` 函数只认经 import 绑定确认的 `os.path`/`ntpath`。每个违规只计一次：从已越界路径派生出的路径（`a = R / "a"`、`p /= "x"`、sink 读取同一值）归到最初越界的值，不重复计数。已知边界：路径求值只跟随同一模块内的名字绑定，经属性、容器、函数返回值或循环传递的路径（如 `self.root.parents[3]`、`parents[-1]`、`__spec__.origin`、`sys.path[0]`、循环内反复取 `parent`/`dirname`）不做数据流分析，相对路径经变量传入未列入清单的 sink 也不识别，由仓库外安装 wheel 的真实执行兜底。排除只按扫描根内的相对位置判断：任意层级的虚拟环境（`.venv` 或含 `pyvenv.cfg` 的目录）、缓存目录与 `*.egg-info`，以及插件根目录下的 setuptools 产物 `build/`、`dist/`（与 `stage_plugin_package` 一致）；检出目录本身叫什么不影响扫描，插件包内部的 `backend/build/` 等子包照常扫描。宿主清单从实际 backend 包/模块发现，同时禁止已移除的旧宿主入口；SDK 还禁止具体插件实现依赖。规则有针对性反例，但不是任意 Python 程序的安全沙箱；仓库外真实执行负责检出未被静态识别、实际触发的环境依赖。

五个 CI job 保留：check-and-test 覆盖宿主集成与真实生产 wheel 资源；plugin-isolation 执行全部插件；desktop-check-and-test 验证 renderer；sdk-artifacts 构建并在仓库外安装 npm tarball/Python wheel、执行 SDK 单测；windows-process-lifecycle 验证 Windows 进程。宿主 wheel 探针保留生产技能、emoji、配置模板初始化和排除私有状态的断言，与无宿主插件证据独立。

`pnpm typecheck` 包含不引用宿主 ambient types 的 `plugins/tsconfig.json`。TypeScript 的边界测试检查真实编译依赖图，并以直接调用、计算属性、解构和类型引用反例阻止宿主全局 bridge 依赖。桌宠通过 SDK surface 能力使用真实 windowId/role 快照。

## 真实宿主集成的所有权

#587 批次中，shell 策略、循环阈值、撤销回复、Observe 落盘和状态命令输出
都在六插件自己的 SDK-only 测试中。真实 AgentLoop/SubAgent 执行、会话撤销事务、
命令 abort、可选 provider 卸载/重载与全局 handler 还原留在对应宿主模块测试。
宿主配置事务使用中性 numeric_config schema，不依赖 ToolLoopGuardConfig 策略。
宿主 passive-turn 验证有界错误日志与 TurnFailed/提交协议，不读取 Observe 私有表。

#588 批次中，生成/自动 CG、Story 状态与取消、屏幕观察以及浏览器/电脑工具策略
由插件自己的 SDK fake 测试验证。真实 RoleStore 原子扩展、会话素材归属与呈现、
runtime lease、kernel 卸载顺序及 screen_perception/desktop_pet 组合留在宿主测试。
原 Windows 浏览器/Driver 的显式 native-runtime 验收入口随集成用例移到
`tests/backend/agent/plugin_host/test_processes_{browser_use,computer_use}.py`；
真实 Windows owned_spawn/WindowsJob/MCP 清理随 PR 的窄范围 Windows job 执行。
独立插件测试不会通过桌宠的依赖重新安装宿主，Story 明确声明 Windows 所需 tzdata。

#589 渠道迁移先以 QQBot 完成独立验证。账号、规则、目标、会话键、消息与渠道声明的纯值测试随定义移入 `packages/sdk/tests/accounts` 和 `packages/sdk/tests/channels`；AgentLoop 流式门控与消息总线重试由宿主中性测试（`tests/backend/agent/looping/core/test_streaming.py`、`tests/backend/bus/test_queue.py`）覆盖；QQBot 的流式预览、取消与不可重发投递，以及重启加载、规则持久化与孤儿清理都在 QQBot 自己的测试中验证。

QQ 已在同票完成 SDK-only 安装验证；平台原文来源/引用的纯函数与测试分别归 `shiori_sdk.channels.message_source`、`reply_context` 及 SDK 镜像测试。投递账本、账号重启/删除与头像持久化集成留在宿主对应 owner 测试。NapCat 使用宿主 `Processes.popen`，Windows CI 保留已有进程测试并加入同步能力和 QQ 直接调用者。

#589 已完成四渠道。Telegram 以 SDK fake 验证命令菜单、用户名/话题、媒体和流式，飞书保留真实离线 HTTP/WebSocket 线程替身验证；两者的存储/生命周期宿主集成继续由根 CI 执行。SDK wheel 冒烟执行镜像后的纯值测试和新增公共 fake 测试。桌宠的 Python 后端与测试已由 #590 迁入 SDK；全插件隔离与两种 SDK 产物安装由上述 CI 流程持续验证。

#590 的桌宠包校验、binding/pets RPC、启用互斥、清理重试与动作限流在插件内使用 SDK fake。实际角色事务/锁、资产迁移凭证与 kernel 装配、停用/重载由宿主集成验证。桌宠安装只依赖 SDK 与 Pillow，最后 44 条 Python 宿主导入豁免已删除。局部开发可使用 `uv run python -m pytest plugins/desktop_pet/tests`；仓库外非 editable 验证用 `uv run python -m scripts.verify_plugin_tests --plugins desktop_pet`。


桌宠 renderer 的控制策略移到 `plugins/desktop_pet/background/controller.test.ts`，surface 几何、惯性、ready/hide/reload/window identity 由宿主 `src/surface/host.test.ts` 的中性 fixture 验证。`desktopPetSurfaceController.test.ts` 保留真实 surface/voice/controller 的公开能力装配，验证隐藏与 ASR 期间角色替换的取消行为。原私有 KV 耦合测试随耦合实现一起移除。

`pnpm typecheck` 包含 `pnpm typecheck:plugins`；后者使用独立 `plugins/tsconfig.json`，覆盖全部插件入口、共享模块与单测，未引用宿主 `types.d.ts`。`pluginTypecheckBoundary.test.ts` 检查实际编译依赖图并验证宿主 ambient bridge/type 不存在；`pluginHostImportBoundary.test.ts` 包含直接调用、计算属性、解构与类型引用的 ESLint 反例。插件测试也不能通过注入宿主全局对象绕过 SDK。
