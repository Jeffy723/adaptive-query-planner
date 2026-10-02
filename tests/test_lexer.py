"""
tests/test_lexer.py

Comprehensive unit tests for the lexical analyser.

Covers all 17 required cases plus additional edge cases:
  1.  Simple SELECT query
  2.  SELECT with multiple columns
  3.  FROM clause
  4.  WHERE with one condition
  5.  WHERE with AND
  6.  WHERE with OR
  7.  All six comparison operators (=, !=, >, <, >=, <=)
  8.  String literals
  9.  Numeric literals
  10. ORDER BY ASC
  11. ORDER BY DESC
  12. Optional semicolon (with and without)
  13. Mixed-case keywords
  14. Whitespace / newlines
  15. Invalid character error
  16. Unterminated string error
  17. Invalid identifier/number boundary

  Plus:
  - STAR wildcard token
  - EOF sentinel always appended
  - Position info (line/col) on tokens
  - Position info inside LexerError
  - Multi-line query (the spec reference query)
  - All valid query examples from the spec
"""

import pytest

from backend.lexer import Lexer, LexerError, Token, TokenType


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def tokenize(query: str) -> list[Token]:
    """Tokenise *query* and return the full token list (including EOF)."""
    return Lexer(query).tokenize()


def types(query: str) -> list[TokenType]:
    """Return just the token types for *query*."""
    return [t.type for t in tokenize(query)]


def values(query: str) -> list[str]:
    """Return just the token values for *query*."""
    return [t.value for t in tokenize(query)]


# ---------------------------------------------------------------------------
# 1. Simple SELECT query
# ---------------------------------------------------------------------------

class TestSimpleSelect:
    def test_select_star_from(self) -> None:
        toks = tokenize("SELECT * FROM students")
        assert toks[0].type  == TokenType.KEYWORD
        assert toks[0].value == "SELECT"
        assert toks[1].type  == TokenType.STAR
        assert toks[1].value == "*"
        assert toks[2].type  == TokenType.KEYWORD
        assert toks[2].value == "FROM"
        assert toks[3].type  == TokenType.IDENTIFIER
        assert toks[3].value == "students"
        assert toks[4].type  == TokenType.EOF

    def test_token_count_simple(self) -> None:
        # SELECT * FROM students  → 4 tokens + EOF = 5
        assert len(tokenize("SELECT * FROM students")) == 5


# ---------------------------------------------------------------------------
# 2. SELECT with multiple columns
# ---------------------------------------------------------------------------

class TestMultipleColumns:
    def test_two_columns(self) -> None:
        toks = tokenize("SELECT name, marks FROM students")
        assert toks[0].value == "SELECT"
        assert toks[1].type  == TokenType.IDENTIFIER
        assert toks[1].value == "name"
        assert toks[2].type  == TokenType.COMMA
        assert toks[3].type  == TokenType.IDENTIFIER
        assert toks[3].value == "marks"
        assert toks[4].value == "FROM"

    def test_three_columns(self) -> None:
        tys = types("SELECT id, name, marks FROM students")
        assert tys == [
            TokenType.KEYWORD,     # SELECT
            TokenType.IDENTIFIER,  # id
            TokenType.COMMA,
            TokenType.IDENTIFIER,  # name
            TokenType.COMMA,
            TokenType.IDENTIFIER,  # marks
            TokenType.KEYWORD,     # FROM
            TokenType.IDENTIFIER,  # students
            TokenType.EOF,
        ]

    def test_five_columns(self) -> None:
        q = "SELECT id, name, department, semester, marks FROM students"
        vals = values(q)
        assert vals == [
            "SELECT",
            "id", ",", "name", ",", "department", ",", "semester", ",", "marks",
            "FROM", "students",
            "",  # EOF
        ]


# ---------------------------------------------------------------------------
# 3. FROM clause
# ---------------------------------------------------------------------------

