"""
tests/test_semantic.py

Comprehensive tests for the semantic analyzer.

Covers all 15 required cases plus:
  - ErrorCode enum values on each error type
  - Token position carried in every error
  - Multiple simultaneous errors collected in one pass
  - Operator compatibility (STRING columns reject >, <, >=, <=)
  - SELECT * wildcard resolution
  - result.resolved_columns populated correctly
  - result.table_schema populated correctly
  - Full integration: query string -> lexer -> parser -> semantic analysis
  - Reference query passes end-to-end
"""

import pytest

from backend.lexer    import Lexer
from backend.parser   import Parser
from backend.schema   import SCHEMA_REGISTRY, ColumnType, STUDENTS_SCHEMA
from backend.semantic import (
    ErrorCode,
    SemanticAnalysisResult,
    SemanticAnalyzer,
    SemanticError,
)
from backend.parser.ast import Query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def analyze(query: str) -> SemanticAnalysisResult:
    """Full pipeline: string -> tokens -> AST -> semantic result."""
    tokens = Lexer(query).tokenize()
    ast    = Parser(tokens).parse()
    return SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)


def analyze_ast(ast: Query) -> SemanticAnalysisResult:
    """Semantic analysis only (no re-parsing)."""
    return SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)


def parse(query: str) -> Query:
    tokens = Lexer(query).tokenize()
    return Parser(tokens).parse()


# ---------------------------------------------------------------------------
# 1. Valid simple SELECT
# ---------------------------------------------------------------------------

class TestValidSimpleSelect:
    def test_is_valid(self) -> None:
        result = analyze("SELECT name FROM students;")
        assert result.valid is True

    def test_no_errors(self) -> None:
        result = analyze("SELECT name FROM students;")
        assert result.errors == []

    def test_resolved_columns(self) -> None:
        result = analyze("SELECT name FROM students;")
        assert result.resolved_columns == ["name"]

    def test_table_schema_populated(self) -> None:
        result = analyze("SELECT name FROM students;")
        assert result.table_schema is STUDENTS_SCHEMA

    def test_result_str_valid(self) -> None:
        result = analyze("SELECT name FROM students;")
        assert "valid=True" in str(result)


# ---------------------------------------------------------------------------
# 2. Valid SELECT with multiple columns
# ---------------------------------------------------------------------------

class TestValidMultipleColumns:
    def test_is_valid(self) -> None:
        result = analyze("SELECT name, marks FROM students;")
        assert result.valid is True

    def test_resolved_columns_order(self) -> None:
        result = analyze("SELECT name, marks FROM students;")
        assert result.resolved_columns == ["name", "marks"]

    def test_five_columns(self) -> None:
        result = analyze("SELECT id, name, department, semester, marks FROM students;")
        assert result.valid is True
        assert result.resolved_columns == ["id", "name", "department", "semester", "marks"]


# ---------------------------------------------------------------------------
# 3. Valid SELECT *
# ---------------------------------------------------------------------------

class TestValidSelectStar:
    def test_is_valid(self) -> None:
        result = analyze("SELECT * FROM students;")
        assert result.valid is True

    def test_resolves_all_columns(self) -> None:
        result = analyze("SELECT * FROM students;")
        assert result.resolved_columns == STUDENTS_SCHEMA.column_names

    def test_no_errors(self) -> None:
        result = analyze("SELECT * FROM students;")
        assert result.errors == []


# ---------------------------------------------------------------------------
# 4. Unknown dataset
# ---------------------------------------------------------------------------

class TestUnknownDataset:
    def test_is_invalid(self) -> None:
        result = analyze("SELECT name FROM teachers;")
        assert result.valid is False

    def test_error_code(self) -> None:
        result = analyze("SELECT name FROM teachers;")
        assert result.errors[0].code == ErrorCode.UNKNOWN_TABLE

    def test_error_message_contains_table(self) -> None:
        result = analyze("SELECT name FROM teachers;")
        assert "teachers" in result.errors[0].message

    def test_table_schema_is_none(self) -> None:
        result = analyze("SELECT name FROM teachers;")
        assert result.table_schema is None

    def test_resolved_columns_empty(self) -> None:
        result = analyze("SELECT name FROM teachers;")
        assert result.resolved_columns == []

    def test_no_spurious_column_errors(self) -> None:
        """When the table is unknown, column errors must NOT be generated."""
        result = analyze("SELECT salary FROM teachers WHERE bonus > 100;")
        codes = [e.code for e in result.errors]
        assert ErrorCode.UNKNOWN_TABLE in codes
        assert ErrorCode.UNKNOWN_COLUMN not in codes

    def test_error_has_position(self) -> None:
        result = analyze("SELECT name FROM teachers;")
        err = result.errors[0]
        assert err.token.line >= 1
        assert err.token.col  >= 1


