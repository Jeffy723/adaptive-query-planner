"""
tests/test_end_to_end.py

Comprehensive tests for the End-to-End Query Execution Pipeline and
Baseline Correctness Verification.

Covers:
  1. Simple SELECT.
  2. SELECT with one WHERE.
  3. SELECT with multiple AND predicates.
  4. SELECT with OR.
  5. SELECT with ORDER BY.
  6. Reference query end-to-end execution and report.
  7. Query with no alternative plans (1 plan).
  8. Query with multiple alternative plans (2 and 6 plans).
  9. Selected plan is actually executed.
  10. Selected plan result equals logical baseline result:
      - same columns
      - same rows
      - same row count
      - same order (for ORDER BY queries).
  11. Selected cost matches the cost estimator.
  12. Selected plan belongs to the generated plan set.
  13. Repeated execution is deterministic.
  14. Error handling:
      - syntax error -> LexerError / ParseError
      - semantic error -> PipelineError
      - result mismatch -> ResultMismatchError.
  15. Formatted explain output validation.
"""

import pytest

from backend.lexer import LexerError
from backend.parser import ParseError
from backend.pipeline import (
    PipelineError,
    QueryPipeline,
    QueryResult,
    ResultMismatchError,
    execute_query,
)


REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


# ---------------------------------------------------------------------------
# 1. Simple SELECT
# ---------------------------------------------------------------------------

class TestSimpleSelectPipeline:
    def test_simple_select_execution(self) -> None:
        result = execute_query("SELECT name FROM students;")
        assert isinstance(result, QueryResult)
        assert result.row_count == 200
        assert result.columns == ["name"]
        assert len(result.candidate_plans) == 1
        assert result.selected_plan_id == "plan_A"
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows


# ---------------------------------------------------------------------------
# 2. SELECT with one WHERE
# ---------------------------------------------------------------------------

class TestSingleWherePipeline:
    def test_single_where_execution(self) -> None:
        result = execute_query("SELECT name, marks FROM students WHERE marks > 80;")
        assert result.row_count == 65
        assert result.columns == ["name", "marks"]
        assert len(result.candidate_plans) == 1
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows
        for row in result.rows:
            assert row["marks"] > 80


# ---------------------------------------------------------------------------
# 3. SELECT with multiple AND predicates
# ---------------------------------------------------------------------------

class TestMultipleAndPipeline:
    def test_two_and_predicates_execution(self) -> None:
        query = "SELECT name, department, marks FROM students WHERE department = 'CSE' AND marks > 80;"
        result = execute_query(query)

        assert result.row_count == 13
        assert len(result.candidate_plans) == 2
        assert result.selected_plan_id == "plan_A"
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows

    def test_three_and_predicates_execution(self) -> None:
        query = "SELECT name, semester, marks FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        result = execute_query(query)

        assert result.row_count > 0
        assert len(result.candidate_plans) == 6
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows


# ---------------------------------------------------------------------------
# 4. SELECT with OR
# ---------------------------------------------------------------------------

class TestOrConditionPipeline:
    def test_or_query_execution(self) -> None:
        query = "SELECT name, department, marks FROM students WHERE department = 'CSE' OR marks > 80;"
        result = execute_query(query)

        assert result.row_count == 90
        assert len(result.candidate_plans) == 1
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows


# ---------------------------------------------------------------------------
# 5. SELECT with ORDER BY
# ---------------------------------------------------------------------------

class TestOrderByPipeline:
    def test_order_by_desc_execution(self) -> None:
        query = "SELECT name, marks FROM students ORDER BY marks DESC;"
        result = execute_query(query)

        assert result.row_count == 200
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list, reverse=True)

    def test_order_by_asc_execution(self) -> None:
        query = "SELECT name, marks FROM students ORDER BY marks ASC;"
        result = execute_query(query)

        assert result.row_count == 200
        assert result.baseline_matched is True
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list)


# ---------------------------------------------------------------------------
# 6. Reference Query End-to-End
# ---------------------------------------------------------------------------

class TestReferenceQueryPipeline:
    def test_reference_query_full_pipeline(self) -> None:
        result = execute_query(REFERENCE_QUERY)

        # 1. Output dimensions
        assert result.row_count == 13
        assert result.columns == ["name", "marks"]

        # 2. Plans and costs
        assert len(result.candidate_plans) == 2
        assert "plan_A" in result.plan_costs
        assert "plan_B" in result.plan_costs
        assert result.plan_costs["plan_A"] == 493.02
        assert result.plan_costs["plan_B"] == 520.02

        # 3. Plan selection
        assert result.selected_plan_id == "plan_A"
        assert result.selected_cost == 493.02
        assert result.selected_plan == result.candidate_plans[0]

        # 4. Correctness verification against logical baseline
        assert result.baseline_matched is True
        assert result.rows == result.baseline_result.rows
        assert result.columns == result.baseline_result.columns
        assert result.row_count == result.baseline_result.row_count

        # 5. Ordered tuples check
        expected_names = [
            "Donna", "Brenda", "Sam", "Isla", "Umar",
            "Carlos", "Harsh", "Alice", "Tarun", "Victor",
            "Judy", "Zaid", "Eve",
        ]
        actual_names = [r["name"] for r in result.rows]
        assert actual_names == expected_names

        # 6. Execution statistics present
        assert len(result.execution_stats) == 5
        ops = [s.operation.split()[0] for s in result.execution_stats]
        assert ops == ["SCAN", "FILTER", "FILTER", "PROJECT", "SORT"]


# ---------------------------------------------------------------------------
# 7 & 8. Alternative plan counts
# ---------------------------------------------------------------------------

