"""真实 qqbot schema 与显式 v2 fixture 的插件配置通道回归。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agent.config import load_config_text
from bootstrap.app import AppRuntime, RuntimeFeatures
from shiori_plugin_testkit.packages import stage_plugin_package
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_QQBOT_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "qqbot"
_TOOL_LOOP_GUARD_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "tool_loop_guard"
_HELLO_FIXTURE_DIR = _REPOSITORY_ROOT / "tests" / "fixtures" / "plugins" / "hello"
_NULLABLE_FIXTURE_DIR = (
    _REPOSITORY_ROOT / "tests" / "fixtures" / "plugins" / "nullable_config"
)


def _config(*, extra: str = "") -> str:
    return (
        "[llm]\nregistrations = []\n"
        "\n[agent.maintenance]\nmemory_optimizer_enabled = false\n"
        '\n[proactive]\nenabled = false\nprofile = "quiet"\n' + extra
    )


def _stage_plugin_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stages qqbot (has ConfigModel), tool_loop_guard (has ConfigModel), hello (has
    none) and a nullable-default model."""
    root = tmp_path / "plugin_dirs"
    shutil.copytree(_QQBOT_PLUGIN_DIR, root / "qqbot")
    _ = stage_plugin_package(_TOOL_LOOP_GUARD_PLUGIN_DIR, root / "tool_loop_guard")
    _ = stage_plugin_package(_HELLO_FIXTURE_DIR, root / "hello")
    _ = stage_plugin_package(_NULLABLE_FIXTURE_DIR, root / "nullable_config")
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda workspace: [root]
    )


