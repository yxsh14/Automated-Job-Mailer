"""
Google Sheets handler — cloud replacement for ExcelHandler.

Reads contacts from a private Google Sheet and tracks sent emails
by writing back to the sheet. Drop-in replacement: identical public API
to ExcelHandler so main.py works without changes.

Setup:
    1. Create a Google Sheet with columns:
       Email | Company | ContactName | Position
    2. Create a Google Cloud Service Account with Sheets API enabled.
    3. Share your Google Sheet with the service account email (Editor).
    4. Set env vars:
       GOOGLE_SHEET_ID          = the long ID from the sheet URL
       GOOGLE_CREDENTIALS_JSON  = the entire service account JSON as a string
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import gspread
from gspread.exceptions import APIError
from requests.exceptions import ConnectionError as RequestsConnectionError

logger = logging.getLogger("email_automation")

# ---------------------------------------------------------------------------
# Network-resilient helper
# ---------------------------------------------------------------------------
_RETRYABLE_ERRORS = (
    RequestsConnectionError,
    APIError,
    TimeoutError,
    OSError,
)


def _sheets_retry(fn, *args, max_retries: int = 5, base_delay: float = 3.0, **kwargs):
    """
    Call ``fn(*args, **kwargs)``, retrying up to ``max_retries`` times on
    transient network / Google API errors with exponential backoff.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except _RETRYABLE_ERRORS as exc:
            if attempt == max_retries:
                logger.error(
                    f"Google Sheets call failed after {max_retries} attempts: {exc}"
                )
                raise
            delay = base_delay * (2 ** (attempt - 1))  # 3s, 6s, 12s, 24s …
            logger.warning(
                f"Google Sheets connection error (attempt {attempt}/{max_retries}): {exc}. "
                f"Retrying in {delay:.0f}s…"
            )
            time.sleep(delay)

# Column aliases — same flexible mapping as ExcelHandler
COLUMN_ALIASES: Dict[str, List[str]] = {
    "ContactName": ["ContactName", "Name", "contact_name", "Full Name", "FullName"],
    "Position":    ["Position", "Title", "Role", "Job Title", "JobTitle"],
    "Company":     ["Company", "Organization", "Org"],
    "Email":       ["Email", "Email Address", "EmailAddress", "email"],
}


