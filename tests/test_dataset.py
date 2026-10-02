"""
tests/test_dataset.py

Tests for the students dataset (data/students.csv) and the schema
definitions in backend/schema.py.

These tests do NOT perform any query execution — they only verify that
the data and the schema model are well-formed and consistent with the
language specification.
"""

import csv
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"
CSV_PATH = DATA_DIR / "students.csv"

REQUIRED_COLUMNS = ["id", "name", "department", "semester", "marks"]
VALID_DEPARTMENTS = {"CSE", "ECE", "ME", "CE", "IT"}
SEMESTER_RANGE   = range(1, 9)   # 1..8 inclusive
MARKS_RANGE      = range(40, 101) # 40..100 inclusive


def _load_csv() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# 1. File existence and basic structure
# ---------------------------------------------------------------------------

class TestDatasetFile:
    def test_csv_file_exists(self) -> None:
        assert CSV_PATH.exists(), f"Dataset not found: {CSV_PATH}"

    def test_csv_has_rows(self) -> None:
        rows = _load_csv()
        assert len(rows) >= 100, (
            f"Expected at least 100 rows for meaningful demo, got {len(rows)}"
        )

    def test_header_has_required_columns(self) -> None:
        rows = _load_csv()
        assert len(rows) > 0
        actual = list(rows[0].keys())
        for col in REQUIRED_COLUMNS:
            assert col in actual, f"Required column '{col}' missing from CSV header"

    def test_header_column_order(self) -> None:
        """Columns should appear in the canonical order defined by the spec."""
        rows = _load_csv()
        actual = list(rows[0].keys())
        assert actual == REQUIRED_COLUMNS, (
            f"Expected column order {REQUIRED_COLUMNS}, got {actual}"
        )

    def test_no_extra_columns(self) -> None:
        rows = _load_csv()
        actual = list(rows[0].keys())
        extras = set(actual) - set(REQUIRED_COLUMNS)
        assert not extras, f"Unexpected columns in CSV: {extras}"


# ---------------------------------------------------------------------------
# 2. Data-type constraints
# ---------------------------------------------------------------------------

class TestDataTypes:
    def test_id_is_integer(self) -> None:
        rows = _load_csv()
        for i, row in enumerate(rows, 1):
            assert row["id"].isdigit(), f"Row {i}: 'id' is not an integer: {row['id']!r}"

    def test_id_is_unique(self) -> None:
        rows = _load_csv()
        ids = [row["id"] for row in rows]
        assert len(ids) == len(set(ids)), "Duplicate 'id' values found in dataset"

    def test_id_is_sequential(self) -> None:
        rows = _load_csv()
        ids = [int(row["id"]) for row in rows]
        assert ids == list(range(1, len(rows) + 1)), "'id' values are not sequential starting at 1"

    def test_name_is_non_empty_string(self) -> None:
        rows = _load_csv()
        for i, row in enumerate(rows, 1):
            assert row["name"].strip() != "", f"Row {i}: 'name' is empty"

    def test_department_values(self) -> None:
        rows = _load_csv()
        for i, row in enumerate(rows, 1):
            assert row["department"] in VALID_DEPARTMENTS, (
                f"Row {i}: unexpected department {row['department']!r}"
            )

    def test_semester_is_integer_in_range(self) -> None:
        rows = _load_csv()
        for i, row in enumerate(rows, 1):
            assert row["semester"].isdigit(), f"Row {i}: 'semester' is not an integer"
            sem = int(row["semester"])
            assert sem in SEMESTER_RANGE, (
                f"Row {i}: semester {sem} out of range 1-8"
            )

    def test_marks_is_integer_in_range(self) -> None:
        rows = _load_csv()
        for i, row in enumerate(rows, 1):
            assert row["marks"].isdigit(), f"Row {i}: 'marks' is not an integer"
            m = int(row["marks"])
            assert m in MARKS_RANGE, (
                f"Row {i}: marks {m} out of range 40-100"
            )


# ---------------------------------------------------------------------------
# 3. Dataset diversity (ensures non-trivial query results)
# ---------------------------------------------------------------------------

