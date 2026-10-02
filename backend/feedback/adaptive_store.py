"""
backend/feedback/adaptive_store.py

Adaptive Statistics Store — in-memory repository for learned predicate selectivities.

Stores updated selectivity estimates calculated from execution feedback and
makes them available to the cost estimator on subsequent query optimization runs.
"""

from __future__ import annotations

from typing import Mapping

from .model import ExecutionFeedback


class AdaptiveStatisticsStore:
    """
    In-memory store for adaptively learned statistics.

    Maintains updated selectivities keyed by (table_name, predicate_string).
    """

    def __init__(self) -> None:
        # Key: (table_name.lower(), predicate_str) -> updated_selectivity (float)
        self._learned_selectivities: dict[tuple[str, str], float] = {}
        self._update_counts: dict[tuple[str, str], int] = {}

    def record_selectivity(
        self,
        table_name: str,
        predicate_str: str,
        selectivity: float,
    ) -> None:
        """Store or update a learned selectivity value."""
        key = (table_name.lower(), predicate_str.strip())
        self._learned_selectivities[key] = selectivity
        self._update_counts[key] = self._update_counts.get(key, 0) + 1

    def get_selectivity(
        self,
        table_name: str,
        predicate_str: str,
    ) -> float | None:
        """
        Return the learned selectivity for the predicate if recorded, else None.
        """
        # Try direct match
        key = (table_name.lower(), predicate_str.strip())
        if key in self._learned_selectivities:
            return self._learned_selectivities[key]

        # Try matching with or without "FILTER " prefix
        clean_pred = predicate_str.strip()
        if clean_pred.startswith("FILTER "):
            clean_pred = clean_pred[7:].strip()
            key2 = (table_name.lower(), clean_pred)
            if key2 in self._learned_selectivities:
                return self._learned_selectivities[key2]
        else:
            key3 = (table_name.lower(), f"FILTER {clean_pred}")
            if key3 in self._learned_selectivities:
                return self._learned_selectivities[key3]

        return None

    def has_selectivity(
        self,
        table_name: str,
        predicate_str: str,
    ) -> bool:
        """Return True if a learned selectivity exists for this predicate."""
        return self.get_selectivity(table_name, predicate_str) is not None

    def update_from_feedback(
        self,
        feedback: ExecutionFeedback,
        table_name: str = "students",
    ) -> int:
        """
        Ingest an ExecutionFeedback report and record all updated filter selectivities.

        Returns
        -------
        int
            Number of predicate selectivities updated.
        """
        updated_count = 0
        for op_fb in feedback.operation_feedback:
            if op_fb.selectivity_feedback is not None:
                sf = op_fb.selectivity_feedback
                self.record_selectivity(
                    table_name=table_name,
                    predicate_str=sf.predicate,
                    selectivity=sf.updated_selectivity,
                )
                updated_count += 1
        return updated_count

    def clear(self) -> None:
        """Reset all learned statistics."""
        self._learned_selectivities.clear()
        self._update_counts.clear()

    def get_all_profiles(self) -> dict[str, float]:
        """Return a read-only dictionary of all stored profiles formatted as strings."""
        return {
            f"{tbl}::{pred}": sel
            for (tbl, pred), sel in self._learned_selectivities.items()
        }

    def __len__(self) -> int:
        return len(self._learned_selectivities)
