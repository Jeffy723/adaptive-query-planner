"""
tests/test_ir.py

Comprehensive tests for the Query IR (Logical Intermediate Representation)
and the AST → IR transformation.

Covers all 10 required cases plus:
  - Operation ordering is always SCAN → FILTER → PROJECT → [SORT]
  - Predicate structure mirrors AST left-to-right logical structure
  - IRLiteral types are correctly tagged (INTEGER / STRING)
  - LogicalPlan.explain() produces readable output
  - Convenience accessors (.scan, .filter, .project, .sort)
  - IRBuildError raised on invalid semantic result
  - Full pipeline integration: query string → lexer → parser → semantic → IR
  - LogicalPlan immutability
"""

import pytest

from backend.ir import (
    FilterOp,
    IRBuildError,
    IRColumnRef,
    IRComparison,
    IRLiteral,
    IRLiteralType,
    IRLogicalExpr,
    LogicalPlan,
    ProjectOp,
    ScanOp,
    SortOp,
    build_ir,
)
from backend.lexer    import Lexer
from backend.parser   import Parser
from backend.schema   import SCHEMA_REGISTRY
from backend.semantic import SemanticAnalyzer


# ---------------------------------------------------------------------------
# Pipeline helper
# ---------------------------------------------------------------------------

def full_pipeline(query_str: str) -> LogicalPlan:
    """Run query_str through the complete pipeline and return a LogicalPlan."""
    tokens  = Lexer(query_str).tokenize()
    ast     = Parser(tokens).parse()
    sem     = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
    return build_ir(ast, sem)


def full_pipeline_sem(query_str: str):
    """Return (ast, sem_result) for cases where we need both."""
    tokens = Lexer(query_str).tokenize()
    ast    = Parser(tokens).parse()
    sem    = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
    return ast, sem


# ---------------------------------------------------------------------------
# 1. SELECT only (no WHERE, no ORDER BY)
# ---------------------------------------------------------------------------

