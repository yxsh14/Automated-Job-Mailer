"""
Email sender with SMTP support, attachments, and retry logic.

Handles template rendering, MIME construction, SMTP connection,
and automatic retries on transient failures.
"""

import logging
import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from src.utils import validate_email, check_file_exists

logger = logging.getLogger("email_automation")


class EmailSender:
    """Constructs and sends personalized emails with attachments via SMTP."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        email_address: str,
        email_password: str,
        template_path: str | Path,
        resume_path: str | Path,
        max_retries: int = 3,
        retry_delay: int = 60,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.email_address = email_address
        self.email_password = email_password
        self.template_path = Path(template_path)
        self.resume_path = Path(resume_path)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._template: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_template(self) -> None:
        """Load the email body template from disk."""
        if not check_file_exists(self.template_path, "Email template"):
            raise FileNotFoundError(f"Template not found: {self.template_path}")
        self._template = self.template_path.read_text(encoding="utf-8")
        logger.info(f"Email template loaded from {self.template_path}")

    def send_email(
        self,
        recipient_email: str,
        contact_name: str,
        company: str,
    ) -> bool:
        """
        Send a personalized email with resume attachment.

        Subject is read from the template's own 'Subject:' line so you
        control it entirely from email_template.txt.

        Args:
            recipient_email: Destination email address.
            contact_name: Name of the contact (HR / hiring manager).
            company: Company name.

        Returns:
            True if the email was sent successfully, False otherwise.
        """
        # Validate recipient
        if not validate_email(recipient_email):
            logger.error(f"Invalid email address: {recipient_email}")
            return False

        # Ensure template loaded
        if self._template is None:
            self.load_template()

        # Extract subject from template, render body
        subject, body = self._render_template(contact_name, company)

        # Build MIME message
        msg = self._build_message(recipient_email, subject, body)

        # Send with retry
        return self._send_with_retry(msg, recipient_email)

    def send_test_email(self, test_address: str) -> bool:
        """Send a quick test email to verify SMTP credentials."""
        logger.info(f"Sending test email to {test_address}")
        return self.send_email(
            recipient_email=test_address,
            contact_name="Hiring Manager",
            company="Test Company",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_template(self, contact_name: str, company: str) -> tuple[str, str]:
        """
        Parse the template and return (subject, body) after token substitution.

        The template's first 'Subject: ...' line becomes the email subject.
        All other lines become the body. Only {contact_name} and {company}
        are substituted; any other curly-brace text is left intact.
        """
        import re

        lines = self._template.strip().split("\n")

        # Extract subject from the Subject: line
        subject = "Job Application"  # sensible default
        body_lines = []
        for line in lines:
            if line.strip().lower().startswith("subject:"):
                subject = line.strip()[len("subject:"):].strip()
            else:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()

        replacements = {
            "contact_name": contact_name,
            "company": company,
        }

        def replace_token(match: re.Match) -> str:
            key = match.group(1)
            return replacements.get(key, match.group(0))  # leave unknown tokens intact

        subject = re.sub(r"\{([^}]+)\}", replace_token, subject)
        subject = subject.strip()
        body = re.sub(r"\{([^}]+)\}", replace_token, body)
        return subject, body

    def _build_message(
        self, recipient: str, subject: str, body: str
    ) -> MIMEMultipart:
        """Construct a MIME message with optional attachment."""
        msg = MIMEMultipart()
        msg["From"] = self.email_address
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach resume if it exists
        if check_file_exists(self.resume_path, "Resume"):
            self._attach_file(msg, self.resume_path)

        return msg

    @staticmethod
    def _attach_file(msg: MIMEMultipart, file_path: Path) -> None:
        """Attach a file to the MIME message."""
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{file_path.name}"',
        )
        msg.attach(part)

    def _send_with_retry(self, msg: MIMEMultipart, recipient: str) -> bool:
        """Attempt to send the email up to max_retries times."""
        # SMTP codes that indicate a permanent failure — no point retrying
        PERMANENT_FAIL_CODES = {
            550,  # Mailbox not found / user unknown
            551,  # User not local
            552,  # Mailbox full (permanent for our purposes)
            553,  # Mailbox name not allowed
            554,  # Transaction failed / spam policy
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                # Automatic SSL/TLS detection
                if self.smtp_port == 465:
                    server_class = smtplib.SMTP_SSL
                else:
                    server_class = smtplib.SMTP

                with server_class(self.smtp_host, self.smtp_port, timeout=30) as server:
                    if self.smtp_port != 465:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                    
                    server.login(self.email_address, self.email_password)
                    server.sendmail(self.email_address, recipient, msg.as_string())

                logger.info(f"Email sent successfully to {recipient}")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(
                    f"SMTP authentication failed (attempt {attempt}/{self.max_retries}): {e}"
                )
                # Don't retry auth errors — they won't self-heal
                return False

            except smtplib.SMTPRecipientsRefused as e:
                # Parse the per-recipient error codes
                refused = e.recipients  # dict: {email: (code, msg)}
                codes = {code for code, _ in refused.values()}
                if codes & PERMANENT_FAIL_CODES:
                    logger.warning(
                        f"Permanent delivery failure for {recipient} "
                        f"(mailbox does not exist or was rejected): {refused}. Skipping."
                    )
                    return False  # Don't retry — address is invalid
                # Transient refusal — fall through to retry logic
                logger.warning(
                    f"Recipients refused for {recipient} "
                    f"(attempt {attempt}/{self.max_retries}): {refused}"
                )
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)

            except smtplib.SMTPResponseException as e:
                # Catch other numeric SMTP errors
                if e.smtp_code in PERMANENT_FAIL_CODES:
                    logger.warning(
                        f"Permanent SMTP error {e.smtp_code} for {recipient}: "
                        f"{e.smtp_error}. Skipping without retry."
                    )
                    return False
                logger.warning(
                    f"SMTP error {e.smtp_code} for {recipient} "
                    f"(attempt {attempt}/{self.max_retries}): {e.smtp_error}"
                )
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)

            except (smtplib.SMTPException, OSError) as e:
                logger.warning(
                    f"Failed to send email to {recipient} "
                    f"(attempt {attempt}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)

        logger.error(
            f"All {self.max_retries} attempts to send email to {recipient} failed."
        )
        return False
