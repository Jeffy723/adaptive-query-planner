"""
backend/lexer/lexer.py

Lexical analyser for the mini SQL-like query language.

Public API
----------
    Lexer(query: str).tokenize() -> list[Token]

The lexer reads the query string character-by-character, produces a flat
list of Token objects, and appends a final EOF token.

Raises LexerError for any character or construct that cannot be tokenised.

Design notes
------------
- Single-pass, character-by-character scan (no regex).
- Tracks 1-based line and column for every token.
- Keywords are recognised case-insensitively; their Token.value is the
  canonical UPPER-CASE form.
- Identifiers preserve their original case.
- STRING token values strip the surrounding single-quotes so consumers
  work with the raw content (e.g. 'CSE' → value "CSE").
- NUMBER tokens store the digit string; conversion to int is left to the
  parser/executor.
- Two-character operators (!=, >=, <=) are detected with one-char lookahead.
- Whitespace (space, tab, carriage-return, newline) is skipped.
- EOF token is always appended as a sentinel.
"""

from __future__ import annotations

from typing import List

from .errors import LexerError
from .token  import KEYWORDS, Token, TokenType


class Lexer:
    """
    Tokenise a mini SQL-like query string.

    Parameters
    ----------
    query:
        The raw query string to tokenise.

    Usage
    -----
        tokens = Lexer("SELECT name FROM students;").tokenize()
    """

    def __init__(self, query: str) -> None:
        self._src: str       = query
        self._pos: int       = 0          # current character index in _src
        self._line: int      = 1          # current 1-based line number
        self._col: int       = 1          # current 1-based column number
        self._tokens: list[Token] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def tokenize(self) -> list[Token]:
        """
        Scan the entire query and return the complete token list.

        The list always ends with a single EOF token.

        Raises
        ------
        LexerError
            If an unrecognised character or malformed literal is encountered.
        """
        self._tokens = []
        while not self._at_end():
            self._skip_whitespace()
            if self._at_end():
                break
            self._scan_token()

        self._tokens.append(
            Token(TokenType.EOF, "", self._line, self._col)
        )
        return self._tokens

    # ------------------------------------------------------------------
    # Core scanner
    # ------------------------------------------------------------------

    def _scan_token(self) -> None:
        """Scan and emit one token starting at the current position."""
        line = self._line
        col  = self._col
        ch   = self._advance()

        # --- Comma -------------------------------------------------------
        if ch == ",":
            self._emit(TokenType.COMMA, ",", line, col)

        # --- Semicolon ---------------------------------------------------
        elif ch == ";":
            self._emit(TokenType.SEMICOLON, ";", line, col)

        # --- Star (wildcard) --------------------------------------------
        elif ch == "*":
            self._emit(TokenType.STAR, "*", line, col)

        # --- Single-quote string literal --------------------------------
        elif ch == "'":
            self._scan_string(line, col)

        # --- Operators --------------------------------------------------
        elif ch in ("=", "!", ">", "<"):
            self._scan_operator(ch, line, col)

        # --- Numeric literal --------------------------------------------
        elif ch.isdigit():
            self._scan_number(ch, line, col)

        # --- Identifier / keyword --------------------------------------
        elif ch.isalpha() or ch == "_":
            self._scan_word(ch, line, col)

        # --- Anything else is an error ---------------------------------
        else:
            src_line = self._source_line(line)
            raise LexerError(
                f"Unexpected character {ch!r}",
                line,
                col,
                src_line,
            )

    # ------------------------------------------------------------------
    # Token-specific scanners
    # ------------------------------------------------------------------

    def _scan_string(self, start_line: int, start_col: int) -> None:
        """
        Scan a single-quoted string literal.

        The opening quote has already been consumed.  Reads until the
        closing quote or end-of-input (which is an error).
        String token value is the content WITHOUT surrounding quotes.
        """
        buf: list[str] = []
        while True:
            if self._at_end():
                src_line = self._source_line(start_line)
                raise LexerError(
                    "Unterminated string literal (missing closing ')",
                    start_line,
                    start_col,
                    src_line,
                )
            ch = self._advance()
            if ch == "'":
                break
            buf.append(ch)
        self._emit(TokenType.STRING, "".join(buf), start_line, start_col)

    def _scan_number(self, first: str, start_line: int, start_col: int) -> None:
        """
        Scan an integer literal.

        *first* is the digit already consumed.
        """
        buf = [first]
        while not self._at_end() and self._peek().isdigit():
            buf.append(self._advance())

        # Reject things like "123abc" — digit string immediately followed
        # by an identifier character is a lexical error.
        if not self._at_end() and (self._peek().isalpha() or self._peek() == "_"):
            bad_col  = start_col + len(buf)
            src_line = self._source_line(start_line)
            raise LexerError(
                f"Invalid token: digit sequence {(''.join(buf))!r} "
                f"immediately followed by identifier character {self._peek()!r}",
                start_line,
                bad_col,
                src_line,
            )

        self._emit(TokenType.NUMBER, "".join(buf), start_line, start_col)

    def _scan_word(self, first: str, start_line: int, start_col: int) -> None:
        """
        Scan an identifier or keyword.

        *first* is the leading letter/underscore already consumed.
        Keywords are emitted with their canonical UPPER-CASE value.
        Identifiers keep their original case.
        """
        buf = [first]
        while not self._at_end() and (
            self._peek().isalnum() or self._peek() == "_"
        ):
            buf.append(self._advance())

        word = "".join(buf)
        if word.upper() in KEYWORDS:
            self._emit(TokenType.KEYWORD, word.upper(), start_line, start_col)
        else:
            self._emit(TokenType.IDENTIFIER, word, start_line, start_col)

    def _scan_operator(self, first: str, start_line: int, start_col: int) -> None:
        """
        Scan a comparison operator.

        Handles both single-character (=, >, <) and two-character (!=, >=, <=)
        forms.  '!' not followed by '=' is a lexical error.
        """
        # Two-character operators
        if first in (">", "<") and not self._at_end() and self._peek() == "=":
            self._advance()
            self._emit(TokenType.OPERATOR, first + "=", start_line, start_col)
        elif first == "!":
            if self._at_end() or self._peek() != "=":
                src_line = self._source_line(start_line)
                raise LexerError(
                    f"Unexpected character '!': did you mean '!='?",
                    start_line,
                    start_col,
                    src_line,
                )
            self._advance()  # consume '='
            self._emit(TokenType.OPERATOR, "!=", start_line, start_col)
        else:
            # Single-character: = > <
            self._emit(TokenType.OPERATOR, first, start_line, start_col)

    # ------------------------------------------------------------------
    # Low-level character helpers
    # ------------------------------------------------------------------

    def _at_end(self) -> bool:
        return self._pos >= len(self._src)

    def _peek(self) -> str:
        """Return the current character without advancing."""
        return self._src[self._pos]

    def _advance(self) -> str:
        """Return the current character and advance the position."""
        ch = self._src[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    def _skip_whitespace(self) -> None:
        """Skip spaces, tabs, carriage-returns, and newlines."""
        while not self._at_end() and self._peek() in (" ", "\t", "\r", "\n"):
            self._advance()

    def _emit(
        self,
        ttype: TokenType,
        value: str,
        line: int,
        col: int,
    ) -> None:
        self._tokens.append(Token(ttype, value, line, col))

    def _source_line(self, line_number: int) -> str:
        """Return the full text of *line_number* (1-based) from the source."""
        lines = self._src.splitlines()
        idx   = line_number - 1
        if 0 <= idx < len(lines):
            return lines[idx]
        return ""
