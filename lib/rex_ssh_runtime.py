"""Private local IPC for splitting a live rex-ssh pane without saving its argv."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import stat
import struct
import threading
from pathlib import Path


def socket_path(pid: int) -> Path:
    # macOS Unix socket paths have a small limit; its normal TMPDIR is too long.
    directory = Path("/tmp") / f"rex-ssh-runtime-{os.getuid()}"
    if directory.is_symlink():
        raise OSError("runtime directory is a symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError("runtime directory ownership mismatch")
    directory.chmod(0o700)
    return directory / f"{pid}.sock"


def same_user(connection: socket.socket) -> bool:
    if hasattr(connection, "getpeereid"):
        return connection.getpeereid()[0] == os.getuid()
    if hasattr(socket, "SO_PEERCRED"):
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return struct.unpack("3i", raw)[1] == os.getuid()
    if hasattr(socket, "LOCAL_PEERCRED"):
        # Darwin's xucred begins with a layout version followed by effective uid.
        raw = connection.getsockopt(0, socket.LOCAL_PEERCRED, 256)
        version, uid = struct.unpack("=II", raw[:8])
        return version == 0 and uid == os.getuid()
    return False


@contextlib.contextmanager
def serve(payload: dict):
    encoded = json.dumps(payload).encode() + b"\n"
    if len(encoded) > 65536:
        raise OSError("connection metadata is too large")
    path = socket_path(os.getpid())
    if path.exists():
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise OSError("unexpected runtime socket")
        path.unlink()
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(path))
    path.chmod(0o600)
    listener.listen(4)
    listener.settimeout(0.2)
    stopped = threading.Event()

    def listen():
        while not stopped.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(1)
                    if (
                        same_user(connection)
                        and connection.recv(128) == b"connection\n"
                    ):
                        connection.sendall(encoded)
                except OSError:
                    pass

    worker = threading.Thread(target=listen, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        listener.close()
        worker.join(timeout=2)
        path.unlink(missing_ok=True)


def read(pid: int) -> dict:
    if type(pid) is not int or pid <= 0:
        raise OSError("invalid process ID")
    path = socket_path(pid)
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise OSError("invalid runtime socket")
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(2)
        connection.connect(str(path))
        if not same_user(connection):
            raise OSError("runtime peer ownership mismatch")
        connection.sendall(b"connection\n")
        chunks = bytearray()
        while len(chunks) <= 65536:
            part = connection.recv(8192)
            if not part:
                break
            chunks.extend(part)
        if len(chunks) > 65536:
            raise OSError("runtime response is too large")
    value = json.loads(chunks)
    if not isinstance(value, dict):
        raise OSError("invalid runtime response")
    return value
