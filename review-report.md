# 审查报告：《Shiori 插件系统四层重构方案》

## 对照修订（2026-10-22）

维护者已按本报告修订方案，全文在 [`docs/plugin-system-four-layer-refactor.md`](docs/plugin-system-four-layer-refactor.md)（决策 D1–D24，含 §8 内核语义规范）。严重项的落地如下。下文保留审查原文。

| 项 | 修订 |
|---|---|
| **S1** | §8.1 写死 `on` 链：依赖拓扑序 + 插件 id 稳定次序（不依赖注册时刻）；核心 handler 固定在插件之前；返回同型事件为替换，否决用显式 `Veto`（不用 `None` 表示删除）；事件类型声明 `fail_open` / `fail_closed`，`ToolCalling` 固定 fail_closed。热重载后顺序须与冷启动一致。 |
| **S2** | §8.2：禁止跨调用缓存 `get` / `require`；reload 覆盖 require 下游，以及已经 `get` 到该 Key 的 optional 下游；核心消费插座禁止长持实例；排空协议为 seal → drain → dispose。**D14** 保留 `supports_hot_unload`（默认 true）。子进程 / 原生扩展插件（`qq`、`gpt_sovits_tts`、`sensevoice_asr` 及同类）可声明 `false`，启用、禁用、重载只在 runtime 重启后生效。 |
| **S3** | **D22**：大版本表示破坏性变更，不再「只认大版本」。manifest `api: 4` 另加最低 SDK 约束（例如 `>=4.0.0`）。SDK 独立 semver，与 `api` 解耦。同大版本新增 Key / Event 靠运行时 `inject` / `optional_inject` 发现，缺 Key 则 setup 失败并产出 `PluginDiagnostic`。 |
| **S4** | **D13 拆分**：`PluginDiagnostic`（及 `PackageContractError` / `RendererActivationError`）留在内核或 bridge，与 observe 是否启用无关。进程崩溃钩子改为核心服务 `CRASH_REPORTING`。observe **只** `inject: [crash_reporting]` 注册 collector，不再直接改写全局钩子。 |
| **S5** | **D23**：桌面发版仅在 P1–P8 全部完成后随 SDK 4.0 一起发。已安装的 3.x / `api: 2` 外部插件启动时 `BLOCKED`，提示升级到 api:4；不迁移，保留文件与配置。 |

另外：**D20** 从「进核心」翻转为系统插件 `memory_optimizer`（证据：只在后台重写 `MEMORY.md` / `SELF.md`，回合路径零引用）。**D24** 规定重复 provide 必须声明 `conflicts` 或 `replaces`；双方都未声明则启动失败并点名双方。

- 被审文档：<https://shiori-j5wk.pages.grok.bot/>（标题「Shiori 插件系统四层重构方案（盘点 + 分阶段计划 + Harness）」，文内日期 2026-10-22，含决策 D1–D21、第 0–7 节）。修订稿见上文链接。
- 取正文方式：页面正文在 sandbox iframe `/__cursor/frame?v=9918bac08bad` 里。普通 GET 返回 404；带上 `Sec-Fetch-Dest: iframe` / `Sec-Fetch-Mode: navigate` / `Sec-Fetch-Site: same-origin` 请求头后返回 200。响应里的 `__sharedCanvasPayload.appJsB64` 是 gzip+base64 的 bundle，解开后 `userModule` 中的 `const MD = '...'` 就是方案 Markdown 全文（约 3.7 万字符），本报告基于这份全文。
- 事实核对基线：方案自称基于 `main @ 976f920`。下文凡是写「源码核实」的地方，都用 `git grep` / `git show 976f920:<path>` 核对过。

## 总评

方案的方向是对的：把 41 个 capability 和 7 个 phase 收敛成 Key + typed event、用真内核替代镜像 fake、让 proactive / affection / schedule 这些业务从宿主里拆出去。盘点数据大部分也准确（plugin_host 7267 行、contract 文档 1686 行、reload.py 405 行 / unload.py 105 行、24 个插件目录，都与源码一致）。

但它把自己定位成「开放问题：无」、可以直接分阶段落地的计划，这一点站不住。下面列出的严重问题集中在四处：**事件和热重载的运行时语义没写清、版本策略与仓库现行规则冲突、对 diagnostics 现状的判断有事实错误、不可逆步骤没有回滚和发布边界**。这几处不补，P1 和 P3 一开工就会各自做出不同的语义选择。

