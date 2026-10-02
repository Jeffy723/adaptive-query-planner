"""
tests/test_feedback.py

Comprehensive test suite for the Runtime Feedback & Adaptive Statistics Learning component.

Tests cover:
  1. Feedback Data Models (SelectivityFeedback, OperationFeedback, ExecutionFeedback)
  2. Error and Metric Calculations (diff, absolute_error, relative_error, percentages, zero handling)
  3. Feedback Collector (matching estimated to actual stats, alpha weighting, edge cases)
  4. Adaptive Statistics Store (recording, retrieving, prefix tolerance, ingestion)
  5. Cost Estimator Adaptive Integration (learned selectivity overrides static inspection)
  6. Pipeline Learning Integration (enable_learning=False vs True, state persistence)
  7. Reference Query End-to-End Verification (exact metrics, report formatting, baseline match)
"""

from __future__ import annotations

import pytest

from backend.cost import CostEstimator, DatasetStatistics, PlanCostEstimate
from backend.cost.model import OperationCostEstimate
from backend.executor import ExecutionResult, OperationStats
from backend.feedback import (
    DEFAULT_ALPHA,
    AdaptiveStatisticsStore,
    ExecutionFeedback,
    FeedbackCollector,
    OperationFeedback,
    SelectivityFeedback,
    collect_feedback,
)
from backend.pipeline import QueryPipeline, execute_query


# ===========================================================================
# 1. Model Unit Tests
# ===========================================================================

class TestFeedbackModels:
    """Test feedback model dataclasses, string representations, and properties."""

    def test_selectivity_feedback_fields_and_str(self):
        sf = SelectivityFeedback(
            predicate="department = 'CSE'",
            previous_selectivity=0.20,
            observed_selectivity=0.19,
            updated_selectivity=0.195,
            alpha=0.5,
        )
        assert sf.predicate == "department = 'CSE'"
        assert sf.previous_selectivity == 0.20
        assert sf.observed_selectivity == 0.19
        assert sf.updated_selectivity == 0.195
        assert sf.alpha == 0.5

        rendered = str(sf)
        assert "department = 'CSE'" in rendered
        assert "0.2000" in rendered
        assert "0.1900" in rendered
        assert "0.1950" in rendered
        assert "alpha=0.50" in rendered

    def test_operation_feedback_metrics(self):
        op_fb = OperationFeedback(
            operation="FILTER marks > 80",
            operation_type="FILTER",
            estimated_input_rows=38,
            actual_input_rows=38,
            estimated_output_rows=12,
            actual_output_rows=13,
            difference=1,
            absolute_error=1,
            relative_error=1 / 13,
        )
        assert op_fb.operation == "FILTER marks > 80"
        assert op_fb.difference == 1
        assert op_fb.absolute_error == 1
        assert pytest.approx(op_fb.relative_error, 0.001) == 0.0769
        assert pytest.approx(op_fb.relative_error_percentage, 0.01) == 7.69

        rendered = str(op_fb)
        assert "FILTER marks > 80" in rendered
        assert "+1" in rendered
        assert "7.69%" in rendered

    def test_execution_feedback_summary_properties(self):
        op1 = OperationFeedback(
            operation="SCAN students",
            operation_type="SCAN",
            estimated_input_rows=0,
            actual_input_rows=0,
            estimated_output_rows=200,
            actual_output_rows=200,
            difference=0,
            absolute_error=0,
            relative_error=0.0,
        )
        op2 = OperationFeedback(
            operation="FILTER department = 'CSE'",
            operation_type="FILTER",
            estimated_input_rows=200,
            actual_input_rows=200,
            estimated_output_rows=40,
            actual_output_rows=38,
            difference=-2,
            absolute_error=2,
            relative_error=2 / 38,
        )
        op3 = OperationFeedback(
            operation="FILTER marks > 80",
            operation_type="FILTER",
            estimated_input_rows=38,
            actual_input_rows=38,
            estimated_output_rows=12,
            actual_output_rows=13,
            difference=1,
            absolute_error=1,
            relative_error=1 / 13,
        )

        fb = ExecutionFeedback(
            query="SELECT name FROM students;",
            selected_plan_id="plan_A",
            total_estimated_cost=278.0,
            operation_feedback=(op1, op2, op3),
        )

        assert fb.total_absolute_error == 3  # 0 + 2 + 1
        assert fb.max_absolute_error == 2
        # Average relative error = (0.0% + (2/38*100)% + (1/13*100)%) / 3
        expected_avg_rel = (0.0 + (2 / 38 * 100) + (1 / 13 * 100)) / 3
        assert pytest.approx(fb.average_relative_error, 0.01) == expected_avg_rel

        rendered = fb.explain()
        assert "RUNTIME FEEDBACK & ADAPTATION REPORT" in rendered
        assert "plan_A" in rendered
        assert "Total Absolute Output Error: 3 rows" in rendered

    def test_execution_feedback_empty_operations(self):
        fb = ExecutionFeedback(
            query="EMPTY",
            selected_plan_id="none",
            total_estimated_cost=0.0,
            operation_feedback=(),
        )
        assert fb.total_absolute_error == 0
        assert fb.max_absolute_error == 0
        assert fb.average_relative_error == 0.0


