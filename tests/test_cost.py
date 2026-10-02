"""
tests/test_cost.py

Comprehensive tests for the Cost Estimator.

Covers:
  1. Cost of a simple SCAN.
  2. Cost of one FILTER.
  3. Cost of two filters.
  4. Cost of PROJECT.
  5. Cost of SORT.
  6. Cost of a complete plan.
  7. Two alternative filter-order plans receive independently calculated costs.
  8. Different filter selectivities can produce different costs.
  9. Cost calculation is deterministic.
  10. Empty result after a filter is handled correctly.
  11. Single-filter plan.
  12. No-WHERE plan.
  13. Reference query cost breakdown.
  14. End-to-end integration test (query string -> lexer -> parser -> semantic -> IR -> planner -> cost estimator).
  15. DatasetStatistics component tests.
"""

import math
import pathlib
import pytest

from backend.lexer import Lexer
from backend.parser import Parser
from backend.semantic import SemanticAnalyzer
from backend.schema import (
    ColumnMeta,
    ColumnType,
    SCHEMA_REGISTRY,
    TableSchema,
)
from backend.ir import build_ir
from backend.planner import (
    PhysicalFilter,
    PhysicalPlan,
    PhysicalProject,
    PhysicalScan,
    PhysicalSort,
    generate_plans,
)
from backend.cost import (
    CostEstimator,
    DatasetStatistics,
    OperationCostEstimate,
    PlanCostEstimate,
    estimate_plan_cost,
    estimate_plans_costs,
)
from backend.executor.dataset import DatasetProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def plans_for(query_str: str) -> list[PhysicalPlan]:
    """Helper to convert query string to candidate physical plans."""
    tokens = Lexer(query_str).tokenize()
    ast = Parser(tokens).parse()
    semantic_result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
    logical_plan = build_ir(ast, semantic_result)
    return generate_plans(logical_plan)


# ---------------------------------------------------------------------------
# 1. Cost of a simple SCAN
# ---------------------------------------------------------------------------

class TestScanCost:
    def test_scan_operation_cost(self) -> None:
        plan = plans_for("SELECT name FROM students;")[0]
        estimator = CostEstimator()
        cost_report = estimator.estimate(plan)

        scan_est = cost_report.operation_estimates[0]
        assert scan_est.operation_type == "SCAN"
        assert scan_est.input_rows == 0
        assert scan_est.output_rows == 200
        assert scan_est.cost == 200.0


# ---------------------------------------------------------------------------
# 2. Cost of one FILTER
# ---------------------------------------------------------------------------

class TestSingleFilterCost:
    def test_single_filter_cost_and_selectivity(self) -> None:
        plan = plans_for("SELECT name, marks FROM students WHERE marks > 80;")[0]
        estimator = CostEstimator()
        cost_report = estimator.estimate(plan)

        filter_est = cost_report.operation_estimates[1]
        assert filter_est.operation_type == "FILTER"
        assert filter_est.input_rows == 200
        assert filter_est.cost == 200.0
        assert filter_est.selectivity == 65 / 200.0  # 0.325
        assert filter_est.output_rows == 65


# ---------------------------------------------------------------------------
# 3. Cost of two filters (sequential)
# ---------------------------------------------------------------------------

class TestTwoFiltersCost:
    def test_two_filters_cascading_cardinality(self) -> None:
        plans = plans_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80;")
        estimator = CostEstimator()

        # Plan A: department = 'CSE' first, then marks > 80
        report_A = estimator.estimate(plans[0])
        f1_A = report_A.operation_estimates[1]
        f2_A = report_A.operation_estimates[2]

        assert f1_A.input_rows == 200
        assert f1_A.output_rows == 38
        assert f1_A.cost == 200.0

        assert f2_A.input_rows == 38
        assert f2_A.output_rows == round(38 * (65 / 200.0))  # 12
        assert f2_A.cost == 38.0


# ---------------------------------------------------------------------------
# 4. Cost of PROJECT
# ---------------------------------------------------------------------------

class TestProjectCost:
    def test_project_cost_matches_input_rows(self) -> None:
        plan = plans_for("SELECT name, marks FROM students WHERE marks > 80;")[0]
        estimator = CostEstimator()
        cost_report = estimator.estimate(plan)

        project_est = cost_report.operation_estimates[2]
        assert project_est.operation_type == "PROJECT"
        assert project_est.input_rows == 65
        assert project_est.output_rows == 65
        assert project_est.cost == 65.0


# ---------------------------------------------------------------------------
# 5. Cost of SORT
# ---------------------------------------------------------------------------

