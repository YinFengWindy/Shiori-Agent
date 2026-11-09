# 桌宠与独立形象插件

状态：已确认。#1006、#1007 的实现遵循本文边界；精灵提取见 PR #1008，2.5D 接入基于该提取继续推进。合并及验收状态以各自 PR 的记录为准。

维护者于 2026-11-09 确认：桌宠保留角色、交互、语音和直播业务，Codex 精灵图与新的 2.5D 形象分别成为独立插件。本期目标是提供的 `prelulu-avatar-package/v1` 包。此前讨论中的 Live2D Cubism 接入不属于本期。

## 用户行为与所有权

用户在桌宠入口选择角色的形象，可使用精灵图或 2.5D 包。两种形象共用桌宠气泡、语音输入、唯一播报队列和 Bilibili 直播陪伴。只安装其中一种形象插件即可使用对应形象。

| 插件 | 所有权 |
| --- | --- |
| `desktop_pet` | 角色绑定、当前形象引用、显示策略、位置偏好、气泡内容和生命周期、语音交互与播报队列、直播、Agent 动作入口 |
| `pet_codex_sprite` | 精灵包导入与存储、图集状态及动作映射、精灵绘制、实际 surface 的创建和销毁 |
| `pet_2d` | `prelulu-avatar-package/v1` 导入与存储、绑定与预计算数据解析、2.5D 绘制和音量口型、实际 surface 的创建和销毁 |

两个形象插件分别声明 `dependencies: [desktop_pet]`。桌宠通过版本化服务契约发现提供者，不反向声明形象插件的硬依赖或可选依赖，不形成依赖环。

语音、弹幕接收和回复生成不进入形象插件。形象插件不建立第二条 TTS 队列，也不自行播放同一份音频。语音合成仍由现有 TTS provider 提供；原生采集、解码与播放仍归宿主，沿用 [P7 音频边界](2026-11-02-p7-scope-and-audio-boundary.md)。

## 为什么让形象插件拥有 surface

现有 [SurfaceRoot](../../apps/desktop/renderer/src/surface/SurfaceRoot.tsx) 按窗口所属插件加载该插件的 surface 组件；[前端入口](../../packages/sdk/src/contract/frontend.ts) 只提供 `ui/background/surface`。现有 JSON 服务不能传递 React 组件。

因此采用已存在的 surface 所有权：桌宠决定显示谁、在哪里显示及展示什么回复；选中的形象插件负责具体窗口和绘制。气泡视图、拖动、菜单与语音手势的通用前端部分提取为一个构建时共享模块，两个形象插件复用。它不是新的运行时插件层，业务状态继续由桌宠持有。共享代码不通过跨插件源码相对 import 获取。

为防止准备窗口首帧闪现，既有 `SurfaceSpec` 增加可选 `visible`（默认 `true`）；宿主发布 `surface.lifecycle` 事件报告实际窗口关闭或 renderer 不可用。两项以 SDK 4.1.1 提供，避免用心跳猜测窗口存活，不增加已有 Protocol 方法。

不为此次接入增加跨插件 React 挂载机制，不将形象业务放入 Electron 主进程，不增加 capability、phase 或插件层。

## 数据与通信契约

桌宠持久化的形象引用包含 `{ provider: { plugin_id, service_id }, model_id }`。素材、格式版本、图片路径与格式专有参数归对应形象插件。公共描述只包含名称、预览、显示尺寸、受支持的动作及必要的展示能力。

公共展示动作使用模型声明的动作 ID，精灵图行名留在精灵插件。Agent 工具仅暴露当前模型实际支持的动作；2.5D 不需要伪装成精灵图的 running-left 等状态。

采用现有 `SERVICES`、插件事件及已声明依赖的 background RPC。服务契约与消息名称在实现时集中定义、校验和生成，不散落字符串副本。最小交互如下：

1. 形象后端通过 `SERVICES` 注册同一版本的模型/呈现契约。桌宠用 `client.services.list/call` 发现提供者、管理模型并提交呈现请求。
2. 形象 background 先订阅自身后端事件，再向自身后端报告就绪。后端服务通过自己的 `RPC.emit` 发送呈现命令；服务已注册、事件已发出都不等于模型已显示。
3. 短服务调用只返回接受或拒绝。模型加载完成、失败、关闭以及交互结果，由形象 background 经 `dependency("desktop_pet").background.call(...)` 回报桌宠。
4. 桌宠在发命令前登记请求；命令和回报携带 `request_id`、呈现实例 `lease_id`、角色与模型身份。桌宠拥有等待期限；失败、超时、取消或提供者失效均终止等待，迟到回报不能恢复已撤销的实例。
5. 实际 surface 用 retained state 保存模型、气泡与持续状态，重载后重放；瞬时动作使用 message。模型实例和动画帧循环始终留在形象插件内。

这条路径不需要 Python 服务等待 renderer 回调，也不需要桌宠读取形象插件的私有 RPC。现有 [直播输出](../../plugins/desktop_pet/backend/live_output.py) 已采用事件驱动输出、显式回报结果的模式；服务调用与依赖授权边界见 [communication.py](../../apps/backend/desktop_bridge/plugin_rpc/communication.py)。

已确认的生命周期验收要求：同角色更换形象时先准备新实例，准备成功再替换当前展示，语音和直播仍由桌宠持有；准备失败保留旧选择与可用展示。换角色、停用或失去当前提供者时撤销旧实例及其输出。提供者缺失时保留已选模型引用并显示不可用原因，不默默切换成别的形象。隐藏窗口与结束直播连接的原有区别不在此次拆分中悄然改变。