# ===========================================================================
# 2. Collector Unit Tests
# ===========================================================================

class TestFeedbackCollector:
    """Test matching, error calculation, and update formulas in FeedbackCollector."""

    def test_invalid_alpha_raises_value_error(self):
        with pytest.raises(ValueError, match="Alpha smoothing parameter"):
            FeedbackCollector(alpha=-0.1)
        with pytest.raises(ValueError, match="Alpha smoothing parameter"):
            FeedbackCollector(alpha=1.1)

    def test_collect_with_no_cost_estimate(self):
        exec_res = ExecutionResult(
            columns=["id"],
            rows=[{"id": 1}],
            row_count=1,
            stats=[OperationStats("SCAN students", 0, 1)],
        )
        fb = FeedbackCollector().collect(cost_estimate=None, execution_result=exec_res)
        assert fb.selected_plan_id == "unknown"
        assert len(fb.operation_feedback) == 0
        assert fb.metadata.get("status") == "no_cost_estimate"

    def test_zero_output_rows_relative_error_handling(self):
        # Case 1: both estimated and actual are 0
        est = PlanCostEstimate(
            plan_id="test_plan",
            total_cost=10.0,
            operation_estimates=(
                OperationCostEstimate(
                    operation="FILTER marks > 100",
                    operation_type="FILTER",
                    input_rows=200,
                    output_rows=0,
                    cost=200.0,
                    selectivity=0.0,
                    description="",
                ),
            ),
        )
        act = ExecutionResult(
            columns=["id"],
            rows=[],
            row_count=0,
            stats=[OperationStats("FILTER marks > 100", 200, 0)],
        )
        fb = FeedbackCollector().collect(est, act)
        assert fb.operation_feedback[0].relative_error == 0.0
        assert fb.operation_feedback[0].absolute_error == 0
        assert fb.operation_feedback[0].difference == 0

        # Case 2: estimated > 0 but actual is 0 (relative error is capped safely to 1.0)
        est2 = PlanCostEstimate(
            plan_id="test_plan",
            total_cost=10.0,
            operation_estimates=(
                OperationCostEstimate(
                    operation="FILTER marks > 100",
                    operation_type="FILTER",
                    input_rows=200,
                    output_rows=5,
                    cost=200.0,
                    selectivity=0.025,
                    description="",
                ),
            ),
        )
        fb2 = FeedbackCollector().collect(est2, act)
        assert fb2.operation_feedback[0].relative_error == 1.0
        assert fb2.operation_feedback[0].absolute_error == 5
        assert fb2.operation_feedback[0].difference == -5

    def test_selectivity_update_formula_with_custom_alpha(self):
        # input=200, est_out=40 (prev_sel=0.20), act_out=50 (obs_sel=50/200=0.25)
        # with alpha=0.4: updated = 0.4 * 0.25 + 0.6 * 0.20 = 0.10 + 0.12 = 0.22
        est = PlanCostEstimate(
            plan_id="plan_test",
            total_cost=100.0,
            operation_estimates=(
                OperationCostEstimate(
                    operation="FILTER department = 'ECE'",
                    operation_type="FILTER",
                    input_rows=200,
                    output_rows=40,
                    cost=200.0,
                    selectivity=0.20,
                    description="",
                ),
            ),
        )
        act = ExecutionResult(
            columns=["id"],
            rows=[{}] * 50,
            row_count=50,
            stats=[OperationStats("FILTER department = 'ECE'", 200, 50)],
        )

        fb = FeedbackCollector(alpha=0.4).collect(est, act)
        sf = fb.operation_feedback[0].selectivity_feedback
        assert sf is not None
        assert pytest.approx(sf.previous_selectivity) == 0.20
        assert pytest.approx(sf.observed_selectivity) == 0.25
        assert pytest.approx(sf.updated_selectivity) == 0.22
        assert sf.alpha == 0.4

    def test_non_filter_operations_do_not_produce_selectivity_feedback(self):
        est = PlanCostEstimate(
            plan_id="plan_test",
            total_cost=50.0,
            operation_estimates=(
                OperationCostEstimate("SCAN t", "SCAN", 0, 10, 10.0, None, ""),
                OperationCostEstimate("PROJECT c", "PROJECT", 10, 10, 10.0, None, ""),
                OperationCostEstimate("SORT c ASC", "SORT", 10, 10, 33.2, None, ""),
            ),
        )
        act = ExecutionResult(
            columns=["c"],
            rows=[{"c": i} for i in range(10)],
            row_count=10,
            stats=[
                OperationStats("SCAN t", 0, 10),
                OperationStats("PROJECT c", 10, 10),
                OperationStats("SORT c ASC", 10, 10),
            ],
        )
        fb = FeedbackCollector().collect(est, act)
        for op in fb.operation_feedback:
            assert op.selectivity_feedback is None