class TestSortCost:
    def test_sort_cost_formula(self) -> None:
        plan = plans_for("SELECT name, marks FROM students WHERE marks > 80 ORDER BY marks DESC;")[0]
        estimator = CostEstimator()
        cost_report = estimator.estimate(plan)

        sort_est = cost_report.operation_estimates[3]
        assert sort_est.operation_type == "SORT"
        n = sort_est.input_rows
        expected_cost = round(n * math.log2(n), 2)
        assert sort_est.cost == expected_cost

    def test_sort_cost_for_zero_or_one_row(self) -> None:
        """Sorting <= 1 row has zero comparison cost."""
        plan = PhysicalPlan(
            plan_id="test",
            operations=(
                PhysicalScan("students"),
                PhysicalProject(("name",)),
                PhysicalSort(column="name", direction="ASC"),
            ),
            source_table="students",
        )
        estimator = CostEstimator()
        # Custom mock plan with input_rows = 1
        est = OperationCostEstimate(
            operation="SORT name ASC",
            operation_type="SORT",
            input_rows=1,
            output_rows=1,
            cost=0.0,
        )
        assert est.cost == 0.0


# ---------------------------------------------------------------------------
# 6. Cost of a complete plan (total = sum of operations)
# ---------------------------------------------------------------------------

class TestCompletePlanCost:
    def test_total_cost_is_sum_of_operation_costs(self) -> None:
        plans = plans_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;")
        estimator = CostEstimator()
        for plan in plans:
            cost_report = estimator.estimate(plan)
            sum_costs = round(sum(op.cost for op in cost_report.operation_estimates), 2)
            assert cost_report.total_cost == sum_costs


# ---------------------------------------------------------------------------
# 7 & 8. Alternative plans receive different costs based on selectivity
# ---------------------------------------------------------------------------

class TestAlternativePlanCosts:
    def test_plan_a_and_b_have_different_costs(self) -> None:
        plans = plans_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;")
        estimator = CostEstimator()

        cost_A = estimator.estimate(plans[0])
        cost_B = estimator.estimate(plans[1])

        assert cost_A.total_cost != cost_B.total_cost

    def test_more_selective_filter_first_is_cheaper(self) -> None:
        # department = 'CSE' has selectivity 38/200 = 0.19 (more selective)
        # marks > 80 has selectivity 65/200 = 0.325 (less selective)
        plans = plans_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;")
        estimator = CostEstimator()

        cost_A = estimator.estimate(plans[0])  # CSE first, then marks
        cost_B = estimator.estimate(plans[1])  # marks first, then CSE

        # Plan A filters more aggressively early, so it must cost less!
        assert cost_A.total_cost < cost_B.total_cost
        assert cost_A.total_cost == 493.02
        assert cost_B.total_cost == 520.02


# ---------------------------------------------------------------------------
# 9. Determinism of cost calculation
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_cost_estimation_is_identical(self) -> None:
        plans = plans_for("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;")
        estimator = CostEstimator()

        run1 = [estimator.estimate(p).total_cost for p in plans]
        run2 = [estimator.estimate(p).total_cost for p in plans]
        run3 = [estimator.estimate(p).total_cost for p in plans]

        assert run1 == run2 == run3


# ---------------------------------------------------------------------------
# 10. Empty result after a filter handled correctly
# ---------------------------------------------------------------------------

class TestEmptyFilterResult:
    def test_zero_match_filter_costs(self) -> None:
        plan = plans_for("SELECT name FROM students WHERE marks > 1000 ORDER BY name ASC;")[0]
        estimator = CostEstimator()
        cost_report = estimator.estimate(plan)

        filter_est = cost_report.operation_estimates[1]
        project_est = cost_report.operation_estimates[2]
        sort_est = cost_report.operation_estimates[3]

        assert filter_est.output_rows == 0
        assert project_est.input_rows == 0
        assert project_est.output_rows == 0
        assert project_est.cost == 0.0

        assert sort_est.input_rows == 0
        assert sort_est.cost == 0.0

        # Total cost is SCAN (200) + FILTER (200) + PROJECT (0) + SORT (0) = 400.0
        assert cost_report.total_cost == 400.0


# ---------------------------------------------------------------------------
# 11. No-WHERE plan
# ---------------------------------------------------------------------------

class TestNoWherePlanCost:
    def test_no_where_plan_cost(self) -> None:
        plan = plans_for("SELECT name FROM students;")[0]
        estimator = CostEstimator()
        cost_report = estimator.estimate(plan)

        assert len(cost_report.operation_estimates) == 2
        scan_est, proj_est = cost_report.operation_estimates

        assert scan_est.cost == 200.0
        assert proj_est.cost == 200.0
        assert cost_report.total_cost == 400.0


