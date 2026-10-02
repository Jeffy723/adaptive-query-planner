"""
tests/test_executor.py

Comprehensive tests for the Basic Query Execution Engine.

Covers:
  1. SELECT name FROM students;
  2. SELECT name, marks FROM students;
  3. SELECT * FROM students;
  4. WHERE marks > 80;
  5. WHERE marks >= 90;
  6. WHERE department = 'CSE';
  7. WHERE department != 'CSE';
  8. WHERE department = 'CSE' AND marks > 80;
  9. WHERE department = 'CSE' OR marks > 80;
  10. ORDER BY marks ASC;
  11. ORDER BY marks DESC;
  12. WHERE + PROJECT + SORT;
  13. Reference query (exact verification);
  14. Execution statistics verification;
  15. Pipeline integration (query string -> lexer -> parser -> semantic -> IR -> executor);
  16. Error handling (missing files, malformed rows, unknown tables);
  17. Architectural decoupling (execution from IR without AST/parser).
"""

import csv
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
from backend.ir import (
    LogicalPlan,
    ProjectOp,
    ScanOp,
    SortOp,
    FilterOp,
    IRComparison,
    IRColumnRef,
    IRLiteral,
    IRLiteralType,
    build_ir,
)
from backend.executor import (
    DatasetProvider,
    ExecutionError,
    ExecutionResult,
    Executor,
    OperationStats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_query(query_str: str, data_dir: pathlib.Path | None = None) -> ExecutionResult:
    """Run a query string end-to-end through the full pipeline."""
    tokens = Lexer(query_str).tokenize()
    ast = Parser(tokens).parse()
    semantic_result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
    plan = build_ir(ast, semantic_result)
    executor = Executor(SCHEMA_REGISTRY, data_dir=data_dir)
    return executor.execute(plan)


# ---------------------------------------------------------------------------
# 1. SELECT only (columns & wildcard)
# ---------------------------------------------------------------------------

class TestSelectExecution:
    def test_select_one_column(self) -> None:
        result = run_query("SELECT name FROM students;")
        assert result.row_count == 200
        assert result.columns == ["name"]
        for row in result.rows:
            assert list(row.keys()) == ["name"]
            assert isinstance(row["name"], str)

    def test_select_multiple_columns(self) -> None:
        result = run_query("SELECT name, marks FROM students;")
        assert result.row_count == 200
        assert result.columns == ["name", "marks"]
        for row in result.rows:
            assert list(row.keys()) == ["name", "marks"]
            assert isinstance(row["name"], str)
            assert isinstance(row["marks"], int)

    def test_select_star(self) -> None:
        result = run_query("SELECT * FROM students;")
        assert result.row_count == 200
        assert result.columns == ["id", "name", "department", "semester", "marks"]
        first = result.rows[0]
        assert isinstance(first["id"], int)
        assert isinstance(first["name"], str)
        assert isinstance(first["department"], str)
        assert isinstance(first["semester"], int)
        assert isinstance(first["marks"], int)


# ---------------------------------------------------------------------------
# 2. WHERE filter conditions
# ---------------------------------------------------------------------------

class TestFilterExecution:
    def test_where_marks_gt_80(self) -> None:
        result = run_query("SELECT name, marks FROM students WHERE marks > 80;")
        assert result.row_count == 65
        for row in result.rows:
            assert row["marks"] > 80

    def test_where_marks_gte_90(self) -> None:
        result = run_query("SELECT name, marks FROM students WHERE marks >= 90;")
        assert result.row_count == 34
        for row in result.rows:
            assert row["marks"] >= 90

    def test_where_department_eq_cse(self) -> None:
        result = run_query("SELECT name, department FROM students WHERE department = 'CSE';")
        assert result.row_count == 38
        for row in result.rows:
            assert row["department"] == "CSE"

    def test_where_department_neq_cse(self) -> None:
        result = run_query("SELECT name, department FROM students WHERE department != 'CSE';")
        assert result.row_count == 162
        for row in result.rows:
            assert row["department"] != "CSE"

    def test_where_and_condition(self) -> None:
        result = run_query("SELECT name, department, marks FROM students WHERE department = 'CSE' AND marks > 80;")
        assert result.row_count == 13
        for row in result.rows:
            assert row["department"] == "CSE"
            assert row["marks"] > 80

    def test_where_or_condition(self) -> None:
        result = run_query("SELECT name, department, marks FROM students WHERE department = 'CSE' OR marks > 80;")
        assert result.row_count == 90
        for row in result.rows:
            assert row["department"] == "CSE" or row["marks"] > 80

    @pytest.mark.parametrize("op,expected_count", [
        ("=", 3),    # marks = 80
        ("!=", 197), # marks != 80
        (">", 65),   # marks > 80
        ("<", 132),  # marks < 80
        (">=", 68),  # marks >= 80
        ("<=", 135), # marks <= 80
    ])
    def test_comparison_operators(self, op: str, expected_count: int) -> None:
        result = run_query(f"SELECT * FROM students WHERE marks {op} 80;")
        assert result.row_count == expected_count

    def test_where_no_matching_rows(self) -> None:
        result = run_query("SELECT name, marks FROM students WHERE marks > 1000;")
        assert result.row_count == 0
        assert result.rows == []
        assert result.columns == ["name", "marks"]

    def test_where_chained_and(self) -> None:
        result = run_query("SELECT name, semester, marks FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;")
        assert result.row_count > 0
        for row in result.rows:
            assert row["semester"] == 3
            assert 70 <= row["marks"] <= 90


# ---------------------------------------------------------------------------
# 3. ORDER BY sorting
# ---------------------------------------------------------------------------

class TestSortExecution:
    def test_order_by_marks_asc(self) -> None:
        result = run_query("SELECT name, marks FROM students ORDER BY marks ASC;")
        assert result.row_count == 200
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list)

    def test_order_by_marks_desc(self) -> None:
        result = run_query("SELECT name, marks FROM students ORDER BY marks DESC;")
        assert result.row_count == 200
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list, reverse=True)

    def test_order_by_default_asc(self) -> None:
        result = run_query("SELECT name, semester FROM students ORDER BY semester;")
        assert result.row_count == 200
        semesters = [r["semester"] for r in result.rows]
        assert semesters == sorted(semesters)

    def test_order_by_string_column(self) -> None:
        result = run_query("SELECT name FROM students ORDER BY name ASC;")
        assert result.row_count == 200
        names = [r["name"] for r in result.rows]
        assert names == sorted(names)

    def test_order_by_non_projected_column(self) -> None:
        """Sorting by a column that is not part of the final SELECT list."""
        result = run_query("SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC;")
        assert result.row_count == 65
        assert result.columns == ["name"]
        for row in result.rows:
            assert list(row.keys()) == ["name"]
        # Alan scored 100, which is top marks
        assert result.rows[0]["name"] == "Alan"