class TestAlternativePlansCount:
    def test_unfiltered_query_has_one_plan(self) -> None:
        result = execute_query("SELECT id FROM students;")
        assert len(result.candidate_plans) == 1

    def test_two_filters_has_two_plans(self) -> None:
        result = execute_query("SELECT name FROM students WHERE department = 'CSE' AND semester = 1;")
        assert len(result.candidate_plans) == 2

    def test_three_filters_has_six_plans(self) -> None:
        result = execute_query("SELECT name FROM students WHERE department = 'CSE' AND semester = 1 AND marks > 50;")
        assert len(result.candidate_plans) == 6


# ---------------------------------------------------------------------------
# 9 & 10. Selected plan execution and baseline equivalence
# ---------------------------------------------------------------------------

class TestBaselineEquivalence:
    @pytest.mark.parametrize("query", [
        "SELECT name FROM students;",
        "SELECT name, marks FROM students WHERE marks >= 90;",
        "SELECT department, name FROM students WHERE department != 'CSE';",
        "SELECT name, marks FROM students WHERE department = 'IT' AND marks >= 80;",
        "SELECT name, marks FROM students WHERE department = 'CSE' OR marks > 80;",
        "SELECT name, semester, marks FROM students WHERE semester = 2 ORDER BY marks DESC;",
        REFERENCE_QUERY,
    ])
    def test_physical_plan_matches_logical_baseline(self, query: str) -> None:
        result = execute_query(query, verify_baseline=True)
        assert result.baseline_matched is True
        assert result.columns == result.baseline_result.columns
        assert result.row_count == result.baseline_result.row_count
        assert result.rows == result.baseline_result.rows


# ---------------------------------------------------------------------------
# 11 & 12. Selected cost and plan identity
# ---------------------------------------------------------------------------

class TestSelectedPlanIntegrity:
    def test_selected_cost_matches_cost_estimate(self) -> None:
        result = execute_query(REFERENCE_QUERY)
        matching_est = next(est for est in result.cost_estimates if est.plan_id == result.selected_plan_id)
        assert result.selected_cost == matching_est.total_cost

    def test_selected_plan_is_member_of_candidate_plans(self) -> None:
        result = execute_query(REFERENCE_QUERY)
        assert result.selected_plan in result.candidate_plans


# ---------------------------------------------------------------------------
# 13. Determinism
# ---------------------------------------------------------------------------

class TestPipelineDeterminism:
    def test_repeated_runs_produce_identical_results(self) -> None:
        r1 = execute_query(REFERENCE_QUERY)
        r2 = execute_query(REFERENCE_QUERY)
        r3 = execute_query(REFERENCE_QUERY)

        assert r1.selected_plan_id == r2.selected_plan_id == r3.selected_plan_id
        assert r1.selected_cost == r2.selected_cost == r3.selected_cost
        assert r1.rows == r2.rows == r3.rows


# ---------------------------------------------------------------------------
# 14. Error handling
# ---------------------------------------------------------------------------

class TestPipelineErrorHandling:
    def test_syntax_error_raises_parse_error(self) -> None:
        with pytest.raises(ParseError):
            execute_query("SELECT FROM students;")

    def test_lexer_error_raises_lexer_error(self) -> None:
        with pytest.raises(LexerError):
            execute_query("SELECT 80abc FROM students;")

    def test_unknown_table_raises_pipeline_error(self) -> None:
        with pytest.raises(PipelineError) as exc_info:
            execute_query("SELECT name FROM teachers;")
        assert "semantic" in str(exc_info.value).lower()
        assert "teachers" in str(exc_info.value).lower()

    def test_unknown_column_raises_pipeline_error(self) -> None:
        with pytest.raises(PipelineError) as exc_info:
            execute_query("SELECT salary FROM students;")
        assert "salary" in str(exc_info.value).lower()

    def test_result_mismatch_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Simulate a result mismatch to verify ResultMismatchError is raised."""
        from backend.executor.result import ExecutionResult

        pipeline = QueryPipeline()

        # Mock executor to return a corrupted execution result
        orig_exec = pipeline._executor.execute

        def mock_execute(plan):
            real_res = orig_exec(plan)
            # If it's a physical plan, tamper with one row to trigger mismatch
            if hasattr(plan, "to_logical") or hasattr(plan, "filter_order"):
                tampered_rows = list(real_res.rows)
                if tampered_rows:
                    tampered_rows[0] = {"tampered": 999}
                return ExecutionResult(columns=real_res.columns, rows=tampered_rows, row_count=len(tampered_rows))
            return real_res

        monkeypatch.setattr(pipeline._executor, "execute", mock_execute)

        with pytest.raises(ResultMismatchError) as exc_info:
            pipeline.execute(REFERENCE_QUERY, verify_baseline=True)
        assert "verification failed" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 15. Formatted report output
# ---------------------------------------------------------------------------

class TestReportOutput:
    def test_explain_contains_all_demonstration_sections(self) -> None:
        result = execute_query(REFERENCE_QUERY)
        report = result.explain()

        assert "QUERY:" in report
        assert "LOGICAL PLAN:" in report
        assert "SCAN students" in report
        assert "ALTERNATIVE PLANS & ESTIMATED COSTS" in report
        assert "plan_A" in report
        assert "plan_B" in report
        assert "SELECTED PLAN:" in report
        assert "plan_A" in report
        assert "EXECUTION RESULT:" in report
        assert "Rows returned: 13" in report
        assert "Execution Statistics:" in report
        assert "CORRECTNESS VERIFICATION:" in report
        assert "YES" in report