# ---------------------------------------------------------------------------
# 5. Unknown SELECT column
# ---------------------------------------------------------------------------

class TestUnknownSelectColumn:
    def test_is_invalid(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert result.valid is False

    def test_error_code(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert result.errors[0].code == ErrorCode.UNKNOWN_COLUMN

    def test_error_message_contains_column(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert "salary" in result.errors[0].message

    def test_error_message_contains_table(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert "students" in result.errors[0].message

    def test_multiple_unknown_select_columns(self) -> None:
        """Both unknown columns must be reported."""
        result = analyze("SELECT salary, bonus FROM students;")
        assert result.valid is False
        assert len(result.errors) == 2

    def test_valid_column_mixed_with_invalid(self) -> None:
        """One valid and one invalid column: only one error."""
        result = analyze("SELECT name, salary FROM students;")
        assert len(result.errors) == 1
        assert "salary" in result.errors[0].message


# ---------------------------------------------------------------------------
# 6. Unknown WHERE column
# ---------------------------------------------------------------------------

class TestUnknownWhereColumn:
    def test_is_invalid(self) -> None:
        result = analyze("SELECT name FROM students WHERE salary > 50000;")
        assert result.valid is False

    def test_error_code(self) -> None:
        result = analyze("SELECT name FROM students WHERE salary > 50000;")
        assert result.errors[0].code == ErrorCode.UNKNOWN_COLUMN

    def test_error_message_contains_column(self) -> None:
        result = analyze("SELECT name FROM students WHERE salary > 50000;")
        assert "salary" in result.errors[0].message

    def test_error_has_position(self) -> None:
        result = analyze("SELECT name FROM students WHERE salary > 50000;")
        err = result.errors[0]
        assert err.token.line >= 1
        assert err.token.col  >= 1


# ---------------------------------------------------------------------------
# 7. Unknown ORDER BY column
# ---------------------------------------------------------------------------

class TestUnknownOrderByColumn:
    def test_is_invalid(self) -> None:
        result = analyze("SELECT name FROM students ORDER BY salary DESC;")
        assert result.valid is False

    def test_error_code(self) -> None:
        result = analyze("SELECT name FROM students ORDER BY salary DESC;")
        assert result.errors[0].code == ErrorCode.UNKNOWN_COLUMN

    def test_error_message_contains_column(self) -> None:
        result = analyze("SELECT name FROM students ORDER BY salary DESC;")
        assert "salary" in result.errors[0].message

    def test_valid_order_by_does_not_error(self) -> None:
        result = analyze("SELECT name FROM students ORDER BY marks DESC;")
        assert result.valid is True


# ---------------------------------------------------------------------------
# 8. Valid numeric comparison
# ---------------------------------------------------------------------------

class TestValidNumericComparison:
    @pytest.mark.parametrize("op", ["=", "!=", ">", "<", ">=", "<="])
    def test_integer_column_all_ops(self, op: str) -> None:
        result = analyze(f"SELECT * FROM students WHERE marks {op} 80;")
        assert result.valid is True, f"Failed for op={op!r}: {result.errors}"

    def test_integer_literal_with_integer_column(self) -> None:
        result = analyze("SELECT * FROM students WHERE semester = 3;")
        assert result.valid is True

    def test_id_column_numeric(self) -> None:
        result = analyze("SELECT * FROM students WHERE id > 50;")
        assert result.valid is True


# ---------------------------------------------------------------------------
# 9. Invalid numeric/string comparison (type mismatch)
# ---------------------------------------------------------------------------

class TestTypeMismatch:
    def test_integer_column_with_string_literal(self) -> None:
        result = analyze("SELECT * FROM students WHERE marks > 'hello';")
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.TYPE_MISMATCH

    def test_error_message_mentions_type(self) -> None:
        result = analyze("SELECT * FROM students WHERE marks > 'hello';")
        assert "INTEGER" in result.errors[0].message

    def test_string_column_with_integer_literal(self) -> None:
        result = analyze("SELECT * FROM students WHERE department = 80;")
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.TYPE_MISMATCH

    def test_string_type_mismatch_message(self) -> None:
        result = analyze("SELECT * FROM students WHERE department = 80;")
        assert "STRING" in result.errors[0].message

    def test_semester_with_string(self) -> None:
        result = analyze("SELECT * FROM students WHERE semester = 'first';")
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.TYPE_MISMATCH

    def test_id_with_string(self) -> None:
        result = analyze("SELECT * FROM students WHERE id = 'x';")
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.TYPE_MISMATCH


# ---------------------------------------------------------------------------
# 10. Valid string comparison
# ---------------------------------------------------------------------------

class TestValidStringComparison:
    def test_eq_string_column(self) -> None:
        result = analyze("SELECT * FROM students WHERE department = 'CSE';")
        assert result.valid is True

    def test_neq_string_column(self) -> None:
        result = analyze("SELECT * FROM students WHERE department != 'ME';")
        assert result.valid is True

    def test_name_string_column(self) -> None:
        result = analyze("SELECT * FROM students WHERE name = 'Alice';")
        assert result.valid is True


# ---------------------------------------------------------------------------
# 11. Multiple valid conditions
# ---------------------------------------------------------------------------

class TestMultipleValidConditions:
    def test_and_two_conditions(self) -> None:
        result = analyze(
            "SELECT name FROM students WHERE department = 'CSE' AND marks > 80;"
        )
        assert result.valid is True

    def test_or_two_conditions(self) -> None:
        result = analyze(
            "SELECT name FROM students WHERE department = 'CSE' OR department = 'ECE';"
        )
        assert result.valid is True

    def test_three_chained_ands(self) -> None:
        result = analyze(
            "SELECT name FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        )
        assert result.valid is True

    def test_mixed_and_or(self) -> None:
        result = analyze(
            "SELECT name FROM students WHERE marks > 80 AND semester = 3 OR department = 'CSE';"
        )
        assert result.valid is True


# ---------------------------------------------------------------------------
# 12. Invalid column inside a later condition
# ---------------------------------------------------------------------------

class TestInvalidColumnInCondition:
    def test_second_condition_bad_column(self) -> None:
        """First condition valid, second condition has bad column."""
        result = analyze(
            "SELECT name FROM students WHERE marks > 80 AND salary > 50000;"
        )
        assert result.valid is False
        assert any(e.code == ErrorCode.UNKNOWN_COLUMN for e in result.errors)
        # Must name the bad column
        assert any("salary" in e.message for e in result.errors)

    def test_or_condition_bad_column(self) -> None:
        result = analyze(
            "SELECT name FROM students WHERE department = 'CSE' OR bonus > 100;"
        )
        assert result.valid is False
        assert any("bonus" in e.message for e in result.errors)

    def test_all_errors_collected(self) -> None:
        """Both conditions have bad columns: both errors must be reported."""
        result = analyze(
            "SELECT name FROM students WHERE salary > 100 AND bonus > 200;"
        )
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# 13. Valid ORDER BY
# ---------------------------------------------------------------------------

class TestValidOrderBy:
    def test_order_by_integer_column(self) -> None:
        result = analyze("SELECT * FROM students ORDER BY marks DESC;")
        assert result.valid is True

    def test_order_by_string_column(self) -> None:
        result = analyze("SELECT * FROM students ORDER BY name ASC;")
        assert result.valid is True

    def test_order_by_default_asc(self) -> None:
        result = analyze("SELECT * FROM students ORDER BY semester;")
        assert result.valid is True


# ---------------------------------------------------------------------------
# 14. Mixed-case identifiers / case sensitivity
# ---------------------------------------------------------------------------

class TestCaseSensitivity:
    def test_keywords_case_insensitive(self) -> None:
        """Keywords are normalised by the lexer; schema lookup is lowercase."""
        result = analyze("select * from students;")
        assert result.valid is True

    def test_column_name_exact_match_required(self) -> None:
        """Column names are case-sensitive per the existing schema."""
        # 'Marks' (capital M) is NOT in the schema — schema has 'marks'.
        result = analyze("SELECT Marks FROM students;")
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.UNKNOWN_COLUMN

    def test_table_lookup_case_insensitive(self) -> None:
        """Table name lookup is case-insensitive (lowered in registry)."""
        result = analyze("SELECT name FROM STUDENTS;")
        assert result.valid is True

    def test_correct_case_column_valid(self) -> None:
        result = analyze("SELECT marks FROM students WHERE marks > 50;")
        assert result.valid is True


# ---------------------------------------------------------------------------
# 15. Reference query passes semantic analysis
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQuery:
    def test_reference_query_valid(self) -> None:
        result = analyze(REFERENCE_QUERY)
        assert result.valid is True

    def test_reference_resolved_columns(self) -> None:
        result = analyze(REFERENCE_QUERY)
        assert result.resolved_columns == ["name", "marks"]

    def test_reference_table_schema(self) -> None:
        result = analyze(REFERENCE_QUERY)
        assert result.table_schema is STUDENTS_SCHEMA

    def test_reference_no_errors(self) -> None:
        result = analyze(REFERENCE_QUERY)
        assert result.errors == []


# ---------------------------------------------------------------------------
# 16. salary column failure
# ---------------------------------------------------------------------------

class TestSalaryColumnFailure:
    def test_salary_select_fails(self) -> None:
        result = analyze("SELECT salary FROM students WHERE marks > 80;")
        assert result.valid is False

    def test_salary_error_is_unknown_column(self) -> None:
        result = analyze("SELECT salary FROM students WHERE marks > 80;")
        codes = [e.code for e in result.errors]
        assert ErrorCode.UNKNOWN_COLUMN in codes

    def test_salary_error_message(self) -> None:
        result = analyze("SELECT salary FROM students WHERE marks > 80;")
        assert any("salary" in e.message for e in result.errors)

    def test_valid_condition_still_checked(self) -> None:
        """Even with bad SELECT column, valid WHERE is checked — no extra errors."""
        result = analyze("SELECT salary FROM students WHERE marks > 80;")
        # marks > 80 is valid: only salary generates an error
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# 17. Operator compatibility for STRING columns
# ---------------------------------------------------------------------------

class TestOperatorCompatibility:
    @pytest.mark.parametrize("op", [">", "<", ">=", "<="])
    def test_ordering_op_on_string_column_fails(self, op: str) -> None:
        result = analyze(f"SELECT * FROM students WHERE department {op} 'CSE';")
        assert result.valid is False
        assert any(e.code == ErrorCode.OPERATOR_MISMATCH for e in result.errors)

    @pytest.mark.parametrize("op", ["=", "!="])
    def test_equality_op_on_string_column_valid(self, op: str) -> None:
        result = analyze(f"SELECT * FROM students WHERE department {op} 'CSE';")
        assert result.valid is True, f"Expected valid for op={op!r}: {result.errors}"

    def test_operator_mismatch_message_contains_operator(self) -> None:
        result = analyze("SELECT * FROM students WHERE department > 'CSE';")
        assert ">" in result.errors[0].message or ">" in str(result.errors[0])

    def test_integer_column_all_ops_valid(self) -> None:
        for op in ["=", "!=", ">", "<", ">=", "<="]:
            result = analyze(f"SELECT * FROM students WHERE marks {op} 80;")
            assert result.valid is True, f"Failed for op={op!r}"


# ---------------------------------------------------------------------------
# 18. Error accumulation — multiple independent errors
# ---------------------------------------------------------------------------

class TestErrorAccumulation:
    def test_two_unknown_select_columns(self) -> None:
        result = analyze("SELECT salary, bonus FROM students;")
        assert len(result.errors) == 2

    def test_unknown_select_and_unknown_where_column(self) -> None:
        result = analyze("SELECT salary FROM students WHERE bonus > 100;")
        assert len(result.errors) == 2

    def test_type_mismatch_and_operator_mismatch_together(self) -> None:
        """STRING column > INTEGER literal produces both a type error and
        an operator error — the analyser must not short-circuit."""
        result = analyze("SELECT * FROM students WHERE department > 80;")
        # type mismatch (INTEGER literal on STRING column) + operator mismatch (>)
        codes = [e.code for e in result.errors]
        assert ErrorCode.TYPE_MISMATCH    in codes
        assert ErrorCode.OPERATOR_MISMATCH in codes


# ---------------------------------------------------------------------------
# 19. SemanticError structure
# ---------------------------------------------------------------------------

class TestSemanticErrorStructure:
    def test_error_has_code(self) -> None:
        result = analyze("SELECT salary FROM students;")
        err = result.errors[0]
        assert isinstance(err.code, ErrorCode)

    def test_error_has_message(self) -> None:
        result = analyze("SELECT salary FROM students;")
        err = result.errors[0]
        assert isinstance(err.message, str)
        assert len(err.message) > 0

    def test_error_has_token(self) -> None:
        result = analyze("SELECT salary FROM students;")
        err = result.errors[0]
        assert err.token is not None

    def test_error_token_has_position(self) -> None:
        result = analyze("SELECT salary FROM students;")
        err = result.errors[0]
        assert err.token.line >= 1
        assert err.token.col  >= 1

    def test_error_str(self) -> None:
        result = analyze("SELECT salary FROM students;")
        s = str(result.errors[0])
        assert "SemanticError" in s
        assert "UNKNOWN_COLUMN" in s

    def test_error_is_frozen(self) -> None:
        result = analyze("SELECT salary FROM students;")
        err = result.errors[0]
        with pytest.raises((AttributeError, TypeError)):
            err.code = ErrorCode.UNKNOWN_TABLE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 20. SemanticAnalysisResult structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_valid_result_has_no_errors(self) -> None:
        result = analyze("SELECT * FROM students;")
        assert result.valid is True
        assert result.error_count == 0

    def test_invalid_result_has_errors(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert result.valid is False
        assert result.error_count >= 1

    def test_first_error(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert result.first_error() is not None

    def test_first_error_none_when_valid(self) -> None:
        result = analyze("SELECT * FROM students;")
        assert result.first_error() is None

    def test_result_str_valid(self) -> None:
        result = analyze("SELECT * FROM students;")
        assert "valid=True" in str(result)

    def test_result_str_invalid(self) -> None:
        result = analyze("SELECT salary FROM students;")
        assert "valid=False" in str(result)

    def test_ast_not_modified(self) -> None:
        """The AST must be unchanged after analysis."""
        ast1 = parse("SELECT name, marks FROM students WHERE marks > 80;")
        ast2 = parse("SELECT name, marks FROM students WHERE marks > 80;")
        SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast1)
        # ast1 must still equal ast2 structurally after analysis
        assert ast1.select.columns == ast2.select.columns  # type: ignore[union-attr]
        assert ast1.from_clause.table_name == ast2.from_clause.table_name


# ---------------------------------------------------------------------------
# 21. Integration tests: full pipeline
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_reference_query_full_pipeline(self) -> None:
        tokens = Lexer(REFERENCE_QUERY).tokenize()
        ast    = Parser(tokens).parse()
        result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert result.valid is True
        assert result.resolved_columns == ["name", "marks"]

    def test_unknown_table_full_pipeline(self) -> None:
        tokens = Lexer("SELECT name FROM teachers;").tokenize()
        ast    = Parser(tokens).parse()
        result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.UNKNOWN_TABLE

    def test_all_spec_examples_valid(self) -> None:
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
            result = analyze(ex)
            assert result.valid is True, (
                f"Expected valid for: {ex}\nErrors: {result.errors}"
            )

    def test_custom_schema_registry(self) -> None:
        """SemanticAnalyzer can be instantiated with any registry."""
        from backend.schema import TableSchema, ColumnMeta, ColumnType
        custom_schema = TableSchema(
            table_name="courses",
            columns=(
                ColumnMeta("course_id", ColumnType.INTEGER),
                ColumnMeta("title",     ColumnType.STRING),
            ),
        )
        custom_registry = {"courses": custom_schema}
        tokens = Lexer("SELECT title FROM courses;").tokenize()
        ast    = Parser(tokens).parse()
        result = SemanticAnalyzer(custom_registry).analyze(ast)
        assert result.valid is True
        assert result.resolved_columns == ["title"]

    def test_type_mismatch_full_pipeline(self) -> None:
        tokens = Lexer("SELECT name FROM students WHERE marks > 'hello';").tokenize()
        ast    = Parser(tokens).parse()
        result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert result.valid is False
        assert result.errors[0].code == ErrorCode.TYPE_MISMATCH

    def test_operator_mismatch_full_pipeline(self) -> None:
        tokens = Lexer("SELECT name FROM students WHERE department > 'CSE';").tokenize()
        ast    = Parser(tokens).parse()
        result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        assert result.valid is False
        codes = [e.code for e in result.errors]
        assert ErrorCode.OPERATOR_MISMATCH in codes
