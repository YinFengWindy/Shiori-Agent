from .services import (
    RoleAggregate,
    RoleAggregateService,
    RoleBindingService,
    RoleChannelBinding,
    RoleMemoryService,
    RoleRepository,
    RoleRequest,
    RoleSessionService,
)
from .relationship_runtime import (
    LonelinessHeartbeatLoop,
    RelationshipSnapshotLoop,
    RelationshipSnapshotOptimizer,
    RoleRelationshipRuntimeService,
)
from .scene_followup_runtime import SceneFollowupRuntime
from .models import (
    RoleAssetCategory,
    RoleChannelBindingConfig,
    RoleProactiveCandidate,
    RoleProactiveConfig,
    RoleRecord,
)
from .profile_models import (
    ImportProvenance,
    RoleCharacterDefinition,
    RoleProfile,
)
from .role_prompt_compiler import (
    CompiledRolePrompt,
    RolePromptCompiler,
)
from .store import RoleStore
from .role_runtime import RoleExecutionContext, RoleRuntime, RoleRuntimeRegistry

__all__ = [
    "InboundRoleRouter",
    "LonelinessHeartbeatLoop",
    "RoleAggregate",
    "RoleAggregateService",
    "RoleAssetCategory",
    "RoleBindingService",
    "RoleChannelBinding",
    "RoleChannelBindingConfig",
    "RoleMemoryService",
    "RoleRelationshipRuntimeService",
    "RoleRecord",
    "RoleProactiveCandidate",
    "RoleProactiveConfig",
    "RoleRepository",
    "SceneFollowupRuntime",
    "RoleExecutionContext",
    "RoleRequest",
    "RelationshipSnapshotLoop",
    "RelationshipSnapshotOptimizer",
    "RoleSessionService",
    "RoleStore",
    "CompiledRolePrompt",
    "ImportProvenance",
    "RoleCharacterDefinition",
    "RoleProfile",
    "RolePromptCompiler",
    "RoleRuntime",
    "RoleRuntimeRegistry",
    "route_inbound_by_role",
]


def __getattr__(name: str):
    if name == "InboundRoleRouter":
        from .inbound import InboundRoleRouter

        return InboundRoleRouter
    if name == "route_inbound_by_role":
        from .inbound import route_inbound_by_role

        return route_inbound_by_role
    raise AttributeError(name)