# ===========================================================================
# 3. Adaptive Statistics Store Unit Tests
# ===========================================================================

class TestAdaptiveStatisticsStore:
    """Test storing, querying, and updating learned statistics in the repository."""

    def test_record_and_get_selectivity(self):
        store = AdaptiveStatisticsStore()
        assert store.get_selectivity("students", "department = 'CSE'") is None
        assert not store.has_selectivity("students", "department = 'CSE'")

        store.record_selectivity("students", "department = 'CSE'", 0.195)
        assert store.has_selectivity("students", "department = 'CSE'")
        assert store.get_selectivity("students", "department = 'CSE'") == 0.195

    def test_case_insensitivity_and_prefix_tolerance(self):
        store = AdaptiveStatisticsStore()
        # Recorded with "FILTER " prefix
        store.record_selectivity("STUDENTS", "FILTER marks > 80", 0.33)

        # Query without prefix
        assert store.get_selectivity("students", "marks > 80") == 0.33
        # Query with prefix
        assert store.get_selectivity("Students", "FILTER marks > 80") == 0.33

        # Recorded without prefix
        store.record_selectivity("students", "marks < 40", 0.05)
        # Query with prefix
        assert store.get_selectivity("STUDENTS", "FILTER marks < 40") == 0.05

    def test_update_from_feedback_multiple_predicates(self):
        store = AdaptiveStatisticsStore()

        op1 = OperationFeedback(
            operation="SCAN students",
            operation_type="SCAN",
            estimated_input_rows=0,
            actual_input_rows=0,
            estimated_output_rows=200,
            actual_output_rows=200,
            difference=0,
            absolute_error=0,
            relative_error=0.0,
        )
        sf2 = SelectivityFeedback("department = 'CSE'", 0.19, 0.19, 0.19, 0.5)
        op2 = OperationFeedback(
            operation="FILTER department = 'CSE'",
            operation_type="FILTER",
            estimated_input_rows=200,
            actual_input_rows=200,
            estimated_output_rows=38,
            actual_output_rows=38,
            difference=0,
            absolute_error=0,
            relative_error=0.0,
            selectivity_feedback=sf2,
        )
        sf3 = SelectivityFeedback("marks > 80", 0.325, 0.3421, 0.3336, 0.5)
        op3 = OperationFeedback(
            operation="FILTER marks > 80",
            operation_type="FILTER",
            estimated_input_rows=38,
            actual_input_rows=38,
            estimated_output_rows=12,
            actual_output_rows=13,
            difference=1,
            absolute_error=1,
            relative_error=1 / 13,
            selectivity_feedback=sf3,
        )

        fb = ExecutionFeedback(
            query="SELECT ...",
            selected_plan_id="plan_A",
            total_estimated_cost=278.0,
            operation_feedback=(op1, op2, op3),
        )

        count = store.update_from_feedback(fb, table_name="students")
        assert count == 2
        assert len(store) == 2
        assert store.get_selectivity("students", "department = 'CSE'") == 0.19
        assert store.get_selectivity("students", "marks > 80") == 0.3336

    def test_clear_resets_store(self):
        store = AdaptiveStatisticsStore()
        store.record_selectivity("students", "col = 1", 0.5)
        assert len(store) == 1
        store.clear()
        assert len(store) == 0
        assert store.get_selectivity("students", "col = 1") is None


# ===========================================================================
# 4. Cost Estimator Adaptive Integration Tests
# ===========================================================================

