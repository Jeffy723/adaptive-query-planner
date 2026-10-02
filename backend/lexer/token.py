"""
backend/lexer/token.py

Token types and the Token data structure used by the lexer.

TokenType — enumeration of every distinct token category
Token     — immutable record produced by the lexer for each lexeme
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """
    Every distinct category of token the lexer can produce.

    Categories
    ----------
    KEYWORD     - reserved word recognised by the language (SELECT, FROM, …)
    IDENTIFIER  - user-supplied name for a table or column
    NUMBER      - integer literal (e.g. 80, 0, 100)
    STRING      - single-quoted string literal (e.g. 'CSE')
    OPERATOR    - comparison operator (=, !=, >, <, >=, <=)
    COMMA       - the , separator in select lists
    STAR        - the * wildcard in SELECT *
    SEMICOLON   - the optional ; query terminator
    EOF         - sentinel emitted once after all tokens are consumed
    """
    KEYWORD    = auto()
    IDENTIFIER = auto()
    NUMBER     = auto()
    STRING     = auto()
    OPERATOR   = auto()
    COMMA      = auto()
    STAR       = auto()
    SEMICOLON  = auto()
    EOF        = auto()


# The nine reserved keywords, stored upper-case for O(1) look-up.
KEYWORDS: frozenset[str] = frozenset({
    "SELECT", "FROM", "WHERE",
    "AND", "OR",
    "ORDER", "BY",
    "ASC", "DESC",
})


@dataclass(frozen=True)
class Token:
    """
    A single token produced by the lexer.

    Attributes
    ----------
    type:
        The category of this token (see TokenType).
    value:
        The exact lexeme as it appeared in the source string.
        - KEYWORD    → canonical uppercase form  (e.g. "SELECT")
        - IDENTIFIER → original mixed-case form  (e.g. "marks")
        - NUMBER     → decimal digit string      (e.g. "80")
        - STRING     → content WITHOUT the surrounding single-quotes
                       (e.g. "CSE" for 'CSE')
        - OPERATOR   → operator characters       (e.g. ">=")
        - COMMA      → ","
        - STAR       → "*"
        - SEMICOLON  → ";"
        - EOF        → ""
    line:
        1-based line number where the token starts.
    col:
        1-based column number where the token starts.
    """
    type:  TokenType
    value: str
    line:  int
    col:   int

    def __repr__(self) -> str:
        return (
            f"Token({self.type.name}, {self.value!r}, "
            f"line={self.line}, col={self.col})"
        )

    def is_keyword(self, *words: str) -> bool:
        """
        Return True if this token is a KEYWORD whose value matches
        any of *words* (comparison is case-insensitive for convenience).
        """
        if self.type is not TokenType.KEYWORD:
            return False
        upper = self.value.upper()
        return any(upper == w.upper() for w in words)