class TestDatasetDiversity:
    def test_all_departments_represented(self) -> None:
        rows = _load_csv()
        found = {row["department"] for row in rows}
        assert found == VALID_DEPARTMENTS, (
            f"Not all departments represented. Missing: {VALID_DEPARTMENTS - found}"
        )

    def test_all_semesters_represented(self) -> None:
        rows = _load_csv()
        found = {int(row["semester"]) for row in rows}
        assert found == set(SEMESTER_RANGE), (
            f"Not all semesters represented. Missing: {set(SEMESTER_RANGE) - found}"
        )

    def test_marks_spread(self) -> None:
        """Marks should span a meaningful range (not all the same)."""
        rows = _load_csv()
        marks = [int(row["marks"]) for row in rows]
        assert max(marks) - min(marks) >= 30, (
            "Marks spread is too narrow to demonstrate meaningful filtering"
        )


# ---------------------------------------------------------------------------
# 4. Schema model tests
# ---------------------------------------------------------------------------

from backend.schema import (
    ColumnMeta,
    ColumnType,
    TableSchema,
    STUDENTS_SCHEMA,
    SCHEMA_REGISTRY,
    get_schema,
)


class TestSchemaModel:
    def test_students_schema_table_name(self) -> None:
        assert STUDENTS_SCHEMA.table_name == "students"

    def test_students_schema_column_names(self) -> None:
        assert STUDENTS_SCHEMA.column_names == REQUIRED_COLUMNS

    def test_id_column_type(self) -> None:
        col = STUDENTS_SCHEMA.get_column("id")
        assert col is not None
        assert col.col_type == ColumnType.INTEGER

    def test_name_column_type(self) -> None:
        col = STUDENTS_SCHEMA.get_column("name")
        assert col is not None
        assert col.col_type == ColumnType.STRING

    def test_department_column_type(self) -> None:
        col = STUDENTS_SCHEMA.get_column("department")
        assert col is not None
        assert col.col_type == ColumnType.STRING

    def test_semester_column_type(self) -> None:
        col = STUDENTS_SCHEMA.get_column("semester")
        assert col is not None
        assert col.col_type == ColumnType.INTEGER

    def test_marks_column_type(self) -> None:
        col = STUDENTS_SCHEMA.get_column("marks")
        assert col is not None
        assert col.col_type == ColumnType.INTEGER

    def test_schema_has_column_true(self) -> None:
        for col in REQUIRED_COLUMNS:
            assert STUDENTS_SCHEMA.has_column(col), f"has_column('{col}') returned False"

    def test_schema_has_column_false_for_unknown(self) -> None:
        assert not STUDENTS_SCHEMA.has_column("gpa")
        assert not STUDENTS_SCHEMA.has_column("grade")

    def test_get_column_returns_none_for_unknown(self) -> None:
        assert STUDENTS_SCHEMA.get_column("nonexistent") is None

    def test_no_nullable_columns_by_default(self) -> None:
        for col in STUDENTS_SCHEMA.columns:
            assert col.nullable is False, f"Column '{col.name}' should not be nullable"

    def test_schema_registry_contains_students(self) -> None:
        assert "students" in SCHEMA_REGISTRY

    def test_get_schema_case_insensitive(self) -> None:
        assert get_schema("students") is STUDENTS_SCHEMA
        assert get_schema("STUDENTS") is STUDENTS_SCHEMA
        assert get_schema("Students") is STUDENTS_SCHEMA

    def test_get_schema_unknown_returns_none(self) -> None:
        assert get_schema("courses") is None

    def test_column_meta_is_frozen(self) -> None:
        col = STUDENTS_SCHEMA.get_column("marks")
        with pytest.raises((AttributeError, TypeError)):
            col.name = "changed"  # type: ignore[misc]

    def test_table_schema_is_frozen(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            STUDENTS_SCHEMA.table_name = "changed"  # type: ignore[misc]

    def test_schema_str_representation(self) -> None:
        s = str(STUDENTS_SCHEMA)
        assert "students" in s
        assert "marks" in s


# ---------------------------------------------------------------------------
# 5. Schema-to-CSV consistency
# ---------------------------------------------------------------------------

class TestSchemaCSVConsistency:
    def test_schema_columns_match_csv_header(self) -> None:
        """The canonical schema must exactly match the CSV header."""
        rows = _load_csv()
        csv_cols = list(rows[0].keys())
        assert csv_cols == STUDENTS_SCHEMA.column_names, (
            f"CSV header {csv_cols} does not match schema {STUDENTS_SCHEMA.column_names}"
        )
