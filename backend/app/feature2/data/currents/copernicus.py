"""
Copernicus Marine Service (CMEMS) hydrodynamic ocean currents provider adapter (Task 4).
Supports:
  1. Local pre-downloaded NetCDF files (COPERNICUS_CURRENTS_DATA_PATH or explicit path).
  2. Domain-keyed local filesystem caching via EnvironmentalDataCacheManager.
  3. Optional live authenticated Copernicus Marine Data Store downloads.
  4. Explicit surface layer depth selection (depth <= 0.494m).
  5. Exact bilinear spatial interpolation and linear temporal interpolation.
  6. Strict coverage validation and provenance tracking.
"""

from datetime import datetime, timezone, timedelta
import os
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from ..base import CurrentSample, ForecastCurrentProvider, HistoricalCurrentProvider
from ..cache import EnvironmentalDataCacheManager, generate_cache_key
from ..local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from ..time_utils import normalize_to_utc
from ...schemas.simulation_schema import EnvironmentalQueryWindow
from ...exceptions import (
    ConfigurationError,
    EnvironmentalCoverageError,
    EnvironmentalDataUnavailableError,
    OutOfDomainError,
    TemporalCoverageError,
)
from ...logging_config import logger
from ...config import Feature2Settings, default_settings


class CopernicusConfig(BaseModel):
    """Configuration and credentials for Copernicus Marine Service API and storage."""
    dataset_id: str = Field(
        default="cmems_mod_glo_phy_my_0.083deg_P1D-m",
        description="Copernicus dataset product identifier (e.g. reanalysis or operational forecast)."
    )
    api_url: str = Field(
        default="https://europe.cloudservice.copernicus.eu/cas/v1/tickets",
        description="Copernicus Marine API endpoint."
    )
    username: Optional[str] = Field(
        default=None,
        description="CMEMS account username. Can be configured via CMEMS_USERNAME env var."
    )
    password: Optional[str] = Field(
        default=None,
        description="CMEMS account password. Can be configured via CMEMS_PASSWORD env var."
    )
    data_path: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for Copernicus currents. Reads from COPERNICUS_CURRENTS_DATA_PATH if not set."
    )
    cache_dir: str = Field(
        default="./data_cache",
        description="Cache directory for downloaded Copernicus current slices."
    )
    depth_level_m: float = Field(
        default=0.494,
        ge=0.0,
        description="Depth slice in meters (surface layer) for 2D horizontal Lagrangian transport."
    )
    u_var: str = Field(
        default="uo",
        description="Variable name for eastward water velocity component."
    )
    v_var: str = Field(
        default="vo",
        description="Variable name for northward water velocity component."
    )


