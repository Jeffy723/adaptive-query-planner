"""
tests/test_planner.py

Comprehensive tests for the Execution Plan Generator.

Covers:
  1. Query with no WHERE -> exactly one plan.
  2. Query with one filter -> exactly one plan.
  3. Query with two AND predicates -> exactly two filter-order plans.
  4. Query with three AND predicates -> exactly six filter-order plans (3! = 6).
  5. Query with OR -> no filter reordering (exactly one plan).
  6. Query with AND + OR -> preserve OR structure and only reorder independent
     top-level AND predicates where semantically safe.
  7. SELECT + WHERE + ORDER BY preserves PROJECT and SORT positions.
  8. All generated plans contain SCAN.
  9. All generated plans preserve the same projection.
  10. All generated plans preserve the same sort.
  11. Every generated plan has a unique deterministic ID.
  12. Reference query: verify Plan A and Plan B operations and filter orders.
  13. Plan equivalence: alternative plans produce identical query results when executed.
  14. Bounded plan generation for large predicate counts.
  15. Plan explain, format_pipeline, and metadata validation.
"""

import pytest

from backend.lexer import Lexer
from backend.parser import Parser
from backend.semantic import SemanticAnalyzer
from backend.schema import SCHEMA_REGISTRY
from backend.ir import build_ir, LogicalPlan
from backend.executor import Executor
from backend.planner import (
    MAX_GENERATED_PLANS,
    PlanGenerator,
    PhysicalFilter,
    PhysicalPlan,
    PhysicalProject,
    PhysicalScan,
    PhysicalSort,
    extract_conjuncts,
    generate_plans,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_logical_plan(query_str: str) -> LogicalPlan:
    """Helper to convert query string to a valid LogicalPlan."""
    tokens = Lexer(query_str).tokenize()
    ast = Parser(tokens).parse()
    semantic_result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
    return build_ir(ast, semantic_result)


def plan_for(query_str: str) -> list[PhysicalPlan]:
    """Helper to generate physical plans from a query string."""
    return generate_plans(get_logical_plan(query_str))


# ---------------------------------------------------------------------------
# 1. Query with no WHERE -> exactly one plan
# ---------------------------------------------------------------------------

class TestNoWherePlanGeneration:
    def test_single_plan_generated(self) -> None:
        plans = plan_for("SELECT name FROM students;")
        assert len(plans) == 1

    def test_operations_sequence(self) -> None:
        plan = plan_for("SELECT name FROM students;")[0]
        assert len(plan.operations) == 2
        assert isinstance(plan.operations[0], PhysicalScan)
        assert plan.operations[0].table_name == "students"
        assert isinstance(plan.operations[1], PhysicalProject)
        assert plan.operations[1].columns == ("name",)

    def test_filter_order_is_empty(self) -> None:
        plan = plan_for("SELECT name FROM students;")[0]
        assert plan.filter_order == ()
        assert plan.filter_operations == ()


# ---------------------------------------------------------------------------
# 2. Query with one filter -> exactly one plan
# ---------------------------------------------------------------------------

class TestSingleFilterPlanGeneration:
    def test_single_plan_generated(self) -> None:
        plans = plan_for("SELECT name, marks FROM students WHERE marks > 80;")
        assert len(plans) == 1

    def test_operations_sequence(self) -> None:
        plan = plan_for("SELECT name, marks FROM students WHERE marks > 80;")[0]
        assert len(plan.operations) == 3
        assert isinstance(plan.operations[0], PhysicalScan)
        assert isinstance(plan.operations[1], PhysicalFilter)
        assert isinstance(plan.operations[2], PhysicalProject)
        assert len(plan.filter_order) == 1
        assert str(plan.filter_order[0]) == "marks > 80"


# ---------------------------------------------------------------------------
# 3. Query with two AND predicates -> exactly two filter-order plans
# ---------------------------------------------------------------------------

class TestTwoPredicatesPlanGeneration:
    def test_generates_two_plans(self) -> None:
        plans = plan_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80;")
        assert len(plans) == 2

    def test_plan_ids(self) -> None:
        plans = plan_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80;")
        assert plans[0].plan_id == "plan_A"
        assert plans[1].plan_id == "plan_B"

    def test_filter_order_permutation(self) -> None:
        plans = plan_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80;")
        order_A = [str(f) for f in plans[0].filter_order]
        order_B = [str(f) for f in plans[1].filter_order]

        assert order_A == ["department = 'CSE'", "marks > 80"]
        assert order_B == ["marks > 80", "department = 'CSE'"]

    def test_filter_operations_match_filter_order(self) -> None:
        plans = plan_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80;")
        for plan in plans:
            filters_in_ops = [str(op.predicate) for op in plan.filter_operations]
            filters_in_order = [str(f) for f in plan.filter_order]
            assert filters_in_ops == filters_in_order


# ---------------------------------------------------------------------------
# 4. Query with three AND predicates -> six plans (3! = 6)
# ---------------------------------------------------------------------------

class TestThreePredicatesPlanGeneration:
    def test_generates_six_plans(self) -> None:
        query = "SELECT name FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        plans = plan_for(query)
        assert len(plans) == 6

    def test_unique_plan_ids(self) -> None:
        query = "SELECT name FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        plans = plan_for(query)
        ids = [p.plan_id for p in plans]
        assert len(ids) == len(set(ids))
        assert ids == ["plan_A", "plan_B", "plan_C", "plan_D", "plan_E", "plan_F"]

    def test_all_permutations_distinct(self) -> None:
        query = "SELECT name FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        plans = plan_for(query)
        orders = [tuple(str(f) for f in p.filter_order) for p in plans]
        assert len(orders) == len(set(orders))


# ---------------------------------------------------------------------------
# 5. Query with OR -> no filter reordering (exactly 1 plan)
# ---------------------------------------------------------------------------

class TestOrConditionNoReordering:
    def test_or_generates_single_plan(self) -> None:
        query = "SELECT name FROM students WHERE department = 'CSE' OR marks > 80;"
        plans = plan_for(query)
        assert len(plans) == 1
        assert plans[0].plan_id == "plan_A"

    def test_or_predicate_structure_preserved(self) -> None:
        query = "SELECT name FROM students WHERE department = 'CSE' OR marks > 80;"
        plan = plan_for(query)[0]
        assert len(plan.filter_order) == 1
        # The entire OR expression is kept intact as a single filter
        assert str(plan.filter_order[0]) == "(department = 'CSE' OR marks > 80)"


# ---------------------------------------------------------------------------
# 6. Query with AND + OR -> preserve OR structure and reorder top-level AND
# ---------------------------------------------------------------------------

class TestAndOrCombinationPlanGeneration:
    def test_and_after_or_reorders_top_level_and(self) -> None:
        # (marks > 80 OR department = 'CSE') AND semester = 5
        query = "SELECT name FROM students WHERE marks > 80 OR department = 'CSE' AND semester = 5;"
        plans = plan_for(query)
        # 2 top-level conjuncts -> 2 plans
        assert len(plans) == 2
        order_A = [str(f) for f in plans[0].filter_order]
        order_B = [str(f) for f in plans[1].filter_order]

        assert order_A == ["(marks > 80 OR department = 'CSE')", "semester = 5"]
        assert order_B == ["semester = 5", "(marks > 80 OR department = 'CSE')"]

    def test_or_after_and_is_single_plan(self) -> None:
        # Top-level is OR: ((marks > 80 AND semester = 3) OR department = 'CSE')
        query = "SELECT name FROM students WHERE marks > 80 AND semester = 3 OR department = 'CSE';"
        plans = plan_for(query)
        assert len(plans) == 1


# ---------------------------------------------------------------------------
# 7. SELECT + WHERE + ORDER BY preserves non-filter positions
# ---------------------------------------------------------------------------

class TestNonFilterOperationPreservation:
    def test_scan_is_first_in_all_plans(self) -> None:
        query = "SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;"
        plans = plan_for(query)
        for plan in plans:
            assert isinstance(plan.operations[0], PhysicalScan)
            assert plan.operations[0].table_name == "students"

    def test_project_and_sort_positions_preserved(self) -> None:
        query = "SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;"
        plans = plan_for(query)
        for plan in plans:
            # Plan has: Scan, Filter1, Filter2, Project, Sort
            assert isinstance(plan.operations[-2], PhysicalProject)
            assert plan.operations[-2].columns == ("name", "marks")
            assert isinstance(plan.operations[-1], PhysicalSort)
            assert plan.operations[-1].column == "marks"
            assert plan.operations[-1].direction == "DESC"

    def test_all_plans_preserve_same_projection(self) -> None:
        query = "SELECT id, name FROM students WHERE marks > 70 AND semester = 2;"
        plans = plan_for(query)
        for plan in plans:
            assert plan.project_operation.columns == ("id", "name")

    def test_all_plans_preserve_same_sort(self) -> None:
        query = "SELECT name FROM students WHERE marks > 70 AND semester = 2 ORDER BY name ASC;"
        plans = plan_for(query)
        for plan in plans:
            assert plan.sort_operation is not None
            assert plan.sort_operation.column == "name"
            assert plan.sort_operation.direction == "ASC"


# ---------------------------------------------------------------------------
# 8. Reference query verification
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQueryPlanGeneration:
    def test_generates_exact_plan_a_and_b(self) -> None:
        plans = plan_for(REFERENCE_QUERY)
        assert len(plans) == 2

        plan_A, plan_B = plans[0], plans[1]

        # Plan A
        assert plan_A.plan_id == "plan_A"
        assert [type(op).__name__ for op in plan_A.operations] == [
            "PhysicalScan",
            "PhysicalFilter",
            "PhysicalFilter",
            "PhysicalProject",
            "PhysicalSort",
        ]
        assert str(plan_A.operations[1]) == "FILTER department = 'CSE'"
        assert str(plan_A.operations[2]) == "FILTER marks > 80"

        # Plan B
        assert plan_B.plan_id == "plan_B"
        assert [type(op).__name__ for op in plan_B.operations] == [
            "PhysicalScan",
            "PhysicalFilter",
            "PhysicalFilter",
            "PhysicalProject",
            "PhysicalSort",
        ]
        assert str(plan_B.operations[1]) == "FILTER marks > 80"
        assert str(plan_B.operations[2]) == "FILTER department = 'CSE'"

    def test_metadata_completeness(self) -> None:
        plans = plan_for(REFERENCE_QUERY)
        for plan in plans:
            assert "plan_id" in plan.metadata
            assert plan.metadata["filter_count"] == 2
            assert plan.metadata["source_table"] == "students"
            assert plan.metadata["has_sort"] is True


# ---------------------------------------------------------------------------
# 9. Plan equivalence execution verification
# ---------------------------------------------------------------------------

class TestPlanEquivalenceExecution:
    def test_reference_query_plans_produce_identical_results(self) -> None:
        """Executing Plan A and Plan B against the dataset yields identical rows."""
        plans = plan_for(REFERENCE_QUERY)
        executor = Executor(SCHEMA_REGISTRY)

        result_A = executor.execute(plans[0].to_logical())
        result_B = executor.execute(plans[1].to_logical())

        assert result_A.row_count == 13
        assert result_B.row_count == 13
        assert result_A.columns == ["name", "marks"]
        assert result_B.columns == ["name", "marks"]
        assert result_A.rows == result_B.rows

    def test_three_filter_plans_produce_identical_results(self) -> None:
        query = "SELECT name, marks FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90 ORDER BY marks ASC;"
        plans = plan_for(query)
        assert len(plans) == 6

        executor = Executor(SCHEMA_REGISTRY)
        reference_rows = executor.execute(plans[0].to_logical()).rows

        for plan in plans[1:]:
            res = executor.execute(plan.to_logical())
            assert res.rows == reference_rows


# ---------------------------------------------------------------------------
# 10. Bounded plan generation
# ---------------------------------------------------------------------------

class TestBoundedPlanGeneration:
    def test_custom_max_plans_bound(self) -> None:
        query = "SELECT name FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        # Normally 6 permutations, capped at 3
        generator = PlanGenerator(max_plans=3)
        plans = generator.generate(get_logical_plan(query))
        assert len(plans) == 3
        assert [p.plan_id for p in plans] == ["plan_A", "plan_B", "plan_C"]

    def test_default_max_plans_constant(self) -> None:
        assert MAX_GENERATED_PLANS == 24


# ---------------------------------------------------------------------------
# 11. String representation & explanation
# ---------------------------------------------------------------------------

class TestPlanExplain:
    def test_explain_includes_plan_id_and_ops(self) -> None:
        plans = plan_for(REFERENCE_QUERY)
        text = plans[0].explain()
        assert "plan_A" in text
        assert "SCAN students" in text
        assert "FILTER department = 'CSE'" in text
        assert "FILTER marks > 80" in text
        assert "PROJECT name, marks" in text
        assert "SORT marks DESC" in text

    def test_format_pipeline_arrow_string(self) -> None:
        plans = plan_for(REFERENCE_QUERY)
        pipeline = plans[0].format_pipeline()
        assert pipeline == "SCAN students -> FILTER department = 'CSE' -> FILTER marks > 80 -> PROJECT name, marks -> SORT marks DESC"

    def test_str_matches_multiline_ops(self) -> None:
        plans = plan_for(REFERENCE_QUERY)
        text = str(plans[0])
        assert "SCAN students" in text
        assert "PROJECT name, marks" in text
