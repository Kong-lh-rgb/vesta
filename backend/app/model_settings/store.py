"""模型设置的非敏感JSON存储。"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import StoredModelSettings

DEFAULT_MODEL_SETTINGS_PATH = (
    Path(__file__).resolve().parents[2] / ".vesta" / "settings" / "models.json"
)


class ModelSettingsStore:
    """用临时文件+原子替换保存设置，文件中禁止出现密钥。"""

    def __init__(self, path: str | Path = DEFAULT_MODEL_SETTINGS_PATH) -> None:
        self.path = Path(path).expanduser().resolve()

    def load(self) -> StoredModelSettings | None:
        if not self.path.is_file():
            return None
        if self.path.is_symlink():
            raise ValueError("model settings file cannot be a symbolic link")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return StoredModelSettings.model_validate(payload)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialize Vesta settings/Keychain operations across processes."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                raise PermissionError("model settings lock must be owner-only")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def save(self, settings: StoredModelSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            settings.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.tmp-",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(serialized + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if temporary_name is not None and os.path.exists(temporary_name):
                os.unlink(temporary_name)


__all__ = ["DEFAULT_MODEL_SETTINGS_PATH", "ModelSettingsStore"]