class CopernicusCurrentsProvider(HistoricalCurrentProvider):
    """
    Real data provider for Copernicus Marine historical ocean currents.
    Consumes local NetCDF files, cached subsets, or authenticated CMEMS downloads.
    Explicitly selects the top ocean surface layer (0 to depth_level_m) for 2D surface drift.
    """

    def __init__(
        self,
        config: Optional[CopernicusConfig] = None,
        data_path: Optional[str] = None,
        cache_manager: Optional[EnvironmentalDataCacheManager] = None,
    ):
        base_cfg = config or CopernicusConfig(
            dataset_id=os.getenv("COPERNICUS_HISTORICAL_DATASET_ID", "cmems_mod_glo_phy_my_0.083deg_P1D-m")
        )
        self.config = base_cfg

        # Resolve local data path: explicit arg > config > environment variable
        resolved_path = (
            data_path
            or self.config.data_path
            or os.getenv("COPERNICUS_CURRENTS_DATA_PATH")
        )
        self.data_path = os.path.abspath(resolved_path) if resolved_path else None

        # Resolve CMEMS credentials: config > environment variables
        self.username = self.config.username if self.config.username is not None else os.getenv("CMEMS_USERNAME")
        self.password = self.config.password if self.config.password is not None else os.getenv("CMEMS_PASSWORD")
        self._is_authenticated = bool(self.username and self.password)

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
        return "copernicus_currents"

    @property
    def provenance(self) -> Dict[str, Any]:
        """Returns provenance metadata for the active ocean currents dataset."""
        return {
            "source": "Copernicus Marine Service",
            "product": self.config.dataset_id,
            "variables": [self.config.u_var, self.config.v_var],
            "units": "m/s",
            "selected_depth_m": self.config.depth_level_m,
            "layer_description": f"Surface ocean layer (0.0 to {self.config.depth_level_m}m)",
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
            field_type="ocean_currents"
        )
        self.reader.open_dataset()
        self._active_filepath = filepath
        self._source_type = source_type
        self._cache_status = cache_status

    def build_subset_request(self, window: Any) -> Dict[str, Any]:
        """
        Constructs parameter payload for Copernicus Marine Data Store subsetting API.
        """
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="historical")
        return {
            "dataset_id": self.config.dataset_id,
            "variables": [self.config.u_var, self.config.v_var],
            "minimum_latitude": min_lat,
            "maximum_latitude": max_lat,
            "minimum_longitude": min_lon,
            "maximum_longitude": max_lon,
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat(),
            "minimum_depth": None,
            "maximum_depth": self.config.depth_level_m,
        }

    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        """
        Prepares or caches the gridded Copernicus current field for target spacetime window.
        Validates coverage against the query window.
        """
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="historical")

        # Case 1: Active local dataset already loaded
        if self.reader is not None:
            try:
                self.reader.validate_domain_coverage(window, mode="historical")
                return True
            except EnvironmentalCoverageError as cov_err:
                logger.warning(f"[CopernicusCurrentsProvider] Loaded dataset coverage failure: {cov_err}")
                raise cov_err

        # Case 2: Configured local data path
        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")
            self.reader.validate_domain_coverage(window, mode="historical")
            return True

        # Case 3: Check cache by deterministic key
        req = self.build_subset_request(window)
        cache_key = generate_cache_key(
            provider_name="copernicus",
            dataset_id=self.config.dataset_id,
            variables=[self.config.u_var, self.config.v_var],
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            start_time_iso=req["start_datetime"],
            end_time_iso=req["end_datetime"],
            extra_params={"depth": self.config.depth_level_m}
        )

        cached_file = self.cache_manager.get_cached_file("copernicus", cache_key)
        if cached_file:
            self._init_reader(cached_file, source_type="cache", cache_status="hit")
            self.reader.validate_domain_coverage(window, mode="historical")
            return True

        # Case 4: Remote download via copernicusmarine SDK
        if not self._is_authenticated:
            logger.warning(
                "[CopernicusCurrentsProvider] CMEMS credentials (CMEMS_USERNAME, CMEMS_PASSWORD) "
                "not provided. Live remote download skipped."
            )
            return False

        try:
            import copernicusmarine
        except ImportError:
            logger.warning(
                "[CopernicusCurrentsProvider] `copernicusmarine` package is not installed. Remote download skipped."
            )
            return False

        # Execute remote subset download with atomic cache save
        try:
            logger.info(f"[CopernicusCurrentsProvider] Initiating authenticated CMEMS download for key '{cache_key}'")
            req = self.build_subset_request(window)

            def _download_action(tmp_path: str) -> None:
                output_dir = os.path.dirname(os.path.abspath(tmp_path))
                output_file = os.path.basename(tmp_path)
                copernicusmarine.subset(
                    dataset_id=req["dataset_id"],
                    variables=req["variables"],
                    minimum_latitude=req["minimum_latitude"],
                    maximum_latitude=req["maximum_latitude"],
                    minimum_longitude=req["minimum_longitude"],
                    maximum_longitude=req["maximum_longitude"],
                    start_datetime=(start_time - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                    end_datetime=(end_time + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0).isoformat(),
                    minimum_depth=req["minimum_depth"],
                    maximum_depth=max(req["maximum_depth"], 0.5) if req["maximum_depth"] is not None else 0.5,
                    output_directory=output_dir,
                    output_filename=output_file,
                    username=self.username,
                    password=self.password,
                    overwrite=True,
                )

            final_path = self.cache_manager.atomic_save(
                "copernicus",
                cache_key,
                _download_action,
            )
            self._init_reader(final_path, source_type="remote_download", cache_status="miss")
            self.reader.validate_domain_coverage(window, mode="historical")
            return True
        except Exception as e:
            logger.error(f"[CopernicusCurrentsProvider] CMEMS download failed: {e}")
            raise EnvironmentalDataUnavailableError(f"Copernicus Marine retrieval failed: {e}") from e

    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        """
        Retrieves interpolated surface ocean current vector (u_current_mps, v_current_mps) in m/s at UTC time.
        Raises OutOfDomainError or TemporalCoverageError if outside coverage.
        """
        if self.reader is None:
            raise EnvironmentalDataUnavailableError(
                "Copernicus Marine currents dataset is not loaded. Please provide a valid NetCDF file path via "
                "`COPERNICUS_CURRENTS_DATA_PATH` or configure valid CMEMS credentials."
            )

        u_mps, v_mps = self.reader.interpolate(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp
        )
        utc_time = normalize_to_utc(timestamp)

        return CurrentSample(
            u_current_mps=u_mps,
            v_current_mps=v_mps,
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )


class CopernicusForecastCurrentsProvider(ForecastCurrentProvider):
    """
    Real data provider for Copernicus Marine operational forecast ocean currents (+0 to +48h).
    Implements ForecastCurrentProvider.
    """

    def __init__(
        self,
        config: Optional[CopernicusConfig] = None,
        data_path: Optional[str] = None,
        cache_manager: Optional[EnvironmentalDataCacheManager] = None,
        settings: Optional[Feature2Settings] = None,
    ):
        base_cfg = config or CopernicusConfig(
            dataset_id=os.getenv("COPERNICUS_FORECAST_DATASET_ID", "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m")
        )
        self.config = base_cfg
        self.settings = settings or default_settings

        resolved_path = (
            data_path
            or self.config.data_path
            or os.getenv("COPERNICUS_FORECAST_CURRENTS_DATA_PATH")
            or os.getenv("COPERNICUS_CURRENTS_DATA_PATH")
        )
        self.data_path = os.path.abspath(resolved_path) if resolved_path else None

        # Resolve CMEMS credentials: config > environment variables
        self.username = self.config.username if self.config.username is not None else os.getenv("CMEMS_USERNAME")
        self.password = self.config.password if self.config.password is not None else os.getenv("CMEMS_PASSWORD")
        self._is_authenticated = bool(self.username and self.password)

        self.cache_manager = cache_manager or EnvironmentalDataCacheManager(
            cache_root_dir=os.getenv("DATA_CACHE_DIR", self.config.cache_dir)
        )

        # Reader instance
        self.reader: Optional[LocalNetCDFDatasetReader] = None
        self._active_filepath: Optional[str] = None
        self._source_type: str = "uninitialized"
        self._cache_status: str = "none"

        # Fail-closed check: In production mode, local fixture paths are strictly forbidden unless explicit replay mode is enabled
        if (
            self.settings.environment == "production"
            and self.data_path
            and not getattr(self.settings.data, "allow_production_replay_fixture", False)
        ):
            raise ConfigurationError(
                f"Production mode strictly forbids local fixture data_path for Copernicus forecast currents ('{self.data_path}') "
                "unless allow_production_replay_fixture=True is explicitly configured."
            )

        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")

    @property
    def provider_name(self) -> str:
        return "copernicus_forecast_currents"

    @property
    def provenance(self) -> Dict[str, Any]:
        return {
            "source": "Copernicus Marine Service",
            "product": self.config.dataset_id,
            "variables": [self.config.u_var, self.config.v_var],
            "units": "m/s",
            "selected_depth_m": self.config.depth_level_m,
            "layer_description": f"Forecast surface ocean layer (0.0 to {self.config.depth_level_m}m)",
            "mode": "forecast",
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
            field_type="ocean_currents"
        )
        self.reader.open_dataset()
        self._active_filepath = filepath
        self._source_type = source_type
        self._cache_status = cache_status

    def build_subset_request(self, window: Any) -> Dict[str, Any]:
        """Constructs parameter payload for Copernicus Marine operational forecast API."""
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="forecast")
        return {
            "dataset_id": self.config.dataset_id,
            "variables": [self.config.u_var, self.config.v_var],
            "minimum_latitude": min_lat,
            "maximum_latitude": max_lat,
            "minimum_longitude": min_lon,
            "maximum_longitude": max_lon,
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat(),
            "minimum_depth": None,
            "maximum_depth": self.config.depth_level_m,
        }

    def fetch_grid(self, window: Any) -> bool:
        """Fetches and caches forecast ocean current grid."""
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="forecast")

        if self.reader is not None:
            try:
                self.reader.validate_domain_coverage(window, mode="forecast")
                return True
            except EnvironmentalCoverageError as cov_err:
                logger.warning(f"[CopernicusForecastCurrentsProvider] Coverage failure: {cov_err}")
                raise cov_err

        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")
            self.reader.validate_domain_coverage(window, mode="forecast")
            return True

        req = self.build_subset_request(window)
        cache_key = generate_cache_key(
            provider_name="copernicus_fc",
            dataset_id=self.config.dataset_id,
            variables=[self.config.u_var, self.config.v_var],
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            start_time_iso=req["start_datetime"],
            end_time_iso=req["end_datetime"],
            extra_params={"depth": self.config.depth_level_m}
        )

        forecast_ttl = (
            self.settings.data.cache_ttl_forecast_seconds
            if hasattr(self, "settings") and self.settings and hasattr(self.settings, "data")
            else 21600.0
        )
        cached_file = self.cache_manager.get_cached_file("copernicus", cache_key, max_age_seconds=forecast_ttl)
        if cached_file:
            self._init_reader(cached_file, source_type="cache", cache_status="hit")
            self.reader.validate_domain_coverage(window, mode="forecast")
            return True

        if not self._is_authenticated:
            logger.warning("[CopernicusForecastCurrentsProvider] Unauthenticated. Remote download skipped.")
            return False

        try:
            import copernicusmarine
        except ImportError:
            logger.warning("[CopernicusForecastCurrentsProvider] `copernicusmarine` package is not installed. Remote download skipped.")
            return False

        # Execute remote subset download with atomic cache save
        try:
            logger.info(f"[CopernicusForecastCurrentsProvider] Initiating authenticated CMEMS forecast download for key '{cache_key}'")
            req = self.build_subset_request(window)

            def _download_action(tmp_path: str) -> None:
                output_dir = os.path.dirname(os.path.abspath(tmp_path))
                output_file = os.path.basename(tmp_path)
                copernicusmarine.subset(
                    dataset_id=req["dataset_id"],
                    variables=req["variables"],
                    minimum_latitude=req["minimum_latitude"],
                    maximum_latitude=req["maximum_latitude"],
                    minimum_longitude=req["minimum_longitude"],
                    maximum_longitude=req["maximum_longitude"],
                    start_datetime=(start_time - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                    end_datetime=(end_time + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0).isoformat(),
                    minimum_depth=req["minimum_depth"],
                    maximum_depth=max(req["maximum_depth"], 0.5) if req["maximum_depth"] is not None else 0.5,
                    output_directory=output_dir,
                    output_filename=output_file,
                    username=self.username,
                    password=self.password,
                    overwrite=True,
                )

            final_path = self.cache_manager.atomic_save(
                "copernicus",
                cache_key,
                _download_action,
            )
            self._init_reader(final_path, source_type="remote_download", cache_status="miss")
            self.reader.validate_domain_coverage(window, mode="forecast")
            return True
        except (TemporalCoverageError, EnvironmentalCoverageError):
            raise
        except Exception as e:
            logger.error(f"[CopernicusForecastCurrentsProvider] CMEMS forecast download failed: {e}")
            raise EnvironmentalDataUnavailableError(f"Copernicus Marine forecast retrieval failed: {e}") from e

    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        if self.reader is None:
            raise EnvironmentalDataUnavailableError(
                "Copernicus Marine forecast currents dataset is not loaded."
            )

        u_mps, v_mps = self.reader.interpolate(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp
        )
        utc_time = normalize_to_utc(timestamp)

        return CurrentSample(
            u_current_mps=u_mps,
            v_current_mps=v_mps,
            latitude=latitude,
            longitude=longitude,
            timestamp=utc_time,
            quality_flag=1
        )
