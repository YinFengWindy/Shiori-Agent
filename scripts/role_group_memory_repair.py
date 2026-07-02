from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.roles import RoleGroupMemoryRepairer
from memory2.store import MemoryStore2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="清理指定角色被历史群聊污染的根记忆与坏 scoped memory2 条目。"
    )
    _ = parser.add_argument(
        "--workspace",
        default=str(Path.cwd()),
        help="workspace 根目录",
    )
    _ = parser.add_argument(
        "--role-id",
        required=True,
        help="目标角色 ID",
    )
    _ = parser.add_argument(
        "--channel",
        default="qq",
        help="群聊渠道名，默认 qq",
    )
    _ = parser.add_argument(
        "--group-chat-id",
        required=True,
        help="目标群聊 ID",
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
    memory_db = (
        Path(args.memory_db).resolve()
        if str(args.memory_db).strip()
        else workspace / "memory" / "memory2.db"
    )
    memory_store = MemoryStore2(memory_db) if memory_db.exists() else None
    try:
        summary = RoleGroupMemoryRepairer(
            workspace=workspace,
            memory_store=memory_store,
        ).repair(
            role_id=args.role_id,
            channel=args.channel,
            group_chat_id=args.group_chat_id,
        )
    finally:
        if memory_store is not None:
            memory_store.close()

    print(
        json.dumps(
            {
                "role_id": summary.role_id,
                "channel": summary.channel,
                "group_chat_id": summary.group_chat_id,
                "removed_history_blocks": summary.removed_history_blocks,
                "removed_pending_blocks": summary.removed_pending_blocks,
                "removed_journal_blocks": summary.removed_journal_blocks,
                "cleared_recent_context": summary.cleared_recent_context,
                "deleted_memory_item_ids": summary.deleted_memory_item_ids,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
