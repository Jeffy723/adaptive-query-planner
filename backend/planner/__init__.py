"""
backend/planner — Adaptive Execution Plan Generator & Selector.

Public API
----------
    from backend.planner import (
        # Plan Generation
        PlanGenerator,
        generate_plans,
        extract_conjuncts,
        MAX_GENERATED_PLANS,
        MAX_PERMUTATION_PREDICATES,

        # Physical Plan Nodes
        PhysicalPlan,
        PhysicalScan,
        PhysicalFilter,
        PhysicalProject,
        PhysicalSort,
        PhysicalOperation,

        # Plan Selection
        PlanSelector,
        select_plan,
        PlanSelectionResult,
        RankedPlan,
        SelectionError,
    )
"""

from .generator import (
    MAX_GENERATED_PLANS,
    MAX_PERMUTATION_PREDICATES,
    PlanGenerator,
    extract_conjuncts,
    generate_plans,
)
from .physical_nodes import (
    PhysicalFilter,
    PhysicalOperation,
    PhysicalPlan,
    PhysicalProject,
    PhysicalScan,
    PhysicalSort,
)
from .selector import (
    PlanSelectionResult,
    PlanSelector,
    RankedPlan,
    SelectionError,
    select_plan,
)

__all__ = [
    # Plan Generation
    "PlanGenerator",
    "generate_plans",
    "extract_conjuncts",
    "MAX_GENERATED_PLANS",
    "MAX_PERMUTATION_PREDICATES",
    # Physical Plan Nodes
    "PhysicalPlan",
    "PhysicalScan",
    "PhysicalFilter",
    "PhysicalProject",
    "PhysicalSort",
    "PhysicalOperation",
    # Plan Selection
    "PlanSelector",
    "select_plan",
    "PlanSelectionResult",
    "RankedPlan",
    "SelectionError",
]