# ---------------------------------------------------------------------------
# 4. WHERE + PROJECT + SORT
# ---------------------------------------------------------------------------

class TestWhereProjectSort:
    def test_where_project_sort(self) -> None:
        result = run_query("SELECT name, marks FROM students WHERE semester = 1 ORDER BY marks DESC;")
        assert result.row_count > 0
        assert result.columns == ["name", "marks"]
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list, reverse=True)


# ---------------------------------------------------------------------------
# 5. Reference query
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQueryExecution:
    def test_reference_query_results(self) -> None:
        result = run_query(REFERENCE_QUERY)

        assert result.row_count == 13
        assert result.columns == ["name", "marks"]

        # Validate all rows satisfy WHERE conditions
        for row in result.rows:
            assert row["marks"] > 80

        # Validate sorting is descending by marks
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list, reverse=True)

        # Expected sequence from data/students.csv
        expected_names = [
            "Donna", "Brenda", "Sam", "Isla", "Umar",
            "Carlos", "Harsh", "Alice", "Tarun", "Victor",
            "Judy", "Zaid", "Eve"
        ]
        actual_names = [r["name"] for r in result.rows]
        assert actual_names == expected_names

        # Verify marks values
        assert result.rows[0] == {"name": "Donna", "marks": 96}
        assert result.rows[1] == {"name": "Brenda", "marks": 96}
        assert result.rows[-1] == {"name": "Eve", "marks": 82}


