"""
backend/schema.py

Canonical data-model definitions for the Adaptive Query Execution Planner.

These types are used across all pipeline stages (semantic analyser, IR,
planner, executor).  They are intentionally simple dataclasses — no ORM,
no DB-server, no external dependencies.

Hierarchy
---------
    ColumnType          enum of supported column value types
    ColumnMeta          metadata about a single column in a table
    TableSchema         ordered collection of ColumnMeta for one table
    STUDENTS_SCHEMA     the authoritative schema for data/students.csv
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Sequence


# ---------------------------------------------------------------------------
# Column type enumeration
# ---------------------------------------------------------------------------

class ColumnType(Enum):
    """
    Value types that the mini query language understands.

    Only INTEGER and STRING are supported.  Floating-point, boolean, and
    NULL types are explicitly excluded from the current language version.
    """
    INTEGER = auto()
    STRING = auto()


# ---------------------------------------------------------------------------
# Column metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnMeta:
    """
    Metadata for a single column in a table.

    Attributes
    ----------
    name:
        Column name as it appears in the CSV header and in queries.
    col_type:
        The ColumnType of values stored in this column.
    nullable:
        Whether the column can contain empty/missing values.
        Always False for the initial dataset; NULL is not supported by the
        query language.
    description:
        Human-readable description (used in docs and error messages).
    """
    name: str
    col_type: ColumnType
    nullable: bool = False
    description: str = ""

    def __str__(self) -> str:
        return f"{self.name} ({self.col_type.name})"


# ---------------------------------------------------------------------------
# Table schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TableSchema:
    """
    Schema for a single table (one CSV file).

    Attributes
    ----------
    table_name:
        The name used to reference this table in queries (e.g. 'students').
    columns:
        Ordered sequence of ColumnMeta, matching CSV column order.
    """
    table_name: str
    columns: tuple[ColumnMeta, ...]

    # Convenience helpers -------------------------------------------------------

    @property
    def column_names(self) -> list[str]:
        """Return column names in declaration order."""
        return [c.name for c in self.columns]

    def get_column(self, name: str) -> ColumnMeta | None:
        """Return the ColumnMeta for *name*, or None if not found."""
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def has_column(self, name: str) -> bool:
        """Return True if *name* is a column in this schema."""
        return self.get_column(name) is not None

    def __str__(self) -> str:
        cols = ", ".join(str(c) for c in self.columns)
        return f"TableSchema({self.table_name}: [{cols}])"


# ---------------------------------------------------------------------------
# Authoritative schema for data/students.csv
# ---------------------------------------------------------------------------

STUDENTS_SCHEMA = TableSchema(
    table_name="students",
    columns=(
        ColumnMeta(
            name="id",
            col_type=ColumnType.INTEGER,
            description="Unique student identifier (1-based sequential)",
        ),
        ColumnMeta(
            name="name",
            col_type=ColumnType.STRING,
            description="Full name of the student",
        ),
        ColumnMeta(
            name="department",
            col_type=ColumnType.STRING,
            description="Department code: one of CSE, ECE, ME, CE, IT",
        ),
        ColumnMeta(
            name="semester",
            col_type=ColumnType.INTEGER,
            description="Current semester (1 through 8 inclusive)",
        ),
        ColumnMeta(
            name="marks",
            col_type=ColumnType.INTEGER,
            description="Total marks scored (40 through 100 inclusive)",
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry: all known schemas (single-table for now)
# ---------------------------------------------------------------------------

#: Maps lower-cased table name -> TableSchema.
#: Extend this dict as new tables/CSV files are added.
SCHEMA_REGISTRY: dict[str, TableSchema] = {
    STUDENTS_SCHEMA.table_name: STUDENTS_SCHEMA,
}


def get_schema(table_name: str) -> TableSchema | None:
    """
    Look up a TableSchema by table name (case-insensitive).

    Returns None if the table is not registered.
    """
    return SCHEMA_REGISTRY.get(table_name.lower())
