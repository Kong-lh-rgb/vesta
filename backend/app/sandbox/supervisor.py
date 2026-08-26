"""沙箱策略解析与平台后端选择。"""

from __future__ import annotations

import sys
from pathlib import Path

from .backends import (
    HostSandboxBackend,
    MacOSSeatbeltBackend,
    SandboxBackend,
    UnsupportedSandboxBackend,
    resolve_executable,
)
from .errors import SandboxPolicyError
from .models import (
    SandboxConfig,
    SandboxFilesystemMode,
    SandboxLaunchSpec,
    SandboxPolicy,
)

_PROTECTED_RELATIVE_PATHS = (
    ".git",
    ".vesta",
    ".env",
    "backend/.env",
)


class SandboxSupervisor:
    """将配置解析为确定策略，并保证平台能力不足时拒绝执行。"""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        native_backend: SandboxBackend | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self._native_backend = native_backend or _platform_backend()
        self._host_backend = HostSandboxBackend()

    def prepare_launch(
        self,
        *,
        command: str,
        args: tuple[str, ...],
        env: dict[str, str],
        cwd: str | None,
        config: SandboxConfig,
    ) -> SandboxLaunchSpec:
        resolved_command = resolve_executable(command, env=env)
        working_directory = self._resolve_working_directory(cwd)
        policy = self._build_policy(
            config,
            command=resolved_command,
            working_directory=working_directory,
            env=env,
        )
        backend = (
            self._host_backend
            if config.filesystem is SandboxFilesystemMode.HOST
            else self._native_backend
        )
        return backend.prepare(
            command=resolved_command,
            args=args,
            env=env,
            policy=policy,
        )

    def _build_policy(
        self,
        config: SandboxConfig,
        *,
        command: Path,
        working_directory: Path,
        env: dict[str, str],
    ) -> SandboxPolicy:
        readable = [command.parent, command.resolve().parent]
        writable: list[Path] = []
        if config.filesystem in {
            SandboxFilesystemMode.READ_ONLY,
            SandboxFilesystemMode.WORKSPACE_WRITE,
        }:
            readable.append(self.workspace_root)
        if config.filesystem is SandboxFilesystemMode.WORKSPACE_WRITE:
            writable.append(self.workspace_root)
        readable.extend(
            self._resolve_extra_root(value) for value in config.readable_roots
        )
        for value in config.writable_roots:
            root = self._resolve_extra_root(value)
            readable.append(root)
            writable.append(root)

        runtime_read, runtime_write = _runtime_support_roots(command, env)
        readable.extend(runtime_read)
        writable.extend(runtime_write)
        denied = tuple(
            path
            for relative in _PROTECTED_RELATIVE_PATHS
            if (path := self.workspace_root / relative).exists()
        )
        return SandboxPolicy(
            filesystem=config.filesystem,
            network=config.network,
            working_directory=working_directory,
            readable_roots=_deduplicate(readable),
            writable_roots=_deduplicate(writable),
            denied_read_paths=denied,
            denied_write_paths=denied,
            allowed_domains=config.allowed_domains,
        )

    def _resolve_working_directory(self, value: str | None) -> Path:
        if value is None:
            return self.workspace_root
        return self._resolve_extra_root(value)

    def _resolve_extra_root(self, value: str) -> Path:
        candidate = Path(value).expanduser()
        is_relative = not candidate.is_absolute()
        if is_relative:
            candidate = self.workspace_root / candidate
        resolved = candidate.resolve()
        if is_relative and not resolved.is_relative_to(self.workspace_root):
            raise SandboxPolicyError(
                f"沙箱相对路径不能越过 workspace：{value}"
            )
        if not resolved.exists():
            raise SandboxPolicyError(f"沙箱路径不存在：{resolved}")
        return resolved


def _platform_backend() -> SandboxBackend:
    if sys.platform == "darwin":
        return MacOSSeatbeltBackend()
    return UnsupportedSandboxBackend(sys.platform)


def _runtime_support_roots(
    command: Path,
    env: dict[str, str],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """仅开放包运行时缓存，不开放整个用户主目录。"""

    home_value = env.get("HOME")
    if not home_value:
        return (), ()
    home = Path(home_value).expanduser().resolve()
    readable: list[Path] = []
    writable: list[Path] = []
    name = command.name.lower()
    if name in {"uv", "uvx"}:
        readable.extend((home / ".cache" / "uv", home / ".local" / "share" / "uv"))
        writable.extend((home / ".cache" / "uv", home / ".local" / "share" / "uv"))
    if name in {"node", "npm", "npx", "pnpm", "yarn", "bun", "bunx"}:
        readable.extend((home / ".npm", home / ".cache" / "node"))
        writable.extend((home / ".npm", home / ".cache" / "node"))
    command_parts = command.absolute().parts
    if "node_modules" in command_parts:
        index = command_parts.index("node_modules")
        readable.append(Path(*command_parts[: index + 1]))
    return (
        tuple(path.resolve() for path in readable if path.exists()),
        tuple(path.resolve() for path in writable if path.exists()),
    )


def _deduplicate(paths: list[Path]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(path.resolve() for path in paths if path.exists()))


__all__ = ["SandboxSupervisor"]
