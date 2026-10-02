"""
Adaptive Query Execution Planner — backend package.

Unified entry point:
    from backend import execute_query, QueryPipeline, QueryResult
"""

from .pipeline import (
    PipelineError,
    QueryPipeline,
    QueryResult,
    ResultMismatchError,
    execute_query,
)

__all__ = [
    "execute_query",
    "QueryPipeline",
    "QueryResult",
    "PipelineError",
    "ResultMismatchError",
]
