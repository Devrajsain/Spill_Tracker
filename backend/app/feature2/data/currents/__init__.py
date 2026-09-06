"""
Ocean current data providers and interfaces.
"""

from .base import OceanCurrentsProvider
from .mock import MockCurrentsProvider
from .local import LocalCurrentsProvider
from .hycom import HYCOMCurrentsProvider, HYCOMConfig
from .copernicus import CopernicusCurrentsProvider, CopernicusConfig

__all__ = [
    "OceanCurrentsProvider",
    "MockCurrentsProvider",
    "LocalCurrentsProvider",
    "HYCOMCurrentsProvider",
    "HYCOMConfig",
    "CopernicusCurrentsProvider",
    "CopernicusConfig",
]
