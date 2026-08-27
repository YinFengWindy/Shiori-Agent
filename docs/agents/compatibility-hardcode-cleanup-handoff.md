# 兼容性与硬编码清理交接

> 关联 Issue：[ #104 refactor: 清理兼容性代码与硬编码 ](https://github.com/YinFengWindy/Shiori-Agent/issues/104)
>
> 状态：C01-C06、C08-C09 已逐项确认并完成删除，C07 保留为只读解析；其他候选项仍以各批次结论为准。本文同时记录已批准项和待确认项。

> 2026-08-27：E01-E04 已按当前产品决策完成。仓库根 `config.toml` 不再作为迁移来源；桌面 settings 只接受 runtime path contract 注入的 workspace 配置路径；开发环境变量已统一为 `SHIORI_*`。E05 保持现状，E06 已完成发布路径 manifest 集中化；E07-E15 已完成等价契约集中或保留型容错整理。
>
> 前置变更：PR #103 已将 Electron bridge/assets、桌面桥接 voice/TTS、Story internal helpers 做了低风险归位；根目录应用边界迁移继续由 Issue #102 跟踪。

> 路径说明：C/M/F 候选表保留了当时审计记录中的相对路径，便于与 Issue #104 的历史讨论对照。当前源码路径统一在 `apps/backend/` 或 `apps/desktop/` 下；E 批次及后续新记录应使用迁移后的完整路径。

## 使用方式

按 ID 逐项审查。每项需要先回答：

1. 当前是否仍有生产调用方、外部调用方或历史数据依赖？
2. 如果删除，是否需要一次性迁移、备份或回滚方案？
3. 这是历史兼容、运行时容错、部署契约，还是应该集中管理的产品常量？
4. 删除或重构后，需要哪些聚焦测试、类型检查、构建或运行时验证？

候选项没有经过批准前，不要删除兼容入口，也不要把 fallback 直接改成抛错。

## 第一批处理结论

2026-08-27，维护者确认本 PR 的第一批兼容入口清理范围。以下项目均已完成仓库内生产代码、测试和维护脚本的调用方核对；删除的是内部历史入口，权威实现路径已在对应模块中保留。仓库不将这些旧路径作为受支持的公共 API 发布。

| ID | 结论 | 核对结果 |
| --- | --- | --- |
| C01 | 删除旧 voice/TTS re-export | 旧 `desktop_bridge` 根路径调用已迁移到 `desktop_bridge/voice/`；保留模块不变。 |
| C02 | 删除 Story internal 旧 re-export | 生产代码和测试已使用 `story_simulation.internal` 的权威实现。 |
| C03 | 删除旧 Story migration wrapper | 迁移调用已统一到 `migrate_story_timeline()`，没有旧入口调用方。 |
| C04 | 删除 `build_vl_provider()` 假兼容 API | 没有生产或维护脚本调用；当前 provider disabled 语义由现有配置路径表达。 |
| C05 | 删除 NovelAI 私有 `_auto_cg_tasks` 转发 | 调用方直接使用 controller 状态 API，未保留旧私有别名。 |
| C06 | 删除 `HyDEAugmentResult.__iter__` 旧解包兼容 | 调用方使用结构化结果字段，未发现二元解包调用。 |
| C07 | 保留只读兼容解析 | 历史 context marker 仍可能出现在已保存消息中，不做 destructive rewrite。 |
| C08 | 删除 QQ channel/stream 旧 facade | 内部调用和测试已迁移到 owning formatting 模块。 |
| C09 | 删除 conversation package-level 旧导出 | `LegacySessionDescriptor` 等当前调用方直接从 owning module 导入。 |

## 第一批：高概率可清理的兼容 Shim

| ID | 位置 | 当前行为 | 审查重点 |
| --- | --- | --- | --- |
| C01 | `apps/backend/desktop_bridge/voice_service.py`、`apps/backend/desktop_bridge/voice/voice_providers.py`、`apps/backend/desktop_bridge/voice/voice_models.py`、`apps/backend/desktop_bridge/voice/voice_http.py`、`apps/backend/desktop_bridge/voice/voice_handler.py`、`apps/backend/desktop_bridge/voice/voice_assets.py`、`apps/backend/desktop_bridge/voice/tts_text.py`、`apps/backend/desktop_bridge/voice/tts_coordinator.py`、`apps/backend/desktop_bridge/voice/role_tts_settings.py` | 旧模块路径 re-export 到 `apps/backend/desktop_bridge/voice/`。 | 全仓没有旧路径 import；确认外部消费者或历史脚本后，可成组删除。 |
| C02 | `apps/backend/story_simulation/_json.py`、`apps/backend/story_simulation/_schema.py` | 移动到 `apps/backend/story_simulation/internal/` 后保留旧导出。 | 生产代码已改用新路径；当前旧路径只被兼容测试引用。 |
| C03 | `apps/backend/story_simulation/schema_migrations.py:100-103` | `migrate_legacy_story_time()` 转发到 `migrate_story_timeline()`。 | 当前生产调用方使用新入口；测试引用清理后可删除。 |
| C04 | `apps/backend/bootstrap/providers.py:33-35` | `build_vl_provider()` 保留兼容签名但固定返回 `None`。 | 搜索旧调用方；若为空，删除假 API 或改成显式 disabled。 |
| C05 | `apps/backend/plugins/novelai/plugin.py:85-88` | `_auto_cg_tasks` 仅转发 controller 状态。 | 确认外部调用；否则改用公开 controller 状态 API。 |
| C06 | `apps/backend/memory2/hyde_enhancer.py:33-46` | `HyDEAugmentResult.__iter__` 支持旧式二元解包。 | 旧调用清零后可删除；否则记录移除版本。 |
| C07 | `apps/backend/agent/prompting/assembler.py:58-67` | 接受旧 `[SYSTEM_CONTEXT_FRAME]` marker。 | 确认历史消息是否仍可读取；若保留，应限制为只读解析。 |
| C08 | `apps/backend/infra/channels/qq_channel/__init__.py:14-20`、`apps/backend/plugins/qqbot/channel.py:116-128` | 暴露旧 channel/stream helper facade。 | 迁移测试和内部调用到权威 formatting 模块。 |
| C09 | `apps/backend/conversation/__init__.py` | 已移除 `ConversationMigrator` re-export；`LegacySessionDescriptor` 由运行时调用方直接从 `apps/backend/conversation/service.py` 导入。 | 不再保留 package-level 兼容导出。 |

## 第二批：必须先确认数据存量的迁移链

| ID | 位置 | 当前行为 | 删除前置条件 |
| --- | --- | --- | --- |
| M01 | `apps/backend/core/common/workspace.py:9-57` | `.akashic` workspace、ncatbot 目录和媒体路径迁移到 `.shiori`。 | 确认旧安装存量；必要时改成显式迁移命令。 |
| M02 | `apps/backend/core/roles/config_migration.py:26-182` | 导入旧角色绑定和旧全局 proactive 配置。 | 统计旧 JSON 存量，确认迁移状态文件和默认值。 |
| M03 | `apps/backend/core/roles/manifest.py:36-85` | `featured_image -> chat_background`，补 asset categories 并写回角色清单。 | 确认旧版本角色文件已升级，增加 schema version 检查。 |
| M04 | `apps/backend/conversation/store.py` session/thread API | `sessions/messages` 与 thread/contact 共享同一 DB，`legacy_session_key` 仍是实时渠道 session 到 thread 的映射键。 | `SessionManager` 和当前渠道运行时仍在使用，不能删表或映射字段。 |
| M05 | `apps/backend/conversation/migrator.py`、`apps/backend/bootstrap/conversation.py` | 已移除启动扫描和旧渠道 session 到 thread/contact 的数据回灌。 | 旧渠道 session/消息已主动清空，不保留迁移入口。 |
| M06 | `apps/backend/conversation/service.py:13-18,59-145,336-368` | `LegacySessionDescriptor` 将当前渠道 session 映射为正式 thread，仍会处理未绑定渠道。 | `apps/backend/core/channels/hub.py`、`apps/backend/agent/turns/orchestrator.py`、`apps/backend/conversation/push_sync.py` 仍构造 descriptor，不能按 M05 删除。 |
| M07 | `apps/backend/session/manager/role_sessions.py` | 已移除旧 transport history 合并、provenance 和防回灌元数据。 | 角色会话仅保存自身的运行时历史。 |
| M08 | `apps/backend/session/manager/__init__.py` | 已移除 facade module 与跨模块 monkeypatch 转发。 | 生产模块直接依赖 owning module，现有测试没有 facade patch 调用方。 |
| M09 | `apps/backend/story_simulation/schema_migrations.py:17-98,106-216` | 迁移旧 Story 时间、资源字段，并 DROP 旧列。 | 先备份/验证历史 DB；审查 `1970-01-01`、`上午` 和失败资源语义。 |
| M10 | `apps/backend/story_simulation/story_time.py:60-89` | 仅用于旧 Story timestamp 的解析。 | Story DB 迁移完成后再删除。 |
| M11 | `apps/backend/plugins/observe/migrate_legacy_rag.py:13-127` | 旧 RAG 表转为新表并 DROP 老表。 | 当前主要是 CLI/测试；应移出常规启动路径并保留回滚说明。 |
| M12 | `apps/backend/plugins/observe/db.py:122-143` | 每次打开 DB 自动补列并删除旧 proactive observe 数据。 | 这是 destructive migration，必须有 schema version、备份和恢复验证。 |
| M13 | `apps/backend/core/memory/markdown_schema.py:57-131,216-223` | 打开角色记忆时重写旧 headings 和内容。 | 检查历史文件覆盖风险，改为一次性迁移并保存 diff/备份。 |

### 2026-08-26 存量审计与已处理项

- 已移除 M02、M03、M09-M13 的运行时兼容处理：当前 `roles.json` 已是 v2，当前 Story DB 与已有备份均没有旧时间/资源列，Observe DB 没有旧 RAG 表或 proactive 数据，角色记忆没有旧 headings。角色清单现只接受 v2；初始化角色记忆不再改写已存在文件；Observe 打开数据库不再删除记录或表。
- M02 的 `roles/channel_bindings.json` 仍存在 4 条记录，但 `config_migration_state.json` 已标记完成；本轮未删除任何 workspace 文件。
- M01 已完成：创建 `workspace/.migration-backups/m01-20260826-202047/`，其中包含 SQLite 一致性备份、77 个 JSON 原件和 manifest；恢复探针确认备份仍有迁移前的 71 个媒体引用与 88 个 JSON 路径值。已改写 65 个消息媒体路径和 83 个 JSON 路径，清空 6 个失效消息附件与 3 个失效 `base_image_path`，删除 2 个无运行时读取的历史报告。live workspace（排除备份）已无 `.akashic` 引用。
- 用户已确认旧渠道 session/消息已主动删除。因此 M05 启动迁移与 M07 历史回灌已退役；M04、M06 与 M08 中仍承载当前运行时会话、渠道 thread 映射或模块边界兼容的部分，必须按实际调用方逐项处理。

### F 阶段已确认方案

以下内容是逐项讨论后确认的设计，尚未全部实施：

- **F01**：保留 ncatbot WebSocket timeout patch。当前依赖版本仍在 adapter 内硬编码 `open_timeout=1`；后续只收紧适配边界和错误报告，不复制第三方 Adapter。
- **F02**：保留单渠道失败不阻塞其他渠道的行为；构造/启动失败通过 `ChannelHost.failures` 暴露 `channel`、`phase`、`error_type` 和 `message`。实现已提交，待 F 阶段方案整体确认后继续。
- **F03**：保留 outbound 的 `bool` 成功契约。空消息、缺目标和业务层明确拒绝返回 `False`；未注册渠道、网络或其他未知外部异常不再统一吞掉，必要时包装为 `OutboundDispatchError`。
- **F04**：保留 sqlite-vec 不可用时的全表扫描；集中暴露 vector backend 状态和降级原因，区分未安装、初始化失败和查询维度不匹配，不改变结果排序和默认阈值。
- **F05**：分离上游真实事件 ID、dedupe key 与时间解析状态。缺少 upstream ID 时只生成稳定 dedupe key，不伪装成真实事件 ID；坏时间事件保留错误原因并拒绝进入可调度队列。
- **F06**：主动任务 scope 由现有 `default_role_id` 或 `role:<role_id>` session key 判定，不新增 scope 字段。角色任务只能使用角色 binding resolver 返回的目标，解析失败即 no-target；只有全局任务可回退到 `default_channel/default_chat_id`。
- **F07**：MCP 通用调用默认不重放。仅代码中明确为读取的 get/context 工具可声明一次 transport retry；超时、响应中断、poll、ack 及其他未声明幂等的工具只清理连接并把结果未知的错误上抛。JSON-RPC 业务错误改为结构化 tool error，不以字符串协议驱动重试。
- **F08-F10**：本轮跳过，不调整 query rewriter、检索 lane 降级或 proactive loop 健康策略。
- **F11**：全局 `MemeCatalog` 回退是允许的产品行为。角色素材优先，角色素材缺失时可以使用全局 meme 素材；本项不再改动。
- **F12**：移除历史全局 `proactive.agent_tick` 输入的兼容读取、校验和字段映射。当前权威入口是角色详情页的 `proactive.agent`、`proactive.drift`；角色持久化、桌面编辑和运行时装配不作调整，也不新增迁移提示或专门拒绝逻辑。
- **F13**：保留去重解析器中明确且可证明安全的旧输出修复（`merge` 别名、1-based index），但把修复和非法输出区分为结构化原因。未知 id/index、冲突动作、多 merge 或缺少明确 merge 目标时走保守 `skip`，不再把格式问题静默当作 `create`；provider/JSON 调用失败仍与解析错误分开处理。
- **F14**：`stories.create` 的 `creation_id` 是必填业务幂等键，不回退到 transport `request_id`。`story_id` 继续由后端创建后生成，保持实体主键与创建请求键分离；renderer 当前传递链保持不变，补齐 bridge 缺字段测试。
- **F15**：移除 Story service 对 `ProviderStoryDirector(provider=None, model="")` 的占位 fallback，改为显式失败 director。正常角色运行时解析和 provider 路径不变，缺依赖时返回 `StoryProviderUnavailableError`。
- **F16**：跳过。LF/CRLF、BOM 和混合换行处理是文件编辑工具的跨平台契约，已有聚焦测试，不按旧兼容代码删除。
- **F17**：保留 context MCP 的公开 `dict` / `list[dict]` 双形态契约。顶层非法返回改为显式源错误，由现有单源隔离边界记录并继续其他源；list 内非法项可继续跳过并保留有效项。

## 第三批：运行时 fallback 与异常吞错

| ID | 位置 | 当前行为 | 审查重点 |
| --- | --- | --- | --- |
| F01 | `apps/backend/infra/channels/qq_channel/compat.py:18-45` | 对 ncatbot 的 websocket 全局 monkey patch，失败只 warning。 | 确认第三方版本是否仍需补丁；优先改显式 adapter/版本检查。 |
| F02 | `apps/backend/bootstrap/channels.py:66-101`、`apps/backend/bootstrap/channel_host.py` | 渠道构造或启动异常时继续让其他渠道运行，并通过 `ChannelHost.failures` 暴露结构化失败状态。 | 已保留独立渠道隔离语义；调用方可据 `channel/phase/error_type/message` 展示健康状态。 |
| F03 | `apps/backend/agent/turns/outbound.py:65-96` | push 任意异常都转成 `False`。 | 区分参数不可发送与外部调用异常，避免业务层吞错。 |
| F04 | `apps/backend/memory2/store/connection.py:14-103`、`apps/backend/memory2/store/vector.py:209-220` | sqlite-vec 失败后全表扫描。 | 确认是否产品必需；若允许降级，增加规模阈值、状态和指标。 |
| F05 | `apps/backend/proactive_v2/event.py:45-55,98-164` | 缺 upstream id 时生成 SHA1 fallback id，坏时间静默忽略。 | 区分 dedupe key 与真实 event id；无 ID 或坏时间应可观测。 |
| F06 | `apps/backend/agent/core/proactive_turn/delivery.py:243-257` | target resolver 失败回退全局默认 channel/chat。 | 确认 role-scoped target 是否已经是唯一权威来源。 |
| F07 | `apps/backend/proactive_v2/mcp_sources.py:145-199` | 任意异常断开、重连并重试一次。 | 仅对 transport 错误重试；确认工具幂等性。 |
| F08 | `apps/backend/memory2/query_rewriter.py:35-72,110,133-137` | LLM 判断失败时默认开启 episodic retrieval，procedure 返回空。 | 保留产品容错时增加 decision source/metrics。 |
| F09 | `apps/backend/memory2/retriever.py:183-231` | embedding 失败跳过向量 lane，继续 keyword lane。 | 降级应返回 metadata，并设置连续失败告警。 |
| F10 | `apps/backend/proactive_v2/loop.py:328-345,394-419` | feed/tick 异常只记录并继续循环。 | 增加连续失败、backoff、健康状态或熔断。 |
| F11 | `apps/backend/plugins/meme/runtime.py:177-191,251-252` | 角色素材缺失时回退全局 MemeCatalog。 | 确认是否允许角色隔离边界被全局素材穿透。 |
| F12 | `apps/backend/proactive_v2/config_loader.py` | 已移除历史全局 `agent_tick` 输入兼容；角色级 `agent` / `drift` 是唯一输入。 | 角色设置、持久化和启动装配保持当前契约。 |
| F13 | `apps/backend/memory2/dedup_decider.py:188-273` | 已保留明确旧输出修复，并区分 legacy repair 与 invalid output；不确定结果保守 skip。 | 解析原因结构化，避免格式错误继续 create。 |
| F14 | `apps/backend/desktop_bridge/story_simulation_handler.py:119-155,651-655` | `creation_id` 收口为必填业务幂等键，不再回退 transport `request_id`。 | `story_id` 继续由后端生成；补齐缺字段测试。 |
| F15 | `desktop_bridge/story_simulation_handler.py:629-634` | 无 director 时不再构造 `provider=None` 占位 director，改为显式失败 director。 | 正常角色运行时 provider 路径保持不变。 |
| F16 | `apps/backend/agent/tools/filesystem.py:58,503-524` | 本轮跳过；LF/CRLF、BOM 与混合换行是保留的跨平台契约。 | 继续使用现有测试覆盖。 |
| F17 | `apps/backend/proactive_v2/mcp_sources.py:234-257` | 保留 context 的 dict/list 双形态；顶层非法返回显式源错误，单源隔离继续生效。 | list 内非法项保留有效项并可记录计数。 |

## 第四批：Electron、Bridge 与环境硬编码

| ID | 位置 | 当前行为 | 审查重点 |
| --- | --- | --- | --- |
| E01 | `apps/desktop/src/runtimePaths.ts` | 已移除仓库根 `config.toml` 的 legacy 读取和迁移入口；首次启动只从 `config.example.toml` 创建 workspace 配置。 | 已完成；不再保留迁移窗口。 |
| E02 | `apps/desktop/src/paths.ts`、`apps/desktop/src/main.ts`、`apps/desktop/scripts/dev.mjs` | 开发服务器 URL、端口和临时 user-data 目录统一使用 `SHIORI_*` 环境变量。 | 已完成；旧 `MIRA_*` 名称不再兼容读取。 |
| E03 | `apps/desktop/src/settings.ts` | settings 不再拥有仓库根配置默认路径，必须由 main 注入 runtime path contract 的 workspace 配置路径。 | 已完成；未初始化时显式失败。 |
| E04 | `apps/desktop/src/runtimePaths.ts` | workspace、config 和 bridge 参数由 runtime path contract 的共享 helper 统一推导，开发/打包只保留 executable 与 prefix 差异。 | 已完成；后续路径变更从该 contract 扩展。 |
| E05 | `apps/desktop/scripts/dev.mjs:14,20,26-40` | 默认端口 `5173`、localhost 绑定、20 次端口尝试。 | 区分开发方便性和 window security 白名单。 |
| E06 | `apps/desktop/scripts/release-manifest.mjs`、`build-runtime.mjs`、`package-win.mjs`、`verify-packaged.mjs`、`hash-release.mjs` | release build、runtime、installer 和 unpacked 校验目录统一由 manifest 计算；`SHIORI_RELEASE_OUTPUT` 仍可覆盖最终 installer 输出。 | 已完成；后续仓库目录迁移优先调整 manifest，不改变交付语义。 |
| E07 | `apps/desktop/src/assets/localAssetRegistry.ts:13,96` | 本地资源上限固定为 `32 MiB`。 | 已完成；由 `localAssetContract.ts` 集中，并与 bridge/import policy 共用，默认值不变。 |
| E08 | `apps/desktop/src/settings.ts:211,216,315` | ASR/TTS/NovelAI endpoint 固定在 Electron 默认值。 | 已完成；由 desktop settings contract 集中，保持与现有 `config.example.toml` 和 integration 默认值相同的值。 |
| E09 | `apps/desktop/src/bridge/shared.ts`、assets 模块 | `shiori-asset` 协议字面量多处重复。 | 已完成；由 local asset contract 集中，安全边界和协议值不变。 |
| E10 | `apps/desktop/src/bridge/bridgeClient.ts:7-14,103-125,284` | bridge health/start/request/image/observation/stop 超时分散。 | 已完成；由 command timeout policy 集中，按现有 command 分类保持默认值。 |
| E11 | `apps/backend/desktop_bridge/voice/voice_http.py:81,111,172` | 多处重复网络 `timeout=60`。 | 已完成；由 `VOICE_HTTP_TIMEOUT_SECONDS` 集中，超时值不变。 |
| E12 | `apps/backend/desktop_bridge/voice/voice_providers.py:40,608` | 音频时长、bitrate 固定。 | 已完成；集中已有 ASR/MiniMax 音频协议常量，不调整 provider 默认值。 |
| E13 | `apps/desktop/renderer/src/roles/roleFormState.ts:21-29,49-54,104-109` | proactive 默认值在 build/load/dirty 三处重复。 | 已完成；由 role proactive defaults 统一，稀疏历史角色仍按原语义加载和 dirty 比较。 |
| E14 | `apps/desktop/renderer/src/chat/chatModelSelection.ts:7,25-36,51-52` | 非法 model effort 回退 registration effort/`none`。 | 已完成；由 shared renderer normalizer 只接受合法值，保留原有 registration effort/`none` 回退。 |
| E15 | `apps/desktop/renderer/src/story/storyBeatPresentation.ts:15-18` | 多种引号正则兼容 mixed legacy beat text。 | 已完成；保留 renderer-only legacy quote 解析，覆盖中文引号和尾随叙述，不改写已提交 Story transcript。 |

## 第五批：产品硬编码与测试夹具

这些项目通常不是直接删除，而是确认权威来源、集中管理并保留测试证据。

- H01 `apps/backend/proactive_v2/config.py`：channel、poll/tick interval、score threshold、interrupt floor、agent/drift limits。
- H02 `apps/backend/memory2/retriever.py`：keyword floor、embedding timeout、score threshold、注入字符数和强制记忆数。
- H03 `apps/backend/agent/provider.py:204-230,440-474`：request timeout、重试次数和 retryable error 集合。
- H04 `apps/backend/bootstrap/providers.py:6-7`：provider timeout `45s`，以及 light provider 返回 `None` 的旧契约。
- H05 `apps/backend/infra/channels/telegram_utils/live_edit.py:21-25`：Telegram 长度上限、更新间隔、flood/backoff。
- H06 `apps/desktop/src/pet/momentum.ts`、`apps/desktop/src/pet/controller.ts`、renderer pet interaction：拖拽、衰减、速度和 duration 常量。
- H07 `apps/desktop/src/voice/interactionState.ts:5`、`apps/desktop/src/observation/bubble.ts:3`：长按和 bubble duration。
- H08 `apps/desktop/renderer/src/chat/chatMessageWindow.ts`、`apps/desktop/renderer/src/chat/chatMessageImageLayout.ts`、`apps/desktop/renderer/src/chat/ChatSurface.tsx`：消息窗口、图片和拖拽 UI 阈值。
- H09 `apps/desktop/renderer/src/story/storyPreferences.ts`、`apps/desktop/renderer/src/story/storyMenuTheme.ts`：音量、文字速度、图像采样和色彩量化参数。
- H10 `apps/desktop/renderer/src/image/useImageStudioState.ts:30`、`apps/desktop/renderer/src/image/ImageFormPanel.tsx:49,281`：NovelAI 默认模型、最大尺寸和 preset fallback。
- H11 `apps/backend/desktop_bridge/role_difference_service.py:127`、`apps/backend/desktop_bridge/stream_writer.py:20`、`apps/backend/desktop_bridge/voice/tts_text.py:7,40`：steps、queue size、TTS sentence max length。
- H12 `apps/desktop/src/windowSecurity.ts:41-85`：localhost、CSP、`shiori-asset` 安全边界；通常应保留，只集中协议常量。
- H13 `apps/desktop/src/voice/hotkey.ts`：uiohook 扫描码映射，是第三方库契约，不是普通业务配置。
- F01 测试中的 `C:\...`、`D:\...`、`mira.png`、`legacy-asset://`：单独判断 portability 或旧协议拒绝测试，不与生产硬编码混删。

## 实施与验证约束

- 每次只处理一个 ID 或同一迁移链中的一组文件。
- 先执行全仓调用方和历史数据存量检查，再决定删除、迁移或保留。
- destructive migration 必须有备份、回滚和真实旧数据验证。
- fallback 若保留，增加 error kind、degraded 状态或指标，避免静默吞错。
- 常量集中化不能改变既有默认值，先添加等价测试再移动来源。
- 每批运行对应 Python tests、Desktop tests、typecheck/build；涉及运行时路径时必须做 Electron smoke。
- 完成批次后运行 `graphify update .`，必要时同步 `docs/knowledge/` 的 source paths 和验证提交。

## 建议审查顺序

1. C01-C09：低风险 shim，先清理无生产调用的旧路径。
2. M09-M13：涉及数据写入或 DROP 的迁移链，先做存量与备份确认。
3. M04-M08：Conversation/Session legacy 链，必须先改生产调用方。
4. F01-F17：按风险从异常吞错、sqlite-vec、MCP 重试开始。
5. E01-E15、H01-H13：最后做路径和产品常量集中化。
