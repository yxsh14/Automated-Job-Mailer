"""
Utility functions for the Email Automation Service.

Provides email validation, file existence checks, and daily summary reports.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("email_automation")

# RFC 5322 simplified email regex
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}"
    r"[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def validate_email(email: str) -> bool:
    """
    Validate an email address against a simplified RFC 5322 pattern.

    Args:
        email: The email address string to validate.

    Returns:
        True if the email is syntactically valid, False otherwise.
    """
    if not email or not isinstance(email, str):
        return False
    return bool(_EMAIL_REGEX.match(email.strip()))


def check_file_exists(file_path: Path, description: str = "File") -> bool:
    """
    Check whether a file exists and log a warning if it does not.

    Args:
        file_path: Path to the file.
        description: Human-readable name for log messages.

    Returns:
        True if the file exists, False otherwise.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"{description} not found: {path}")
        return False
    if not path.is_file():
        logger.warning(f"{description} is not a regular file: {path}")
        return False
    return True


def generate_daily_summary(
    total_sent: int,
    total_failed: int,
    total_remaining: int,
    log_dir: Optional[Path] = None,
) -> str:
    """
    Generate a plain-text daily summary and optionally write it to a file.

    Args:
        total_sent: Number of emails successfully sent today.
        total_failed: Number of emails that failed today.
        total_remaining: Number of unsent contacts remaining.
        log_dir: If provided, the summary is also written to this directory.

    Returns:
        The summary string.
    """
    now = datetime.now()
    summary_lines = [
        "=" * 50,
        f"  DAILY SUMMARY — {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 50,
        f"  Emails sent today      : {total_sent}",
        f"  Emails failed today    : {total_failed}",
        f"  Contacts remaining     : {total_remaining}",
        "=" * 50,
    ]
    summary = "\n".join(summary_lines)

    logger.info(f"Daily summary:\n{summary}")

    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        summary_file = log_dir / f"summary_{now.strftime('%Y-%m-%d')}.txt"
        summary_file.write_text(summary, encoding="utf-8")
        logger.info(f"Summary written to {summary_file}")

    return summary
