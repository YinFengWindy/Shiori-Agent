# 兼容性与硬编码清理交接

> 关联 Issue：[ #104 refactor: 清理兼容性代码与硬编码 ](https://github.com/YinFengWindy/Shiori-Agent/issues/104)
>
> 状态：只读审计完成，候选项待逐项确认。本文不是已批准的删除计划。
>
> 前置变更：PR #103 已将 Electron bridge/assets、桌面桥接 voice/TTS、Story internal helpers 做了低风险归位；根目录应用边界迁移继续由 Issue #102 跟踪。

## 使用方式

按 ID 逐项审查。每项需要先回答：

1. 当前是否仍有生产调用方、外部调用方或历史数据依赖？
2. 如果删除，是否需要一次性迁移、备份或回滚方案？
3. 这是历史兼容、运行时容错、部署契约，还是应该集中管理的产品常量？
4. 删除或重构后，需要哪些聚焦测试、类型检查、构建或运行时验证？

候选项没有经过批准前，不要删除兼容入口，也不要把 fallback 直接改成抛错。

## 第一批：高概率可清理的兼容 Shim

| ID | 位置 | 当前行为 | 审查重点 |
| --- | --- | --- | --- |
| C01 | `desktop_bridge/voice_service.py`、`voice_providers.py`、`voice_models.py`、`voice_http.py`、`voice_handler.py`、`voice_assets.py`、`tts_text.py`、`tts_coordinator.py`、`role_tts_settings.py` | 旧模块路径 re-export 到 `desktop_bridge/voice/`。 | 全仓没有旧路径 import；确认外部消费者或历史脚本后，可成组删除。 |
| C02 | `story_simulation/_json.py`、`story_simulation/_schema.py` | 移动到 `story_simulation/internal/` 后保留旧导出。 | 生产代码已改用新路径；当前旧路径只被兼容测试引用。 |
| C03 | `story_simulation/schema_migrations.py:100-103` | `migrate_legacy_story_time()` 转发到 `migrate_story_timeline()`。 | 当前生产调用方使用新入口；测试引用清理后可删除。 |
| C04 | `bootstrap/providers.py:33-35` | `build_vl_provider()` 保留兼容签名但固定返回 `None`。 | 搜索旧调用方；若为空，删除假 API 或改成显式 disabled。 |
| C05 | `plugins/novelai/plugin.py:85-88` | `_auto_cg_tasks` 仅转发 controller 状态。 | 确认外部调用；否则改用公开 controller 状态 API。 |
| C06 | `memory2/hyde_enhancer.py:33-46` | `HyDEAugmentResult.__iter__` 支持旧式二元解包。 | 旧调用清零后可删除；否则记录移除版本。 |
| C07 | `agent/prompting/assembler.py:58-67` | 接受旧 `[SYSTEM_CONTEXT_FRAME]` marker。 | 确认历史消息是否仍可读取；若保留，应限制为只读解析。 |
| C08 | `infra/channels/qq_channel/__init__.py:14-20`、`plugins/qqbot/channel.py:116-128` | 暴露旧 channel/stream helper facade。 | 迁移测试和内部调用到权威 formatting 模块。 |
| C09 | `conversation/__init__.py` | 已移除 `ConversationMigrator` re-export；`LegacySessionDescriptor` 由运行时调用方直接从 `conversation.service` 导入。 | 不再保留 package-level 兼容导出。 |

## 第二批：必须先确认数据存量的迁移链

| ID | 位置 | 当前行为 | 删除前置条件 |
| --- | --- | --- | --- |
| M01 | `core/common/workspace.py:9-57` | `.akashic` workspace、ncatbot 目录和媒体路径迁移到 `.shiori`。 | 确认旧安装存量；必要时改成显式迁移命令。 |
| M02 | `core/roles/config_migration.py:26-182` | 导入旧角色绑定和旧全局 proactive 配置。 | 统计旧 JSON 存量，确认迁移状态文件和默认值。 |
| M03 | `core/roles/manifest.py:36-85` | `featured_image -> chat_background`，补 asset categories 并写回角色清单。 | 确认旧版本角色文件已升级，增加 schema version 检查。 |
| M04 | `conversation/store.py` session/thread API | `sessions/messages` 与 thread/contact 共享同一 DB，`legacy_session_key` 仍是实时渠道 session 到 thread 的映射键。 | `SessionManager` 和当前渠道运行时仍在使用，不能删表或映射字段。 |
| M05 | `conversation/migrator.py`、`bootstrap/conversation.py` | 已移除启动扫描和旧渠道 session 到 thread/contact 的数据回灌。 | 旧渠道 session/消息已主动清空，不保留迁移入口。 |
| M06 | `conversation/service.py:13-18,59-145,336-368` | `LegacySessionDescriptor` 将当前渠道 session 映射为正式 thread，仍会处理未绑定渠道。 | `core/channels/hub.py`、`agent/turns/orchestrator.py`、`conversation/push_sync.py` 仍构造 descriptor，不能按 M05 删除。 |
| M07 | `session/manager/role_sessions.py` | 已移除旧 transport history 合并、provenance 和防回灌元数据。 | 角色会话仅保存自身的运行时历史。 |
| M08 | `session/manager/__init__.py` | 已移除 facade module 与跨模块 monkeypatch 转发。 | 生产模块直接依赖 owning module，现有测试没有 facade patch 调用方。 |
| M09 | `story_simulation/schema_migrations.py:17-98,106-216` | 迁移旧 Story 时间、资源字段，并 DROP 旧列。 | 先备份/验证历史 DB；审查 `1970-01-01`、`上午` 和失败资源语义。 |
| M10 | `story_simulation/story_time.py:60-89` | 仅用于旧 Story timestamp 的解析。 | Story DB 迁移完成后再删除。 |
| M11 | `plugins/observe/migrate_legacy_rag.py:13-127` | 旧 RAG 表转为新表并 DROP 老表。 | 当前主要是 CLI/测试；应移出常规启动路径并保留回滚说明。 |
| M12 | `plugins/observe/db.py:122-143` | 每次打开 DB 自动补列并删除旧 proactive observe 数据。 | 这是 destructive migration，必须有 schema version、备份和恢复验证。 |
| M13 | `core/memory/markdown_schema.py:57-131,216-223` | 打开角色记忆时重写旧 headings 和内容。 | 检查历史文件覆盖风险，改为一次性迁移并保存 diff/备份。 |

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
- **F11**：全局 `MemeCatalog` 回退是允许的产品行为。角色素材优先，角色素材缺失时可以使用全局 meme 素材；本项不再改动。

## 第三批：运行时 fallback 与异常吞错

| ID | 位置 | 当前行为 | 审查重点 |
| --- | --- | --- | --- |
| F01 | `infra/channels/qq_channel/compat.py:18-45` | 对 ncatbot 的 websocket 全局 monkey patch，失败只 warning。 | 确认第三方版本是否仍需补丁；优先改显式 adapter/版本检查。 |
| F02 | `bootstrap/channels.py:66-101`、`bootstrap/channel_host.py` | 渠道构造或启动异常时继续让其他渠道运行，并通过 `ChannelHost.failures` 暴露结构化失败状态。 | 已保留独立渠道隔离语义；调用方可据 `channel/phase/error_type/message` 展示健康状态。 |
| F03 | `agent/turns/outbound.py:65-96` | push 任意异常都转成 `False`。 | 区分参数不可发送与外部调用异常，避免业务层吞错。 |
| F04 | `memory2/store/connection.py:14-103`、`memory2/store/vector.py:209-220` | sqlite-vec 失败后全表扫描。 | 确认是否产品必需；若允许降级，增加规模阈值、状态和指标。 |
| F05 | `proactive_v2/event.py:45-55,98-164` | 缺 upstream id 时生成 SHA1 fallback id，坏时间静默忽略。 | 区分 dedupe key 与真实 event id；无 ID 或坏时间应可观测。 |
| F06 | `agent/core/proactive_turn/delivery.py:243-257` | target resolver 失败回退全局默认 channel/chat。 | 确认 role-scoped target 是否已经是唯一权威来源。 |
| F07 | `proactive_v2/mcp_sources.py:145-199` | 任意异常断开、重连并重试一次。 | 仅对 transport 错误重试；确认工具幂等性。 |
| F08 | `memory2/query_rewriter.py:35-72,110,133-137` | LLM 判断失败时默认开启 episodic retrieval，procedure 返回空。 | 保留产品容错时增加 decision source/metrics。 |
| F09 | `memory2/retriever.py:183-231` | embedding 失败跳过向量 lane，继续 keyword lane。 | 降级应返回 metadata，并设置连续失败告警。 |
| F10 | `proactive_v2/loop.py:328-345,394-419` | feed/tick 异常只记录并继续循环。 | 增加连续失败、backoff、健康状态或熔断。 |
| F11 | `plugins/meme/runtime.py:177-191,251-252` | 角色素材缺失时回退全局 MemeCatalog。 | 确认是否允许角色隔离边界被全局素材穿透。 |
| F12 | `proactive_v2/config_loader.py:197-200,335-368` | 新配置块兼容旧 `agent_tick` / `drift_*` 平铺字段。 | 检查旧配置存量，增加 warning 和移除期限。 |
| F13 | `memory2/dedup_decider.py:188-205,218-273` | 兼容旧 LLM decision、空列表、1-based index 和多 merge。 | 区分 legacy repair 与 invalid output，返回结构化原因。 |
| F14 | `desktop_bridge/story_simulation_handler.py:651-655` | 缺 `creation_id` 时回退 `request_id`。 | 确认所有调用方是否已提供 creation_id，避免幂等退化。 |
| F15 | `desktop_bridge/story_simulation_handler.py:629-634` | 无 director 时构造 `provider=None` 的 director。 | 确认是否只用于测试；生产路径应明确依赖缺失。 |
| F16 | `agent/tools/filesystem.py:58,513-516` | old_text 匹配失败后自动 LF/CRLF 转换再匹配。 | 保留跨平台容错或改为显式 newline normalization。 |
| F17 | `proactive_v2/mcp_sources.py:235-257` | MCP context 同时接受 dict/list，非法形态静默返回空。 | 固定 contract 后删除旧包装或改为明确错误。 |

## 第四批：Electron、Bridge 与环境硬编码

| ID | 位置 | 当前行为 | 审查重点 |
| --- | --- | --- | --- |
| E01 | `desktop/src/runtimePaths.ts:20,49,75-77` | 继续读取根 `config.toml` 作为 legacy config。 | 确认迁移窗口是否结束。 |
| E02 | `desktop/src/paths.ts:33`、`desktop/src/main.ts`、`desktop/scripts/dev.mjs` | 使用 `MIRA_RENDERER_DEV_SERVER_URL`、`MIRA_DESKTOP_USER_DATA_DIR`。 | 统一改为 `SHIORI_*`，是否保留一次兼容读取。 |
| E03 | `desktop/src/settings.ts:23` | 与 runtimePaths 并存的根 `config.toml` 默认路径。 | 统一由 runtimePaths/config service 提供。 |
| E04 | `desktop/src/runtimePaths.ts:38-64` | `.shiori/workspace`、打包 runtime 和 bridge args 分散硬编码。 | 集中为唯一 runtime path contract。 |
| E05 | `desktop/scripts/dev.mjs:14,20,26-40` | 默认端口 `5173`、localhost 绑定、20 次端口尝试。 | 区分开发方便性和 window security 白名单。 |
| E06 | `desktop/scripts/release-paths.mjs`、`build-runtime.mjs`、`package.json` | release/runtime/installer 目录契约分散。 | 建立单一 release manifest。 |
| E07 | `desktop/src/assets/localAssetRegistry.ts:13,96` | 本地资源上限固定为 `32 MiB`。 | 与 bridge/import policy 对齐并验证大文件需求。 |
| E08 | `desktop/src/settings.ts:211,216,315` | ASR/TTS/NovelAI endpoint 固定在 Electron 默认值。 | 权威来源应是 integration config/schema。 |
| E09 | `desktop/src/bridge/shared.ts`、assets 模块 | `shiori-asset` 协议字面量多处重复。 | 集中 protocol constants，保持安全测试。 |
| E10 | `desktop/src/bridge/bridgeClient.ts:7-14,103-125,284` | bridge health/start/request/image/observation/stop 超时分散。 | 按 command policy 集中，并记录验证依据。 |
| E11 | `desktop_bridge/voice/voice_http.py:81,111,172` | 多处重复网络 `timeout=60`。 | 与 voice/bridge 总超时统一。 |
| E12 | `desktop_bridge/voice/voice_providers.py:40,608` | 音频时长、bitrate 固定。 | 确认 provider SLA 与容量约束。 |
| E13 | `desktop/renderer/src/roles/roleFormState.ts:21-29,49-54,104-109` | proactive 默认值在 build/load/dirty 三处重复。 | 抽共享 defaults 或由 bridge 规范化。 |
| E14 | `desktop/renderer/src/chat/chatModelSelection.ts:7,25-36,51-52` | 非法 model effort 回退 registration effort/`none`。 | 由 bridge normalize，renderer 只展示合法值。 |
| E15 | `desktop/renderer/src/story/storyBeatPresentation.ts:15-18` | 多种引号正则兼容 mixed legacy beat text。 | 确认历史文本迁移后是否可移出展示层。 |

## 第五批：产品硬编码与测试夹具

这些项目通常不是直接删除，而是确认权威来源、集中管理并保留测试证据。

- H01 `proactive_v2/config.py`：channel、poll/tick interval、score threshold、interrupt floor、agent/drift limits。
- H02 `memory2/retriever.py`：keyword floor、embedding timeout、score threshold、注入字符数和强制记忆数。
- H03 `agent/provider.py:204-230,440-474`：request timeout、重试次数和 retryable error 集合。
- H04 `bootstrap/providers.py:6-7`：provider timeout `45s`，以及 light provider 返回 `None` 的旧契约。
- H05 `infra/channels/telegram_utils/live_edit.py:21-25`：Telegram 长度上限、更新间隔、flood/backoff。
- H06 `desktop/src/pet/momentum.ts`、`pet/controller.ts`、renderer pet interaction：拖拽、衰减、速度和 duration 常量。
- H07 `desktop/src/voice/interactionState.ts:5`、`observation/bubble.ts:3`：长按和 bubble duration。
- H08 `desktop/renderer/src/chat/chatMessageWindow.ts`、`chatMessageImageLayout.ts`、`ChatSurface.tsx`：消息窗口、图片和拖拽 UI 阈值。
- H09 `desktop/renderer/src/story/storyPreferences.ts`、`storyMenuTheme.ts`：音量、文字速度、图像采样和色彩量化参数。
- H10 `desktop/renderer/src/image/useImageStudioState.ts:30`、`ImageFormPanel.tsx:49,281`：NovelAI 默认模型、最大尺寸和 preset fallback。
- H11 `desktop_bridge/role_difference_service.py:127`、`stream_writer.py:20`、`voice/tts_text.py:7,40`：steps、queue size、TTS sentence max length。
- H12 `desktop/src/windowSecurity.ts:41-85`：localhost、CSP、`shiori-asset` 安全边界；通常应保留，只集中协议常量。
- H13 `desktop/src/voice/hotkey.ts`：uiohook 扫描码映射，是第三方库契约，不是普通业务配置。
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
