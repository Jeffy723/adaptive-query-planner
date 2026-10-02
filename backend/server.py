"""
backend/server.py

REST API Server for the Adaptive Query Execution Planner Interactive UI.

Exposes endpoints to execute queries through the complete compiler pipeline,
inspect individual stage outputs, manage adaptive statistics learning, and
retrieve supported example queries.

Endpoints
---------
  GET  /api/health
  GET  /api/examples
  POST /api/query/execute
  POST /api/adaptive/reset
"""

from __future__ import annotations

import traceback
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.cost import CostEstimator
from backend.executor import Executor
from backend.feedback import (
    AdaptiveStatisticsStore,
    collect_feedback,
)
from backend.ir import build_ir
from backend.lexer import Lexer, LexerError
from backend.parser import (
    ColumnRef,
    ComparisonExpr,
    LogicalExpr,
    ParseError,
    Parser,
    Query,
    Wildcard,
)
from backend.planner import PlanSelector, generate_plans
from backend.schema import SCHEMA_REGISTRY

# In-memory global store for adaptive learning across UI sessions
_GLOBAL_ADAPTIVE_STORE = AdaptiveStatisticsStore()


# ---------------------------------------------------------------------------
# AST Formatter and Serializer Helpers
# ---------------------------------------------------------------------------

def ast_to_tree_lines(query_ast: Query) -> list[str]:
    """Format Query AST into a human-readable indented tree diagram."""
    lines = ["QUERY"]

    clauses = [("SELECT", query_ast.select), ("FROM", query_ast.from_clause)]
    if query_ast.where is not None:
        clauses.append(("WHERE", query_ast.where))
    if query_ast.order_by is not None:
        clauses.append(("ORDER BY", query_ast.order_by))

    def _render_condition(cond: Any, prefix: str, is_tail: bool) -> list[str]:
        branch = "└── " if is_tail else "├── "
        child_pfx = prefix + ("    " if is_tail else "│   ")
        res = []

        if isinstance(cond, ComparisonExpr):
            res.append(f"{prefix}{branch}{cond.column.name} {cond.operator} {cond.right}")
        elif isinstance(cond, LogicalExpr):
            res.append(f"{prefix}{branch}{cond.operator}")
            res.extend(_render_condition(cond.left, child_pfx, False))
            res.extend(_render_condition(cond.right, child_pfx, True))
        else:
            res.append(f"{prefix}{branch}{cond}")
        return res

    for idx, (clause_name, clause_node) in enumerate(clauses):
        is_last_clause = idx == len(clauses) - 1
        branch = "└── " if is_last_clause else "├── "
        child_pfx = "    " if is_last_clause else "│   "

        lines.append(f"{branch}{clause_name}")

        if clause_name == "SELECT":
            if clause_node.is_wildcard:
                lines.append(f"{child_pfx}└── *")
            else:
                cols = list(clause_node.columns)
                for j, item in enumerate(cols):
                    is_last_item = j == len(cols) - 1
                    b = "└── " if is_last_item else "├── "
                    lines.append(f"{child_pfx}{b}{item.name}")

        elif clause_name == "FROM":
            lines.append(f"{child_pfx}└── {clause_node.table_name}")

        elif clause_name == "WHERE":
            lines.extend(_render_condition(clause_node.condition, child_pfx, True))

        elif clause_name == "ORDER BY":
            lines.append(f"{child_pfx}└── {clause_node.column.name} {clause_node.direction}")

    return lines


