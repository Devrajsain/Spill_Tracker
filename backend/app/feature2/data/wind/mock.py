"""
Deterministic mock atmospheric surface wind provider for reproducible tests.
"""

from datetime import datetime
from typing import Optional, Union
import math
from ..base import HistoricalWindProvider, WindSample
from ..time_utils import normalize_to_utc
from ...schemas.simulation_schema import EnvironmentalQueryWindow


class MockWindProvider(HistoricalWindProvider):
    """
    Synthetic analytical surface wind provider (10m winds).
    Supports uniform flow, cyclonic rotation, or temporal oscillating wind fields.
    """

    def __init__(
        self,
        const_u: float = 3.5,
        const_v: float = 2.0,
        pattern: str = "uniform",
        center_lat: Optional[float] = None,
        center_lon: Optional[float] = None,
    ):
        self.const_u = const_u
        self.const_v = const_v
        self.pattern = pattern
        self.center_lat = center_lat if center_lat is not None else 0.0
        self.center_lon = center_lon if center_lon is not None else 0.0

    @property
    def provider_name(self) -> str:
        return "mock_surface_wind"

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        return True

    def get_wind(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> WindSample:
        """Computes deterministic 10m surface wind vector at given location & time."""
        utc_time = normalize_to_utc(timestamp)

        if self.pattern == "uniform":
            u = self.const_u
            v = self.const_v
        elif self.pattern == "cyclonic":
            # Cyclonic circulation around center
            d_lat = latitude - self.center_lat
            d_lon = longitude - self.center_lon
            r_deg = math.sqrt(d_lat**2 + d_lon**2)
            if r_deg < 1e-6:
                u, v = 0.0, 0.0
            else:
                tangential = 8.0 * math.exp(-(r_deg * 111.0 / 100.0)**2)
                u = -tangential * (d_lat / r_deg)
                v = tangential * (d_lon / r_deg)
        elif self.pattern == "diurnal":
            # Diurnal sea breeze oscillation (24h period)
            hour = utc_time.hour + utc_time.minute / 60.0
            phase = 2.0 * math.pi * (hour / 24.0)
            u = self.const_u + 2.0 * math.cos(phase)
            v = self.const_v + 2.0 * math.sin(phase)
        else:
            u = self.const_u
            v = self.const_v

        return WindSample(
            u_wind_mps=float(u),
            v_wind_mps=float(v),
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )
