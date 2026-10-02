"""
backend/cost/estimator.py

Cost Estimator — estimates the logical processing cost of physical execution plans.

Mathematical Model
------------------
1. SCAN:
     input_rows  = 0
     output_rows = N_table
     cost        = N_table

2. FILTER:
     input_rows  = N_in
     selectivity = (matching rows in table) / N_table
     output_rows = round(N_in * selectivity)  (or 0 if N_in == 0 or selectivity == 0.0)
     cost        = N_in  (number of rows inspected by the filter)

3. PROJECT:
     input_rows  = N_in
     output_rows = N_in
     cost        = N_in  (number of rows projected)

4. SORT:
     input_rows  = N_in
     output_rows = N_in
     cost        = N_in * log2(N_in)  (if N_in > 1, else 0.0)

Total Plan Cost:
     Total Cost = Sum(operation_costs)
"""

from __future__ import annotations

import math
import pathlib
from typing import Sequence

from backend.executor.dataset import DatasetProvider
from backend.planner.physical_nodes import (
    PhysicalFilter,
    PhysicalOperation,
    PhysicalPlan,
    PhysicalProject,
    PhysicalScan,
    PhysicalSort,
)
from backend.schema import TableSchema

from .model import OperationCostEstimate, PlanCostEstimate
from .stats import DatasetStatistics


class CostEstimator:
    """
    Estimates the processing costs of PhysicalPlan instances using dataset statistics.

    Parameters
    ----------
    stats:
        Optional DatasetStatistics instance. If not provided, one will be created.
    schema_registry:
        Optional schema registry mapping table names to TableSchema.
    data_dir:
        Optional path to CSV dataset directory.
    dataset_provider:
        Optional DatasetProvider instance.
    """

    def __init__(
        self,
        stats: DatasetStatistics | None = None,
        schema_registry: dict[str, TableSchema] | None = None,
        data_dir: pathlib.Path | str | None = None,
        *,
        dataset_provider: DatasetProvider | None = None,
        adaptive_store: object | None = None,
    ) -> None:
        if stats is not None:
            self._stats = stats
        else:
            self._stats = DatasetStatistics(
                schema_registry=schema_registry,
                data_dir=data_dir,
                dataset_provider=dataset_provider,
                adaptive_store=adaptive_store,
            )

    @property
    def stats(self) -> DatasetStatistics:
        """The underlying DatasetStatistics component."""
        return self._stats

    def estimate(self, plan: PhysicalPlan) -> PlanCostEstimate:
        """
        Estimate the processing cost for a single PhysicalPlan.

        Parameters
        ----------
        plan:
            The PhysicalPlan to evaluate.

        Returns
        -------
        PlanCostEstimate
            Complete structured cost report including per-operation costs
            and cardinality estimates.
        """
        table_name = plan.source_table
        current_rows: int = 0
        estimates: list[OperationCostEstimate] = []

        for op in plan.operations:
            if isinstance(op, PhysicalScan):
                table_rows = self._stats.get_row_count(table_name)
                op_cost = float(table_rows)
                estimate = OperationCostEstimate(
                    operation=str(op),
                    operation_type="SCAN",
                    input_rows=0,
                    output_rows=table_rows,
                    cost=op_cost,
                    selectivity=None,
                    description=f"Read {table_rows} rows from table '{table_name}'",
                )
                current_rows = table_rows

            elif isinstance(op, PhysicalFilter):
                input_rows = current_rows
                sel = self._stats.calculate_selectivity(table_name, op.predicate)
                if input_rows == 0 or sel == 0.0:
                    output_rows = 0
                else:
                    output_rows = max(1, round(input_rows * sel))
                op_cost = float(input_rows)

                estimate = OperationCostEstimate(
                    operation=str(op),
                    operation_type="FILTER",
                    input_rows=input_rows,
                    output_rows=output_rows,
                    cost=op_cost,
                    selectivity=sel,
                    description=f"Examine {input_rows} rows with selectivity {sel:.4f}",
                )
                current_rows = output_rows

            elif isinstance(op, PhysicalProject):
                input_rows = current_rows
                output_rows = current_rows
                op_cost = float(input_rows)
                estimate = OperationCostEstimate(
                    operation=str(op),
                    operation_type="PROJECT",
                    input_rows=input_rows,
                    output_rows=output_rows,
                    cost=op_cost,
                    selectivity=None,
                    description=f"Project columns: {', '.join(op.columns)}",
                )
                current_rows = output_rows

            elif isinstance(op, PhysicalSort):
                input_rows = current_rows
                output_rows = current_rows
                if input_rows > 1:
                    op_cost = round(input_rows * math.log2(input_rows), 2)
                else:
                    op_cost = 0.0

                estimate = OperationCostEstimate(
                    operation=str(op),
                    operation_type="SORT",
                    input_rows=input_rows,
                    output_rows=output_rows,
                    cost=op_cost,
                    selectivity=None,
                    description=f"Sort {input_rows} rows by {op.column} {op.direction}",
                )
                current_rows = output_rows

            else:
                raise ValueError(f"Unknown physical operation: {type(op).__name__}")

            estimates.append(estimate)

        total_cost = round(sum(e.cost for e in estimates), 2)

        return PlanCostEstimate(
            plan_id=plan.plan_id,
            total_cost=total_cost,
            operation_estimates=tuple(estimates),
            metadata={
                "plan_id": plan.plan_id,
                "source_table": table_name,
                "operation_count": len(estimates),
                "final_estimated_rows": current_rows,
                "original_plan_description": plan.description,
            },
        )

    def estimate_all(self, plans: Sequence[PhysicalPlan]) -> list[PlanCostEstimate]:
        """
        Estimate costs for a list of candidate physical plans.

        Parameters
        ----------
        plans:
            Sequence of PhysicalPlan instances.

        Returns
        -------
        list[PlanCostEstimate]
            List of cost estimates corresponding to each input plan.
        """
        return [self.estimate(plan) for plan in plans]


# ---------------------------------------------------------------------------
# Public functional helpers
# ---------------------------------------------------------------------------

def estimate_plan_cost(
    plan: PhysicalPlan,
    estimator: CostEstimator | None = None,
) -> PlanCostEstimate:
    """Convenience function to estimate cost for a single PhysicalPlan."""
    est = estimator or CostEstimator()
    return est.estimate(plan)


def estimate_plans_costs(
    plans: Sequence[PhysicalPlan],
    estimator: CostEstimator | None = None,
) -> list[PlanCostEstimate]:
    """Convenience function to estimate costs for multiple physical plans."""
    est = estimator or CostEstimator()
    return est.estimate_all(plans)
