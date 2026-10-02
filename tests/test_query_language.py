"""
tests/test_query_language.py

Tests that verify the *specification* of the mini SQL-like query language
defined in docs/QUERY_LANGUAGE.md.

These tests do NOT run a lexer, parser, or executor.  They exercise:
  - Supported keywords, operators, and literals (as constants in schema.py)
  - Valid and invalid query *strings* by inspecting their textual properties
  - The documented limitations

Think of these as "spec compliance" tests — they freeze the language contract
before the lexer is written.
"""

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Constants mirroring the language specification
# ---------------------------------------------------------------------------

SUPPORTED_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "ORDER", "BY", "ASC", "DESC",
}

SUPPORTED_COMPARISON_OPS = {"=", "!=", ">", "<", ">=", "<="}

SUPPORTED_LOGICAL_OPS = {"AND", "OR"}

# Features that are explicitly OUT of scope
UNSUPPORTED_FEATURES = [
    "JOIN",
    "GROUP BY",
    "HAVING",
    "LIMIT",
    "OFFSET",
    "COUNT(",
    "SUM(",
    "AVG(",
    "MAX(",
    "MIN(",
    "BETWEEN",
    "LIKE",
    "IS NULL",
    "IS NOT NULL",
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "DROP",
    "ALTER",
    "DISTINCT",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "SUBQUERY",
]

# Queries that ARE valid per the spec
VALID_QUERIES = [
    # Example 1 — two WHERE conditions, AND, ORDER BY DESC
    "SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;",
    # Example 2 — single column, single WHERE
    "SELECT name FROM students WHERE marks >= 90;",
    # Example 3 — two columns, OR condition
    "SELECT name, department FROM students WHERE department = 'CSE' OR department = 'ECE';",
    # Example 4 — wildcard, ORDER BY ASC (explicit)
    "SELECT * FROM students ORDER BY semester ASC;",
    # Example 5 — inequality
    "SELECT name, department, marks FROM students WHERE department != 'ME';",
    # Example 6 — chained AND
    "SELECT name, marks FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;",
    # Example 7 — minimal (no optional clauses)
    "SELECT * FROM students;",
    # No semicolon — semicolon is optional
    "SELECT name FROM students WHERE marks > 50",
    # ORDER BY without direction (defaults to ASC)
    "SELECT name FROM students ORDER BY name",
    # All columns explicitly listed
    "SELECT id, name, department, semester, marks FROM students",
]

# Queries that are INVALID / use unsupported features
INVALID_OR_UNSUPPORTED_QUERIES = [
    # Multi-table
    ("SELECT name FROM students, courses", "multiple tables"),
    # Aggregate
    ("SELECT COUNT(*) FROM students", "aggregate function"),
    # BETWEEN
    ("SELECT name FROM students WHERE marks BETWEEN 50 AND 90", "BETWEEN keyword"),
    # LIKE
    ("SELECT name FROM students WHERE name LIKE 'A%'", "LIKE keyword"),
    # LIMIT
    ("SELECT name FROM students LIMIT 10", "LIMIT keyword"),
    # IS NULL
    ("SELECT name FROM students WHERE name IS NULL", "IS NULL"),
    # GROUP BY
    ("SELECT department FROM students GROUP BY department", "GROUP BY"),
    # HAVING
    ("SELECT department FROM students GROUP BY department HAVING marks > 80", "HAVING"),
    # JOIN
    ("SELECT s.name FROM students s JOIN courses c ON s.id = c.id", "JOIN"),
    # Double-quoted string
    ('SELECT name FROM students WHERE department = "CSE"', "double-quoted string"),
    # Arithmetic in SELECT
    ("SELECT marks * 2 FROM students", "arithmetic expression"),
    # DML
    ("INSERT INTO students VALUES (201, 'Zach', 'CSE', 4, 88)", "INSERT statement"),
    # Subquery
    ("SELECT name FROM (SELECT * FROM students) AS sub", "subquery"),
    # Multi-column ORDER BY
    ("SELECT name FROM students ORDER BY marks, semester", "multi-column ORDER BY"),
]


# ---------------------------------------------------------------------------
# 1. Language spec document exists
# ---------------------------------------------------------------------------

