"""
backend/executor/dataset.py

CSV dataset loader and row type-converter.

This is the ONLY place in the executor that knows about CSV files and
type conversion.  All other executor modules work with plain Python dicts.

Public API
----------
    DatasetProvider(data_dir)
        .load(table_name, schema) -> list[Row]

Design
------
- Reads the CSV using the stdlib csv module (no third-party deps).
- Converts every field to the Python type declared by the schema:
      ColumnType.INTEGER -> int
      ColumnType.STRING  -> str (already the default from csv.reader)
- Raises ExecutionError on:
      * file not found
      * row with wrong number of columns
      * a value that cannot be converted to the declared type
- Does not cache — each call reads the file fresh.
  Caching can be added by the planner layer without changing this API.
"""

from __future__ import annotations

import csv
import pathlib

from backend.schema import ColumnType, TableSchema

from .errors import ExecutionError
from .result import Row


class DatasetProvider:
    """
    Loads a CSV dataset and converts it to typed Python rows.

    Parameters
    ----------
    data_dir:
        Path to the directory that contains the CSV files.
        Each table `students` is expected at `<data_dir>/students.csv`.
    """

    def __init__(self, data_dir: pathlib.Path | str | None = None) -> None:
        if data_dir is None:
            data_dir = pathlib.Path(__file__).parent.parent.parent / "data"
        self._data_dir = pathlib.Path(data_dir)

    def load(self, table_name: str, schema: TableSchema) -> list[Row]:
        """
        Read and type-convert all rows from <data_dir>/<table_name>.csv.

        Parameters
        ----------
        table_name:
            Name of the table (lower-case, no extension).
        schema:
            The TableSchema that drives column ordering and type conversion.

        Returns
        -------
        list[Row]
            Each Row is a dict[str, object] with one entry per column.

        Raises
        ------
        ExecutionError
            On any file or parsing problem.
        """
        csv_path = self._data_dir / f"{table_name}.csv"

        if not csv_path.exists():
            raise ExecutionError(
                f"Dataset file not found: {csv_path}"
            )

        rows: list[Row] = []
        try:
            with csv_path.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)

                # Validate header matches schema column names.
                if reader.fieldnames is None:
                    raise ExecutionError(
                        f"CSV file has no header row: {csv_path}"
                    )
                header = list(reader.fieldnames)
                schema_cols = schema.column_names
                if header != schema_cols:
                    raise ExecutionError(
                        f"CSV header {header} does not match "
                        f"schema columns {schema_cols} for table '{table_name}'."
                    )

                for line_num, raw_row in enumerate(reader, start=2):
                    rows.append(
                        self._convert_row(raw_row, schema, csv_path, line_num)
                    )
        except ExecutionError:
            raise
        except OSError as exc:
            raise ExecutionError(
                f"Cannot read dataset file {csv_path}: {exc}"
            ) from exc

        return rows

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_row(
        raw: dict[str, str | None],
        schema: TableSchema,
        csv_path: pathlib.Path,
        line_num: int,
    ) -> Row:
        """Convert one CSV row dict from strings to typed Python values."""
        row: Row = {}
        for col_meta in schema.columns:
            raw_value = raw.get(col_meta.name)

            if raw_value is None or raw_value == "":
                if not col_meta.nullable:
                    raise ExecutionError(
                        f"Missing value for non-nullable column "
                        f"'{col_meta.name}' at {csv_path}:{line_num}."
                    )
                row[col_meta.name] = None
                continue

            if col_meta.col_type == ColumnType.INTEGER:
                try:
                    row[col_meta.name] = int(raw_value)
                except ValueError:
                    raise ExecutionError(
                        f"Cannot convert value {raw_value!r} to INTEGER "
                        f"for column '{col_meta.name}' at {csv_path}:{line_num}."
                    ) from None
            else:
                # ColumnType.STRING — csv.DictReader already returns str
                row[col_meta.name] = str(raw_value)

        return row
