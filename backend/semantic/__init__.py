"""
backend/semantic — Semantic Analyzer for the mini SQL-like query language.

Public API
----------
    from backend.semantic import SemanticAnalyzer, SemanticAnalysisResult
    from backend.semantic import SemanticError, ErrorCode

    from backend.schema import SCHEMA_REGISTRY

    result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)

    if result.valid:
        print("Query is semantically valid.")
        print("Resolved columns:", result.resolved_columns)
    else:
        for err in result.errors:
            print(err)
"""

from .analyzer import SemanticAnalyzer
from .errors   import ErrorCode, SemanticError
from .result   import SemanticAnalysisResult

__all__ = [
    "SemanticAnalyzer",
    "SemanticAnalysisResult",
    "SemanticError",
    "ErrorCode",
]
