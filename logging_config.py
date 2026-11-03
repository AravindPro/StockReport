"""Shared root logging configuration for the application."""

import logging
from pathlib import Path


LOG_DIRECTORY = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIRECTORY / "run_log.log"


def configure_logging() -> None:
    """Append every root-logger message to the shared log file."""
    root_logger = logging.getLogger()
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    root_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_myagent_run_log", False)
        ),
        None,
    )
    if file_handler is None:
        file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        file_handler._myagent_run_log = True  # type: ignore[attr-defined]
        root_logger.addHandler(file_handler)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Streamlit and other libraries may install console handlers before this
    # function runs. Keep only our file handler on the root logger.
    for handler in root_logger.handlers[:]:
        if handler is not file_handler:
            root_logger.removeHandler(handler)

    root_logger._myagent_configured = True  # type: ignore[attr-defined]