async def _start_service(
    tmp_path: Path,
    config_text: str | None = None,
) -> tuple[ReloadableDesktopService, Path, AppRuntime]:
    config_text = config_text if config_text is not None else _config()
    path = tmp_path / "config.toml"
    path.write_text(config_text, encoding="utf-8")
    app = AppRuntime(
        load_config_text(config_text),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    return service, path, app


async def _request(service: ReloadableDesktopService, method: str, payload=None):
    return await service.handle(
        {"id": method, "method": method, "payload": payload or {}},
        emit_event=lambda event: None,
    )


@pytest.mark.asyncio
async def test_get_returns_schema_and_default_backed_values(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugin.config.get", {"plugin_id": "qqbot"})

        assert response.error is None, response.error
        assert response.payload["plugin_id"] == "qqbot"
        assert response.payload["schema"]["title"] == "QQBotConfigModel"
        # 未写入过配置：值来自模型默认值补全
        assert response.payload["values"]["app_id"] == ""
        assert response.payload["values"]["client_secret"] == ""
        assert response.payload["values"]["groups"] == []
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_get_reports_null_schema_for_a_plugin_without_a_config_model(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugin.config.get", {"plugin_id": "hello"})

        assert response.error is None, response.error
        assert response.payload["schema"] is None
        assert response.payload["values"] == {}
        # 插件缺席时上面两条同样成立，必须确认它真的被加载了，否则是假绿
        kernel = app.core.plugin_manager
        assert kernel is not None
        assert any(item["id"] == "hello" for item in kernel.states())
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_rejects_a_plugin_without_a_config_model_and_writes_nothing(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "hello",
                "operation_id": "op-unsupported",
                "values": {"anything": 1},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_unsupported"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_rejects_invalid_values_and_writes_nothing(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-invalid",
                "values": {"groups": 123},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_invalid"
        # 校验失败必须原样保留磁盘文件，一个字节都不能改
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_validates_commits_and_survives_a_restart(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-valid",
                "values": {"app_id": "app-123", "client_secret": "secret-xyz"},
            },
        )

        assert response.error is None, response.error
        assert response.payload["plugin_id"] == "qqbot"
        assert response.payload["values"]["app_id"] == "app-123"
        assert response.payload["values"]["client_secret"] == "secret-xyz"
        assert "generation" in response.payload

        # 落盘确认：磁盘文件已包含新值
        on_disk = path.read_text(encoding="utf-8")
        assert "app-123" in on_disk
        assert "secret-xyz" in on_disk

        # 同一 generation 内立即读回一致
        after = await _request(service, "plugin.config.get", {"plugin_id": "qqbot"})
        assert after.payload["values"]["app_id"] == "app-123"
    finally:
        await service.aclose()
        await app.shutdown()

    # 模拟进程重启：脱离当前运行时，从磁盘文件重新解析配置
    restarted = load_config_text(path.read_text(encoding="utf-8"))
    assert restarted.plugins["qqbot"]["app_id"] == "app-123"
    assert restarted.plugins["qqbot"]["client_secret"] == "secret-xyz"

    # 只证明磁盘文件正确还不够：验收标准要求"写入成功后事务化应用并在重启后
    # 保持"，真正需要证明的是重启后的运行时能读回新值，而不只是磁盘字节正确。
    # 用同一份配置文件重新构建一个全新的 AppRuntime + ReloadableDesktopService，
    # 模拟进程重启后重新启动桥接。
    restarted_app = AppRuntime(
        restarted,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await restarted_app.start()
    restarted_service = ReloadableDesktopService(
        restarted_app, path, RoleStore(tmp_path)
    )
    try:
        response_after_restart = await _request(
            restarted_service,
            "plugin.config.get",
            {"plugin_id": "qqbot"},
        )
        assert response_after_restart.error is None, response_after_restart.error
        assert response_after_restart.payload["values"]["app_id"] == "app-123"
        assert response_after_restart.payload["values"]["client_secret"] == "secret-xyz"
    finally:
        await restarted_service.aclose()
        await restarted_app.shutdown()


@pytest.mark.asyncio
async def test_set_refuses_a_value_toml_cannot_represent(tmp_path, monkeypatch):
    """校验通过但落盘会失真的值必须被拒绝，而不是静默写成默认值。

    TOML 没有 null，``toml.dumps`` 会直接丢弃 None 字段。对一个"可空但默认值
    非空"的字段写 null，如果照常提交，重启后读回的是默认值而不是用户存的 null，
    用户的写入被静默改写。这里断言这种情况被识别并整体拒绝。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "nullable_config",
                "operation_id": "op-null",
                "values": {"label": None},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_unrepresentable"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_rejects_a_merge_that_corrupts_an_unrelated_table(
    tmp_path, monkeypatch
):
    """整份文档回读守卫：目标表之外的任何键值变化都必须整体拒绝。

    之前的守卫只重新校验目标插件自己的那张表，对合并逻辑意外改动了别的表
    （例如行扫描定位表头出错）视而不见——目标表校验照常通过，写入照常提交，
    用户配置被静默破坏。这里模拟一次"合并结果本身仍能通过目标表校验，但
    顺带改动了无关表"的合并，断言它现在会被整体拒绝而不是被放行。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        import desktop_bridge.runtime.plugin_config as plugin_config_module
        from desktop_bridge.plugin_config_text import merge_plugin_table as real_merge

        def _merge_but_corrupt_an_unrelated_table(config_toml, plugin_id, values):
            merged = real_merge(config_toml, plugin_id, values)
            assert 'profile = "quiet"' in merged
            return merged.replace('profile = "quiet"', 'profile = "loud"')

        monkeypatch.setattr(
            plugin_config_module,
            "merge_plugin_table",
            _merge_but_corrupt_an_unrelated_table,
        )

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-corrupt",
                "values": {"app_id": "app-1", "client_secret": "secret-1"},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_unrepresentable"
        # 目标表校验本身会通过（app_id/client_secret 都合法），必须靠整份文档
        # 对比才能发现 [proactive] 被意外改动，写入必须整体取消。
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_requires_plugin_id_and_operation_id(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        missing_plugin_id = await _request(
            service,
            "plugin.config.set",
            {
                "operation_id": "op-1",
                "values": {},
            },
        )
        missing_operation_id = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "values": {},
            },
        )

        assert missing_plugin_id.error.code == "runtime_invalid_request"
        assert missing_operation_id.error.code == "runtime_invalid_request"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_get_returns_json_safe_defaults(tmp_path, monkeypatch):
    """默认值必须以 JSON 形态返回，否则 plugin.config.get 会在传输层炸掉。

    ``defaults_for`` 直接从 ``model_fields`` 取默认值，拿到的是原始 Python 对象；
    而这个结果会与已存值合并后经桥接序列化回 renderer。模型里一旦有 Enum /
    datetime / Path / 嵌套模型这类默认值，原样送上传输层就会失败。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service,
            "plugin.config.get",
            {"plugin_id": "nullable_config"},
        )

        assert response.error is None, response.error
        # Enum 默认值必须已经是它的 JSON 值，而不是 Enum 实例
        assert response.payload["values"]["mode"] == "quiet"
        # 最直接的证据：整个响应能被 JSON 序列化
        _ = json.dumps(response.payload)
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_survives_the_kernel_generation_being_replaced(tmp_path, monkeypatch):
    """写入过程中旧 generation 被处置，不能变成 internal_error。

    ``plugin.config.set`` 要等设置事务的锁，期间别的 apply 可能发布新 generation
    并处置旧内核，其 schema 注册表随之注销。若写入路径在锁内再回查注册表，就会
    抛 KeyError 并被外层兜成 internal_error。这里在校验完成后直接把内核的 schema
    注销掉，模拟那一刻的状态。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        kernel = app.core.plugin_manager
        assert kernel is not None
        original_merge = service.plugin_config._settings.apply

        async def _apply_with_disposed_kernel(*args, **kwargs):
            # 模拟旧代被处置：schema 注册表已清空
            kernel.config_schemas.unregister("qqbot")
            return await original_merge(*args, **kwargs)

        monkeypatch.setattr(
            service.plugin_config._settings, "apply", _apply_with_disposed_kernel
        )

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-stale",
                "values": {"app_id": "app-1", "client_secret": "s-1"},
            },
        )

        assert response.error is None, response.error
        assert response.payload["values"]["app_id"] == "app-1"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_identical_retry_is_idempotent_after_unrelated_config_changes(
    tmp_path, monkeypatch
):
    """同一请求原样重试不能因为无关设置变了就被判成操作冲突。

    幂等指纹若取派生出来的整份配置文本，任何无关改动都会让指纹漂移，重试同一个
    operation_id 就会返回 runtime_operation_conflict——而 renderer 的保存队列正是
    靠原样重试来做幂等的。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        payload = {
            "plugin_id": "qqbot",
            "operation_id": "op-retry",
            "values": {"app_id": "app-1", "client_secret": "s-1"},
        }
        first = await _request(service, "plugin.config.set", payload)
        assert first.error is None, first.error

        # 无关设置发生变化：直接改动已提交的配置文本
        service.settings.config_text = service.settings.config_text + (
            "\n[plugins.unrelated]\nflag = true\n"
        )

        retry = await _request(service, "plugin.config.set", dict(payload))

        assert retry.error is None, retry.error
        assert retry.payload["values"]["app_id"] == "app-1"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_identical_retry_hits_memo_even_when_re_deriving_would_now_fail_the_guard(
    tmp_path,
    monkeypatch,
):
    """原样重试必须直接命中幂等 memo，不能重新触发合并与整份文档回读守卫。

    幂等短路曾经发生在派生（合并 + 回读守卫）之后：同一请求原样重试仍会重新
    跑一遍合并与守卫。这里在首次成功后，把已提交的基准文本改成一份 tomllib
    无法解析的文本，模拟"重试时基准文本已经变化到会让守卫拒绝"的场景——如果
    重试真的重新派生，会在这里踩中 ``_assert_config_round_trip`` 的解析失败，
    返回 plugin_config_unrepresentable 而不是命中 memo 返回第一次的结果。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        payload = {
            "plugin_id": "qqbot",
            "operation_id": "op-retry-guard",
            "values": {"app_id": "app-1", "client_secret": "s-1"},
        }
        first = await _request(service, "plugin.config.set", payload)
        assert first.error is None, first.error

        # 基准文本被换成一份语法上无法解析的文本；重新派生必然会在回读守卫的
        # tomllib.loads(original_text) 这一步失败。
        service.settings.config_text = service.settings.config_text + "\n[broken\n"

        retry = await _request(service, "plugin.config.set", dict(payload))

        assert retry.error is None, retry.error
        assert retry.payload == first.payload
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_rejects_a_dotted_key_form_it_cannot_locate(tmp_path, monkeypatch):
    """``[plugins]`` 下用点分键写目标插件（合法 TOML）时必须被明确拒绝。

    定位器只认独立的表头行；``[plugins]`` 表下 ``qqbot.app_id = "existing"``
    这类点分键合法但定位不到，若照常走追加分支会生成 ``plugins.qqbot`` 的重复
    表声明，解析失败后被守卫报出一个跟真实原因（点分键）毫无关系的
    plugin_config_unrepresentable 文案；用户永远存不上，也看不懂问题在哪。

    错误码本身不足以证明新守卫生效了：重复表声明就算不被新守卫拦截，也会在
    下游 ``_assert_config_round_trip`` 解析合并后文本失败时得到同一个
    plugin_config_unrepresentable 错误码，只是文案不同——所以这里额外断言
    消息文本里出现"点分键"，这是只有新守卫才会给出的措辞。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")
        service.settings.config_text = (
            before + '\n[plugins]\nqqbot.app_id = "existing"\n'
        )

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-dotted",
                "values": {"app_id": "app-1", "client_secret": "secret-1"},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_unrepresentable"
        assert "点分键" in response.error.message
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_get_returns_schema_and_default_repeat_limit_for_tool_loop_guard(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service, "plugin.config.get", {"plugin_id": "tool_loop_guard"}
        )

        assert response.error is None, response.error
        assert response.payload["schema"]["title"] == "ToolLoopGuardConfig"
        # 未写入过配置：值来自模型默认值补全，迁移前后默认值都必须是 3。
        assert response.payload["values"]["repeat_limit"] == 3
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_validates_and_persists_repeat_limit_for_tool_loop_guard(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-valid",
                "values": {"repeat_limit": 5},
            },
        )

        assert response.error is None, response.error
        assert response.payload["values"]["repeat_limit"] == 5
        assert "repeat_limit = 5" in path.read_text(encoding="utf-8")

        after = await _request(
            service, "plugin.config.get", {"plugin_id": "tool_loop_guard"}
        )
        assert after.payload["values"]["repeat_limit"] == 5
    finally:
        await service.aclose()
        await app.shutdown()

    restarted = load_config_text(path.read_text(encoding="utf-8"))
    assert restarted.plugins["tool_loop_guard"]["repeat_limit"] == 5


@pytest.mark.asyncio
async def test_illegal_persisted_repeat_limit_fails_load_but_stays_repairable(
    tmp_path, monkeypatch
):
    """#239 补漏：因为自己存量配置非法而 setup() 失败的插件，必须仍然能通过
    plugin.config.set 修复。

    修复前，config schema 是作为 setup 回滚 effect 注册的：setup 一失败就跟着
    其它 effect 一起被回滚注销，plugin.config.get/set 立刻变回
    plugin_config_unsupported——用户唯一的出路是手改 config.toml，而这正是
    AC5（plugin.config.get/set 可读写、校验 repeat_limit）这条验收标准要保证
    永远可用的通道。这个洞不是 tool_loop_guard 独有的：任何在 setup() 里校验
    自己 config_model 的插件（novelai、qqbot）今天都有同样的问题。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(
        tmp_path, _config(extra="\n[plugins.tool_loop_guard]\nrepeat_limit = 1\n")
    )
    try:
        kernel = app.core.plugin_manager
        assert kernel is not None
        state = next(
            item for item in kernel.states() if item["id"] == "tool_loop_guard"
        )
        assert state["state"] == "FAILED"
        assert "repeat_limit" in state["error"]

        # Plugins 页面走的是 plugins.list，不是 kernel.states() 本身：确认
        # FAILED 状态、诊断文案和"有配置表单"这三件事都真的传到了那个通道上，
        # 而不只是内核内部知道。has_config_schema 尤其关键——它就是靠
        # kernel.config_schemas.schema_for() 判定的，本 ticket 修复前它会在
        # FAILED 后翻转成 False，配置入口会直接从页面上消失。
        list_response = await _request(service, "plugins.list")
        assert list_response.error is None, list_response.error
        list_entry = next(
            item
            for item in list_response.payload["plugins"]
            if item["id"] == "tool_loop_guard"
        )
        assert list_entry["state"] == "FAILED"
        assert "repeat_limit" in list_entry["error"]
        assert list_entry["has_config_schema"] is True

        # 依然能读到 schema：FAILED 不等于"配置通道不可用"。
        get_response = await _request(
            service, "plugin.config.get", {"plugin_id": "tool_loop_guard"}
        )
        assert get_response.error is None, get_response.error
        assert get_response.payload["schema"]["title"] == "ToolLoopGuardConfig"

        # 用合法值修复：必须成功，而不是 plugin_config_unsupported。
        set_response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-repair",
                "values": {"repeat_limit": 5},
            },
        )
        assert set_response.error is None, set_response.error
        assert set_response.payload["values"]["repeat_limit"] == 5
        assert "repeat_limit = 5" in path.read_text(encoding="utf-8")

        # 修复后热应用重新加载：插件应当变回 ACTIVE，Plugins 页面同步反映。
        after_kernel = app.core.plugin_manager
        assert after_kernel is not None
        after_state = next(
            item for item in after_kernel.states() if item["id"] == "tool_loop_guard"
        )
        assert after_state["state"] == "ACTIVE"

        after_list = await _request(service, "plugins.list")
        assert after_list.error is None, after_list.error
        after_entry = next(
            item
            for item in after_list.payload["plugins"]
            if item["id"] == "tool_loop_guard"
        )
        assert after_entry["state"] == "ACTIVE"
        assert after_entry["error"] == ""
    finally:
        await service.aclose()
        await app.shutdown()


