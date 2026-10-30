# 场景观察（scene）

系统插件。提供 `SCENE`：回合结束后用轻量模型观察当前场景，供自动场景 CG（NovelAI）和场景追问读取。只观察有人登记需求的角色：其他插件用 `SCENE.request` 登记，宿主的场景追问策略经 `SCENE_HOST.followup_wanted` 判断。

## 配置

```toml
[plugins.scene]
observation_enabled = true   # 场景观察，默认开
```

没有配置轻量模型时不观察。旧的 `[agent.scene_observation] enabled` 会在启动时一次性移到 `[plugins.scene] observation_enabled`，并删除旧表；`[plugins.scene]` 已有该键时保留原值。

## 生命周期

- 换代时，新一代发布后才开始观察。
- 插件设置页改配置（代内重载）或代内重新启用后，立即恢复观察，不必等下次换代。
- 本代被丢弃前，宿主先停止观察并等进行中的观察结束。

状态存于 `<workspace>/scene/state.json`，首次写入时会导入旧 `scene_awareness` 插件留下的状态。

## 插件关闭时

`get(SCENE)` 为空，不观察，NovelAI 不登记场景 CG 需求，聊天照常。
