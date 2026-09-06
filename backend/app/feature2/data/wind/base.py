"""
Specialized surface wind provider interface.
"""

from ..base import EnvironmentalDataProvider


class SurfaceWindProvider(EnvironmentalDataProvider):
    """Abstract base class for 10-meter surface wind (u10, v10) providers."""

    @property
    def field_type(self) -> str:
        return "surface_wind_10m"