class TestFromClause:
    def test_from_keyword_type(self) -> None:
        toks = tokenize("SELECT * FROM students")
        from_tok = next(t for t in toks if t.value == "FROM")
        assert from_tok.type == TokenType.KEYWORD

    def test_table_name_is_identifier(self) -> None:
        toks = tokenize("SELECT * FROM students")
        table_tok = toks[3]
        assert table_tok.type  == TokenType.IDENTIFIER
        assert table_tok.value == "students"


# ---------------------------------------------------------------------------
# 4. WHERE with one condition
# ---------------------------------------------------------------------------

class TestWhereSingleCondition:
    def test_where_marks_gt_80(self) -> None:
        toks = tokenize("SELECT name FROM students WHERE marks > 80")
        tys  = [t.type for t in toks]
        assert TokenType.KEYWORD    in tys   # WHERE
        assert TokenType.OPERATOR   in tys   # >
        assert TokenType.NUMBER     in tys   # 80

    def test_where_eq_string(self) -> None:
        toks = tokenize("SELECT name FROM students WHERE department = 'CSE'")
        # Find the string token
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.value == "CSE"   # quotes stripped

    def test_where_token_sequence(self) -> None:
        tys = types("SELECT name FROM students WHERE marks > 80")
        assert tys == [
            TokenType.KEYWORD,     # SELECT
            TokenType.IDENTIFIER,  # name
            TokenType.KEYWORD,     # FROM
            TokenType.IDENTIFIER,  # students
            TokenType.KEYWORD,     # WHERE
            TokenType.IDENTIFIER,  # marks
            TokenType.OPERATOR,    # >
            TokenType.NUMBER,      # 80
            TokenType.EOF,
        ]


# ---------------------------------------------------------------------------
# 5. WHERE with AND
# ---------------------------------------------------------------------------

class TestWhereAnd:
    def test_and_keyword_emitted(self) -> None:
        q = "SELECT name FROM students WHERE department = 'CSE' AND marks > 80"
        kws = [t.value for t in tokenize(q) if t.type == TokenType.KEYWORD]
        assert "AND" in kws

    def test_full_and_sequence(self) -> None:
        q = "SELECT name FROM students WHERE department = 'CSE' AND marks > 80"
        tys = types(q)
        assert tys == [
            TokenType.KEYWORD,     # SELECT
            TokenType.IDENTIFIER,  # name
            TokenType.KEYWORD,     # FROM
            TokenType.IDENTIFIER,  # students
            TokenType.KEYWORD,     # WHERE
            TokenType.IDENTIFIER,  # department
            TokenType.OPERATOR,    # =
            TokenType.STRING,      # CSE
            TokenType.KEYWORD,     # AND
            TokenType.IDENTIFIER,  # marks
            TokenType.OPERATOR,    # >
            TokenType.NUMBER,      # 80
            TokenType.EOF,
        ]


# ---------------------------------------------------------------------------
# 6. WHERE with OR
# ---------------------------------------------------------------------------

class TestWhereOr:
    def test_or_keyword_emitted(self) -> None:
        q = "SELECT name FROM students WHERE department = 'CSE' OR department = 'ECE'"
        kws = [t.value for t in tokenize(q) if t.type == TokenType.KEYWORD]
        assert "OR" in kws

    def test_full_or_sequence(self) -> None:
        q = "SELECT name FROM students WHERE department = 'CSE' OR department = 'ECE'"
        tys = types(q)
        assert tys == [
            TokenType.KEYWORD,     # SELECT
            TokenType.IDENTIFIER,  # name
            TokenType.KEYWORD,     # FROM
            TokenType.IDENTIFIER,  # students
            TokenType.KEYWORD,     # WHERE
            TokenType.IDENTIFIER,  # department
            TokenType.OPERATOR,    # =
            TokenType.STRING,      # CSE
            TokenType.KEYWORD,     # OR
            TokenType.IDENTIFIER,  # department
            TokenType.OPERATOR,    # =
            TokenType.STRING,      # ECE
            TokenType.EOF,
        ]


# ---------------------------------------------------------------------------
# 7. Comparison operators
# ---------------------------------------------------------------------------

