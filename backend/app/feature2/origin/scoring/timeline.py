"""
Release time window estimation based on multi-horizon trajectory convergence (Task 3D).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from ...schemas.output_schema import ReleaseTimeWindow, ReleaseTimeWindowRange, OriginCandidate
from ...config import BackwardTracingConfig, default_settings


class ReleaseTimelineEstimator:
    """
    Estimates the plausible historical window [start, end] and peak evidence release time
    from ranked origin candidates passing a relative evidence threshold.
    """

    def __init__(self, config: Optional[BackwardTracingConfig] = None):
        self.config = config or default_settings.backward

    def estimate_candidate_window(
        self,
        ranked_candidates: List[OriginCandidate],
        relative_score_threshold: Optional[float] = None,
    ) -> Optional[ReleaseTimeWindowRange]:
        """
        Derives the plausible release time window from candidates whose scores
        are within the relative threshold of the best candidate score.

        Args:
            ranked_candidates: Candidates sorted descending by candidate_score.
            relative_score_threshold: Threshold ratio (default from config, e.g. 0.8).

        Returns:
            ReleaseTimeWindowRange or None if no candidates are provided.
        """
        if not ranked_candidates:
            return None

        threshold_ratio = (
            relative_score_threshold if relative_score_threshold is not None
            else self.config.relative_score_threshold
        )

        best = ranked_candidates[0]
        min_score = best.candidate_score * threshold_ratio

        plausible = [c for c in ranked_candidates if c.candidate_score >= min_score]
        if not plausible:
            plausible = [best]

        earliest = min(c.release_time for c in plausible)
        latest = max(c.release_time for c in plausible)
        duration_h = (latest - earliest).total_seconds() / 3600.0

        return ReleaseTimeWindowRange(
            start=earliest,
            end=latest,
            peak_evidence_time=best.release_time,
            duration_hours=round(duration_h, 3)
        )

    @staticmethod
    def estimate_window(
        cluster_info: Dict[str, Any],
        observation_time: datetime
    ) -> ReleaseTimeWindow:
        """
        DEPRECATED (Legacy Compatibility Only).
        Production code uses estimate_candidate_window() based on dynamic multi-horizon evidence scores.
        This static fallback remains strictly for legacy test compatibility.
        """
        import warnings
        warnings.warn(
            "ReleaseTimelineEstimator.estimate_window is deprecated. "
            "Use estimate_candidate_window() for dynamic score-based release window calculation.",
            DeprecationWarning,
            stacklevel=2,
        )
        peak_t = cluster_info.get("peak_evidence_utc", observation_time - timedelta(hours=12))
        return ReleaseTimeWindow(
            earliest_utc=observation_time - timedelta(hours=24),
            latest_utc=observation_time - timedelta(hours=6),
            peak_evidence_utc=peak_t,
            window_duration_hours=18.0
        )
