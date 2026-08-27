"""角色关系快照与寂寞运行时的稳定 facade。"""

from .loneliness import (
    LonelinessRuntimeState,
    _LONELINESS_TICK_MINUTES,
    _NIGHT_SUPPRESSION_END_HOUR,
    _NIGHT_SUPPRESSION_START_HOUR,
    _PROACTIVE_CLOSENESS_THRESHOLD,
    _UNANSWERED_REPLY_WINDOW_HOURS,
    _advance_by_loneliness_ticks,
    _loneliness_tick_count,
    _now_iso,
    _parse_iso,
)
from .loops import LonelinessHeartbeatLoop, RelationshipSnapshotLoop
from .models import (
    RelationshipSnapshot,
    _BEHAVIOR_PROFILE_KEYS,
    _DEFAULT_BEHAVIOR_PROFILE,
    _DEFAULT_RELATION_STATE,
    _FIRST_PERSON_MARKERS,
    _MAX_RELATION_TAGS,
    _RECENT_MESSAGE_CHAR_LIMIT,
    _RECENT_MESSAGE_LIMIT,
    _RELATION_STATE_KEYS,
    _clamp,
    _is_first_person_self_view,
    _normalize_behavior_profile,
    _normalize_relation_state,
    _normalize_tags,
)
from .persistence import _RUNTIME_FILE, _SNAPSHOT_FILE
from .service import RoleRelationshipRuntimeService
from .snapshot import (
    RelationshipSnapshotOptimizer,
    _RELATIONSHIP_PROMPT,
    _RELATIONSHIP_SYSTEM,
)

__all__ = [
    "LonelinessHeartbeatLoop",
    "LonelinessRuntimeState",
    "RelationshipSnapshot",
    "RelationshipSnapshotLoop",
    "RelationshipSnapshotOptimizer",
    "RoleRelationshipRuntimeService",
]
