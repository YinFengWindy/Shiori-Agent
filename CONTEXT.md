---
title: Shiori 项目上下文
kind: Agent 入口
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - main.py
  - bootstrap/
  - docs/knowledge/
related:
  - docs/knowledge/index.md
  - docs/knowledge/map.md
---

# Shiori 项目上下文

Shiori（Mira-Agent）是基于 Akashic 的角色型 Agent 助手。项目的核心不是单一聊天界面，而是围绕角色、关系、会话、记忆、主动行为、多渠道和桌面端组成的持续运行系统。

## 领域语言

**已提交 Story 节拍（Committed Story Beat）**：
Story 中已经正式发生的最小叙事单位，也是 Story 自身的正式记录，不是 World 时间线事件的包装。只有完成提交的 Story 节拍属于故事记录；模型生成草稿和待玩家确认的结果都不属于已发生剧情。
_避免使用_：把模型输出、生成草稿称为已发生剧情；用 `TimelineEvent` 表示 Story 节拍

**Story 段（Story Segment）**：
同一个 Story 中，从创建或继续开始，到下一次归档为止的一段活动经历。同一 Story 同时只能有一个活动 Story 段；新段从上一归档末尾同刻或更晚开始，不能回到已归档剧情之前。
_避免使用_：用暂停时长推进剧情时间；在同一 Story 中回填更早的新段

**Story 归档（Story Archive）**：
一个 Story 段结束时产生的不可变记录。它冻结该段的正式剧情和逐角色故事回忆；继续会在原 Story 中开始新段，分支才会创建新的 Story。
_避免使用_：把归档称为整个 Story 的终止

**角色故事回忆（Story Archive Memory）**：
Story 归档时按参与角色视角生成并冻结的自然语言回忆。它属于 Story 归档，即使尚未投递到 Akasha 也不会重新生成或改变内容。

**角色故事回忆投递（Story Memory Delivery）**：
将 Story 归档中已经冻结的角色视角回忆幂等写入该角色普通记忆的过程。投递状态按角色独立记录，投递失败不会撤销或修改 Story 归档。
_避免使用_：把回忆投递失败称为归档失败

**Story 时间锚点（Story Temporal Anchor）**：
一个 Story 段在角色经历时间轴上的发生位置，与 Story 的创建时间无关。它由玩家显式指定并解析为不可变的固定时间，决定角色在该段开始时可以知道的记忆和所处的关系阶段。
_避免使用_：把当前关系状态直接当作历史 Story 的开场状态；让模型从背景中猜测发生时间

**Story 剧情时间（Story Effective Time）**：
已提交 Story 节拍在角色经历中的发生时间。它从段的时间锚点开始，只能保持或向前推进；跨越明显时段必须成为剧情中的显式时间跳跃。
_避免使用_：用生成耗时或提交时间代替剧情发生时间；向已提交段中回填更早节拍

**Story 提交时间（Story Recorded Time）**：
系统将 Story 节拍正式提交的操作时间，只用于审计和恢复，不决定节拍在剧情中何时发生。

**Story 开场上下文（Story Opening Context）**：
玩家在 Story 段开始前确认的角色身份、关系阶段和当时已知事实集合。它与时间锚点一起冻结，系统建议或未来记忆系统的预填都不能绕过玩家确认。
_避免使用_：把角色当前状态直接复制成历史 Story 的开场状态

**Story 后续连续性（Story Future Continuity）**：
玩家确认的、时间锚点之后已经明确发生的角色经历和关系结果。它只作为系统侧不可推翻的约束，不能进入角色可见上下文；Story 的发展不能使这些后续历史变得不可能。
_避免使用_：把后续连续性注入角色提示；把系统当前状态直接当作未经确认的历史约束

**Story 连续性冲突（Story Continuity Conflict）**：
候选 Story 节拍会泄露后续信息，或使已确认的后续连续性不再可能成立。发生冲突或系统无法确定是否冲突时，该候选内容都不属于已发生剧情。
_避免使用_：先提交冲突节拍再回滚或改写历史

**Story 待决策（Pending Story Decision）**：
重大不可逆结果进入正式剧情前持久化的玩家决策点。安全前置节拍可以已经发生，但待决策结果本身不属于正式剧情；玩家回应后仍须重新生成、校验并提交。
_避免使用_：把待决策选项或玩家点击直接写成已发生事实；沿用世界级 `DecisionBarrier`

**记忆记录时间（Memory Recorded Time）**：
Akasha 获得一条记忆来源的时间，由原始来源消息的提交时间确定。它回答“系统何时知道这条来源”，不等同于来源描述的事件何时发生。

**记忆发生时间（Memory Effective Time）**：
一条记忆来源所描述事件在角色经历中的发生时间。它可以未知，但不能用记忆记录时间冒充；从内容提取的发生时间必须保留来源依据。
_避免使用_：用单一“记忆时间”混指记录时间和发生时间

## 开始工作前

1. 先读 [知识库入口](docs/knowledge/index.md) 和 [能力地图](docs/knowledge/map.md)。
2. 回答“功能在哪里、依赖谁、修改影响什么”时，先查询本地 Graphify 图谱，再打开命中的源码核验。
3. 图谱是导航索引，不替代源码；`INFERRED` 边和健康页列出的异常不能当作确定事实。
4. 修改业务行为后，更新对应知识页的行为、影响面、`source_paths` 和 `last_verified_commit`。

## 常用查询

```powershell
graphify query "自动 CG 如何触发，失败和去重如何处理？" --budget 1800
graphify query "修改角色删除会影响哪些模块？" --budget 1800
graphify path "RoleAggregateService" "AutoCgController"
graphify explain "ProactiveLoop"
```

本地图谱输出位于 `graphify-out/`，该目录不提交 Git。提交后和切换分支后，已安装的 Git hook 会在后台增量刷新代码图谱。
