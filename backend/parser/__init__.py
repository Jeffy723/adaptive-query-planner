"""
backend/parser — Parser and AST for the mini SQL-like query language.

Public API
----------
    from backend.parser import Parser, ParseError
    from backend.parser import (
        Query, SelectClause, FromClause, WhereClause, OrderByClause,
        ComparisonExpr, LogicalExpr, ColumnRef, Wildcard,
        IntegerLiteral, StringLiteral,
    )

    tokens = Lexer(query_string).tokenize()
    ast    = Parser(tokens).parse()       # -> Query
"""

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
from .parser import Parser

__all__ = [
    # Entry point
    "Parser",
    # Error
    "ParseError",
    # AST nodes — root
    "Query",
    # AST nodes — clauses
    "SelectClause",
    "FromClause",
    "WhereClause",
    "OrderByClause",
    # AST nodes — expressions
    "ComparisonExpr",
    "LogicalExpr",
    # AST nodes — leaves
    "ColumnRef",
    "Wildcard",
    "IntegerLiteral",
    "StringLiteral",
    # Union aliases (useful for type hints in later stages)
    "ConditionNode",
    "Literal",
]
