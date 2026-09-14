# 插件开发

Shiori 只有一套显式 v2 插件运行时。插件提供 `manifest.yaml` 和异步 `setup(ctx)`，宿主按声明授予能力，并用作用域回收事件、阶段贡献、工具和后台任务。

## 包布局与发现

```text
plugins/example/
  manifest.yaml
  backend/
    plugin.py
    config.py
  ui/index.tsx         # 可选，主窗口贡献
  background/index.ts # 可选，app.background
  surface/index.tsx   # 可选，桌面 surface
  tests/test_plugin.py
  pyproject.toml
  TESTING.md
  README.md
```

后端扫描 `bootstrap.paths.plugin_roots()` 返回的插件根目录。开发态和桌面 bundle 使用顶层 `plugins/`；安装态使用已安装插件包。只有显式 `api: 2` 的 manifest 会成为插件，默认入口是 `backend/plugin.py`。入口作为包导入，内部可使用相对 import；同目录名先发现者优先，重复 manifest ID 会报错。

```yaml
api: 2
id: example
version: '0.1.0'
desc: 示例插件
capabilities:
  - config
  - events
  - lifecycle
  - rpc
config_model: config:ExampleConfig
supports_hot_unload: true
```

`capabilities` 必须显式列出，可以是空列表。只声明实际使用的能力；未授权属性访问会抛 `CapabilityNotGranted`。`config_model` 可以是入口中的类名，也可以是相对入口包的 `模块:类名`。模型必须继承 Pydantic `BaseModel`。

## setup 与配置

```python
# backend/config.py
from pydantic import BaseModel

class ExampleConfig(BaseModel):
    """Values editable through the plugin configuration channel."""
    label: str = "example"
```

```python
# backend/plugin.py
from agent.lifecycle.types import AfterTurnCtx
from .config import ExampleConfig

async def setup(ctx):
    """Registers this activation's contributions and cleanup."""
    config = ExampleConfig.model_validate(ctx.config.as_dict())

    async def after_turn(event: AfterTurnCtx):
        await ctx.rpc.emit("updated", {"label": config.label})

    async def read_label(payload):
        return {"label": config.label}

    ctx.events.on(AfterTurnCtx, after_turn)
    ctx.rpc.register("label.get", read_label)
```

运行配置来自 `[plugins.example]`。`enabled` 是宿主拥有的启停字段，不应放进插件模型。插件自己在 `setup` 校验读取值；宿主配置 schema 注册表为 `plugin.config.get/set` 提供 schema、默认值和写入校验。没有配置模型的插件不会得到自动表单。

桌面普通设置草稿不携带插件配置快照。保存时后端在同一配置事务锁内保留当前插件表，因此不会覆盖其它窗口刚完成的插件设置或启停更改。原始 `runtime.apply` 仍是整份配置替换；普通表单通过 `preserve_plugins: true` 明确选择保留语义。

## 能力与副作用

| 能力 | 用途 |
| --- | --- |
| `events` | `ctx.events.on(EventType, handler)`；卸载先停用并退订，再清理其它 effect，与登记先后无关 |
| `lifecycle` | `ctx.lifecycle.contribute(phase, modules)`；登记阶段模块 |
| `tools` / `tool_hooks` | 注册工具或工具执行前处理器 |
| `proactive_gates` | 贡献主动行为准入 gate |
| `channels` / `bot_commands` | 贡献渠道及机器人命令 |
| `rpc` | 注册 `plugin.<id>.<method>`，发送同命名空间事件 |
| `background` | `ctx.background.spawn(coro, name=...)`；卸载取消并等待任务 |
| `kv` | 工作区 `plugins/<id>/kv.json` 中的私有状态 |
| `config` | 本代插件配置快照 |
| `dependencies` | 读取已声明提供方的本代公开 API |
| `runtime` | 本代是否重载、前代是否活动，以及收尾任务登记 |
| `workspace` / `role_store` / `session_manager` / `memory_engine` | 获取宿主拥有的实际服务 |
| `scene_observations` / `role_runtime_registry` | 场景观察需求与角色运行时协作 |

