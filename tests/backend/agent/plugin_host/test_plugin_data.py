"""插件私有数据落在 workspace，而不是插件目录（issue #209）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent.plugin_host.plugin_data as plugin_data
from agent.plugin_host.plugin_data import (
    open_plugin_kv,
    plugin_data_dir,
)


@pytest.mark.parametrize("existing", ["old-only", "new-only", "both"])
def test_workspace_kv_survives_upgrade_restart_and_package_replacement(
    tmp_path, existing
):
    workspace = tmp_path / "workspace"
    package = tmp_path / "install/demo"
    old = workspace / "plugins/demo/kv.json"
    target = plugin_data_dir(workspace, "demo") / "kv.json"
    for file, value in ((old, "old"), (target, "new")):
        if existing == "both" or existing.startswith(value):
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps({"value": value}), encoding="utf-8")
    package.mkdir(parents=True)
    stale = package / ".kv.json"
    stale.write_text('{"value":"package"}', encoding="utf-8")
    store = open_plugin_kv(workspace=workspace, plugin_id="demo", plugin_dir=package)
    assert store.get("value") == ("old" if existing == "old-only" else "new")
    assert old.exists() is (existing == "both")
    assert stale.is_file()
    store.set("value", "updated")
    stale.write_text('{"value":"replacement"}', encoding="utf-8")
    assert (
        open_plugin_kv(workspace=workspace, plugin_id="demo", plugin_dir=package).get(
            "value"
        )
        == "updated"
    )


def test_workspace_kv_atomic_replace_failure_preserves_original_and_retries(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    old = workspace / "plugins/demo/kv.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"value":"old"}', encoding="utf-8")
    target = plugin_data_dir(workspace, "demo") / "kv.json"
    replace = Path.replace

    def fail(source, destination):
        if destination == target:
            raise OSError("disk full")
        return replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail)
        with pytest.raises(OSError, match="disk full"):
            open_plugin_kv(
                workspace=workspace, plugin_id="demo", plugin_dir=tmp_path / "install"
            )
    assert old.read_text(encoding="utf-8") == '{"value":"old"}'
    assert not target.exists()
    assert (
        open_plugin_kv(
            workspace=workspace, plugin_id="demo", plugin_dir=tmp_path / "install"
        ).get("value")
        == "old"
    )


def test_kv_lands_under_the_workspace_not_the_plugin_directory(tmp_path: Path):
    """插件目录在打包形态下属于只读的应用安装目录，写进去的数据升级即丢。"""
    workspace = tmp_path / "workspace"
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)

    store = open_plugin_kv(workspace=workspace, plugin_id="demo", plugin_dir=plugin_dir)
    store.set("counter", 3)

    assert (plugin_data_dir(workspace, "demo") / "kv.json").is_file()
    assert not (plugin_dir / ".kv.json").exists()


def test_missing_workspace_fails_loudly_instead_of_falling_back(tmp_path: Path):
    """宿主没给 workspace 时必须报错，不能悄悄退回写插件目录——那正是 #209 的病根。"""
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()

    with pytest.raises(RuntimeError, match="workspace"):
        _ = open_plugin_kv(workspace=None, plugin_id="demo", plugin_dir=plugin_dir)

    assert not (plugin_dir / ".kv.json").exists()


def test_legacy_kv_in_the_plugin_directory_is_migrated_once(tmp_path: Path):
    """已有用户的数据存在插件目录里；不迁移会让 novelai 的冷却与场景去重归零。"""
    workspace = tmp_path / "workspace"
    plugin_dir = tmp_path / "plugins" / "novelai"
    plugin_dir.mkdir(parents=True)
    legacy = plugin_dir / ".kv.json"
    _ = legacy.write_text(
        json.dumps({"auto_cg_sessions": {"role:mira": {"turn": 7}}}), encoding="utf-8"
    )

    store = open_plugin_kv(
        workspace=workspace, plugin_id="novelai", plugin_dir=plugin_dir
    )

    assert store.get("auto_cg_sessions") == {"role:mira": {"turn": 7}}
    assert not legacy.exists(), "迁移后旧文件应被移除，避免两份数据并存"


def test_migration_never_overwrites_existing_workspace_data(tmp_path: Path):
    """workspace 已有数据时，插件目录里的陈旧残留不得覆盖它。"""
    workspace = tmp_path / "workspace"
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    target = plugin_data_dir(workspace, "demo") / "kv.json"
    target.parent.mkdir(parents=True)
    _ = target.write_text(json.dumps({"value": "current"}), encoding="utf-8")
    _ = (plugin_dir / ".kv.json").write_text(
        json.dumps({"value": "stale"}), encoding="utf-8"
    )

    store = open_plugin_kv(workspace=workspace, plugin_id="demo", plugin_dir=plugin_dir)

    assert store.get("value") == "current"


