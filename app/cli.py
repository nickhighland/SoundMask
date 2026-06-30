from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn

from app.config import get_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="soundmask",
        description="Run the SoundMask web application.",
    )
    parser.set_defaults(host=None, port=None, reload=False)
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the SoundMask web server.",
    )
    serve_parser.add_argument(
        "--host",
        help="Bind host. Defaults to SOUNDMASK_HOST or the app default.",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        help="Bind port. Defaults to SOUNDMASK_PORT or 8080.",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = args.command or "serve"

    if command != "serve":
        parser.error(f"Unsupported command: {command}")

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=args.host or config.host,
        port=args.port or config.port,
        reload=bool(args.reload),
    )