---

## 一、严重（阻塞）

### S1. `on` 链的顺序、错误和否决语义没有定义，热重载后顺序会变

- **位置**：§3「lifecycle → 事件；顺序 = 插件依赖拓扑序 + 注册序；requires/produces 删除」；§1 ctx API 的 `on` / `emit`；D14 `kernel.reload`。
- **问题**：
  1. 现在的 phase handler 用 requires/produces 表达**数据依赖**（比如谁先产出、谁后消费）。这类约束不等于插件之间的依赖关系，换成「拓扑序 + 注册序」以后，两个互不依赖的插件谁先谁后就取决于加载和注册的时机。
  2. 和 D14 一起看问题更大：`reload(plugin_id)` 会先 dispose 再重新 setup，被重载的插件会**重新注册到链尾**。热重载之后的执行顺序和冷启动不一样，「热重载无残留」那条契约测试（§5.2）只比较数量，抓不到这个问题。
  3. 核心模块自己的 handler 和插件 handler 怎么排序没有写。核心不是插件，不在依赖拓扑里。
  4. handler 抛错时怎么处理没有写：是中断整条链、跳过这个 handler，还是让整个回合失败？`ToolCalling` 说「可改写参数或拒绝」，但没有写「拒绝」用什么表达（返回哨兵值？抛特定异常？）。对 shell_safety 这类安全拦截，handler 自己出错时应该 **fail-closed**（拒绝执行），而通用策略「跳过出错的 handler」恰好是 fail-open。
  5. `E | None` 的返回值里，`None` 到底是「不改动」还是「删除事件」，没有说明。
- **为什么不妥**：P3 被标成「中高（回合内顺序语义）」风险，计划却只靠一份没定义的「golden trace」兜底。顺序和错误语义是内核契约的核心，留给实现者临场决定，P3 的 6 个迁移插件很可能各写各的。
- **建议**：在内核契约里写清楚 ① 排序键：显式 `before/after` 约束或数值 priority，加上插件 id 作为稳定的次序键，**不依赖注册时间**，保证 reload 前后顺序不变；② 核心 handler 固定排在插件之前或之后；③ 每个事件类型声明出错策略（`fail_open` / `fail_closed`），`ToolCalling` 固定为 fail-closed；④ 否决用显式类型（例如 `Veto(reason)`）表达。给每条语义配一个内核单测，并补一条「reload 后顺序与冷启动一致」的契约测试。

### S2. 热重载会让 `get` 拿到的引用和核心持有的引用失效；in-flight 请求怎么处理也没写

- **位置**：D14「按逆拓扑序 dispose 该插件和 **require** 了它 Key 的下游插件」；D1′「消费方统一 `ctx.get(MEMORY_ENGINE)`」；§5.2 热重载契约测试。
- **问题**：
  1. 重新 setup 的只有用 `require` 声明依赖的下游。用 `optional_inject` / `get` 的消费方（plugin_undo 对 `memory_engine`，proactive 对 `affection/scene/schedule`）不会被重新 setup，手里还拿着**已经 dispose 的旧实例**。
  2. **核心模块**也消费插件提供的 Key：核心检索管线（`agent/retrieval/default_pipeline.py`）通过插座拿 `MEMORY_ENGINE`，核心 tools 收 schedule 插件注册进来的工具。核心不归内核重新 setup，default_memory 重载之后，核心拿到的引用要么是旧的，要么是悬空的。
  3. 重载的时候，可能有回合正在用这个插件（检索进行到一半、工具正在执行）。方案没有写要不要先排空再 dispose（quiesce/drain），也没有写 `spawn` 出去的任务被取消后，进行中的写操作怎么收尾。仓库在 #823 已经踩过「换代时等后台任务导致卡死」的坑，方案却把 reload 装配层从 510 行估到「约 150 行」，没有给依据。
  4. D14 同时删掉了 `supports_hot_unload`，要求「所有插件都必须可重载」。可是 qq（NapCat 子进程）、gpt_sovits_tts / sensevoice_asr（外部进程）、带原生扩展的依赖都没办法真正卸载重新 import，方案没有讨论这些插件怎么满足「必须可重载」。
