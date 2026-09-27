# 插件测试

插件的 Python 测试随 `plugins/<id>/tests/` 保存。插件包的 `pyproject.toml` 声明宿主依赖、兄弟插件依赖、`test` extra 和 pytest 配置。新增含测试的插件必须提供此声明；独立验证会因缺失声明直接失败。

## 仓库开发

在仓库根目录运行：

```sh
uv sync --dev
uv run pytest
```

`uv.lock` 与本地 source 声明会安装真实宿主、默认记忆和测试支持包。使用既有 requirements 入口时，在仓库根目录向项目虚拟环境安装 `apps/backend/requirements/development.txt`；其中的相对路径刻意从根目录解析。该入口同时安装本地宿主、默认记忆、testkit 和质量工具。

根目录不再有 `conftest.py`。`tests/conftest.py` 与 `tests/support/` 只提供宿主测试所需的 fixture 和历史 SDK stub。插件测试不得导入这些模块，不得从父目录推导原仓库路径。插件自己的文件可相对 `__file__` 定位；已声明的兄弟插件通过 `shiori_plugin_testkit.packages.plugin_directory()` 定位。整包暂存统一调用 `stage_plugin_package(source: Path, target: Path) -> Path`（同一模块），它保留插件源码、manifest、测试及资源，排除 `.venv`、含 `pyvenv.cfg` 的环境目录、构建缓存与包级运行状态；不要在各插件中复制 ignore 规则。宿主的 v2 fixture 也直接使用整包暂存；迁移回归在暂存后显式构造历史状态文件，不保留旧布局适配器。testkit 自身测试位于 `packages/shiori-plugin-testkit/tests/`，根 pytest 和测试类型检查均显式覆盖。

## 可安装边界

- `shiori-agent` 是真实生产 Python 模块组成的私有 runtime wheel，使用显式包清单，不包含测试树、其他插件或用户状态。
- `shiori-plugin-default-memory` 是真实 `AppRuntime` 的必需依赖，由宿主明确声明。
- `shiori-plugin-testkit` 位于 `packages/shiori-plugin-testkit/`，只提供公共 fake、包资源定位和真实 `AppRuntime` 启动 fixture。安装后由 pytest entry point 注册。它不复制宿主测试树，也不伪造宿主 API。
- 每个插件的 wheel 只包含该插件后端及其声明资源，测试从插件副本运行。Story 显式依赖 NovelAI，Meme 显式依赖 citation；未声明的兄弟插件不能隐式获得。

上述包只在私有 wheelhouse 或本地开发环境使用，不发布 PyPI，也不承诺稳定 SDK。普通部署和 PyInstaller 打包入口保持不变。生产技能、配置模板及共享 emoji 由 `bootstrap.paths` 统一定位，wheel 构建和桌面 bundle 使用相同源资源。

## 插件副本运行

每个插件的 `TESTING.md` 都随包提供仓库外安装与运行命令。拿到插件副本及私有 wheelhouse 后，进入副本目录，先 `uv venv .venv --python 3.12`，再按该文件安装真实宿主、testkit、默认记忆与 `.[test]`，最后执行 `uv run --no-project --python .venv python -m pytest -c pyproject.toml tests`。私有 wheel 缺失时应补齐构建产物，不能改为导入原仓库。

## 仓库外验收

```sh
uv run python scripts/verify_plugin_tests.py --output /absolute/path/outside-repository/plugin-isolation
```

输出目录必须在仓库外且是新目录。不传 `--output` 会创建系统临时目录。可用 `--plugins novelai story` 只验证受影响插件；不传时发现所有具有 Python 测试的插件。`--jobs N` 控制 wheel 构建与插件验证的并发数，默认为 CPU 数；已知耗时最长的插件（telegram、feishu、qqbot）优先调度。

脚本将被测插件复制到输出目录，从副本构建 wheel，并构建真实宿主和 testkit wheel。每个目标有单独的干净 venv，仅安装宿主、testkit、目标与其声明依赖。闭包按实际安装的 `目标[test]` 计算：目标的 `project.dependencies` 与 `project.optional-dependencies.test` 都参与构建和来源审计；仅供测试的兄弟依赖（例如状态命令测试使用的 observe）应放在 test extra，不进入运行时依赖。传递兄弟插件只跟随运行时依赖和依赖边显式请求的 extras，不自动启用兄弟的 test extra。环境 marker 按实际测试解释器及已启用 extra 求值；testkit 单独构建，不当作插件目录。安装为非 editable；不会共享已安装的其他测试目标。子进程清空 Python/pytest 导入注入与服务凭证，不调用真实收费模型。

每个目标执行全部测试后验证宿主模块来自该环境的 site-packages、目标插件代码与副本一致、安装依赖闭包正确、没有 editable 安装；还实际读取内置技能、共享 emoji 并调用初始化流程复制配置模板。最后单独运行故意在 `await` 后失败的异步用例，要求退出码 1 和执行标记，证明 pytest 真正等待了协程。

`results.json`、`host-wheel-files.txt`、各包的 `pytest.log`、`provenance.json`、`async-failure.log` 是验收证据。预期失败的异步探针不算插件失败。wheel 构建失败会停止验证；单个插件的失败或依赖缺失不会中止其余插件，全部跑完后列出失败插件及其日志路径并以非零退出。`results.json` 在全部完成后统一写入，按插件排序，包含通过与失败条目及各自耗时。CI 在独立的 `plugin-isolation` job 中对全部插件执行此流程并上传证据，不能用只收集测试或跳过宿主集成用例替代。
