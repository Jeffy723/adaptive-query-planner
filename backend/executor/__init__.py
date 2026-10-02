"""
backend/executor — Basic Query Execution Engine.

Public API
----------
    from backend.executor import (
        Executor,
        ExecutionResult,
        OperationStats,
        Row,
        DatasetProvider,
        ExecutionError,
    )

    from backend.schema import SCHEMA_REGISTRY

    result = Executor(SCHEMA_REGISTRY).execute(plan)

    print(f"Returned {result.row_count} rows.")
    for row in result.rows:
        print(row)
    print(result.explain_stats())
"""

from .dataset import DatasetProvider
from .engine  import Executor
from .errors  import ExecutionError
from .result  import ExecutionResult, OperationStats, Row

__all__ = [
    "Executor",
    "ExecutionResult",
    "OperationStats",
    "Row",
    "DatasetProvider",
    "ExecutionError",
]
