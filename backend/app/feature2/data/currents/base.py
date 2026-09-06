"""
Specialized ocean currents provider interface.
"""

from abc import abstractmethod
from ..base import EnvironmentalDataProvider


class OceanCurrentsProvider(EnvironmentalDataProvider):
    """Abstract base class for surface ocean current (u_current, v_current) providers."""

    @property
    def field_type(self) -> str:
        return "ocean_currents"
