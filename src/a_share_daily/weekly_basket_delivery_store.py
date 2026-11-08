"""Private durable files and stable process locks for basket delivery."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


def private_directory(path: Path) -> None:
    """Create the private state directory without following a final symlink."""
    if path.is_symlink():
        raise ValueError("private directory cannot be a symlink")
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        fsync_directory(directory.parent)
    path.chmod(0o700)


def fsync_directory(path: Path) -> None:
    """Commit directory entries on supported POSIX filesystems."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    """Atomically publish bytes and fsync both file and parent directory."""
    private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def exclusive_lock(path: Path) -> Generator[None]:
    """Hold a stable lock inode for the entire delivery transaction."""
    import fcntl

    private_directory(path.parent)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    """Hash exact local bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