能力名的完整权威清单位于 `agent/plugin_host/manifest.py`。不要自己构造另一份 RoleStore 来写同一份角色文件，应获取宿主共享的 `role_store`。能力是架构边界，不是 Python 进程内安全沙箱。

其它外部资源用 `ctx.effect("label", disposer)` 登记清理；disposer 可同步或异步。Python 插件作用域分两段处置：先停止接收新事件并撤销所有 `ctx.events.on` 订阅，再按登记的逆序（LIFO）清理其余 effect，包括自定义 disposer、后台任务与贡献。订阅和资源的登记先后不影响退订优先规则；其它资源之间仍需按依赖顺序登记，例如先登记 writer，再登记需要向 writer 最终 flush 的采集器，使采集器先清理。

开始处置后拒绝新订阅、后台任务和资源登记；即使总线已选中某个 handler，只要它尚未开始也不会再调用。已经执行中的 handler 不会被强制取消，插件应在 disposer 中取消或等待其持有的任务。`ctx.events.off` 使用原始 handler 的对象身份退订，移除同一 handler 的重复订阅，重复退订安全。一项清理失败不会跳过剩余 effect。初始化抛错使用相同规则撤销已登记贡献；再次启用使用新作用域，不能重复保留旧订阅。

## 阶段与依赖

阶段槽位为 `before_turn`、`before_reasoning`、`prompt_render`、`before_step`、`after_step`、`after_reasoning`、`after_turn`。模块声明唯一 `slot`、所需 `requires` 和导出的 `produces`；宿主核心拥有具体执行顺序与帧语义。

```python
from agent.lifecycle.types import PromptRenderCtx
from agent.prompting import PromptSectionRender

class ExamplePrompt:
    """Adds a prompt section after the host creates its prompt context."""
    slot = "example.prompt"
    requires = ("prompt_render.emit", "prompt:ctx")
    produces = ("prompt:ctx",)

    async def run(self, frame):
        ctx = frame.slots.get("prompt:ctx")
        if isinstance(ctx, PromptRenderCtx):
            ctx.system_sections_bottom.append(
                PromptSectionRender(name="example", content="Example context", is_static=True)
            )
        return frame

async def setup(ctx):
    """Contributes one scoped prompt module."""
    ctx.lifecycle.contribute("prompt_render", [ExamplePrompt()])
```

模块依赖其它插件提供的槽位时，还应在 manifest 声明插件依赖。例如 meme 的 `dependencies: [citation]` 保证 citation 先活动；提供方缺失、停用或失败时 meme 为 `BLOCKED`，不会显示活动但缺少提示词。卸载提供方会级联其强依赖消费者。

需要调用另一个插件的 API 时，提供方用 `ctx.expose(api)`，消费者声明 `dependencies` 和同名 capability，再调用 `ctx.dependencies.require("provider")`。只需要加载顺序时不必调用 `require`。可选提供方用 `optional_dependencies` 和 `get_optional`：它不会强制启动提供方，提供方不可用时返回 `None`，也不会触发消费者级联卸载。

## 热卸载与进程退出

`supports_hot_unload` 是严格布尔值，省略时为 `true`。不能可靠在进程内卸载的插件必须显式写 `false`。

- 正常卸载先检查目标和全部强依赖消费者；任一活动插件不支持热卸载，整次操作拒绝，所有实例保持活动。
- 当前设置修改采用整代准备/发布。如果当前代存在这类活动插件，插件启停、插件配置、普通或原始配置保存均返回 `plugin_restart_required`，包含 `plugin_ids`，不启动候选、不写配置或角色数据、不切换 generation。完全相同配置与只改角色模型绑定的事务仍可执行。
- 用户应退出应用后修改配置，再重新启动；本轮没有“已保存、待重启”的第二份配置。
- 真正退出宿主、未发布候选失败/取消/丢弃，以及初始化回滚都强制回收已登记资源。声明不会豁免 effect 清理。

内核的 `unload`、`terminate_all` 及宿主 `CoreRuntime.stop` 正常入口遵守声明；`force` 仅供最终资源回收路径。普通退出仍按引用排空，不因强制清理而提前取消已接受的工作。