class TestCostEstimatorAdaptiveIntegration:
    """Verify that CostEstimator dynamically picks up learned selectivities."""

    def test_cost_estimator_uses_learned_selectivity(self):
        store = AdaptiveStatisticsStore()
        # In students dataset, static selectivity for marks > 80 is 65 / 200 = 0.325
        stats_static = DatasetStatistics()
        from backend.ir import IRColumnRef, IRComparison, IRLiteral, IRLiteralType
        pred = IRComparison(
            column=IRColumnRef("marks"),
            operator=">",
            value=IRLiteral(80, IRLiteralType.INTEGER),
        )

        static_sel = stats_static.calculate_selectivity("students", pred)
        assert pytest.approx(static_sel, 0.001) == 0.325

        # Now configure with adaptive store containing updated selectivity (e.g. 0.50)
        store.record_selectivity("students", str(pred), 0.50)
        stats_learned = DatasetStatistics(adaptive_store=store)
        learned_sel = stats_learned.calculate_selectivity("students", pred)
        assert pytest.approx(learned_sel, 0.001) == 0.50

        # Unlearned predicate continues to use static inspection
        pred_other = IRComparison(
            column=IRColumnRef("department"),
            operator="=",
            value=IRLiteral("CSE", IRLiteralType.STRING),
        )
        assert pytest.approx(stats_learned.calculate_selectivity("students", pred_other), 0.001) == 0.19

    def test_cost_estimator_produces_modified_estimates_with_learned_store(self):
        store = AdaptiveStatisticsStore()
        est_default = CostEstimator()
        est_adaptive = CostEstimator(adaptive_store=store)

        from backend.planner import generate_plans
        from backend.ir import build_ir
        from backend.lexer import Lexer
        from backend.parser import Parser
        from backend.schema import SCHEMA_REGISTRY
        from backend.semantic import SemanticAnalyzer

        tokens = Lexer("SELECT name FROM students WHERE marks > 80;").tokenize()
        ast = Parser(tokens).parse()
        sem = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        ir = build_ir(ast, sem)
        plan = next(iter(generate_plans(ir)))

        cost_default = est_default.estimate(plan)
        # Default: 200 * 0.325 = 65 output rows
        filter_op_default = cost_default.operation_estimates[1]
        assert filter_op_default.output_rows == 65

        # Override marks > 80 to selectivity 0.10
        store.record_selectivity("students", "marks > 80", 0.10)
        cost_learned = est_adaptive.estimate(plan)
        filter_op_learned = cost_learned.operation_estimates[1]
        assert filter_op_learned.output_rows == 20  # 200 * 0.10


# ===========================================================================
# 5. Pipeline Learning Integration Tests
# ===========================================================================

class TestPipelineFeedbackAndLearning:
    """Test the complete query pipeline with feedback collection and adaptive learning."""

    def test_default_pipeline_has_feedback_but_learning_disabled(self):
        pipeline = QueryPipeline()
        assert not pipeline.learning_enabled
        assert pipeline.adaptive_store is None

        res = pipeline.execute("SELECT name, marks FROM students WHERE marks > 80;")
        assert res.feedback is not None
        assert isinstance(res.feedback, ExecutionFeedback)
        assert res.feedback.selected_plan_id == res.selected_plan_id
        assert len(res.feedback.operation_feedback) > 0

    def test_pipeline_with_enable_learning_learns_across_runs(self):
        # Initialize pipeline with learning enabled
        pipeline = QueryPipeline(enable_learning=True, alpha=0.5)
        assert pipeline.learning_enabled
        assert pipeline.adaptive_store is not None
        assert len(pipeline.adaptive_store) == 0

        query = (
            "SELECT name, marks FROM students "
            "WHERE department = 'CSE' AND marks > 80 "
            "ORDER BY marks DESC;"
        )

        # Run 1: Store is empty, uses static dataset selectivities
        res1 = pipeline.execute(query)
        assert res1.feedback is not None
        # In students dataset:
        # Filter 1 (department = 'CSE'): 200 -> 38 rows (est 38, act 38)
        # Filter 2 (marks > 80): 38 -> 13 rows (est 12, act 13)
        assert len(pipeline.adaptive_store) >= 1

        # Run 2: Store now has learned selectivities!
        res2 = pipeline.execute(query)
        # Query results (rows, columns, row_count) must be identical
        assert res2.columns == res1.columns
        assert res2.rows == res1.rows
        assert res2.row_count == res1.row_count
        assert res2.baseline_matched

    def test_execute_query_helper_function_passes_feedback(self):
        query = "SELECT name FROM students WHERE marks > 90;"
        res = execute_query(query)
        assert res.feedback is not None
        assert res.feedback.query == query
        assert "RUNTIME FEEDBACK & ADAPTATION REPORT" in res.explain()


