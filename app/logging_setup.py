from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import AppConfig


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(config: AppConfig) -> None:
    logger = logging.getLogger("app")
    if getattr(logger, "_soundmask_configured", False):
        return

    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = RotatingFileHandler(
        config.paths.logs / "soundmask.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    logger._soundmask_configured = True  # type: ignore[attr-defined]

