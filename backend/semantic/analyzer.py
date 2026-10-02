"""
backend/semantic/analyzer.py

Semantic Analyzer for the mini SQL-like query language.

Public API
----------
    SemanticAnalyzer(schema_registry).analyze(ast) -> SemanticAnalysisResult

Takes the Query AST produced by the parser, validates it against the
registered table schemas, and returns a SemanticAnalysisResult describing
every semantic error found (or confirming that the query is valid).

The AST is NEVER modified.

Semantic rules implemented
--------------------------
  1. Dataset existence        — FROM table must be in the schema registry.
  2. SELECT column existence  — every named column in SELECT must exist.
  3. WHERE column existence   — every column referenced in conditions must exist.
  4. ORDER BY column existence — the ORDER BY column must exist.
  5. Type/literal compatibility:
       - INTEGER column  ↔  IntegerLiteral   : always valid
       - STRING  column  ↔  StringLiteral    : always valid
       - INTEGER column  ↔  StringLiteral    : TYPE_MISMATCH error
       - STRING  column  ↔  IntegerLiteral   : TYPE_MISMATCH error
  6. Operator/type compatibility:
       - INTEGER columns support all six operators (=, !=, >, <, >=, <=).
       - STRING  columns support equality/inequality (=, !=) only.
         Ordering operators (>, <, >=, <=) on strings are OPERATOR_MISMATCH.
  7. SELECT wildcard          — SELECT * resolves to all table columns, no error.
  8. Column case sensitivity  — column names are matched exactly as in the schema.

Error collection strategy
--------------------------
The analyser collects ALL errors rather than stopping at the first one.
Exception: if the table is unknown the column-level checks are skipped
(they would all produce spurious "column not found" errors).

Design
------
- Does not modify the AST.
- Does not execute the query.
- Does not access the CSV file.
- Uses only the schema registry passed at construction time.
"""

from __future__ import annotations

from backend.parser.ast import (
    ColumnRef,
    ComparisonExpr,
    ConditionNode,
    IntegerLiteral,
    LogicalExpr,
    Query,
    StringLiteral,
    Wildcard,
)
from backend.schema import ColumnType, TableSchema

from .errors import ErrorCode, SemanticError
from .result import SemanticAnalysisResult

# Schema registry type alias — maps lower-cased table name -> TableSchema.
SchemaRegistry = dict[str, TableSchema]

# Operators that are valid for STRING columns.
_STRING_OPS: frozenset[str] = frozenset({"=", "!="})

# All six comparison operators (valid for INTEGER columns).
_ALL_OPS: frozenset[str] = frozenset({"=", "!=", ">", "<", ">=", "<="})


