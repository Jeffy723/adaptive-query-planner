"""
backend/ir/nodes.py

Logical Intermediate Representation (IR) node definitions.

The IR is a language-agnostic, syntax-independent description of WHAT a
query must do.  It does NOT describe HOW to execute it — that is the job
of the future execution planner and executor.

Design principles
-----------------
- All nodes are frozen dataclasses: immutable, printable, inspectable.
- No execution logic lives here.
- No CSV / filesystem access.
- No AST imports — the IR is deliberately decoupled from the parser.
- The structure is a simple ordered list of operations (LogicalPlan)
  rather than a tree, which is easier for the planner to traverse and
  transform one step at a time.

Hierarchy
---------
    # Predicate sub-nodes (used inside FilterOp)
    IRLiteral           — a typed value (integer or string)
    IRColumnRef         — a column name reference
    IRComparison        — column op literal  (e.g. marks > 80)
    IRLogicalExpr       — left AND|OR right  (mirrors AST LogicalExpr)
    IRPredicate         — union alias for condition types

    # Relational operation nodes
    ScanOp              — SCAN <table>
    FilterOp            — FILTER <predicate>
    ProjectOp           — PROJECT <columns>  (or *)
    SortOp              — SORT <column> ASC|DESC

    # Root container
    LogicalPlan         — ordered list of the above operations
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Union


# ---------------------------------------------------------------------------
# Literal value type
# ---------------------------------------------------------------------------

class IRLiteralType(Enum):
    """Type tag for an IR literal value."""
    INTEGER = auto()
    STRING  = auto()


@dataclass(frozen=True)
class IRLiteral:
    """
    A typed literal value used inside a filter predicate.

    Attributes
    ----------
    value:
        The raw Python value: int for INTEGER, str for STRING.
    literal_type:
        IRLiteralType tag — lets the executor branch without isinstance().
    """
    value:        Union[int, str]
    literal_type: IRLiteralType

    def __str__(self) -> str:
        if self.literal_type == IRLiteralType.STRING:
            return f"'{self.value}'"
        return str(self.value)


# ---------------------------------------------------------------------------
# Column reference
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IRColumnRef:
    """
    A reference to a named column, as it appears in predicates or projections.

    Attributes
    ----------
    name:
        Column name exactly as validated by the semantic analyser.
    """
    name: str

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Predicate nodes (used inside FilterOp)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IRComparison:
    """
    A single comparison predicate: column op literal.

    Examples:  marks > 80,  department = 'CSE',  semester != 3

    Attributes
    ----------
    column:
        The column being tested.
    operator:
        One of: =  !=  >  <  >=  <=
    value:
        The literal to compare against.
    """
    column:   IRColumnRef
    operator: str
    value:    IRLiteral

    def __str__(self) -> str:
        return f"{self.column} {self.operator} {self.value}"


@dataclass(frozen=True)
class IRLogicalExpr:
    """
    A binary logical combination of predicates: left AND|OR right.

    Per the language spec, predicates are stored in left-to-right order
    exactly as they appeared in the query (no reordering is done here).
    The planner may later split or reorder them.

    Attributes
    ----------
    left:
        The left predicate (IRComparison or another IRLogicalExpr).
    operator:
        "AND" or "OR".
    right:
        The right predicate.
    """
    left:     "IRPredicate"
    operator: str
    right:    "IRPredicate"

    def __str__(self) -> str:
        return f"({self.left} {self.operator} {self.right})"


#: Union of all predicate node types.
IRPredicate = Union[IRComparison, IRLogicalExpr]


# ---------------------------------------------------------------------------
# Relational operation nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScanOp:
    """
    SCAN <table_name>

    Represents reading all rows from a named dataset (CSV file).
    The executor resolves the actual file path from the table name.

    Attributes
    ----------
    table_name:
        Name of the table as validated by the semantic analyser.
    """
    table_name: str

    def __str__(self) -> str:
        return f"SCAN {self.table_name}"

    def explain(self) -> str:
        return str(self)


@dataclass(frozen=True)
class FilterOp:
    """
    FILTER <predicate>

    Represents applying a boolean predicate to each row and keeping only
    those rows for which the predicate evaluates to True.

    Attributes
    ----------
    predicate:
        The condition to evaluate (IRComparison or IRLogicalExpr).
        Preserves the exact logical structure from the WHERE clause.
    """
    predicate: IRPredicate

    def __str__(self) -> str:
        return f"FILTER {self.predicate}"

    def explain(self) -> str:
        return str(self)


@dataclass(frozen=True)
class ProjectOp:
    """
    PROJECT <columns>

    Represents selecting a subset of columns from each row.

    Attributes
    ----------
    columns:
        Ordered tuple of column names to keep.
        This is always fully resolved — SELECT * has been expanded to
        the concrete list of columns by the semantic analyser.
    """
    columns: tuple[str, ...]

    def __str__(self) -> str:
        return f"PROJECT {', '.join(self.columns)}"

    def explain(self) -> str:
        return str(self)


@dataclass(frozen=True)
class SortOp:
    """
    SORT <column> <direction>

    Represents ordering the result set by one column.

    Attributes
    ----------
    column:
        Name of the column to sort by.
    direction:
        "ASC" or "DESC".
    """
    column:    str
    direction: str   # "ASC" | "DESC"

    def __str__(self) -> str:
        return f"SORT {self.column} {self.direction}"

    def explain(self) -> str:
        return str(self)


#: Union of all relational operation node types.
Operation = Union[ScanOp, FilterOp, ProjectOp, SortOp]


# ---------------------------------------------------------------------------
# Root container: LogicalPlan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LogicalPlan:
    """
    An ordered sequence of relational operations that together describe
    a complete query.

    The canonical initial ordering produced by build_ir() is:

        ScanOp → [FilterOp] → ProjectOp → [SortOp]

    This ordering is NOT optimised.  The future planner will read the
    LogicalPlan and may produce alternative orderings or physical plans.

    Attributes
    ----------
    operations:
        Tuple of relational operations in pipeline order.
    source_table:
        The name of the table being queried (convenience attribute,
        mirrors the ScanOp).
    """
    operations:   tuple[Operation, ...]
    source_table: str

    def explain(self) -> str:
        """
        Return a human-readable multi-line string describing the plan.

        Example output:

            SCAN students
            FILTER (department = 'CSE' AND marks > 80)
            PROJECT name, marks
            SORT marks DESC
        """
        return "\n".join(op.explain() for op in self.operations)

    def __str__(self) -> str:
        return self.explain()

    # Convenience accessors ---------------------------------------------------

    @property
    def scan(self) -> ScanOp:
        """Return the ScanOp (always the first operation)."""
        op = self.operations[0]
        assert isinstance(op, ScanOp)
        return op

    @property
    def filter(self) -> FilterOp | None:
        """Return the FilterOp if present, or None."""
        for op in self.operations:
            if isinstance(op, FilterOp):
                return op
        return None

    @property
    def project(self) -> ProjectOp:
        """Return the ProjectOp (always present)."""
        for op in self.operations:
            if isinstance(op, ProjectOp):
                return op
        raise AssertionError("LogicalPlan has no ProjectOp")  # pragma: no cover

    @property
    def sort(self) -> SortOp | None:
        """Return the SortOp if present, or None."""
        for op in self.operations:
            if isinstance(op, SortOp):
                return op
        return None