class SheetsHandler:
    """Reads and updates a private Google Sheet as the contacts database."""

    def __init__(self, sheet_id: str, credentials_json: str) -> None:
        """
        Args:
            sheet_id: The Google Sheet ID (from the URL).
            credentials_json: The service account JSON key as a string.
        """
        self.sheet_id = sheet_id
        
        # Robust JSON parsing to handle potential .env wrapping/escaping issues
        cleaned_json = credentials_json.strip()
        if (cleaned_json.startswith("'") and cleaned_json.endswith("'")) or \
           (cleaned_json.startswith('"') and cleaned_json.endswith('"')):
            cleaned_json = cleaned_json[1:-1]
        
        try:
            self._creds_dict: Dict[str, Any] = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            # Try one more time by unescaping if it looks like it was double-escaped
            try:
                self._creds_dict = json.loads(cleaned_json.encode().decode('unicode_escape'))
            except Exception:
                raise ValueError(
                    f"Failed to parse GOOGLE_CREDENTIALS_JSON. Error: {e}. "
                    "Ensure the JSON is a valid string in your .env file. "
                    "Try wrapping it in single quotes: GOOGLE_CREDENTIALS_JSON='{...}'"
                ) from e

        self._client: Optional[gspread.Client] = None
        self._worksheet: Optional[gspread.Worksheet] = None
        self._headers: List[str] = []

    # ------------------------------------------------------------------
    # Public API (matches ExcelHandler exactly)
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Connect to Google Sheets and load the first worksheet."""
        # gspread 6.x: service_account_from_dict handles auth + default scopes
        self._client = gspread.service_account_from_dict(self._creds_dict)

        spreadsheet = self._client.open_by_key(self.sheet_id)
        self._worksheet = spreadsheet.sheet1

        # Fetch headers, resolve aliases, ensure tracking columns
        self._headers = self._worksheet.row_values(1)
        self._resolve_column_aliases()
        self._ensure_tracking_columns()

        logger.info(
            f"Connected to Google Sheet '{spreadsheet.title}' | "
            f"{self.count_unsent()} unsent contacts"
        )

    def validate(self) -> bool:
        """Validate required columns exist."""
        self._ensure_loaded()
        missing = {"Email", "Company"} - set(self._headers)
        if missing:
            raise ValueError(
                f"Sheet is missing required columns: {missing}. "
                f"Found: {self._headers}"
            )
        logger.info("Google Sheet validation passed.")
        return True

    def get_next_unsent(self) -> Optional[Dict[str, Any]]:
        """Return the first row where Sent != TRUE, or None."""
        self._ensure_loaded()
        records = _sheets_retry(self._worksheet.get_all_records)
        for record in records:
            sent_val = str(record.get("Sent", "")).strip().upper()
            if sent_val != "TRUE":
                return record
        return None

    def mark_as_sent(self, email: str) -> None:
        """Find the row by email and write TRUE + timestamp."""
        self._ensure_loaded()
        email_col = self._col_index("Email")
        sent_col  = self._col_index("Sent")
        date_col  = self._col_index("SentDate")

        col_values = _sheets_retry(self._worksheet.col_values, email_col)
        for row_idx, cell_email in enumerate(col_values, start=1):
            if cell_email.strip().lower() == email.strip().lower() and row_idx > 1:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _sheets_retry(self._worksheet.update_cell, row_idx, sent_col, "TRUE")
                _sheets_retry(self._worksheet.update_cell, row_idx, date_col, now)
                logger.info(f"Marked {email} as sent in Google Sheet at {now}")
                return

        logger.warning(f"Email {email} not found in sheet -- cannot mark as sent.")

    def has_unsent(self) -> bool:
        """Return True if any unsent contacts remain."""
        return self.count_unsent() > 0

    def count_unsent(self) -> int:
        """Count rows where Sent != TRUE."""
        self._ensure_loaded()
        records = _sheets_retry(self._worksheet.get_all_records)
        return sum(
            1 for r in records
            if str(r.get("Sent", "")).strip().upper() != "TRUE"
        )

    def count_sent(self) -> int:
        """Count rows where Sent == TRUE."""
        self._ensure_loaded()
        records = _sheets_retry(self._worksheet.get_all_records)
        return sum(
            1 for r in records
            if str(r.get("Sent", "")).strip().upper() == "TRUE"
        )

    def total_contacts(self) -> int:
        """Total number of data rows (excluding header)."""
        self._ensure_loaded()
        return len(_sheets_retry(self._worksheet.get_all_records))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._worksheet is None:
            self.load()

    def _col_index(self, col_name: str) -> int:
        """Return 1-based column index for a header name."""
        if col_name not in self._headers:
            raise ValueError(f"Column '{col_name}' not found in sheet headers: {self._headers}")
        return self._headers.index(col_name) + 1

    def _resolve_column_aliases(self) -> None:
        """Rename aliased headers to canonical names (updates sheet header row)."""
        updates: Dict[int, str] = {}
        for canonical, aliases in COLUMN_ALIASES.items():
            if canonical in self._headers:
                continue
            for alias in aliases:
                if alias in self._headers:
                    idx = self._headers.index(alias)
                    self._headers[idx] = canonical
                    updates[idx + 1] = canonical  # 1-based for Sheets API
                    logger.info(f"Column alias resolved: '{alias}' -> '{canonical}'")
                    break
        if updates:
            for col_idx, new_name in updates.items():
                self._worksheet.update_cell(1, col_idx, new_name)

    def _ensure_tracking_columns(self) -> None:
        """Add Sent / SentDate columns to the sheet if they don't exist."""
        for col_name in ("Sent", "SentDate"):
            if col_name not in self._headers:
                self._headers.append(col_name)
                col_idx = len(self._headers)
                self._worksheet.update_cell(1, col_idx, col_name)
                logger.info(f"Added '{col_name}' column to sheet at column {col_idx}.")
