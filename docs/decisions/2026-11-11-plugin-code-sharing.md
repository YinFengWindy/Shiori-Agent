# 插件之间的代码复用归属

状态：2026-11-11 维护者确认。修订 [桌宠与独立形象插件](2026-11-09-desktop-pet-2d-providers.md) 中共享前端模块的位置；`packages/desktop-pet` 已按本文迁入桌宠。

## 背景

桌宠形象拆分（#1006–#1008）把形象插件共用的气泡、拖动、菜单、呈现协议和呈现控制器放进 `packages/desktop-pet`（`@yinfengwindy/shiori-pet`）。审查时曾用宿主的「同一段逻辑第二处出现就抽 helper」论证这个位置。这条规则针对单一 owner 的代码，套到插件之间会忽略两件事：插件需要彼此独立地安装、停用和升级；有依赖关系的主插件与子插件之间又确实存在共用逻辑。放在 `packages/` 的共享代码不属于任何插件，也不随主插件版本变化，契约改动无法通过插件版本约束表达。

## 规则

按插件之间的 manifest 关系决定代码放在哪里。

| 关系 | 复用方式 |
| --- | --- |
| 同一插件内部 | 按 AGENTS.md 的代码原则抽共享 helper / hook |
| 互不依赖的插件 | 不共享插件业务代码，也不为去重新建公共包或互相引用。小段重复可以接受 |
| 子插件声明 `dependencies` 依赖主插件 | 共用逻辑归主插件，作为主插件对子插件的公开接口，放在主插件目录下，随主插件版本发布 |
| 领域无关、宿主或多个互不依赖的插件都要用 | 进 SDK（宿主契约），或作为 `packages/` 下的独立库（如 `packages/mcp-client`） |

`packages/` 只放领域无关的库与宿主契约，不放某个插件私有的契约或界面套件。

### 主插件导出

- Python：运行时接口用 `ctx.expose(api)`，子插件经 `DEPENDENCIES` 取得。契约常量、类型等静态内容可以 import 已声明依赖的主插件模块，`scripts/plugin_import_contract.py` 只允许 import manifest 声明过的插件。子插件在 `pyproject.toml` 声明对主插件包的版本约束。
- 前端：主插件在自己目录里提供按包名引用的导出子路径，子插件按包名 import，不写跨插件相对路径，也不读主插件的非导出文件。
- 主插件导出的内容改变了契约时，主插件升版本，子插件同步更新版本约束。

### 前端是构建时快照

前端共享代码在构建时内联进子插件的 bundle，子插件运行的是构建那一刻的副本；Python 子插件在运行时导入已安装的主插件。因此主插件对子插件的前端导出只放稳定的协议定义与 UI 套件。运行时状态和决策仍以主插件为准，经 `SERVICES`、插件事件或 `client.dependency(...)` 的后台调用取得，不因代码共享而在子插件内复制主插件的判断。

### 通用工具

`isRecord` 这类与领域无关的小工具不经主插件导出。各插件自行持有，或在确有多处插件需要时提议进入 SDK。

## 对桌宠的影响

`packages/desktop-pet` 迁入 `plugins/desktop_pet/provider/`，作为桌宠对形象插件的前端导出，与 Python 侧已有的 `provider_presentation.py`、`provider_files.py` 等导出同归桌宠。桌宠的 `package.json`（`@shiori-plugin/desktop_pet`）只导出 `./provider` 与其样式，根 `package.json` 以 `link:` 引用，使形象插件按包名 import；桌宠自身代码用插件内相对路径。`isRecord`、`nonempty` 留在 `provider/guards.ts`，不进入导出；形象插件各自持有 `isRecord`。迁移在发版前进行，桌宠版本保持本轮唯一一次 patch（0.1.4）。
