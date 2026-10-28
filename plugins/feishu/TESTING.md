# 独立运行 Python 测试

将插件复制到 Shiori 仓库外；wheelhouse 只需 `shiori_sdk-4.0.0` wheel。插件显式声明 `shiori-sdk>=4.0.0,<5` 与 lark-oapi、httpx、pydantic；测试依赖 `shiori-sdk[testing]>=4.0.0,<5` 与 Pillow，不安装宿主或旧 testkit。

在插件副本目录执行（将 `/path/to/wheelhouse` 替换为实际绝对路径）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

禁止 editable 安装或指向原仓库的 PYTHONPATH，也不要复制原仓库 `tests/` 或根 conftest。公共 fake 来自 `shiori_sdk.testing`；平台命令、凭据引用、消息/附件、流式与重连在本插件验证。`ctx.channels.group` 和 `session_manager.identity_index` 注入宿主协调服务；单测用 SDK fake，真实实现不复制到插件。

测试不联网：飞书 REST 由 `httpx.MockTransport` 替代，长连接由假连接替代；`tests/test_ws.py` 另用真实 lark-oapi 客户端在私有事件循环上做离线校验，lark-oapi 升级时它会先报出本插件依赖的私有接口是否变化。

保存的应用在加载时的注册、规则持久化与孤儿清理在本插件 `tests/test_accounts.py` 验证。宿主 `tests/backend/desktop_bridge/runtime/test_plugin_management_feishu.py` 只经 bridge 请求验证真实重载与角色/账号删除；头像缓存由宿主的中性测试覆盖。平台集成通过公开渠道启动与外部网络替身装配，飞书的独立测试无需宿主 fixture。每轮修改可运行 `uv run python -m scripts.verify_plugin_tests --plugins feishu` 获得仓库外 wheel 安装、来源与异步执行证据。

# 用真实飞书应用手动验收

自动测试覆盖不到飞书服务端的真实行为（长连接投递、CardKit 流式效果、频控），合并前需要用真实应用走一遍。

## 1. 创建应用

1. 打开 [飞书开发者后台](https://open.feishu.cn/app)（Lark 国际版为 <https://open.larksuite.com/app>），创建**企业自建应用**。商店应用不支持长连接。
2. 「添加应用能力」里添加**机器人**。
3. 「权限管理」开通 [README 的应用权限](README.md#应用权限) 里列出的权限：`im:message.p2p_msg:readonly`、`im:message:send_as_bot`、`im:message`、`im:resource`、`cardkit:card:write`、`contact:user.base:readonly`（名称以后台实际显示为准）。
4. 在「凭证与基础信息」复制 App ID 和 App Secret。

## 2. 在 Shiori 里启用

1. 角色详情 › 账号：添加账号，选择飞书或 Lark 区域，填入 App ID、App Secret，点击「连接」。App Secret 也可以写成 `${FEISHU_APP_SECRET}` 引用环境变量。
2. 再添加一个不同 App ID 的应用，确认两个账号分别显示连接状态、机器人名称和本应用的机器人 `open_id`；凭据验证失败时原账号保持原连接。
3. 确认「已交互私聊（本应用）」只包含该应用已经交互过的私聊，`open_id` 属于当前应用，不是租户完整通讯录。

## 3. 订阅事件（长连接）

1. 开发者后台「事件与回调」›「事件配置」，订阅方式选**使用长连接接收事件**并保存。**保存时 Shiori 必须在线且该账号已连上**，否则后台会提示未检测到连接。
2. 「添加事件」：`im.message.receive_v1`（接收消息）。
3. 「版本管理与发布」创建版本并发布，可用范围要包含测试账号（企业管理员可能需要审核）。之后开通或调整权限，也要发布新版本才生效。

## 4. 发布后绑定会话

1. 在飞书里搜索机器人并发一条私聊消息。账号归属的角色会收到这条消息；账号未归属角色、未在线或响应规则关闭了私聊时，消息被拒绝，账号状态与日志显示 `私聊未进入角色（账号未归属、未在线或响应规则拒绝）：chat_id=oc_…，open_id=ou_…`。
2. 在私聊里发送 `/chatid`：机器人回复「会话类型：私聊」与「私聊 chat_id：oc_…」，这条命令不进入角色。需要指定这个会话（如主动推送的目标）时使用这个 `oc_…`。
3. 在设置 ›「我的身份」生成配对码，用自己的飞书账号私聊发给机器人：机器人回复「已绑定」，配对码不进入角色，之后这位发送者被识别为你。

## 5. 验收清单

- 文本私聊一问一答；回复以卡片逐字打出，结束后聊天列表预览不再是「[生成中...]」。
- 回复（流式卡片或普通卡片）以引用形式回复触发它的那条用户消息；主动推送、定时任务的消息不带引用。
- 超过约 4000 字的回复：第一张卡片原地结束，其余内容以新卡片补发，只有第一张带引用。
- 图片、文件、富文本（带图）消息都能被角色看到。
- 引用机器人的回复、引用自己的旧消息（含图片）后提问，角色能看到被引用内容。
- 回复过程中发送 `/stop`：回复中断；下一轮开始时上一张未完成的卡片被收尾。
- 让角色用 `message_push` 主动发文本、图片、文件。
- 撤销开发者后台的 `cardkit:card:write` 权限后再对话：回复仍以普通卡片送达。
- 发送者的昵称与头像：第二条消息起小手机里显示发送者昵称，会话列表与聊天页显示其飞书头像；撤销 `contact:user.base:readonly` 后换一个新用户私聊，消息照常收发，日志有一条警告。
- 断网再恢复：状态先变为未连接，随后自动重连并继续收消息。
- 在账号详情编辑 App Secret 草稿时连接不变；断开后点击「连接」，先验证机器人身份再只连接该账号；`config.toml` 中不出现飞书凭据。
- 账号详情「断开连接」只停该应用；再点「连接」只重建该应用连接，重启 Shiori 后断开状态仍保留，其他账号继续在线。
- 停用插件：日志出现「飞书渠道已停止」，进程里不再有 `feishu-ws` 线程。
- Lark 国际版账号至少验证一次能建立连接。

注意：飞书长连接是集群模式，同一应用有多个客户端在线时每条消息只随机投递给其中一个。不要让多台设备上的 Shiori 同时使用同一个应用。