- **为什么不妥**：这类 bug 只在热重载之后出现，平时的测试路径覆盖不到，属于典型的潜伏缺陷。
- **建议**：二选一并写进契约：(a) `get` 返回的是**活引用**（代理对象，或者规定只能在使用时调用 `ctx.get`、不允许缓存），核心消费插座时也遵守同样的规则；(b) reload 时把 optional 消费方也纳入重新 setup 的集合，核心改为订阅 `ProviderChanged` 一类的内核事件。另外写明 reload 的排空协议（先停止接收新调用 → 等待进行中的调用或超时 → dispose），并保留一个「不可热重载、只能重启生效」的声明，不要用契约测试去强行要求所有插件都能重载。

### S3. 版本策略与仓库现行规则冲突，而且「只认大版本」表达不了新增能力

- **位置**：P5「版本只认大版本 4.x，删掉 Unreleased 批次流程、sync 脚本简化」；§5.9「不搞版本批次，SDK 只在破坏性变更时升大版本」；manifest v4 的 `api: 4`；D10「插座契约变更随 api 4 一起发布，不单独升版本」。
- **问题**：
  1. 和 AGENTS.md 正面冲突：AGENTS.md 规定普通契约 PR 在 `plugin-runtime-contract.md` 的 Unreleased 区累积，由维护者在发版时统一定版，用 `scripts/sync_sdk_version.mjs` 同步，并统一插件最低版本约束。方案在附带的改动里直接废除这套流程，没有把它当成一项需要单独确认的决策。
  2. 只认大版本以后，4.x 范围内的**新增能力**（例如 D10 给插座加的 `rollback_turn`、D19 新增的 5 个 API）没办法用版本表达。插件声明 `api: 4` 也无从得知宿主是否已经提供 `SESSIONS.presence`，只能等到运行时 `AttributeError`。
  3. `api: 4` 把三样东西混成了一样：manifest 格式版本（现在是 `api: 2`）、SDK 版本（现在 `_version.py` 是 3.1.2）、运行时契约范围（现在是 `runtime_api: ">=3.1.x <4.0.0"`）。而插件 `pyproject.toml` 里的 `shiori-sdk>=3.1.2,<4` 怎么改、和 `api` 是什么关系，方案都没写。
  4. 内置插件版本：P4 一次性改动 24 个 manifest，按 AGENTS.md 每个插件要升一次 patch，`manifest.yaml` 和 `pyproject.toml` 要保持一致，方案没有覆盖。
- **建议**：把「版本策略」从附带改动中拿出来，单列为一项决策请维护者确认。推荐保留「大版本 = 破坏性」，同时保留最低版本声明（例如 `api: 4` 加上 `sdk: ">=4.0.x"`，或者内核在加载时按 Key / Event 是否存在做能力校验并给出明确错误）。写清楚 manifest 格式版本、SDK 版本、pyproject 约束三者的对应关系和同步工具。

### S4. 对 diagnostics 的定性有事实错误，D13 照方案执行会删掉插件失败状态上报，也会拿走 observe 需要的进程级钩子

- **位置**：D13「删掉 `agent/plugin_host/diagnostics.py` 68 行、`shiori_sdk.diagnostics`，内核只保留 `ctx.log` 和三个事件，observe 用 watch 消费」；§3 diagnostics 一行。
- **源码核实**：
  - `agent/plugin_host/diagnostics.py` **不是遥测**。它定义的是 `PluginDiagnostic(code, stage, field, reason, path, state="BLOCKED")`、`PackageContractError`、`RendererActivationError`，也就是插件被拒绝或激活失败时**面向宿主和 UI 的失败详情契约**，被 `desktop_bridge/runtime/plugin_packages.py`、`plugin_package_listing.py`、安装器、`kernel.py` 等 10 余处使用。
  - `shiori_sdk.diagnostics` 是**进程级异常钩子的宿主仲裁契约**（`install_global_hooks(owner, handler, sys/thread/loop hook)`）。observe 的 `collector.py` 靠它安装 `sys.excepthook`、`threading.excepthook` 和事件循环的异常处理器。
