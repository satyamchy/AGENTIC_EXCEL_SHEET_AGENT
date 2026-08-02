"""
Tool: import CSV data into an existing Google Sheet.
"""
import csv
import re
from pathlib import Path

import gspread
from langchain_core.tools import tool

from config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SHEET_LINK_PATH,
    GOOGLE_SPREADSHEET_ID,
    GOOGLE_SPREADSHEET_URL,
)
from tools.common import get_logger, progress, retry

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_client():
    from google.oauth2.service_account import Credentials

    if not Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists():
        raise FileNotFoundError(
            f"Google service account file not found at {GOOGLE_SERVICE_ACCOUNT_FILE}."
        )
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def _configured_spreadsheet_id() -> str:
    if GOOGLE_SPREADSHEET_ID:
        return GOOGLE_SPREADSHEET_ID.strip()

    if GOOGLE_SPREADSHEET_URL:
        match = re.search(r"/spreadsheets/d/([^/]+)", GOOGLE_SPREADSHEET_URL)
        if match:
            return match.group(1)

    raise ValueError(
        "Set GOOGLE_SPREADSHEET_ID or GOOGLE_SPREADSHEET_URL in .env for your existing Google Sheet."
    )


@tool
@retry()
def import_csv_to_google_sheets(csv_path: str, sheet_title: str = "Employee Data") -> dict:
    """Import CSV rows into the configured existing Google Sheet.

    The spreadsheet must already exist and must be shared with the service
    account client_email from service_account.json as an editor.
    """
    src = Path(csv_path).expanduser().resolve()
    if not src.exists():
        return {"success": False, "error": f"CSV not found at {csv_path}"}

    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    try:
        client = _get_client()
        spreadsheet_id = _configured_spreadsheet_id()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.sheet1
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Google Sheets setup failed: {exc}", "retryable": False}

    try:
        progress(f"Opening existing Google Sheet: {spreadsheet.url}")
        worksheet.clear()
        worksheet.update(range_name="A1", values=rows)
    except gspread.exceptions.APIError as exc:
        return {"success": False, "error": f"Google Sheets API failed: {exc}"}

    url = spreadsheet.url or f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit"
    GOOGLE_SHEET_LINK_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOOGLE_SHEET_LINK_PATH.write_text(url + "\n", encoding="utf-8")

    progress(f"Uploaded {len(rows) - 1} rows to Google Sheets")
    progress(f"Saved Google Sheet link to {GOOGLE_SHEET_LINK_PATH}")
    log.info("Google Sheet URL: %s", url)

    return {
        "success": True,
        "spreadsheet_url": url,
        "spreadsheet_id": spreadsheet.id,
        "spreadsheet_link_file": str(GOOGLE_SHEET_LINK_PATH),
        "rows_imported": len(rows) - 1,
    }
