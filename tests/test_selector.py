"""
tests/test_selector.py

Comprehensive tests for the Plan Selector.

Covers:
  1. Two plans with different costs -> lowest cost selected.
  2. Three plans with different costs -> lowest cost selected.
  3. Equal costs -> deterministic tie-break.
  4. One plan -> that plan selected.
  5. Empty list -> clear SelectionError.
  6. Invalid cost -> clear SelectionError (negative, NaN, Inf).
  7. Plan/cost association is preserved (mismatched IDs raise SelectionError).
  8. Ranking information is correct (all candidates ranked 1..N with costs).
  9. Selection is deterministic across repeated runs.
  10. Critical integration test with the reference query.
  11. Functional helper select_plan(...) usage.
  12. Formatted explanation output.
"""

import math
import pytest

from backend.lexer import Lexer
from backend.parser import Parser
from backend.semantic import SemanticAnalyzer
from backend.schema import SCHEMA_REGISTRY
from backend.ir import build_ir
from backend.planner import (
    PhysicalPlan,
    PhysicalProject,
    PhysicalScan,
    PlanSelectionResult,
    PlanSelector,
    RankedPlan,
    SelectionError,
    generate_plans,
    select_plan,
)
from backend.cost import CostEstimator, PlanCostEstimate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dummy_plan(plan_id: str) -> PhysicalPlan:
    """Create a minimal physical plan for testing selection logic in isolation."""
    return PhysicalPlan(
        plan_id=plan_id,
        operations=(
            PhysicalScan("students"),
            PhysicalProject(("name",)),
        ),
        source_table="students",
        description=f"Dummy plan {plan_id}",
    )


# ---------------------------------------------------------------------------
# 1. Two plans with different costs -> lowest selected
# ---------------------------------------------------------------------------

