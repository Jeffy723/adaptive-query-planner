"""
backend/executor/engine.py

Query Executor — runs a LogicalPlan against the CSV dataset.

Public API
----------
    Executor(schema_registry, data_dir).execute(plan) -> ExecutionResult

The executor knows only about the IR node types (ScanOp, FilterOp,
ProjectOp, SortOp) and the schema.  It has NO knowledge of:
  - SQL keywords or syntax
  - Lexer tokens
  - AST node classes
  - Parser internals

Architecture
------------
Each IR operation is executed by a dedicated private method.
A running list of OperationStats is accumulated alongside the rows.

Operation pipeline (executed in the order given by LogicalPlan.operations):

    _exec_scan(op)      -> reads CSV, converts types  -> rows
    _exec_filter(op)    -> evaluates predicate         -> subset of rows
    _exec_project(op)   -> selects columns             -> projected rows
    _exec_sort(op)      -> sorts rows                  -> sorted rows

Predicate evaluation
--------------------
    _eval_predicate(pred, row) -> bool
        |
        +-- IRComparison   -> _eval_comparison(cmp, row) -> bool
        +-- IRLogicalExpr  -> _eval_logical(expr, row)   -> bool
                                  left AND|OR right (left-to-right, per spec)
"""

from __future__ import annotations

import pathlib

from backend.ir.nodes import (
    FilterOp,
    IRComparison,
    IRLiteralType,
    IRLogicalExpr,
    IRPredicate,
    LogicalPlan,
    Operation,
    ProjectOp,
    ScanOp,
    SortOp,
)
from backend.schema import SCHEMA_REGISTRY, TableSchema

from .dataset import DatasetProvider
from .errors  import ExecutionError
from .result  import ExecutionResult, OperationStats, Row

# Type alias: the schema registry dict
SchemaRegistry = dict[str, TableSchema]