def ast_to_dict(node: Any) -> dict[str, Any]:
    """Serialize AST into structured JSON representation."""
    if isinstance(node, Query):
        return {
            "type": "Query",
            "select": ast_to_dict(node.select),
            "from": ast_to_dict(node.from_clause),
            "where": ast_to_dict(node.where) if node.where else None,
            "order_by": ast_to_dict(node.order_by) if node.order_by else None,
        }
    elif hasattr(node, "is_wildcard"):  # SelectClause
        return {
            "type": "SelectClause",
            "columns": ["*"] if node.is_wildcard else [c.name for c in node.columns],
        }
    elif hasattr(node, "table_name"):  # FromClause
        return {
            "type": "FromClause",
            "table": node.table_name,
        }
    elif hasattr(node, "condition"):  # WhereClause
        return {
            "type": "WhereClause",
            "condition": ast_to_dict(node.condition),
        }
    elif isinstance(node, ComparisonExpr):
        val = node.right.value if hasattr(node.right, "value") else str(node.right)
        return {
            "type": "ComparisonExpr",
            "column": node.column.name,
            "operator": node.operator,
            "value": val,
        }
    elif isinstance(node, LogicalExpr):
        return {
            "type": "LogicalExpr",
            "operator": node.operator,
            "left": ast_to_dict(node.left),
            "right": ast_to_dict(node.right),
        }
    elif hasattr(node, "column") and hasattr(node, "direction"):  # OrderByClause
        return {
            "type": "OrderByClause",
            "column": node.column.name,
            "direction": node.direction,
        }
    return {"type": type(node).__name__, "repr": str(node)}


