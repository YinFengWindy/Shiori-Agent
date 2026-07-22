from .services import (
    RoleAggregate,
    RoleAggregateService,
    RoleBindingService,
    RoleChannelBinding,
    RoleMemoryService,
    RoleSelfSeedGenerator,
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
from .store import RoleAssetCategory, RolePetPackage, RoleRecord, RoleStore
from .store import RoleChannelBindingConfig, RoleProactiveConfig
from .pet_packages import RolePetPackageService
from .config_migration import RoleConfigMigrationSummary, RoleConfigMigrator
from .world import RoleExecutionContext, RoleWorld, RoleWorldRegistry

__all__ = [
    "InboundRoleRouter",
    "LonelinessHeartbeatLoop",
    "RoleAggregate",
    "RoleAggregateService",
    "RoleAssetCategory",
    "RoleBindingService",
    "RoleChannelBinding",
    "RoleChannelBindingConfig",
    "RoleConfigMigrationSummary",
    "RoleConfigMigrator",
    "RoleMemoryService",
    "RolePetPackage",
    "RolePetPackageService",
    "RoleRelationshipRuntimeService",
    "RoleSelfSeedGenerator",
    "RoleRecord",
    "RoleProactiveConfig",
    "RoleRepository",
    "SceneFollowupRuntime",
    "RoleExecutionContext",
    "RoleRequest",
    "RelationshipSnapshotLoop",
    "RelationshipSnapshotOptimizer",
    "RoleSessionService",
    "RoleStore",
    "RoleWorld",
    "RoleWorldRegistry",
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