class SemanticAnalyzer:
    """
    Validates a parsed Query AST against the given schema registry.

    Parameters
    ----------
    schema_registry:
        A dict mapping lower-cased table names to TableSchema objects.
        The canonical registry is ``backend.schema.SCHEMA_REGISTRY``.

    Usage
    -----
        from backend.schema          import SCHEMA_REGISTRY
        from backend.semantic        import SemanticAnalyzer

        result = SemanticAnalyzer(SCHEMA_REGISTRY).analyze(ast)
        if not result.valid:
            for err in result.errors:
                print(err)
    """

    def __init__(self, schema_registry: SchemaRegistry) -> None:
        self._registry = schema_registry

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(self, ast: Query) -> SemanticAnalysisResult:
        """
        Perform full semantic analysis on *ast*.

        Returns a SemanticAnalysisResult that is always fully populated:
        - result.valid is True iff result.errors is empty.
        - result.table_schema holds the resolved schema (or None on failure).
        - result.resolved_columns lists the columns the SELECT expands to.

        The AST is not modified.
        """
        errors: list[SemanticError] = []

        # --- Rule 1: dataset existence -----------------------------------
        schema = self._resolve_table(ast.from_clause, errors)
        if schema is None:
            # All further column checks would be spurious — stop here.
            return SemanticAnalysisResult(
                valid=False, errors=errors,
                table_schema=None, resolved_columns=[],
            )

        # --- Rule 2: SELECT column existence + wildcard ------------------
        resolved_columns = self._check_select(ast.select, schema, errors)

        # --- Rule 3: WHERE column existence, types, and operators --------
        if ast.where is not None:
            self._check_condition(ast.where.condition, schema, errors)

        # --- Rule 4: ORDER BY column existence ---------------------------
        if ast.order_by is not None:
            self._check_column_ref(
                ast.order_by.column,
                schema,
                errors,
                context="ORDER BY",
            )

        return SemanticAnalysisResult(
            valid=(len(errors) == 0),
            errors=errors,
            table_schema=schema,
            resolved_columns=resolved_columns,
        )

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    def _resolve_table(
        self,
        from_clause,
        errors: list[SemanticError],
    ) -> TableSchema | None:
        """Rule 1 — table must exist in the registry."""
        schema = self._registry.get(from_clause.table_name.lower())
        if schema is None:
            errors.append(SemanticError(
                code=ErrorCode.UNKNOWN_TABLE,
                message=(
                    f"Unknown table '{from_clause.table_name}'. "
                    f"Known tables: {sorted(self._registry.keys())}."
                ),
                token=from_clause.token,
            ))
        return schema

    def _check_select(
        self,
        select,
        schema: TableSchema,
        errors: list[SemanticError],
    ) -> list[str]:
        """
        Rule 2 — validate SELECT column list.

        Returns the list of column names the SELECT resolves to.
        For SELECT * this is all table columns; for named columns it is
        the names as written in the query (preserving order).
        """
        # SELECT * — always valid; resolves to all schema columns.
        if select.is_wildcard:
            return schema.column_names[:]

        # Named column list.
        resolved: list[str] = []
        for col_ref in select.columns:   # type: ignore[union-attr]
            meta = schema.get_column(col_ref.name)
            if meta is None:
                errors.append(SemanticError(
                    code=ErrorCode.UNKNOWN_COLUMN,
                    message=(
                        f"Column '{col_ref.name}' does not exist in "
                        f"table '{schema.table_name}'. "
                        f"Available columns: {schema.column_names}."
                    ),
                    token=col_ref.token,
                ))
            else:
                resolved.append(meta.name)
        return resolved

    def _check_condition(
        self,
        node: ConditionNode,
        schema: TableSchema,
        errors: list[SemanticError],
    ) -> None:
        """
        Rules 3, 5, 6 — recursively validate a condition tree.

        Walks LogicalExpr nodes depth-first; validates each ComparisonExpr
        for column existence, type compatibility, and operator compatibility.
        """
        if isinstance(node, LogicalExpr):
            self._check_condition(node.left,  schema, errors)
            self._check_condition(node.right, schema, errors)
        elif isinstance(node, ComparisonExpr):
            self._check_comparison(node, schema, errors)

    def _check_comparison(
        self,
        node: ComparisonExpr,
        schema: TableSchema,
        errors: list[SemanticError],
    ) -> None:
        """
        Validate one comparison expression:
          - column must exist (rule 3)
          - literal type must match column type (rule 5)
          - operator must be valid for the column type (rule 6)
        """
        col_meta = schema.get_column(node.column.name)

        # --- Column existence (rule 3) ---
        if col_meta is None:
            errors.append(SemanticError(
                code=ErrorCode.UNKNOWN_COLUMN,
                message=(
                    f"Column '{node.column.name}' does not exist in "
                    f"table '{schema.table_name}'. "
                    f"Available columns: {schema.column_names}."
                ),
                token=node.column.token,
            ))
            # Cannot do type/operator checks without a known column.
            return

        # --- Type compatibility (rule 5) ---
        col_type    = col_meta.col_type
        literal     = node.right
        type_error  = self._check_type_compat(col_meta, literal, node)
        if type_error:
            errors.append(type_error)
            # Operator check still meaningful — fall through.

        # --- Operator compatibility (rule 6) ---
        op_error = self._check_operator_compat(col_meta, node)
        if op_error:
            errors.append(op_error)

    def _check_type_compat(
        self,
        col_meta,
        literal,
        node: ComparisonExpr,
    ) -> SemanticError | None:
        """
        Rule 5 — literal type must match column type.

        INTEGER column  ↔ IntegerLiteral : OK
        STRING  column  ↔ StringLiteral  : OK
        INTEGER column  ↔ StringLiteral  : TYPE_MISMATCH
        STRING  column  ↔ IntegerLiteral : TYPE_MISMATCH
        """
        col_type = col_meta.col_type

        if col_type == ColumnType.INTEGER and isinstance(literal, StringLiteral):
            return SemanticError(
                code=ErrorCode.TYPE_MISMATCH,
                message=(
                    f"Column '{col_meta.name}' is of type INTEGER but was "
                    f"compared with a STRING literal '{literal.value}'. "
                    f"Use a numeric value instead."
                ),
                token=literal.token,
            )

        if col_type == ColumnType.STRING and isinstance(literal, IntegerLiteral):
            return SemanticError(
                code=ErrorCode.TYPE_MISMATCH,
                message=(
                    f"Column '{col_meta.name}' is of type STRING but was "
                    f"compared with an INTEGER literal {literal.value}. "
                    f"Use a quoted string value instead."
                ),
                token=literal.token,
            )

        return None

    def _check_operator_compat(
        self,
        col_meta,
        node: ComparisonExpr,
    ) -> SemanticError | None:
        """
        Rule 6 — operator must be valid for the column type.

        INTEGER: all six operators (=, !=, >, <, >=, <=) are valid.
        STRING:  only equality operators (=, !=) are valid.
        """
        if col_meta.col_type == ColumnType.STRING:
            if node.operator not in _STRING_OPS:
                return SemanticError(
                    code=ErrorCode.OPERATOR_MISMATCH,
                    message=(
                        f"Operator '{node.operator}' is not supported for "
                        f"STRING column '{col_meta.name}'. "
                        f"STRING columns only support: {sorted(_STRING_OPS)}."
                    ),
                    token=node.token,
                )
        return None

    def _check_column_ref(
        self,
        col_ref: ColumnRef,
        schema: TableSchema,
        errors: list[SemanticError],
        context: str = "",
    ) -> None:
        """Check that *col_ref* names an existing column (rules 3/4)."""
        if not schema.has_column(col_ref.name):
            ctx = f" in {context}" if context else ""
            errors.append(SemanticError(
                code=ErrorCode.UNKNOWN_COLUMN,
                message=(
                    f"Column '{col_ref.name}'{ctx} does not exist in "
                    f"table '{schema.table_name}'. "
                    f"Available columns: {schema.column_names}."
                ),
                token=col_ref.token,
            ))
