from world_simulation.performance import (
    PRESENTATION_PROTOCOL_VERSION,
    PerformancePlan,
    PresentationCue,
    compile_performance_plan,
    cue_id_for_plan,
    plan_id_for_event,
)
from world_simulation.timeline import TimelineEvent


def event(**changes):
    return TimelineEvent(
        id="event-1",
        world_id="world-1",
        event_type="scene.action.committed",
        effective_at="2026-04-01T09:00:00+00:00",
        sequence=3,
        changes=changes,
    )


def test_plan_ids_are_stable_and_protocol_versioned():
    plan_id = plan_id_for_event("world-1", "event-1")
    assert plan_id == plan_id_for_event("world-1", "event-1")
    assert plan_id != plan_id_for_event("world-1", "event-2")
    assert cue_id_for_plan(plan_id, 0, "dialogue") != cue_id_for_plan(
        plan_id, 1, "dialogue"
    )


def test_compiler_emits_deterministic_cues_and_parallel_stage_group():
    plan = compile_performance_plan(
        event(
            presentation={
                "content": "推开灯塔的门。",
                "speaker_name": "岚",
                "background": {"asset": "harbor"},
                "sprites": [{"actor_id": "oc-1", "mood": "alert"}],
                "camera": [{"kind": "pan", "duration_ms": 240}],
                "audio": [{"kind": "ambience", "asset": "rain"}],
            }
        )
    )

    assert plan.schema_version == PRESENTATION_PROTOCOL_VERSION
    assert [cue.kind for cue in plan.cues] == [
        "background",
        "sprites",
        "camera",
        "dialogue",
        "audio",
    ]
    assert plan.cues[0].parallel_group == plan.cues[1].parallel_group
    assert plan.cues[3].blocking is True
    assert plan.cues[3].checkpoint is True
    assert plan.to_bridge_dict()["cues"][3]["completionState"] == "completed"


def test_compiler_falls_back_to_text_for_events_without_presentation():
    plan = compile_performance_plan(event())

    assert len(plan.cues) == 1
    assert plan.cues[0].kind == "text"
    assert plan.cues[0].payload == {"text": "scene.action.committed"}


def test_plan_rejects_cues_from_another_plan():
    cue = PresentationCue(
        schema_version=1,
        cue_id="cue-1",
        plan_id="other-plan",
        sequence=0,
        kind="text",
        payload={"text": "hello"},
    )
    plan = PerformancePlan(
        id="plan-1", world_id="world-1", event_id="event-1", cues=(cue,)
    )

    try:
        plan.validate()
    except ValueError as exc:
        assert "plan_id" in str(exc)
    else:
        raise AssertionError("plan validation should reject a foreign cue")