- **为什么不妥**：① 删掉前者以后，「插件被拒绝或加载失败」在设置页的展示就没有了数据来源。observe 可以被禁用，失败状态不能依赖一个可禁用的插件来展示。② 删掉后者，observe 就得自己直接改写进程全局钩子。这和「系统插件没有任何特权」自相矛盾，多个插件或宿主同时装钩子时也没有了仲裁。`watch` 只能收到内核主动 emit 的事件，替代不了捕获未处理异常的能力。
- **建议**：把 D13 拆成两部分重新决策：(a) `PluginDiagnostic` 失败状态契约留在内核或 bridge，这是 `PluginFailed` 事件的载荷，也是 UI 的数据源，与 observe 是否启用无关；(b) 进程级异常钩子由核心提供一个服务（例如 `CRASH_REPORTING` Key），宿主负责仲裁，observe 通过它注册，不直接改全局状态。

### S5. 不可逆步骤没有回滚路径，也没有发布边界

- **位置**：D4（3.x zip 直接拒绝，无兼容层）；§4「每期可单独合并，CI 绿，app 可用」；P4、P6b。
- **问题**：
  1. P4 是不可逆的切换点，此后外部 3.x 插件一律拒绝。可是 P5–P8 还没完成，方案没有说明 **P4 到 P8 之间能不能发桌面版本**。如果中途发版，用户拿到的是一个「旧插件全部失效、新 SDK 还没定型」的中间态。
  2. 用户 workspace 里**已经装好的** 3.x 外部插件，升级后启动时会怎样：标记为不兼容并保留文件？自动禁用？反复报错？它们的配置和启用状态还保不保留？D4 只覆盖了「安装时」和「加载时」报一条错误，没有交代用户可见的状态和数据保全。
  3. 回滚和降级完全没讨论：用户升级以后再降回 0.5.x，新版本写入的数据（`ROLES.plugin_settings` 写进角色 JSON 的字段、presence 迁到核心 sessions 后的写法、新系统插件的启用状态键）旧版本能否读取？D4′ 只保证新版本读得了旧数据，没有反过来保证。
  4. 合并层面的回滚：P3 和 P6b 都是删掉旧路径、换成新路径。出现回归时，是 revert 单个 PR 还是有开关可以切回？方案没有给出。
- **建议**：① 明确发布边界：P1–P8 全部完成后才随 SDK 4.0 一起发桌面版本；或者标出哪些阶段之后可以安全发版。② 写清楚已安装 3.x 插件的启动行为（建议标记为 `BLOCKED` 并保留文件、配置和启用状态，UI 给出升级提示，这正好依赖 S4 里的 `PluginDiagnostic`）。③ 补一节「降级说明」：列出所有新版本会**写入**的持久化字段，说明旧版本读到时的行为。④ 对 P3 和 P6b PR4 这两个高风险阶段，说明出现回归时的回退手段（revert 粒度或过渡开关）。

---

## 二、中等

### M1. 「插座」的多 provider 规则和重复 provide 的处理没有定义
- **位置**：D1「default_memory 可以被其他实现插件替换」；§1「`Key[T]`、provide」。
- **问题**：两个插件同时 `provide(MEMORY_ENGINE)` 时，内核是报错、后者覆盖，还是按优先级选？「替换」靠用户手动禁用 default_memory，还是由内核仲裁？没有写。D1′ 去掉了 provider 数量校验，使这一点更不确定。
- **建议**：在内核契约里写明「单值 Key 重复 provide 时启动失败，产生 `PluginDiagnostic`」；如果需要可替换，在 manifest 里用 `conflicts` 或 `replaces` 显式声明。

### M2. Key 的字符串名与 `Key[T]` 的映射规则不清楚，命名也前后不一致
- **位置**：manifest 示例 `inject: [roles, sessions, conversation]` / `optional_inject: [memory]`；D10 `optional_inject: [memory_engine]`；§3 `MEMORY` / `MEMORY_ENGINE`；§5.4「`shiori_sdk.kernel` 不能 import 核心契约模块」。
- **问题**：manifest 里写的是字符串，代码里用的是 `Key[T]` 对象。内核要校验「require 的 Key 都在 inject 里」，就必须知道字符串到 Key 的对应关系，可它又不能 import 核心契约。这个映射放在哪里、`memory` 和 `memory_engine` 这类名字由谁保证唯一，都没有说明。
- **建议**：规定 `Key[T]` 的 name 必须与 manifest 字符串完全一致，由 provider 在 provide 时登记，内核只做字符串比对；用 manifest schema 加一份生成出来的 Key 清单在 CI 里校验命名唯一。

