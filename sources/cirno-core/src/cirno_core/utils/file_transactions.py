"""Shared in-process ownership for file comparison, replacement and rollback."""

from __future__ import annotations

import os
from _thread import RLock
from collections.abc import Generator, Iterable
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Event, Lock
from weakref import WeakValueDictionary

_registry: WeakValueDictionary[str, RLock] = WeakValueDictionary()
_registry_lock = Lock()


@contextmanager
def file_write_transaction(
    paths: Iterable[Path], *, cancelled: Event | None = None
) -> Generator[None, None, None]:
    """Own all target paths through comparison and publication in stable order.

    Reentrant ownership lets atomic writers join a surrounding edit transaction.
    Idle paths leave the registry when their last owner or waiter releases them.
    Cancellation is honored before the first write; accepted batches settle as a unit.
    """
    keys = sorted({os.path.normcase(str(path.resolve())) for path in paths})
    with _registry_lock:
        locks: list[RLock] = []
        for key in keys:
            lock = _registry.get(key)
            if lock is None:
                lock = RLock()
                _registry[key] = lock
            locks.append(lock)
    with ExitStack() as stack:
        for lock in locks:
            if cancelled is None:
                lock.acquire()
            else:
                while not lock.acquire(timeout=0.05):
                    if cancelled.is_set():
                        raise InterruptedError("File operation cancelled while waiting to write")
            stack.callback(lock.release)
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError("File operation cancelled before writing")
        yield
