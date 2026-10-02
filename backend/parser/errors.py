"""
backend/parser/errors.py

ParseError — the only exception type raised by the parser.
"""

from __future__ import annotations

from backend.lexer.token import Token


class ParseError(Exception):
    """
    Raised when the parser encounters a token sequence that violates the
    supported grammar.

    Attributes
    ----------
    message:
        Human-readable description of the syntax problem.
    token:
        The token at which the error was detected.
        May be an EOF token when input ends unexpectedly.
    """

    def __init__(self, message: str, token: Token) -> None:
        self.message = message
        self.token   = token
        super().__init__(self._format())

    def _format(self) -> str:
        return (
            f"ParseError at line {self.token.line}, col {self.token.col} "
            f"(token={self.token.type.name} {self.token.value!r}): "
            f"{self.message}"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ParseError(message={self.message!r}, token={self.token!r})"
        )