# ---------------------------------------------------------------------------
# 6. Execution statistics
# ---------------------------------------------------------------------------

class TestExecutionStatistics:
    def test_stats_recorded_for_each_operation(self) -> None:
        result = run_query(REFERENCE_QUERY)
        assert len(result.stats) == 4

        scan_stat = result.stats[0]
        assert scan_stat.operation_type == "SCAN"
        assert scan_stat.input_rows == 0
        assert scan_stat.output_rows == 200

        filter_stat = result.stats[1]
        assert filter_stat.operation_type == "FILTER"
        assert filter_stat.input_rows == 200
        assert filter_stat.output_rows == 13

        project_stat = result.stats[2]
        assert project_stat.operation_type == "PROJECT"
        assert project_stat.input_rows == 13
        assert project_stat.output_rows == 13

        sort_stat = result.stats[3]
        assert sort_stat.operation_type == "SORT"
        assert sort_stat.input_rows == 13
        assert sort_stat.output_rows == 13

    def test_explain_stats_format(self) -> None:
        result = run_query(REFERENCE_QUERY)
        text = result.explain_stats()
        assert "SCAN students" in text
        assert "input:  0" in text
        assert "output: 200" in text
        assert "FILTER" in text
        assert "PROJECT name, marks" in text
        assert "SORT marks DESC" in text

    def test_stats_for_simple_select(self) -> None:
        result = run_query("SELECT name FROM students;")
        assert len(result.stats) == 2
        assert result.stats[0].operation_type == "SCAN"
        assert result.stats[0].output_rows == 200
        assert result.stats[1].operation_type == "PROJECT"
        assert result.stats[1].input_rows == 200
        assert result.stats[1].output_rows == 200


# ---------------------------------------------------------------------------
# 7. Error handling & dataset validation
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_missing_dataset_file(self, tmp_path: pathlib.Path) -> None:
        provider = DatasetProvider(data_dir=tmp_path)
        executor = Executor(SCHEMA_REGISTRY, dataset_provider=provider)
        plan = LogicalPlan(
            operations=(
                ScanOp("students"),
                ProjectOp(("name",)),
            ),
            source_table="students",
        )
        with pytest.raises(ExecutionError) as exc_info:
            executor.execute(plan)
        assert "not found" in str(exc_info.value).lower()

    def test_unknown_table_in_scan(self) -> None:
        executor = Executor(SCHEMA_REGISTRY)
        plan = LogicalPlan(
            operations=(
                ScanOp("unknown_table"),
                ProjectOp(("name",)),
            ),
            source_table="unknown_table",
        )
        with pytest.raises(ExecutionError) as exc_info:
            executor.execute(plan)
        assert "unknown table" in str(exc_info.value).lower()

    def test_corrupted_integer_in_csv(self, tmp_path: pathlib.Path) -> None:
        bad_csv = tmp_path / "students.csv"
        bad_csv.write_text("id,name,department,semester,marks\n1,Alice,CSE,1,not_a_number\n", encoding="utf-8")
        provider = DatasetProvider(data_dir=tmp_path)
        executor = Executor(SCHEMA_REGISTRY, dataset_provider=provider)
        plan = LogicalPlan(
            operations=(
                ScanOp("students"),
                ProjectOp(("name", "marks")),
            ),
            source_table="students",
        )
        with pytest.raises(ExecutionError) as exc_info:
            executor.execute(plan)
        assert "cannot convert" in str(exc_info.value).lower() or "integer" in str(exc_info.value).lower()

    def test_missing_non_nullable_value(self, tmp_path: pathlib.Path) -> None:
        bad_csv = tmp_path / "students.csv"
        bad_csv.write_text("id,name,department,semester,marks\n1,,CSE,1,80\n", encoding="utf-8")
        provider = DatasetProvider(data_dir=tmp_path)
        executor = Executor(SCHEMA_REGISTRY, dataset_provider=provider)
        plan = LogicalPlan(
            operations=(
                ScanOp("students"),
                ProjectOp(("id", "name")),
            ),
            source_table="students",
        )
        with pytest.raises(ExecutionError) as exc_info:
            executor.execute(plan)
        assert "missing value" in str(exc_info.value).lower()

    def test_csv_header_mismatch(self, tmp_path: pathlib.Path) -> None:
        bad_csv = tmp_path / "students.csv"
        bad_csv.write_text("id,name,wrong_col,semester,marks\n1,Alice,CSE,1,80\n", encoding="utf-8")
        provider = DatasetProvider(data_dir=tmp_path)
        executor = Executor(SCHEMA_REGISTRY, dataset_provider=provider)
        plan = LogicalPlan(
            operations=(
                ScanOp("students"),
                ProjectOp(("name",)),
            ),
            source_table="students",
        )
        with pytest.raises(ExecutionError) as exc_info:
            executor.execute(plan)
        assert "header" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 8. Decoupled execution & API flexibility
