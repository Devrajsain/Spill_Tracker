"""
Local NetCDF ocean currents provider implementing HistoricalCurrentProvider.
Reads and interpolates gridded currents (u, v) from local disk files (HYCOM, Copernicus, CMEMS NetCDF).
"""

from datetime import datetime
from typing import Optional, Union
from ..base import HistoricalCurrentProvider, CurrentSample
from ..local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from ...schemas.simulation_schema import EnvironmentalQueryWindow
from ...logging_config import logger


class LocalCurrentsProvider(HistoricalCurrentProvider):
    """
    Local file-based provider for historical ocean current fields.
    Reuses open NetCDF dataset across simulation particle queries to eliminate I/O overhead.
    """

    def __init__(
        self,
        filepath: str,
        variable_mapping: Optional[VariableMapping] = None
    ):
        self.filepath = filepath
        self.mapping = variable_mapping
        self.reader = LocalNetCDFDatasetReader(
            filepath=filepath,
            variable_mapping=variable_mapping,
            field_type="ocean_currents"
        )

    @property
    def provider_name(self) -> str:
        return "local_netcdf_currents"

    def open(self) -> None:
        """Opens dataset and loads grid structure into memory."""
        self.reader.open_dataset()

    def close(self) -> None:
        """Closes open dataset file handle."""
        self.reader.close_dataset()

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        """Ensures dataset is open and ready for queries within the bounding box."""
        self.reader.open_dataset()
        return True

    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        """
        Retrieves interpolated ocean current sample in meters per second (m/s) at UTC time.
        """
        u_mps, v_mps = self.reader.interpolate(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp
        )
        # Parse timestamp to UTC datetime
        from ..time_utils import normalize_to_utc
        utc_time = normalize_to_utc(timestamp)

        return CurrentSample(
            u_current_mps=u_mps,
            v_current_mps=v_mps,
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )
