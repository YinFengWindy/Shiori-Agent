---
title: 启动与关闭流程
kind: 流程说明
status: 当前有效
last_verified_commit: 0f870fd0
source_paths:
  - apps/backend/main.py
  - apps/backend/bootstrap/app.py
  - apps/backend/bootstrap/tools.py
  - apps/backend/bootstrap/runtime/
  - apps/backend/bootstrap/channels.py
  - apps/backend/bootstrap/channel_host.py
  - apps/backend/core/roles/role_runtime.py
  - apps/desktop/src/bridge/bridgeClient.ts
related:
  - ../architecture/current-backend.md
---

# 启动与关闭流程

## 当前启动

```mermaid
sequenceDiagram
  participant Main as main.py
  participant App as AppRuntime
  participant Core as build_core_runtime
  participant Plugin as PluginKernel
  participant Bridge as DesktopBridgeServer
  Main->>Main: ConfigTransaction.recover() / 固定插件文件迁移
  Main->>Main: apply_pending_plugin_operations() / MCP 自动启用 / Config.load()
  Main->>App: Config + workspace
  App->>App: 首次 start 幂等检查固定插件文件迁移
  App->>Core: prepare_core_runtime(build_core_runtime)
  Core->>Core: providers / sessions / roles / tools / memory
  App->>Core: CoreRuntime.start()
  Core->>Plugin: load_all()
  Plugin-->>Core: event handlers / channels
  Core->>Core: AgentLoop / spawn 绑定内核（回合与工具事件每次使用时读取）
  App->>App: GenerationManager.start(第 1 代)
  App->>App: start_channels() -> ChannelHost.start_all()
  App->>App: RuntimeDispatcher / outbound / RuntimeBackground 发布 scene；定时、主动与整理循环由插件拥有
  Main->>Bridge: create server
  Bridge-->>Main: serve_stdio()
```

`serve_bridge()` 运行期间把进程 stdout 重定向到 stderr，stdout 只留给 JSONL 协议。Python bridge 的 readiness 由 Electron `DesktopBridgeClient` 轮询 `health` 完成，`restart()` 负责重启子进程。

scene、schedule、mcp 和 proactive 的五个固定旧文件在插件加载前迁入 `plugin-data/`，已有新目标优先，旧来源核对后归档；失败阻止启动。迁移先于待执行安装/卸载，使用户要求的插件数据删除也覆盖迁入文件。`init_workspace` 在配置加载和预建空文件前执行同一迁移；直接调用 `AppRuntime.start()` 也会处理。代际准备和热重载不迁移文件。路径与恢复边界见[存储决策](../../decisions/2026-11-04-plugin-storage-paths.md)。

设置保存不重启进程：`AppRuntime.prepare()` 构建新一代 `CoreRuntime`，`publish()` 切换后旧代排空后关闭（见 [当前后端架构](../architecture/current-backend.md#运行时换代)）。

## 当前关闭

```mermaid
sequenceDiagram
  participant App as AppRuntime
  participant Loop as Bus / AgentLoop
  participant Gen as 各代 CoreRuntime
  participant Plugin as PluginKernel
  participant Store as Channels / Memory / HTTP
  App->>Loop: close inbound, stop control tasks
  App->>App: stop (cancel in-flight work) and drain RuntimeBackground
  App->>Gen: drain accepted work
  App->>Loop: drain outbound
  App->>Store: ChannelHost.stop_all()
  App->>Gen: stop(force)
  Gen->>Plugin: terminate_all()
  Gen->>Gen: EventBus close / provider close
  Gen->>Store: MemoryRuntime.aclose()
  App->>Loop: stop outbound dispatch, close EventBus
  App->>Store: SharedHttpResources.aclose()
```

各步骤经 `run_cleanup_steps(..., aggregate_errors=True)` 执行，单步失败不阻止后续清理，错误最终聚合抛出。

`RoleRuntimeRegistry.close()` 关闭单个 RoleRuntime 时先 `begin_closing()` 拒绝新工作，再取消已登记的 active work；active work 仍未归零时直接抛错，不能静默结束。
