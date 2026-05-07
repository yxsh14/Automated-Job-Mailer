"""
Logging configuration for the Email Automation Service.

Creates daily rotating log files under the configured log directory
and also streams to stdout for interactive use.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logging(
    log_dir: Path,
    log_level: str = "INFO",
    logger_name: str = "email_automation",
) -> logging.Logger:
    """
    Configure and return the application logger.

    Args:
        log_dir: Directory where log files will be written.
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        logger_name: Name of the logger instance.

    Returns:
        Configured logging.Logger instance.
    """
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Daily log file name
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"email_automation_{today}.log"

    # Create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
