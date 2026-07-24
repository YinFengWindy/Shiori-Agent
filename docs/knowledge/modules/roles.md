---
title: 角色、关系、心情与素材
kind: 领域说明
status: 当前有效
last_verified_commit: 8fdae87c
source_paths:
  - core/roles/store.py
  - core/roles/pet_packages.py
  - core/roles/services.py
  - core/roles/world.py
  - core/roles/relationship_runtime/
  - core/roles/scene_followup_runtime.py
related:
  - conversations-and-sessions.md
  - proactive-and-drift.md
  - novelai-and-auto-cg.md
---

# 角色、关系、心情与素材

## 模块边界

`RoleStore` 负责角色记录持久化，`RoleAggregateService` 和相关 service 提供角色聚合业务入口，`RoleWorldRegistry` 将持久化角色装配为运行时角色世界。桌面端、渠道和主动能力应调用这些服务，不应各自读写角色文件。

角色能力包含基本设定、渠道绑定、工作区、素材、心情相关配置和运行时关系状态。角色素材既被桌面管理页使用，也可能进入提示词、场景和图片生成流程。

## 关系与场景

`core/roles/relationship_runtime/` 负责关系快照、持久化、寂寞计算和维护循环。`SceneFollowupRuntime` 负责场景追问状态。它们为 Proactive、Drift 和自动 CG 提供上下文，但不直接拥有 Agent 回合。

## 修改影响

- 修改角色 schema：同步检查 store 序列化、配置迁移、桌面共享类型、表单适配、渠道绑定和角色世界装配。
- 修改角色删除：检查会话、对话线程、关系状态、记忆、调度任务、工作区和素材清理。
- 修改心情或关系：检查主动触发条件、提示词装配、场景判断和桌面展示。
- 修改素材分类：检查角色素材页、选择器、图片提示词与本地资源传输。
- 导入桌宠素材包：`pet.json` 的预览图字段兼容可选；提供 `previewPath` 时仍校验并保存预览图。

## 不变量

- 业务入口显式携带 `role_id`。
- 角色身份与渠道账号绑定分离；渠道标识不能替代角色主键。
- 运行时派生状态不应反向覆盖角色持久化定义，除非经过 owning service。
