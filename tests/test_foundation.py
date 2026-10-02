"""
tests/test_foundation.py

Smoke tests that verify the project foundation is importable and
the entry-point function runs without errors.
These tests contain no logic that depends on query-processing code.
"""

import importlib
import io
import sys

import pytest


# ---------------------------------------------------------------------------
# 1. Package-import tests
# ---------------------------------------------------------------------------

PACKAGES = [
    "backend",
    "backend.lexer",
    "backend.parser",
    "backend.semantic",
    "backend.ir",
    "backend.planner",
    "backend.cost",
    "backend.executor",
]


@pytest.mark.parametrize("package", PACKAGES)
def test_package_importable(package: str) -> None:
    """Every backend sub-package must be importable without errors."""
    mod = importlib.import_module(package)
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Entry-point smoke test
# ---------------------------------------------------------------------------

def test_main_runs_without_error(capsys: pytest.CaptureFixture) -> None:
    """backend.main.main() must execute successfully and print a banner."""
    from backend.main import main

    main()

    captured = capsys.readouterr()
    assert "Adaptive Query Execution Planner" in captured.out
    assert "foundation ready" in captured.out


# ---------------------------------------------------------------------------
# 3. Dataset sanity check
# ---------------------------------------------------------------------------

def test_sample_dataset_exists() -> None:
    """The sample CSV dataset must exist and have at least one data row."""
    import csv
    from pathlib import Path

    REQUIRED_COLUMNS = ["id", "name", "department", "semester", "marks"]

    csv_path = Path(__file__).parent.parent / "data" / "students.csv"
    assert csv_path.exists(), f"Dataset not found at {csv_path}"

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert len(rows) >= 100, f"Expected at least 100 rows, got {len(rows)}"
    for col in REQUIRED_COLUMNS:
        assert col in rows[0], f"Expected column '{col}' in students.csv"
