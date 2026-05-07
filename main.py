"""
main.py — Entry point for the Email Automation Service.

Usage:
    # Run the full scheduler (respects 9 AM - 4 PM window):
    python main.py

    # Send ONE email right now (for testing, bypasses time window):
    python main.py --now

    # Send N emails right now:
    python main.py --now --count 5

Data source (auto-detected from env vars):
    - GOOGLE_SHEET_ID set  -> uses Google Sheets (cloud, for Railway deployment)
    - GOOGLE_SHEET_ID unset -> uses local Excel file (data/contacts.xlsx)
"""

import argparse
import os
import signal
import sys
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config.settings import get_settings
from config.logging_config import setup_logging
from src.email_sender import EmailSender
from src.scheduler import Scheduler
from src.excel_handler import ExcelHandler
from src.sheets_handler import SheetsHandler
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Email Automation Service")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Send email(s) immediately regardless of the scheduled time window.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        metavar="N",
        help="Number of emails to send when using --now (default: 1).",
    )
    return parser.parse_args()


def build_components(settings):
    """Instantiate and wire all service components."""
    email_sender = EmailSender(
        smtp_host=settings.smtp.host,
        smtp_port=settings.smtp.port,
        email_address=settings.smtp.email_address,
        email_password=settings.smtp.email_password,
        template_path=settings.files.template_file,
        resume_path=settings.files.resume_file,
        max_retries=settings.safety.max_retries,
        retry_delay=settings.safety.retry_delay_seconds,
    )
    email_sender.load_template()

    # Auto-detect backend: Google Sheets (cloud) or local Excel
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()

    if sheet_id and creds_json:
        data_handler = SheetsHandler(sheet_id=sheet_id, credentials_json=creds_json)
        logger_tmp = logging.getLogger("email_automation")
        logger_tmp.info("Backend: Google Sheets (cloud mode)")
    else:
        data_handler = ExcelHandler(settings.files.excel_file)
        logger_tmp = logging.getLogger("email_automation")
        logger_tmp.info(f"Backend: Local Excel ({settings.files.excel_file})")

    data_handler.load()
    data_handler.validate()

    return email_sender, data_handler


def run_now(email_sender: EmailSender, data_handler: Any, count: int, logger: logging.Logger) -> None:
    """Send `count` emails immediately — used for testing."""
    logger.info(f"[--now mode] Sending {count} email(s) immediately.")
    sent = 0
    failed = 0

    for i in range(count):
        contact = data_handler.get_next_unsent()
        if contact is None:
            logger.warning("No more unsent contacts. Stopping.")
            break

        email     = str(contact.get("Email", "")).strip()
        name      = str(contact.get("ContactName", "Hiring Manager")).strip()
        company   = str(contact.get("Company", "")).strip()

        logger.info(f"[{i+1}/{count}] Sending to {email} - {name} at {company}")

        success = email_sender.send_email(
            recipient_email=email,
            contact_name=name,
            company=company,
        )

        if success:
            sent += 1
            data_handler.mark_as_sent(email)
            logger.info(f"Sent and marked: {email}")
        else:
            failed += 1
            # Still mark to avoid hammering a broken address
            data_handler.mark_as_sent(email)
            logger.error(f"Failed (marked to skip on retry): {email}")

    logger.info(
        f"[--now mode] Done. Sent: {sent} | Failed: {failed} | "
        f"Remaining: {data_handler.count_unsent()}"
    )


def run_scheduler(email_sender: EmailSender, data_handler: Any, settings, logger: logging.Logger) -> None:
    """Start the full scheduler loop (respects 9 AM - 4 PM window)."""
    scheduler = Scheduler(
        email_sender=email_sender,
        data_handler=data_handler,
        start_hour=settings.schedule.start_hour,
        end_hour=settings.schedule.end_hour,
        emails_per_day=settings.schedule.emails_per_day,
        min_interval=settings.schedule.min_interval_minutes,
        max_interval=settings.schedule.max_interval_minutes,
        log_dir=settings.logging.log_dir,
    )

    # Graceful shutdown on SIGTERM / Ctrl-C
    def _handle_signal(signum, frame):
        logger.info(f"Signal {signum} received - shutting down gracefully.")
        scheduler.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        f"Scheduler running | window: {settings.schedule.start_hour}:00-{settings.schedule.end_hour}:00 (IST) "
        f"| {settings.schedule.emails_per_day} emails/day "
        f"| interval: {settings.schedule.min_interval_minutes}-{settings.schedule.max_interval_minutes} min"
    )
    scheduler.run()


def start_dummy_server():
    """Starts a tiny web server to satisfy Render's port check."""
    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Service is running")
        def log_message(self, format, *args):
            return # Silent logs

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.getLogger("email_automation").info(f"Health-check server started on port {port}")
    server.serve_forever()


def main() -> None:
    args = parse_args()
    settings = get_settings()

    # Bootstrap logging
    logger = setup_logging(
        log_dir=settings.logging.log_dir,
        log_level=settings.logging.log_level,
    )

    logger.info("=" * 60)
    logger.info("  Email Automation Service - starting up")
    logger.info("=" * 60)

    # Validate credentials
    try:
        settings.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Build components
    try:
        email_sender, data_handler = build_components(settings)
    except FileNotFoundError as e:
        logger.error(f"Missing file: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Data backend initialization failed: {e}")
        sys.exit(1)

    logger.info(
        f"Contacts loaded: {data_handler.total_contacts()} total | "
        f"{data_handler.count_unsent()} unsent | "
        f"{data_handler.count_sent()} already sent"
    )

    # Start health-check server in a background thread for Render
    threading.Thread(target=start_dummy_server, daemon=True).start()

    # Run mode
    if args.now:
        run_now(email_sender, data_handler, args.count, logger)
    else:
        run_scheduler(email_sender, data_handler, settings, logger)


if __name__ == "__main__":
    main()
