"""
backend/cost/stats.py

Dataset statistics analyzer for the cost model.

Extracts deterministic statistics directly from the dataset:
- Total row counts
- Predicate match counts and selectivity
- Distinct column values count
- Min/Max column bounds for numeric values
"""

from __future__ import annotations

import pathlib
from typing import Sequence

from backend.executor.dataset import DatasetProvider
from backend.executor.result import Row
from backend.ir.nodes import (
    IRComparison,
    IRLogicalExpr,
    IRPredicate,
)
from backend.schema import SCHEMA_REGISTRY, TableSchema


# Comparison operator dispatch functions
_OP_FUNCS = {
    "=":  lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">":  lambda a, b: a >  b,
    "<":  lambda a, b: a <  b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


def eval_predicate(pred: IRPredicate, row: Row) -> bool:
    """
    Evaluate an IRPredicate against a row dictionary.

    Supports IRComparison and IRLogicalExpr (with left-to-right evaluation).
    """
    if isinstance(pred, IRComparison):
        col_val = row.get(pred.column.name)
        lit_val = pred.value.value
        op_fn = _OP_FUNCS.get(pred.operator)
        if op_fn is None or col_val is None:
            return False
        return bool(op_fn(col_val, lit_val))

    if isinstance(pred, IRLogicalExpr):
        left_val = eval_predicate(pred.left, row)
        if pred.operator == "AND":
            if not left_val:
                return False
            return eval_predicate(pred.right, row)
        if pred.operator == "OR":
            if left_val:
                return True
            return eval_predicate(pred.right, row)

    return False


class DatasetStatistics:
    """
    Analyzes and caches table and predicate statistics from datasets.

    Parameters
    ----------
    schema_registry:
        Maps table name to TableSchema. Defaults to SCHEMA_REGISTRY.
    data_dir:
        Optional directory path containing CSV datasets.
    dataset_provider:
        Optional DatasetProvider instance to use for data loading.
    """

    def __init__(
        self,
        schema_registry: dict[str, TableSchema] | None = None,
        data_dir: pathlib.Path | str | None = None,
        *,
        dataset_provider: DatasetProvider | None = None,
        adaptive_store: object | None = None,
    ) -> None:
        self._registry = schema_registry or SCHEMA_REGISTRY
        if dataset_provider is not None:
            self._provider = dataset_provider
        else:
            self._provider = DatasetProvider(data_dir=data_dir)
        self._adaptive_store = adaptive_store

        # In-memory cache for loaded table rows: table_name -> list[Row]
        self._table_cache: dict[str, list[Row]] = {}

    def get_rows(self, table_name: str) -> list[Row]:
        """Load and cache rows for the specified table."""
        key = table_name.lower()
        if key not in self._table_cache:
            schema = self._registry.get(key)
            if schema is None:
                raise ValueError(f"Table '{table_name}' not found in schema registry.")
            self._table_cache[key] = self._provider.load(key, schema)
        return self._table_cache[key]

    def get_row_count(self, table_name: str) -> int:
        """Return the total number of rows in the table."""
        return len(self.get_rows(table_name))

    def get_matching_count(self, table_name: str, predicate: IRPredicate) -> int:
        """Return the number of rows in the table that satisfy *predicate*."""
        rows = self.get_rows(table_name)
        return sum(1 for row in rows if eval_predicate(predicate, row))

    def calculate_selectivity(self, table_name: str, predicate: IRPredicate) -> float:
        """
        Calculate the selectivity of *predicate* on *table_name*.

        If an adaptive statistics store is configured and contains a learned
        selectivity for this predicate, that learned value is returned.
        Otherwise, computes exact static selectivity from dataset inspection.

        Selectivity = (matching rows) / (total rows).
        Returns a float in the range [0.0, 1.0].
        If the table is empty, returns 0.0.
        """
        if self._adaptive_store is not None and hasattr(self._adaptive_store, "get_selectivity"):
            learned = self._adaptive_store.get_selectivity(table_name, str(predicate))
            if learned is not None:
                return float(learned)

        total = self.get_row_count(table_name)
        if total == 0:
            return 0.0
        matching = self.get_matching_count(table_name, predicate)
        return matching / total

    def get_distinct_count(self, table_name: str, column: str) -> int:
        """Return the number of distinct values for a given column."""
        rows = self.get_rows(table_name)
        return len({r.get(column) for r in rows if r.get(column) is not None})

    def get_min_max(self, table_name: str, column: str) -> tuple[object, object] | None:
        """Return (min_val, max_val) for a column, or None if no non-null values."""
        rows = self.get_rows(table_name)
        vals = [r[column] for r in rows if r.get(column) is not None]
        if not vals:
            return None
        return min(vals), max(vals)
