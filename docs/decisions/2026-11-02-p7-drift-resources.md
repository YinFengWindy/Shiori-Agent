# P7：Drift 技能资源归 proactive 所有

范围：#963，承接 #907 留下的内置 Drift skill 分发项。

`meme-manage` 和 `create-drift-skill` 的源文件迁入 proactive 的 `skills/`。插件 wheel 显式携带这两个资源目录；桌面冻结打包沿用通用插件 staging，不在宿主增加技能名单。插件按自身模块位置读取资源，删除 `PROACTIVE_HOST.builtin_skills_dir`。

这两个技能此前也出现在普通聊天的技能目录里，迁移不能只修 Drift 的调用者。proactive 在 `TurnStarting` 中将用户显式提及的包内技能加入 `skill_names`，再通过 `PromptRendering` 提供技能目录与激活内容。宿主与插件复用 `shiori_sdk.skills.collect_skill_mentions` 的既有提及语法、名称过滤和去重规则；工作区同名技能由核心继续选择和加载，插件不重复注入。目录和激活内容使用已有 `skills_catalog` / `active_skills` 段名，继续服从预算裁剪、上下文帧归属和最小请求规则。插件停用后其事件处理器撤回，普通聊天不再选择或加载包内技能。

角色自己的 `roles/<id>/drift/skills` 仍优先于包内技能。状态及工作文件仍写在原角色目录，安装目录只读；普通聊天的工作区 `skills/` 覆盖规则不变。无需迁移用户数据，不改变技能正文。