桌宠通过已有 `plugins.reloaded` 宿主事件撤销被替换提供者的租约：此时旧 RPC 所有者已退出，不能依赖其卸载回调补发失效报告。重新启用后，提供者的就绪通知只恢复当前仍有效的显示意图；隐藏或新选择会撤销恢复。已退休实例不向后继提供者发送 update 或 close。

## 目标样包与运行时

调查样本为维护者提供的 `character (1).zip`，归档 SHA-256 为 `478d98a59a753d076ff03824a6e5ac7b5e4150dcc07f27cbb51a9f0ae68bd500`。样本不作为公开测试素材提交；自动回归使用合成的小包，实机验收记录样本摘要。

- `manifest.json`：`prelulu-avatar-package/v1`；`cubism: false`、`amplitudeOnly: true`、`visemes: false`。
- `binding.json`：`prelulu-avatar-binding/v1`；25 个原始图层、嘴部定位和修正记录，源图 1024×1024 到画布 768×768 的配准。
- `rig/rig.json`：`prelulu-rig-bundle/v1`；28 个绑定图层，含自动补出的左右闭眼与闭嘴层。
- `rig/baked.json`：`prelulu-rig-bake/v1`；包含预处理图层、头发与眼睑数据及 `parametric` 嘴部数据。
- 本次调查核对了清单的 68 个文件，大小与 SHA-256 全部匹配。ZIP 不含渲染运行时代码。

包记录的 rigger、runtime、PSD worker、genericparts 源码哈希与 [Anime2.5DRig 的固定提交](https://github.com/852wa/Anime2.5DRig/tree/7ddbd9943ea3152561b3dc8348fd752c850f3e95) 一致。维护者随后提供[实际预览页](https://paper-avatar-preview.zjudn2013.workers.dev/c/job_188e29e4691e94dcf75a7937)，其中的 `main.042bf1e250766319.js` 与 `package-loader.f2b666a85c6bf5f6.js` 包含完整消费者。prepared、mouth、hair、lids 的四个算法标识与样包一致；用该播放器离线加载原 ZIP 的 ready 回报确认四段 baked 数据均被使用，没有回退到重新绑定。

产品只实现已核验的数据消费语义，不加载网站脚本。样包与网站当前分享包的角色 ID、manifest 哈希不同，外观验收使用原 ZIP 在原播放器中的本地参考。原播放器提供的短剧、表情编排等能力不是包内动作资源，不因此自动进入本次插件范围。

2.5D 任务先建立格式解析与样包还原证据，再接到桌宠。优先消费包中的绑定和预计算结果，保留 PSD 为原始可编辑素材，不在每次启动时重新推理、拆层或自动绑定。不同 schema 或无法解释的数据必须明确拒绝，不能丢弃修正数据后仍声称导入成功。

## 口型与播放

本期验收随 TTS 实际播放音量开合的基础口型，覆盖普通语音回复和直播回复。样包不提供音素口型，不增加 AEIOU、摄像头面捕、用户麦克风驱动角色口型或自动生成新动作。

音量和播放起止从实际播放所有者取得。当前 [VoicePlaybackRenderer](../../apps/desktop/renderer/src/voice/playbackController.ts) 已有真实播放 ID 和开始/结束回执，但 [公开原生音频接口](../../packages/sdk/src/contract/native.ts) 没有向插件发布播放进度或振幅的契约。实施需补齐受 owner/generation/playback 身份约束的通用播放观测事件，桌宠将有效信号路由到当前呈现实例，2.5D 插件只负责把信号变成嘴部参数。

不得用 TTS 请求开始时间代替实际播放开始，不得另播一份音频测量振幅。结束、取消和播放失败均复位嘴部；旧音频回报不能驱动新角色或新实例。SDK 4.1.2 新增 `native.audio.playback` 事件与可选 `NativeAudio.request_id`，已有 `audio.play` 方法保持兼容。宿主只向通过 token、owner 和 generation 校验的所属 background 分发实际开始、RMS 和结束；桌宠按请求号及播放 ID 关联唯一队列中的任务，再写入当前实例的展示状态。

## 兼容、验证与范围

精灵提取必须迁移已有素材、选择和动作，保留角色启用状态、位置、语音与直播设置；用户不重新导入旧包。文件迁移和角色命名空间更新需可重试，失败保留原数据，读取和清理都遵循明确的所有者。禁止用删除旧目录后重建的方式迁移。

验证覆盖：旧数据迁移与失败恢复；模型导入的路径和大小边界、哈希及引用完整性；选择与单个可见展示；真实插件装配与依赖停用；快速切换、迟到回调与资源清理；聊天/直播共用播报、来源隔离取消；实际播放口型。检查按变更及直接调用者执行，保留既有 CI，不以此规划自动运行完整本地套件。

真实 Electron 验收需要检查透明背景、拖动、气泡、模型还原、眨眼与头发运动、声音和口型同步，以及停用后的窗口、音频和 GPU 资源回收。源码、哈希或单测通过均不能替代这些结果。

本期不含标准 Cubism、图片生成、自动拆层服务、PSD 编辑器、OBS/推流、多角色并发或其它直播平台。原始 PSD 的生成工具尚未查明，不影响直接消费已提供包的目标；确切渲染兼容性仍须在实现中验证。
