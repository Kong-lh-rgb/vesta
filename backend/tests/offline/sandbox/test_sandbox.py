from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from app.sandbox import (
    SandboxBackend,
    SandboxConfig,
    SandboxFilesystemMode,
    SandboxLaunchSpec,
    SandboxNetworkMode,
    SandboxPolicy,
    SandboxPolicyError,
    SandboxSupervisor,
    SandboxUnavailableError,
    UnsupportedSandboxBackend,
)
from app.tools.builtin.shell import ShellCommandTool


class RecordingBackend(SandboxBackend):
    def __init__(self) -> None:
        self.policy: SandboxPolicy | None = None

    def prepare(
        self,
        *,
        command: Path,
        args: tuple[str, ...],
        env: dict[str, str],
        policy: SandboxPolicy,
    ) -> SandboxLaunchSpec:
        self.policy = policy
        return SandboxLaunchSpec(
            command=str(command),
            args=args,
            cwd=str(policy.working_directory),
            env=env,
            backend="recording",
            sandboxed=True,
        )


def test_supervisor_compiles_workspace_policy_and_protects_metadata(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".env").write_text("SECRET=value", encoding="utf-8")
    extra = workspace / "input"
    extra.mkdir()
    backend = RecordingBackend()
    supervisor = SandboxSupervisor(workspace, native_backend=backend)

    launch = supervisor.prepare_launch(
        command=sys.executable,
        args=("-V",),
        env={"PATH": os.environ.get("PATH", "")},
        cwd=None,
        config=SandboxConfig(
            filesystem=SandboxFilesystemMode.WORKSPACE_WRITE,
            network=SandboxNetworkMode.DENIED,
            readable_roots=("input",),
        ),
    )

    assert launch.sandboxed is True
    assert launch.backend == "recording"
    assert backend.policy is not None
    assert workspace in backend.policy.readable_roots
    assert workspace in backend.policy.writable_roots
    assert workspace / ".git" in backend.policy.denied_write_paths
    assert workspace / ".env" in backend.policy.denied_read_paths
    assert backend.policy.network is SandboxNetworkMode.DENIED


def test_supervisor_rejects_relative_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    supervisor = SandboxSupervisor(workspace, native_backend=RecordingBackend())

    with pytest.raises(SandboxPolicyError, match="不能越过 workspace"):
        supervisor.prepare_launch(
            command=sys.executable,
            args=(),
            env={"PATH": os.environ.get("PATH", "")},
            cwd=None,
            config=SandboxConfig(readable_roots=("../outside",)),
        )


def test_unsupported_platform_fails_closed(tmp_path: Path) -> None:
    supervisor = SandboxSupervisor(
        tmp_path,
        native_backend=UnsupportedSandboxBackend("unsupported"),
    )

    with pytest.raises(SandboxUnavailableError, match="拒绝降级执行"):
        supervisor.prepare_launch(
            command=sys.executable,
            args=(),
            env={"PATH": os.environ.get("PATH", "")},
            cwd=None,
            config=SandboxConfig(),
        )


def test_explicit_host_mode_is_visible_in_launch_spec(tmp_path: Path) -> None:
    supervisor = SandboxSupervisor(
        tmp_path,
        native_backend=UnsupportedSandboxBackend("unused"),
    )

    launch = supervisor.prepare_launch(
        command=sys.executable,
        args=(),
        env={"PATH": os.environ.get("PATH", "")},
        cwd=None,
        config=SandboxConfig(filesystem=SandboxFilesystemMode.HOST),
    )

    assert launch.sandboxed is False
    assert launch.backend == "host"


@pytest.mark.skipif(sys.platform != "darwin", reason="仅验证 macOS Seatbelt")
@pytest.mark.asyncio
async def test_native_sandbox_blocks_read_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("host-secret", encoding="utf-8")
    (workspace / ".env").write_text("workspace-secret", encoding="utf-8")
    launch = SandboxSupervisor(workspace).prepare_launch(
        command=sys.executable,
        args=("-c", f"print(open({str(secret)!r}).read())"),
        env={
            key: value
            for key in ("HOME", "LANG", "PATH", "TMPDIR")
            if (value := os.environ.get(key))
        },
        cwd=None,
        config=SandboxConfig(network=SandboxNetworkMode.DENIED),
    )

    process = await asyncio.create_subprocess_exec(
        launch.command,
        *launch.args,
        cwd=launch.cwd,
        env=launch.env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    assert process.returncode != 0
    assert b"host-secret" not in stdout
    assert b"Operation not permitted" in stderr


@pytest.mark.skipif(sys.platform != "darwin", reason="仅验证 macOS Seatbelt")
@pytest.mark.asyncio
async def test_shell_tool_uses_workspace_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("host-secret", encoding="utf-8")
    (workspace / ".env").write_text("workspace-secret", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    tool = ShellCommandTool(
        workspace,
        sandbox_supervisor=SandboxSupervisor(workspace),
    )

    write_result = await tool.execute({"command": "printf safe > result.txt"})
    read_result = await tool.execute({"command": f"cat {secret}"})
    protected_result = await tool.execute({"command": "cat .env"})
    env_result = await tool.execute(
        {"command": "printf %s ${OPENAI_API_KEY:-not-present}"}
    )
    network_result = await tool.execute(
        {
            "command": (
                "/usr/bin/python3 -c 'import socket; socket.socket(socket.AF_INET, "
                "socket.SOCK_STREAM)'"
            )
        }
    )

    assert write_result["exit_code"] == 0
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "safe"
    assert read_result["exit_code"] != 0
    assert "host-secret" not in read_result["stdout"]
    assert "Operation not permitted" in read_result["stderr"]
    assert protected_result["exit_code"] != 0
    assert "workspace-secret" not in protected_result["stdout"]
    assert "Operation not permitted" in protected_result["stderr"]
    assert env_result["stdout"] == "not-present"
    assert network_result["exit_code"] != 0
    assert "Operation not permitted" in network_result["stderr"]
