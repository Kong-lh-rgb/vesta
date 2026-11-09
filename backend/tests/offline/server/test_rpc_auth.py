"""RPC credential file must be private and stable across Host restarts."""

from __future__ import annotations

import os

import pytest

from app.server.auth import load_or_create_rpc_token


def test_rpc_token_is_private_and_reused(tmp_path) -> None:
    token_file = tmp_path / "private" / "rpc-token"
    token = load_or_create_rpc_token(token_file)
    assert len(token) >= 32
    assert load_or_create_rpc_token(token_file) == token
    assert token_file.stat().st_mode & 0o077 == 0
    assert token_file.parent.stat().st_mode & 0o077 == 0


def test_rpc_token_rejects_insecure_file_and_symlink(tmp_path) -> None:
    token_file = tmp_path / "rpc-token"
    token_file.write_text("a" * 43, encoding="ascii")
    os.chmod(token_file, 0o644)
    with pytest.raises(PermissionError):
        load_or_create_rpc_token(token_file)

    token_file.unlink()
    token_file.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(OSError):
        load_or_create_rpc_token(token_file)


def test_rpc_token_rejects_insecure_directory(tmp_path) -> None:
    directory = tmp_path / "shared"
    directory.mkdir(mode=0o755)
    with pytest.raises(PermissionError):
        load_or_create_rpc_token(directory / "rpc-token")
