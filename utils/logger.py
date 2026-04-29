"""Logging setup for the complaint agent system."""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "complaint_agent",
    level: str = "INFO",
    log_file: Optional[Path] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "complaint_agent") -> logging.Logger:
    return logging.getLogger(name)
