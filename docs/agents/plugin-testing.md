# 插件测试

插件的 Python 测试随 `plugins/<id>/tests/` 保存。插件包的 `pyproject.toml` 声明 SDK（未迁移插件暂时声明宿主）依赖、兄弟插件依赖、`test` extra 和 pytest 配置。新增含测试的插件必须提供此声明；独立验证会因缺失声明直接失败。

## 仓库开发

在仓库根目录运行：

```sh
uv sync --dev
uv run pytest
```

`uv.lock` 与本地 source 声明会安装真实宿主、默认记忆和测试支持包。使用既有 requirements 入口时，在仓库根目录向项目虚拟环境安装 `apps/backend/requirements/development.txt`；其中的相对路径刻意从根目录解析。该入口同时安装本地宿主、默认记忆、testkit 和质量工具。

根目录不再有 `conftest.py`。`tests/conftest.py` 与 `tests/support/` 只提供宿主测试所需的 fixture；生产依赖使用项目环境中安装的真实包，测试在各自边界 mock 网络请求，不全局替换第三方模块。插件测试不得导入这些模块，不得从父目录推导原仓库路径。插件自己的文件可相对 `__file__` 定位；已声明的兄弟插件通过 `shiori_sdk.testing.packages.plugin_directory()` 定位。整包暂存统一调用 `stage_plugin_package(source: Path, target: Path) -> Path`（同一模块），它保留插件源码、manifest、测试及资源，排除 `.venv`、含 `pyvenv.cfg` 的环境目录、构建缓存与包级运行状态；不要在各插件中复制 ignore 规则。宿主的 v2 fixture 也直接使用整包暂存；迁移回归在暂存后显式构造历史状态文件，不保留旧布局适配器。独立支持测试位于 `packages/sdk/tests/testing/`，真实 AppRuntime fixture 与对应测试分别位于 `packages/shiori-host-testing/src/shiori_host_testing/`、`tests/backend/shiori_host_testing/`。根 pytest 和测试类型检查均显式覆盖。

SDK 的 pytest 插件在整个会话内按参数与证书环境变量缓存 httpx 的 SSL 上下文，避免每个 client 重复加载 CA 证书；宿主测试与插件独立运行都会启用。测试不得修改从 httpx 拿到的 SSL 上下文。

## 可安装边界

- `shiori-agent` 是真实生产 Python 模块组成的私有 runtime wheel，使用显式包清单，不包含测试树、其他插件或用户状态。
- `shiori-plugin-default-memory` 是真实 `AppRuntime` 的必需依赖，由宿主明确声明。
- `shiori-sdk[testing]` 提供独立 ctx/capability fake、包资源定位、bridge helper 与 pytest 入口；不安装宿主、不打开宿主存储。
- `shiori-plugin-testkit` 仅供未迁移插件暂存，转发 SDK 的独立 helper 和宿主 `shiori_host_testing` 的真实启动 fixture；旧记忆 fake 尚待对应插件迁移后删除。
- 每个插件的 wheel 只包含该插件后端及其声明资源，测试从插件副本运行。Story 显式依赖 NovelAI，Meme 显式依赖 citation；未声明的兄弟插件不能隐式获得。

上述包只在私有 wheelhouse 或本地开发环境使用，不发布 PyPI，契约版本与兼容范围见 `packages/sdk/README.md`。普通部署和 PyInstaller 打包入口保持不变。生产技能、配置模板及共享 emoji 由 `bootstrap.paths` 统一定位，wheel 构建和桌面 bundle 使用相同源资源。

## 插件副本运行

每个插件的 `TESTING.md` 都随包提供仓库外安装与运行命令。拿到插件副本及私有 wheelhouse 后，进入副本目录，先 `uv venv .venv --python 3.12`，再按该文件安装 `.[test]`（未迁移插件仍需要宿主、testkit 与默认记忆），最后执行 `uv run --no-project --python .venv python -m pytest -c pyproject.toml tests`。私有 wheel 缺失时应补齐构建产物，不能改为导入原仓库。

## 仓库外验收

```sh
uv run python scripts/verify_plugin_tests.py --output /absolute/path/outside-repository/plugin-isolation
```

输出目录必须在仓库外且是新目录。不传 `--output` 会创建系统临时目录。可用 `--plugins novelai story` 只验证受影响插件；不传时发现所有具有 Python 测试的插件。`--jobs N` 控制 wheel 构建与插件验证的并发数，默认为 CPU 数；已知耗时最长的插件（telegram、feishu、qqbot）优先调度。

