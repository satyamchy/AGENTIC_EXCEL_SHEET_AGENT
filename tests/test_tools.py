import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from tools.csv_tool import generate_employee_csv
from tools.excel_tool import import_csv_to_excel
from tools.verify_tool import verify_imports


def test_generate_employee_csv_creates_at_least_20_rows(tmp_path):
    out = tmp_path / "employees.csv"
    result = generate_employee_csv.invoke({"num_rows": 20, "output_path": str(out)})
    assert result["success"] is True
    assert result["rows_generated"] == 20
    assert out.exists()

    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 20
    assert set(rows[0].keys()) == {"Employee ID", "Name", "Department", "Email", "Salary"}


def test_generate_employee_csv_enforces_minimum_20_rows(tmp_path):
    out = tmp_path / "employees.csv"
    result = generate_employee_csv.invoke({"num_rows": 5, "output_path": str(out)})
    assert result["rows_generated"] == 20  # floor enforced


def test_import_csv_to_excel_uses_openpyxl_fallback_when_com_unavailable(tmp_path, monkeypatch):
    import tools.excel_tool as excel_tool
    monkeypatch.setattr(excel_tool, "_excel_available", lambda: False)

    csv_path = tmp_path / "employees.csv"
    generate_employee_csv.invoke({"num_rows": 20, "output_path": str(csv_path)})

    xlsx_path = tmp_path / "employees.xlsx"
    result = import_csv_to_excel.invoke({"csv_path": str(csv_path), "xlsx_path": str(xlsx_path)})

    assert result["success"] is True
    assert result["method"] == "openpyxl_fallback"
    assert xlsx_path.exists()
    assert result["rows_imported"] == 20


def test_import_csv_to_excel_missing_source_fails_gracefully(tmp_path):
    result = import_csv_to_excel.invoke(
        {"csv_path": str(tmp_path / "does_not_exist.csv"), "xlsx_path": str(tmp_path / "out.xlsx")}
    )
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_verify_imports_matches_row_counts(tmp_path, monkeypatch):
    import tools.excel_tool as excel_tool
    monkeypatch.setattr(excel_tool, "_excel_available", lambda: False)

    csv_path = tmp_path / "employees.csv"
    generate_employee_csv.invoke({"num_rows": 20, "output_path": str(csv_path)})

    xlsx_path = tmp_path / "employees.xlsx"
    import_csv_to_excel.invoke({"csv_path": str(csv_path), "xlsx_path": str(xlsx_path)})

    report = verify_imports.invoke({"csv_path": str(csv_path), "xlsx_path": str(xlsx_path)})
    assert report["success"] is True
    assert report["excel"]["verified"] is True
    assert report["excel"]["rows_found"] == 20


def test_verify_imports_rejects_placeholder_spreadsheet_id(tmp_path):
    csv_path = tmp_path / "employees.csv"
    generate_employee_csv.invoke({"num_rows": 20, "output_path": str(csv_path)})

    report = verify_imports.invoke(
        {"csv_path": str(csv_path), "spreadsheet_id": "your_spreadsheet_id"}
    )

    assert report["success"] is False
    assert report["google_sheets"]["verified"] is False
    assert "placeholder" in report["google_sheets"]["error"].lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
