# 独立运行 Python 测试

将本插件目录复制到 Shiori 仓库外。准备私有 wheelhouse，其中必须有 `shiori-agent`、`shiori-plugin-testkit`、`shiori-plugin-default-memory` 的 0.1.0 wheel。这些私有包不发布到 PyPI；其余第三方依赖（包括 `lark-oapi`）由包元数据解析。

在插件副本目录执行（将 `/path/to/wheelhouse` 替换为实际绝对路径）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse /path/to/wheelhouse/shiori_agent-0.1.0-py3-none-any.whl /path/to/wheelhouse/shiori_plugin_testkit-0.1.0-py3-none-any.whl /path/to/wheelhouse/shiori_plugin_default_memory-0.1.0-py3-none-any.whl ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable。不要设置 `PYTHONPATH` 指向原仓库，也不要复制原仓库 `tests/` 或根 conftest。测试不联网：飞书 REST 由 `httpx.MockTransport` 替代，长连接由假连接替代；`tests/test_ws.py` 另用真实 lark-oapi 客户端在私有事件循环上做离线校验，SDK 升级时它会先报出本插件依赖的私有接口是否变化。

宿主仓库中的 `docs/agents/plugin-testing.md` 说明 wheelhouse 构建与 CI 隔离验收；本插件的运行不依赖该文档所在仓库。

# 用真实飞书应用手动验收

自动测试覆盖不到飞书服务端的真实行为（长连接投递、CardKit 流式效果、频控），合并前需要用真实应用走一遍。

## 1. 创建应用

1. 打开 [飞书开发者后台](https://open.feishu.cn/app)（Lark 国际版为 <https://open.larksuite.com/app>），创建**企业自建应用**。商店应用不支持长连接。
2. 「添加应用能力」里添加**机器人**。
3. 「权限管理」开通以下权限（名称以后台实际显示为准）：
   - `im:message.p2p_msg:readonly`：读取用户发给机器人的单聊消息
   - `im:message:send_as_bot`：以应用的身份发消息
   - `im:message`：获取与发送单聊、群组消息（读取被引用的消息、撤回失败的流式卡片需要）
   - `im:resource`：获取与上传图片或文件资源
   - `cardkit:card:write`：创建与更新卡片（流式卡片需要；缺少时回复会退回普通卡片，不影响收发）
4. 在「凭证与基础信息」复制 App ID 和 App Secret。

## 2. 在 Shiori 里启用

1. 设置 › 插件 › 飞书 › 账号：添加账号，选择飞书或 Lark 区域，填入 App ID、App Secret，点击“保存并连接”。App Secret 也可以写成 `${FEISHU_APP_SECRET}` 引用环境变量。
2. 再添加一个不同 App ID 的应用，确认两个账号分别显示连接状态、机器人名称和 `open_id`；凭据验证失败时原账号保持原连接。
3. 确认私聊目录只包含各应用已经交互过的私聊，`open_id` 属于当前应用，不是租户完整通讯录。

## 3. 订阅事件（长连接）

1. 开发者后台 「事件与回调」 › 「事件配置」，订阅方式选**使用长连接接收事件**并保存。**保存时 Shiori 必须在线且已连上**，否则后台会提示未检测到连接。
2. 「添加事件」：`im.message.receive_v1`（接收消息）。
3. 「版本管理与发布」创建版本并发布，可用范围要包含测试账号（企业管理员可能需要审核）。

## 4. 绑定角色

在飞书里搜索机器人并发一条私聊消息。消息会因未绑定被拒绝，渠道状态和日志会显示 `未绑定的私聊：chat_id=oc_…，open_id=ou_…`。在角色的渠道绑定里选择「飞书」，类型为私聊，chat_id 填 `oc_…`，保存后重发。

第二个账号的角色归属入站路由与自主选目标由 #425 接入；本插件在此之前仍分别缓存其已交互私聊目标并保持连接、身份和回执隔离。

## 5. 验收清单

- 文本私聊一问一答；回复以卡片逐字打出，结束后聊天列表预览不再是「[生成中...]」。
- 回复（流式卡片或普通卡片）以引用形式回复触发它的那条用户消息；主动推送、定时任务的消息不带引用。
- 超过约 4000 字的回复：第一张卡片原地结束，其余内容以新卡片补发，只有第一张带引用。
- 图片、文件、富文本（带图）消息都能被角色看到。
- 引用机器人的回复、引用自己的旧消息（含图片）后提问，角色能看到被引用内容。
- 回复过程中发送 `/stop`：回复中断；下一轮开始时上一张未完成的卡片被收尾。
- 让角色用 `message_push` 主动发文本、图片、文件。
- 撤销开发者后台的 `cardkit:card:write` 权限后再对话：回复仍以普通卡片送达。
- 断网再恢复：状态先变为未连接，随后自动重连并继续收消息。
- 在账号详情编辑 App Secret 草稿时连接不变；点击“保存并连接”后先验证机器人身份，再热更新该账号。只改其它插件时飞书连接被复用（日志没有「已停止/已启动」）。
- 账号详情“断开连接”只停该应用；“重新连接”只重建该应用连接，重启 Shiori 后断开状态仍保留，其他账号继续在线。
- 停用插件：日志出现「飞书渠道已停止」，进程里不再有 `feishu-ws` 线程。
- Lark 国际版账号至少验证一次能建立连接。

注意：飞书长连接是集群模式，同一应用有多个客户端在线时每条消息只随机投递给其中一个。不要让多台设备上的 Shiori 同时使用同一个应用。
