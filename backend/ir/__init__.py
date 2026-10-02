"""
backend/ir — Logical Intermediate Representation for the query engine.

Public API
----------
    from backend.ir import build_ir, IRBuildError
    from backend.ir import LogicalPlan, ScanOp, FilterOp, ProjectOp, SortOp
    from backend.ir import IRPredicate, IRComparison, IRLogicalExpr
    from backend.ir import IRColumnRef, IRLiteral, IRLiteralType

    plan = build_ir(ast, semantic_result)
    print(plan.explain())

The canonical pipeline:

    query string
        -> Lexer        -> tokens
        -> Parser       -> AST (Query)
        -> SemanticAnalyzer -> SemanticAnalysisResult
        -> build_ir()   -> LogicalPlan
"""

from .builder import IRBuildError, build_ir
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

__all__ = [
    # Builder
    "build_ir",
    "IRBuildError",
    # Plan container
    "LogicalPlan",
    # Operation nodes
    "ScanOp",
    "FilterOp",
    "ProjectOp",
    "SortOp",
    # Predicate nodes
    "IRComparison",
    "IRLogicalExpr",
    "IRColumnRef",
    "IRLiteral",
    "IRLiteralType",
    # Union aliases
    "IRPredicate",
    "Operation",
]
