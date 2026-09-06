"""
ECMWF ERA5 Atmospheric Reanalysis surface wind data provider adapter (Task 4).
Supports:
  1. Local pre-downloaded NetCDF files (ERA5_WIND_DATA_PATH or explicit path).
  2. Domain-keyed local filesystem caching via EnvironmentalDataCacheManager.
  3. Optional live authenticated Copernicus Climate Data Store (CDS) downloads.
  4. Exact bilinear spatial interpolation and linear temporal interpolation.
  5. Strict coverage validation and provenance tracking.
"""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from ..base import HistoricalWindProvider, WindSample
from ..cache import EnvironmentalDataCacheManager, generate_cache_key
from ..local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from ..time_utils import normalize_to_utc
from ...schemas.simulation_schema import EnvironmentalQueryWindow
from ...exceptions import (
    EnvironmentalCoverageError,
    EnvironmentalDataUnavailableError,
    OutOfDomainError,
    TemporalCoverageError,
)
from ...logging_config import logger


class ERA5Config(BaseModel):
    """Configuration for ECMWF Copernicus CDS API client and local ERA5 storage."""
    dataset_name: str = Field(
        default="reanalysis-era5-single-levels",
        description="CDS dataset product identifier for hourly surface single levels."
    )
    api_url: str = Field(
        default="https://cds.climate.copernicus.eu/api/v2",
        description="Copernicus Climate Data Store API URL."
    )
    api_key: Optional[str] = Field(
        default=None,
        description="CDS API Key (UID:API-Key). Reads from CDSAPI_KEY env var if not set."
    )
    data_path: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for ERA5 wind. Reads from ERA5_WIND_DATA_PATH if not set."
    )
    cache_dir: str = Field(
        default="./data_cache",
        description="Cache directory for downloaded ERA5 slices."
    )
    spatial_resolution_deg: float = Field(
        default=0.25,
        description="Grid resolution in degrees (~28km)."
    )
    u_var: str = Field(
        default="u10",
        description="Variable name for 10m eastward wind component."
    )
    v_var: str = Field(
        default="v10",
        description="Variable name for 10m northward wind component."
    )


