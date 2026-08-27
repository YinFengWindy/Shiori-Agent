---
title: 角色、关系、心情与素材
kind: 领域说明
status: 当前有效
last_verified_commit: 5ed016f2
source_paths:
  - apps/backend/core/roles/store.py
  - apps/backend/core/roles/models.py
  - apps/backend/core/roles/manifest.py
  - apps/backend/core/roles/assets.py
  - apps/backend/core/roles/binding_policy.py
  - apps/backend/core/roles/pet_state.py
  - apps/backend/core/roles/pet_packages.py
  - apps/backend/core/roles/services.py
  - apps/backend/core/roles/role_runtime.py
  - apps/backend/core/roles/relationship_runtime/
  - apps/backend/core/roles/scene_followup_runtime.py
  - apps/backend/desktop_bridge/role_difference_service.py
  - apps/desktop/src/bridge/bridgeClient.ts
  - apps/desktop/renderer/src/roles/useRoleDifferenceGeneration.ts
  - apps/desktop/renderer/src/roles/RoleAssetCategoryGroups.tsx
related:
  - conversations-and-sessions.md
  - proactive-and-drift.md
  - novelai-and-auto-cg.md
---

# 角色、关系、心情与素材

## 模块边界

`RoleStore` 是兼容 facade：`RoleManifestRepository` 负责版本化 JSON 清单的校验、持久化和进程内锁，`RoleAssetStore` 负责素材文件、路径安全与分类，`RoleBindingPolicy` 负责渠道联系人和主动目标不变量，`RolePetStateStore` 负责桌宠选择与单启用状态，持久化数据契约集中在 `models.py`。`RoleAggregateService` 和相关 service 提供角色聚合业务入口，`RoleRuntimeRegistry` 将持久化角色装配为角色运行时。桌面端、渠道和主动能力应调用这些服务，不应各自读写角色文件。

角色能力包含基本设定、渠道绑定、工作区、素材、心情相关配置和运行时关系状态。角色素材既被桌面管理页使用，也可能进入提示词、场景和图片生成流程。

## 关系与场景

`apps/backend/core/roles/relationship_runtime/` 负责关系快照、持久化、寂寞计算和维护循环。`SceneFollowupRuntime` 负责场景追问状态。它们为 Proactive、Drift 和自动 CG 提供上下文，但不直接拥有 Agent 回合。

## 修改影响

- 修改角色 schema：同步检查 `models.py` 序列化、manifest 迁移、桌面共享类型、表单适配、渠道绑定和角色运行时装配。
- 修改角色删除：检查会话、对话线程、关系状态、记忆、调度任务、工作区和素材清理。
- 修改心情或关系：检查主动触发条件、提示词装配、场景判断和桌面展示。
- 修改素材分类：检查角色素材页、选择器、图片提示词与本地资源传输。
- 修改自动差分生成或 bridge 等待策略：同步检查五张差分的最终角色快照、素材分组刷新和图片生成请求超时。
- 自动生成角色差分：五张带纯白背景的差分图串行生成并持久化到 `AI 差分` 分类后，bridge 会同步角色会话的运行时配置，再返回最终角色快照；`roles.differences.generate` 使用图片生成长超时，renderer 依靠最终快照刷新素材分组。
- 导入桌宠素材包：`pet.json` 的预览图字段兼容可选；提供 `previewPath` 时仍校验并保存预览图。

## 不变量

- 业务入口显式携带 `role_id`。
- 角色身份与渠道账号绑定分离；渠道标识不能替代角色主键。
- 运行时派生状态不应反向覆盖角色持久化定义，除非经过 owning service。