# ---------------------------------------------------------------------------
# Stage-by-Stage Pipeline Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline_with_stages(
    query_str: str,
    enable_learning: bool = False,
    alpha: float = 0.5,
    adaptive_store: AdaptiveStatisticsStore | None = None,
) -> dict[str, Any]:
    """
    Executes the query stage-by-stage and captures full structured metadata
    for every single compiler and planning stage.
    """
    store = adaptive_store if adaptive_store is not None else _GLOBAL_ADAPTIVE_STORE

    stages: dict[str, Any] = {
        "lexer": {"status": "NOT_RUN"},
        "parser": {"status": "NOT_RUN"},
        "semantic": {"status": "NOT_RUN"},
        "logical_ir": {"status": "NOT_RUN"},
        "planner": {"status": "NOT_RUN"},
        "cost": {"status": "NOT_RUN"},
        "selector": {"status": "NOT_RUN"},
        "execution": {"status": "NOT_RUN"},
        "feedback": {"status": "NOT_RUN"},
        "result": {"status": "NOT_RUN"},
    }

    # 1. Lexical Analysis
    try:
        lexer = Lexer(query_str)
        tokens = lexer.tokenize()
        token_list = [
            {
                "index": i + 1,
                "type": tok.type.name,
                "value": tok.value,
                "line": tok.line,
                "col": tok.col,
            }
            for i, tok in enumerate(tokens)
        ]
        stages["lexer"] = {
            "status": "PASSED",
            "token_count": len(tokens),
            "tokens": token_list,
        }
    except LexerError as exc:
        stages["lexer"] = {
            "status": "ERROR",
            "error": {"message": exc.message, "line": exc.line, "col": exc.col},
            "token_count": 0,
            "tokens": [],
        }
        return {
            "success": false_val(),
            "query": query_str,
            "error": {"stage": "lexer", "message": exc.message, "line": exc.line, "col": exc.col},
            "active_stage": "lexer",
            "stages": stages,
        }

    # 2. Syntax Analysis / Parser
    try:
        parser = Parser(tokens)
        ast = parser.parse()
        tree_lines = ast_to_tree_lines(ast)
        stages["parser"] = {
            "status": "PASSED",
            "ast_tree_text": "\n".join(tree_lines),
            "ast": ast_to_dict(ast),
        }
    except ParseError as exc:
        line = exc.token.line if exc.token else 1
        col = exc.token.col if exc.token else 1
        stages["parser"] = {
            "status": "ERROR",
            "error": {"message": exc.message, "line": line, "col": col},
        }
        return {
            "success": false_val(),
            "query": query_str,
            "error": {"stage": "parser", "message": exc.message, "line": line, "col": col},
            "active_stage": "parser",
            "stages": stages,
        }

    # 3. Semantic Analysis
    from backend.semantic import SemanticAnalyzer
    sem_analyzer = SemanticAnalyzer(SCHEMA_REGISTRY)
    sem_result = sem_analyzer.analyze(ast)

    if not sem_result.valid:
        first_err = sem_result.first_error()
        err_line = first_err.token.line if first_err and first_err.token else 1
        err_col = first_err.token.col if first_err and first_err.token else 1
        errors_serialized = [
            {
                "code": err.code.name,
                "message": err.message,
                "line": err.token.line if err.token else 1,
                "col": err.token.col if err.token else 1,
            }
            for err in sem_result.errors
        ]
        stages["semantic"] = {
            "status": "ERROR",
            "valid": False,
            "error_count": len(sem_result.errors),
            "errors": errors_serialized,
        }
        return {
            "success": false_val(),
            "query": query_str,
            "error": {
                "stage": "semantic",
                "message": "; ".join(e.message for e in sem_result.errors),
                "line": err_line,
                "col": err_col,
                "errors": errors_serialized,
            },
            "active_stage": "semantic",
            "stages": stages,
        }

    # Build list of specific checks performed
    table_name = ast.from_clause.table_name
    target_cols = ", ".join(sem_result.resolved_columns)
    checks = [
        {
            "name": "Dataset existence",
            "description": f"Table '{table_name}' verified in Schema Registry",
            "passed": True,
        },
        {
            "name": "SELECT column validation",
            "description": f"Columns [{target_cols}] exist and resolved for table '{table_name}'",
            "passed": True,
        },
    ]
    if ast.where is not None:
        checks.append({
            "name": "WHERE condition validation",
            "description": f"Predicate '{ast.where.condition}' verified for column types and operator compatibility",
            "passed": True,
        })
    if ast.order_by is not None:
        checks.append({
            "name": "ORDER BY validation",
            "description": f"Order by column '{ast.order_by.column.name}' verified and direction is '{ast.order_by.direction}'",
            "passed": True,
        })

    stages["semantic"] = {
        "status": "PASSED",
        "valid": True,
        "table": table_name,
        "resolved_columns": sem_result.resolved_columns,
        "checks": checks,
        "errors": [],
    }

    # 4. Logical Query IR
    logical_plan = build_ir(ast, sem_result)
    ir_ops = []
    for i, op in enumerate(logical_plan.operations):
        op_type = op.__class__.__name__.replace("Op", "").upper()
        ir_ops.append({
            "index": i + 1,
            "type": op_type,
            "description": str(op),
        })

    stages["logical_ir"] = {
        "status": "PASSED",
        "source_table": logical_plan.source_table,
        "operations": ir_ops,
        "explain_text": logical_plan.explain(),
    }

    # 5. Physical Plan Generation
    candidate_plans = list(generate_plans(logical_plan))
    plan_list = []
    for p in candidate_plans:
        filter_order = [
            str(op.predicate)
            for op in p.operations
            if hasattr(op, "predicate")
        ]
        plan_list.append({
            "plan_id": p.plan_id,
            "description": p.description,
            "pipeline": p.format_pipeline(),
            "operations": [
                {
                    "type": op.__class__.__name__.replace("Physical", "").upper(),
                    "description": str(op),
                }
                for op in p.operations
            ],
            "filter_order": filter_order,
            "is_selected": False,  # Updated after selection
        })

    stages["planner"] = {
        "status": "PASSED",
        "candidate_count": len(candidate_plans),
        "plans": plan_list,
    }

    # 6. Cost Estimation
    estimator = CostEstimator(
        schema_registry=SCHEMA_REGISTRY,
        adaptive_store=store if enable_learning else None,
    )
    cost_estimates = estimator.estimate_all(candidate_plans)
    plan_costs_map = {est.plan_id: est.total_cost for est in cost_estimates}

    estimates_serialized = []
    for est in cost_estimates:
        op_estimates = []
        for op_est in est.operation_estimates:
            op_estimates.append({
                "operation": op_est.operation,
                "operation_type": op_est.operation_type,
                "input_rows": op_est.input_rows,
                "output_rows": op_est.output_rows,
                "cost": op_est.cost,
                "selectivity": op_est.selectivity,
                "description": op_est.description,
            })
        estimates_serialized.append({
            "plan_id": est.plan_id,
            "total_cost": est.total_cost,
            "operations": op_estimates,
        })

    stages["cost"] = {
        "status": "PASSED",
        "plan_costs": plan_costs_map,
        "estimates": estimates_serialized,
    }

    # 7. Plan Selection
    selector = PlanSelector()
    selection_result = selector.select(candidate_plans, cost_estimates)
    selected_plan_id = selection_result.selected_plan_id
    selected_plan = selection_result.selected_plan

    # Mark selected plan in planner stage
    for p in stages["planner"]["plans"]:
        if p["plan_id"] == selected_plan_id:
            p["is_selected"] = True

    ranked_candidates = [
        {
            "rank": ranked.rank,
            "plan_id": ranked.plan.plan_id,
            "cost": ranked.cost,
            "is_selected": ranked.plan.plan_id == selected_plan_id,
        }
        for ranked in selection_result.ranked_candidates
    ]

    stages["selector"] = {
        "status": "PASSED",
        "selected_plan_id": selected_plan_id,
        "selected_cost": selection_result.selected_cost,
        "selection_rule": "Lowest estimated total processing cost according to current cost model",
        "reason": selection_result.reason,
        "ranked_candidates": ranked_candidates,
    }

    # 8. Execution
    executor = Executor(SCHEMA_REGISTRY)
    execution_result = executor.execute(selected_plan)
    baseline_result = executor.execute(logical_plan)
    baseline_matched = (
        execution_result.columns == baseline_result.columns and
        execution_result.row_count == baseline_result.row_count and
        execution_result.rows == baseline_result.rows
    )

    # Match execution stats with estimated operations
    sel_estimate = next((e for e in cost_estimates if e.plan_id == selected_plan_id), None)
    exec_stats_table = []
    if sel_estimate:
        for i in range(min(len(sel_estimate.operation_estimates), len(execution_result.stats))):
            e_op = sel_estimate.operation_estimates[i]
            a_op = execution_result.stats[i]
            exec_stats_table.append({
                "operation": a_op.operation,
                "operation_type": e_op.operation_type,
                "estimated_input": e_op.input_rows,
                "actual_input": a_op.input_rows,
                "estimated_output": e_op.output_rows,
                "actual_output": a_op.output_rows,
            })

    stages["execution"] = {
        "status": "PASSED",
        "selected_plan_id": selected_plan_id,
        "rows_returned": execution_result.row_count,
        "baseline_matched": baseline_matched,
        "statistics": exec_stats_table,
    }

    # 9. Runtime Adaptive Feedback
    feedback = collect_feedback(
        cost_estimate=sel_estimate,
        execution_result=execution_result,
        query=query_str,
        alpha=alpha,
    )

    if enable_learning:
        store.update_from_feedback(feedback, table_name=logical_plan.source_table)

    op_feedback_list = []
    for op_fb in feedback.operation_feedback:
        sf_dict = None
        if op_fb.selectivity_feedback is not None:
            sf = op_fb.selectivity_feedback
            sf_dict = {
                "predicate": sf.predicate,
                "previous_selectivity": sf.previous_selectivity,
                "observed_selectivity": sf.observed_selectivity,
                "updated_selectivity": sf.updated_selectivity,
                "alpha": sf.alpha,
            }
        op_feedback_list.append({
            "operation": op_fb.operation,
            "operation_type": op_fb.operation_type,
            "estimated_input": op_fb.estimated_input_rows,
            "actual_input": op_fb.actual_input_rows,
            "estimated_output": op_fb.estimated_output_rows,
            "actual_output": op_fb.actual_output_rows,
            "difference": op_fb.difference,
            "absolute_error": op_fb.absolute_error,
            "relative_error": op_fb.relative_error,
            "relative_error_percentage": op_fb.relative_error_percentage,
            "selectivity_feedback": sf_dict,
        })

    stages["feedback"] = {
        "status": "PASSED",
        "learning_enabled": enable_learning,
        "selected_plan_id": selected_plan_id,
        "total_absolute_error": feedback.total_absolute_error,
        "max_absolute_error": feedback.max_absolute_error,
        "average_relative_error": feedback.average_relative_error,
        "operations": op_feedback_list,
        "stored_profile_count": len(store),
        "explain_text": feedback.explain(),
    }

    # 10. Query Result
    stages["result"] = {
        "status": "PASSED",
        "columns": execution_result.columns,
        "rows": execution_result.rows,
        "row_count": execution_result.row_count,
    }

    return {
        "success": True,
        "query": query_str,
        "error": None,
        "active_stage": "completed",
        "stages": stages,
    }


