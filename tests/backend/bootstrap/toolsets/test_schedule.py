from json import JSONDecodeError
from unittest.mock import Mock

import pytest

from bootstrap.toolsets.schedule import build_scheduler
from core.roles.store import RoleStore
from tests.support.scheduler import make_job


@pytest.mark.parametrize("shared_store", [False, True])
def test_built_scheduler_recovers_only_existing_roles(tmp_path, shared_store):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    scheduler = build_scheduler(
        tmp_path, Mock(), role_store=roles if shared_store else None
    )
    live = make_job(role_id="mira")
    orphan = make_job(role_id="deleted")
    scheduler.store.save({job.id: job for job in (orphan, live)})

    scheduler.load_and_recover()

    assert [job.id for job in scheduler.list_jobs()] == [live.id]
    assert [job.id for job in scheduler.store.load()] == [live.id]


def test_built_scheduler_does_not_treat_unreadable_roles_as_missing(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    scheduler = build_scheduler(tmp_path, Mock(), role_store=roles)
    job = make_job(role_id="mira")
    scheduler.store.save({job.id: job})
    roles.manifest_path.write_text("invalid JSON", encoding="utf-8")

    with pytest.raises(JSONDecodeError):
        scheduler.load_and_recover()

    assert scheduler.list_jobs() == []
    assert [stored.id for stored in scheduler.store.load()] == [job.id]
