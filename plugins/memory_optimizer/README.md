# 记忆整理（memory_optimizer）

系统插件，默认启用。后台定时整理每个角色的 Markdown 记忆：把 `PENDING.md` 里待合并的事实并进 `MEMORY.md`，再按需更新 `SELF.md` 的三个固定段落。用角色自己的对话模型（`MODELS`），文档经宿主端口 `MARKDOWN_MEMORY` 读写。

## 配置

`[plugins.memory_optimizer]`：

| 键 | 默认 | 说明 |
|---|---|---|
| `enabled` | `true` | 宿主的插件开关；关掉即不整理 |
| `interval_seconds` | `64800` | 整理间隔（秒，最小 60），按 epoch 起的整倍数对齐 |

在「设置 › 插件 › 记忆整理」的自动表单里编辑。旧的 `[agent.maintenance]`（及根级同名键）`memory_optimizer_enabled` / `memory_optimizer_interval_seconds` 在启动时一次性迁入本表并从 `config.toml` 删除：`memory_optimizer_enabled = false` 变成 `enabled = false`，间隔变成 `interval_seconds`（小于 60 的按 60）；本表已有的键不覆盖。

## 运行

整理循环是插件的进程资源：进程里只有一份，第一次 setup 时启动，等到本代发布后先补跑过期角色（从未整理、距上次超过一个间隔、或 `SELF.md` 还没按当前写入规则重写），之后每到间隔边界整理全部角色，一次一个角色。某一轮出错只记日志、跳过这一轮。换代和代内重载只重新绑定宿主服务与间隔，循环只用已发布代的那一份（间隔也从它读），没发布就被丢弃的候选代不留影响；在途整理若跑在已退役的一代上会被取消（待合并事实放回 `PENDING.md`），随即在当前代重跑该角色。没有模型注册时不启动。

整理状态（`last_memory_optimized_at`、`self_rules_version`）仍存在角色记录的 `memory_init_state` 里，路径与格式与插件化之前一致。

## 界面

插件 provide `MEMORY_OPTIMIZER`（`active_run()`）；宿主据此在聊天右栏「任务」面板列出正在进行的「记忆维护」任务（不可取消）。

## 插件关闭时

循环停止，在途整理取消并回滚待合并事实；任务面板不再出现记忆维护任务，聊天与其他后台任务照常。重新启用后按启动补跑规则继续。
