"""
backend/planner/selector.py

Plan Selector — chooses the optimal physical execution plan based on
estimated execution costs.

Architecture
------------
The Plan Selector is the decision-making component of the query planner.
It takes candidate physical plans and their corresponding cost estimates,
evaluates them under a deterministic cost-based policy, and returns the
winning execution plan along with full ranking metadata for debugging and UI.

Key Responsibilities:
- Input validation (validates plans, non-empty candidate lists, finite non-negative costs).
- Cost comparison (orders candidates by estimated total cost).
- Deterministic tie-breaking (resolves equal-cost ties deterministically).
- Structured result output (PlanSelectionResult with ranked candidates and rationale).

Important Separation of Concerns:
- Does NOT generate plans (done by PlanGenerator).
- Does NOT calculate costs (done by CostEstimator).
- Does NOT execute queries (done by Executor).
- Does NOT modify the AST, IR, or physical plan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from backend.cost.model import PlanCostEstimate
from backend.planner.physical_nodes import PhysicalPlan


class SelectionError(Exception):
    """
    Raised when the Plan Selector encounters invalid or inconsistent input.

    Examples:
    - Empty plan list
    - Missing cost estimate
    - Non-finite or negative cost values
    - Inconsistent plan/cost associations
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __repr__(self) -> str:  # pragma: no cover
        return f"SelectionError({self.message!r})"


@dataclass(frozen=True)
class RankedPlan:
    """
    A candidate physical plan evaluated and ranked by the Plan Selector.

    Attributes
    ----------
    rank:
        1-based rank among all evaluated candidates (1 = lowest cost).
    plan:
        The PhysicalPlan instance.
    plan_id:
        Identifier of the plan (e.g. 'plan_A').
    cost:
        Estimated total cost of the plan.
    cost_estimate:
        Full PlanCostEstimate details if available.
    """
    rank:          int
    plan:          PhysicalPlan
    plan_id:       str
    cost:          float
    cost_estimate: PlanCostEstimate | None = None

    def __str__(self) -> str:
        return f"#{self.rank} {self.plan_id:<10} cost: {self.cost:.2f}"


