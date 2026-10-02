"""
backend/feedback/collector.py

Feedback Collector — compares estimated operation statistics with actual
runtime execution statistics to generate structured feedback reports.
"""

from __future__ import annotations

from typing import Sequence

from backend.cost.model import OperationCostEstimate, PlanCostEstimate
from backend.executor.result import ExecutionResult, OperationStats

from .model import ExecutionFeedback, OperationFeedback, SelectivityFeedback

DEFAULT_ALPHA: float = 0.5


class FeedbackCollector:
    """
    Compares cost model estimates with actual runtime statistics from the executor.

    Parameters
    ----------
    alpha:
        Smoothing weight for adaptive selectivity updates (default 0.5).
        updated = alpha * observed + (1 - alpha) * previous.
    """

    def __init__(self, alpha: float = DEFAULT_ALPHA) -> None:
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"Alpha smoothing parameter must be between 0.0 and 1.0, got {alpha}.")
        self.alpha = alpha

    def collect(
        self,
        cost_estimate: PlanCostEstimate | None,
        execution_result: ExecutionResult,
        query: str = "",
    ) -> ExecutionFeedback:
        """
        Produce structured feedback comparing *cost_estimate* against *execution_result*.

        Parameters
        ----------
        cost_estimate:
            PlanCostEstimate computed before query execution. If None,
            produces an empty feedback summary.
        execution_result:
            Actual ExecutionResult returned by the Executor.
        query:
            Optional original query text.

        Returns
        -------
        ExecutionFeedback
            Structured report with per-operation comparisons and errors.
        """
        if cost_estimate is None:
            return ExecutionFeedback(
                query=query,
                selected_plan_id="unknown",
                total_estimated_cost=0.0,
                operation_feedback=(),
                metadata={"status": "no_cost_estimate"},
            )

        op_feedbacks: list[OperationFeedback] = []
        est_ops = cost_estimate.operation_estimates
        act_ops = execution_result.stats

        # Match corresponding operations by position
        for i in range(min(len(est_ops), len(act_ops))):
            e_op: OperationCostEstimate = est_ops[i]
            a_op: OperationStats = act_ops[i]

            diff = a_op.output_rows - e_op.output_rows
            abs_err = abs(diff)

            # Calculate relative error safely
            if a_op.output_rows > 0:
                rel_err = abs_err / float(a_op.output_rows)
            else:
                rel_err = 0.0 if e_op.output_rows == 0 else 1.0

            # Filter selectivity learning
            sel_feedback: SelectivityFeedback | None = None
            if e_op.operation_type == "FILTER":
                prev_sel = e_op.selectivity if e_op.selectivity is not None else 0.0
                obs_sel = (
                    float(a_op.output_rows) / float(a_op.input_rows)
                    if a_op.input_rows > 0
                    else 0.0
                )
                updated_sel = (self.alpha * obs_sel) + ((1.0 - self.alpha) * prev_sel)

                sel_feedback = SelectivityFeedback(
                    predicate=e_op.operation,
                    previous_selectivity=prev_sel,
                    observed_selectivity=obs_sel,
                    updated_selectivity=updated_sel,
                    alpha=self.alpha,
                )

            op_feedbacks.append(
                OperationFeedback(
                    operation=e_op.operation,
                    operation_type=e_op.operation_type,
                    estimated_input_rows=e_op.input_rows,
                    actual_input_rows=a_op.input_rows,
                    estimated_output_rows=e_op.output_rows,
                    actual_output_rows=a_op.output_rows,
                    difference=diff,
                    absolute_error=abs_err,
                    relative_error=rel_err,
                    selectivity_feedback=sel_feedback,
                )
            )

        return ExecutionFeedback(
            query=query,
            selected_plan_id=cost_estimate.plan_id,
            total_estimated_cost=cost_estimate.total_cost,
            operation_feedback=tuple(op_feedbacks),
            metadata={
                "operation_count": len(op_feedbacks),
                "actual_row_count": execution_result.row_count,
            },
        )


# ---------------------------------------------------------------------------
# Public functional helper
# ---------------------------------------------------------------------------

def collect_feedback(
    cost_estimate: PlanCostEstimate | None,
    execution_result: ExecutionResult,
    query: str = "",
    alpha: float = DEFAULT_ALPHA,
) -> ExecutionFeedback:
    """
    Convenience function to generate ExecutionFeedback for an execution run.

    Usage
    -----
        from backend.feedback import collect_feedback

        feedback = collect_feedback(cost_estimate, execution_result, query)
        print(feedback.explain())
    """
    return FeedbackCollector(alpha=alpha).collect(cost_estimate, execution_result, query)
