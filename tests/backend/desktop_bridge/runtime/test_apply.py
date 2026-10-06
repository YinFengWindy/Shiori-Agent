"""RuntimeSettingsApplication.build_config_toml：派生文本必须在事务锁内计算。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.config import load_config_text
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore
from desktop_bridge.runtime.apply import (
    DerivedWrite,
    RuntimeApplyError,
    RuntimeSettingsApplication,
)


def _config(*, optimizer: bool) -> str:
    # optimizer 取值不同会让 Config 真的不相等，从而走 prepare/publish 异步慢路径；
    # 若两份配置相等，apply 会同步提交、根本不让出控制权，测试就失去区分度。
    return (
        "[llm]\nregistrations = []\n"
        f"\n[agent.maintenance]\nmemory_optimizer_enabled = {str(optimizer).lower()}\n"
        '\n[proactive]\nenabled = false\nprofile = "quiet"\n'
    )


@pytest.mark.asyncio
async def test_build_config_toml_sees_the_text_committed_by_a_queued_apply(
    tmp_path: Path,
):
    """并发的 runtime.apply 先提交时，派生回调必须看到它提交后的文本。

    插件配置写入只改一张表、其余文本沿用当前已提交的配置。如果基准文本在事务锁
    外读取，一个刚刚落地的 runtime.apply 会被整份覆盖掉——用户的设置静默丢失。
    这里让两次 apply 排队，断言后一次的派生回调拿到的是前一次的提交结果。
    """
    original = _config(optimizer=False)
    updated = _config(optimizer=True)
    path = tmp_path / "config.toml"
    path.write_text(original, encoding="utf-8")
    app = AppRuntime(
        load_config_text(original),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    settings = RuntimeSettingsApplication(app, path, RoleStore(tmp_path))
    try:
        seen: list[str] = []
        # 用闸门把第一次 apply 钉在 prepare 上，制造确定性的交错，不依赖调度顺序
        gate = asyncio.Event()
        original_prepare = app.prepare

        async def _gated_prepare(config):
            await gate.wait()
            return await original_prepare(config)

        app.prepare = _gated_prepare

        async def _first() -> None:
            await settings.apply(
                {"config_toml": updated, "operation_id": "first"},
                prepare_service=lambda core: None,
                publish_service=lambda service: None,
            )

        async def _second() -> None:
            def _derive(current: str) -> str:
                seen.append(current)
                return current

            await settings.apply(
                {"operation_id": "second"},
                prepare_service=lambda core: None,
                publish_service=lambda service: None,
                derive=DerivedWrite(
                    build_config_toml=_derive,
                    fingerprint_payload={"marker": "second"},
                ),
            )

        first = asyncio.create_task(_first())
        # 第一次 apply 拿到锁后停在闸门上
        for _ in range(5):
            await asyncio.sleep(0)
        second = asyncio.create_task(_second())
        # 给第二次 apply 充分的机会：修复到位时它应当阻塞在锁上而不是立刻派生
        for _ in range(5):
            await asyncio.sleep(0)
        assert not seen, "派生回调在第一次 apply 提交之前就跑了，说明它不在事务锁内"
        gate.set()
        await asyncio.gather(first, second)

        assert seen, "派生回调没有被调用"
        assert seen[0] == updated, (
            "派生回调看到的是陈旧文本，说明合并发生在事务锁之外，"
            "并发的 runtime.apply 会被静默覆盖"
        )
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_a_derived_write_retry_never_reruns_the_deriver(tmp_path: Path):
    """派生式写入的原样重试必须直接命中幂等 memo，不能重新触发派生。

    幂等短路曾经发生在派生之后：``apply`` 先跑 ``build_config_toml``，直到
    ``_apply`` 内部才查 memo。同一请求原样重试因此仍会重新派生一次——如果
    派生逻辑（如插件配置的整份文档回读守卫）在两次请求之间失效，一次本该
    命中 memo、原样返回第一次结果的重试就会失败。这里让派生回调在第二次
    被调用时直接断言失败，只有 memo 检查真的抢在派生之前发生，这个回调才
    不会被再次调用。
    """
    config = _config(optimizer=False)
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")
    app = AppRuntime(
        load_config_text(config),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    settings = RuntimeSettingsApplication(app, path, RoleStore(tmp_path))
    try:
        call_count = 0

        def _derive(current: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise AssertionError(
                    "build_config_toml re-ran on a memoized retry; the memo check "
                    "must short-circuit before deriving"
                )
            return current

        derive = DerivedWrite(
            build_config_toml=_derive,
            fingerprint_payload={"op": "x"},
        )
        payload = {"operation_id": "op-retry"}

        first = await settings.apply(
            payload,
            prepare_service=lambda core: None,
            publish_service=lambda service: None,
            derive=derive,
        )
        retry = await settings.apply(
            dict(payload),
            prepare_service=lambda core: None,
            publish_service=lambda service: None,
            derive=derive,
        )

        assert retry == first
        assert call_count == 1
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_a_fingerprint_payload_that_cannot_be_json_encoded_is_rejected_cleanly(
    tmp_path: Path,
):
    """指纹载荷不可 JSON 序列化时必须转成 RuntimeApplyError，而不是让 TypeError 逃出 apply。

    ``fingerprint_payload`` 只标注了一个具体类型（``dict[str, Any]``），本身不
    保证内容可序列化；若不加守卫，``json.dumps`` 抛出的 ``TypeError`` 会直接
    逃出 ``apply``，在桥接层被兜成一个跟真实原因无关的 internal_error。
    """
    config = _config(optimizer=False)
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")
    app = AppRuntime(
        load_config_text(config),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    settings = RuntimeSettingsApplication(app, path, RoleStore(tmp_path))
    try:
        derive = DerivedWrite(
            build_config_toml=lambda current: current,
            fingerprint_payload={"bad": object()},
        )

        with pytest.raises(RuntimeApplyError) as excinfo:
            await settings.apply(
                {"operation_id": "op-bad-fingerprint"},
                prepare_service=lambda core: None,
                publish_service=lambda service: None,
                derive=derive,
            )

        assert excinfo.value.code == "runtime_invalid_request"
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_form_write_derives_after_queued_plugin_change_commits(
    tmp_path, monkeypatch
):
    import tomllib
    from desktop_bridge.runtime.settings_form import settings_form_write

    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda workspace: [])
    original = _config(optimizer=False) + '\n[plugins.qqbot]\napp_id = "old"\n'
    path = tmp_path / "config.toml"
    path.write_text(original, encoding="utf-8")
    app = AppRuntime(
        load_config_text(original),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    settings = RuntimeSettingsApplication(app, path, RoleStore(tmp_path))
    entered, release = asyncio.Event(), asyncio.Event()
    prepare = app.prepare

    async def gated(config):
        entered.set()
        await release.wait()
        return await prepare(config)

    monkeypatch.setattr(app, "prepare", gated)
    first = second = None
    try:
        latest = _config(optimizer=False) + '\n[plugins.qqbot]\napp_id = "new"\n'
        first = asyncio.create_task(
            settings.apply(
                {"config_toml": latest, "operation_id": "plugin"},
                prepare_service=lambda core: None,
                publish_service=lambda service: None,
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        # The ordinary form owns agent/llm/etc.; proactive is an opaque current
        # table and must be preserved by the transaction rather than drafted.
        payload = {
            "config_toml": _config(optimizer=True).split("\n[proactive]", 1)[0],
            "preserve_plugins": True,
            "operation_id": "form",
        }
        second = asyncio.create_task(
            settings.apply(
                payload,
                prepare_service=lambda core: None,
                publish_service=lambda service: None,
                derive=settings_form_write(payload),
            )
        )
        await asyncio.sleep(0)
        assert not second.done()
        release.set()
        await asyncio.gather(first, second)
        assert tomllib.loads(path.read_text(encoding="utf-8"))["plugins"] == {
            "qqbot": {"app_id": "new"}
        }
    finally:
        release.set()
        if first is not None:
            await first
        if second is not None:
            await second
        await app.shutdown()
