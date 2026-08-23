"""Vesta Host 入口：``python -m app.server``。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Vesta Host (FastAPI + JSON-RPC WebSocket)."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--database",
        help="SQLite database path (default: backend/.vesta/vesta.db).",
    )
    parser.add_argument("--provider", help="Model provider (default: auto-select).")
    parser.add_argument("--model", help="Override the configured model name.")
    parser.add_argument(
        "--mcp-config",
        help="Path to the MCP Server JSON configuration file.",
    )
    parser.add_argument(
        "--computer-helper",
        help="Explicit Swift helper binary path (overrides env/dev auto-detect).",
    )
    parser.add_argument(
        "--disable-computer",
        action="store_true",
        help="Disable Computer Runtime even if a helper is available.",
    )
    return parser


def _application_kwargs(args: argparse.Namespace) -> dict[str, object]:
    """按同一份启动参数为每次Host实例构造依赖。"""

    from app.computer import build_macos_computer

    application_kwargs: dict[str, object] = {}
    if args.database:
        application_kwargs["database"] = args.database
    if args.mcp_config:
        application_kwargs["mcp_config"] = args.mcp_config

    computer_runtime, computer_host_status = build_macos_computer(
        helper_path=args.computer_helper,
        enabled=False if args.disable_computer else None,
    )
    application_kwargs["computer_runtime"] = computer_runtime
    application_kwargs["computer_host_status"] = computer_host_status
    return application_kwargs


async def _serve(args: argparse.Namespace) -> int:
    """运行Host；收到受控重启请求后优雅关闭并重新装配。"""

    import uvicorn

    from app.application import Application
    from app.server.app import create_app

    while True:
        restart_requested = False
        server: Any = None

        def request_restart() -> None:
            nonlocal restart_requested
            restart_requested = True
            if server is not None:
                server.should_exit = True

        try:
            application = Application(
                provider=args.provider,
                model=args.model,
                **_application_kwargs(args),
            )
        except ValueError as exc:
            print(f"启动失败：{exc}", file=sys.stderr)
            return 2

        app = create_app(application, restart_callback=request_restart)
        config = uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
        if not restart_requested:
            return 0
        logging.getLogger("vesta.server").info(
            "Restarting Vesta Host with saved configuration"
        )


def main() -> int:
    args = _parser().parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        return asyncio.run(_serve(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
