"""内置文件工具共用的工作区路径校验。"""

from __future__ import annotations

from pathlib import Path

# 与 SandboxSupervisor 的 _PROTECTED_RELATIVE_PATHS 一致的敏感入口。
# 工具免审批直接落盘，必须与沙箱子进程执行同一套敏感文件定义；
# 这里取保守超集：任何层级命中都拒绝，包括尚未创建的目标。
_PROTECTED_ENTRY_NAMES = frozenset({".git", ".vesta", ".env"})


def workspace_root_path(workspace_root: str | Path | None) -> Path:
    if workspace_root is None:
        workspace_root = Path(__file__).resolve().parents[4] / "workspace"
    return Path(workspace_root).resolve()


def resolve_workspace_path(
    workspace_root: Path,
    relative_path: str,
    *,
    allow_root: bool = False,
) -> Path:
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("path must be relative to the workspace")

    resolved = (workspace_root / requested).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        raise ValueError("path escapes the workspace") from None

    if not allow_root and resolved == workspace_root:
        raise ValueError("path must reference an item inside the workspace")
    return resolved


def is_protected_workspace_path(workspace_root: Path, target: Path) -> bool:
    """目标是否落在受保护的工作区条目（.git / .vesta / .env）内。

    免审批的文件工具据此与沙箱 deny 列表保持一致：模型不能经由
    write_file 覆盖 .git/config 或 .env —— 那正是沙箱给 shell 与
    MCP 子进程划出的红线。越界路径不在此判定（由
    resolve_workspace_path 负责）。
    """

    try:
        relative = target.relative_to(workspace_root)
    except ValueError:
        return False
    return any(part in _PROTECTED_ENTRY_NAMES for part in relative.parts)