class TestSpecDocumentExists:
    def test_query_language_doc_exists(self) -> None:
        doc = Path(__file__).parent.parent / "docs" / "QUERY_LANGUAGE.md"
        assert doc.exists(), "docs/QUERY_LANGUAGE.md is missing"

    def test_query_language_doc_non_empty(self) -> None:
        doc = Path(__file__).parent.parent / "docs" / "QUERY_LANGUAGE.md"
        content = doc.read_text(encoding="utf-8")
        assert len(content) > 500, "QUERY_LANGUAGE.md seems too short"

    def test_spec_contains_ebnf_section(self) -> None:
        doc = Path(__file__).parent.parent / "docs" / "QUERY_LANGUAGE.md"
        content = doc.read_text(encoding="utf-8")
        assert "EBNF" in content or "ebnf" in content.lower()

    def test_spec_contains_limitations_section(self) -> None:
        doc = Path(__file__).parent.parent / "docs" / "QUERY_LANGUAGE.md"
        content = doc.read_text(encoding="utf-8")
        assert "limitation" in content.lower() or "not supported" in content.lower()


# ---------------------------------------------------------------------------
# 2. Keyword set
# ---------------------------------------------------------------------------

class TestKeywords:
    def test_keyword_count(self) -> None:
        assert len(SUPPORTED_KEYWORDS) == 9

    @pytest.mark.parametrize("kw", sorted(SUPPORTED_KEYWORDS))
    def test_keyword_is_uppercase(self, kw: str) -> None:
        assert kw == kw.upper(), f"Keyword {kw!r} should be uppercase"

    def test_select_in_keywords(self) -> None:
        assert "SELECT" in SUPPORTED_KEYWORDS

    def test_from_in_keywords(self) -> None:
        assert "FROM" in SUPPORTED_KEYWORDS

    def test_where_in_keywords(self) -> None:
        assert "WHERE" in SUPPORTED_KEYWORDS

    def test_order_by_keywords_present(self) -> None:
        assert "ORDER" in SUPPORTED_KEYWORDS
        assert "BY" in SUPPORTED_KEYWORDS

    def test_asc_desc_in_keywords(self) -> None:
        assert "ASC" in SUPPORTED_KEYWORDS
        assert "DESC" in SUPPORTED_KEYWORDS

    def test_and_or_in_keywords(self) -> None:
        assert "AND" in SUPPORTED_KEYWORDS
        assert "OR" in SUPPORTED_KEYWORDS


# ---------------------------------------------------------------------------
# 3. Operator set
# ---------------------------------------------------------------------------

class TestOperators:
    @pytest.mark.parametrize("op", sorted(SUPPORTED_COMPARISON_OPS))
    def test_comparison_op_is_string(self, op: str) -> None:
        assert isinstance(op, str)

    def test_six_comparison_operators(self) -> None:
        assert len(SUPPORTED_COMPARISON_OPS) == 6

    def test_two_logical_operators(self) -> None:
        assert len(SUPPORTED_LOGICAL_OPS) == 2

    def test_no_not_operator(self) -> None:
        """NOT as a standalone logical operator is not supported."""
        assert "NOT" not in SUPPORTED_LOGICAL_OPS
        assert "NOT" not in SUPPORTED_KEYWORDS


# ---------------------------------------------------------------------------
# 4. Valid query structural checks (text-level, no parsing)
# ---------------------------------------------------------------------------

_SELECT_RE = re.compile(r"^\s*SELECT\s", re.IGNORECASE)
_FROM_RE    = re.compile(r"\bFROM\s+\w+", re.IGNORECASE)


class TestValidQueryStructure:
    @pytest.mark.parametrize("query", VALID_QUERIES)
    def test_valid_query_starts_with_select(self, query: str) -> None:
        assert _SELECT_RE.match(query), f"Query does not start with SELECT: {query!r}"

    @pytest.mark.parametrize("query", VALID_QUERIES)
    def test_valid_query_contains_from(self, query: str) -> None:
        assert _FROM_RE.search(query), f"Query missing FROM clause: {query!r}"

    @pytest.mark.parametrize("query", VALID_QUERIES)
    def test_valid_query_references_students(self, query: str) -> None:
        assert "students" in query.lower(), (
            f"Valid query does not reference 'students' table: {query!r}"
        )

    @pytest.mark.parametrize("query", VALID_QUERIES)
    def test_valid_query_string_literals_use_single_quotes(self, query: str) -> None:
        """String literals in valid queries must use single quotes only."""
        # Strip anything before the first single-quote to check for rogue double-quotes
        # Any " that appears in a valid query is a problem.
        assert '"' not in query, (
            f"Double-quoted string found in valid query: {query!r}"
        )

    def test_wildcard_select_is_valid(self) -> None:
        wildcard_queries = [q for q in VALID_QUERIES if "SELECT *" in q]
        assert len(wildcard_queries) >= 1, "No wildcard SELECT * query in valid examples"

    def test_order_by_asc_and_desc_both_represented(self) -> None:
        has_asc  = any("ASC"  in q.upper() for q in VALID_QUERIES)
        has_desc = any("DESC" in q.upper() for q in VALID_QUERIES)
        assert has_asc,  "No ASC ORDER BY in valid query examples"
        assert has_desc, "No DESC ORDER BY in valid query examples"

    def test_and_or_both_represented_in_valid_queries(self) -> None:
        has_and = any(" AND " in q.upper() for q in VALID_QUERIES)
        has_or  = any(" OR "  in q.upper() for q in VALID_QUERIES)
        assert has_and, "No AND condition in valid query examples"
        assert has_or,  "No OR condition in valid query examples"


# ---------------------------------------------------------------------------
# 5. Unsupported / invalid query checks
# ---------------------------------------------------------------------------

class TestUnsupportedFeatures:
    @pytest.mark.parametrize("query,reason", INVALID_OR_UNSUPPORTED_QUERIES)
    def test_unsupported_query_not_in_valid_set(
        self, query: str, reason: str
    ) -> None:
        """Every invalid/unsupported query must NOT appear in the valid set."""
        for valid in VALID_QUERIES:
            assert query.strip().upper() != valid.strip().upper(), (
                f"Unsupported query ({reason}) incorrectly listed as valid: {query!r}"
            )

    def test_join_not_supported(self) -> None:
        join_queries = [q for q, _ in INVALID_OR_UNSUPPORTED_QUERIES if "JOIN" in q.upper()]
        assert len(join_queries) >= 1

    def test_aggregate_not_supported(self) -> None:
        agg_queries = [q for q, _ in INVALID_OR_UNSUPPORTED_QUERIES
                       if any(fn in q.upper() for fn in ["COUNT(", "SUM(", "AVG("])]
        assert len(agg_queries) >= 1

    def test_limit_not_supported(self) -> None:
        limit_queries = [q for q, _ in INVALID_OR_UNSUPPORTED_QUERIES if "LIMIT" in q.upper()]
        assert len(limit_queries) >= 1


# ---------------------------------------------------------------------------
# 6. Literal format checks
# ---------------------------------------------------------------------------

_INTEGER_LITERAL_RE = re.compile(r"^\d+$")
_STRING_LITERAL_RE  = re.compile(r"^'[^']*'$")


class TestLiteralFormats:
    @pytest.mark.parametrize("s", ["0", "1", "80", "100", "99999"])
    def test_integer_literal_pattern(self, s: str) -> None:
        assert _INTEGER_LITERAL_RE.match(s), f"{s!r} should match integer literal pattern"

    @pytest.mark.parametrize("s", ["-1", "3.14", "1e5", "0x10", ""])
    def test_non_integer_literal_rejected(self, s: str) -> None:
        assert not _INTEGER_LITERAL_RE.match(s), (
            f"{s!r} should NOT match integer literal pattern"
        )

    @pytest.mark.parametrize("s", ["'CSE'", "'Alice'", "''", "'hello world'"])
    def test_string_literal_pattern(self, s: str) -> None:
        assert _STRING_LITERAL_RE.match(s), f"{s!r} should match string literal pattern"

    @pytest.mark.parametrize("s", ['"CSE"', "CSE", "'unterminated"])
    def test_non_string_literal_rejected(self, s: str) -> None:
        assert not _STRING_LITERAL_RE.match(s), (
            f"{s!r} should NOT match string literal pattern"
        )


# ---------------------------------------------------------------------------
# 7. Column name / identifier format checks
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

VALID_IDENTIFIERS   = ["id", "name", "department", "semester", "marks", "students", "_col", "col2"]
INVALID_IDENTIFIERS = ["2col", "col-name", "col name", "", "123", "col.name"]


class TestIdentifierFormat:
    @pytest.mark.parametrize("ident", VALID_IDENTIFIERS)
    def test_valid_identifier(self, ident: str) -> None:
        assert _IDENTIFIER_RE.match(ident), f"{ident!r} should be a valid identifier"

    @pytest.mark.parametrize("ident", INVALID_IDENTIFIERS)
    def test_invalid_identifier(self, ident: str) -> None:
        assert not _IDENTIFIER_RE.match(ident), (
            f"{ident!r} should NOT be a valid identifier"
        )
