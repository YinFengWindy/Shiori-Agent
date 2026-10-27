# natural_chat 开关收口

关联：[#902](https://github.com/YinFengWindy/Shiori-Agent/issues/902) P3-9，以及方案 D8、审查 M7。`REPLY_POLICY` 和系统插件 `natural_chat` 仍留到 P6a，本决定不新增 Key，也不改 `PromptRendering` 已有字段。

## 数据源

角色记录 `RoleRecord.runtime_config` 是唯一开关。读取入口只有 `core.roles.natural_chat.natural_chat_enabled`：仅当 `natural_chat_enabled is True` 时为开。缺角色、缺键、`false`、`1`、`"true"` 都是关。

会话 `metadata["role_runtime_config"]` 是 `open_by_role` 写下的副本，心情目录等其它字段继续用它。它不再决定自然聊天。副本和角色记录不一致时，以角色记录为准。

P3 里原先的七处读取都改走这个入口：

| 调用方 | 原先 |
| --- | --- |
| `bootstrap/runtime/dispatcher.py` | 角色记录 |
| `agent/turns/reply_interruption.py` 的 `refresh` | 角色记录 |
| `agent/turns/orchestrator.py` | 有 `role_lookup` 时读角色记录，否则读会话副本 |
| `agent/looping/core/processing.py` | 角色记录 |
| `desktop_bridge/chat_service.py` | 会话副本 |
| `agent/lifecycle/phases/prompt_render.py` | 会话副本 |

`TurnOrchestrator.natural_chat_enabled` 仍是主动回合的调用点，内部只转发给上面的入口。没有 `role_lookup` 时视为关：没有角色记录就没有开关。生产装配始终传入运行时的 `RoleStore`。

`PromptRendering.reply_mode` 的初值仍是这个开关，再被 `supports_reply_sequence` 与 `minimal_request` 收窄。不新增字段。

选用与否不改变核心里的多消息协议：`finish_reply` 校验和 `deliver_sequence` 投递一直在，不论开关状态。

## 真值表

本表只决定这一轮是否选用自然聊天（提示词、分条准入、打断刷新、主动与后台分条）。投递协议不在表里。

### 当前（P3，插件还不存在）

代码不读插件启用状态。有效开关只有角色记录。

| `runtime_config.natural_chat_enabled` | 行为 |
| --- | --- |
| `True` | 选用自然聊天 |
| 其它 | 单条回复，照常聊天 |

### P6a 起（插件启用 × 角色开关）

P6a 把提示词和策略搬进系统插件 `natural_chat` 时按这张表实现，不再另定。两个条件都为真才选用。插件未启用等于不注入提示词和策略，角色开关单独为真也不选用。

| 插件启用 | `runtime_config.natural_chat_enabled` | 行为 |
| --- | --- | --- |
| 否 | 任意 | 不选用。回复单条。核心协议仍在 |
| 是 | 不是 `True` | 插件在架，该角色关闭。回复单条 |
| 是 | `True` | 选用。插件提供提示词和策略，核心按分条执行 |

`REPLY_POLICY` Key 与插件一起在 P6a 加入。P3 不添加。