def test_kv_migrates_from_the_pre_move_plugin_root(tmp_path: Path):
    """插件包上移前的旧位置也必须作为迁移来源。

    `.kv.json` 被 gitignore 覆盖，目录重命名经 git 落到本地时不会跟着搬——旧数据
    会留在 apps/backend/plugins/<id>/。只看新位置就会静默丢掉 novelai 的自动 CG
    冷却与场景去重状态，导致同一场景被重复生图（真金白银的 NovelAI 调用）。
    """
    workspace = tmp_path / "workspace"
    plugin_dir = tmp_path / "plugins" / "novelai"
    plugin_dir.mkdir(parents=True)
    legacy_root = tmp_path / "apps" / "backend" / "plugins"
    legacy_file = legacy_root / "novelai" / ".kv.json"
    legacy_file.parent.mkdir(parents=True)
    _ = legacy_file.write_text(
        json.dumps(
            {
                "auto_cg_sessions": {
                    "role:mira": {"turn": 1076, "last_success_turn": 1061}
                }
            }
        ),
        encoding="utf-8",
    )

    store = open_plugin_kv(
        workspace=workspace,
        plugin_id="novelai",
        plugin_dir=plugin_dir,
        legacy_plugin_root=legacy_root,
    )

    assert store.get("auto_cg_sessions") == {
        "role:mira": {"turn": 1076, "last_success_turn": 1061}
    }
    assert not legacy_file.exists()


def test_migration_only_deletes_the_candidate_it_actually_migrated(tmp_path: Path):
    """迁移只应删除真正被当作来源的那份候选，不得顺手销毁用户的另一份数据。

    `target.exists()` 早退意味着一旦迁移成功，其余候选此后永远不会再被读取；
    删除它们没有任何收益，只会把用户的另一份 kv 数据静默销毁——这正是复审
    #2 指出的问题：之前的实现无条件删光了 candidates 里所有存在的文件。
    """
    workspace = tmp_path / "workspace"
    plugin_dir = tmp_path / "plugins" / "novelai"
    plugin_dir.mkdir(parents=True)
    used_source = plugin_dir / ".kv.json"
    _ = used_source.write_text(json.dumps({"value": "used"}), encoding="utf-8")
    legacy_root = tmp_path / "apps" / "backend" / "plugins"
    untouched_candidate = legacy_root / "novelai" / ".kv.json"
    untouched_candidate.parent.mkdir(parents=True)
    _ = untouched_candidate.write_text(
        json.dumps({"value": "must survive"}), encoding="utf-8"
    )

    store = open_plugin_kv(
        workspace=workspace,
        plugin_id="novelai",
        plugin_dir=plugin_dir,
        legacy_plugin_root=legacy_root,
    )

    assert store.get("value") == "used"
    assert not used_source.exists(), "真正被迁移的来源应该被删除"
    assert untouched_candidate.exists(), "未被用作来源的候选不得被顺手删除"
    assert json.loads(untouched_candidate.read_text(encoding="utf-8")) == {
        "value": "must survive"
    }


def test_migration_failure_leaves_source_intact_and_no_partial_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """写入中途失败必须原样保留旧数据，不能留下半截 target 也不能提前删 source。

    复审 #3：旧实现是 `target.write_text(...)` 非原子写，写到一半失败会留下
    半截 kv.json；下次启动 `target.exists()` 为真直接早退，旧数据从此再也读
    不到——变成永久损坏。这里用 monkeypatch 模拟写入失败，断言 source 完整
    保留、target 不存在（而不是存在但损坏），且异常照常冒泡（失败即停，不吞错）。
    """
    workspace = tmp_path / "workspace"
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    source = plugin_dir / ".kv.json"
    _ = source.write_text(json.dumps({"value": "still here"}), encoding="utf-8")

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk failure mid-write")

    monkeypatch.setattr(plugin_data, "atomic_save_json", _boom)

    with pytest.raises(OSError, match="simulated disk failure"):
        _ = open_plugin_kv(workspace=workspace, plugin_id="demo", plugin_dir=plugin_dir)

    assert source.exists(), "写入失败时旧数据必须原样保留"
    assert json.loads(source.read_text(encoding="utf-8")) == {"value": "still here"}
    assert not (
        plugin_data_dir(workspace, "demo") / "kv.json"
    ).exists(), "写入失败不能留下半截 target"


@pytest.mark.parametrize(
    "plugin_id",
    ["", ".", "..", "../outside", "folder/child", "folder\\child", "D:outside"],
)
def test_plugin_data_paths_reject_nonportable_directory_traversal(tmp_path, plugin_id):
    with pytest.raises(ValueError, match="ID"):
        plugin_data_dir(tmp_path, plugin_id)
