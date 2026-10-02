"""
backend/planner/generator.py

Execution Plan Generator — generates semantically equivalent physical plans
from a LogicalPlan.

Optimization Strategy (Step 2 of the Adaptive Query Planner)
------------------------------------------------------------
The core adaptive optimization implemented in this stage is FILTER ORDERING:
- Extracts independent top-level conjunctive (AND) predicates from the logical
  WHERE condition.
- Generates alternative execution plans corresponding to distinct valid
  orderings of these filter predicates.
- Preserves the logical and physical semantics:
    * Non-filter operations (SCAN, PROJECT, SORT) remain in their established order.
    * OR expressions are treated as single atomic predicates and are NOT reordered.
    * Only independent top-level AND predicates are permuted.
    * All generated plans are guaranteed to be semantically equivalent to the
      original query and produce identical results.
- Bounded generation:
    * N = 1  -> 1 plan
    * N = 2  -> 2 plans (both orderings)
    * N = 3  -> 6 plans (all 3! permutations)
    * N >= 4 -> bounded by MAX_GENERATED_PLANS (default 24) to avoid combinatorial explosion.
"""

from __future__ import annotations

import itertools
from typing import Sequence

from backend.ir.nodes import (
    IRLogicalExpr,
    IRPredicate,
    LogicalPlan,
)

from .physical_nodes import (
    PhysicalFilter,
    PhysicalOperation,
    PhysicalPlan,
    PhysicalProject,
    PhysicalScan,
    PhysicalSort,
)

#: Maximum number of physical plans to generate for a single query to avoid
#: factorial explosion on large predicate chains.
MAX_GENERATED_PLANS: int = 24

#: Maximum number of predicates for which exhaustive permutation is attempted.
MAX_PERMUTATION_PREDICATES: int = 4


# ---------------------------------------------------------------------------
# Predicate decomposition
# ---------------------------------------------------------------------------

def extract_conjuncts(predicate: IRPredicate) -> list[IRPredicate]:
    """
    Extract independent top-level conjunctive (AND) predicates from a condition tree.

    Recursively splits on top-level AND operators.
    OR expressions and atomic comparison expressions are kept intact as single
    atomic predicate units to preserve semantic correctness.

    Parameters
    ----------
    predicate:
        The root IRPredicate tree from a FilterOp.

    Returns
    -------
    list[IRPredicate]
        List of independent conjunctive predicates.

    Examples
    --------
    marks > 80
        -> [marks > 80]

    department = 'CSE' AND marks > 80
        -> [department = 'CSE', marks > 80]

    semester = 3 AND marks >= 70 AND marks <= 90
        -> [semester = 3, marks >= 70, marks <= 90]

    department = 'CSE' OR marks > 80
        -> [(department = 'CSE' OR marks > 80)]  (not split!)

    (marks > 80 OR department = 'CSE') AND semester = 5
        -> [(marks > 80 OR department = 'CSE'), semester = 5]
    """
    if isinstance(predicate, IRLogicalExpr) and predicate.operator == "AND":
        return extract_conjuncts(predicate.left) + extract_conjuncts(predicate.right)
    return [predicate]


# ---------------------------------------------------------------------------
# Plan Generator
# ---------------------------------------------------------------------------

class PlanGenerator:
    """
    Generates alternative physical execution plans from a LogicalPlan.

    Parameters
    ----------
    max_plans:
        Maximum number of alternative plans to generate (default 24).
    """

    def __init__(self, max_plans: int = MAX_GENERATED_PLANS) -> None:
        self.max_plans = max_plans

    def generate(self, logical_plan: LogicalPlan) -> list[PhysicalPlan]:
        """
        Generate all valid, semantically equivalent physical execution plans
        for the given *logical_plan*.

        Parameters
        ----------
        logical_plan:
            The input LogicalPlan produced by build_ir().

        Returns
        -------
        list[PhysicalPlan]
            List of generated physical plans, ordered deterministically
            starting with Plan A (the original query ordering).
        """
        source_table = logical_plan.source_table
        project_cols = logical_plan.project.columns
        sort_op = logical_plan.sort

        # Base non-filter physical operations
        scan = PhysicalScan(table_name=source_table)
        project = PhysicalProject(columns=project_cols)
        sort = PhysicalSort(column=sort_op.column, direction=sort_op.direction) if sort_op else None

        # Case 1: No WHERE clause -> Exactly one plan
        if logical_plan.filter is None:
            ops: list[PhysicalOperation] = [scan, project]
            if sort:
                ops.append(sort)
            return [
                PhysicalPlan(
                    plan_id="plan_A",
                    operations=tuple(ops),
                    source_table=source_table,
                    filter_order=(),
                    description="Unfiltered scan and project",
                    metadata={
                        "plan_id": "plan_A",
                        "filter_count": 0,
                        "filter_order": [],
                        "source_table": source_table,
                        "has_sort": sort is not None,
                    },
                )
            ]

        # Case 2: Extract top-level conjunctive predicates
        conjuncts = extract_conjuncts(logical_plan.filter.predicate)

        # Case 3: Exactly one filter predicate (or an indivisible OR expression)
        if len(conjuncts) <= 1:
            ops = [scan, PhysicalFilter(predicate=conjuncts[0]), project]
            if sort:
                ops.append(sort)
            return [
                PhysicalPlan(
                    plan_id="plan_A",
                    operations=tuple(ops),
                    source_table=source_table,
                    filter_order=tuple(conjuncts),
                    description=f"Single filter: [{conjuncts[0]}]",
                    metadata={
                        "plan_id": "plan_A",
                        "filter_count": 1,
                        "filter_order": [str(conjuncts[0])],
                        "source_table": source_table,
                        "has_sort": sort is not None,
                    },
                )
            ]

        # Case 4: Multiple independent AND predicates -> Generate filter permutations
        permutations = list(
            itertools.islice(
                itertools.permutations(conjuncts),
                self.max_plans,
            )
        )

        plans: list[PhysicalPlan] = []
        for idx, perm in enumerate(permutations):
            plan_letter = chr(65 + idx) if idx < 26 else str(idx + 1)
            plan_id = f"plan_{plan_letter}"

            plan_ops: list[PhysicalOperation] = [scan]
            for predicate in perm:
                plan_ops.append(PhysicalFilter(predicate=predicate))
            plan_ops.append(project)
            if sort:
                plan_ops.append(sort)

            filter_order_strs = [str(p) for p in perm]
            description = f"Filter order: [{', '.join(filter_order_strs)}]"

            plans.append(
                PhysicalPlan(
                    plan_id=plan_id,
                    operations=tuple(plan_ops),
                    source_table=source_table,
                    filter_order=perm,
                    description=description,
                    metadata={
                        "plan_id": plan_id,
                        "filter_count": len(perm),
                        "filter_order": filter_order_strs,
                        "source_table": source_table,
                        "has_sort": sort is not None,
                        "permutation_index": idx,
                    },
                )
            )

        return plans


# ---------------------------------------------------------------------------
# Functional public helper
# ---------------------------------------------------------------------------

def generate_plans(
    logical_plan: LogicalPlan,
    max_plans: int = MAX_GENERATED_PLANS,
) -> list[PhysicalPlan]:
    """
    Convenience function to generate physical plans from a LogicalPlan.

    Usage
    -----
        from backend.planner import generate_plans

        plans = generate_plans(logical_plan)
        for plan in plans:
            print(plan.explain())
    """
    return PlanGenerator(max_plans=max_plans).generate(logical_plan)
