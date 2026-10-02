"""
backend/pipeline.py

End-to-End Adaptive Query Execution Pipeline.

Connects all query compilation and execution stages into a unified workflow:
  1. Lexical Analysis (Lexer)
  2. Syntactic Parsing (Parser)
  3. Semantic Validation (SemanticAnalyzer)
  4. Logical Query IR (build_ir)
  5. Physical Plan Generation (generate_plans)
  6. Cost Estimation (CostEstimator)
  7. Plan Selection (PlanSelector)
  8. Physical Plan Execution (Executor)
  9. Baseline Correctness Verification (Selected Plan vs Logical Baseline)

Public API
----------
    from backend.pipeline import execute_query, QueryPipeline, QueryResult, PipelineError, ResultMismatchError

    result = execute_query("SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;")
    print(result.explain())
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Sequence

from backend.cost import CostEstimator, PlanCostEstimate
from backend.executor import DatasetProvider, ExecutionError, ExecutionResult, Executor, OperationStats
from backend.feedback import (
    AdaptiveStatisticsStore,
    ExecutionFeedback,
    collect_feedback,
)
from backend.ir import LogicalPlan, build_ir
from backend.lexer import Lexer, LexerError
from backend.parser import ParseError, Parser
from backend.planner import (
    PhysicalPlan,
    PlanSelectionResult,
    PlanSelector,
    generate_plans,
)
from backend.schema import SCHEMA_REGISTRY, TableSchema


class PipelineError(Exception):
    """Base exception for end-to-end pipeline execution failures."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ResultMismatchError(PipelineError):
    """
    Raised when the result of the selected physical plan differs from the
    original logical baseline execution.
    """
    pass


@dataclass(frozen=True)
class QueryResult:
    """
    Comprehensive end-to-end result of compiling, planning, and executing a query.

    Contains all artifacts from every stage for consumption by future UI or CLI tools.
    """
    query:             str
    logical_plan:      LogicalPlan
    candidate_plans:   tuple[PhysicalPlan, ...]
    cost_estimates:    tuple[PlanCostEstimate, ...]
    plan_costs:        dict[str, float]
    selection_result:  PlanSelectionResult
    selected_plan:     PhysicalPlan
    selected_plan_id:  str
    selected_cost:     float
    execution_result:  ExecutionResult
    baseline_result:   ExecutionResult
    baseline_matched:  bool
    columns:           list[str]
    rows:              list[dict[str, object]]
    row_count:         int
    execution_stats:   list[OperationStats]
    metadata:          dict[str, object] = field(default_factory=dict)
    feedback:          ExecutionFeedback | None = None

    def explain(self) -> str:
        """
        Return a comprehensive, structured demonstration report of the query
        lifecycle from logical formulation to physical execution and verification.
        """
        lines = [
            "=" * 70,
            "QUERY:",
            f"  {self.query.strip()}",
            "",
            "LOGICAL PLAN:",
            "\n".join(f"  {line}" for line in self.logical_plan.explain().splitlines()),
            "",
            f"ALTERNATIVE PLANS & ESTIMATED COSTS ({len(self.candidate_plans)} generated):",
        ]

        for plan in self.candidate_plans:
            cost = self.plan_costs.get(plan.plan_id, 0.0)
            marker = "  <-- SELECTED" if plan.plan_id == self.selected_plan_id else ""
            lines.append(f"  {plan.plan_id:<8} (Cost: {cost:8.2f}){marker}")
            lines.append(f"    Pipeline: {plan.format_pipeline()}")

        lines.extend([
            "",
            "SELECTED PLAN:",
            f"  {self.selected_plan_id} (Estimated Cost: {self.selected_cost:.2f})",
            f"  Reason: {self.selection_result.reason}",
            "",
            "EXECUTION RESULT:",
            f"  Rows returned: {self.row_count}",
            f"  Columns: {self.columns}",
            "  Execution Statistics:",
        ])

        for stat in self.execution_stats:
            lines.append(f"    {stat.operation}: input={stat.input_rows} -> output={stat.output_rows}")

        verif_status = "YES (Identical columns, row count, and ordered tuples)" if self.baseline_matched else "NO"
        lines.extend([
            "",
            "CORRECTNESS VERIFICATION:",
            f"  Selected plan result == logical baseline result: {verif_status}",
        ])

        if self.feedback is not None:
            lines.extend([
                "",
                self.feedback.explain(),
            ])

        lines.append("=" * 70)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.explain()