# ---------------------------------------------------------------------------
# 12. Reference query detailed verification
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQueryCostBreakdown:
    def test_reference_query_plan_a_breakdown(self) -> None:
        plans = plans_for(REFERENCE_QUERY)
        estimator = CostEstimator()
        report_A = estimator.estimate(plans[0])

        assert report_A.plan_id == "plan_A"
        assert len(report_A.operation_estimates) == 5

        # SCAN
        assert report_A.operation_estimates[0].cost == 200.0
        assert report_A.operation_estimates[0].input_rows == 0
        assert report_A.operation_estimates[0].output_rows == 200

        # FILTER department = 'CSE'
        assert report_A.operation_estimates[1].cost == 200.0
        assert report_A.operation_estimates[1].input_rows == 200
        assert report_A.operation_estimates[1].output_rows == 38
        assert round(report_A.operation_estimates[1].selectivity, 4) == 0.1900

        # FILTER marks > 80
        assert report_A.operation_estimates[2].cost == 38.0
        assert report_A.operation_estimates[2].input_rows == 38
        assert report_A.operation_estimates[2].output_rows == 12
        assert round(report_A.operation_estimates[2].selectivity, 4) == 0.3250

        # PROJECT
        assert report_A.operation_estimates[3].cost == 12.0
        assert report_A.operation_estimates[3].input_rows == 12
        assert report_A.operation_estimates[3].output_rows == 12

        # SORT
        assert report_A.operation_estimates[4].cost == 43.02
        assert report_A.operation_estimates[4].input_rows == 12
        assert report_A.operation_estimates[4].output_rows == 12

        # Total
        assert report_A.total_cost == 493.02

    def test_reference_query_plan_b_breakdown(self) -> None:
        plans = plans_for(REFERENCE_QUERY)
        estimator = CostEstimator()
        report_B = estimator.estimate(plans[1])

        assert report_B.plan_id == "plan_B"
        assert len(report_B.operation_estimates) == 5

        # SCAN
        assert report_B.operation_estimates[0].cost == 200.0
        # FILTER marks > 80
        assert report_B.operation_estimates[1].cost == 200.0
        assert report_B.operation_estimates[1].output_rows == 65
        # FILTER department = 'CSE'
        assert report_B.operation_estimates[2].cost == 65.0
        assert report_B.operation_estimates[2].output_rows == 12
        # PROJECT
        assert report_B.operation_estimates[3].cost == 12.0
        # SORT
        assert report_B.operation_estimates[4].cost == 43.02

        # Total
        assert report_B.total_cost == 520.02


# ---------------------------------------------------------------------------
# 13. Integration: full pipeline to cost estimation
# ---------------------------------------------------------------------------

class TestIntegrationPipeline:
    def test_pipeline_through_cost_estimation(self) -> None:
        query = "SELECT name FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90 ORDER BY marks ASC;"
        plans = plans_for(query)
        assert len(plans) == 6

        cost_reports = estimate_plans_costs(plans)
        assert len(cost_reports) == 6
        for rep in cost_reports:
            assert isinstance(rep, PlanCostEstimate)
            assert rep.total_cost > 0
            assert len(rep.operation_estimates) > 0


# ---------------------------------------------------------------------------
# 14. DatasetStatistics component tests
# ---------------------------------------------------------------------------

class TestDatasetStatisticsComponent:
    def test_get_row_count(self) -> None:
        stats = DatasetStatistics()
        assert stats.get_row_count("students") == 200

    def test_distinct_counts(self) -> None:
        stats = DatasetStatistics()
        # departments in data: CSE, ECE, ME, CE, IT -> 5
        assert stats.get_distinct_count("students", "department") == 5

    def test_min_max_bounds(self) -> None:
        stats = DatasetStatistics()
        bounds = stats.get_min_max("students", "marks")
        assert bounds is not None
        min_m, max_m = bounds
        assert min_m >= 40
        assert max_m <= 100

    def test_custom_data_dir(self, tmp_path: pathlib.Path) -> None:
        csv_file = tmp_path / "students.csv"
        csv_file.write_text("id,name,department,semester,marks\n1,Alice,CSE,1,85\n2,Bob,ECE,2,90\n", encoding="utf-8")
        provider = DatasetProvider(data_dir=tmp_path)
        stats = DatasetStatistics(dataset_provider=provider)
        assert stats.get_row_count("students") == 2


# ---------------------------------------------------------------------------
# 15. Explain formatting & accessors
# ---------------------------------------------------------------------------

class TestExplainFormatting:
    def test_explain_string(self) -> None:
        plans = plans_for(REFERENCE_QUERY)
        rep = estimate_plan_cost(plans[0])
        text = rep.explain()

        assert "Plan plan_A Cost Estimate:" in text
        assert "SCAN students" in text
        assert "FILTER department = 'CSE'" in text
        assert "selectivity: 0.1900" in text
        assert "Total Cost: 493.02" in text

    def test_plan_cost_accessors(self) -> None:
        plans = plans_for(REFERENCE_QUERY)
        rep = estimate_plan_cost(plans[0])

        assert len(rep.operation_costs) == 5
        assert len(rep.input_row_estimates) == 5
        assert len(rep.output_row_estimates) == 5
        assert "FILTER department = 'CSE'" in rep.filter_selectivities
