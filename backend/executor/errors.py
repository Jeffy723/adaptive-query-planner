"""
backend/executor/errors.py

ExecutionError — the only exception type raised by the executor.
"""

from __future__ import annotations


class ExecutionError(Exception):
    """
    Raised when the executor encounters a runtime problem.

    Examples:
    - CSV file not found or unreadable
    - Malformed CSV row (wrong number of columns)
    - Unexpected type conversion failure
    - Missing column in a row during filter/project/sort

    Attributes
    ----------
    message:
        Human-readable description of the problem.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __repr__(self) -> str:  # pragma: no cover
        return f"ExecutionError({self.message!r})"