### M3. `watch` 的 fire-and-forget 没有背压、没有顺序保证，还被用来改状态
- **位置**：D15；§7.4「proactive `watch(TurnFinished)` 更新冷却和能量」。
- **问题**：
  1. 每次 emit 都为每个 watcher 新建一个任务，没有上限。`StepStarting` / `ToolCalled` 这类高频事件加上 observe，任务数可能无界增长。
  2. 同一个 watcher 对多个事件的执行顺序没有保证，observe 记下的时间线可能乱序。
  3. proactive 在 watch 回调里修改冷却和能量状态，和自己 tick 循环里的读写形成竞态。「只读」只约束了事件对象，约束不了 watcher 去改自身的状态。
  4. 插件 dispose 时直接取消还在执行的 watcher，可能丢遥测或丢状态写入。
  5. 「frozen dataclass」只是浅冻结，事件里的 list / dict 字段仍然可以被改。
- **建议**：每个 (插件, 事件) 一个串行队列，设上限和溢出策略（丢弃并计数）；dispose 时先 drain 并设超时，再取消；事件载荷字段统一用不可变类型（tuple / `MappingProxyType`）；会改状态的消费方（proactive）改用 `on`，或者在插件内部串行处理。

### M4. 回滚跨两个插座，没有原子性也没有补偿
- **位置**：D10 `SESSIONS.rollback_last_turn(session_key)` 加上 `MemoryEngine.rollback_turn(turn_id)`。
- **问题**：会话回滚成功、记忆回滚失败（或者反过来）时，状态不一致；`turn_id` 从哪里来、怎样和 `session_key` 对应，也没有写。
- **建议**：先回滚记忆（可以重试），成功后再回滚会话；失败时整体中止，并通过命令回复告知用户。`RollbackResult` 里带上 `turn_id`，作为两步之间的关联键，契约测试覆盖「第二步失败」的场景。

### M5. 配置的数据位置与「不写迁移脚本」矛盾
- **位置**：P6b PR2「ProactiveConfig 移进插件 `config_model`，配置键原样保留」；D4′；D20 `memory_optimizer_enabled`。
- **源码核实**：proactive 配置现在由核心 `agent/config.py` 从宿主的 `config.toml` 解析（`_load_proactive_config(data)`），而插件配置走插件配置存储（`ctx.config`）。
- **问题**：「键不变」不等于「位置不变」。插件化以后 `ctx.config` 从哪里读：继续读 `config.toml` 的某一段，还是读插件配置存储？前者需要宿主为某个插件开一条特殊读取路径，和「无特权」冲突；后者需要迁移，和「不写迁移脚本」冲突。affection、natural_chat、scene 搬家时也有同样的问题。
- **建议**：对每个从宿主搬出去的模块列出「现在的存储位置 → 插件化后的读取位置」。要么接受一次性迁移（启动时幂等执行，可重复），要么明确规定 `ctx.config` 的来源可以是宿主配置的某个命名段，并写进契约。

### M6. 分层判定规则自身没有贯彻（D20、D11、shell_safety）
- **位置**：§0「把它拔掉 app 还能聊天吗？」；D20、D11、§2.1 shell_safety。
- **问题**：
  1. D20 把 621 行、由 LLM 驱动的 memory_optimizer 放进**核心**。它自带开关、拔掉照样能聊，按方案自己的规则应该是系统插件。
  2. D11 把 shell/fs、web、skills、subagent 留在核心，理由并不是「拔掉不能聊」。这本身没问题，但需要写明这是对判定规则的例外和例外的理由，否则后来的人会按规则把它们再拆出去。
  3. shell_safety 是「默认开、可禁用、无特权」的系统插件。也就是说，用户禁用一个插件，shell 工具就失去了危险命令拦截，而核心里的 shell 工具会继续执行。「能聊天」这个判定标准没有覆盖**安全不变量**。
- **建议**：给判定规则补一条「安全不变量」维度：shell 工具存在时必须有拦截层，否则 shell 工具不注册。也可以把 shell_safety 的最小规则并入核心 tools。D20 要么改成系统插件，要么把规则的例外写清楚。