@dataclass(frozen=True)
class PlanSelectionResult:
    """
    Structured outcome of the plan selection process.

    Attributes
    ----------
    selected_plan:
        The winning PhysicalPlan with the lowest estimated total cost.
    selected_plan_id:
        Identifier of the selected plan.
    selected_cost:
        Estimated total cost of the selected plan.
    ranked_candidates:
        Tuple of all candidate plans ordered from lowest to highest cost.
    reason:
        Human-readable explanation of why this plan was selected.
    metadata:
        Additional metrics and properties for future UI display.
    """
    selected_plan:     PhysicalPlan
    selected_plan_id:  str
    selected_cost:     float
    ranked_candidates: tuple[RankedPlan, ...]
    reason:            str
    metadata:          dict[str, object] = field(default_factory=dict)

    def explain(self) -> str:
        """Return a formatted plan comparison report suitable for UI or console."""
        lines = [
            "PLAN COMPARISON",
            "--------------------------------------------------",
        ]
        for cand in self.ranked_candidates:
            marker = "  <-- SELECTED" if cand.plan_id == self.selected_plan_id else ""
            lines.append(f"  #{cand.rank} {cand.plan_id:<10} cost: {cand.cost:8.2f}{marker}")
        lines.append("--------------------------------------------------")
        lines.append(f"Selected Plan: {self.selected_plan_id}")
        lines.append(f"Estimated Cost: {self.selected_cost:.2f}")
        lines.append(f"Reason: {self.reason}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.explain()


class PlanSelector:
    """
    Cost-based plan selector.

    Ranks candidate physical execution plans by estimated cost and selects
    the candidate with the lowest cost. Ties are broken deterministically by
    alphabetical plan_id order.
    """

    def select(
        self,
        costed_plans_or_plans: Sequence[tuple[PhysicalPlan, PlanCostEstimate | float]] | Sequence[PhysicalPlan],
        costs: Sequence[PlanCostEstimate | float] | None = None,
    ) -> PlanSelectionResult:
        """
        Select the plan with the lowest estimated cost.

        Parameters
        ----------
        costed_plans_or_plans:
            Either:
            1. A sequence of (PhysicalPlan, PlanCostEstimate | float) tuples; OR
            2. A sequence of PhysicalPlan instances (with *costs* passed as 2nd arg).
        costs:
            Optional sequence of PlanCostEstimate or float values matching
            the plans in *costed_plans_or_plans*.

        Returns
        -------
        PlanSelectionResult
            Structured result containing the selected plan, its cost,
            and the full ranking of all candidate plans.

        Raises
        ------
        SelectionError
            On empty plan list, mismatched counts, missing costs, or invalid values.
        """
        pairs = self._normalize_inputs(costed_plans_or_plans, costs)

        if not pairs:
            raise SelectionError("Cannot select plan from an empty plan list.")

        # Validate all candidate plan/cost pairs
        validated_items: list[tuple[PhysicalPlan, float, PlanCostEstimate | None, int]] = []
        for orig_idx, (plan, cost_obj) in enumerate(pairs):
            if not isinstance(plan, PhysicalPlan):
                raise SelectionError(
                    f"Expected PhysicalPlan instance at index {orig_idx}, got {type(plan).__name__}."
                )

            if cost_obj is None:
                raise SelectionError(f"Missing cost estimate for plan '{plan.plan_id}'.")

            # Extract numerical cost and estimate object
            if isinstance(cost_obj, PlanCostEstimate):
                if cost_obj.plan_id != plan.plan_id:
                    raise SelectionError(
                        f"Inconsistent plan and cost association: plan ID '{plan.plan_id}' "
                        f"does not match cost estimate plan ID '{cost_obj.plan_id}'."
                    )
                cost_val = cost_obj.total_cost
                estimate_ref: PlanCostEstimate | None = cost_obj
            elif isinstance(cost_obj, (int, float)):
                cost_val = float(cost_obj)
                estimate_ref = None
            else:
                raise SelectionError(
                    f"Invalid cost estimate type for plan '{plan.plan_id}': {type(cost_obj).__name__}."
                )

            # Validate numerical properties
            if math.isnan(cost_val) or math.isinf(cost_val):
                raise SelectionError(
                    f"Invalid non-finite cost ({cost_val}) for plan '{plan.plan_id}'."
                )
            if cost_val < 0.0:
                raise SelectionError(
                    f"Invalid negative cost ({cost_val}) for plan '{plan.plan_id}'."
                )

            validated_items.append((plan, cost_val, estimate_ref, orig_idx))

        # Deterministic ranking:
        # 1. Primary sort key: total cost (lowest first)
        # 2. Secondary sort key: plan_id alphabetical order (deterministic tie-break)
        # 3. Tertiary sort key: original index order (guarantees strict total order)
        validated_items.sort(key=lambda item: (item[1], item[0].plan_id, item[3]))

        ranked_candidates: list[RankedPlan] = []
        for rank_idx, (plan, cost_val, est_ref, _) in enumerate(validated_items, start=1):
            ranked_candidates.append(
                RankedPlan(
                    rank=rank_idx,
                    plan=plan,
                    plan_id=plan.plan_id,
                    cost=cost_val,
                    cost_estimate=est_ref,
                )
            )

        winner = ranked_candidates[0]

        # Determine selection explanation
        if len(ranked_candidates) == 1:
            reason = "Only one candidate plan available."
        else:
            runner_up = ranked_candidates[1]
            diff = runner_up.cost - winner.cost
            if diff > 0.0:
                reason = (
                    f"Lowest estimated total cost ({winner.cost:.2f} vs "
                    f"{runner_up.plan_id} at {runner_up.cost:.2f}, saving {diff:.2f} cost units)."
                )
            else:
                reason = (
                    f"Tied for lowest estimated total cost ({winner.cost:.2f}); "
                    f"selected by deterministic plan ID priority '{winner.plan_id}'."
                )

        return PlanSelectionResult(
            selected_plan=winner.plan,
            selected_plan_id=winner.plan_id,
            selected_cost=winner.cost,
            ranked_candidates=tuple(ranked_candidates),
            reason=reason,
            metadata={
                "candidate_count": len(ranked_candidates),
                "tie_detected": len(ranked_candidates) > 1 and ranked_candidates[0].cost == ranked_candidates[1].cost,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_inputs(
        costed_plans_or_plans: Sequence[tuple[PhysicalPlan, PlanCostEstimate | float]] | Sequence[PhysicalPlan],
        costs: Sequence[PlanCostEstimate | float] | None,
    ) -> list[tuple[PhysicalPlan, PlanCostEstimate | float]]:
        """Normalize varied input calling conventions into a uniform list of (plan, cost) pairs."""
        if costs is not None:
            plans = costed_plans_or_plans
            if len(plans) != len(costs):
                raise SelectionError(
                    f"Mismatched plan and cost counts: received {len(plans)} plans "
                    f"but {len(costs)} cost estimates."
                )
            return list(zip(plans, costs))  # type: ignore[arg-type]

        # Single argument: list of (plan, cost) tuples
        result: list[tuple[PhysicalPlan, PlanCostEstimate | float]] = []
        for item in costed_plans_or_plans:
            if isinstance(item, tuple) and len(item) == 2:
                result.append(item)  # type: ignore[arg-type]
            else:
                raise SelectionError(
                    f"Expected (PhysicalPlan, cost) tuple, received: {type(item).__name__}."
                )
        return result


# ---------------------------------------------------------------------------
# Public functional helper
# ---------------------------------------------------------------------------

def select_plan(
    costed_plans_or_plans: Sequence[tuple[PhysicalPlan, PlanCostEstimate | float]] | Sequence[PhysicalPlan],
    costs: Sequence[PlanCostEstimate | float] | None = None,
) -> PlanSelectionResult:
    """
    Convenience function to select the optimal physical plan with lowest cost.

    Usage
    -----
        result = select_plan(plans, cost_estimates)
        print(result.selected_plan.explain())
    """
    return PlanSelector().select(costed_plans_or_plans, costs)
