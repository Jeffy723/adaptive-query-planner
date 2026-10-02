"""
backend/planner/physical_nodes.py

Physical execution plan node definitions.

The physical plan represents HOW a query is executed step-by-step as an
ordered sequence of physical operations.

Design principles
-----------------
- Distinct from the logical IR (LogicalPlan represents WHAT, PhysicalPlan represents HOW).
- Represents concrete physical stages:
    PhysicalScan    — read source dataset
    PhysicalFilter  — evaluate predicate on each row
    PhysicalProject — select/project specified columns
    PhysicalSort    — sort rows by key column and direction
- Immutable frozen dataclasses.
- Carries plan metadata (plan_id, filter_order, descriptions) for use by
  the cost estimator and planner in future stages.
- Provides a thin adapter `.to_logical()` to enable execution via the
  existing execution engine without modifying the executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from backend.ir.nodes import (
    FilterOp,
    IRPredicate,
    LogicalPlan,
    Operation,
    ProjectOp,
    ScanOp,
    SortOp,
)


# ---------------------------------------------------------------------------
# Physical operation nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhysicalScan:
    """
    Physical scan operation: loads rows from the named table.

    Attributes
    ----------
    table_name:
        Name of the source table to scan (e.g. 'students').
    """
    table_name: str

    def __str__(self) -> str:
        return f"SCAN {self.table_name}"

    def explain(self) -> str:
        return str(self)


@dataclass(frozen=True)
class PhysicalFilter:
    """
    Physical filter operation: applies a predicate to each input row.

    Attributes
    ----------
    predicate:
        The boolean IRPredicate to evaluate (IRComparison or IRLogicalExpr).
    """
    predicate: IRPredicate

    def __str__(self) -> str:
        return f"FILTER {self.predicate}"

    def explain(self) -> str:
        return str(self)


@dataclass(frozen=True)
class PhysicalProject:
    """
    Physical projection operation: retains only the specified columns.

    Attributes
    ----------
    columns:
        Tuple of column names in output order.
    """
    columns: tuple[str, ...]

    def __str__(self) -> str:
        return f"PROJECT {', '.join(self.columns)}"

    def explain(self) -> str:
        return str(self)


@dataclass(frozen=True)
class PhysicalSort:
    """
    Physical sort operation: sorts rows by column in ASC or DESC order.

    Attributes
    ----------
    column:
        Name of the sort key column.
    direction:
        "ASC" or "DESC".
    """
    column:    str
    direction: str

    def __str__(self) -> str:
        return f"SORT {self.column} {self.direction}"

    def explain(self) -> str:
        return str(self)


#: Union of all physical operation node types.
PhysicalOperation = Union[PhysicalScan, PhysicalFilter, PhysicalProject, PhysicalSort]


# ---------------------------------------------------------------------------
# Root container: PhysicalPlan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhysicalPlan:
    """
    A concrete physical execution plan.

    Attributes
    ----------
    plan_id:
        Unique, deterministic identifier (e.g. 'plan_A', 'plan_B').
    operations:
        Ordered tuple of physical operations to execute.
    source_table:
        Name of the dataset table being queried.
    filter_order:
        Tuple of IRPredicate objects in the exact order they are evaluated
        in this plan. Empty if no filters are present.
    description:
        Human-readable summary of this plan variant.
    metadata:
        Additional plan properties consumed by future cost estimation and UI.
    """
    plan_id:      str
    operations:   tuple[PhysicalOperation, ...]
    source_table: str
    filter_order: tuple[IRPredicate, ...]        = field(default_factory=tuple)
    description:  str                            = ""
    metadata:     dict[str, object]              = field(default_factory=dict)

    def explain(self) -> str:
        """Return a human-readable multi-line explanation of the plan."""
        lines = [f"{self.plan_id}: {self.description}" if self.description else f"{self.plan_id}:"]
        for op in self.operations:
            lines.append(f"  {op.explain()}")
        return "\n".join(lines)

    def format_pipeline(self) -> str:
        """Return a compact single-line arrow-separated pipeline description."""
        return " -> ".join(str(op) for op in self.operations)

    def __str__(self) -> str:
        return "\n".join(op.explain() for op in self.operations)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def scan_operation(self) -> PhysicalScan:
        """Return the PhysicalScan operation."""
        for op in self.operations:
            if isinstance(op, PhysicalScan):
                return op
        raise AssertionError("PhysicalPlan has no PhysicalScan")  # pragma: no cover

    @property
    def filter_operations(self) -> tuple[PhysicalFilter, ...]:
        """Return all PhysicalFilter operations in execution order."""
        return tuple(op for op in self.operations if isinstance(op, PhysicalFilter))

    @property
    def project_operation(self) -> PhysicalProject:
        """Return the PhysicalProject operation."""
        for op in self.operations:
            if isinstance(op, PhysicalProject):
                return op
        raise AssertionError("PhysicalPlan has no PhysicalProject")  # pragma: no cover

    @property
    def sort_operation(self) -> PhysicalSort | None:
        """Return the PhysicalSort operation if present, else None."""
        for op in self.operations:
            if isinstance(op, PhysicalSort):
                return op
        return None

    # ------------------------------------------------------------------
    # Thin adapter to LogicalPlan
    # ------------------------------------------------------------------

    def to_logical(self) -> LogicalPlan:
        """
        Convert this physical plan into an equivalent LogicalPlan.

        Enables seamless execution by the existing Executor engine for testing
        and plan equivalence verification without modifying the executor.
        """
        logical_ops: list[Operation] = []
        for op in self.operations:
            if isinstance(op, PhysicalScan):
                logical_ops.append(ScanOp(table_name=op.table_name))
            elif isinstance(op, PhysicalFilter):
                logical_ops.append(FilterOp(predicate=op.predicate))
            elif isinstance(op, PhysicalProject):
                logical_ops.append(ProjectOp(columns=op.columns))
            elif isinstance(op, PhysicalSort):
                logical_ops.append(SortOp(column=op.column, direction=op.direction))
        return LogicalPlan(
            operations=tuple(logical_ops),
            source_table=self.source_table,
        )
