"""Nonblocking filesystem ownership across independent plugin generations."""

import errno
import os
from contextlib import contextmanager
from pathlib import Path


class LeaseBusy(RuntimeError):
    """The resource is still owned by another live process or generation."""


@contextmanager
def exclusive_file_lease(path: Path):
    """Hold one OS lock without deleting its inode while other owners can wait."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        if os.name == "nt":
            import msvcrt

            def lock(acquire: bool):
                handle.seek(0)
                msvcrt.locking(
                    handle.fileno(), msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1
                )

        else:
            import fcntl

            def lock(acquire: bool):
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB if acquire else fcntl.LOCK_UN,
                )

        try:
            lock(True)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise LeaseBusy("资源仍由其他活动插件实例占用") from error
            raise
        try:
            yield
        finally:
            lock(False)