class TestSelectOnly:
    def test_returns_logical_plan(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert isinstance(plan, LogicalPlan)

    def test_two_operations(self) -> None:
        # SCAN + PROJECT
        plan = full_pipeline("SELECT name FROM students;")
        assert len(plan.operations) == 2

    def test_first_op_is_scan(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert isinstance(plan.operations[0], ScanOp)

    def test_scan_table_name(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert plan.scan.table_name == "students"

    def test_second_op_is_project(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert isinstance(plan.operations[1], ProjectOp)

    def test_project_columns(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert plan.project.columns == ("name",)

    def test_no_filter(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert plan.filter is None

    def test_no_sort(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert plan.sort is None

    def test_source_table(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert plan.source_table == "students"


# ---------------------------------------------------------------------------
# 2. SELECT * (wildcard)
# ---------------------------------------------------------------------------

class TestSelectStar:
    def test_project_expands_star(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        # Wildcard must be expanded to all schema columns
        assert plan.project.columns == (
            "id", "name", "department", "semester", "marks"
        )

    def test_no_filter_for_star(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        assert plan.filter is None

    def test_two_operations(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        assert len(plan.operations) == 2


# ---------------------------------------------------------------------------
# 3. SELECT with one WHERE condition
# ---------------------------------------------------------------------------

class TestWhereOneCondition:
    def test_three_operations(self) -> None:
        # SCAN + FILTER + PROJECT
        plan = full_pipeline("SELECT name FROM students WHERE marks > 80;")
        assert len(plan.operations) == 3

    def test_operation_order(self) -> None:
        plan = full_pipeline("SELECT name FROM students WHERE marks > 80;")
        assert isinstance(plan.operations[0], ScanOp)
        assert isinstance(plan.operations[1], FilterOp)
        assert isinstance(plan.operations[2], ProjectOp)

    def test_filter_is_comparison(self) -> None:
        plan = full_pipeline("SELECT name FROM students WHERE marks > 80;")
        assert isinstance(plan.filter.predicate, IRComparison)

    def test_comparison_column(self) -> None:
        plan = full_pipeline("SELECT name FROM students WHERE marks > 80;")
        cmp = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.column.name == "marks"

    def test_comparison_operator(self) -> None:
        plan = full_pipeline("SELECT name FROM students WHERE marks > 80;")
        cmp = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.operator == ">"

    def test_comparison_value(self) -> None:
        plan = full_pipeline("SELECT name FROM students WHERE marks > 80;")
        cmp = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.value.value == 80
        assert cmp.value.literal_type == IRLiteralType.INTEGER

    def test_string_literal(self) -> None:
        plan = full_pipeline("SELECT name FROM students WHERE department = 'CSE';")
        cmp = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.value.value == "CSE"
        assert cmp.value.literal_type == IRLiteralType.STRING


# ---------------------------------------------------------------------------
# 4. SELECT with multiple AND conditions
# ---------------------------------------------------------------------------

class TestWhereAndConditions:
    def test_filter_is_logical(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE department = 'CSE' AND marks > 80;"
        )
        assert isinstance(plan.filter.predicate, IRLogicalExpr)

    def test_logical_operator_and(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE department = 'CSE' AND marks > 80;"
        )
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        assert expr.operator == "AND"

    def test_left_comparison(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE department = 'CSE' AND marks > 80;"
        )
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        left = expr.left
        assert isinstance(left, IRComparison)
        assert left.column.name == "department"
        assert left.value.value == "CSE"

    def test_right_comparison(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE department = 'CSE' AND marks > 80;"
        )
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        right = expr.right
        assert isinstance(right, IRComparison)
        assert right.column.name == "marks"
        assert right.value.value == 80

    def test_three_ands_left_assoc(self) -> None:
        """A AND B AND C => IRLogicalExpr(IRLogicalExpr(A,AND,B), AND, C)"""
        plan = full_pipeline(
            "SELECT name FROM students "
            "WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        )
        root = plan.filter.predicate
        assert isinstance(root, IRLogicalExpr)
        assert root.operator == "AND"
        # Left of root is another AND
        assert isinstance(root.left, IRLogicalExpr)
        assert root.left.operator == "AND"


# ---------------------------------------------------------------------------
# 5. SELECT with OR conditions
# ---------------------------------------------------------------------------

class TestWhereOrConditions:
    def test_logical_operator_or(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students "
            "WHERE department = 'CSE' OR department = 'ECE';"
        )
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        assert expr.operator == "OR"

    def test_or_both_sides_comparisons(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students "
            "WHERE department = 'CSE' OR department = 'ECE';"
        )
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        assert isinstance(expr.left,  IRComparison)
        assert isinstance(expr.right, IRComparison)
        assert expr.left.value.value  == "CSE"
        assert expr.right.value.value == "ECE"


# ---------------------------------------------------------------------------
# 6. SELECT with ORDER BY ASC
# ---------------------------------------------------------------------------

class TestOrderByAsc:
    def test_three_operations(self) -> None:
        # SCAN + PROJECT + SORT
        plan = full_pipeline("SELECT * FROM students ORDER BY marks ASC;")
        assert len(plan.operations) == 3

    def test_operation_order(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks ASC;")
        assert isinstance(plan.operations[0], ScanOp)
        assert isinstance(plan.operations[1], ProjectOp)
        assert isinstance(plan.operations[2], SortOp)

    def test_sort_column(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks ASC;")
        assert plan.sort.column == "marks"

    def test_sort_direction_asc(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks ASC;")
        assert plan.sort.direction == "ASC"

    def test_sort_default_asc(self) -> None:
        """When no direction is written the parser defaults to ASC."""
        plan = full_pipeline("SELECT * FROM students ORDER BY semester;")
        assert plan.sort.direction == "ASC"


# ---------------------------------------------------------------------------
# 7. SELECT with ORDER BY DESC
# ---------------------------------------------------------------------------

class TestOrderByDesc:
    def test_sort_direction_desc(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks DESC;")
        assert plan.sort.direction == "DESC"

    def test_sort_column_desc(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY semester DESC;")
        assert plan.sort.column == "semester"


# ---------------------------------------------------------------------------
# 8. SELECT with WHERE + ORDER BY
# ---------------------------------------------------------------------------

class TestWhereAndOrderBy:
    def test_four_operations(self) -> None:
        # SCAN + FILTER + PROJECT + SORT
        plan = full_pipeline(
            "SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC;"
        )
        assert len(plan.operations) == 4

    def test_operation_order(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC;"
        )
        assert isinstance(plan.operations[0], ScanOp)
        assert isinstance(plan.operations[1], FilterOp)
        assert isinstance(plan.operations[2], ProjectOp)
        assert isinstance(plan.operations[3], SortOp)

    def test_filter_and_sort_present(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC;"
        )
        assert plan.filter is not None
        assert plan.sort   is not None

    def test_correct_filter(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC;"
        )
        cmp = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.operator == ">"
        assert cmp.value.value == 80

    def test_correct_sort(self) -> None:
        plan = full_pipeline(
            "SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC;"
        )
        assert plan.sort.column    == "marks"
        assert plan.sort.direction == "DESC"


# ---------------------------------------------------------------------------
# 9. Reference query — full structural assertion
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQuery:
    def test_returns_plan(self) -> None:
        assert isinstance(full_pipeline(REFERENCE_QUERY), LogicalPlan)

    def test_four_operations(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        assert len(plan.operations) == 4

    def test_scan(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        assert plan.scan.table_name == "students"

    def test_filter_is_logical_and(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        assert expr.operator == "AND"

    def test_filter_left(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        left = expr.left
        assert isinstance(left, IRComparison)
        assert left.column.name  == "department"
        assert left.operator     == "="
        assert left.value.value  == "CSE"
        assert left.value.literal_type == IRLiteralType.STRING

    def test_filter_right(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        expr = plan.filter.predicate
        assert isinstance(expr, IRLogicalExpr)
        right = expr.right
        assert isinstance(right, IRComparison)
        assert right.column.name  == "marks"
        assert right.operator     == ">"
        assert right.value.value  == 80
        assert right.value.literal_type == IRLiteralType.INTEGER

    def test_project_columns(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        assert plan.project.columns == ("name", "marks")

    def test_sort(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        assert plan.sort.column    == "marks"
        assert plan.sort.direction == "DESC"

    def test_explain_contains_all_ops(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        text = plan.explain()
        assert "SCAN"    in text
        assert "FILTER"  in text
        assert "PROJECT" in text
        assert "SORT"    in text

    def test_explain_output(self) -> None:
        plan    = full_pipeline(REFERENCE_QUERY)
        lines   = plan.explain().splitlines()
        assert lines[0].startswith("SCAN")
        assert lines[1].startswith("FILTER")
        assert lines[2].startswith("PROJECT")
        assert lines[3].startswith("SORT")

    def test_str_same_as_explain(self) -> None:
        plan = full_pipeline(REFERENCE_QUERY)
        assert str(plan) == plan.explain()


# ---------------------------------------------------------------------------
# 10. Invalid semantic query must not produce a valid IR
# ---------------------------------------------------------------------------

class TestInvalidQueryRejected:
    def test_unknown_table_raises(self) -> None:
        tokens = Lexer("SELECT name FROM teachers;").tokenize()
        ast    = Parser(tokens).parse()
        sem    = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert not sem.valid
        with pytest.raises(IRBuildError) as exc_info:
            build_ir(ast, sem)
        assert "invalid" in str(exc_info.value).lower() or \
               "error"   in str(exc_info.value).lower()

    def test_unknown_column_raises(self) -> None:
        tokens = Lexer("SELECT salary FROM students;").tokenize()
        ast    = Parser(tokens).parse()
        sem    = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert not sem.valid
        with pytest.raises(IRBuildError):
            build_ir(ast, sem)

    def test_type_mismatch_raises(self) -> None:
        tokens = Lexer("SELECT name FROM students WHERE marks > 'hello';").tokenize()
        ast    = Parser(tokens).parse()
        sem    = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert not sem.valid
        with pytest.raises(IRBuildError):
            build_ir(ast, sem)

    def test_irbuild_error_has_message(self) -> None:
        tokens = Lexer("SELECT salary FROM students;").tokenize()
        ast    = Parser(tokens).parse()
        sem    = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        with pytest.raises(IRBuildError) as exc_info:
            build_ir(ast, sem)
        err = exc_info.value
        assert err.message != ""
        assert "salary" in err.message or "invalid" in err.message.lower()


# ---------------------------------------------------------------------------
# 11. All operator variants produce correct IRComparisons
# ---------------------------------------------------------------------------

class TestAllComparisonOperators:
    @pytest.mark.parametrize("op", ["=", "!=", ">", "<", ">=", "<="])
    def test_integer_operators(self, op: str) -> None:
        plan = full_pipeline(f"SELECT * FROM students WHERE marks {op} 80;")
        cmp  = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.operator == op

    def test_string_eq(self) -> None:
        plan = full_pipeline("SELECT * FROM students WHERE department = 'CSE';")
        cmp  = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.operator == "="

    def test_string_neq(self) -> None:
        plan = full_pipeline("SELECT * FROM students WHERE department != 'ME';")
        cmp  = plan.filter.predicate
        assert isinstance(cmp, IRComparison)
        assert cmp.operator == "!="


# ---------------------------------------------------------------------------
# 12. Explain / __str__ output format
# ---------------------------------------------------------------------------

class TestExplainOutput:
    def test_scan_str(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        assert str(plan.scan) == "SCAN students"

    def test_project_str_named(self) -> None:
        plan = full_pipeline("SELECT name, marks FROM students;")
        assert str(plan.project) == "PROJECT name, marks"

    def test_project_str_star(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        s = str(plan.project)
        assert s.startswith("PROJECT ")
        assert "id" in s   # expanded

    def test_filter_str_comparison(self) -> None:
        plan = full_pipeline("SELECT * FROM students WHERE marks > 80;")
        assert str(plan.filter) == "FILTER marks > 80"

    def test_filter_str_string_literal(self) -> None:
        plan = full_pipeline("SELECT * FROM students WHERE department = 'CSE';")
        assert str(plan.filter) == "FILTER department = 'CSE'"

    def test_sort_str_desc(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks DESC;")
        assert str(plan.sort) == "SORT marks DESC"

    def test_sort_str_asc(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks ASC;")
        assert str(plan.sort) == "SORT marks ASC"

    def test_ir_comparison_str(self) -> None:
        cmp = IRComparison(
            column=IRColumnRef("marks"),
            operator=">",
            value=IRLiteral(80, IRLiteralType.INTEGER),
        )
        assert str(cmp) == "marks > 80"

    def test_ir_logical_expr_str(self) -> None:
        left  = IRComparison(IRColumnRef("department"), "=",
                             IRLiteral("CSE", IRLiteralType.STRING))
        right = IRComparison(IRColumnRef("marks"), ">",
                             IRLiteral(80, IRLiteralType.INTEGER))
        expr  = IRLogicalExpr(left=left, operator="AND", right=right)
        s     = str(expr)
        assert "AND" in s
        assert "department" in s
        assert "marks" in s

    def test_ir_literal_string_str(self) -> None:
        lit = IRLiteral("CSE", IRLiteralType.STRING)
        assert str(lit) == "'CSE'"

    def test_ir_literal_integer_str(self) -> None:
        lit = IRLiteral(80, IRLiteralType.INTEGER)
        assert str(lit) == "80"


# ---------------------------------------------------------------------------
# 13. LogicalPlan convenience accessors
# ---------------------------------------------------------------------------

class TestLogicalPlanAccessors:
    def test_scan_accessor(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        assert isinstance(plan.scan, ScanOp)

    def test_filter_accessor_none(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        assert plan.filter is None

    def test_filter_accessor_present(self) -> None:
        plan = full_pipeline("SELECT * FROM students WHERE marks > 80;")
        assert isinstance(plan.filter, FilterOp)

    def test_project_accessor(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        assert isinstance(plan.project, ProjectOp)

    def test_sort_accessor_none(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        assert plan.sort is None

    def test_sort_accessor_present(self) -> None:
        plan = full_pipeline("SELECT * FROM students ORDER BY marks DESC;")
        assert isinstance(plan.sort, SortOp)


# ---------------------------------------------------------------------------
# 14. LogicalPlan is immutable
# ---------------------------------------------------------------------------

class TestLogicalPlanImmutability:
    def test_plan_frozen(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        with pytest.raises((AttributeError, TypeError)):
            plan.source_table = "courses"  # type: ignore[misc]

    def test_scan_op_frozen(self) -> None:
        plan = full_pipeline("SELECT * FROM students;")
        with pytest.raises((AttributeError, TypeError)):
            plan.scan.table_name = "courses"  # type: ignore[misc]

    def test_project_op_frozen(self) -> None:
        plan = full_pipeline("SELECT name FROM students;")
        with pytest.raises((AttributeError, TypeError)):
            plan.project.columns = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 15. Integration: full pipeline query string → IR
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_all_spec_examples(self) -> None:
        examples = [
            "SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;",
            "SELECT name FROM students WHERE marks >= 90;",
            "SELECT name, department FROM students WHERE department = 'CSE' OR department = 'ECE';",
            "SELECT * FROM students ORDER BY semester ASC;",
            "SELECT name, department, marks FROM students WHERE department != 'ME';",
            "SELECT name, marks FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;",
            "SELECT * FROM students;",
        ]
        for ex in examples:
            plan = full_pipeline(ex)
            assert isinstance(plan, LogicalPlan), f"Failed: {ex}"
            # Operations always start with SCAN
            assert isinstance(plan.operations[0], ScanOp)

    def test_minimal_query(self) -> None:
        plan = full_pipeline("SELECT * FROM students")
        assert plan.scan.table_name == "students"
        assert plan.filter is None
        assert plan.sort   is None

    def test_multiple_select_columns(self) -> None:
        plan = full_pipeline("SELECT id, name, department, semester, marks FROM students;")
        assert plan.project.columns == ("id", "name", "department", "semester", "marks")

    def test_ir_decoupled_from_ast(self) -> None:
        """IR nodes must not be instances of AST classes."""
        from backend.parser.ast import ComparisonExpr as ASTComparison
        plan = full_pipeline("SELECT * FROM students WHERE marks > 80;")
        cmp  = plan.filter.predicate
        assert not isinstance(cmp, ASTComparison)
        assert isinstance(cmp, IRComparison)