def false_val() -> bool:
    return False


# ---------------------------------------------------------------------------
# Flask Application Factory
# ---------------------------------------------------------------------------

EXAMPLE_QUERIES = [
    {
        "id": "ref",
        "title": "Reference Query (Chained Filters & Sorting)",
        "query": (
            "SELECT name, marks\n"
            "FROM students\n"
            "WHERE department = 'CSE'\n"
            "AND marks > 80\n"
            "ORDER BY marks DESC;"
        ),
        "description": "Standard benchmark comparing Plan A vs Plan B with CSE filtering.",
    },
    {
        "id": "simple_scan",
        "title": "Simple Scan & Projection",
        "query": "SELECT name\nFROM students;",
        "description": "Minimal projection query demonstrating single physical plan generation.",
    },
    {
        "id": "single_filter",
        "title": "Single Filter Predicate",
        "query": "SELECT name, marks\nFROM students\nWHERE marks > 80;",
        "description": "Numeric comparison filter with selectivity calculation.",
    },
    {
        "id": "equality_filter",
        "title": "String Equality Filter",
        "query": "SELECT name, semester\nFROM students\nWHERE department = 'ECE';",
        "description": "String comparison with exact selectivity match.",
    },
    {
        "id": "or_condition",
        "title": "Logical OR Condition",
        "query": (
            "SELECT name, department, marks\n"
            "FROM students\n"
            "WHERE department = 'CSE' OR marks > 90;"
        ),
        "description": "Compound OR condition evaluated as a single filter block.",
    },
    {
        "id": "invalid_column",
        "title": "[Error Demo] Unknown Column",
        "query": "SELECT name, salary\nFROM students;",
        "description": "Demonstrates semantic validation error for non-existent columns.",
    },
    {
        "id": "syntax_error",
        "title": "[Error Demo] Syntax Error",
        "query": "SELECT FROM students;",
        "description": "Demonstrates syntax parser error with line and column reporting.",
    },
]


