"""
backend/parser/parser.py

Recursive-descent parser for the mini SQL-like query language.

Public API
----------
    Parser(tokens).parse() -> Query

Takes the list[Token] produced by the lexer (must include the trailing EOF),
validates the grammar, and returns the root Query AST node.

Raises ParseError on any grammar violation with the offending token attached.

Grammar (matches docs/QUERY_LANGUAGE.md exactly)
-------------------------------------------------
    query
        = SELECT select_list FROM identifier
          [ WHERE condition ]
          [ ORDER BY identifier [ ASC | DESC ] ]
          [ SEMICOLON ]
          EOF

    select_list
        = STAR
        | identifier { COMMA identifier }

    condition
        = comparison { logical_op comparison }   -- left-to-right, no precedence

    comparison
        = identifier comparison_op literal

    comparison_op
        = '=' | '!=' | '>' | '<' | '>=' | '<='

    logical_op
        = AND | OR

    literal
        = NUMBER | STRING

Design notes
------------
- Single-pass, index-based token scan (no mutation of the token list).
- `_peek()` looks ahead one token without consuming; `_advance()` consumes.
- `_expect(type, value?)` consumes and returns the next token or raises.
- Conditions are parsed left-associatively in one flat loop so that
  A AND B OR C always yields LogicalExpr(LogicalExpr(A,AND,B), OR, C).
- Trailing non-EOF tokens after a valid query are a hard error.
"""

from __future__ import annotations

from backend.lexer.token import Token, TokenType

from .ast import (
    ColumnRef,
    ComparisonExpr,
    ConditionNode,
    FromClause,
    IntegerLiteral,
    Literal,
    LogicalExpr,
    OrderByClause,
    Query,
    SelectClause,
    StringLiteral,
    WhereClause,
    Wildcard,
)
from .errors import ParseError

# The comparison operators recognised in WHERE conditions.
_COMPARISON_OPS: frozenset[str] = frozenset({"=", "!=", ">", "<", ">=", "<="})