class ERA5WindProvider(HistoricalWindProvider):
    """
    Real data provider for ECMWF ERA5 hourly 10m surface wind reanalysis.
    Consumes local NetCDF files, cached subsets, or authenticated CDS downloads.
    """

    def __init__(
        self,
        config: Optional[ERA5Config] = None,
        data_path: Optional[str] = None,
        cache_manager: Optional[EnvironmentalDataCacheManager] = None,
    ):
        self.config = config or ERA5Config()

        # Resolve local data path: explicit arg > config > environment variable
        resolved_path = (
            data_path
            or self.config.data_path
            or os.getenv("ERA5_WIND_DATA_PATH")
        )
        self.data_path = os.path.abspath(resolved_path) if resolved_path else None

        # Resolve CDS API Key: config > environment variable
        self.api_key = self.config.api_key if self.config.api_key is not None else os.getenv("CDSAPI_KEY")
        self.api_url = os.getenv("CDSAPI_URL", self.config.api_url)
        self._is_authenticated = bool(self.api_key or os.path.exists(os.path.expanduser("~/.cdsapirc")))

        # Cache manager
        self.cache_manager = cache_manager or EnvironmentalDataCacheManager(
            cache_root_dir=os.getenv("DATA_CACHE_DIR", self.config.cache_dir)
        )

        # Reader instance
        self.reader: Optional[LocalNetCDFDatasetReader] = None
        self._active_filepath: Optional[str] = None
        self._source_type: str = "uninitialized"
        self._cache_status: str = "none"

        # Initialize reader if local data path is present
        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")

    @property
    def provider_name(self) -> str:
        return "era5_hourly_wind"

    @property
    def provenance(self) -> Dict[str, Any]:
        """Returns provenance metadata for the active environmental wind dataset."""
        return {
            "source": "ECMWF ERA5",
            "product": self.config.dataset_name,
            "variables": [self.config.u_var, self.config.v_var],
            "units": "m/s",
            "mode": "historical",
            "source_type": self._source_type,
            "cache_status": self._cache_status,
            "active_filepath": self._active_filepath,
            "spatial_domain": {
                "min_lat": self.reader.min_lat if self.reader else None,
                "max_lat": self.reader.max_lat if self.reader else None,
                "min_lon": self.reader.min_lon if self.reader else None,
                "max_lon": self.reader.max_lon if self.reader else None,
            },
            "temporal_domain": {
                "start": self.reader.min_time.isoformat() if self.reader else None,
                "end": self.reader.max_time.isoformat() if self.reader else None,
            }
        }

    def _init_reader(self, filepath: str, source_type: str, cache_status: str) -> None:
        """Initializes LocalNetCDFDatasetReader on the given NetCDF file."""
        mapping = VariableMapping(
            u_var=self.config.u_var,
            v_var=self.config.v_var,
        )
        self.reader = LocalNetCDFDatasetReader(
            filepath=filepath,
            variable_mapping=mapping,
            field_type="surface_wind"
        )
        self.reader.open_dataset()
        self._active_filepath = filepath
        self._source_type = source_type
        self._cache_status = cache_status

    def build_cds_request(self, window: Any) -> Dict[str, Any]:
        """
        Constructs parameter dictionary for CDS API retrieval.
        Area bounding box format in CDS is [North, West, South, East].
        """
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="historical")
        from datetime import timedelta
        cur_date = start_time.date()
        end_date = end_time.date()
        years = set()
        months = set()
        days = set()
        while cur_date <= end_date:
            years.add(str(cur_date.year))
            months.add(f"{cur_date.month:02d}")
            days.add(f"{cur_date.day:02d}")
            cur_date += timedelta(days=1)

        year_val = sorted(list(years))[0] if len(years) == 1 else sorted(list(years))

        return {
            "product_type": ["reanalysis"],
            "format": "netcdf",
            "data_format": "netcdf",
            "download_format": "unarchived",
            "variable": [
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
            ],
            "year": year_val,
            "month": sorted(list(months)),
            "day": sorted(list(days)),
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [
                max_lat,  # North
                min_lon,  # West
                min_lat,  # South
                max_lon,  # East
            ],
        }

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        """
        Prepares or caches the gridded ERA5 wind field for target spacetime window.
        Validates coverage against the query window.
        """
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="historical")

        # Case 1: Active local dataset already loaded
        if self.reader is not None:
            # Validate coverage
            try:
                self.reader.validate_domain_coverage(window, mode="historical")
                return True
            except EnvironmentalCoverageError as cov_err:
                logger.warning(f"[ERA5WindProvider] Loaded dataset coverage failure: {cov_err}")
                raise cov_err

        # Case 2: Configured local data path
        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")
            self.reader.validate_domain_coverage(window, mode="historical")
            return True

        # Case 3: Check cache by deterministic key
        cache_key = generate_cache_key(
            provider_name="era5",
            dataset_id=self.config.dataset_name,
            variables=[self.config.u_var, self.config.v_var],
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            start_time_iso=start_time.isoformat(),
            end_time_iso=end_time.isoformat(),
        )

        cached_file = self.cache_manager.get_cached_file("era5", cache_key)
        if cached_file:
            self._init_reader(cached_file, source_type="cache", cache_status="hit")
            self.reader.validate_domain_coverage(window, mode="historical")
            return True

        # Case 4: Remote download via CDS API client
        if not self._is_authenticated:
            logger.warning(
                "[ERA5WindProvider] CDS API credentials (CDSAPI_KEY) not found and no local/cached "
                "ERA5 dataset covers requested domain. Live remote download skipped."
            )
            return False

        try:
            import cdsapi
        except ImportError:
            logger.warning(
                "[ERA5WindProvider] `cdsapi` package is not installed. Remote download skipped."
            )
            return False

        # Execute remote download with atomic cache save
        try:
            logger.info(f"[ERA5WindProvider] Initiating authenticated CDS download for key '{cache_key}'")
            cds_req = self.build_cds_request(window)

            def _download_action(tmp_path: str) -> None:
                client = cdsapi.Client(url=self.api_url, key=self.api_key, quiet=True)
                client.retrieve(self.config.dataset_name, cds_req, tmp_path)

            final_path = self.cache_manager.atomic_save("era5", cache_key, _download_action)
            self._init_reader(final_path, source_type="remote_download", cache_status="miss")
            self.reader.validate_domain_coverage(window, mode="historical")
            return True
        except Exception as e:
            logger.error(f"[ERA5WindProvider] CDS download failed: {e}")
            raise EnvironmentalDataUnavailableError(f"ERA5 CDS retrieval failed: {e}") from e

    def get_wind(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> WindSample:
        """
        Retrieves interpolated 10m surface wind vector (u_wind_mps, v_wind_mps) in m/s at UTC time.
        Raises OutOfDomainError or TemporalCoverageError if outside coverage.
        """
        if self.reader is None:
            raise EnvironmentalDataUnavailableError(
                "ERA5 dataset is not loaded. Please provide a valid NetCDF file path via "
                "`ERA5_WIND_DATA_PATH` or configure valid CDS credentials."
            )

        u_mps, v_mps = self.reader.interpolate(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp
        )
        utc_time = normalize_to_utc(timestamp)

        return WindSample(
            u_wind_mps=u_mps,
            v_wind_mps=v_mps,
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )
