"""
tests/test_parser.py

Comprehensive unit and integration tests for the parser and AST.

Covers all 19 required cases plus:
  - Reference query full structural assertion
  - Left-to-right condition associativity (spec-defined, no SQL precedence)
  - Integration test: raw query string → lexer → parser → AST
  - AST node __str__ representations
  - is_wildcard helper
  - ORDER BY default direction
  - ParseError position information
"""

import pytest

from backend.lexer import Lexer
from backend.parser import (
    ColumnRef,
    ComparisonExpr,
    FromClause,
    IntegerLiteral,
    LogicalExpr,
    OrderByClause,
    ParseError,
    Parser,
    Query,
    SelectClause,
    StringLiteral,
    WhereClause,
    Wildcard,
)
from backend.lexer.token import TokenType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(query: str) -> Query:
    """Lex + parse in one step."""
    tokens = Lexer(query).tokenize()
    return Parser(tokens).parse()


def parse_tokens(query: str):
    """Return the token list (for constructing Parser directly in tests)."""
    return Lexer(query).tokenize()


# ---------------------------------------------------------------------------
# 1. SELECT one column
# ---------------------------------------------------------------------------

class TestSelectOneColumn:
    def test_single_col_returns_query(self) -> None:
        q = parse("SELECT name FROM students")
        assert isinstance(q, Query)

    def test_select_clause_type(self) -> None:
        q = parse("SELECT name FROM students")
        assert isinstance(q.select, SelectClause)

    def test_column_count(self) -> None:
        q = parse("SELECT name FROM students")
        assert not q.select.is_wildcard
        assert len(q.select.columns) == 1  # type: ignore[arg-type]

    def test_column_name(self) -> None:
        q = parse("SELECT name FROM students")
        assert isinstance(q.select.columns, tuple)
        assert q.select.columns[0].name == "name"  # type: ignore[index]

    def test_column_is_column_ref(self) -> None:
        q = parse("SELECT name FROM students")
        assert isinstance(q.select.columns[0], ColumnRef)  # type: ignore[index]


# ---------------------------------------------------------------------------
# 2. SELECT multiple columns
# ---------------------------------------------------------------------------

class TestSelectMultipleColumns:
    def test_two_columns(self) -> None:
        q = parse("SELECT name, marks FROM students")
        assert len(q.select.columns) == 2  # type: ignore[arg-type]

    def test_two_column_names(self) -> None:
        q = parse("SELECT name, marks FROM students")
        names = [c.name for c in q.select.columns]  # type: ignore[union-attr]
        assert names == ["name", "marks"]

    def test_five_columns(self) -> None:
        q = parse("SELECT id, name, department, semester, marks FROM students")
        assert len(q.select.columns) == 5  # type: ignore[arg-type]

    def test_five_column_names_order(self) -> None:
        q = parse("SELECT id, name, department, semester, marks FROM students")
        names = [c.name for c in q.select.columns]  # type: ignore[union-attr]
        assert names == ["id", "name", "department", "semester", "marks"]


# ---------------------------------------------------------------------------
# 3. SELECT *
# ---------------------------------------------------------------------------

class TestSelectStar:
    def test_wildcard_is_wildcard(self) -> None:
        q = parse("SELECT * FROM students")
        assert q.select.is_wildcard

    def test_wildcard_node_type(self) -> None:
        q = parse("SELECT * FROM students")
        assert isinstance(q.select.columns, Wildcard)

    def test_non_wildcard_is_not_wildcard(self) -> None:
        q = parse("SELECT name FROM students")
        assert not q.select.is_wildcard

    def test_select_str_wildcard(self) -> None:
        q = parse("SELECT * FROM students")
        assert str(q.select) == "SELECT *"

    def test_select_str_columns(self) -> None:
        q = parse("SELECT name, marks FROM students")
        assert str(q.select) == "SELECT name, marks"


# ---------------------------------------------------------------------------
# 4. FROM clause
# ---------------------------------------------------------------------------

class TestFromClause:
    def test_from_clause_type(self) -> None:
        q = parse("SELECT * FROM students")
        assert isinstance(q.from_clause, FromClause)

    def test_table_name(self) -> None:
        q = parse("SELECT * FROM students")
        assert q.from_clause.table_name == "students"

    def test_from_str(self) -> None:
        q = parse("SELECT * FROM students")
        assert str(q.from_clause) == "FROM students"

    def test_from_token_is_identifier(self) -> None:
        q = parse("SELECT * FROM students")
        assert q.from_clause.token.type == TokenType.IDENTIFIER


# ---------------------------------------------------------------------------
# 5. Query with no WHERE
# ---------------------------------------------------------------------------

class TestNoWhere:
    def test_where_is_none(self) -> None:
        q = parse("SELECT * FROM students")
        assert q.where is None

    def test_order_by_also_none(self) -> None:
        q = parse("SELECT * FROM students")
        assert q.order_by is None

    def test_still_valid_query(self) -> None:
        q = parse("SELECT name, marks FROM students")
        assert q.from_clause.table_name == "students"


# ---------------------------------------------------------------------------
# 6. WHERE with one comparison
# ---------------------------------------------------------------------------

class TestWhereOneComparison:
    def test_where_not_none(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        assert q.where is not None

    def test_where_is_where_clause(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        assert isinstance(q.where, WhereClause)

    def test_condition_is_comparison(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        assert isinstance(q.where.condition, ComparisonExpr)

    def test_column_name(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert cmp.column.name == "marks"

    def test_operator(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert cmp.operator == ">"

    def test_integer_literal(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert isinstance(cmp.right, IntegerLiteral)
        assert cmp.right.value == 80

    def test_string_literal(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE'")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert isinstance(cmp.right, StringLiteral)
        assert cmp.right.value == "CSE"

    def test_string_literal_no_quotes(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE'")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert "'" not in cmp.right.value  # type: ignore[union-attr]

    @pytest.mark.parametrize("op", ["=", "!=", ">", "<", ">=", "<="])
    def test_all_operators(self, op: str) -> None:
        q = parse(f"SELECT * FROM students WHERE marks {op} 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert cmp.operator == op


# ---------------------------------------------------------------------------
# 7. WHERE with AND
# ---------------------------------------------------------------------------

class TestWhereAnd:
    def test_condition_is_logical(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' AND marks > 80")
        assert isinstance(q.where.condition, LogicalExpr)

    def test_logical_operator_is_and(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' AND marks > 80")
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        assert logic.operator == "AND"

    def test_left_is_comparison(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' AND marks > 80")
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        assert isinstance(logic.left, ComparisonExpr)
        assert logic.left.column.name == "department"

    def test_right_is_comparison(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' AND marks > 80")
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        assert isinstance(logic.right, ComparisonExpr)
        assert logic.right.column.name == "marks"


# ---------------------------------------------------------------------------
# 8. WHERE with OR
# ---------------------------------------------------------------------------

class TestWhereOr:
    def test_condition_is_logical(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' OR department = 'ECE'")
        assert isinstance(q.where.condition, LogicalExpr)

    def test_logical_operator_is_or(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' OR department = 'ECE'")
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        assert logic.operator == "OR"

    def test_both_sides_are_comparisons(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' OR department = 'ECE'")
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        assert isinstance(logic.left, ComparisonExpr)
        assert isinstance(logic.right, ComparisonExpr)

    def test_right_string_value(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' OR department = 'ECE'")
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        right_cmp = logic.right
        assert isinstance(right_cmp, ComparisonExpr)
        assert isinstance(right_cmp.right, StringLiteral)
        assert right_cmp.right.value == "ECE"


# ---------------------------------------------------------------------------
# 9. Multiple conditions — LEFT-TO-RIGHT associativity (spec-defined)
# ---------------------------------------------------------------------------

class TestLeftToRightAssociativity:
    """
    The spec explicitly states conditions are evaluated left-to-right with
    NO operator precedence.  Therefore:

        A AND B OR C   =>   (A AND B) OR C   NOT   A AND (B OR C)

        A OR B AND C   =>   (A OR B) AND C   NOT   A OR (B AND C)

    These tests verify the parser follows the spec rather than standard SQL.
    """

    def test_and_or_is_left_assoc(self) -> None:
        """A AND B OR C => LogicalExpr(LogicalExpr(A, AND, B), OR, C)"""
        q = parse("SELECT * FROM students "
                  "WHERE marks > 80 AND semester = 3 OR department = 'CSE'")
        # Root must be OR
        root = q.where.condition
        assert isinstance(root, LogicalExpr)
        assert root.operator == "OR"

        # Left of OR must be AND
        left = root.left
        assert isinstance(left, LogicalExpr)
        assert left.operator == "AND"

        # Innermost left is the first comparison
        assert isinstance(left.left, ComparisonExpr)
        assert left.left.column.name == "marks"

    def test_or_and_is_left_assoc(self) -> None:
        """A OR B AND C => LogicalExpr(LogicalExpr(A, OR, B), AND, C)"""
        q = parse("SELECT * FROM students "
                  "WHERE marks > 80 OR semester = 3 AND department = 'CSE'")
        root = q.where.condition
        assert isinstance(root, LogicalExpr)
        assert root.operator == "AND"

        left = root.left
        assert isinstance(left, LogicalExpr)
        assert left.operator == "OR"

    def test_three_ands_chain(self) -> None:
        """A AND B AND C => LogicalExpr(LogicalExpr(A, AND, B), AND, C)"""
        q = parse("SELECT * FROM students "
                  "WHERE semester = 3 AND marks >= 70 AND marks <= 90")
        root = q.where.condition
        assert isinstance(root, LogicalExpr)
        assert root.operator == "AND"

        left = root.left
        assert isinstance(left, LogicalExpr)
        assert left.operator == "AND"
        assert isinstance(left.left, ComparisonExpr)
        assert left.left.column.name == "semester"

    def test_spec_mixed_example(self) -> None:
        """
        Verifies the exact query from the task spec:

            SELECT name
            FROM students
            WHERE marks > 80 OR department = 'CSE'
            AND semester = 5;

        Expected (left-to-right):
            LogicalExpr(
                LogicalExpr(marks > 80, OR, department = 'CSE'),
                AND,
                semester = 5
            )
        """
        q = parse(
            "SELECT name FROM students "
            "WHERE marks > 80 OR department = 'CSE' AND semester = 5;"
        )
        root = q.where.condition
        # Root is AND  (because OR comes first left-to-right, folded first)
        assert isinstance(root, LogicalExpr)
        assert root.operator == "AND"

        # Left of AND is the earlier OR
        left = root.left
        assert isinstance(left, LogicalExpr)
        assert left.operator == "OR"
        assert isinstance(left.left, ComparisonExpr)
        assert left.left.column.name == "marks"
        assert isinstance(left.right, ComparisonExpr)
        assert left.right.column.name == "department"

        # Right of AND is the last comparison
        right = root.right
        assert isinstance(right, ComparisonExpr)
        assert right.column.name == "semester"
        assert isinstance(right.right, IntegerLiteral)
        assert right.right.value == 5


# ---------------------------------------------------------------------------
# 10. ORDER BY ASC
# ---------------------------------------------------------------------------

class TestOrderByAsc:
    def test_order_by_not_none(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks ASC")
        assert q.order_by is not None

    def test_order_by_is_clause(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks ASC")
        assert isinstance(q.order_by, OrderByClause)

    def test_order_by_column_name(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks ASC")
        assert q.order_by.column.name == "marks"

    def test_order_by_direction_asc(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks ASC")
        assert q.order_by.direction == "ASC"

    def test_order_by_default_is_asc(self) -> None:
        """When neither ASC nor DESC is written, direction defaults to ASC."""
        q = parse("SELECT * FROM students ORDER BY marks")
        assert q.order_by.direction == "ASC"

    def test_order_by_str(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks ASC")
        assert str(q.order_by) == "ORDER BY marks ASC"


# ---------------------------------------------------------------------------
# 11. ORDER BY DESC
# ---------------------------------------------------------------------------

class TestOrderByDesc:
    def test_direction_desc(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks DESC")
        assert q.order_by.direction == "DESC"

    def test_column_name_with_desc(self) -> None:
        q = parse("SELECT * FROM students ORDER BY semester DESC")
        assert q.order_by.column.name == "semester"

    def test_order_by_str_desc(self) -> None:
        q = parse("SELECT * FROM students ORDER BY marks DESC")
        assert str(q.order_by) == "ORDER BY marks DESC"


# ---------------------------------------------------------------------------
# 12. Optional semicolon
# ---------------------------------------------------------------------------

class TestOptionalSemicolon:
    def test_with_semicolon_parses(self) -> None:
        q = parse("SELECT * FROM students;")
        assert q.from_clause.table_name == "students"

    def test_without_semicolon_parses(self) -> None:
        q = parse("SELECT * FROM students")
        assert q.from_clause.table_name == "students"

    def test_semicolon_does_not_change_ast(self) -> None:
        q1 = parse("SELECT name FROM students WHERE marks > 80;")
        q2 = parse("SELECT name FROM students WHERE marks > 80")
        assert q1.select.columns == q2.select.columns  # type: ignore[union-attr]
        assert q1.from_clause.table_name == q2.from_clause.table_name
        cmp1 = q1.where.condition
        cmp2 = q2.where.condition
        assert isinstance(cmp1, ComparisonExpr)
        assert isinstance(cmp2, ComparisonExpr)
        assert cmp1.operator == cmp2.operator
        assert isinstance(cmp1.right, IntegerLiteral)
        assert isinstance(cmp2.right, IntegerLiteral)
        assert cmp1.right.value == cmp2.right.value


# ---------------------------------------------------------------------------
# 13. Mixed-case keywords
# ---------------------------------------------------------------------------

class TestMixedCaseKeywords:
    def test_lowercase_select(self) -> None:
        q = parse("select * from students")
        assert q.from_clause.table_name == "students"

    def test_mixed_case_keywords(self) -> None:
        q = parse("Select Name From Students Where Marks > 80 Order By Marks Desc")
        assert q.from_clause.table_name == "Students"
        assert q.order_by.direction == "DESC"

    def test_keyword_stored_uppercase(self) -> None:
        # The SELECT token value is always uppercase (normalised by lexer)
        q = parse("select * from students")
        assert q.select.token.value == "SELECT"

    def test_identifier_case_preserved(self) -> None:
        q = parse("SELECT myColumn FROM students")
        assert q.select.columns[0].name == "myColumn"  # type: ignore[index]


# ---------------------------------------------------------------------------
# 14–19. Error cases
# ---------------------------------------------------------------------------

class TestInvalidSelectSyntax:
    """14. Invalid SELECT syntax."""

    def test_select_directly_from(self) -> None:
        """SELECT FROM students — missing column list."""
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT FROM students")
        assert "SELECT" in str(exc_info.value) or "column" in str(exc_info.value).lower()

    def test_select_no_comma(self) -> None:
        """SELECT name marks — missing comma between columns."""
        with pytest.raises(ParseError):
            parse("SELECT name marks FROM students")

    def test_select_trailing_comma(self) -> None:
        """SELECT name, FROM students — dangling comma."""
        with pytest.raises(ParseError):
            parse("SELECT name, FROM students")

    def test_select_empty(self) -> None:
        with pytest.raises(ParseError):
            parse("SELECT")


class TestMissingFrom:
    """15. Missing FROM keyword."""

    def test_no_from(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT name students")
        assert "FROM" in str(exc_info.value) or "Expected" in str(exc_info.value)

    def test_from_missing_table(self) -> None:
        """SELECT name FROM; — no table name after FROM."""
        with pytest.raises(ParseError):
            parse("SELECT name FROM;")

    def test_from_with_keyword_as_table(self) -> None:
        """SELECT name FROM WHERE — keyword used as table name is rejected."""
        with pytest.raises(ParseError):
            parse("SELECT name FROM WHERE")


class TestMissingWhereExpression:
    """16. Missing WHERE expression."""

    def test_where_no_condition(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT name FROM students WHERE")
        assert "condition" in str(exc_info.value).lower() or \
               "expected" in str(exc_info.value).lower()

    def test_where_incomplete_comparison(self) -> None:
        """WHERE marks > — missing right-hand literal."""
        with pytest.raises(ParseError):
            parse("SELECT name FROM students WHERE marks >")

    def test_where_operator_only(self) -> None:
        """WHERE > 80 — missing column name."""
        with pytest.raises(ParseError):
            parse("SELECT name FROM students WHERE > 80")

    def test_where_missing_operator(self) -> None:
        """WHERE marks 80 — missing comparison operator."""
        with pytest.raises(ParseError):
            parse("SELECT name FROM students WHERE marks 80")


class TestMissingOrderByColumn:
    """17. Missing ORDER BY column."""

    def test_order_no_by(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT name FROM students ORDER")
        assert "BY" in str(exc_info.value) or "Expected" in str(exc_info.value)

    def test_order_by_no_column(self) -> None:
        with pytest.raises(ParseError):
            parse("SELECT name FROM students ORDER BY")

    def test_order_by_keyword_as_column(self) -> None:
        """ORDER BY DESC — DESC without a column name before it."""
        with pytest.raises(ParseError):
            parse("SELECT name FROM students ORDER BY DESC")


class TestUnexpectedTrailingTokens:
    """18. Unexpected trailing tokens."""

    def test_garbage_after_complete_query(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT name FROM students WHERE marks > 80 garbage")
        assert "Unexpected" in str(exc_info.value) or \
               "end" in str(exc_info.value).lower()

    def test_extra_keyword_after_query(self) -> None:
        with pytest.raises(ParseError):
            parse("SELECT * FROM students SELECT")

    def test_number_after_query(self) -> None:
        with pytest.raises(ParseError):
            parse("SELECT * FROM students 42")


class TestInvalidComparisonStructure:
    """19. Invalid comparison operator structure."""

    def test_literal_on_left_rejected(self) -> None:
        """80 > marks — literal on left side is not an identifier."""
        with pytest.raises(ParseError):
            parse("SELECT * FROM students WHERE 80 > marks")

    def test_missing_right_literal(self) -> None:
        with pytest.raises(ParseError):
            parse("SELECT * FROM students WHERE marks >")

    def test_and_without_right_condition(self) -> None:
        with pytest.raises(ParseError):
            parse("SELECT * FROM students WHERE marks > 80 AND")


# ---------------------------------------------------------------------------
# 20. ParseError carries position information
# ---------------------------------------------------------------------------

class TestParseErrorPosition:
    def test_error_has_token(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT FROM students")
        err = exc_info.value
        assert err.token is not None

    def test_error_has_line(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT FROM students")
        err = exc_info.value
        assert err.token.line >= 1

    def test_error_has_col(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT FROM students")
        err = exc_info.value
        assert err.token.col >= 1

    def test_error_message_non_empty(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            parse("SELECT FROM students")
        assert exc_info.value.message != ""


# ---------------------------------------------------------------------------
# 21. Reference query — full structural assertion
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


class TestReferenceQuery:
    def test_returns_query(self) -> None:
        assert isinstance(parse(REFERENCE_QUERY), Query)

    def test_select_columns(self) -> None:
        q = parse(REFERENCE_QUERY)
        assert not q.select.is_wildcard
        names = [c.name for c in q.select.columns]  # type: ignore[union-attr]
        assert names == ["name", "marks"]

    def test_from_table(self) -> None:
        q = parse(REFERENCE_QUERY)
        assert q.from_clause.table_name == "students"

    def test_where_is_logical(self) -> None:
        q = parse(REFERENCE_QUERY)
        assert isinstance(q.where.condition, LogicalExpr)

    def test_where_operator_and(self) -> None:
        q = parse(REFERENCE_QUERY)
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        assert logic.operator == "AND"

    def test_left_condition(self) -> None:
        q = parse(REFERENCE_QUERY)
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        left = logic.left
        assert isinstance(left, ComparisonExpr)
        assert left.column.name == "department"
        assert left.operator == "="
        assert isinstance(left.right, StringLiteral)
        assert left.right.value == "CSE"

    def test_right_condition(self) -> None:
        q = parse(REFERENCE_QUERY)
        logic = q.where.condition
        assert isinstance(logic, LogicalExpr)
        right = logic.right
        assert isinstance(right, ComparisonExpr)
        assert right.column.name == "marks"
        assert right.operator == ">"
        assert isinstance(right.right, IntegerLiteral)
        assert right.right.value == 80

    def test_order_by_column(self) -> None:
        q = parse(REFERENCE_QUERY)
        assert q.order_by.column.name == "marks"

    def test_order_by_direction(self) -> None:
        q = parse(REFERENCE_QUERY)
        assert q.order_by.direction == "DESC"

    def test_query_str(self) -> None:
        q = parse(REFERENCE_QUERY)
        s = str(q)
        assert "SELECT" in s
        assert "students" in s
        assert "WHERE" in s
        assert "ORDER BY" in s


# ---------------------------------------------------------------------------
# 22. Integration: raw string → lexer → parser → AST
# ---------------------------------------------------------------------------

class TestLexerParserIntegration:
    def test_full_pipeline_reference(self) -> None:
        """End-to-end: tokenise then parse the reference query."""
        tokens = Lexer(REFERENCE_QUERY).tokenize()
        ast    = Parser(tokens).parse()
        assert isinstance(ast, Query)
        assert ast.from_clause.table_name == "students"

    def test_full_pipeline_simple(self) -> None:
        tokens = Lexer("SELECT * FROM students;").tokenize()
        ast    = Parser(tokens).parse()
        assert ast.select.is_wildcard
        assert ast.where is None

    def test_full_pipeline_complex(self) -> None:
        q_str = (
            "SELECT name, department FROM students "
            "WHERE semester = 3 AND marks >= 70 AND marks <= 90 "
            "ORDER BY name ASC;"
        )
        tokens = Lexer(q_str).tokenize()
        ast    = Parser(tokens).parse()

        # 2 select columns
        assert len(ast.select.columns) == 2  # type: ignore[arg-type]

        # Condition root is AND (rightmost fold)
        root = ast.where.condition
        assert isinstance(root, LogicalExpr)
        assert root.operator == "AND"

        # Left of root AND is itself an AND
        left = root.left
        assert isinstance(left, LogicalExpr)
        assert left.operator == "AND"

        # ORDER BY name ASC
        assert ast.order_by.column.name == "name"
        assert ast.order_by.direction == "ASC"

    def test_all_spec_examples(self) -> None:
        """All seven valid examples from the language spec must parse cleanly."""
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
            ast = parse(ex)
            assert isinstance(ast, Query), f"Failed to parse: {ex}"


# ---------------------------------------------------------------------------
# 23. AST node __str__ representations
# ---------------------------------------------------------------------------

class TestASTStr:
    def test_integer_literal_str(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert str(cmp.right) == "80"

    def test_string_literal_str(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE'")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert str(cmp.right) == "'CSE'"

    def test_comparison_expr_str(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        assert str(cmp) == "marks > 80"

    def test_logical_expr_str(self) -> None:
        q = parse("SELECT * FROM students WHERE department = 'CSE' AND marks > 80")
        assert "AND" in str(q.where.condition)

    def test_where_clause_str(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        assert str(q.where) == "WHERE marks > 80"

    def test_column_ref_str(self) -> None:
        q = parse("SELECT marks FROM students")
        col = q.select.columns[0]  # type: ignore[index]
        assert str(col) == "marks"

    def test_wildcard_str(self) -> None:
        q = parse("SELECT * FROM students")
        assert str(q.select.columns) == "*"

    def test_query_str_contains_all_clauses(self) -> None:
        s = str(parse(REFERENCE_QUERY))
        assert "SELECT" in s
        assert "FROM"   in s
        assert "WHERE"  in s
        assert "ORDER BY" in s


# ---------------------------------------------------------------------------
# 24. AST nodes are frozen (immutable)
# ---------------------------------------------------------------------------

class TestASTImmutability:
    def test_query_frozen(self) -> None:
        q = parse("SELECT * FROM students")
        with pytest.raises((AttributeError, TypeError)):
            q.from_clause = None  # type: ignore[misc]

    def test_comparison_expr_frozen(self) -> None:
        q = parse("SELECT * FROM students WHERE marks > 80")
        cmp = q.where.condition
        assert isinstance(cmp, ComparisonExpr)
        with pytest.raises((AttributeError, TypeError)):
            cmp.operator = "="  # type: ignore[misc]

    def test_select_clause_frozen(self) -> None:
        q = parse("SELECT * FROM students")
        with pytest.raises((AttributeError, TypeError)):
            q.select.columns = None  # type: ignore[misc]
