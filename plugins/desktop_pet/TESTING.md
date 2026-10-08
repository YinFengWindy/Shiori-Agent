# 独立运行 Python 测试

复制插件到仓库外，准备包含 `shiori-sdk` 3.1.10 wheel 的私有 wheelhouse；无需安装宿主、testkit 或默认记忆。进入插件副本：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置 `PYTHONPATH` 指向原仓库。插件声明 httpx、Pillow、pydantic、qrcode（B 站登录二维码 PNG）与 websockets（直播弹幕连接）；测试只额外依赖 SDK testing，覆盖包校验/导入、角色单点启用、RPC、动作限流、资源清理、B 站扫码登录和直播运行引擎。整包暂存使用 `shiori_sdk.testing.packages.stage_plugin_package`。

B 站扫码登录全程不联网：`tests/conftest.py` 的 `bilibili` fixture 用 `httpx.MockTransport` 脚本化 generate / poll / nav 三个接口，测试通过 `scan_code`（86101/86090/86038/0）、`login_valid` 切换平台响应，并经 `BilibiliLoginApi(transport)` 注入；`gate` + `hold_path` 可挂起指定接口的响应，用于验证退出登录、并发轮询和角色删除与在途请求的竞态。真机仍需验收：真实扫码成功后取得 Cookie、`nav` 返回昵称、登录态失效时状态为 `invalid`。

真实 canonical 角色锁、原子保存、升级迁移凭证以及 kernel 停用/重载集成保留在宿主 `tests/backend/agent/plugin_host/test_kernel_desktop_pet.py`，经真实内核加载插件、只通过公开 RPC 与宿主角色存储断言；它们不属于插件的独立安装依赖。

直播运行引擎同样全程不联网：`bilibili` fixture 另外脚本化 `get_info`、首页 `buvid3`、`getDanmuInfo` 三个接口；`danmaku_source` fixture 是可控弹幕源（每次 `run` 是一条连接，测试用 `current.send(...)` 投递弹幕、`current.drop(error)` 断线）；`clock` fixture 是可控时钟（`advance` 推进时间、`settle` 只跑就绪任务），冷却、过期、退避、输出兜底超时与绑定巡检都只按它计时；外部回合用 SDK 的 `FakeExternalTurns`（`answers` fixture 构造回复、忙、挂起与失败的应答）；展示与播报走真实的 `LiveReplyOutput`（`pet_output` / `lost_pet_output` fixture），测试经 `live.reply.outcome` RPC 回报结果。真机仍需验收：登录态下收到的弹幕带完整 uid 与昵称、`getDanmuInfo` 的 WBI 签名与风控、`protover` 2 的 zlib 包、断线重连，以及桌宠气泡与语音的实际输出。