## 桌面 RPC、事件与 UI

`ctx.rpc.register("label.get", handler)` 注册 `plugin.example.label.get`。前端插件组件得到已绑定自身命名空间的 `client.call("label.get")`，不自行拼宿主 IPC。`await ctx.rpc.emit("updated", payload)` 通过 `PluginBridgeEvent` 与所属 generation 的服务下发 `plugin.example.updated`，旧代事件不会冒充新代。

主窗口在构建时发现 `plugins/*/ui/index.tsx`，默认导出 `PluginUiModule`：

```tsx
import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";

const exampleUi: PluginUiModule = {
  pluginId: "example",
  settingsSection: { kind: "schema", label: "Example" },
};
export default exampleUi;
```

已使用的插槽包括 `settings.section`（qqbot/novelai）、`nav.page`（story）、`role.assets`（desktop_pet）。角色设置与聊天图片动作也有独立贡献契约。插件 UI 只通过注入的服务和 RPC 协作，启停状态决定其可见性。

`app.background` 在隐藏的 plugin-host renderer 运行，入口是 `background/index.ts` 的 `{ pluginId, setup(ctx) }`。桌宠已通过它拥有控制器、surface、托盘项与订阅。它的 `BackgroundCtx` 不是 Python 上下文：通过自己的 `effect`、`events`、`rpc`、`surfaces`、`tray`、`store` 管理资源。使用 `surface/` 入口渲染独立桌面窗口。

通用命名空间事件已经存在；桌宠仍有的专用跨 renderer/宿主桥迁移由 #218 承接，屏幕观察/语音边界由 #220/#221 承接，不应据此新增宿主领域硬编码。

## 测试、安装与数据升级

测试放在本包 `tests/`，文件与 `backend/` 模块对应。通过显式安装的 `shiori-plugin-testkit` 使用公共 fake 与包暂存：

```python
from pathlib import Path
from shiori_plugin_testkit.packages import stage_plugin_package

PLUGIN_DIR = Path(__file__).resolve().parents[1]
# 在 tmp_path 下整包暂存，保留源码/manifest/资源，排除运行状态和构建缓存。
# staged = stage_plugin_package(PLUGIN_DIR, tmp_path / "plugins/example")
```

兄弟插件通过 `plugin_directory("citation")` 定位，并在 `pyproject.toml` 明确声明安装依赖；不得推导原仓库路径，也不得导入宿主测试树。异步测试由 pytest-asyncio 执行，公共支持来自 testkit 的 pytest entry point。宿主 fixture 仅存在于 `tests/conftest.py`。

仓库开发使用 `uv sync --dev`，再 `uv run pytest plugins/example/tests`。仓库外验收运行 `uv run python scripts/verify_plugin_tests.py --plugins example --output <仓库外新目录>`：从副本构建非 editable wheel，在独立环境运行真实插件测试，检查模块来源，并确认 await 后故意失败的异步断言真正执行。完整步骤见 [插件测试](../agents/plugin-testing.md) 与各包 `TESTING.md`。

旧停用标记仅由配置启动升级读取：按当前 manifest 身份写入缺失的 `[plugins.<id>].enabled = false`，显式配置优先。持久化失败保留原配置与标记，重试不会覆盖已保存选择；无法确认当前插件身份时保留标记，等待包可用。内核日常启停不读取标记。已归核心的主动/场景偏好保持各自升级逻辑。

通用 KV 位于 `agent/plugin_host/kv.py`，旧 `.kv.json` 的现存可恢复数据仍由 `plugin_data` 原子迁入工作区。历史 `plugin_config.json` 与 `config.local.toml` 的数据归位由 #214 独立跟踪；本轮删除旧 loader，不删除用户这些文件，也不把它们重新作为 v2 配置回退。

External package authors: see [External Plugin Runtime Contract v1](plugin-runtime-contract.md)
for the versioned distribution layout, compatibility gate, ESM/CSS requirements
and independent build example. The tutorial's bundled source-plugin workflow
continues to use the existing v2 path.