# ===========================================================================
# 6. Reference Query Verification
# ===========================================================================

class TestReferenceQueryFeedback:
    """
    Detailed verification of runtime feedback on the official project reference query:
        SELECT name, marks
        FROM students
        WHERE department = 'CSE'
        AND marks > 80
        ORDER BY marks DESC;
    """

    QUERY = (
        "SELECT name, marks "
        "FROM students "
        "WHERE department = 'CSE' "
        "AND marks > 80 "
        "ORDER BY marks DESC;"
    )

    def test_reference_query_runtime_feedback_values(self):
        res = execute_query(self.QUERY)
        fb = res.feedback
        assert fb is not None
        assert fb.selected_plan_id == "plan_A"

        # Operations in Plan A:
        # [0] SCAN students
        # [1] FILTER department = 'CSE'
        # [2] FILTER marks > 80
        # [3] PROJECT name, marks
        # [4] SORT marks DESC
        assert len(fb.operation_feedback) == 5

        # Scan
        op_scan = fb.operation_feedback[0]
        assert op_scan.operation_type == "SCAN"
        assert op_scan.estimated_output_rows == 200
        assert op_scan.actual_output_rows == 200
        assert op_scan.absolute_error == 0

        # Filter 1: department = 'CSE'
        op_f1 = fb.operation_feedback[1]
        assert op_f1.operation_type == "FILTER"
        assert op_f1.actual_input_rows == 200
        assert op_f1.estimated_output_rows == 38
        assert op_f1.actual_output_rows == 38
        assert op_f1.difference == 0
        assert op_f1.absolute_error == 0
        assert op_f1.selectivity_feedback is not None
        assert pytest.approx(op_f1.selectivity_feedback.previous_selectivity, 0.001) == 0.19

        # Filter 2: marks > 80
        # In students.csv, exactly 13 students are in CSE with marks > 80
        # The cost estimator estimated 12 rows (independence assumption: 38 * 0.325 = 12.35 -> 12)
        op_f2 = fb.operation_feedback[2]
        assert op_f2.operation_type == "FILTER"
        assert op_f2.actual_input_rows == 38
        assert op_f2.estimated_output_rows == 12
        assert op_f2.actual_output_rows == 13
        assert op_f2.difference == 1
        assert op_f2.absolute_error == 1
        assert pytest.approx(op_f2.relative_error, 0.001) == 1 / 13

        # Check observed selectivity on Filter 2: 13 / 38 = 0.3421
        sf2 = op_f2.selectivity_feedback
        assert sf2 is not None
        assert pytest.approx(sf2.previous_selectivity, 0.001) == 0.325
        assert pytest.approx(sf2.observed_selectivity, 0.001) == 13 / 38
        # Updated selectivity with alpha=0.5: 0.5 * (13/38) + 0.5 * 0.325 = 0.17105 + 0.1625 = 0.33355
        expected_updated = 0.5 * (13 / 38) + 0.5 * 0.325
        assert pytest.approx(sf2.updated_selectivity, 0.001) == expected_updated

        # Project
        op_proj = fb.operation_feedback[3]
        assert op_proj.operation_type == "PROJECT"
        assert op_proj.estimated_input_rows == 12
        assert op_proj.actual_input_rows == 13

        # Sort
        op_sort = fb.operation_feedback[4]
        assert op_sort.operation_type == "SORT"
        assert op_sort.estimated_input_rows == 12
        assert op_sort.actual_input_rows == 13

        # Summary error metrics
        # Absolute errors: scan(0) + f1(0) + f2(1) + proj(1) + sort(1) = 3
        assert fb.total_absolute_error == 3
        assert fb.max_absolute_error == 1

    def test_explain_contains_feedback_report(self):
        res = execute_query(self.QUERY)
        report = res.explain()
        assert "RUNTIME FEEDBACK & ADAPTATION REPORT" in report
        assert "Plan Evaluated: plan_A" in report
        assert "OPERATION ACCURACY ANALYSIS:" in report
        assert "FILTER department = 'CSE'" in report
        assert "FILTER marks > 80" in report
        assert "Learning:" in report
        assert "Total Absolute Output Error:" in report
