"""
HYCOM (Hybrid Coordinate Ocean Model) hydrodynamic data provider adapter.
Provides configuration, THREDDS / OPeNDAP URL construction, and coordinate bounding box formulation.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field

from ..base import HistoricalCurrentProvider, CurrentSample
from ..time_utils import normalize_to_utc
from ...schemas.simulation_schema import EnvironmentalQueryWindow
from ...exceptions import EnvironmentalDataUnavailableError
from ...logging_config import logger


class HYCOMConfig(BaseModel):
    """Configuration for HYCOM OPeNDAP / THREDDS server."""
    thredds_base_url: str = Field(
        default="https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0",
        description="Base OPeNDAP dataset URL for global 1/12 degree HYCOM."
    )
    timeout_seconds: int = Field(default=60, description="Network timeout in seconds.")
    spatial_resolution_deg: float = Field(default=0.08, description="Grid resolution in degrees (~8-9km).")


class HYCOMCurrentsProvider(HistoricalCurrentProvider):
    """
    Adapter for global HYCOM 1/12 degree surface current reanalysis / analysis via OPeNDAP.
    
    Status: ADAPTER_SCAFFOLD
    Note: Requires direct internet connectivity to tds.hycom.org for OPeNDAP slicing.
    """

    def __init__(self, config: Optional[HYCOMConfig] = None):
        self.config = config or HYCOMConfig()

    @property
    def provider_name(self) -> str:
        return "hycom_ocean_currents"

    def build_opendap_slice_url(self, window: Any) -> str:
        """
        Constructs OPeNDAP constraint expression URL for remote server-side slicing.
        """
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="historical")
        # Example OPeNDAP expression requesting surface water_u and water_v variables
        return (
            f"{self.config.thredds_base_url}?"
            f"water_u[0:1:0][0:1:0][{min_lat}:1:{max_lat}][{min_lon}:1:{max_lon}],"
            f"water_v[0:1:0][0:1:0][{min_lat}:1:{max_lat}][{min_lon}:1:{max_lon}]"
        )

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        """
        Fetches or connects to HYCOM OPeNDAP stream for the given spacetime bounding box.
        """
        slice_url = self.build_opendap_slice_url(window)
        logger.info(f"[HYCOMCurrentsProvider] Formulated OPeNDAP slice endpoint: {slice_url}")
        # TODO (Phase 4): Connect to OPeNDAP endpoint or download NetCDF slice into local cache
        return True

    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        """
        Retrieves current from ingested HYCOM stream.
        Raises EnvironmentalDataUnavailableError if live OPeNDAP stream is not configured.
        """
        utc_time = normalize_to_utc(timestamp)
        raise EnvironmentalDataUnavailableError(
            "HYCOM OPeNDAP live remote stream is not initialized with a cached dataset. "
            "Please use LocalCurrentsProvider with a downloaded NetCDF file or MockCurrentsProvider for testing."
        )