脚本将被测插件复制到输出目录，从副本构建 wheel，并构建真实宿主和 testkit wheel。每个目标有单独的干净 venv，仅安装宿主、testkit、目标与其声明依赖。闭包按实际安装的 `目标[test]` 计算：目标的 `project.dependencies` 与 `project.optional-dependencies.test` 都参与构建和来源审计；仅供测试的兄弟依赖（例如状态命令测试使用的 observe）应放在 test extra，不进入运行时依赖。传递兄弟插件只跟随运行时依赖和依赖边显式请求的 extras，不自动启用兄弟的 test extra。环境 marker 按实际测试解释器及已启用 extra 求值；testkit 单独构建，不当作插件目录。安装为非 editable；不会共享已安装的其他测试目标。子进程清空 Python/pytest 导入注入与服务凭证，不调用真实收费模型。

每个目标执行全部测试后验证宿主模块来自该环境的 site-packages、目标插件代码与副本一致、安装依赖闭包正确、没有 editable 安装；还实际读取内置技能、共享 emoji 并调用初始化流程复制配置模板。最后单独运行故意在 `await` 后失败的异步用例，要求退出码 1 和执行标记，证明 pytest 真正等待了协程。

`results.json`、`host-wheel-files.txt`、各包的 `pytest.log`、`provenance.json`、`async-failure.log` 是验收证据。预期失败的异步探针不算插件失败。wheel 构建失败会停止验证；单个插件的失败或依赖缺失不会中止其余插件，全部跑完后列出失败插件及其日志路径并以非零退出；命令失败指向该命令的日志，其他异常的完整 traceback 写入 `cases/<id>/failure.log`。`results.json` 由主线程在每个插件完成后重写一次（超时中断也保留已完成的证据），按插件排序，包含通过与失败条目及各自耗时。CI 在独立的 `plugin-isolation` job 中对全部插件执行此流程并上传证据，不能用只收集测试或跳过宿主集成用例替代。


## SDK 隔离与导入守护

citation/context_pressure/default_memory/shell_safety/shell_restore/tool_loop_guard/plugin_undo/observe/status_commands/meme/novelai/story/screen_perception/browser_use/computer_use/qqbot/qq/telegram/feishu 已迁入 `shiori-sdk[testing]`，安装声明不再依赖宿主。
`uv run python scripts/verify_plugin_tests.py --sdk-only` 仅为这十九个插件构建
SDK/插件 wheel，逐一在仓库外普通安装、执行全部测试，并断言没有
shiori-agent、testkit、宿主测试支持与源码路径注入；default_memory 只在验证自己时安装。普通全插件验证也对这十九个插件
使用相同无宿主路径；其余插件保留真实宿主安装与资源检查。

`uv run python -m scripts.verify_sdk` 另外安装 SDK wheel 并执行 SDK 自身测试；
`pnpm run sdk:smoke` 安装 npm tarball，检查所有子入口、DOM 测试工具和声明。
CI 的 sdk-artifacts job 与既有宿主测试并存，不发布产物到公共注册表。

`uv run python scripts/check_sdk_imports.py --base <base-commit>` 检查 SDK 与插件
backend/tests 的宿主导入（含类型导入和字面量动态导入）。豁免以每个文件、符号及
次数记录在 `scripts/sdk_import_exemptions.json`，只能随迁移删除，不能增加。


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

#589 渠道迁移先以 QQBot 完成独立验证。账号、规则、目标、会话键、消息与渠道声明的纯值测试随定义移入 `packages/sdk/tests/accounts` 和 `packages/sdk/tests/channels`；真实消息总线/AgentLoop 流式与取消验证留在 `tests/backend/agent/looping/test_core_qqbot_streaming.py`，通过公开渠道启动、外部 HTTP/WebSocket 替身装配。重载与角色删除保留在宿主 plugin_management 集成测试，平台凭据和私有连接状态断言留在 QQBot 自己的测试。

QQ 已在同票完成 SDK-only 安装验证；平台原文来源/引用的纯函数与测试分别归 `shiori_sdk.channels.message_source`、`reply_context` 及 SDK 镜像测试。投递账本、账号重启/删除与头像持久化集成留在宿主对应 owner 测试。NapCat 使用宿主 `Processes.popen`，Windows CI 保留已有进程测试并加入同步能力和 QQ 直接调用者。

#589 已完成四渠道。Telegram 以 SDK fake 验证命令菜单、用户名/话题、媒体和流式，飞书保留真实离线 HTTP/WebSocket 线程替身验证；两者的存储/生命周期宿主集成继续由根 CI 执行。SDK wheel 冒烟执行镜像后的纯值测试和新增公共 fake 测试。尚未迁移的仅桌宠，归 #590；#591 做全插件最终发行验收。
