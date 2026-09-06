"""
Local NetCDF surface wind provider implementing HistoricalWindProvider.
Reads and interpolates 10-meter wind fields (u10, v10) from local disk files (ERA5, GFS, WRF NetCDF).
"""

from datetime import datetime
from typing import Optional, Union
from ..base import HistoricalWindProvider, WindSample
from ..local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from ...schemas.simulation_schema import EnvironmentalQueryWindow
from ...logging_config import logger


class LocalWindProvider(HistoricalWindProvider):
    """
    Local file-based provider for historical atmospheric surface wind fields.
    Reuses open NetCDF dataset across simulation particle queries.
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
            field_type="surface_wind"
        )

    @property
    def provider_name(self) -> str:
        return "local_netcdf_wind"

    def open(self) -> None:
        """Opens dataset and loads grid structure into memory."""
        self.reader.open_dataset()

    def close(self) -> None:
        """Closes open dataset file handle."""
        self.reader.close_dataset()

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        self.reader.open_dataset()
        return True

    def get_wind(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> WindSample:
        """
        Retrieves interpolated 10-meter surface wind sample in meters per second (m/s) at UTC time.
        """
        u_mps, v_mps = self.reader.interpolate(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp
        )
        from ..time_utils import normalize_to_utc
        utc_time = normalize_to_utc(timestamp)

        return WindSample(
            u_wind_mps=u_mps,
            v_wind_mps=v_mps,
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )
