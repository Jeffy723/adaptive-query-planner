"""
backend/lexer/errors.py

LexerError — the only exception type raised by the lexer.
"""

from __future__ import annotations


class LexerError(Exception):
    """
    Raised when the lexer encounters a character sequence it cannot tokenise.

    Attributes
    ----------
    message:
        Human-readable description of the problem.
    line:
        1-based line number where the error occurred.
    col:
        1-based column number where the error occurred.
    source_line:
        The full source line that contains the error, for display purposes.
        May be an empty string if not available.
    """

    def __init__(
        self,
        message: str,
        line: int,
        col: int,
        source_line: str = "",
    ) -> None:
        self.message     = message
        self.line        = line
        self.col         = col
        self.source_line = source_line
        super().__init__(self._format())

    def _format(self) -> str:
        base = f"LexerError at line {self.line}, col {self.col}: {self.message}"
        if self.source_line:
            pointer = " " * (self.col - 1) + "^"
            base += f"\n  {self.source_line}\n  {pointer}"
        return base

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"LexerError(message={self.message!r}, "
            f"line={self.line}, col={self.col})"
        )
