# 插件指南

插件包在 `plugins/<id>/`：`manifest.yaml`、`backend/`、可选的 `ui/`、`surface/`、`background/` 和 `tests/`。方法签名以 [API 参考](plugin-api.md) 为准，那份文件由 `python -m scripts.gen_plugin_api` 从源码生成。版本记录见 [插件变更](plugin-changelog.md)。

## manifest

只接受整数 `api: 4`。同时声明最低 SDK 约束，基线是：

```yaml
api: 4
sdk: ">=4.0.0"
```

`sdk` 是空格分隔的 `=`、`>`、`>=`、`<`、`<=` 比较，逻辑与。省略、写错语法，安装和发现都是 `invalid_manifest`。约束不包含当前 SDK 时，安装被拒绝，已安装的包在名册里是 `BLOCKED` / `incompatible_sdk`，内置包也同样，不会中断整个启动。`api` 不是整数 4 时是 `unsupported_api`。

`inject`、`optional_inject`、`provides` 写服务 Key 的名字。`ctx.require` 只取 `inject` 里声明过的 Key，`ctx.get` 只取 `optional_inject`，`ctx.provide` 只发布 `provides`。没声明就失败。宿主没有提供某个已声明的 Key 时，setup 失败并留下 `PluginDiagnostic`。

`runtime_api`、`capabilities`、`package_contract` 和顶层 `channels` 已删除。渠道写在 `contributes.channels`，并且 `inject` 含 `channels`。`renderer` 与 `peer_dependencies` 保留到前端入口统一（P7）。

## 内核

`setup(ctx)` 收到 `shiori_sdk.kernel.Context`。插件用的是这一面：

- `require` / `get` / `provide`：按 Key 取服务或发布服务。
- `on` / `watch` / `emit`：有序处理事件，或在链结束后旁观。`on` 可以返回替换后的事件，或 `Veto`。
- `effect`：登记卸载时要跑的清理。
- `spawn`：插件自己的任务，卸载时取消。
- `on_drain`：热重载前的额外排空。

`ctx.plugin_id`、`ctx.log`、`ctx.config`、`ctx.data_dir` 是本插件的身份、日志、配置和数据目录。宿主用同一个 `Kernel` 在插件启动前 `provide` 它拥有的 Key。

## 版本

SDK 独立 semver，源只在 `packages/sdk/python/shiori_sdk/_version.py`。大版本是破坏性变更。4.x 内禁止给已有 Key 或 Protocol 加方法；新能力用新 Key 或新 Event。下一个大版本可以合并拆开的 Key，不要把 `SESSIONS_PRESENCE_V2` 这种名字一直留着。

npm 包、宿主 `setup.py` 和 host-testing 的精确 pin 必须等于这个版本。`node scripts/check_sdk_release.mjs --align` 只核对这三处。正式 tag 再跑完整检查：拒绝回退，也拒绝已发布 tag 上的同版本源码被改掉。没有 Unreleased 批次，也没有 `sync_sdk_version.mjs`。

插件自己的 `version` 独立。SDK 升大版本不因此给每个插件升 patch。插件的 `shiori-sdk` 依赖要承认它实际要跑的 SDK；本仓库插件是 `>=4.0.0,<5`。

## 4.0 基线里的插座

回滚在 `SESSIONS`：`last_passive_turn`、`rollback_last_turn`。记忆引擎的 `rollback_turn` 在 `MEMORY_ENGINE` 上。

在场心跳在 `SESSIONS.presence`：`record_user_message`、`last_user_at`、`record_initiated_sent`、`last_initiated_at`。表列仍是 `last_user_at` / `last_proactive_at`。`role:` 会话用原 key，其他会话在有 `metadata.role_id` 时记到 `role:<id>`。

角色命名空间在 `ROLES.plugin_settings(role_id, namespace)`。目前只有 `proactive`，宿主仍用核心的主动配置解析它，直到主动行为移出核心。写入这条路径不会清掉 candidates。渲染侧的 `roleSettings` 槽已经存在，不是这次新加的。

`CONVERSATION.deliver_initiated_reply(session_key, reply, source)` 和事件 `InitiatedMessageCommitted` 在契约里。宿主要在主动投递 generalize、4.0 桌面发出之前提供这个 Key。现在还没有提供方：声明 `inject: [conversation]` 的插件会因缺少提供方而 BLOCKED。4.x 不能事后再给这个 Protocol 加方法，所以签名先放进 4.0。

## 测试

插件测试只用 `shiori_sdk.testing`。`FakePluginContext` 把内核调用交给真正的 `Kernel`，服务用 testing 里的 stub。`KernelHarness` 是同一套内核的显式入口。不要导入 `tests.support`、`shiori_host_testing` 或 `apps/backend`。

仓库外的验收是 `python -m scripts.verify_plugin_tests`：用 SDK wheel 和插件 wheel 安装，不把宿主放进 `sys.path`。CI 的 `plugin-isolation` 跑的就是它。

## 还留在 SDK 里的东西

内核、`shiori_sdk.core` 的 Key / Protocol / Event、testing（真内核 + stub），以及插件仍在导入的 helper：渠道、文件、进程、记忆类型、账号、消息、SQL、命令和提示词。P4 删掉的是 `ctx` 上的 capability 属性；这些模块现在就是插座契约和测试 stub，不是第二套 capability 镜像。