# Operator dispatch table — maps operator string to a comparison function.
# Using a pre-built dict avoids a long if/elif chain in the hot evaluation path.
_OP_FUNCS: dict[str, object] = {
    "=":  lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">":  lambda a, b: a >  b,
    "<":  lambda a, b: a <  b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


class Executor:
    """
    Executes a LogicalPlan against the CSV dataset.

    Parameters
    ----------
    schema_registry:
        Maps lower-cased table names to TableSchema objects.
        The canonical registry is ``backend.schema.SCHEMA_REGISTRY``.
    data_dir:
        Path to the directory containing the CSV files.
        Defaults to the project-standard ``data/`` directory relative to
        the repository root (resolved at construction time).

    Usage
    -----
        from backend.executor import Executor
        from backend.schema   import SCHEMA_REGISTRY

        result = Executor(SCHEMA_REGISTRY).execute(plan)
        print(result.row_count, "rows")
        for row in result.rows:
            print(row)
    """

    def __init__(
        self,
        schema_registry_or_provider: SchemaRegistry | DatasetProvider | None = None,
        data_dir: pathlib.Path | str | None = None,
        *,
        schema_registry: SchemaRegistry | None = None,
        dataset_provider: DatasetProvider | None = None,
    ) -> None:
        if isinstance(schema_registry_or_provider, DatasetProvider):
            self._provider = schema_registry_or_provider
            self._registry = schema_registry or SCHEMA_REGISTRY
        else:
            self._registry = (
                schema_registry_or_provider
                if schema_registry_or_provider is not None
                else (schema_registry or SCHEMA_REGISTRY)
            )
            if dataset_provider is not None:
                self._provider = dataset_provider
            else:
                self._provider = DatasetProvider(data_dir)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, plan: LogicalPlan | object) -> ExecutionResult:
        """
        Execute *plan* and return the structured result.

        Supports LogicalPlan and PhysicalPlan (via thin adapter .to_logical()).
        The operations in plan.operations are executed in order.
        Statistics are accumulated per operation.

        Parameters
        ----------
        plan:
            A LogicalPlan produced by build_ir() or a PhysicalPlan.

        Returns
        -------
        ExecutionResult
            Contains the final rows, column list, row count, and per-op stats.

        Raises
        ------
        ExecutionError
            On any runtime problem (missing file, type error, etc.).
        """
        if hasattr(plan, "to_logical"):
            plan = plan.to_logical()

        rows:  list[Row]          = []
        stats: list[OperationStats] = []

        for i, op in enumerate(plan.operations):
            remaining_ops = list(plan.operations[i + 1:])
            rows, op_stats = self._execute_op(op, rows, remaining_ops)
            stats.append(op_stats)

        # Determine final column list from the ProjectOp.
        columns: list[str] = []
        for op in plan.operations:
            if isinstance(op, ProjectOp):
                columns = list(op.columns)
                break
        if not columns and rows:
            columns = list(rows[0].keys())

        # Final projection: ensure rows contain ONLY the requested columns in exact order
        final_rows = [
            {col: row[col] for col in columns if col in row}
            for row in rows
        ]

        return ExecutionResult(
            columns=columns,
            rows=final_rows,
            row_count=len(final_rows),
            stats=stats,
        )

    # ------------------------------------------------------------------
    # Operation dispatch
    # ------------------------------------------------------------------

    def _execute_op(
        self,
        op: Operation,
        current_rows: list[Row],
        remaining_ops: list[Operation] | None = None,
    ) -> tuple[list[Row], OperationStats]:
        """Route an operation to the appropriate handler."""
        if isinstance(op, ScanOp):
            return self._exec_scan(op)
        if isinstance(op, FilterOp):
            return self._exec_filter(op, current_rows)
        if isinstance(op, ProjectOp):
            return self._exec_project(op, current_rows, remaining_ops)
        if isinstance(op, SortOp):
            return self._exec_sort(op, current_rows)
        raise ExecutionError(  # pragma: no cover
            f"Unknown operation type: {type(op).__name__}"
        )

    # ------------------------------------------------------------------
    # SCAN
    # ------------------------------------------------------------------

    def _exec_scan(self, op: ScanOp) -> tuple[list[Row], OperationStats]:
        """
        Load all rows from the dataset identified by op.table_name.

        Type conversion (str -> int for INTEGER columns) is handled by
        DatasetProvider; this method just asks for rows.
        """
        schema = self._registry.get(op.table_name.lower())
        if schema is None:
            raise ExecutionError(
                f"SCAN: unknown table '{op.table_name}'. "
                f"Known tables: {sorted(self._registry.keys())}."
            )

        rows = self._provider.load(op.table_name, schema)
        stats = OperationStats(
            operation=str(op),
            input_rows=0,           # SCAN has no upstream
            output_rows=len(rows),
        )
        return rows, stats

    # ------------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------------

    def _exec_filter(
        self,
        op: FilterOp,
        rows: list[Row],
    ) -> tuple[list[Row], OperationStats]:
        """
        Retain only those rows for which the predicate evaluates to True.

        Predicate evaluation is left-to-right per the language spec.
        """
        result: list[Row] = []
        for row in rows:
            try:
                if self._eval_predicate(op.predicate, row):
                    result.append(row)
            except ExecutionError:
                raise
            except Exception as exc:  # pragma: no cover
                raise ExecutionError(
                    f"FILTER evaluation error: {exc}"
                ) from exc

        stats = OperationStats(
            operation=str(op),
            input_rows=len(rows),
            output_rows=len(result),
        )
        return result, stats

    # ------------------------------------------------------------------
    # PROJECT
    # ------------------------------------------------------------------

    def _exec_project(
        self,
        op: ProjectOp,
        rows: list[Row],
        remaining_ops: list[Operation] | None = None,
    ) -> tuple[list[Row], OperationStats]:
        """
        Select only the requested columns from each row.

        Column order matches op.columns (already resolved by the IR builder).
        If downstream operations (such as SortOp) require additional columns,
        those columns are retained temporarily and pruned at the end of execution.
        """
        needed_cols = list(op.columns)
        if remaining_ops:
            for next_op in remaining_ops:
                if isinstance(next_op, SortOp) and next_op.column not in needed_cols:
                    needed_cols.append(next_op.column)

        result: list[Row] = []
        for row in rows:
            projected: Row = {}
            for col in op.columns:
                if col not in row:
                    raise ExecutionError(
                        f"PROJECT: column '{col}' not found in row. "
                        f"Available columns: {list(row.keys())}."
                    )
                projected[col] = row[col]

            for extra_col in needed_cols[len(op.columns):]:
                if extra_col in row:
                    projected[extra_col] = row[extra_col]

            result.append(projected)

        stats = OperationStats(
            operation=str(op),
            input_rows=len(rows),
            output_rows=len(result),
        )
        return result, stats

    # ------------------------------------------------------------------
    # SORT
    # ------------------------------------------------------------------

    def _exec_sort(
        self,
        op: SortOp,
        rows: list[Row],
    ) -> tuple[list[Row], OperationStats]:
        """
        Sort rows by op.column in op.direction order.

        Creates a new list — does NOT mutate the input.
        The sort is stable (Python's built-in sort) so ties between rows
        that compare equal on the sort key preserve their relative order,
        making results deterministic given a fixed input order.
        """
        col       = op.column
        reverse   = (op.direction == "DESC")

        # Validate that the sort column exists in at least the first row.
        if rows and col not in rows[0]:
            raise ExecutionError(
                f"SORT: column '{col}' not found in rows. "
                f"Available columns: {list(rows[0].keys())}."
            )

        try:
            result = sorted(rows, key=lambda r: r[col], reverse=reverse)
        except TypeError as exc:
            raise ExecutionError(
                f"SORT: cannot compare values in column '{col}': {exc}"
            ) from exc

        stats = OperationStats(
            operation=str(op),
            input_rows=len(rows),
            output_rows=len(result),
        )
        return result, stats

    # ------------------------------------------------------------------
    # Predicate evaluation
    # ------------------------------------------------------------------

    def _eval_predicate(self, pred: IRPredicate, row: Row) -> bool:
        """Dispatch to the appropriate predicate evaluator."""
        if isinstance(pred, IRComparison):
            return self._eval_comparison(pred, row)
        if isinstance(pred, IRLogicalExpr):
            return self._eval_logical(pred, row)
        raise ExecutionError(  # pragma: no cover
            f"Unknown predicate type: {type(pred).__name__}"
        )

    def _eval_comparison(self, pred: IRComparison, row: Row) -> bool:
        """
        Evaluate a single comparison: row[column] op literal.

        The row value was already converted to the correct Python type
        by DatasetProvider, so int vs int and str vs str comparisons
        work correctly without further coercion here.
        """
        col_name = pred.column.name
        if col_name not in row:
            raise ExecutionError(
                f"FILTER: column '{col_name}' not found in row. "
                f"Available: {list(row.keys())}."
            )
        row_value = row[col_name]

        # Literal value is already the correct Python type (int or str).
        literal_value = pred.value.value

        op_fn = _OP_FUNCS.get(pred.operator)
        if op_fn is None:
            raise ExecutionError(  # pragma: no cover
                f"FILTER: unknown operator '{pred.operator}'."
            )
        return op_fn(row_value, literal_value)  # type: ignore[operator]

    def _eval_logical(self, pred: IRLogicalExpr, row: Row) -> bool:
        """
        Evaluate a logical AND/OR expression left-to-right.

        Short-circuits: AND stops on first False, OR stops on first True.
        This matches the language spec's left-to-right evaluation order.
        """
        left_result = self._eval_predicate(pred.left, row)

        if pred.operator == "AND":
            if not left_result:
                return False                          # short-circuit
            return self._eval_predicate(pred.right, row)

        if pred.operator == "OR":
            if left_result:
                return True                           # short-circuit
            return self._eval_predicate(pred.right, row)

        raise ExecutionError(  # pragma: no cover
            f"FILTER: unknown logical operator '{pred.operator}'."
        )