# ---------------------------------------------------------------------------

class TestDecoupledExecution:
    def test_execute_manually_built_plan(self) -> None:
        """The executor can run plans constructed directly without parser or AST."""
        plan = LogicalPlan(
            operations=(
                ScanOp("students"),
                FilterOp(
                    IRComparison(
                        column=IRColumnRef("department"),
                        operator="=",
                        value=IRLiteral("IT", IRLiteralType.STRING),
                    )
                ),
                ProjectOp(("name", "marks")),
                SortOp(column="marks", direction="DESC"),
            ),
            source_table="students",
        )
        executor = Executor(SCHEMA_REGISTRY)
        result = executor.execute(plan)
        assert result.row_count > 0
        assert result.columns == ["name", "marks"]
        marks_list = [r["marks"] for r in result.rows]
        assert marks_list == sorted(marks_list, reverse=True)

    def test_constructor_with_dataset_provider_directly(self) -> None:
        provider = DatasetProvider()
        executor = Executor(provider)
        plan = LogicalPlan(
            operations=(
                ScanOp("students"),
                ProjectOp(("name",)),
            ),
            source_table="students",
        )
        result = executor.execute(plan)
        assert result.row_count == 200

    def test_custom_table_schema_and_data(self, tmp_path: pathlib.Path) -> None:
        courses_csv = tmp_path / "courses.csv"
        courses_csv.write_text("course_id,title,credits\n101,Math,4\n102,Physics,3\n", encoding="utf-8")
        courses_schema = TableSchema(
            table_name="courses",
            columns=(
                ColumnMeta("course_id", ColumnType.INTEGER),
                ColumnMeta("title", ColumnType.STRING),
                ColumnMeta("credits", ColumnType.INTEGER),
            ),
        )
        registry = {"courses": courses_schema}
        provider = DatasetProvider(data_dir=tmp_path)
        executor = Executor(registry, dataset_provider=provider)

        plan = LogicalPlan(
            operations=(
                ScanOp("courses"),
                FilterOp(
                    IRComparison(
                        column=IRColumnRef("credits"),
                        operator=">",
                        value=IRLiteral(3, IRLiteralType.INTEGER),
                    )
                ),
                ProjectOp(("title", "credits")),
            ),
            source_table="courses",
        )
        result = executor.execute(plan)
        assert result.row_count == 1
        assert result.rows[0] == {"title": "Math", "credits": 4}

    def test_execution_result_string_representation(self) -> None:
        result = run_query("SELECT name FROM students WHERE marks > 95;")
        text = str(result)
        assert "ExecutionResult" in text
        assert "columns: name" in text