def create_app() -> Flask:
    """Create and configure the Flask API application."""
    app = Flask(__name__)
    CORS(app)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "version": "1.0.0",
            "dataset": "students",
            "dataset_rows": 200,
            "pipeline_stages": [
                "lexer",
                "parser",
                "semantic",
                "logical_ir",
                "planner",
                "cost",
                "selector",
                "execution",
                "feedback",
            ],
        })

    @app.route("/api/examples", methods=["GET"])
    def get_examples():
        return jsonify({"examples": EXAMPLE_QUERIES})

    @app.route("/api/query/execute", methods=["POST"])
    def execute():
        data = request.get_json(silent=True) or {}
        query_str = data.get("query", "").strip()
        if not query_str:
            return jsonify({"success": False, "error": {"message": "Query string is empty"}}), 400

        enable_learning = bool(data.get("enable_learning", False))
        alpha = float(data.get("alpha", 0.5))

        if bool(data.get("reset_learned_stats", False)):
            _GLOBAL_ADAPTIVE_STORE.clear()

        try:
            result = run_pipeline_with_stages(
                query_str=query_str,
                enable_learning=enable_learning,
                alpha=alpha,
                adaptive_store=_GLOBAL_ADAPTIVE_STORE,
            )
            return jsonify(result)
        except Exception as exc:
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": {
                    "stage": "system",
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            }), 500

    @app.route("/api/adaptive/reset", methods=["POST"])
    def reset_adaptive():
        _GLOBAL_ADAPTIVE_STORE.clear()
        return jsonify({
            "status": "reset",
            "message": "Adaptive learned statistics store cleared successfully.",
            "stored_profiles": 0,
        })

    return app


if __name__ == "__main__":
    import os
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    app = create_app()
    print(f"Adaptive Query Execution Planner API listening on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)

