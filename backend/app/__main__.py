"""允许通过 ``python -m app`` 启动 Vesta CLI。"""

from __future__ import annotations

from .models.chat import main

if __name__ == "__main__":
    main()