class Parser:
    """
    Recursive-descent parser for the mini SQL-like query language.

    Parameters
    ----------
    tokens:
        The flat token list produced by ``Lexer.tokenize()``.
        Must contain at least one EOF token as the last element.

    Usage
    -----
        from backend.lexer  import Lexer
        from backend.parser import Parser

        tokens = Lexer(query_string).tokenize()
        ast    = Parser(tokens).parse()
    """

    def __init__(self, tokens: list[Token]) -> None:
        if not tokens:
            raise ValueError("Token list must not be empty (expected at least EOF).")
        self._tokens: list[Token] = tokens
        self._pos:    int         = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse(self) -> Query:
        """
        Parse the token stream and return the root Query AST node.

        Raises
        ------
        ParseError
            On any grammar violation.
        """
        query = self._parse_query()
        # After a complete query, only SEMICOLON and EOF are acceptable.
        # _parse_query already consumed the optional semicolon.
        if self._peek().type is not TokenType.EOF:
            raise ParseError(
                f"Unexpected token after end of query; "
                f"expected end of input",
                self._peek(),
            )
        return query

    # ------------------------------------------------------------------
    # Grammar rules (one method per non-terminal)
    # ------------------------------------------------------------------

    def _parse_query(self) -> Query:
        """
        query = SELECT select_list FROM identifier
                [ WHERE condition ]
                [ ORDER BY identifier [ ASC | DESC ] ]
                [ SEMICOLON ]
        """
        # --- SELECT ---
        select_tok = self._expect(TokenType.KEYWORD, "SELECT")
        select_clause = self._parse_select_list(select_tok)

        # --- FROM ---
        self._expect(TokenType.KEYWORD, "FROM")
        table_tok = self._expect(TokenType.IDENTIFIER)
        from_clause = FromClause(table_name=table_tok.value, token=table_tok)

        # --- WHERE (optional) ---
        where_clause: WhereClause | None = None
        if self._peek().is_keyword("WHERE"):
            where_tok = self._advance()          # consume WHERE
            condition  = self._parse_condition()
            where_clause = WhereClause(condition=condition, token=where_tok)

        # --- ORDER BY (optional) ---
        order_clause: OrderByClause | None = None
        if self._peek().is_keyword("ORDER"):
            order_clause = self._parse_order_by()

        # --- optional SEMICOLON ---
        if self._peek().type is TokenType.SEMICOLON:
            self._advance()

        return Query(
            select=select_clause,
            from_clause=from_clause,
            where=where_clause,
            order_by=order_clause,
        )

    def _parse_select_list(self, select_tok: Token) -> SelectClause:
        """
        select_list = STAR | identifier { COMMA identifier }
        """
        tok = self._peek()

        # SELECT *
        if tok.type is TokenType.STAR:
            self._advance()
            return SelectClause(columns=Wildcard(token=tok), token=select_tok)

        # Must have at least one identifier
        if tok.type is not TokenType.IDENTIFIER:
            raise ParseError(
                "Expected a column name or '*' after SELECT",
                tok,
            )

        columns: list[ColumnRef] = []
        columns.append(ColumnRef(name=tok.value, token=tok))
        self._advance()

        while self._peek().type is TokenType.COMMA:
            self._advance()   # consume comma
            col_tok = self._expect(TokenType.IDENTIFIER,
                                   error_hint="Expected a column name after ','")
            columns.append(ColumnRef(name=col_tok.value, token=col_tok))

        return SelectClause(columns=tuple(columns), token=select_tok)

    def _parse_condition(self) -> ConditionNode:
        """
        condition = comparison { ( AND | OR ) comparison }

        Left-associative: A AND B OR C => LogicalExpr(LogicalExpr(A,AND,B), OR, C)
        """
        # We need at least one comparison; if none found, raise immediately.
        if not self._is_start_of_comparison():
            raise ParseError(
                "Expected a condition expression (e.g. column = value) "
                "after WHERE",
                self._peek(),
            )

        left: ConditionNode = self._parse_comparison()

        while self._peek().is_keyword("AND", "OR"):
            op_tok   = self._advance()          # consume AND / OR
            # right side must be a comparison
            if not self._is_start_of_comparison():
                raise ParseError(
                    f"Expected a comparison expression after {op_tok.value}",
                    self._peek(),
                )
            right = self._parse_comparison()
            left  = LogicalExpr(left=left, operator=op_tok.value, right=right,
                                token=op_tok)

        return left

    def _parse_comparison(self) -> ComparisonExpr:
        """
        comparison = identifier comparison_op literal
        """
        col_tok = self._expect(TokenType.IDENTIFIER,
                               error_hint="Expected a column name in condition")
        column  = ColumnRef(name=col_tok.value, token=col_tok)

        op_tok  = self._expect_operator()
        literal = self._parse_literal()

        return ComparisonExpr(column=column, operator=op_tok.value,
                               right=literal, token=op_tok)

    def _parse_literal(self) -> Literal:
        """
        literal = NUMBER | STRING
        """
        tok = self._peek()
        if tok.type is TokenType.NUMBER:
            self._advance()
            return IntegerLiteral(value=int(tok.value), token=tok)
        if tok.type is TokenType.STRING:
            self._advance()
            return StringLiteral(value=tok.value, token=tok)
        raise ParseError(
            f"Expected a literal value (number or quoted string), "
            f"got {tok.type.name} {tok.value!r}",
            tok,
        )

    def _parse_order_by(self) -> OrderByClause:
        """
        ORDER BY identifier [ ASC | DESC ]
        """
        order_tok = self._advance()          # consume ORDER

        if not self._peek().is_keyword("BY"):
            raise ParseError(
                "Expected 'BY' after 'ORDER'",
                self._peek(),
            )
        self._advance()                      # consume BY

        col_tok = self._expect(TokenType.IDENTIFIER,
                               error_hint="Expected a column name after 'ORDER BY'")
        column  = ColumnRef(name=col_tok.value, token=col_tok)

        direction = "ASC"                    # default
        if self._peek().is_keyword("ASC", "DESC"):
            direction = self._advance().value   # "ASC" or "DESC"

        return OrderByClause(column=column, direction=direction, token=order_tok)

    # ------------------------------------------------------------------
    # Token-stream helpers
    # ------------------------------------------------------------------

    def _peek(self) -> Token:
        """Return the current token without consuming it."""
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        """Return and consume the current token."""
        tok       = self._tokens[self._pos]
        if tok.type is not TokenType.EOF:
            self._pos += 1
        return tok

    def _expect(
        self,
        ttype:      TokenType,
        value:      str | None = None,
        error_hint: str | None = None,
    ) -> Token:
        """
        Consume the next token and return it.

        Raises ParseError if the token type (and optional value) do not match.

        Parameters
        ----------
        ttype:
            Required token type.
        value:
            If given, the token's value must also match (case-sensitive for
            non-keyword types; keywords are already uppercase).
        error_hint:
            Optional human-readable description of what was expected, used
            to build a clearer error message.
        """
        tok = self._peek()

        type_ok  = tok.type is ttype
        value_ok = (value is None) or (tok.value == value)

        if not (type_ok and value_ok):
            expected_desc = error_hint or (
                f"{ttype.name} {value!r}" if value else ttype.name
            )
            raise ParseError(
                f"Expected {expected_desc}, "
                f"got {tok.type.name} {tok.value!r}",
                tok,
            )
        return self._advance()

    def _expect_operator(self) -> Token:
        """
        Consume and return an OPERATOR token whose value is a valid
        comparison operator.  Raises ParseError otherwise.
        """
        tok = self._peek()
        if tok.type is not TokenType.OPERATOR or tok.value not in _COMPARISON_OPS:
            raise ParseError(
                f"Expected a comparison operator (=, !=, >, <, >=, <=), "
                f"got {tok.type.name} {tok.value!r}",
                tok,
            )
        return self._advance()

    def _is_start_of_comparison(self) -> bool:
        """
        Return True if the current token can begin a comparison expression.
        A comparison always starts with an IDENTIFIER (column name).
        """
        return self._peek().type is TokenType.IDENTIFIER
