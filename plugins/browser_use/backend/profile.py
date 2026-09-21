"""Exclusive lease of a persistent profile, including across host processes."""

from pathlib import Path
import sys
from typing import BinaryIO


class ProfileLease:
    """Prevents two hosts or plugin generations from launching the same profile."""

    def __init__(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._file: BinaryIO | None = (path / "shiori.lock").open("a+b")
        self._file.seek(0, 2)
        if self._file.tell() == 0:
            self._file.write(b"0")
            self._file.flush()
        self._file.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._file.close()
            self._file = None
            raise RuntimeError("Browser Use 角色配置目录已被另一会话占用") from exc

    def close(self) -> None:
        """Releases the OS lease while keeping cookies and site storage on disk."""
        if self._file is not None:
            self._file.close()
            self._file = None
