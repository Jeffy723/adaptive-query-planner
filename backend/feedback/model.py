"""
backend/feedback/model.py

Data structures for runtime feedback and adaptive statistics learning.

Defines:
- SelectivityFeedback: Compares estimated vs observed predicate selectivity.
- OperationFeedback: Compares estimated vs actual input/output rows for one operator.
- ExecutionFeedback: Comprehensive query-level feedback report.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SelectivityFeedback:
    """
    Selectivity comparison and learning details for a filter predicate.

    Attributes
    ----------
    predicate:
        String representation of the filter condition.
    previous_selectivity:
        The selectivity value estimated before execution.
    observed_selectivity:
        The empirical selectivity observed during execution
        (actual_output_rows / actual_input_rows).
    updated_selectivity:
        The new selectivity computed via the adaptive learning rule.
    alpha:
        The smoothing weight used for the update rule.
    """
    predicate:            str
    previous_selectivity: float
    observed_selectivity: float
    updated_selectivity:  float
    alpha:                float

    def __str__(self) -> str:
        return (
            f"Predicate: {self.predicate}\n"
            f"  Previous selectivity: {self.previous_selectivity:.4f}\n"
            f"  Observed selectivity: {self.observed_selectivity:.4f}\n"
            f"  Updated selectivity:  {self.updated_selectivity:.4f} (alpha={self.alpha:.2f})"
        )


@dataclass(frozen=True)
class OperationFeedback:
    """
    Comparison between estimated and actual statistics for a single operation.

    Attributes
    ----------
    operation:
        String description of the operation (e.g. "FILTER department = 'CSE'").
    operation_type:
        Category ("SCAN", "FILTER", "PROJECT", "SORT").
    estimated_input_rows:
        Input row count estimated by the cost model.
    actual_input_rows:
        Input row count observed during actual execution.
    estimated_output_rows:
        Output row count estimated by the cost model.
    actual_output_rows:
        Output row count observed during actual execution.
    difference:
        Signed difference (actual_output_rows - estimated_output_rows).
        Positive means actual was higher than estimate; negative means lower.
    absolute_error:
        Absolute magnitude of estimation error (|estimated_output - actual_output|).
    relative_error:
        Relative error ratio (absolute_error / max(1, actual_output_rows)).
    selectivity_feedback:
        Optional SelectivityFeedback for filter operations.
    """
    operation:             str
    operation_type:        str
    estimated_input_rows:  int
    actual_input_rows:     int
    estimated_output_rows: int
    actual_output_rows:    int
    difference:            int
    absolute_error:        int
    relative_error:        float
    selectivity_feedback:  SelectivityFeedback | None = None

    @property
    def relative_error_percentage(self) -> float:
        """Relative error formatted as a percentage."""
        return self.relative_error * 100.0

    def __str__(self) -> str:
        lines = [
            f"{self.operation} ({self.operation_type}):",
            f"  Input:  estimated={self.estimated_input_rows}, actual={self.actual_input_rows}",
            f"  Output: estimated={self.estimated_output_rows}, actual={self.actual_output_rows}",
            f"  Difference:     {self.difference:+d}",
            f"  Absolute error: {self.absolute_error}",
            f"  Relative error: {self.relative_error_percentage:.2f}%",
        ]
        if self.selectivity_feedback is not None:
            sf = self.selectivity_feedback
            lines.append(
                f"  Selectivity: estimated={sf.previous_selectivity:.4f}, "
                f"observed={sf.observed_selectivity:.4f} -> updated={sf.updated_selectivity:.4f}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class ExecutionFeedback:
    """
    Comprehensive query-level feedback report comparing cost model estimates
    with actual runtime execution metrics.

    Attributes
    ----------
    query:
        SQL-like query string.
    selected_plan_id:
        Identifier of the executed plan (e.g. 'plan_A').
    total_estimated_cost:
        Total cost computed by the cost estimator before execution.
    operation_feedback:
        Tuple of OperationFeedback entries for each stage in pipeline order.
    metadata:
        Summary metrics (average relative error, max error, total actual rows).
    """
    query:                str
    selected_plan_id:     str
    total_estimated_cost: float
    operation_feedback:   tuple[OperationFeedback, ...]
    metadata:             dict[str, object] = field(default_factory=dict)

    @property
    def total_absolute_error(self) -> int:
        """Sum of absolute output row errors across all operations."""
        return sum(op.absolute_error for op in self.operation_feedback)

    @property
    def max_absolute_error(self) -> int:
        """Maximum absolute error observed in any operation."""
        if not self.operation_feedback:
            return 0
        return max(op.absolute_error for op in self.operation_feedback)

    @property
    def average_relative_error(self) -> float:
        """Mean relative error percentage across all operations."""
        if not self.operation_feedback:
            return 0.0
        return sum(op.relative_error_percentage for op in self.operation_feedback) / len(self.operation_feedback)

    def explain(self) -> str:
        """Return a formatted, human-readable feedback and adaptation report."""
        lines = [
            "RUNTIME FEEDBACK & ADAPTATION REPORT",
            "==================================================",
            f"Plan Evaluated: {self.selected_plan_id}",
            f"Estimated Total Cost: {self.total_estimated_cost:.2f}",
            "",
            "OPERATION ACCURACY ANALYSIS:",
        ]
        for op in self.operation_feedback:
            lines.append(f"  {op.operation}")
            lines.append(f"    Estimated: input={op.estimated_input_rows}, output={op.estimated_output_rows}")
            lines.append(f"    Actual:    input={op.actual_input_rows}, output={op.actual_output_rows}")
            lines.append(f"    Feedback:  error={op.absolute_error} ({op.relative_error_percentage:.1f}%), diff={op.difference:+d}")
            if op.selectivity_feedback is not None:
                sf = op.selectivity_feedback
                lines.append(
                    f"    Learning:  prev_sel={sf.previous_selectivity:.4f}, "
                    f"observed_sel={sf.observed_selectivity:.4f} -> updated_sel={sf.updated_selectivity:.4f}"
                )
        lines.extend([
            "",
            "SUMMARY:",
            f"  Total Absolute Output Error: {self.total_absolute_error} rows",
            f"  Average Relative Error:      {self.average_relative_error:.2f}%",
            "==================================================",
        ])
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.explain()
