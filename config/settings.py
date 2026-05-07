"""
Application settings loaded from environment variables.

All configuration values are centralized here and loaded from a .env file
at project root. Defaults are provided for non-sensitive values.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Determine project root (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class SMTPSettings:
    """SMTP / email server configuration."""
    host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port: int = int(os.getenv("SMTP_PORT", "587"))
    email_address: str = os.getenv("EMAIL_ADDRESS", "")
    email_password: str = os.getenv("EMAIL_PASSWORD", "")

    def validate(self) -> None:
        """Raise ValueError if critical fields are missing."""
        if not self.email_address:
            raise ValueError("EMAIL_ADDRESS is not set in the environment.")
        if not self.email_password:
            raise ValueError("EMAIL_PASSWORD is not set in the environment.")


@dataclass(frozen=True)
class FileSettings:
    """Paths to data files used by the service."""
    excel_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("EXCEL_FILE", "data/contacts.xlsx")
    )
    resume_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("RESUME_FILE", "data/resume.pdf")
    )
    template_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("TEMPLATE_FILE", "templates/email_template.txt")
    )


@dataclass(frozen=True)
class ScheduleSettings:
    """Scheduling parameters."""
    start_hour: int = int(os.getenv("START_HOUR", "9"))
    end_hour: int = int(os.getenv("END_HOUR", "16"))
    emails_per_day: int = int(os.getenv("EMAILS_PER_DAY", "20"))
    min_interval_minutes: int = int(os.getenv("MIN_INTERVAL_MINUTES", "18"))
    max_interval_minutes: int = int(os.getenv("MAX_INTERVAL_MINUTES", "24"))


@dataclass(frozen=True)
class SafetySettings:
    """Retry and safety configuration."""
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    retry_delay_seconds: int = int(os.getenv("RETRY_DELAY_SECONDS", "60"))


@dataclass(frozen=True)
class LogSettings:
    """Logging configuration."""
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("LOG_DIR", "logs")
    )


@dataclass(frozen=True)
class AppSettings:
    """Aggregated application settings."""
    smtp: SMTPSettings = field(default_factory=SMTPSettings)
    files: FileSettings = field(default_factory=FileSettings)
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    logging: LogSettings = field(default_factory=LogSettings)

    def validate(self) -> None:
        """Run all validations."""
        self.smtp.validate()


def get_settings() -> AppSettings:
    """Create and return the application settings singleton."""
    return AppSettings()
