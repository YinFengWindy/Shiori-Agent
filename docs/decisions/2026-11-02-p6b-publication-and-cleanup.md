# P6b 清零与场景发布通知评估

范围：#907 第 6 步，接在角色设置插件化之后。只清理主动行为外迁留下的依赖，不扩展 P7/P8。

## 保留 SCENE_HOST.on_published

不把 `SCENE_HOST.on_published` 机械替换为 `PROCESS_RESOURCES.on_published`。当前两个通知代表不同的时机：

| 路径 | 进程资源发布 | 场景观察开始 |
|---|---|---|
| 冷启动 `AppRuntime.start` | 核心代开始、账号发布之后，`start_channels` / `channel_host.start_all` 和 dispatcher 任务创建之前 | 渠道已启动、dispatcher 和出站任务已创建，进入 `_publish_background` / `RuntimeBackground.start` 后 |
| 换代 `RuntimeReloadMixin._publish_pointer` | 新指针提交之后 | 进程资源已发布、旧后台组被 stop、新后台组接手时 |
| 已发布代内启用或重载 | 注册回调时立即调用 | 注册回调时立即开始观察 |

进程资源的发布回调异常会被记录并继续发布；场景适配器的同步回调不采用这套异常处理。两者不能只因名字相同就合并。要统一通知，需要单独定义运行时就绪阶段及失败语义，并回归冷启动、换代、候选丢弃和代内启停；本次不扩大生命周期重构。

## 清零结果与边界

- 核心主动提示词索引和行为段由 proactive 插件在 `PromptRendering` 提供。文件位置是 `workspace/roles/<role_id>/PROACTIVE_CONTEXT.md`；无角色或插件停用时没有此贡献。规则模板与读取已由插件 `context_panel.py` 拥有。
- 宿主通过 `SessionManager.presence` 读写同一会话库，不再跨层注入第二份 `presence`。插件仍使用 SDK `SESSIONS.presence`。
- 已有「核心模块不 import 插件」契约包含全部宿主包，并禁止 `plugins`，自然覆盖 proactive；不叠加等价的第二条规则。
- 崩溃报告的 `proactive_v2`、旧事件别名、预览 RPC 和场景主动专用端口已由前置 PR 删除，本次只核对无回归。
- 真实宿主冒烟加载 proactive 和 memory_optimizer，再通过插件启停路径同时停用两者，确认聊天、引用标记清理和核心 presence 仍正常。
- 内置 Drift skill 随插件打包，以及插件自拼 `role:` 会话 key 的收口继续延期。无数据路径迁移，不新增「立即整理」。