### M7. natural_chat 的拆分漏了几个现存的行为分支
- **位置**：D8、P6a。
- **源码核实**：`natural_chat_enabled` 除了提示词（`lifecycle/phases/prompt_render.py`），还出现在 `agent/turns/reply_interruption.py`（打断策略）、`bootstrap/runtime/dispatcher.py`（分发）、`desktop_bridge/chat_service.py`，`core/roles/migration.py` 里也有。
- **问题**：打断和分发这两类策略，方案列出的 7 个回合事件加上 `ToolCalling/ToolCalled` 都覆盖不到，插件「只通过 PromptRendering / ReasoningFinished」接不住它们。另外存在两个开关：插件的全局启用状态和角色级的 `runtime_config.natural_chat_enabled`。两者组合起来的行为（插件禁用但角色开着、或者反过来）没有说明。
- **建议**：先盘点每个分支要哪个事件或服务来承接，缺事件就在 P3 补上；写明两个开关的组合真值表。

### M8. 内核放进 SDK（D3）带来的版本漂移和归属问题没有分析
- **位置**：D3、§5.10（删除 wheelhouse/provenance 隔离）。
- **问题**：插件 `pyproject.toml` 现在依赖 `shiori-sdk>=3.1.2,<4`。内核进入 SDK 以后，第三方插件在开发环境里装的 SDK（以及内核）版本可能和宿主打包的版本不同：测试时跑的是 A 版内核，生产环境跑的是 B 版。偏偏方案还要删掉 wheelhouse/provenance 隔离，而这套隔离正是用来证明「插件只依赖发布出去的 SDK」的。在仓库里直接 `pytest plugins` 时，`apps/backend` 也在导入路径上，插件意外 import 宿主模块的问题只能靠 import-linter 的静态分析去发现。这也和 AGENTS.md「插件测试自包含、不依赖根 conftest」的要求相抵触。
- **建议**：保留一个最小的隔离 job，用发布形态的 SDK wheel 跑插件测试；内核在运行时自报版本，宿主加载插件时校验 SDK 版本（与 S3 一起处理）。

### M9. 用 import-linter 替换 check_sdk_imports，覆盖面的损失没有评估
- **位置**：§5.4「约 30 行配置 + 60 行脚本替换约 1.6k 的 check_sdk_imports + sdk_* path-sink 分析」。
- **问题**：import-linter 只检查静态 import 关系，path-sink 分析检查的是另一类东西（路径和数据流向）。方案没有列出现有检查覆盖了哪些规则、替换以后哪些规则不再检查。
- **建议**：先把现有检查规则逐条列出来，标出哪些由 import-linter 覆盖、哪些主动放弃（写明理由）、哪些需要单独保留。

### M10. 生命周期和资源释放：effect / on / spawn 共用一个作用域，释放顺序没有规定
- **位置**：§1 ctx API 的 `effect` / `on` / `spawn`。
- **问题**：仓库在 #227 踩过这个坑：`ctx.effect` 和 `ctx.events.on` 共用 `EffectScope`，按 LIFO 释放，按自然阅读顺序写（先订阅、再登记 terminate）恰好是错的，卸载瞬间会漏掉一个永远不被取消的任务。新的内核要把 `watch` 和 `spawn` 也放进同一个作用域，方案却没有规定释放顺序。
- **建议**：在契约里固定释放顺序，例如「先取消所有订阅（on/watch）→ 再 drain 并取消 spawn 出去的任务 → 最后按 LIFO 执行 effect」。由内核负责，不交给插件作者记忆。契约测试里放一个并发卸载的竞态用例。

### M11. 失败场景和验收标准不完整
- **位置**：§4 每个阶段只写了「CI 绿、app 可用」；§5 Harness。
- **问题**：下面几项都没有写：插件 setup 失败时内核是继续启动其他插件还是中止，依赖它的下游插件怎么办；依赖图有环时的检测和报错；核心模块 provide 失败时宿主怎么处理；前端入口加载失败（现在的 `RendererActivationError`）和后端状态怎么联动。「golden trace」怎么录制、比对哪些字段、LLM 输出不确定时怎么处理，也没有定义。
- **建议**：每个阶段都补一张「验收清单」（功能断言、对应的失败场景测试）。在内核契约里写清楚失败传播规则：失败的插件标记 BLOCKED，它的 require 下游连带 BLOCKED，optional 消费方降级，核心失败则启动失败。golden trace 只比对事件序列和关键字段，并使用假 LLM。

