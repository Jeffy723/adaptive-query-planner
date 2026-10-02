"""
backend/executor/result.py

OperationStats and ExecutionResult — structured output of the executor.

The future cost estimator and planner read per-operation stats to reason
about how much data each logical operation processes.  Using row counts
(rather than wall-clock time) makes the metrics deterministic and
machine-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OperationStats:
    """
    Execution statistics for a single logical operation.

    Attributes
    ----------
    operation:
        Human-readable label for the operation, e.g. "SCAN students",
        "FILTER marks > 80", "PROJECT name, marks", "SORT marks DESC".
    input_rows:
        Number of rows fed into this operation.
    output_rows:
        Number of rows produced by this operation.
    """
    operation:   str
    input_rows:  int
    output_rows: int

    @property
    def operation_type(self) -> str:
        """The operation category, e.g. 'SCAN', 'FILTER', 'PROJECT', 'SORT'."""
        return self.operation.split()[0] if self.operation else ""

    def __str__(self) -> str:
        return (
            f"{self.operation}\n"
            f"  input:  {self.input_rows}\n"
            f"  output: {self.output_rows}"
        )


#: A single result row: maps column name -> Python value.
Row = dict[str, object]


@dataclass
class ExecutionResult:
    """
    The complete result of executing a LogicalPlan.

    Attributes
    ----------
    columns:
        Ordered list of column names in the result.
    rows:
        List of result rows, each a dict mapping column name -> value.
    row_count:
        Total number of rows returned (equals len(rows)).
    stats:
        Per-operation execution statistics in pipeline order.
        Consumed by the future cost estimator and planner.
    """
    columns:   list[str]
    rows:      list[Row]
    row_count: int
    stats:     list[OperationStats] = field(default_factory=list)

    def explain_stats(self) -> str:
        """
        Return a human-readable summary of the per-operation statistics.

        Example output::

            SCAN students
              input:  0
              output: 200
            FILTER (department = 'CSE' AND marks > 80)
              input:  200
              output: 18
            PROJECT name, marks
              input:  18
              output: 18
            SORT marks DESC
              input:  18
              output: 18
        """
        return "\n".join(str(s) for s in self.stats)

    def __str__(self) -> str:
        col_line  = ", ".join(self.columns)
        row_lines = "\n".join(
            "  " + ", ".join(str(row.get(c, "")) for c in self.columns)
            for row in self.rows
        )
        return (
            f"ExecutionResult({self.row_count} rows)\n"
            f"  columns: {col_line}\n"
            f"{row_lines}"
        )
