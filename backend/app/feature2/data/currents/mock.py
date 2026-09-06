"""
Deterministic mock ocean currents provider for reproducible tests and offline development.
"""

from datetime import datetime
from typing import Callable, Optional, Union
import math
from ..base import HistoricalCurrentProvider, CurrentSample
from ..time_utils import normalize_to_utc
from ...schemas.simulation_schema import EnvironmentalQueryWindow


class MockCurrentsProvider(HistoricalCurrentProvider):
    """
    Synthetic analytical ocean current provider.
    Supports uniform flow, linear spatial shear, or analytical vortex structures.
    """

    def __init__(
        self,
        const_u: float = 0.25,
        const_v: float = 0.10,
        pattern: str = "uniform",
        center_lat: Optional[float] = None,
        center_lon: Optional[float] = None,
        vortex_radius_km: float = 50.0,
        vortex_max_speed: float = 0.50,
    ):
        self.const_u = const_u
        self.const_v = const_v
        self.pattern = pattern
        self.center_lat = center_lat if center_lat is not None else 0.0
        self.center_lon = center_lon if center_lon is not None else 0.0
        self.vortex_radius_km = vortex_radius_km
        self.vortex_max_speed = vortex_max_speed

    @property
    def provider_name(self) -> str:
        return "mock_currents"

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        return True

    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        """Computes deterministic ocean current vector at given location & time."""
        utc_time = normalize_to_utc(timestamp)

        if self.pattern == "uniform":
            u = self.const_u
            v = self.const_v
        elif self.pattern == "vortex":
            # Circular Rankine-like vortex around center (center_lat, center_lon)
            d_lat = latitude - self.center_lat
            d_lon = longitude - self.center_lon
            r_deg = math.sqrt(d_lat**2 + d_lon**2)
            if r_deg < 1e-6:
                u, v = 0.0, 0.0
            else:
                # Tangential velocity: perpendicular to radius vector (-d_lat, d_lon)
                tangential = self.vortex_max_speed * math.exp(-((r_deg * 111.0) / self.vortex_radius_km)**2)
                u = -tangential * (d_lat / r_deg)
                v = tangential * (d_lon / r_deg)
        elif self.pattern == "gradient":
            # Spatial gradient: flow increases northward
            u = self.const_u + 0.01 * (latitude - self.center_lat)
            v = self.const_v + 0.01 * (longitude - self.center_lon)
        else:
            u = self.const_u
            v = self.const_v

        return CurrentSample(
            u_current_mps=float(u),
            v_current_mps=float(v),
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )
