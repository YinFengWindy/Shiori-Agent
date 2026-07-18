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
