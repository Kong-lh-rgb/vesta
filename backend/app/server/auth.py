"""Local Host RPC credential shared with the Electron process.

The credential is never served over HTTP.  Both processes read the same
per-user file; a new installation creates it with owner-only permissions.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

RPC_SUBPROTOCOL_PREFIX = "vesta-rpc."


def default_rpc_token_file() -> Path:
    return Path.home() / ".vesta" / "rpc-token"


def load_or_create_rpc_token(path: Path | None = None) -> str:
    token_file = path or default_rpc_token_file()
    token_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = token_file.parent.stat()
    if directory.st_uid != os.getuid() or directory.st_mode & 0o077:
        raise PermissionError(
            f"RPC token directory must be owner-only: {token_file.parent}"
        )

    try:
        return _read_token(token_file)
    except FileNotFoundError:
        pass

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="ascii", dir=token_file.parent, delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(secrets.token_urlsafe(32))
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_name, token_file, follow_symlinks=False)
        except FileExistsError:
            pass  # Another Host created the credential concurrently.
    finally:
        if temporary_name is not None:
            os.unlink(temporary_name)
    return _read_token(token_file)


def _read_token(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise PermissionError(f"RPC token file must be owner-only: {path}")
        with os.fdopen(fd, "r", encoding="ascii") as stream:
            fd = -1
            token = stream.read(256).strip()
    finally:
        if fd >= 0:
            os.close(fd)
    if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) is None:
        raise ValueError("RPC token file is invalid")
    return token
