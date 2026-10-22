"""Static planning: order, replacement, conflicts, duplicate providers and cycles."""

from typing import Any

import pytest

from shiori_sdk.kernel import KernelError, KernelState, PluginSpec
from shiori_sdk.kernel.graph import plan


async def _setup(_ctx: object) -> None:
    return None


def spec(plugin_id: str, **fields: Any) -> PluginSpec:
    return PluginSpec(plugin_id, _setup, **fields)


def test_order_is_dependency_depth_then_plugin_id_not_input_order() -> None:
    specs = [
        spec("zeta"),
        spec("consumer", requires=("base",), optional=("extra",)),
        spec("beta", provides=("base",)),
        spec("alpha", provides=("extra",)),
        spec("top", requires=("consumed",)),
        spec("mid", requires=("base",), provides=("consumed",)),
    ]

    planned = plan(specs, core=())

    assert planned.order == ("alpha", "beta", "zeta", "consumer", "mid", "top")
    assert plan(list(reversed(specs)), core=()).order == planned.order


def test_replaced_plugin_is_excluded_and_its_key_goes_to_the_replacement() -> None:
    planned = plan(
        [
            spec("default_memory", provides=("memory_engine",)),
            spec(
                "vector_memory",
                provides=("memory_engine",),
                replaces=("default_memory",),
            ),
            spec("reader", requires=("memory_engine",)),
        ],
        core=(),
    )

    assert planned.excluded["default_memory"].state == KernelState.REPLACED
    assert "vector_memory" in planned.excluded["default_memory"].reason
    assert planned.owners["memory_engine"] == "vector_memory"
    assert planned.order == ("vector_memory", "reader")


def test_conflicting_plugins_are_both_blocked_naming_each_other() -> None:
    planned = plan(
        [spec("one", conflicts=("two",)), spec("two"), spec("free")], core=()
    )

    assert planned.order == ("free",)
    assert "two" in planned.excluded["one"].reason
    assert "one" in planned.excluded["two"].reason
    assert {d.code for d in planned.excluded.values()} == {"conflict"}


def test_undeclared_duplicate_provider_blocks_both_and_names_both() -> None:
    planned = plan(
        [
            spec("first", provides=("tts",)),
            spec("second", provides=("tts",)),
            spec("speaker", requires=("tts",)),
        ],
        core=(),
    )

    for owner in ("first", "second"):
        problem = planned.excluded[owner]
        assert problem.code == "duplicate_provider"
        assert "first" in problem.reason and "second" in problem.reason
    assert "tts" not in planned.owners
    assert planned.order == ("speaker",)


def test_plugin_providing_a_core_key_refuses_the_whole_plan() -> None:
    with pytest.raises(KernelError) as refused:
        plan([spec("rogue", provides=("tools",))], core=("tools",))

    assert refused.value.diagnostic.code == "duplicate_provider"
    assert refused.value.plugin_ids == ("rogue",)


def test_requires_cycle_is_refused_before_setup_listing_its_members() -> None:
    planned = plan(
        [
            spec("a", requires=("b_key",), provides=("a_key",)),
            spec("b", requires=("c_key",), provides=("b_key",)),
            spec("c", requires=("a_key",), provides=("c_key",)),
            spec("outside", requires=("a_key",)),
            # Mutual optional injection is not a cycle: both still load.
            spec("x", optional=("y_key",), provides=("x_key",)),
            spec("y", optional=("x_key",), provides=("y_key",)),
        ],
        core=(),
    )

    for member in ("a", "b", "c"):
        problem = planned.excluded[member]
        assert problem.code == "dependency_cycle"
        assert problem.reason == "插件依赖成环: a -> b -> c -> a"
    assert set(planned.excluded) == {"a", "b", "c"}
    assert set(planned.order) == {"outside", "x", "y"}
