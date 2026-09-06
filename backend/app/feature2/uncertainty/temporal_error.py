"""
Temporal uncertainty bounds for estimated release time windows.
"""

from datetime import datetime, timedelta
from typing import Tuple
from ..schemas.output_schema import ReleaseTimeWindow


class TemporalUncertaintyEstimator:
    """Estimates temporal dispersion bounds for release time hypotheses."""

    @staticmethod
    def calculate_bounds(
        peak_time: datetime,
        window_hours: float
    ) -> ReleaseTimeWindow:
        half_window = timedelta(hours=window_hours / 2.0)
        return ReleaseTimeWindow(
            earliest_utc=peak_time - half_window,
            latest_utc=peak_time + half_window,
            peak_evidence_utc=peak_time,
            window_duration_hours=window_hours
        )
