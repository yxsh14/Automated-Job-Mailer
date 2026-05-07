"""
Excel handler for reading contacts and tracking sent emails.

Manages the contacts spreadsheet — reads unsent recipients, marks them
as sent with timestamps, and provides aggregate counts.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

logger = logging.getLogger("email_automation")


class ExcelHandler:
    """Reads, updates, and persists the contacts Excel workbook."""

    # Minimum required columns (flexible — aliases resolved on load)
    REQUIRED_COLUMNS = {"Email", "Company"}

    def __init__(self, excel_path: str | Path) -> None:
        """
        Args:
            excel_path: Path to the contacts .xlsx file.
        """
        self.excel_path = Path(excel_path)
        self._df: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Accepted aliases for each canonical column name
    COLUMN_ALIASES: Dict[str, list] = {
        "ContactName": ["ContactName", "Name", "contact_name", "Full Name", "FullName"],
        "Position":    ["Position", "Title", "Role", "Job Title", "JobTitle"],
        "Company":     ["Company", "Organization", "Org"],
        "Email":       ["Email", "Email Address", "EmailAddress", "email"],
    }

    def load(self) -> None:
        """Load the workbook into memory and resolve column aliases."""
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {self.excel_path}")

        self._df = pd.read_excel(self.excel_path, engine="openpyxl")
        self._resolve_column_aliases()

        # Ensure tracking columns exist — use object dtype to avoid StringDtype conflicts
        if "Sent" not in self._df.columns:
            self._df["Sent"] = ""
        self._df["Sent"] = self._df["Sent"].astype(object)
        if "SentDate" not in self._df.columns:
            self._df["SentDate"] = ""
        self._df["SentDate"] = self._df["SentDate"].astype(object)

        logger.info(
            f"Loaded {len(self._df)} contacts from {self.excel_path} "
            f"(columns: {list(self._df.columns)}) "
            f"| {self.count_unsent()} unsent"
        )

    def validate(self) -> bool:
        """
        Validate that the workbook contains the required columns.

        Returns:
            True if valid, raises ValueError otherwise.
        """
        self._ensure_loaded()
        missing = self.REQUIRED_COLUMNS - set(self._df.columns)
        if missing:
            raise ValueError(
                f"Excel file is missing required columns: {missing}. "
                f"Found columns: {list(self._df.columns)}"
            )
        logger.info("Excel file validation passed.")
        return True

    def get_next_unsent(self) -> Optional[Dict[str, Any]]:
        """
        Return the next row that has not been sent yet.

        Returns:
            A dict with keys Email, Company, ContactName, Position — or None.
        """
        self._ensure_loaded()
        unsent = self._df[
            ~(self._df["Sent"].astype(str).str.upper() == "TRUE")
        ]
        if unsent.empty:
            return None
        row = unsent.iloc[0]
        return row.to_dict()

    def mark_as_sent(self, email: str) -> None:
        """
        Mark a contact as sent by email address and persist changes.

        Args:
            email: The email address to mark.
        """
        self._ensure_loaded()
        mask = self._df["Email"].str.strip().str.lower() == email.strip().lower()
        if not mask.any():
            logger.warning(f"Email {email} not found in spreadsheet — cannot mark as sent.")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._df.loc[mask, "Sent"] = "TRUE"
        self._df.loc[mask, "SentDate"] = now
        self._save()
        logger.info(f"Marked {email} as sent at {now}")

    def has_unsent(self) -> bool:
        """Return True if there are any unsent contacts remaining."""
        self._ensure_loaded()
        return self.count_unsent() > 0

    def count_unsent(self) -> int:
        """Return the number of unsent contacts."""
        self._ensure_loaded()
        unsent = self._df[
            ~(self._df["Sent"].astype(str).str.upper() == "TRUE")
        ]
        return len(unsent)

    def count_sent(self) -> int:
        """Return the number of sent contacts."""
        self._ensure_loaded()
        return len(self._df) - self.count_unsent()

    def total_contacts(self) -> int:
        """Return total number of contacts."""
        self._ensure_loaded()
        return len(self._df)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_column_aliases(self) -> None:
        """Rename aliased columns to their canonical names."""
        rename_map: Dict[str, str] = {}
        existing = set(self._df.columns)
        for canonical, aliases in self.COLUMN_ALIASES.items():
            if canonical in existing:
                continue  # already correct
            for alias in aliases:
                if alias in existing:
                    rename_map[alias] = canonical
                    logger.info(f"Column alias resolved: '{alias}' -> '{canonical}'")
                    break
        if rename_map:
            self._df.rename(columns=rename_map, inplace=True)

    def _ensure_loaded(self) -> None:
        if self._df is None:
            self.load()

    def _save(self) -> None:
        """Persist the dataframe back to the Excel file."""
        self._df.to_excel(self.excel_path, index=False, engine="openpyxl")
        logger.debug(f"Saved workbook to {self.excel_path}")
