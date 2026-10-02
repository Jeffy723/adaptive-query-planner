"""
backend/lexer — Lexical analyser for the mini SQL-like query language.

Public API
----------
    from backend.lexer import Lexer, Token, TokenType, LexerError

    tokens = Lexer("SELECT name FROM students;").tokenize()

The tokenize() method returns a list[Token] ending with a single EOF token.
Raises LexerError on any unrecognised input.
"""

from .errors import LexerError
from .lexer  import Lexer
from .token  import KEYWORDS, Token, TokenType

__all__ = [
    "Lexer",
    "Token",
    "TokenType",
    "LexerError",
    "KEYWORDS",
]
