---
title: 持久世界与演出
kind: 领域说明
status: 当前有效
last_verified_commit: 12f37fe5
source_paths:
  - world_simulation/
  - desktop_bridge/world_simulation_handler.py
  - desktop_bridge/world_presentation_assets.py
  - desktop/renderer/src/world/
  - desktop/src/localAssetRegistry.ts
related:
  - roles.md
  - desktop-and-bridge.md
---

# 持久世界与演出

## 模块边界

`world_simulation/` 拥有世界实例、共享时间线、事件结算、决策屏障、角色模板快照和演出协议。`WorldRepository` 将权威事实与派生的播放游标保存到独立 `worlds.db`；React 世界工作台只消费 bridge read model，不直接读数据库。

角色进入世界时会冻结为 `RoleTemplateSnapshot`，角色素材复制到世界私有目录。后续角色修改或删除不能改变已有世界中的 persona、心情立绘、avatar 或声音配置。`WorldVisualResolver` 按“当前 mood、默认 mood、avatar、剪影”解析冻结素材。

## 演出链路

已提交事件由 `compile_performance_plan()` 确定性编译为版本化 cue。`WorldPresentationAssetResolver` 在 bridge read boundary 将 `{actor_id, mood}` 补成冻结快照中的素材 ID、路径和 avatar fallback；Electron `LocalAssetRegistry` 只为受信字段和工作区内文件签发 `shiori-asset://local/<token>`。

React 在进入 `WorldStage` 前用 `hydrateWorldPresentationAssets()` 将 bridge 路径替换为 opaque URL 并移除原始路径。Pixi adapter 只接收 `PerformancePlan` 与 `WorldAssetManifestEntry`，不读取 bridge、store 或世界数据库；WebGL 失效时切换文本 adapter。

## 修改影响

- 修改世界事实或结算：检查 repository transaction、timeline projection、idempotency、outbox、复制世界和 backfill 因果约束。
- 修改演出 cue：同步检查 Python protocol、renderer parser、checkpoint 恢复、文本降级和 Pixi adapter。
- 修改角色快照素材：同步检查复制边界、`WorldVisualResolver`、bridge asset resolver、本地资源授权与 manifest fallback。
- 修改播放状态：检查 pause/resume/checkpoint 的持久游标、重连重建、skip 和 dispose 清理。

## 不变量

- 世界事实只由结算流程提交；演出进度和纹理缓存都是可重建派生状态。
- 已有世界只读取自己的角色快照，不回读可变角色定义。
- Pixi 不接触本地路径；本地图片只能通过 opaque asset transport 加载。
- 恢复已完成 cue 时不得重复业务 checkpoint。
