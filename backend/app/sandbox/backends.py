"""沙箱策略的平台执行后端。"""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from .errors import SandboxUnavailableError
from .models import (
    SandboxLaunchSpec,
    SandboxNetworkMode,
    SandboxPolicy,
)


class SandboxBackend(ABC):
    """把统一策略编译为实际进程启动参数。"""

    @abstractmethod
    def prepare(
        self,
        *,
        command: Path,
        args: tuple[str, ...],
        env: dict[str, str],
        policy: SandboxPolicy,
    ) -> SandboxLaunchSpec:
        """生成启动规格，不执行进程。"""


class HostSandboxBackend(SandboxBackend):
    """显式关闭隔离时使用；仍保留清理后的环境变量。"""

    def prepare(
        self,
        *,
        command: Path,
        args: tuple[str, ...],
        env: dict[str, str],
        policy: SandboxPolicy,
    ) -> SandboxLaunchSpec:
        return SandboxLaunchSpec(
            command=str(command),
            args=args,
            cwd=str(policy.working_directory),
            env=env,
            backend="host",
            sandboxed=False,
        )


class MacOSSeatbeltBackend(SandboxBackend):
    """使用 macOS Seatbelt 对整个 MCP 子进程树施加限制。"""

    executable = Path("/usr/bin/sandbox-exec")

    def prepare(
        self,
        *,
        command: Path,
        args: tuple[str, ...],
        env: dict[str, str],
        policy: SandboxPolicy,
    ) -> SandboxLaunchSpec:
        if not self.executable.is_file():
            raise SandboxUnavailableError(
                "macOS sandbox-exec 不可用，拒绝在宿主机直接启动第三方进程"
            )
        if policy.allowed_domains:
            raise SandboxUnavailableError(
                "当前 macOS 后端尚不能强制域名白名单，拒绝弱化网络策略"
            )
        profile = _seatbelt_profile(command, policy)
        return SandboxLaunchSpec(
            command=str(self.executable),
            args=("-p", profile, str(command), *args),
            cwd=str(policy.working_directory),
            env=env,
            backend="macos_seatbelt",
            sandboxed=True,
        )


class UnsupportedSandboxBackend(SandboxBackend):
    """没有可靠平台实现时 fail closed。"""

    def __init__(self, platform: str) -> None:
        self.platform = platform

    def prepare(
        self,
        *,
        command: Path,
        args: tuple[str, ...],
        env: dict[str, str],
        policy: SandboxPolicy,
    ) -> SandboxLaunchSpec:
        del command, args, env, policy
        raise SandboxUnavailableError(
            f"平台 {self.platform!r} 尚无可用的 Vesta 沙箱后端，拒绝降级执行"
        )


def _seatbelt_profile(command: Path, policy: SandboxPolicy) -> str:
    lines = [
        "(version 1)",
        "(deny default)",
        '(import "system.sb")',
        "(allow process*)",
    ]
    readable = _unique_paths((*_platform_read_roots(), command, *policy.readable_roots))
    metadata_paths = _ancestor_paths(
        (command, *policy.readable_roots, *policy.writable_roots)
    )
    if metadata_paths:
        lines.append(_literal_path_rule("allow", "file-read-metadata", metadata_paths))
    if readable:
        lines.append(_path_rule("allow", "file-read*", readable))
    if policy.writable_roots:
        lines.append(_path_rule("allow", "file-write*", policy.writable_roots))
    if policy.denied_read_paths:
        lines.append(_path_rule("deny", "file-read*", policy.denied_read_paths))
    if policy.denied_write_paths:
        lines.append(_path_rule("deny", "file-write*", policy.denied_write_paths))
    if policy.network is SandboxNetworkMode.UNRESTRICTED:
        lines.append("(allow network*)")
    return "\n".join(lines)


def _path_rule(effect: str, operation: str, paths: tuple[Path, ...]) -> str:
    selectors = " ".join(
        f"(subpath {json.dumps(str(path))})" for path in _unique_paths(paths)
    )
    return f"({effect} {operation} {selectors})"


def _literal_path_rule(effect: str, operation: str, paths: tuple[Path, ...]) -> str:
    unique = tuple(
        dict.fromkeys(item.absolute() for item in paths if item.exists())
    )
    selectors = " ".join(
        f"(literal {json.dumps(str(path))})"
        for path in unique
    )
    return f"({effect} {operation} {selectors})"


def _platform_read_roots() -> tuple[Path, ...]:
    return tuple(
        path
        for path in (
            Path("/System"),
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/Library/Frameworks"),
            Path("/opt"),
            Path("/opt/homebrew"),
            Path("/private/var/select"),
        )
        if path.exists()
    )


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(path.resolve() for path in paths if path.exists()))


def _ancestor_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    ancestors: list[Path] = []
    for path in paths:
        current = path.absolute()
        while current.parent != current:
            ancestors.append(current)
            current = current.parent
    return tuple(dict.fromkeys(ancestors))


def resolve_executable(command: str, *, env: dict[str, str]) -> Path:
    """只接受真实存在的绝对 executable，同时保留虚拟环境入口语义。"""

    candidate = Path(command).expanduser()
    if candidate.is_absolute() or "/" in command:
        executable = candidate.absolute()
    else:
        found = shutil.which(command, path=env.get("PATH"))
        if found is None:
            raise SandboxUnavailableError(f"找不到可执行文件：{command}")
        executable = Path(found).absolute()
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise SandboxUnavailableError(f"可执行文件无效：{executable}") from exc
    if not resolved.is_file() or not executable.is_file():
        raise SandboxUnavailableError(f"可执行文件无效：{executable}")
    return executable


__all__ = [
    "HostSandboxBackend",
    "MacOSSeatbeltBackend",
    "SandboxBackend",
    "UnsupportedSandboxBackend",
    "resolve_executable",
]