_QQBOT_SECRET_REFERENCE = "${SHIORI_TEST_QQBOT_SECRET}"


def _qqbot_reference_config() -> str:
    return _config(
        extra=(
            "\n[plugins.qqbot]\n"
            'app_id = "app-old"\n'
            f'client_secret = "{_QQBOT_SECRET_REFERENCE}"\n'
        )
    )


@pytest.mark.asyncio
async def test_get_returns_the_unexpanded_reference_and_its_env_status(
    tmp_path, monkeypatch
):
    """get 必须给出 config.toml 里的原始 ``${VAR}``，而不是运行时展开后的密钥。"""
    monkeypatch.setenv("SHIORI_TEST_QQBOT_SECRET", "resolved-secret-value")
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path, _qqbot_reference_config())
    try:
        # 运行时拿到的仍是展开后的值：插件本身照常能用上密钥。
        assert app.config.plugins["qqbot"]["client_secret"] == "resolved-secret-value"

        response = await _request(service, "plugin.config.get", {"plugin_id": "qqbot"})

        assert response.error is None, response.error
        assert response.payload["values"]["client_secret"] == _QQBOT_SECRET_REFERENCE
        assert response.payload["env_status"] == {"client_secret": "set"}
        assert "resolved-secret-value" not in json.dumps(response.payload)
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_get_reports_a_reference_whose_variable_is_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("SHIORI_TEST_QQBOT_SECRET", raising=False)
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path, _qqbot_reference_config())
    try:
        response = await _request(service, "plugin.config.get", {"plugin_id": "qqbot"})

        assert response.error is None, response.error
        assert response.payload["values"]["client_secret"] == _QQBOT_SECRET_REFERENCE
        assert response.payload["env_status"] == {"client_secret": "unset"}
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_reference_survives_an_unrelated_field_edit(tmp_path, monkeypatch):
    """渲染端保存时整表回传：改一个无关字段不能把展开后的密钥明文写回文件。"""
    monkeypatch.setenv("SHIORI_TEST_QQBOT_SECRET", "resolved-secret-value")
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path, _qqbot_reference_config())
    try:
        loaded = await _request(service, "plugin.config.get", {"plugin_id": "qqbot"})
        values = {**loaded.payload["values"], "app_id": "app-new"}

        response = await _request(
            service,
            "plugin.config.set",
            {"plugin_id": "qqbot", "operation_id": "op-edit", "values": values},
        )

        assert response.error is None, response.error
        on_disk = path.read_text(encoding="utf-8")
        assert 'app_id = "app-new"' in on_disk
        assert _QQBOT_SECRET_REFERENCE in on_disk
        assert "resolved-secret-value" not in on_disk
        assert response.payload["values"]["client_secret"] == _QQBOT_SECRET_REFERENCE
        assert response.payload["env_status"] == {"client_secret": "set"}
        assert "resolved-secret-value" not in json.dumps(response.payload)
        # 热应用后的运行时依旧拿到展开后的密钥。
        assert app.config.plugins["qqbot"]["client_secret"] == "resolved-secret-value"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_a_typed_literal_replaces_the_reference(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIORI_TEST_QQBOT_SECRET", "resolved-secret-value")
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path, _qqbot_reference_config())
    try:
        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-literal",
                "values": {"app_id": "app-old", "client_secret": "typed-literal"},
            },
        )

        assert response.error is None, response.error
        on_disk = path.read_text(encoding="utf-8")
        assert 'client_secret = "typed-literal"' in on_disk
        assert _QQBOT_SECRET_REFERENCE not in on_disk
        assert response.payload["env_status"] == {}
        assert app.config.plugins["qqbot"]["client_secret"] == "typed-literal"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_a_reference_is_type_checked_by_its_resolved_value(tmp_path, monkeypatch):
    """整数字段里的 ``${VAR}``：按展开值校验，按原始引用落盘；非法时照常报错。"""
    monkeypatch.setenv("SHIORI_TEST_REPEAT_LIMIT", "5")
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(
        tmp_path,
        _config(
            extra='\n[plugins.tool_loop_guard]\nrepeat_limit = "${SHIORI_TEST_REPEAT_LIMIT}"\n'
        ),
    )
    try:
        loaded = await _request(
            service, "plugin.config.get", {"plugin_id": "tool_loop_guard"}
        )
        assert loaded.payload["values"] == {
            "repeat_limit": "${SHIORI_TEST_REPEAT_LIMIT}"
        }

        kept = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-keep",
                "values": loaded.payload["values"],
            },
        )
        assert kept.error is None, kept.error
        assert 'repeat_limit = "${SHIORI_TEST_REPEAT_LIMIT}"' in path.read_text(
            encoding="utf-8"
        )

        # 展开值不满足模型约束时，校验错误照常冒出来，且不回显展开后的值。
        monkeypatch.setenv("SHIORI_TEST_REPEAT_LIMIT", "1")
        before = path.read_text(encoding="utf-8")
        rejected = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-invalid-reference",
                "values": loaded.payload["values"],
            },
        )
        assert rejected.error is not None
        assert rejected.error.code == "plugin_config_invalid"
        assert "repeat_limit" in rejected.error.message
        assert all("input" not in item for item in rejected.error.details["errors"])
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()
