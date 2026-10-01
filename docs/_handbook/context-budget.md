# 模型输入预算

模型注册显式保存 `context_window_tokens`、`max_output_tokens`。旧条目缺失时保持未填写，角色可浏览，但不可发起模型对话。设置和首次引导不从模型名称推测容量。

`agent.max_tokens` 是本次输出上限；注册的最大输出能力只是校验上限。带模型档案的未限定输出请求明确发送注册上限并预留相同数量；辅助请求按实际 provider 策略应用更小上限。`extra_body` 不能覆盖消息、模型、工具、输出预算或响应格式。

`agent.context` 的 `trigger_ratio`、`target_ratio`、`safety_margin_tokens` 默认分别为 0.75、0.4、4096。比例以模型上下文窗口为基数，触发与目标都不超过 `窗口 − 实际输出上限 − 安全余量`。无有效输入空间或输出超过模型能力时明确报错。已移除旧的固定 `consolidation_input_token_threshold` 设置。

预算只计算 provider 最终归一化后的完整消息、工具 schema 和响应格式，不再额外扣 schema。初始请求、工具循环、空回复恢复、阶段性收尾共用此依据。初始超预算仍调用现有 `ensure_consolidation`，以显式预算压力启动既有记忆窗口选择；重新渲染后按完整请求检查目标，再沿用既有裁剪计划。本阶段没有新摘要、压缩游标或控制器。

用量锚点保存在运行时，绑定实际连接、模型、可见上下文、身份绑定视图和发送请求快照。同一角色的用户上下文共用视图，群聊和陌生私聊各自隔离。历史只追加及带明确标记的系统 context frame 替换可用旧实际输入加本地差值；历史重写、模型/连接/身份绑定或未知系统提示/schema 变化时失效。迟到响应不能覆盖较新请求；辅助调用不改写对话锚点。

状态来源为 `actual`、`anchor_delta`、`local`。缺失用量为 null，单次 input/output/cache 与累计已知用量、未知调用数分别记录在 `context_retry.request_usage`。流式请求使用公开的 `stream_options.include_usage`；未返回 usage 不生成零值锚点。

本地估算按字符类别计算文本，非 ASCII 字符按每字 2 token 保守计入。图片独立预留 4096 token（显式 low detail 为 85），不读取 Base64 文本长度作为 token 数。它仍是估算；真实 provider 的图片计算可能不同，后续实际 prompt_tokens 用于校准。

验证使用了受控中文、带图、非缓存 usage、流式尾部 usage、动态 context frame、真实提示渲染与会话续接、身份/连接切换及并发迟到响应测试。未调用真实 provider；中文/图片误差和缓存命中效果仍未取得真实数据，不能据测试桩数值宣称已验证。
