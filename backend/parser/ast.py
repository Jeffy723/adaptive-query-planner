"""
backend/parser/ast.py

Abstract Syntax Tree (AST) node definitions for the mini SQL-like query
language.

Design principles
-----------------
- Every node is a frozen dataclass: immutable, hashable, printable.
- Nodes carry only structural / syntactic information — no runtime values,
  no execution logic, no schema lookups.
- Every node records the source Token that anchored it so that later stages
  (semantic analyser, visualiser) can report accurate line/col positions.
- The hierarchy is deliberately flat: one class per distinct concept, with
  a union type (ConditionNode) to allow condition trees of arbitrary depth.

Node hierarchy
--------------
    IntegerLiteral       — numeric literal  (e.g. 80)
    StringLiteral        — string literal   (e.g. 'CSE')
    Literal              — union alias for the two literal types

    ColumnRef            — reference to a column by name
    Wildcard             — the '*' in SELECT *

    ComparisonExpr       — <column> <op> <literal>
    LogicalExpr          — <left-condition> AND|OR <right-condition>
    ConditionNode        — union alias for condition types

    SelectClause         — the SELECT part (list of columns or wildcard)
    FromClause           — the FROM part (table name)
    OrderByClause        — the ORDER BY part (column + direction)
    WhereClause          — the WHERE part (root condition)

    Query                — root node: the complete parsed query
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from backend.lexer.token import Token


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntegerLiteral:
    """
    An integer literal value, e.g. 80.

    Attributes
    ----------
    value:
        The integer value parsed from the NUMBER token.
    token:
        The source NUMBER token (preserves position).
    """
    value: int
    token: Token

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class StringLiteral:
    """
    A string literal value, e.g. 'CSE' (stored without quotes).

    Attributes
    ----------
    value:
        The string content (quotes already stripped by the lexer).
    token:
        The source STRING token (preserves position).
    """
    value: str
    token: Token

    def __str__(self) -> str:
        return f"'{self.value}'"


#: Union of supported literal node types.
Literal = Union[IntegerLiteral, StringLiteral]


# ---------------------------------------------------------------------------
# Column reference and wildcard
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnRef:
    """
    A reference to a named column (identifier), e.g. ``marks``.

    Attributes
    ----------
    name:
        Column name as written (case preserved).
    token:
        The source IDENTIFIER token.
    """
    name: str
    token: Token

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Wildcard:
    """
    The ``*`` wildcard in ``SELECT *``.

    Attributes
    ----------
    token:
        The source STAR token.
    """
    token: Token

    def __str__(self) -> str:
        return "*"


# ---------------------------------------------------------------------------
# Condition expressions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComparisonExpr:
    """
    A simple comparison: ``<column> <op> <literal>``.

    Examples:  marks > 80,  department = 'CSE',  semester != 3

    Attributes
    ----------
    column:
        The left-hand column reference.
    operator:
        One of: =  !=  >  <  >=  <=
    right:
        The right-hand literal.
    token:
        The OPERATOR token (anchors position for error messages).
    """
    column:   ColumnRef
    operator: str
    right:    Literal
    token:    Token

    def __str__(self) -> str:
        return f"{self.column} {self.operator} {self.right}"


@dataclass(frozen=True)
class LogicalExpr:
    """
    A binary logical combination: ``<left> AND|OR <right>``.

    Per the language spec, conditions are evaluated strictly left-to-right
    with no operator precedence.  This means that:

        A AND B OR C

    is parsed as:

        LogicalExpr(LogicalExpr(A, "AND", B), "OR", C)

    Attributes
    ----------
    left:
        The left operand (a ComparisonExpr or another LogicalExpr).
    operator:
        "AND" or "OR".
    right:
        The right operand (always a ComparisonExpr at parse time,
        because we fold left-to-right).
    token:
        The AND/OR keyword token (anchors position).
    """
    left:     "ConditionNode"
    operator: str
    right:    "ConditionNode"
    token:    Token

    def __str__(self) -> str:
        return f"({self.left} {self.operator} {self.right})"


#: Union of all valid condition-tree node types.
ConditionNode = Union[ComparisonExpr, LogicalExpr]


# ---------------------------------------------------------------------------
# Clause nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelectClause:
    """
    The SELECT part of a query.

    Attributes
    ----------
    columns:
        Either a single Wildcard, or a tuple of one or more ColumnRef nodes.
    token:
        The SELECT keyword token.
    """
    columns: Union[Wildcard, tuple[ColumnRef, ...]]
    token:   Token

    @property
    def is_wildcard(self) -> bool:
        """True when the user wrote SELECT *."""
        return isinstance(self.columns, Wildcard)

    def __str__(self) -> str:
        if self.is_wildcard:
            return "SELECT *"
        cols = ", ".join(str(c) for c in self.columns)  # type: ignore[union-attr]
        return f"SELECT {cols}"


@dataclass(frozen=True)
class FromClause:
    """
    The FROM part of a query.

    Attributes
    ----------
    table_name:
        The name of the table as written.
    token:
        The IDENTIFIER token for the table name.
    """
    table_name: str
    token:      Token

    def __str__(self) -> str:
        return f"FROM {self.table_name}"


@dataclass(frozen=True)
class WhereClause:
    """
    The WHERE part of a query (optional).

    Attributes
    ----------
    condition:
        The root of the condition tree (ComparisonExpr or LogicalExpr).
    token:
        The WHERE keyword token.
    """
    condition: ConditionNode
    token:     Token

    def __str__(self) -> str:
        return f"WHERE {self.condition}"


@dataclass(frozen=True)
class OrderByClause:
    """
    The ORDER BY part of a query (optional).

    Attributes
    ----------
    column:
        The column to sort by.
    direction:
        "ASC" or "DESC".  Default (when neither keyword is written) is "ASC".
    token:
        The ORDER keyword token.
    """
    column:    ColumnRef
    direction: str       # "ASC" | "DESC"
    token:     Token

    def __str__(self) -> str:
        return f"ORDER BY {self.column} {self.direction}"


# ---------------------------------------------------------------------------
# Root node
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    """
    Root AST node representing a complete parsed query.

    Attributes
    ----------
    select:
        The SELECT clause (always present).
    from_clause:
        The FROM clause (always present).
    where:
        The WHERE clause, or None if omitted.
    order_by:
        The ORDER BY clause, or None if omitted.
    """
    select:      SelectClause
    from_clause: FromClause
    where:       WhereClause | None
    order_by:    OrderByClause | None

    def __str__(self) -> str:
        parts = [str(self.select), str(self.from_clause)]
        if self.where:
            parts.append(str(self.where))
        if self.order_by:
            parts.append(str(self.order_by))
        return " ".join(parts)
