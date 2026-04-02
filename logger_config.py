"""
Structured logging configuration.
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path


def setup_logging() -> logging.Logger:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir   = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file  = log_dir / f"nl2sql_{datetime.now():%Y%m%d}.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("nl2sql")
    logger.setLevel(log_level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler
    fh = logging.FileHandler(log_file)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logging()
