# Computer Use

独立的 v2 Windows 桌面操作插件。工具通过现有插件管理启停和发现，不依赖 Browser Use、桌宠或屏幕感知。截图、窗口身份和控件引用通过共享 MCP ToolResult 进入当前聊天模型；不创建第二个 Agent，也不切换视觉模型。

## 运行组件

在仓库根执行 `pnpm prepare:computer-use`。固定的独立 Cua Driver **0.28.2** 来自官方 `cua-driver-rs-v0.28.2` release；下载归档和两个安装文件的 SHA256、来源及 MIT 许可证信息记录在 `native-runtime.json` 和 `LICENSE.cua-driver`。

首版支持 **Windows x64**。无需全局 npm、系统 Python、云服务或 UAC 安装。构建脚本把 `cua-driver.exe`、`cua-driver-uia.exe`、版本清单和许可证收集到 `native/computer-use`。开发准备的解压使用本 checkout 的 `.venv`；插件运行只启动原生 `mcp --direct`，不会连接已有 daemon。缺失组件会明确报错。

Driver 的子进程、配置、临时目录、遥测目录均由插件管理；状态目录位于 workspace 的 plugin-data 内。遥测和自动版本检查关闭，Driver 环境中的外部 `CUA_*` 配置不继承。插件只终止自己启动的驱动进程树，绝不关闭被操作的应用。

## 工具约定

提供 `computer_list_windows`、`computer_get_window_state`、`computer_click`、`computer_type_text`、`computer_press_key`、`computer_hotkey`、`computer_scroll` 和 `computer_release`。参数 schema 从固定 binary 的 MCP tools/list 获取并缩减为本插件实际支持的窗口接口；会话、socket、进程启动、配置、桌面全局目标和文件输出不对模型开放。

先发现窗口，再读取指定 `pid` + `window_id` 的状态。保留原始 `snapshot_id`、`element_token`；额外的 `observation_id` 区分驱动重启后重用的快照编号。动作须携带这三项对应的观察身份；控件操作使用原始 token，像素操作使用返回截图内的坐标。重新观察会使旧引用失效，窗口进程重建、移动或 DPI 改变后须再次观察。不会用其他窗口替代失效目标。

同一桌面由一个角色的宿主回合独占，模型思考期间仍保持所有权；其他角色、回合、插件代际和 Shiori 进程收到 busy 错误。被动回合重试、直接 reasoning loop、后台 Agent loop 和 drift loop 均有回合资源边界。正常结束、超时、取消、显式释放和插件停用都会先关闭输入入口，再回收驱动，最后释放桌面。已停止的回合不能重新开启输入。

## 验证过的边界

- 仅操作完整位于主显示器、未最小化的窗口，包括主屏最大化窗口。使用 DWM 的可见物理边界，避免把不可见 resize border 当作跨屏。跨屏和其他显示器窗口明确失败；不承诺多显示器输入支持。
- 鼠标坐标是当前窗口截图内的像素，不是屏幕绝对坐标。Windows 实机验收覆盖 150% / 144 DPI 的 UIA 点击和截图坐标点击。
- Cua Driver 0.28.2 的后台组合键在受控 WinForms 应用中出现了只插入普通字母、没有执行组合键的部分效果。因此 `hotkey` 和带 `modifiers` 的 `press_key` 在后台模式下于输入前拒绝；调用者必须显式选择 `delivery_mode="foreground"`。插件不会自动升级到前台。前台模式会短暂切换焦点。
- `effect="unverifiable"` 不代表动作成功。每次动作后应重新观察目标状态；中文输入和快捷键的验收以应用实际内容及事件状态为准。`type_text` 插入文字，不应假定会覆盖原内容。

验收与独立 wheel 命令见 `TESTING.md`。
