"""Operation markers and file leases belong to an exact live owner."""

import pytest
from shiori_sdk.files.json import load_json
from plugins.gpt_sovits_tts.backend.instance import InstanceBusy, InstanceState


def test_health_marker_wire_shape_for_idle_live_and_unknown(tmp_path):
    instance = InstanceState(tmp_path)
    assert instance.status() == {
        "busy": False,
        "recovery_required": False,
        "instance": None,
    }
    url = "http://127.0.0.1:9880"
    with instance.lease():
        operation = instance.begin(url)
        assert InstanceState(tmp_path).status() == {
            "busy": True,
            "recovery_required": False,
            "instance": {"operation": operation, "url": url, "state": "in_flight"},
        }
        instance.finish(operation, unknown=True)
    assert InstanceState(tmp_path).status() == {
        "busy": False,
        "recovery_required": True,
        "instance": {"operation": operation, "url": url, "state": "unknown"},
    }


def test_distinct_owners_cannot_enter_or_report_live_work_as_unknown(tmp_path):
    old, new = InstanceState(tmp_path), InstanceState(tmp_path)
    with old.lease():
        operation = old.begin("http://127.0.0.1:9880")
        assert new.status()["busy"] is True
        assert new.status()["recovery_required"] is False
        with pytest.raises(InstanceBusy):
            with new.lease():
                pytest.fail("a live instance was entered twice")
        old.finish(operation, unknown=True)
    assert new.status()["recovery_required"] is True
    with new.lease():
        new.recover()
    assert not old.marker.exists()


@pytest.mark.parametrize("unknown", [False, True])
def test_late_completion_never_clears_or_rewrites_replacement_marker(tmp_path, unknown):
    old, new = InstanceState(tmp_path), InstanceState(tmp_path)
    previous = old.begin("http://127.0.0.1:9880")
    current = new.begin("http://127.0.0.1:9880")
    old.finish(previous, unknown=unknown)
    assert load_json(new.marker)["operation"] == current
    assert load_json(new.marker)["state"] == "in_flight"
