"""
backend/ir/builder.py

AST → IR transformation (build_ir).

Public API
----------
    build_ir(ast, semantic_result) -> LogicalPlan

Transforms a semantically valid Query AST into a LogicalPlan.

Raises IRBuildError if the semantic result indicates an invalid query,
so that callers cannot accidentally build an IR from a broken AST.

Transformation rules
--------------------
    SELECT clause   → ProjectOp (columns resolved by semantic analyser)
    FROM clause     → ScanOp
    WHERE clause    → FilterOp  (condition tree preserved as IRPredicate)
    ORDER BY clause → SortOp

Pipeline ordering (SCAN → FILTER → PROJECT → SORT)
---------------------------------------------------
The initial IR always uses this deterministic order.
No optimisation or reordering is performed here.

The builder is a pure function — it reads the AST and the semantic result,
creates new immutable IR nodes, and returns them.
It does NOT modify the AST or the semantic result.
"""

from __future__ import annotations

from backend.parser.ast import (
    ComparisonExpr,
    ConditionNode,
    IntegerLiteral,
    LogicalExpr,
    Query,
    StringLiteral,
)
from backend.semantic.result import SemanticAnalysisResult

from .nodes import (
    FilterOp,
    IRColumnRef,
    IRComparison,
    IRLiteral,
    IRLiteralType,
    IRLogicalExpr,
    IRPredicate,
    LogicalPlan,
    Operation,
    ProjectOp,
    ScanOp,
    SortOp,
)


class IRBuildError(Exception):
    """
    Raised when build_ir() is called with a semantically invalid result.

    Attributes
    ----------
    message:
        Human-readable reason why the IR could not be built.
    """
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def build_ir(ast: Query, semantic_result: SemanticAnalysisResult) -> LogicalPlan:
    """
    Transform a validated Query AST into a LogicalPlan.

    Parameters
    ----------
    ast:
        The root Query AST node produced by the parser.
    semantic_result:
        The SemanticAnalysisResult from analyzing *ast*.
        Must be valid (semantic_result.valid == True).

    Returns
    -------
    LogicalPlan
        An immutable, ordered sequence of relational operations.

    Raises
    ------
    IRBuildError
        If semantic_result.valid is False, preventing IR generation
        from invalid queries.
    """
    if not semantic_result.valid:
        error_summary = "; ".join(e.message for e in semantic_result.errors)
        raise IRBuildError(
            f"Cannot build IR from a semantically invalid query. "
            f"Errors: {error_summary}"
        )

    ops: list[Operation] = []

    # 1. SCAN — always first
    scan = ScanOp(table_name=ast.from_clause.table_name)
    ops.append(scan)

    # 2. FILTER — only if a WHERE clause is present
    if ast.where is not None:
        predicate = _build_predicate(ast.where.condition)
        ops.append(FilterOp(predicate=predicate))

    # 3. PROJECT — always present; uses the columns resolved by the semantic analyser
    # semantic_result.resolved_columns is already expanded (SELECT * → concrete list)
    project = ProjectOp(columns=tuple(semantic_result.resolved_columns))
    ops.append(project)

    # 4. SORT — only if an ORDER BY clause is present
    if ast.order_by is not None:
        sort = SortOp(
            column=ast.order_by.column.name,
            direction=ast.order_by.direction,
        )
        ops.append(sort)

    return LogicalPlan(
        operations=tuple(ops),
        source_table=ast.from_clause.table_name,
    )


# ---------------------------------------------------------------------------
# Internal helpers — condition/predicate translation
# ---------------------------------------------------------------------------

def _build_predicate(node: ConditionNode) -> IRPredicate:
    """
    Recursively translate an AST condition tree into an IRPredicate tree.

    The logical structure (AND/OR nesting, left-to-right order) is preserved
    exactly — no reordering, no flattening.
    """
    if isinstance(node, LogicalExpr):
        return IRLogicalExpr(
            left=_build_predicate(node.left),
            operator=node.operator,          # "AND" | "OR"
            right=_build_predicate(node.right),
        )

    if isinstance(node, ComparisonExpr):
        return _build_comparison(node)

    # Should never happen with a well-formed AST, but guard anyway.
    raise IRBuildError(  # pragma: no cover
        f"Unknown condition node type: {type(node).__name__}"
    )


def _build_comparison(node: ComparisonExpr) -> IRComparison:
    """Translate a single AST ComparisonExpr into an IRComparison."""
    column = IRColumnRef(name=node.column.name)
    value  = _build_literal(node.right)
    return IRComparison(column=column, operator=node.operator, value=value)


def _build_literal(node) -> IRLiteral:
    """Translate an AST literal into an IRLiteral."""
    if isinstance(node, IntegerLiteral):
        return IRLiteral(value=node.value, literal_type=IRLiteralType.INTEGER)
    if isinstance(node, StringLiteral):
        return IRLiteral(value=node.value, literal_type=IRLiteralType.STRING)
    raise IRBuildError(  # pragma: no cover
        f"Unknown literal node type: {type(node).__name__}"
    )
