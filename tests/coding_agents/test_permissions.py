import pytest

from coding_agents.models import PermissionLevel, Provider, TaskMode
from coding_agents.permissions import (
    PermissionApproval,
    PermissionPolicy,
    PermissionPolicyError,
)


@pytest.mark.parametrize(
    ("level", "can_write", "can_test", "codex_sandbox"),
    [
        (PermissionLevel.READ_ONLY, False, False, "read-only"),
        (PermissionLevel.WORKSPACE_WRITE, True, True, "workspace-write"),
    ],
)
def test_base_permission_matrix(level, can_write, can_test, codex_sandbox):
    effective = PermissionPolicy().resolve(
        run_id="run-1",
        provider=Provider.CODEX,
        mode=TaskMode.EXECUTE,
        requested_level=level,
    )

    assert effective.repository_read is True
    assert effective.worktree_write is can_write
    assert effective.run_tests is can_test
    assert effective.network is False
    assert effective.secret_names == frozenset()
    assert effective.merge is False
    assert effective.push is False
    assert effective.codex_sandbox == codex_sandbox


def test_plan_mode_forces_read_only_without_requesting_elevation():
    effective = PermissionPolicy().resolve(
        run_id="run-1",
        provider=Provider.CODEX,
        mode=TaskMode.PLAN,
        requested_level=PermissionLevel.FULL_ACCESS,
    )

    assert effective.level is PermissionLevel.READ_ONLY
    assert effective.worktree_write is False


def test_full_access_requires_matching_explicit_approval():
    policy = PermissionPolicy()

    with pytest.raises(PermissionPolicyError) as missing:
        policy.resolve(
            run_id="run-1",
            provider=Provider.CODEX,
            mode=TaskMode.EXECUTE,
            requested_level=PermissionLevel.FULL_ACCESS,
            outer_sandbox_available=True,
        )
    with pytest.raises(PermissionPolicyError) as mismatched:
        policy.resolve(
            run_id="run-1",
            provider=Provider.CODEX,
            mode=TaskMode.EXECUTE,
            requested_level=PermissionLevel.FULL_ACCESS,
            approval=PermissionApproval(
                approval_id="approval-1",
                run_id="other-run",
                approved_level=PermissionLevel.FULL_ACCESS,
            ),
            outer_sandbox_available=True,
        )

    assert missing.value.code == "permission_denied"
    assert mismatched.value.code == "permission_denied"


def test_full_access_requires_outer_sandbox_boundary():
    approval = PermissionApproval(
        approval_id="approval-1",
        run_id="run-1",
        approved_level=PermissionLevel.FULL_ACCESS,
    )

    with pytest.raises(PermissionPolicyError) as error:
        PermissionPolicy().resolve(
            run_id="run-1",
            provider=Provider.CODEX,
            mode=TaskMode.EXECUTE,
            requested_level=PermissionLevel.FULL_ACCESS,
            approval=approval,
        )

    assert error.value.code == "sandbox_unavailable"


def test_full_access_only_exposes_approved_network_and_secrets():
    approval = PermissionApproval(
        approval_id="approval-1",
        run_id="run-1",
        approved_level=PermissionLevel.FULL_ACCESS,
        allow_network=True,
        secret_names=frozenset({"PROVIDER_TOKEN", " EXTRA_TOKEN "}),
    )

    effective = PermissionPolicy().resolve(
        run_id="run-1",
        provider=Provider.CODEX,
        mode=TaskMode.EXECUTE,
        requested_level=PermissionLevel.FULL_ACCESS,
        approval=approval,
        outer_sandbox_available=True,
    )

    assert effective.codex_sandbox == "danger-full-access"
    assert effective.outer_sandbox_profile == "shiori-full-access"
    assert effective.network is True
    assert effective.secret_names == frozenset({"PROVIDER_TOKEN", "EXTRA_TOKEN"})
    assert effective.merge is False
    assert effective.push is False


def test_full_access_rejects_invalid_secret_environment_name():
    with pytest.raises(PermissionPolicyError) as error:
        PermissionPolicy().resolve(
            run_id="run-1",
            provider=Provider.CODEX,
            mode=TaskMode.EXECUTE,
            requested_level=PermissionLevel.FULL_ACCESS,
            approval=PermissionApproval(
                approval_id="approval-1",
                run_id="run-1",
                approved_level=PermissionLevel.FULL_ACCESS,
                secret_names=frozenset({"TOKEN=value"}),
            ),
            outer_sandbox_available=True,
        )

    assert error.value.code == "permission_denied"


def test_unknown_permission_level_fails_without_fallback():
    with pytest.raises(PermissionPolicyError) as error:
        PermissionPolicy().resolve(
            run_id="run-1",
            provider=Provider.CODEX,
            mode=TaskMode.EXECUTE,
            requested_level="unknown",
        )

    assert error.value.code == "permission_denied"


@pytest.mark.parametrize(
    ("level", "expected_profile"),
    [
        (PermissionLevel.READ_ONLY, "shiori-read-only"),
        (PermissionLevel.WORKSPACE_WRITE, "shiori-workspace-write"),
    ],
)
def test_claude_permissions_use_named_outer_sandbox(level, expected_profile):
    effective = PermissionPolicy().resolve(
        run_id="run-1",
        provider=Provider.CLAUDE,
        mode=TaskMode.EXECUTE,
        requested_level=level,
        outer_sandbox_available=True,
    )

    assert effective.outer_sandbox_profile == expected_profile


def test_claude_fails_closed_when_outer_sandbox_is_unavailable():
    with pytest.raises(PermissionPolicyError) as error:
        PermissionPolicy().resolve(
            run_id="run-1",
            provider=Provider.CLAUDE,
            mode=TaskMode.EXECUTE,
            requested_level=PermissionLevel.WORKSPACE_WRITE,
        )

    assert error.value.code == "sandbox_unavailable"


def test_claude_full_access_uses_named_outer_sandbox():
    effective = PermissionPolicy().resolve(
        run_id="run-1",
        provider=Provider.CLAUDE,
        mode=TaskMode.EXECUTE,
        requested_level=PermissionLevel.FULL_ACCESS,
        approval=PermissionApproval(
            approval_id="approval-1",
            run_id="run-1",
            approved_level=PermissionLevel.FULL_ACCESS,
        ),
        outer_sandbox_available=True,
    )

    assert effective.outer_sandbox_profile == "shiori-full-access"
