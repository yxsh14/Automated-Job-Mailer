"""
Scheduler for the Email Automation Service.

Orchestrates the daily email-sending loop: checks for unsent contacts,
randomises intervals between sends, enforces daily limits, and stops
outside the configured operating hours.
"""

import logging
import random
import time
import pytz
from datetime import datetime, timedelta
from src.email_sender import EmailSender
from src.utils import generate_daily_summary
from typing import Any, Optional

logger = logging.getLogger("email_automation")


class Scheduler:
    """Manages the daily schedule of outbound emails."""

    def __init__(
        self,
        email_sender: EmailSender,
        data_handler: Any,
        start_hour: int = 9,
        end_hour: int = 16,
        emails_per_day: int = 20,
        min_interval: int = 18,
        max_interval: int = 24,
        log_dir: Optional[str] = None,
    ) -> None:
        self.email_sender = email_sender
        self.data_handler = data_handler
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.emails_per_day = emails_per_day
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.log_dir = log_dir

        # Daily counters (reset every new day)
        self._sent_today: int = 0
        self._failed_today: int = 0
        self._current_date: Optional[str] = None
        self._last_send_time: Optional[datetime] = None

        # Graceful shutdown flag (set externally via signal handler)
        self.should_stop: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Main loop - runs indefinitely until stopped.
        """
        logger.info("Scheduler started. Operating in IST (Asia/Kolkata) timezone.")
        tz = pytz.timezone("Asia/Kolkata")

        while not self.should_stop:
            try:
                now = datetime.now(tz)

                # ---- Day boundary reset ----
                today_str = now.strftime("%Y-%m-%d")
                if self._current_date != today_str:
                    self._reset_daily_counters(today_str)

                # ---- Outside operating hours → sleep until start ----
                if now.hour < self.start_hour:
                    wait = self._seconds_until(self.start_hour)
                    logger.info(
                        f"Before operating hours ({self.start_hour}:00). "
                        f"Sleeping {wait // 60:.0f} minutes."
                    )
                    self._sleep(wait)
                    continue

                if now.hour >= self.end_hour:
                    self._end_of_day_summary()
                    wait = self._seconds_until_next_day_start()
                    logger.info(
                        f"After operating hours ({self.end_hour}:00). "
                        f"Sleeping until tomorrow {self.start_hour}:00 "
                        f"({wait // 3600:.1f} hours)."
                    )
                    self._sleep(wait)
                    continue

                # ---- Daily limit reached ----
                if self._sent_today >= self.emails_per_day:
                    logger.info(
                        f"Daily limit reached ({self.emails_per_day} emails). "
                        f"Waiting for next day."
                    )
                    self._end_of_day_summary()
                    wait = self._seconds_until_next_day_start()
                    self._sleep(wait)
                    continue

                # ---- No unsent contacts ----
                if not self.data_handler.has_unsent():
                    logger.info("No new contacts to process. Sleeping until next day.")
                    self._end_of_day_summary()
                    wait = self._seconds_until_next_day_start()
                    self._sleep(wait)
                    continue

                # ---- Send next email ----
                self._send_next()
                self._last_send_time = datetime.now(tz)

                # ---- Random interval ----
                interval = random.randint(self.min_interval, self.max_interval) * 60
                logger.info(f"Next email in {interval // 60} minutes.")
                self._sleep(interval)

            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"Unexpected error in scheduler loop: {exc}. "
                    "Recovering and retrying in 30 seconds…",
                    exc_info=True,
                )
                self._sleep(30)

        logger.info("Scheduler loop stopped.")

    def process_once(self) -> str:
        """
        Check conditions and send ONE email if appropriate.
        This is designed to be called by an external trigger (e.g. HTTP request).
        Returns a status message.
        """
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)

        # ---- Day boundary reset ----
        today_str = now.strftime("%Y-%m-%d")
        if self._current_date != today_str:
            self._reset_daily_counters(today_str)

        # ---- Outside operating hours ----
        if now.hour < self.start_hour or now.hour >= self.end_hour:
            msg = f"Outside operating hours ({self.start_hour}:00-{self.end_hour}:00)."
            logger.info(msg)
            return msg

        # ---- Daily limit reached ----
        if self._sent_today >= self.emails_per_day:
            msg = f"Daily limit reached ({self.emails_per_day})."
            logger.info(msg)
            return msg

        # ---- Interval check (throttle) ----
        if self._last_send_time:
            # We use the minimum interval as the throttle
            elapsed = (now - self._last_send_time).total_seconds() / 60
            if elapsed < self.min_interval:
                msg = f"Throttling: only {elapsed:.1f} min elapsed since last send (min: {self.min_interval})."
                logger.info(msg)
                return msg

        # ---- No unsent contacts ----
        if not self.data_handler.has_unsent():
            msg = "No unsent contacts remaining."
            logger.info(msg)
            return msg

        # ---- Send next email ----
        self._send_next()
        self._last_send_time = now
        
        msg = f"Email sent to next contact. Total today: {self._sent_today}."
        logger.info(msg)
        return msg

    def stop(self) -> None:
        """Request a graceful shutdown."""
        logger.info("Graceful shutdown requested.")
        self.should_stop = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_next(self) -> None:
        """Fetch the next unsent contact and attempt to send an email."""
        contact = self.data_handler.get_next_unsent()
        if contact is None:
            return

        email = str(contact.get("Email", "")).strip()
        name = str(contact.get("ContactName", "Hiring Manager")).strip()
        company = str(contact.get("Company", "")).strip()
        position = str(contact.get("Position", "")).strip()

        logger.info(f"Sending email to {email} ({name} at {company})")

        success = self.email_sender.send_email(
            recipient_email=email,
            contact_name=name,
            company=company,
        )

        if success:
            self._sent_today += 1
            self.data_handler.mark_as_sent(email)
        else:
            self._failed_today += 1
            # Mark as sent to avoid retrying the same broken address forever
            self.data_handler.mark_as_sent(email)
            logger.warning(f"Email to {email} failed - marked to prevent retry loop.")

    def _reset_daily_counters(self, today_str: str) -> None:
        self._sent_today = 0
        self._failed_today = 0
        self._current_date = today_str
        logger.info(f"Daily counters reset for {today_str}.")

    def _end_of_day_summary(self) -> None:
        remaining = self.data_handler.count_unsent()
        generate_daily_summary(
            total_sent=self._sent_today,
            total_failed=self._failed_today,
            total_remaining=remaining,
            log_dir=self.log_dir,
        )

    def _seconds_until(self, target_hour: int) -> float:
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)
        target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    def _seconds_until_next_day_start(self) -> float:
        return self._seconds_until(self.start_hour)

    def _sleep(self, seconds: float) -> None:
        """Sleep in small increments so we can react to ``should_stop``."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self.should_stop:
            time.sleep(min(5, end - time.monotonic()))
