"""Private atomic writes and a process-lifetime account directory lock."""

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from .errors import SessionError


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".rewards-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    atomic_write(path, json.dumps(payload, allow_nan=False, indent=2))


@contextmanager
def account_lock(data_dir: Path) -> Iterator[None]:
    directory = data_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SessionError("Another worker or import holds the data directory lock") from None
        yield
    finally:
        os.close(fd)
