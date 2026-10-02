"""
backend/cost/model.py

Cost estimation data structures.

Defines:
- OperationCostEstimate: Per-operation cost and row estimates.
- PlanCostEstimate: Structured cost result for a complete PhysicalPlan.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OperationCostEstimate:
    """
    Cost and cardinality estimate for a single physical operation.

    Attributes
    ----------
    operation:
        Human-readable string representation of the operation.
    operation_type:
        Operation category ('SCAN', 'FILTER', 'PROJECT', 'SORT').
    input_rows:
        Estimated number of input rows processed by this operation.
    output_rows:
        Estimated number of output rows produced by this operation.
    cost:
        Estimated logical processing cost (number of rows examined / processed,
        plus n * log2(n) for sort).
    selectivity:
        For FILTER operations, the estimated selectivity of the predicate
        (fraction between 0.0 and 1.0). None for non-filter operations.
    description:
        Optional explanatory details for display.
    """
    operation:      str
    operation_type: str
    input_rows:     int
    output_rows:    int
    cost:           float
    selectivity:    float | None = None
    description:    str          = ""

    def __str__(self) -> str:
        lines = [
            f"{self.operation}",
            f"  input:  {self.input_rows}",
            f"  output: {self.output_rows}",
        ]
        if self.selectivity is not None:
            lines.append(f"  selectivity: {self.selectivity:.4f}")
        lines.append(f"  cost:   {self.cost:.2f}")
        return "\n".join(lines)


@dataclass(frozen=True)
class PlanCostEstimate:
    """
    Structured cost estimation result for an entire PhysicalPlan.

    Attributes
    ----------
    plan_id:
        Identifier of the evaluated physical plan (e.g. 'plan_A').
    total_cost:
        Sum of all individual operation costs.
    operation_estimates:
        Tuple of OperationCostEstimate objects in pipeline execution order.
    metadata:
        Additional plan properties and statistics.
    """
    plan_id:             str
    total_cost:          float
    operation_estimates: tuple[OperationCostEstimate, ...]
    metadata:            dict[str, object] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def operation_costs(self) -> tuple[float, ...]:
        """Tuple of costs for each operation in execution order."""
        return tuple(op.cost for op in self.operation_estimates)

    @property
    def input_row_estimates(self) -> tuple[int, ...]:
        """Tuple of input row counts for each operation."""
        return tuple(op.input_rows for op in self.operation_estimates)

    @property
    def output_row_estimates(self) -> tuple[int, ...]:
        """Tuple of output row counts for each operation."""
        return tuple(op.output_rows for op in self.operation_estimates)

    @property
    def filter_selectivities(self) -> dict[str, float]:
        """Dictionary mapping filter operation text to its selectivity."""
        return {
            op.operation: op.selectivity
            for op in self.operation_estimates
            if op.selectivity is not None
        }

    def explain(self) -> str:
        """
        Return a clean human-readable multi-line cost breakdown.
        """
        lines = [f"Plan {self.plan_id} Cost Estimate:"]
        for op in self.operation_estimates:
            lines.append(f"  {op.operation}")
            lines.append(f"    input:  {op.input_rows}")
            lines.append(f"    output: {op.output_rows}")
            if op.selectivity is not None:
                lines.append(f"    selectivity: {op.selectivity:.4f}")
            lines.append(f"    cost:   {op.cost:.2f}")
        lines.append(f"Total Cost: {self.total_cost:.2f}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.explain()
