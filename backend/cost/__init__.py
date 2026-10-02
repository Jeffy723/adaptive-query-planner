"""
backend/cost — Cost Estimator for Physical Execution Plans.

Public API
----------
    from backend.cost import (
        CostEstimator,
        estimate_plan_cost,
        estimate_plans_costs,
        PlanCostEstimate,
        OperationCostEstimate,
        DatasetStatistics,
    )

    estimator = CostEstimator()
    for plan in candidate_plans:
        cost_report = estimator.estimate(plan)
        print(cost_report.explain())
"""

from .estimator import (
    CostEstimator,
    estimate_plan_cost,
    estimate_plans_costs,
)
from .model import (
    OperationCostEstimate,
    PlanCostEstimate,
)
from .stats import (
    DatasetStatistics,
    eval_predicate,
)

__all__ = [
    "CostEstimator",
    "estimate_plan_cost",
    "estimate_plans_costs",
    "PlanCostEstimate",
    "OperationCostEstimate",
    "DatasetStatistics",
    "eval_predicate",
]
