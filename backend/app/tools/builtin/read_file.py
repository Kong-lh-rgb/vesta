"""仅允许读取 Vesta 工作区的 UTF-8 文本工具。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.models.types import ToolDefinition

from ..base import BaseTool
from ._workspace import (
    is_protected_workspace_path,
    resolve_workspace_path,
    workspace_root_path,
)

MAX_READ_BYTES = 2 * 1024 * 1024


class ReadFileTool(BaseTool):
    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self._workspace_root = workspace_root_path(workspace_root)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read a UTF-8 text file inside the local workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the workspace.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            strict=True,
        )

    async def execute(self, arguments: dict[str, Any]) -> str:
        relative_path = arguments.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("'path' must be a non-empty string")
        target = resolve_workspace_path(self._workspace_root, relative_path)
        if is_protected_workspace_path(self._workspace_root, target):
            # 与沙箱对子进程的 deny 列表保持一致：模型不能经由免审批的
            # read_file 读取 shell 沙箱都读不到的 .git / .vesta / .env。
            raise ValueError(
                "'path' targets a protected workspace entry "
                "(.git / .vesta / .env); ask the user to provide the content"
            )
        return await asyncio.to_thread(_read_utf8_file, target)


def _read_utf8_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"file does not exist: {path.name}")
    size = path.stat().st_size
    if size > MAX_READ_BYTES:
        # 读前限额：工具输出最终只保留 2 万字符，整文件读入内存与证据
        # 落盘只是浪费；超大文件引导模型用 run_shell_command 取局部。
        raise ValueError(
            f"file is too large to read: {size} bytes exceeds the "
            f"{MAX_READ_BYTES}-byte limit; use run_shell_command "
            "(head/tail/sed) to read a smaller slice"
        )
    return path.read_text(encoding="utf-8")
