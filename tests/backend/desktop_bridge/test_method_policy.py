from __future__ import annotations

from desktop_bridge.method_policy import (
    METHOD_POLICIES,
    Concurrency,
    Handler,
    OwnerRouting,
    method_policy,
)


def test_unregistered_methods_keep_conservative_defaults():
    policy = method_policy("roles.update")
    assert policy.concurrency is Concurrency.MUTATION
    assert not policy.admission_exempt
    assert policy.owner_routing is OwnerRouting.CURRENT
    assert policy.handler is Handler.GENERATION


def test_only_cancellations_route_to_a_busy_owner():
    for method, policy in METHOD_POLICIES.items():
        if policy.owner_routing is not OwnerRouting.CURRENT:
            assert method.endswith(".cancel"), method
            assert policy.admission_exempt, method


def test_admission_exempt_generation_methods_are_read_only_or_cancellations():
    for method, policy in METHOD_POLICIES.items():
        if policy.handler is not Handler.GENERATION or not policy.admission_exempt:
            continue
        assert policy.concurrency is Concurrency.READ_ONLY or method.endswith(
            ".cancel"
        ), method


def test_dedicated_handlers_cover_exactly_the_settings_and_role_task_methods():
    assert method_policy("plugins.trust").handler is Handler.PLUGIN_MANAGEMENT
    assert method_policy("plugins.trust").concurrency is Concurrency.MUTATION
    settings = {
        name
        for name, policy in METHOD_POLICIES.items()
        if policy.handler is Handler.SETTINGS
    }
    role_tasks = {
        name
        for name, policy in METHOD_POLICIES.items()
        if policy.handler is Handler.ROLE_TASKS
    }
    plugin_config = {
        name
        for name, policy in METHOD_POLICIES.items()
        if policy.handler is Handler.PLUGIN_CONFIG
    }
    assert settings == {"runtime.status", "runtime.apply"}
    assert role_tasks == {"roles.tasks.list", "roles.tasks.cancel"}
    assert plugin_config == {"plugin.config.get", "plugin.config.set"}
    assert method_policy("runtime.apply").concurrency is Concurrency.SETTINGS_APPLY
    assert method_policy("plugin.config.set").concurrency is Concurrency.SETTINGS_APPLY


def test_channel_listing_is_a_read_only_reload_exempt_query():
    policy = method_policy("channels.list")
    assert policy.concurrency is Concurrency.READ_ONLY
    assert policy.admission_exempt
    assert policy.handler is Handler.PLUGIN_MANAGEMENT
