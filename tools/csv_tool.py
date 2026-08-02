"""
Tool: generate sample employee CSV data.
"""
import csv
import random
from pathlib import Path

from faker import Faker
from langchain_core.tools import tool

from config import DEFAULT_CSV_PATH, DEFAULT_ROW_COUNT
from tools.common import get_logger, progress, retry

log = get_logger(__name__)
fake = Faker()

DEPARTMENTS = ["Sales", "HR", "Engineering", "Marketing", "Finance", "Operations", "Support"]


@tool
@retry()
def generate_employee_csv(num_rows: int = DEFAULT_ROW_COUNT, output_path: str = "") -> dict:
    """Generate a realistic sample employee CSV file.

    Creates a CSV with columns: Employee ID, Name, Department, Email, Salary.
    Use this as the FIRST step whenever the user asks to create sample
    employee data, or to import employee data into Excel/Google Sheets.

    Args:
        num_rows: number of employee rows to generate (default 25, minimum 20
            to satisfy the "at least 20 rows" requirement).
        output_path: optional custom path for the CSV file. If empty, a
            default path under ./data/employees.csv is used.

    Returns:
        dict with success flag, csv_path, and rows_generated.
    """
    num_rows = max(num_rows, 20)
    path = Path(output_path) if output_path else DEFAULT_CSV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    progress(f"Generating {num_rows} rows of sample employee data...")

    rows = []
    for i in range(1, num_rows + 1):
        name = fake.name()
        rows.append(
            {
                "Employee ID": f"EMP{i:03d}",
                "Name": name,
                "Department": random.choice(DEPARTMENTS),
                "Email": name.lower().replace(" ", ".").replace(",", "") + "@example.com",
                "Salary": random.randint(45000, 115000),
            }
        )

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Employee ID", "Name", "Department", "Email", "Salary"])
        writer.writeheader()
        writer.writerows(rows)

    log.info("Wrote %d rows to %s", len(rows), path)
    progress(f"CSV written to {path} ({len(rows)} rows)")

    return {
        "success": True,
        "csv_path": str(path),
        "rows_generated": len(rows),
    }
