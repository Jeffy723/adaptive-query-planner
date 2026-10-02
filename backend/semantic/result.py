"""
backend/semantic/result.py

SemanticAnalysisResult — the structured outcome of semantic validation.

Returning a result object (rather than raising an exception) lets callers
collect *all* errors in one pass and present them together in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.schema import TableSchema

from .errors import SemanticError


@dataclass
class SemanticAnalysisResult:
    """
    The complete outcome of a semantic analysis pass.

    Attributes
    ----------
    valid:
        True if and only if no semantic errors were found.
    errors:
        List of SemanticError objects, one per violation discovered.
        Empty when valid is True.
    table_schema:
        The TableSchema resolved for the query's FROM clause.
        None if the table was not found (in which case valid is False and
        further column checks were skipped).
    resolved_columns:
        The ordered list of column names that the SELECT clause resolves to.
        For ``SELECT *`` this is every column in the table.
        For named columns it is exactly the names written in the query.
        Empty if semantic analysis failed before resolution was possible.
    """
    valid:            bool
    errors:           list[SemanticError] = field(default_factory=list)
    table_schema:     TableSchema | None  = None
    resolved_columns: list[str]           = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers used by later pipeline stages
    # ------------------------------------------------------------------

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def first_error(self) -> SemanticError | None:
        """Return the first error, or None if there are none."""
        return self.errors[0] if self.errors else None

    def __str__(self) -> str:
        if self.valid:
            cols = ", ".join(self.resolved_columns)
            return f"SemanticAnalysisResult(valid=True, columns=[{cols}])"
        msgs = "; ".join(e.message for e in self.errors)
        return f"SemanticAnalysisResult(valid=False, errors=[{msgs}])"
