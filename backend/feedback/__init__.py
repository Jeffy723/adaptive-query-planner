"""
backend/feedback — Runtime Feedback & Adaptive Learning.

Public API
----------
    from backend.feedback import (
        FeedbackCollector,
        collect_feedback,
        AdaptiveStatisticsStore,
        OperationFeedback,
        ExecutionFeedback,
        SelectivityFeedback,
        DEFAULT_ALPHA,
    )
"""

from .adaptive_store import AdaptiveStatisticsStore
from .collector import (
    DEFAULT_ALPHA,
    FeedbackCollector,
    collect_feedback,
)
from .model import (
    ExecutionFeedback,
    OperationFeedback,
    SelectivityFeedback,
)

__all__ = [
    "FeedbackCollector",
    "collect_feedback",
    "AdaptiveStatisticsStore",
    "OperationFeedback",
    "ExecutionFeedback",
    "SelectivityFeedback",
    "DEFAULT_ALPHA",
]
