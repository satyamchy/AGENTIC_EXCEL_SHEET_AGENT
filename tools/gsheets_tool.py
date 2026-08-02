"""
Tool: create a Google Sheet and import the same CSV data into it,
using the Google Sheets API (via gspread + a service account).
"""
import csv
from pathlib import Path

import gspread
from langchain_core.tools import tool

from config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHARE_WITH_EMAIL
from tools.common import get_logger, progress, retry

log = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_client():
    import gspread
    from google.oauth2.service_account import Credentials

    if not Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists():
        raise FileNotFoundError(
            f"Google service account file not found at {GOOGLE_SERVICE_ACCOUNT_FILE}. "
            "See README for setup instructions."
        )
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


@tool
@retry()
def import_csv_to_google_sheets(csv_path: str, sheet_title: str = "Employee Data") -> dict:
    """Create a Google Sheet and import the CSV data into it via the Sheets API.

    Authenticates with a service account (see GOOGLE_SERVICE_ACCOUNT_FILE in
    config/.env), creates a new spreadsheet, writes the CSV rows into it,
    and optionally shares it with GOOGLE_SHARE_WITH_EMAIL so a human can
    view it (service-account-created files aren't visible in a normal
    Google Drive UI unless shared).

    Args:
        csv_path: path to the CSV file previously generated.
        sheet_title: title for the new Google Sheet.

    Returns:
        dict with success flag, spreadsheet_url, spreadsheet_id, and rows_imported.
    """
    src = Path(csv_path)
    if not src.exists():
        return {"success": False, "error": f"CSV not found at {csv_path}"}

    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    try:
        client = _get_client()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Google auth failed: {exc}"}

    try:
        progress("Authenticated with Google Sheets API")
        progress(f"Creating Google Sheet '{sheet_title}'...")
        spreadsheet = client.create(sheet_title)
        worksheet = spreadsheet.sheet1

        progress(f"Uploading {len(rows) - 1} data rows to Google Sheets...")
        worksheet.update(range_name="A1", values=rows)

        if GOOGLE_SHARE_WITH_EMAIL:
            spreadsheet.share(GOOGLE_SHARE_WITH_EMAIL, perm_type="user", role="writer")
            progress(f"Shared sheet with {GOOGLE_SHARE_WITH_EMAIL}")
    except gspread.exceptions.APIError as exc:
        message = str(exc)
        retryable = not ("403" in message and "quota" in message.lower())
        return {
            "success": False,
            "error": f"Google Sheets API failed: {message}",
            "retryable": retryable,
        }

    url = spreadsheet.url or f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit"
    progress(f"Google Sheet ready: {url}")

    return {
        "success": True,
        "spreadsheet_url": url,
        "spreadsheet_id": spreadsheet.id,
        "rows_imported": len(rows) - 1,
    }
