from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.roles import RoleAggregateService, RoleLegacyMigrator, RoleStore
from memory2.store import MemoryStore2
from session.manager import SessionManager


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将可确认归属的 legacy session / memory 数据迁入角色聚合模型。"
    )
    _ = parser.add_argument(
        "--workspace",
        default=str(Path.cwd()),
        help="workspace 根目录",
    )
    _ = parser.add_argument(
        "--memory-db",
        default="",
        help="memory2.db 路径；留空时默认使用 workspace/memory/memory2.db",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    session_manager = SessionManager(workspace)
    role_store = RoleStore(workspace)
    role_service = RoleAggregateService.from_runtime(
        workspace=workspace,
        role_store=role_store,
        session_manager=session_manager,
    )
    memory_db = (
        Path(args.memory_db).resolve()
        if str(args.memory_db).strip()
        else workspace / "memory" / "memory2.db"
    )
    memory_store = MemoryStore2(memory_db) if memory_db.exists() else None
    try:
        summary = RoleLegacyMigrator(
            workspace=workspace,
            roles=role_service,
            session_manager=session_manager,
            memory_store=memory_store,
        ).migrate()
    finally:
        if memory_store is not None:
            memory_store.close()

    print(
        json.dumps(
            {
                "migrated_session_keys": summary.migrated_session_keys,
                "migrated_memory_item_ids": summary.migrated_memory_item_ids,
                "migrated_bindings": summary.migrated_bindings,
                "unresolved_session_keys": summary.unresolved_session_keys,
                "unresolved_memory_item_ids": summary.unresolved_memory_item_ids,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