### M12. 前端生命周期和后端热重载之间怎么配合没有写
- **位置**：P7、D14、§1「前端入口」。
- **问题**：后端 reload 以后，`BRIDGE.expose` 的 handler 会重新注册。这时前端正在进行的 rpc 调用、后台隐藏窗口（`background`）和 surface 窗口要不要一起重建？方案里的内核只覆盖 Python，前端的 dispose 和 re-setup 语义是空白。
- **建议**：规定 reload 时给前端发一个 `pluginReloaded` 事件，由前端宿主统一重挂入口；正在进行的 rpc 返回明确的「插件正在重载」错误，不要静默挂起。

---

## 三、轻微

1. **「开放问题：无」与正文不一致**：D7 scene 仍然是「暂定」，§2.1 context_pressure 还带着 ⚠️，§2.3 自己也说有遗留的实施细节。建议保留一个「已知待定」小节，写明各自的触发条件。
2. **统计口径过时**：§4 合计标的是「按 D1–D18 重算」，决策已经写到 D21。总数复算是对的（新增 6900 / 删除 22450），只是标签需要更新。
3. **基线描述**：只给了 commit 976f920，以及作者本机路径 `/workspace/research/...` 和读者拿不到的 `plugin_compare.md`。建议附上可以访问的前置对比，或者把关键结论摘进正文。
4. **内核 500 LOC 预算是一个容易被钻空子的指标**：D14「超预算时先把逻辑挪到装配层」，等于鼓励把复杂度搬到装配层（约 1.2k 行）。用 `wc -l` 统计还会逼着删注释，和 AGENTS.md「对外暴露的函数要写注释」相冲突。建议预算统计排除注释和 docstring，同时要求装配层有同等强度的测试。
5. **「四层」实际上是三层**：系统插件和外部插件只差 `default_enabled`（§0 也承认这一点），技术上是同一层。建议改成「三层 + 一个插件分类字段」，免得读者以为两类插件的能力边界不同。
6. **D18 `contributes.channels` 与运行时 `CHANNELS` 是两处声明**：已经有契约测试检查一致性，但「账号表单 schema」和插件的 `config_model` 可能出现第三处重复，建议说明两者的关系。
7. **mermaid 图的依赖方向不完整**：图里只画了 `S/E → K`，看不到插件 → 核心契约（`shiori_sdk.core.*`）这条真实存在的依赖，也看不到核心 → 插件提供的 Key（检索管线 → `MEMORY_ENGINE`）这条反向的运行时依赖。建议补上，并标明哪些是编译期依赖、哪些是运行时依赖。
8. **流程**：AGENTS.md 要求 PR 关联 Issue。方案没有对应仓库里已有的 Issue（插件系统旧重构 #174 及后续的 #210、#854 单插件代内重载、#823 换代卡死），没有说明它和这些已交付设计是什么关系，也没有说明哪些属于推翻、哪些属于延续。
9. **P6b PR1 保留一版别名**：`ProactiveMessageCommitted` 的别名要在 PR6 删除，这和 S5 的发布边界相关。如果中间发了版本，别名一删就是一次破坏性变更。

---

## 四、总体判断

**这份方案还不能直接进入实现阶段。** 它是一份质量不错的盘点和方向性计划，分层方向、搬迁清单、Harness 的思路都可以保留。但它在三个地方把「需要决策的运行时语义」当成了「已经决定的实现细节」：

1. **先补内核契约（对应 S1、S2、M1–M3、M10、M11）**：`on` 的排序、出错和否决语义，`get` 引用在热重载下的行为，reload 的排空协议，重复 provide 的规则，watch 的背压和顺序，作用域的释放顺序，失败的传播规则。这些是 P1 的输入，不写清楚 P1 就开不了工。建议写成一页「内核语义规范」，每条配一个内核单测。
2. **改正事实错误并重新决策 D13（对应 S4）**：区分「失败状态契约」和「进程级异常钩子」，两者都不应该依赖可禁用的 observe。
3. **把版本策略和发布边界单列出来请维护者拍板（对应 S3、S5、M8）**：它们和 AGENTS.md 现行规则冲突，涉及外部插件生态和用户数据，不能作为重构的附带改动一起通过。还要补上已安装 3.x 插件的启动行为、降级说明，以及 P3、P6b 的回退手段。

上面三项补齐以后，P0（护栏）和 P1（内核骨架）可以先启动；P3 之后的阶段要等 M5（配置位置）、M7（natural_chat 分支盘点）和每个阶段的验收清单补齐再开工。
