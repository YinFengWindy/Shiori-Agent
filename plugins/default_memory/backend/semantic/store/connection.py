"""Memory v2 SQLite 连接、迁移与生命周期管理。"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from .common import (
    OCCURRED_EPOCH_SQL_FUNCTION,
    SCHEMA,
    VEC_DIM,
    _emb_to_blob,
    _occurred_epoch,
)

try:
    import sqlite_vec

    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _SQLITE_VEC_AVAILABLE = False

logger = logging.getLogger(__name__)


class _StoreConnection:
    # 打开前视为已关闭：构造失败（含缺少 opener 或租约被拒）时 __del__ 不触碰未建立的连接。
    _closed = True

    def __init__(
        self,
        db_path: str | Path,
        vec_dim: int = VEC_DIM,
        *,
        open_database: Callable[[Path], sqlite3.Connection],
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 连接必须经宿主存储端口打开，以受数据库租约约束；不提供裸连接兜底。
        self._db = open_database(self.db_path)
        self._lock = threading.RLock()
        self._closed = False
        try:
            self._initialize(vec_dim)
        except BaseException:
            self.close()
            raise

    def _initialize(self, vec_dim: int) -> None:
        # Admin listing sorts by this; SQL text comparison cannot mix time zones.
        self._db.create_function(
            OCCURRED_EPOCH_SQL_FUNCTION, 2, _occurred_epoch, deterministic=True
        )
        self._db.executescript(SCHEMA)
        self._db.commit()

        cols = {r[1] for r in self._db.execute("PRAGMA table_info(memory_items)")}
        if "status" not in cols:
            self._db.execute(
                "ALTER TABLE memory_items ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
            self._db.commit()
        if "emotional_weight" not in cols:
            self._db.execute(
                "ALTER TABLE memory_items ADD COLUMN emotional_weight INTEGER NOT NULL DEFAULT 0"
            )
            self._db.commit()
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS ix_items_status ON memory_items (status)"
        )
        self._db.commit()

        # --- sqlite-vec 初始化 ---
        self._vec_dim = vec_dim
        self._vec_enabled = False
        self._vec_init_error: str | None = None
        self._vec_fallback_logged = False
        if _SQLITE_VEC_AVAILABLE:
            try:
                self._db.enable_load_extension(True)
                sqlite_vec.load(self._db)
                self._db.enable_load_extension(False)
                vec_schema = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(
    embedding float[{self._vec_dim}]
);
"""
                self._db.executescript(vec_schema)
                self._db.commit()
                self._vec_enabled = True
                self._migrate_existing_to_vec()
                logger.info("sqlite-vec 已启用（dim=%d）", self._vec_dim)
            except Exception as exc:
                self._vec_init_error = str(exc)
                logger.warning("sqlite-vec 初始化失败（%s），回退到全表扫描", exc)
        else:
            self._vec_init_error = "sqlite_vec 未安装"
            logger.debug("sqlite-vec 未安装，使用全表扫描")

    # ------------------------------------------------------------------
    # vec_items 内部辅助
    # ------------------------------------------------------------------

    def _migrate_existing_to_vec(self) -> None:
        """启动时将 memory_items 中尚未同步到 vec_items 的 embedding 迁移过去。"""
        existing = {
            r[0] for r in self._db.execute("SELECT rowid FROM vec_items").fetchall()
        }
        rows = self._db.execute(
            "SELECT rowid, embedding FROM memory_items WHERE embedding IS NOT NULL"
        ).fetchall()
        migrated = 0
        for rowid, emb_json in rows:
            if rowid in existing:
                continue
            try:
                emb = json.loads(emb_json)
                if len(emb) != self._vec_dim:
                    continue
                self._db.execute(
                    "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                    (rowid, _emb_to_blob(emb)),
                )
                migrated += 1
            except Exception as exc:
                logger.debug("vec migrate skip rowid %s: %s", rowid, exc)
        if migrated:
            self._db.commit()
            logger.info("sqlite-vec: 迁移了 %d 条历史 embedding", migrated)

    def _vec_insert(self, rowid: int, emb: list[float]) -> None:
        """向 vec_items 插入一条向量（幂等：先删再插）。维度不匹配时静默跳过。"""
        if not self._vec_enabled or len(emb) != self._vec_dim:
            return
        try:
            self._db.execute("DELETE FROM vec_items WHERE rowid=?", (rowid,))
            self._db.execute(
                "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                (rowid, _emb_to_blob(emb)),
            )
        except Exception as exc:
            logger.warning("vec_insert rowid=%s 失败: %s", rowid, exc)

    def _vec_delete(self, rowids: list[int]) -> None:
        """从 vec_items 批量删除。"""
        if not self._vec_enabled or not rowids:
            return
        try:
            self._db.executemany(
                "DELETE FROM vec_items WHERE rowid=?", [(r,) for r in rowids]
            )
        except Exception as exc:
            logger.warning("vec_delete 失败: %s", exc)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._db.close()
        finally:
            self._closed = True

    def __del__(self) -> None:
        self.close()
