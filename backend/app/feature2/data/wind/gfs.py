"""
NOAA Global Forecast System (GFS) operational surface wind forecast provider adapter (Task 4).
Supports:
  1. Local pre-downloaded NetCDF forecast files (GFS_WIND_DATA_PATH or explicit path).
  2. Domain-keyed local filesystem caching via EnvironmentalDataCacheManager.
  3. Operational +0 to +48h forecast horizons anchored strictly to T0.
  4. Exact bilinear spatial interpolation and linear temporal interpolation.
  5. Strict coverage validation and provenance tracking.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Dict, List, Optional, Union
import urllib.request
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
import xarray as xr

from ..base import ForecastWindProvider, WindSample
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


class GFSConfig(BaseModel):
    """Configuration for NOAA GFS 0.25-degree forecast products and storage."""
    aws_s3_bucket: str = Field(
        default="noaa-gfs-bdp-pds",
        description="Public AWS S3 Open Data bucket for NOAA GFS."
    )
    nomads_url: str = Field(
        default="https://nomads.ncep.noaa.gov/dods/gfs_0p25",
        description="NOAA NOMADS OPeNDAP / OpenDAP endpoint."
    )
    endpoint_url: str = Field(
        default="https://api.open-meteo.com/v1/gfs",
        description="NOAA GFS operational forecast API endpoint."
    )
    data_path: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for GFS wind. Reads from GFS_WIND_DATA_PATH if not set."
    )
    cache_dir: str = Field(
        default="./data_cache",
        description="Cache directory for downloaded GFS forecast slices."
    )
    forecast_step_hours: int = Field(
        default=3,
        description="Temporal resolution of GFS forecast slices."
    )
    spatial_resolution_deg: float = Field(
        default=0.25,
        description="Spatial resolution in degrees (~28km)."
    )
    u_var: str = Field(
        default="u10",
        description="Variable name for 10m eastward wind velocity."
    )
    v_var: str = Field(
        default="v10",
        description="Variable name for 10m northward wind velocity."
    )


class GFSWindProvider(ForecastWindProvider):
    """
    Real data provider for NOAA GFS 0.25-degree operational surface wind forecasts.
    Supplies forward meteorological forcing for slick forecasts (+0 to +48h).
    """

    def __init__(
        self,
        config: Optional[GFSConfig] = None,
        data_path: Optional[str] = None,
        cache_manager: Optional[EnvironmentalDataCacheManager] = None,
        settings: Optional[Feature2Settings] = None,
        mode: str = "forecast",
    ):
        self.config = config or GFSConfig()
        self.settings = settings or default_settings
        self.mode = mode.lower() if mode else "forecast"

        # Resolve local data path: explicit arg > config > environment variable
        resolved_path = (
            data_path
            or self.config.data_path
            or os.getenv("GFS_WIND_DATA_PATH")
        )
        self.data_path = os.path.abspath(resolved_path) if resolved_path else None

        # Cache manager
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
                f"Production mode strictly forbids local fixture data_path for GFS wind ('{self.data_path}') "
                "unless allow_production_replay_fixture=True is explicitly configured."
            )

        # Initialize reader if local data path is present
        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")

    @property
    def provider_name(self) -> str:
        return "gfs_operational_wind" if self.mode == "historical" else "gfs_forecast_wind"

    @property
    def data_category(self) -> str:
        return self.mode

    @property
    def field_type(self) -> str:
        return "surface_wind"

    @property
    def provenance(self) -> Dict[str, Any]:
        """Returns provenance metadata for the active GFS forecast wind dataset."""
        return {
            "source": "NOAA GFS",
            "product": "gfs_0p25_forecast" if self.mode == "forecast" else "gfs_0p25_operational",
            "variables": [self.config.u_var, self.config.v_var],
            "units": "m/s",
            "mode": self.mode,
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

    def close(self) -> None:
        """Closes reader dataset and releases open file handles."""
        if self.reader is not None:
            self.reader.close_dataset()

    def __enter__(self) -> "GFSWindProvider":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def build_forecast_request(self, window: Any) -> Dict[str, Any]:
        """Constructs forecast window parameters for GFS wind queries."""
        from ..domain import extract_query_bounds
        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode="forecast")
        return {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "product": "0p25_surface_wind",
        }

    def build_query_url(self, flat_lats: Any, flat_lons: Any, forecast_days: int = 3, past_days: int = 0) -> str:
        """Constructs query URL with native m/s units for Open-Meteo GFS endpoint."""
        lat_param = ",".join(f"{x:.4f}" for x in flat_lats)
        lon_param = ",".join(f"{x:.4f}" for x in flat_lons)
        past_param = f"&past_days={past_days}" if past_days > 0 else ""
        return (
            f"{self.config.endpoint_url}?latitude={lat_param}&longitude={lon_param}"
            f"&hourly=wind_u_component_10m,wind_v_component_10m&wind_speed_unit=ms&forecast_days={forecast_days}{past_param}"
        )

    def fetch_grid(self, window: EnvironmentalQueryWindow, mode: Optional[str] = None) -> bool:
        """
        Prepares or caches the gridded GFS surface wind field for target spacetime window.
        Supports both forward forecast (+0 to +48h) and operational historical backtracking (-72h to 0h).
        Validates coverage and data integrity against the query window.
        """
        from ..domain import extract_query_bounds
        target_mode = (mode or self.mode).lower()
        if target_mode not in ["historical", "forecast"]:
            target_mode = "forecast"

        min_lat, max_lat, min_lon, max_lon, start_time, end_time = extract_query_bounds(window, mode=target_mode)

        # Case 1: Active local dataset already loaded
        if self.reader is not None:
            try:
                self.reader.validate_domain_coverage(window, mode=target_mode)
                return True
            except EnvironmentalCoverageError as cov_err:
                logger.warning(f"[GFSWindProvider] Loaded dataset coverage failure: {cov_err}")
                raise cov_err

        # Case 2: Configured local data path
        if self.data_path and os.path.exists(self.data_path):
            self._init_reader(self.data_path, source_type="local_netcdf", cache_status="direct")
            self.reader.validate_domain_coverage(window, mode=target_mode)
            return True

        # Case 3: Check cache by deterministic key
        cache_key = generate_cache_key(
            provider_name=f"gfs_{target_mode}",
            dataset_id="gfs_0p25",
            variables=[self.config.u_var, self.config.v_var],
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            start_time_iso=start_time.isoformat(),
            end_time_iso=end_time.isoformat(),
        )

        forecast_ttl = (
            self.settings.data.cache_ttl_forecast_seconds
            if hasattr(self, "settings") and self.settings and hasattr(self.settings, "data")
            else 21600.0
        )
        cached_file = self.cache_manager.get_cached_file(f"gfs_{target_mode}", cache_key, max_age_seconds=forecast_ttl)
        if not cached_file:
            cached_file = self.cache_manager.get_cached_file("gfs", cache_key, max_age_seconds=forecast_ttl)
        if not cached_file:
            key_gfs = generate_cache_key(
                provider_name="gfs",
                dataset_id="gfs_0p25",
                variables=[self.config.u_var, self.config.v_var],
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                start_time_iso=start_time.isoformat(),
                end_time_iso=end_time.isoformat(),
            )
            cached_file = self.cache_manager.get_cached_file("gfs", key_gfs, max_age_seconds=forecast_ttl)
            if not cached_file:
                cached_file = self.cache_manager.get_cached_file(f"gfs_{target_mode}", key_gfs, max_age_seconds=forecast_ttl)

        if cached_file:
            self._init_reader(cached_file, source_type="cache", cache_status="hit")
            self.reader.validate_domain_coverage(window, mode=target_mode)
            return True

        # Case 4: Remote download from NOAA GFS operational forecast via Open-Meteo
        now_utc = datetime.now(timezone.utc)
        if target_mode == "historical" and start_time < now_utc - timedelta(days=14):
            logger.warning(
                f"[GFSWindProvider] NOAA GFS operational rolling archive is limited to past 14 days. "
                f"Historical query start {start_time.isoformat()} exceeds archive window."
            )
            raise TemporalCoverageError(
                f"NOAA GFS operational rolling archive is limited to past 14 days. "
                f"Historical query start {start_time.isoformat()} exceeds archive window."
            )
        elif target_mode == "forecast" and end_time < now_utc - timedelta(days=7):
            logger.warning(
                f"[GFSWindProvider] NOAA GFS operational forecast is unavailable for historical query window ending {end_time.isoformat()}."
            )
            raise TemporalCoverageError(
                f"NOAA GFS operational forecast is unavailable for historical query window ending {end_time.isoformat()}."
            )

        try:
            logger.info(f"[GFSWindProvider] Initiating live NOAA GFS download ({target_mode}) for key '{cache_key}'")

            def _download_action(tmp_path: str) -> None:
                res_deg = self.config.spatial_resolution_deg
                lat_start = np.floor(min_lat / res_deg) * res_deg
                lat_end = np.ceil(max_lat / res_deg) * res_deg
                lon_start = np.floor(min_lon / res_deg) * res_deg
                lon_end = np.ceil(max_lon / res_deg) * res_deg

                lats = np.arange(lat_start, lat_end + 1e-4, res_deg, dtype=np.float32)
                lons = np.arange(lon_start, lon_end + 1e-4, res_deg, dtype=np.float32)

                if len(lats) < 2:
                    lats = np.array([min_lat - res_deg, max_lat + res_deg], dtype=np.float32)
                if len(lons) < 2:
                    lons = np.array([min_lon - res_deg, max_lon + res_deg], dtype=np.float32)

                mesh_lats, mesh_lons = np.meshgrid(lats, lons, indexing="ij")
                flat_lats = mesh_lats.flatten()
                flat_lons = mesh_lons.flatten()

                past_h = max((now_utc - start_time).total_seconds() / 3600.0, 0.0)
                past_days = int(min(np.ceil(past_h / 24.0) + 1, 14)) if past_h > 0 else 0
                forward_h = max((end_time - now_utc).total_seconds() / 3600.0, 0.0)
                forecast_days = int(min(max(np.ceil(forward_h / 24.0) + 1, 2), 16)) if forward_h > 0 else 2

                url = self.build_query_url(flat_lats, flat_lons, forecast_days=forecast_days, past_days=past_days)

                req = urllib.request.Request(url, headers={"User-Agent": "Feature2-Environmental-Engine/2.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                locations = data if isinstance(data, list) else [data]
                if not locations or "hourly" not in locations[0]:
                    raise EnvironmentalDataUnavailableError("Invalid response payload from NOAA GFS forecast endpoint")

                time_strings = locations[0]["hourly"]["time"]
                times = pd.to_datetime(time_strings).tz_localize(None).to_numpy(dtype="datetime64[ns]")
                n_times = len(times)

                if n_times == 0:
                    raise EnvironmentalDataUnavailableError("Empty time series returned from NOAA GFS endpoint")

                # Verify actual returned timestamps against required query window (Adjustment 2)
                first_time = pd.to_datetime(times[0]).tz_localize("UTC")
                last_time = pd.to_datetime(times[-1]).tz_localize("UTC")
                if first_time > start_time + timedelta(hours=1) or last_time < end_time - timedelta(hours=1):
                    raise EnvironmentalCoverageError(
                        f"Open-Meteo GFS returned timestamps [{first_time.isoformat()} to {last_time.isoformat()}] "
                        f"do not cover the required historical window [{start_time.isoformat()} to {end_time.isoformat()}]."
                    )

                u_grid = np.full((n_times, len(lats), len(lons)), np.nan, dtype=np.float32)
                v_grid = np.full((n_times, len(lats), len(lons)), np.nan, dtype=np.float32)

                for idx, loc in enumerate(locations):
                    i = idx // len(lons)
                    j = idx % len(lons)
                    if i < len(lats) and j < len(lons):
                        u_vals = loc["hourly"]["wind_u_component_10m"]
                        v_vals = loc["hourly"]["wind_v_component_10m"]
                        u_grid[:, i, j] = u_vals
                        v_grid[:, i, j] = v_vals

                # Strict environmental data validation (Part 8 / Adjustment 2)
                if np.isnan(u_grid).any() or np.isnan(v_grid).any():
                    raise EnvironmentalDataUnavailableError("Downloaded GFS surface wind grid contains NaN or missing values.")

                ds = xr.Dataset(
                    data_vars={
                        self.config.u_var: (["time", "latitude", "longitude"], u_grid),
                        self.config.v_var: (["time", "latitude", "longitude"], v_grid),
                    },
                    coords={"time": times, "latitude": lats, "longitude": lons},
                    attrs={
                        "source": "NOAA NCEP GFS",
                        "product": "gfs_0p25",
                        "units": "m/s",
                        "mode": target_mode,
                    }
                )
                ds.to_netcdf(tmp_path)

            final_path = self.cache_manager.atomic_save(
                f"gfs_{target_mode}",
                cache_key,
                _download_action,
            )
            self._init_reader(final_path, source_type="remote_download", cache_status="miss")
            self.reader.validate_domain_coverage(window, mode=target_mode)
            return True

        except (TemporalCoverageError, EnvironmentalCoverageError):
            raise
        except Exception as err:
            logger.error(f"[GFSWindProvider] NOAA GFS operational download failed: {err}")
            raise EnvironmentalDataUnavailableError(f"NOAA GFS forecast retrieval failed: {err}") from err

    def get_wind(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> WindSample:
        """
        Retrieves interpolated 10m forecast surface wind vector (u_wind_mps, v_wind_mps) in m/s at UTC time.
        Raises OutOfDomainError or TemporalCoverageError if outside coverage.
        """
        if self.reader is None:
            raise EnvironmentalDataUnavailableError(
                "NOAA GFS forecast wind dataset is not loaded. Please provide a valid NetCDF file path via "
                "`GFS_WIND_DATA_PATH` or configure local dataset."
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