class TestComparisonOperators:
    @pytest.mark.parametrize("op", ["=", "!=", ">", "<", ">=", "<="])
    def test_operator_tokenised(self, op: str) -> None:
        q = f"SELECT name FROM students WHERE marks {op} 80"
        op_toks = [t for t in tokenize(q) if t.type == TokenType.OPERATOR]
        assert len(op_toks) == 1
        assert op_toks[0].value == op

    def test_all_six_operators_distinct(self) -> None:
        seen = set()
        for op in ["=", "!=", ">", "<", ">=", "<="]:
            q = f"SELECT * FROM students WHERE marks {op} 50"
            op_toks = [t for t in tokenize(q) if t.type == TokenType.OPERATOR]
            seen.add(op_toks[0].value)
        assert seen == {"=", "!=", ">", "<", ">=", "<="}

    def test_gt_eq_not_confused(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE marks >= 80")
        op_tok = next(t for t in toks if t.type == TokenType.OPERATOR)
        assert op_tok.value == ">="

    def test_lt_eq_not_confused(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE marks <= 80")
        op_tok = next(t for t in toks if t.type == TokenType.OPERATOR)
        assert op_tok.value == "<="

    def test_not_eq_operator(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE department != 'ME'")
        op_tok = next(t for t in toks if t.type == TokenType.OPERATOR)
        assert op_tok.value == "!="


# ---------------------------------------------------------------------------
# 8. String literals
# ---------------------------------------------------------------------------

class TestStringLiterals:
    def test_string_value_strips_quotes(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE department = 'CSE'")
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.value == "CSE"

    def test_string_with_spaces(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE name = 'hello world'")
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.value == "hello world"

    def test_empty_string(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE name = ''")
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.value == ""

    def test_string_type_correct(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE department = 'IT'")
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.type == TokenType.STRING

    def test_multiple_strings(self) -> None:
        q = "SELECT * FROM students WHERE department = 'CSE' OR department = 'ECE'"
        str_toks = [t for t in tokenize(q) if t.type == TokenType.STRING]
        assert len(str_toks) == 2
        assert str_toks[0].value == "CSE"
        assert str_toks[1].value == "ECE"


# ---------------------------------------------------------------------------
# 9. Numeric literals
# ---------------------------------------------------------------------------

class TestNumericLiterals:
    def test_number_value(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE marks > 80")
        num_tok = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num_tok.value == "80"

    def test_number_type(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE marks > 80")
        num_tok = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num_tok.type == TokenType.NUMBER

    def test_zero(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE marks > 0")
        num_tok = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num_tok.value == "0"

    def test_multi_digit(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE marks >= 100")
        num_tok = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num_tok.value == "100"

    def test_number_is_digit_string(self) -> None:
        toks = tokenize("SELECT * FROM students WHERE semester = 3")
        num_tok = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num_tok.value.isdigit()


# ---------------------------------------------------------------------------
# 10. ORDER BY ASC
# ---------------------------------------------------------------------------

class TestOrderByAsc:
    def test_order_by_asc_keywords(self) -> None:
        toks = tokenize("SELECT * FROM students ORDER BY marks ASC")
        kws = [t.value for t in toks if t.type == TokenType.KEYWORD]
        assert "ORDER" in kws
        assert "BY" in kws
        assert "ASC" in kws

    def test_order_by_asc_sequence(self) -> None:
        tys = types("SELECT * FROM students ORDER BY marks ASC")
        assert tys == [
            TokenType.KEYWORD,     # SELECT
            TokenType.STAR,        # *
            TokenType.KEYWORD,     # FROM
            TokenType.IDENTIFIER,  # students
            TokenType.KEYWORD,     # ORDER
            TokenType.KEYWORD,     # BY
            TokenType.IDENTIFIER,  # marks
            TokenType.KEYWORD,     # ASC
            TokenType.EOF,
        ]


# ---------------------------------------------------------------------------
# 11. ORDER BY DESC
# ---------------------------------------------------------------------------

class TestOrderByDesc:
    def test_order_by_desc_keywords(self) -> None:
        toks = tokenize("SELECT * FROM students ORDER BY marks DESC")
        kws = [t.value for t in toks if t.type == TokenType.KEYWORD]
        assert "DESC" in kws

    def test_order_by_desc_sequence(self) -> None:
        tys = types("SELECT * FROM students ORDER BY marks DESC")
        assert tys == [
            TokenType.KEYWORD,
            TokenType.STAR,
            TokenType.KEYWORD,
            TokenType.IDENTIFIER,
            TokenType.KEYWORD,     # ORDER
            TokenType.KEYWORD,     # BY
            TokenType.IDENTIFIER,  # marks
            TokenType.KEYWORD,     # DESC
            TokenType.EOF,
        ]


# ---------------------------------------------------------------------------
# 12. Optional semicolon
# ---------------------------------------------------------------------------

class TestOptionalSemicolon:
    def test_with_semicolon_emits_token(self) -> None:
        toks = tokenize("SELECT * FROM students;")
        semi_toks = [t for t in toks if t.type == TokenType.SEMICOLON]
        assert len(semi_toks) == 1
        assert semi_toks[0].value == ";"

    def test_without_semicolon_no_token(self) -> None:
        toks = tokenize("SELECT * FROM students")
        semi_toks = [t for t in toks if t.type == TokenType.SEMICOLON]
        assert len(semi_toks) == 0

    def test_eof_always_present_with_semicolon(self) -> None:
        toks = tokenize("SELECT * FROM students;")
        assert toks[-1].type == TokenType.EOF

    def test_eof_always_present_without_semicolon(self) -> None:
        toks = tokenize("SELECT * FROM students")
        assert toks[-1].type == TokenType.EOF

    def test_semicolon_is_last_non_eof_token(self) -> None:
        toks = tokenize("SELECT * FROM students;")
        assert toks[-2].type == TokenType.SEMICOLON


# ---------------------------------------------------------------------------
# 13. Mixed-case keywords
# ---------------------------------------------------------------------------

class TestMixedCaseKeywords:
    @pytest.mark.parametrize("variant", ["SELECT", "select", "Select", "sElEcT"])
    def test_select_case_variants(self, variant: str) -> None:
        toks = tokenize(f"{variant} * FROM students")
        assert toks[0].type  == TokenType.KEYWORD
        assert toks[0].value == "SELECT"   # always canonical uppercase

    @pytest.mark.parametrize("variant", ["FROM", "from", "From"])
    def test_from_case_variants(self, variant: str) -> None:
        toks = tokenize(f"SELECT * {variant} students")
        kw_tok = next(t for t in toks if t.value == "FROM")
        assert kw_tok.type == TokenType.KEYWORD

    @pytest.mark.parametrize("kw", ["where", "Where", "WHERE"])
    def test_where_case_variants(self, kw: str) -> None:
        toks = tokenize(f"SELECT * FROM students {kw} marks > 80")
        kw_tok = next(t for t in toks if t.type == TokenType.KEYWORD and t.value == "WHERE")
        assert kw_tok is not None

    def test_all_keywords_canonical_uppercase(self) -> None:
        q = "select * from students where marks > 80 order by marks desc"
        kw_vals = [t.value for t in tokenize(q) if t.type == TokenType.KEYWORD]
        assert all(v == v.upper() for v in kw_vals)

    def test_identifier_case_preserved(self) -> None:
        """Identifiers must NOT be case-folded."""
        toks = tokenize("SELECT myColumn FROM students")
        ident = next(t for t in toks if t.type == TokenType.IDENTIFIER and "my" in t.value.lower())
        assert ident.value == "myColumn"


# ---------------------------------------------------------------------------
# 14. Whitespace and newlines
# ---------------------------------------------------------------------------

class TestWhitespaceAndNewlines:
    def test_spaces_ignored(self) -> None:
        toks1 = tokenize("SELECT * FROM students")
        toks2 = tokenize("SELECT    *    FROM    students")
        assert [t.value for t in toks1] == [t.value for t in toks2]

    def test_newlines_ignored(self) -> None:
        q = "SELECT *\nFROM students\n"
        toks = tokenize(q)
        assert [t.value for t in toks] == ["SELECT", "*", "FROM", "students", ""]

    def test_tabs_ignored(self) -> None:
        q = "SELECT\t*\tFROM\tstudents"
        toks = tokenize(q)
        assert [t.value for t in toks] == ["SELECT", "*", "FROM", "students", ""]

    def test_mixed_whitespace(self) -> None:
        q = "SELECT  *  \n  FROM  \t students\r\n"
        toks = tokenize(q)
        assert [t.value for t in toks] == ["SELECT", "*", "FROM", "students", ""]

    def test_multiline_preserves_tokens(self) -> None:
        q = (
            "SELECT name, marks\n"
            "FROM students\n"
            "WHERE department = 'CSE'\n"
        )
        str_tok = next(t for t in tokenize(q) if t.type == TokenType.STRING)
        assert str_tok.value == "CSE"


# ---------------------------------------------------------------------------
# 15. Invalid character
# ---------------------------------------------------------------------------

class TestInvalidCharacter:
    def test_at_sign_raises(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT @name FROM students")
        err = exc_info.value
        assert "@" in err.message or "@" in str(err)

    def test_hash_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize("SELECT name FROM students # comment")

    def test_dollar_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize("SELECT $col FROM students")

    def test_error_has_position(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT @name FROM students")
        err = exc_info.value
        assert err.line >= 1
        assert err.col  >= 1

    def test_error_has_source_line(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT @name FROM students")
        err = exc_info.value
        assert "SELECT" in err.source_line   # the source line is captured

    def test_error_col_points_at_bad_char(self) -> None:
        # "SELECT @name..." — '@' is at column 8 (1-based)
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT @name FROM students")
        err = exc_info.value
        assert err.col == 8

    def test_double_quote_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize('SELECT name FROM students WHERE department = "CSE"')


# ---------------------------------------------------------------------------
# 16. Unterminated string
# ---------------------------------------------------------------------------

class TestUnterminatedString:
    def test_unterminated_raises(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT name FROM students WHERE department = 'CSE")
        err = exc_info.value
        assert "unterminated" in err.message.lower() or "missing" in err.message.lower()

    def test_unterminated_error_has_position(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT name FROM students WHERE department = 'CSE")
        err = exc_info.value
        assert err.line >= 1
        assert err.col  >= 1

    def test_empty_unterminated(self) -> None:
        with pytest.raises(LexerError):
            tokenize("SELECT * FROM students WHERE name = '")

    def test_multiline_unterminated(self) -> None:
        q = "SELECT name FROM students\nWHERE department = 'CSE\n"
        with pytest.raises(LexerError):
            tokenize(q)


# ---------------------------------------------------------------------------
# 17. Invalid identifier / number boundary
# ---------------------------------------------------------------------------

class TestInvalidBoundary:
    def test_digit_then_alpha_raises(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("SELECT * FROM students WHERE marks > 80abc")
        err = exc_info.value
        assert err.line >= 1

    def test_digit_start_identifier_raises(self) -> None:
        """A bare digit-starting word is caught at the boundary check."""
        with pytest.raises(LexerError):
            tokenize("SELECT * FROM students WHERE marks > 9x")

    def test_valid_number_not_rejected(self) -> None:
        """Pure integer followed by whitespace is fine."""
        toks = tokenize("SELECT * FROM students WHERE marks > 100")
        num = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num.value == "100"


# ---------------------------------------------------------------------------
# 18. STAR (wildcard) token
# ---------------------------------------------------------------------------

class TestStarToken:
    def test_star_type(self) -> None:
        toks = tokenize("SELECT * FROM students")
        assert toks[1].type == TokenType.STAR

    def test_star_value(self) -> None:
        toks = tokenize("SELECT * FROM students")
        assert toks[1].value == "*"


# ---------------------------------------------------------------------------
# 19. EOF sentinel
# ---------------------------------------------------------------------------

class TestEOF:
    def test_eof_always_last(self) -> None:
        for q in [
            "SELECT * FROM students",
            "SELECT * FROM students;",
            "SELECT name FROM students WHERE marks > 80",
        ]:
            toks = tokenize(q)
            assert toks[-1].type == TokenType.EOF

    def test_eof_value_is_empty(self) -> None:
        toks = tokenize("SELECT * FROM students")
        assert toks[-1].value == ""

    def test_empty_query_yields_only_eof(self) -> None:
        toks = tokenize("")
        assert toks == [Token(TokenType.EOF, "", 1, 1)]

    def test_whitespace_only_yields_only_eof(self) -> None:
        toks = tokenize("   \n\t  ")
        assert toks[-1].type == TokenType.EOF
        assert len(toks) == 1


# ---------------------------------------------------------------------------
# 20. Token position tracking (line and col)
# ---------------------------------------------------------------------------

class TestPositionTracking:
    def test_first_token_at_line1_col1(self) -> None:
        toks = tokenize("SELECT * FROM students")
        assert toks[0].line == 1
        assert toks[0].col  == 1

    def test_column_advances(self) -> None:
        toks = tokenize("SELECT * FROM students")
        # SELECT starts at col 1, * at col 8
        select_tok = toks[0]
        star_tok   = toks[1]
        assert select_tok.col < star_tok.col

    def test_newline_resets_column(self) -> None:
        q = "SELECT *\nFROM students"
        toks = tokenize(q)
        from_tok = next(t for t in toks if t.value == "FROM")
        assert from_tok.line == 2
        assert from_tok.col  == 1

    def test_string_token_position(self) -> None:
        q = "SELECT * FROM students WHERE department = 'CSE'"
        toks = tokenize(q)
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.line == 1
        assert str_tok.col > 1   # starts after the opening quote

    def test_number_token_position(self) -> None:
        q = "SELECT * FROM students WHERE marks > 80"
        toks = tokenize(q)
        num_tok = next(t for t in toks if t.type == TokenType.NUMBER)
        assert num_tok.line == 1
        assert num_tok.col  > 1


# ---------------------------------------------------------------------------
# 21. Reference query — full exact token sequence
#
#     SELECT name, marks
#     FROM students
#     WHERE department = 'CSE'
#     AND marks > 80
#     ORDER BY marks DESC;
# ---------------------------------------------------------------------------

REFERENCE_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""

EXPECTED_REFERENCE_TYPES = [
    TokenType.KEYWORD,     # SELECT
    TokenType.IDENTIFIER,  # name
    TokenType.COMMA,       # ,
    TokenType.IDENTIFIER,  # marks
    TokenType.KEYWORD,     # FROM
    TokenType.IDENTIFIER,  # students
    TokenType.KEYWORD,     # WHERE
    TokenType.IDENTIFIER,  # department
    TokenType.OPERATOR,    # =
    TokenType.STRING,      # CSE
    TokenType.KEYWORD,     # AND
    TokenType.IDENTIFIER,  # marks
    TokenType.OPERATOR,    # >
    TokenType.NUMBER,      # 80
    TokenType.KEYWORD,     # ORDER
    TokenType.KEYWORD,     # BY
    TokenType.IDENTIFIER,  # marks
    TokenType.KEYWORD,     # DESC
    TokenType.SEMICOLON,   # ;
    TokenType.EOF,
]

EXPECTED_REFERENCE_VALUES = [
    "SELECT", "name", ",", "marks",
    "FROM", "students",
    "WHERE", "department", "=", "CSE",
    "AND", "marks", ">", "80",
    "ORDER", "BY", "marks", "DESC",
    ";", "",
]


class TestReferenceQuery:
    def test_reference_token_types(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        assert [t.type for t in toks] == EXPECTED_REFERENCE_TYPES

    def test_reference_token_values(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        assert [t.value for t in toks] == EXPECTED_REFERENCE_VALUES

    def test_reference_token_count(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        assert len(toks) == len(EXPECTED_REFERENCE_TYPES)

    def test_reference_select_on_line1(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        assert toks[0].line == 1

    def test_reference_from_on_line2(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        from_tok = next(t for t in toks if t.value == "FROM")
        assert from_tok.line == 2

    def test_reference_where_on_line3(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        where_tok = next(t for t in toks if t.value == "WHERE")
        assert where_tok.line == 3

    def test_reference_and_on_line4(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        and_tok = next(t for t in toks if t.value == "AND")
        assert and_tok.line == 4

    def test_reference_order_on_line5(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        order_tok = next(t for t in toks if t.value == "ORDER")
        assert order_tok.line == 5

    def test_string_value_no_quotes(self) -> None:
        toks = tokenize(REFERENCE_QUERY)
        str_tok = next(t for t in toks if t.type == TokenType.STRING)
        assert str_tok.value == "CSE"
        assert "'" not in str_tok.value


# ---------------------------------------------------------------------------
# 22. All spec valid-query examples
# ---------------------------------------------------------------------------

class TestSpecExamples:
    def test_example_2_marks_gte_90(self) -> None:
        q = "SELECT name FROM students WHERE marks >= 90;"
        toks = tokenize(q)
        op_tok = next(t for t in toks if t.type == TokenType.OPERATOR)
        assert op_tok.value == ">="

    def test_example_3_or_condition(self) -> None:
        q = "SELECT name, department FROM students WHERE department = 'CSE' OR department = 'ECE';"
        kws = [t.value for t in tokenize(q) if t.type == TokenType.KEYWORD]
        assert "OR" in kws

    def test_example_4_star_order_asc(self) -> None:
        q = "SELECT * FROM students ORDER BY semester ASC;"
        tys = types(q)
        assert TokenType.STAR    in tys
        assert TokenType.KEYWORD in tys

    def test_example_5_not_equal(self) -> None:
        q = "SELECT name, department, marks FROM students WHERE department != 'ME';"
        op_tok = next(t for t in tokenize(q) if t.type == TokenType.OPERATOR)
        assert op_tok.value == "!="

    def test_example_6_chained_and(self) -> None:
        q = "SELECT name, marks FROM students WHERE semester = 3 AND marks >= 70 AND marks <= 90;"
        kws = [t.value for t in tokenize(q) if t.type == TokenType.KEYWORD]
        assert kws.count("AND") == 2

    def test_example_7_minimal(self) -> None:
        q = "SELECT * FROM students;"
        tys = types(q)
        assert tys == [
            TokenType.KEYWORD,
            TokenType.STAR,
            TokenType.KEYWORD,
            TokenType.IDENTIFIER,
            TokenType.SEMICOLON,
            TokenType.EOF,
        ]


# ---------------------------------------------------------------------------
# 23. is_keyword() helper
# ---------------------------------------------------------------------------

class TestTokenHelpers:
    def test_is_keyword_true(self) -> None:
        toks = tokenize("SELECT * FROM students")
        select_tok = toks[0]
        assert select_tok.is_keyword("SELECT")
        assert select_tok.is_keyword("select")   # case-insensitive

    def test_is_keyword_false_for_identifier(self) -> None:
        toks = tokenize("SELECT name FROM students")
        name_tok = next(t for t in toks if t.value == "name")
        assert not name_tok.is_keyword("name")

    def test_is_keyword_multi_arg(self) -> None:
        toks = tokenize("SELECT * FROM students ORDER BY marks DESC")
        desc_tok = next(t for t in toks if t.value == "DESC")
        assert desc_tok.is_keyword("ASC", "DESC")

    def test_token_repr(self) -> None:
        tok = Token(TokenType.KEYWORD, "SELECT", 1, 1)
        r = repr(tok)
        assert "KEYWORD" in r
        assert "SELECT"  in r
