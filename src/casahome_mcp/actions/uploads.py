"""Bounded descriptor-based snapshots. Paths never appear in results or errors."""

import asyncio
import os
import stat
import threading
from collections.abc import Callable
from contextlib import suppress

from .store import ActionStore, action_error

LOCAL_FILE_CAP = 25 * 1024 * 1024


class SnapshotWorker:
    """Lease a lock and capacity until the filesystem worker actually finishes.

    Cancellation of the awaiting request can't interrupt a regular-file syscall.
    A dedicated daemon thread avoids asyncio's default-executor shutdown join.
    Server shutdown abandons workers without waiting. A stalled filesystem may
    keep one lease busy until it recovers, but can't create unbounded workers.
    All store/lock transitions and byte handoffs happen on the owning event loop.
    """

    def __init__(
        self,
        store: ActionStore,
        lock: asyncio.Lock,
        owners: set["SnapshotWorker"],
        file_path: str,
        limit: int,
        reader: Callable[[str, int], bytes],
    ) -> None:
        self._store = store
        self._lock = lock
        self._owners = owners
        self._loop = asyncio.get_running_loop()
        self._completion: asyncio.Future[None] = self._loop.create_future()
        self._abandoned = threading.Event()
        self._content: bytes | None = None
        self._failed = False
        self._released = False
        self.reservation = store.reserve_snapshot(limit)
        owners.add(self)
        self._completion.add_done_callback(self._finished)
        try:
            threading.Thread(
                target=self._run,
                args=(file_path, limit, reader),
                daemon=True,
                name="casa-upload-snapshot",
            ).start()
        except Exception:
            # Construction didn't transfer the caller's lock lease. Release only
            # the reservation here. The caller still releases its own lock.
            self._released = True
            self._abandoned.set()
            self._store.release_snapshot(self.reservation)
            self._owners.discard(self)
            self._completion.set_result(None)
            raise action_error("INVALID_FILE") from None

    def _run(self, file_path: str, limit: int, reader: Callable[[str, int], bytes]) -> None:
        content: bytes | None = None
        failed = False
        try:
            content = reader(file_path, limit)
        except Exception:
            # Never retain exception tracebacks, paths or source bytes in errors.
            failed = True
        if self._abandoned.is_set():
            content = None
        # A closed loop can't receive handoffs. Drop the daemon's result rather
        # than retaining bytes or mutating asyncio locks from this thread.
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._complete, content, failed)

    def _complete(self, content: bytes | None, failed: bool) -> None:
        if not self._abandoned.is_set():
            self._content = content
        self._failed = failed
        self._completion.set_result(None)

    def _finished(self, completed: asyncio.Future[None]) -> None:
        if self._abandoned.is_set():
            self._release()

    async def content(self) -> bytes:
        # Shield the completion future itself. Repeated parent cancellation must
        # never mark a still-allocating worker as completed.
        await asyncio.shield(self._completion)
        if self._abandoned.is_set() or self._failed or self._content is None:
            raise action_error("INVALID_FILE")
        return self._content

    def abandon(self) -> None:
        self._abandoned.set()
        self._content = None
        if self._completion.done():
            self._release()

    def _release(self) -> None:
        if self._released:
            return
        self._released = True
        self._content = None
        self._store.release_snapshot(self.reservation)
        self._owners.discard(self)
        self._lock.release()


def snapshot_file(path: str, limit: int) -> bytes:
    """Allow symlinks to regular files, inspect the actual opened descriptor.

    Nonblocking open prevents FIFO hangs. No directory walk, glob or path copy.
    Reading is bounded even if the opened regular file grows during the read.
    """
    fd: int | None = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= limit:
            raise action_error("INVALID_FILE")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            content = stream.read(limit + 1)
        if not 0 < len(content) <= limit:
            raise action_error("INVALID_FILE")
        return content
    except (OSError, ValueError):
        raise action_error("INVALID_FILE") from None
    finally:
        if fd is not None:
            os.close(fd)
