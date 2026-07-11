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
from .store import RoleRecord, RoleStore
from .store import RoleChannelBindingConfig, RoleProactiveConfig
from .config_migration import RoleConfigMigrationSummary, RoleConfigMigrator

__all__ = [
    "InboundRoleRouter",
    "LonelinessHeartbeatLoop",
    "RoleAggregate",
    "RoleAggregateService",
    "RoleBindingService",
    "RoleChannelBinding",
    "RoleChannelBindingConfig",
    "RoleConfigMigrationSummary",
    "RoleConfigMigrator",
    "RoleMemoryService",
    "RoleRelationshipRuntimeService",
    "RoleSelfSeedGenerator",
    "RoleRecord",
    "RoleProactiveConfig",
    "RoleRepository",
    "RoleRequest",
    "RelationshipSnapshotLoop",
    "RelationshipSnapshotOptimizer",
    "RoleSessionService",
    "RoleStore",
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