class TestTwoPlansSelection:
    def test_lowest_cost_selected(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")

        # p1 has cost 500, p2 has cost 300
        costed = [(p1, 500.0), (p2, 300.0)]
        result = PlanSelector().select(costed)

        assert result.selected_plan_id == "plan_B"
        assert result.selected_cost == 300.0
        assert result.selected_plan == p2

    def test_reverse_input_order_still_picks_lowest(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")

        # p1 has lower cost
        costed = [(p2, 600.0), (p1, 250.0)]
        result = PlanSelector().select(costed)

        assert result.selected_plan_id == "plan_A"
        assert result.selected_cost == 250.0


# ---------------------------------------------------------------------------
# 2. Three plans with different costs -> lowest selected
# ---------------------------------------------------------------------------

class TestThreePlansSelection:
    def test_three_plans_ranking(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")
        p3 = dummy_plan("plan_C")

        costed = [(p1, 600.0), (p2, 350.0), (p3, 450.0)]
        result = PlanSelector().select(costed)

        assert result.selected_plan_id == "plan_B"
        assert result.selected_cost == 350.0
        assert len(result.ranked_candidates) == 3

        # Check full ranking
        ranks = [(c.rank, c.plan_id, c.cost) for c in result.ranked_candidates]
        assert ranks == [
            (1, "plan_B", 350.0),
            (2, "plan_C", 450.0),
            (3, "plan_A", 600.0),
        ]


# ---------------------------------------------------------------------------
# 3. Equal costs -> deterministic tie-break
# ---------------------------------------------------------------------------

class TestEqualCostsTieBreak:
    def test_tie_broken_by_alphabetical_plan_id(self) -> None:
        p1 = dummy_plan("plan_B")
        p2 = dummy_plan("plan_A")

        # Both have identical costs
        costed = [(p1, 400.0), (p2, 400.0)]
        result = PlanSelector().select(costed)

        # plan_A comes before plan_B alphabetically
        assert result.selected_plan_id == "plan_A"
        assert result.selected_cost == 400.0
        assert result.metadata["tie_detected"] is True
        assert "tied" in result.reason.lower()

    def test_three_way_tie_break(self) -> None:
        p1 = dummy_plan("plan_Z")
        p2 = dummy_plan("plan_M")
        p3 = dummy_plan("plan_A")

        costed = [(p1, 100.0), (p2, 100.0), (p3, 100.0)]
        result = PlanSelector().select(costed)

        assert result.selected_plan_id == "plan_A"
        ranked_ids = [c.plan_id for c in result.ranked_candidates]
        assert ranked_ids == ["plan_A", "plan_M", "plan_Z"]


# ---------------------------------------------------------------------------
# 4. Single plan -> that plan selected
# ---------------------------------------------------------------------------

class TestSinglePlanSelection:
    def test_single_plan_always_selected(self) -> None:
        p1 = dummy_plan("plan_A")
        result = PlanSelector().select([(p1, 400.0)])

        assert result.selected_plan_id == "plan_A"
        assert result.selected_cost == 400.0
        assert len(result.ranked_candidates) == 1
        assert "only one candidate" in result.reason.lower()


# ---------------------------------------------------------------------------
# 5. Empty plan list -> clear error
# ---------------------------------------------------------------------------

class TestEmptyListValidation:
    def test_empty_list_raises_selection_error(self) -> None:
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([])
        assert "empty" in str(exc_info.value).lower()

    def test_empty_lists_two_args(self) -> None:
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([], [])
        assert "empty" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 6. Invalid / non-finite costs -> clear error
# ---------------------------------------------------------------------------

class TestInvalidCostValidation:
    def test_negative_cost_raises_error(self) -> None:
        p1 = dummy_plan("plan_A")
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([(p1, -10.0)])
        assert "negative" in str(exc_info.value).lower()

    def test_nan_cost_raises_error(self) -> None:
        p1 = dummy_plan("plan_A")
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([(p1, float("nan"))])
        assert "non-finite" in str(exc_info.value).lower()

    def test_infinite_cost_raises_error(self) -> None:
        p1 = dummy_plan("plan_A")
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([(p1, float("inf"))])
        assert "non-finite" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 7. Plan/cost association and consistency
# ---------------------------------------------------------------------------

class TestPlanCostAssociation:
    def test_mismatched_plan_and_cost_lengths(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([p1, p2], [100.0])
        assert "mismatched" in str(exc_info.value).lower()

    def test_mismatched_plan_id_in_estimate_object(self) -> None:
        p1 = dummy_plan("plan_A")
        # Estimate object has plan_id="plan_B", but plan has "plan_A"
        bad_est = PlanCostEstimate(plan_id="plan_B", total_cost=200.0, operation_estimates=())
        with pytest.raises(SelectionError) as exc_info:
            PlanSelector().select([p1], [bad_est])
        assert "inconsistent" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 8. Ranking information
# ---------------------------------------------------------------------------

class TestRankingInformation:
    def test_ranking_attributes(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")
        est1 = PlanCostEstimate("plan_A", 500.0, ())
        est2 = PlanCostEstimate("plan_B", 300.0, ())

        result = PlanSelector().select([p1, p2], [est1, est2])

        assert len(result.ranked_candidates) == 2
        first = result.ranked_candidates[0]
        assert first.rank == 1
        assert first.plan_id == "plan_B"
        assert first.cost == 300.0
        assert first.cost_estimate is est2
        assert first.plan is p2

        second = result.ranked_candidates[1]
        assert second.rank == 2
        assert second.plan_id == "plan_A"
        assert second.cost == 500.0
        assert second.cost_estimate is est1
        assert second.plan is p1


# ---------------------------------------------------------------------------
# 9. Determinism across repeated runs
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_selection_is_deterministic(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")
        p3 = dummy_plan("plan_C")
        items = [(p1, 400.0), (p2, 400.0), (p3, 200.0)]

        selector = PlanSelector()
        results = [selector.select(items).selected_plan_id for _ in range(10)]
        assert all(pid == "plan_C" for pid in results)


# ---------------------------------------------------------------------------
# 10. Critical integration test with reference query
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQueryPlanSelection:
    def test_end_to_end_selection_pipeline(self) -> None:
        # Full pipeline: query -> lexer -> parser -> semantic -> IR -> planner -> cost -> selector
        tokens = Lexer(REFERENCE_QUERY).tokenize()
        ast = Parser(tokens).parse()
        semantic_result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        logical_plan = build_ir(ast, semantic_result)
        plans = generate_plans(logical_plan)

        # 1. Multiple valid physical plans are generated
        assert len(plans) == 2
        plan_ids = [p.plan_id for p in plans]
        assert "plan_A" in plan_ids
        assert "plan_B" in plan_ids

        # 2. Each plan receives a cost
        estimator = CostEstimator()
        costs = [estimator.estimate(p) for p in plans]
        assert len(costs) == 2

        # 3. Selector chooses the plan with the minimum estimated cost
        selection = PlanSelector().select(plans, costs)

        # In our dataset:
        # department = 'CSE' has selectivity 0.1900
        # marks > 80 has selectivity 0.3250
        # Plan A evaluates department = 'CSE' first -> Cost 493.02
        # Plan B evaluates marks > 80 first -> Cost 520.02
        assert selection.selected_plan_id == "plan_A"
        assert selection.selected_cost == 493.02
        assert selection.selected_plan == plans[0]

        # 4. Ranking is correct
        assert selection.ranked_candidates[0].plan_id == "plan_A"
        assert selection.ranked_candidates[0].cost == 493.02
        assert selection.ranked_candidates[1].plan_id == "plan_B"
        assert selection.ranked_candidates[1].cost == 520.02

        # 5. Rationale is informative
        assert "saving 27.00" in selection.reason


# ---------------------------------------------------------------------------
# 11. Functional helper select_plan
# ---------------------------------------------------------------------------

class TestFunctionalHelper:
    def test_select_plan_helper(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")
        res = select_plan([p1, p2], [100.0, 200.0])
        assert res.selected_plan_id == "plan_A"
        assert res.selected_cost == 100.0


# ---------------------------------------------------------------------------
# 12. Explanation and formatting
# ---------------------------------------------------------------------------

class TestExplanationFormatting:
    def test_explain_string_format(self) -> None:
        p1 = dummy_plan("plan_A")
        p2 = dummy_plan("plan_B")
        res = select_plan([(p1, 493.02), (p2, 520.02)])
        text = res.explain()

        assert "PLAN COMPARISON" in text
        assert "plan_A" in text
        assert "493.02" in text
        assert "plan_B" in text
        assert "520.02" in text
        assert "Selected Plan: plan_A" in text
        assert "SELECTED" in text
