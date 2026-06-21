"""Logging configuration."""

import logging
import sys
from pathlib import Path


def configure_logging(debug: bool = False, log_dir: Path = Path("data/logs")) -> None:
    """Configure process logging without stacking duplicate app handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in list(root_logger.handlers):
        if getattr(handler, "_dynasty_timer_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler._dynasty_timer_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_dir / "app.log")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler._dynasty_timer_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(file_handler)

    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