class QueryPipeline:
    """
    Orchestrates the entire query planning and execution lifecycle.

    Parameters
    ----------
    schema_registry:
        Maps table names to TableSchema. Defaults to SCHEMA_REGISTRY.
    data_dir:
        Directory path containing CSV files.
    dataset_provider:
        Optional custom DatasetProvider instance.
    """

    def __init__(
        self,
        schema_registry: dict[str, TableSchema] | None = None,
        data_dir: pathlib.Path | str | None = None,
        *,
        dataset_provider: DatasetProvider | None = None,
        adaptive_store: AdaptiveStatisticsStore | None = None,
        enable_learning: bool = False,
        alpha: float = 0.5,
    ) -> None:
        self._registry = schema_registry or SCHEMA_REGISTRY
        if dataset_provider is not None:
            self._provider = dataset_provider
        else:
            self._provider = DatasetProvider(data_dir=data_dir)

        self._enable_learning = enable_learning
        self._alpha = alpha
        if adaptive_store is not None:
            self._adaptive_store: AdaptiveStatisticsStore | None = adaptive_store
        elif enable_learning:
            self._adaptive_store = AdaptiveStatisticsStore()
        else:
            self._adaptive_store = None

        self._executor = Executor(self._registry, dataset_provider=self._provider)
        self._cost_estimator = CostEstimator(
            schema_registry=self._registry,
            dataset_provider=self._provider,
            adaptive_store=self._adaptive_store if self._enable_learning else None,
        )
        self._plan_selector = PlanSelector()

    @property
    def adaptive_store(self) -> AdaptiveStatisticsStore | None:
        """The active adaptive statistics store, if configured."""
        return self._adaptive_store

    @property
    def learning_enabled(self) -> bool:
        """Whether runtime feedback updates future cost estimation."""
        return self._enable_learning

    def execute(self, query: str, verify_baseline: bool = True) -> QueryResult:
        """
        Execute *query* through the complete pipeline.

        1. Tokenizes with Lexer.
        2. Parses into Query AST.
        3. Validates against schema with SemanticAnalyzer.
        4. Builds LogicalPlan IR.
        5. Generates alternative physical execution plans.
        6. Estimates costs using actual dataset statistics.
        7. Selects minimum cost plan with PlanSelector.
        8. Executes selected plan using Executor.
        9. Executes logical baseline and verifies equivalence.
        10. Collects runtime feedback and optionally updates learned statistics.

        Parameters
        ----------
        query:
            SQL-like query string.
        verify_baseline:
            If True, runs the logical baseline and asserts that the physical
            plan output exactly matches the logical baseline.

        Returns
        -------
        QueryResult
            Comprehensive structured report of the execution.

        Raises
        ------
        LexerError
            On invalid characters / tokens.
        ParseError
            On syntactic grammar errors.
        PipelineError
            On semantic or planning failures.
        ResultMismatchError
            If selected physical plan result differs from the logical baseline.
        ExecutionError
            On runtime execution failure.
        """
        # 1. Lexer
        tokens = Lexer(query).tokenize()

        # 2. Parser
        ast = Parser(tokens).parse()

        # 3. Semantic Analysis
        from backend.semantic import SemanticAnalyzer
        semantic_result = SemanticAnalyzer(self._registry).analyze(ast)
        if not semantic_result.valid:
            err_msgs = "; ".join(e.message for e in semantic_result.errors)
            raise PipelineError(f"Semantic validation failed: {err_msgs}")

        # 4. Logical IR
        logical_plan = build_ir(ast, semantic_result)

        # 5. Physical Plan Generation
        candidate_plans = tuple(generate_plans(logical_plan))
        if not candidate_plans:
            raise PipelineError("Plan generation produced no candidate physical plans.")

        # 6. Cost Estimation
        cost_estimates = tuple(self._cost_estimator.estimate_all(candidate_plans))
        plan_costs = {est.plan_id: est.total_cost for est in cost_estimates}

        # 7. Plan Selection
        selection_result = self._plan_selector.select(candidate_plans, cost_estimates)
        selected_plan = selection_result.selected_plan

        # 8. Physical Execution (using thin adapter .to_logical() via existing Executor)
        execution_result = self._executor.execute(selected_plan)

        # 9. Baseline Correctness Verification
        baseline_result = self._executor.execute(logical_plan)
        baseline_matched = False

        if verify_baseline:
            columns_match = execution_result.columns == baseline_result.columns
            counts_match = execution_result.row_count == baseline_result.row_count
            rows_match = execution_result.rows == baseline_result.rows

            if not (columns_match and counts_match and rows_match):
                diff_details = []
                if not columns_match:
                    diff_details.append(f"Columns mismatch: {execution_result.columns} != {baseline_result.columns}")
                if not counts_match:
                    diff_details.append(f"Row count mismatch: {execution_result.row_count} != {baseline_result.row_count}")
                if not rows_match:
                    diff_details.append("Row data or ordering mismatch.")

                raise ResultMismatchError(
                    f"Correctness verification failed for plan '{selected_plan.plan_id}': "
                    f"{'; '.join(diff_details)}"
                )
            baseline_matched = True

        # 10. Runtime Feedback & Adaptation
        selected_estimate = next(
            (est for est in cost_estimates if est.plan_id == selection_result.selected_plan_id),
            None,
        )
        feedback = collect_feedback(
            cost_estimate=selected_estimate,
            execution_result=execution_result,
            query=query,
            alpha=self._alpha,
        )

        if self._enable_learning and self._adaptive_store is not None:
            self._adaptive_store.update_from_feedback(
                feedback,
                table_name=logical_plan.source_table,
            )

        return QueryResult(
            query=query,
            logical_plan=logical_plan,
            candidate_plans=candidate_plans,
            cost_estimates=cost_estimates,
            plan_costs=plan_costs,
            selection_result=selection_result,
            selected_plan=selected_plan,
            selected_plan_id=selection_result.selected_plan_id,
            selected_cost=selection_result.selected_cost,
            execution_result=execution_result,
            baseline_result=baseline_result,
            baseline_matched=baseline_matched,
            columns=execution_result.columns,
            rows=execution_result.rows,
            row_count=execution_result.row_count,
            execution_stats=execution_result.stats,
            metadata={
                "source_table": logical_plan.source_table,
                "candidate_plan_count": len(candidate_plans),
                "verified_against_baseline": verify_baseline,
                "learning_enabled": self._enable_learning,
            },
            feedback=feedback,
        )


# ---------------------------------------------------------------------------
# Public functional helper
# ---------------------------------------------------------------------------

def execute_query(
    query: str,
    schema_registry: dict[str, TableSchema] | None = None,
    data_dir: pathlib.Path | str | None = None,
    *,
    dataset_provider: DatasetProvider | None = None,
    verify_baseline: bool = True,
    adaptive_store: AdaptiveStatisticsStore | None = None,
    enable_learning: bool = False,
    alpha: float = 0.5,
) -> QueryResult:
    """
    Convenience function to execute a query string through the full adaptive pipeline.

    Usage
    -----
        from backend.pipeline import execute_query

        result = execute_query("SELECT name, marks FROM students WHERE marks > 80;")
        print(result.explain())
    """
    pipeline = QueryPipeline(
        schema_registry=schema_registry,
        data_dir=data_dir,
        dataset_provider=dataset_provider,
        adaptive_store=adaptive_store,
        enable_learning=enable_learning,
        alpha=alpha,
    )
    return pipeline.execute(query, verify_baseline=verify_baseline)
