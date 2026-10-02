"""
backend/semantic/errors.py

SemanticError — a single semantic validation failure.

Each error is associated with the AST token that caused it so that future
UI layers can highlight the exact query location.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from backend.lexer.token import Token


class ErrorCode(Enum):
    """
    Machine-readable category for each semantic error.

    Using an enum instead of bare strings lets the UI and future stages
    switch on error category without string parsing.
    """
    UNKNOWN_TABLE       = auto()   # Table not registered in the schema registry
    UNKNOWN_COLUMN      = auto()   # Column does not exist in the resolved table
    TYPE_MISMATCH       = auto()   # Literal type incompatible with column type
    OPERATOR_MISMATCH   = auto()   # Operator not supported for the column type


@dataclass(frozen=True)
class SemanticError:
    """
    A single semantic validation error.

    Attributes
    ----------
    code:
        Machine-readable error category (ErrorCode).
    message:
        Human-readable description suitable for display in a UI.
    token:
        The source token closest to the problem; carries line/col info.
        Used by the UI to highlight the relevant query location.
    """
    code:    ErrorCode
    message: str
    token:   Token

    def __str__(self) -> str:
        return (
            f"SemanticError [{self.code.name}] "
            f"at line {self.token.line}, col {self.token.col}: "
            f"{self.message}"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SemanticError(code={self.code.name!r}, "
            f"message={self.message!r}, "
            f"line={self.token.line}, col={self.token.col})"
        )
