"""
Local NetCDF dataset reader and 4D/3D bilinear-temporal interpolation engine.
Reads and validates NetCDF oceanographic and meteorological gridded files,
handling coordinate conversions ([-180, 180] vs [0, 360]), latitude direction (ascending/descending),
and strict UTC time interpolation.
"""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import numpy as np
import xarray as xr
from pydantic import BaseModel, Field

from ..exceptions import (
    EnvironmentalCoverageError,
    EnvironmentalDataUnavailableError,
    InvalidDatasetError,
    OutOfDomainError,
    TemporalCoverageError,
)
from ..logging_config import logger
from .coord_utils import (
    detect_longitude_convention,
    find_grid_bounding_indices,
    normalize_longitude,
)
from .time_utils import datetime_to_seconds, normalize_to_utc, seconds_to_datetime


class VariableMapping(BaseModel):
    """Configurable variable and coordinate name mappings for NetCDF datasets."""
    u_var: Optional[str] = Field(None, description="Variable name for U velocity component.")
    v_var: Optional[str] = Field(None, description="Variable name for V velocity component.")
    lat_var: Optional[str] = Field(None, description="Coordinate name for Latitude.")
    lon_var: Optional[str] = Field(None, description="Coordinate name for Longitude.")
    time_var: Optional[str] = Field(None, description="Coordinate name for Time.")


# Common aliases for autodetection when explicit mapping is not specified
U_CANDIDATES = ["u", "eastward_current", "uo", "water_u", "u10", "10m_u_component", "u_wind", "10u", "var131"]
V_CANDIDATES = ["v", "northward_current", "vo", "water_v", "v10", "10m_v_component", "v_wind", "10v", "var132"]
LAT_CANDIDATES = ["latitude", "lat", "nav_lat", "y", "LATITUDE", "Lat"]
LON_CANDIDATES = ["longitude", "lon", "nav_lon", "x", "LONGITUDE", "Lon"]
TIME_CANDIDATES = ["time", "valid_time", "datetime", "t", "TIME", "Time"]


class LocalNetCDFDatasetReader:
    """
    Robust NetCDF dataset reader for hydrodynamic currents and surface winds.
    Provides in-memory caching of coordinates and fast bilinear/temporal interpolation.
    """

    def __init__(
        self,
        filepath: str,
        variable_mapping: Optional[VariableMapping] = None,
        field_type: Literal["ocean_currents", "surface_wind"] = "ocean_currents",
    ):
        self.filepath = filepath
        self.mapping = variable_mapping or VariableMapping()
        self.field_type = field_type

        # Internal state
        self._dataset: Optional[xr.Dataset] = None
        self._is_open: bool = False
        self._cached_arrays: Dict[str, np.ndarray] = {}

        # Resolved variable and coordinate names
        self.resolved_u_var: str = ""
        self.resolved_v_var: str = ""
        self.resolved_lat_var: str = ""
        self.resolved_lon_var: str = ""
        self.resolved_time_var: str = ""

        # Cached coordinate arrays and metadata
        self.lats: np.ndarray = np.array([])
        self.lons: np.ndarray = np.array([])
        self.time_seconds: np.ndarray = np.array([])
        self.time_datetimes: List[datetime] = []
        self.lon_convention: Literal["[-180, 180]", "[0, 360]"] = "[-180, 180]"

        # Bounds
        self.min_lat: float = 0.0
        self.max_lat: float = 0.0
        self.min_lon: float = 0.0
        self.max_lon: float = 0.0
        self.min_time: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self.max_time: datetime = datetime.max.replace(tzinfo=timezone.utc)

    @property
    def dataset(self) -> Optional[xr.Dataset]:
        """Underlying open xarray Dataset."""
        return self._dataset


    def __enter__(self):
        self.open_dataset()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_dataset()

    def open_dataset(self) -> None:
        """Opens and validates the NetCDF dataset, populating in-memory grid metadata."""
        if self._is_open and self._dataset is not None:
            return

        if not os.path.exists(self.filepath):
            raise EnvironmentalDataUnavailableError(
                f"NetCDF dataset file not found at path: '{self.filepath}'"
            )

        try:
            # Open dataset via xarray with decode_times enabled
            self._dataset = xr.open_dataset(self.filepath)
        except Exception as e:
            raise InvalidDatasetError(
                f"Failed to open NetCDF file '{self.filepath}': {str(e)}"
            ) from e

        self.validate_dataset()
        self._is_open = True
        logger.info(
            f"Successfully loaded NetCDF dataset '{os.path.basename(self.filepath)}' "
            f"covering lat[{self.min_lat:.2f}, {self.max_lat:.2f}], "
            f"lon[{self.min_lon:.2f}, {self.max_lon:.2f}], "
            f"time[{self.min_time.isoformat()} to {self.max_time.isoformat()}]"
        )

    def close_dataset(self) -> None:
        """Closes open dataset file handle and releases resources."""
        if self._dataset is not None:
            try:
                self._dataset.close()
            except Exception:
                pass
            self._dataset = None
        self._is_open = False

    def validate_dataset(self) -> None:
        """
        Validates presence of required variables, coordinates, numeric continuity,
        and temporal integrity.
        """
        if self._dataset is None:
            raise InvalidDatasetError("Dataset is not open.")

        ds = self._dataset

        # 1. Resolve coordinates
        self.resolved_lat_var = self._find_name(
            configured=self.mapping.lat_var,
            candidates=LAT_CANDIDATES,
            available=list(ds.coords.keys()) + list(ds.data_vars.keys()),
            var_desc="latitude coordinate"
        )
        self.resolved_lon_var = self._find_name(
            configured=self.mapping.lon_var,
            candidates=LON_CANDIDATES,
            available=list(ds.coords.keys()) + list(ds.data_vars.keys()),
            var_desc="longitude coordinate"
        )
        self.resolved_time_var = self._find_name(
            configured=self.mapping.time_var,
            candidates=TIME_CANDIDATES,
            available=list(ds.coords.keys()) + list(ds.data_vars.keys()),
            var_desc="time coordinate"
        )

        # 2. Resolve data variables
        self.resolved_u_var = self._find_name(
            configured=self.mapping.u_var,
            candidates=U_CANDIDATES,
            available=list(ds.data_vars.keys()) + list(ds.coords.keys()),
            var_desc="U-component velocity variable"
        )
        self.resolved_v_var = self._find_name(
            configured=self.mapping.v_var,
            candidates=V_CANDIDATES,
            available=list(ds.data_vars.keys()) + list(ds.coords.keys()),
            var_desc="V-component velocity variable"
        )

        # 3. Extract and validate Latitude
        lat_arr = np.asarray(ds[self.resolved_lat_var].values, dtype=float)
        if lat_arr.ndim != 1:
            # Handle 2D meshgrid if flat coordinates
            if lat_arr.ndim == 2 and (lat_arr[:, 0] == lat_arr[:, -1]).all():
                lat_arr = lat_arr[:, 0]
            else:
                raise InvalidDatasetError(
                    f"Latitude coordinate '{self.resolved_lat_var}' has unsupported dimension {lat_arr.ndim} (expected 1D)."
                )
        if len(lat_arr) < 2:
            raise InvalidDatasetError(f"Latitude coordinate has fewer than 2 points ({len(lat_arr)}).")
        if np.isnan(lat_arr).any():
            raise InvalidDatasetError(f"Latitude coordinate contains NaN values.")
        self.lats = lat_arr
        self.min_lat = float(min(lat_arr[0], lat_arr[-1]))
        self.max_lat = float(max(lat_arr[0], lat_arr[-1]))

        # 4. Extract and validate Longitude
        lon_arr = np.asarray(ds[self.resolved_lon_var].values, dtype=float)
        if lon_arr.ndim != 1:
            if lon_arr.ndim == 2 and (lon_arr[0, :] == lon_arr[-1, :]).all():
                lon_arr = lon_arr[0, :]
            else:
                raise InvalidDatasetError(
                    f"Longitude coordinate '{self.resolved_lon_var}' has unsupported dimension {lon_arr.ndim} (expected 1D)."
                )
        if len(lon_arr) < 2:
            raise InvalidDatasetError(f"Longitude coordinate has fewer than 2 points ({len(lon_arr)}).")
        if np.isnan(lon_arr).any():
            raise InvalidDatasetError(f"Longitude coordinate contains NaN values.")
        self.lons = lon_arr
        self.lon_convention = detect_longitude_convention(self.lons)
        self.min_lon = float(min(lon_arr[0], lon_arr[-1]))
        self.max_lon = float(max(lon_arr[0], lon_arr[-1]))

        # 5. Extract and validate Time
        raw_times = ds[self.resolved_time_var].values
        if len(raw_times) < 1:
            raise InvalidDatasetError(f"Time coordinate '{self.resolved_time_var}' is empty.")

        parsed_times: List[datetime] = []
        for t_val in raw_times:
            try:
                utc_dt = normalize_to_utc(t_val)
                parsed_times.append(utc_dt)
            except Exception as e:
                raise InvalidDatasetError(
                    f"Failed to parse time coordinate value '{t_val}' into UTC datetime: {str(e)}"
                ) from e

        self.time_datetimes = parsed_times
        self.time_seconds = np.array([datetime_to_seconds(dt) for dt in parsed_times])
        self.min_time = self.time_datetimes[0]
        self.max_time = self.time_datetimes[-1]

        # 6. Validate U and V variables
        u_da = ds[self.resolved_u_var]
        v_da = ds[self.resolved_v_var]
        if u_da.shape != v_da.shape:
            raise InvalidDatasetError(
                f"U variable '{self.resolved_u_var}' shape {u_da.shape} does not match "
                f"V variable '{self.resolved_v_var}' shape {v_da.shape}."
            )

        # 7. Validate units metadata if available
        for var_name in [self.resolved_u_var, self.resolved_v_var]:
            da = ds[var_name]
            unit = str(da.attrs.get("units", "")).strip().lower()
            if unit:
                valid_velocity_units = {"m/s", "m s-1", "m*s-1", "m.s-1", "meters/second", "meter/sec", "mps"}
                if unit not in valid_velocity_units and not any(vu in unit for vu in ["m/s", "m s-1", "mps"]):
                    logger.warning(
                        f"[LocalNetCDF] Variable '{var_name}' metadata unit is '{unit}'. "
                        "Expected SI velocity (m/s)."
                    )

        # 8. Cache in-memory numpy array slices for ultra-fast interpolation
        self._cached_arrays = {}
        for var_name in [self.resolved_u_var, self.resolved_v_var]:
            self._cached_arrays[var_name] = self._extract_surface_slice(ds[var_name])

    def _extract_surface_slice(self, da: xr.DataArray) -> np.ndarray:
        """
        Extracts 3D (time, lat, lon) or 2D (lat, lon) surface array from DataArray,
        identifying depth dimension by semantic name rather than positional indexing.
        """
        if da.ndim in (2, 3):
            return np.asarray(da.values, dtype=float)

        if da.ndim == 4:
            known_depth_dims = ["depth", "depth_level", "lev", "level", "z", "deptht", "nz"]
            depth_dim = None
            for d in da.dims:
                if str(d).lower() in known_depth_dims:
                    depth_dim = d
                    break

            if depth_dim is None:
                spatial_temporal_dims = {
                    str(self.resolved_time_var).lower(),
                    str(self.resolved_lat_var).lower(),
                    str(self.resolved_lon_var).lower(),
                }
                for d in da.dims:
                    if str(d).lower() not in spatial_temporal_dims:
                        depth_dim = d
                        break

            if depth_dim is not None:
                return np.asarray(da.isel({depth_dim: 0}).values, dtype=float)
            else:
                return np.asarray(da.isel({da.dims[1]: 0}).values, dtype=float)

        raise InvalidDatasetError(f"Unsupported array dimension {da.ndim} for variable '{da.name}'.")

    def _find_name(
        self,
        configured: Optional[str],
        candidates: List[str],
        available: List[str],
        var_desc: str
    ) -> str:
        """Finds matching variable name from configured preference or candidate aliases."""
        if configured:
            if configured in available:
                return configured
            raise InvalidDatasetError(
                f"Configured {var_desc} '{configured}' not found in dataset variables: {available}"
            )

        for cand in candidates:
            if cand in available:
                return cand

        raise InvalidDatasetError(
            f"Could not identify {var_desc} in dataset variables: {available}. "
            f"Please specify an explicit variable mapping."
        )

    def validate_domain_coverage(
        self,
        domain: Any,
        mode: str = "historical",
        strict_buffer: bool = False
    ) -> None:
        """
        Validates that the open dataset fully covers the requested EnvironmentalQueryDomain
        spatially and temporally. Raises EnvironmentalCoverageError if not covered.
        """
        if not self._is_open or self._dataset is None:
            self.open_dataset()

        if hasattr(domain, "validate_spatial_coverage") and hasattr(domain, "validate_temporal_coverage"):
            domain.validate_spatial_coverage(
                dataset_min_lat=self.min_lat,
                dataset_max_lat=self.max_lat,
                dataset_min_lon=self.min_lon,
                dataset_max_lon=self.max_lon,
                strict_buffer=strict_buffer
            )
            domain.validate_temporal_coverage(
                dataset_min_time=self.min_time,
                dataset_max_time=self.max_time,
                mode=mode
            )
        else:
            from .domain import extract_query_bounds
            q_min_lat, q_max_lat, q_min_lon, q_max_lon, q_start_time, q_end_time = extract_query_bounds(domain, mode=mode)
            tol = 0.085  # Grid node discretization tolerance (1 cell for CMEMS/ERA5)
            if self.min_lat > q_min_lat + tol or self.max_lat < q_max_lat - tol or self.min_lon > q_min_lon + tol or self.max_lon < q_max_lon - tol:
                raise EnvironmentalCoverageError(
                    f"Dataset spatial bounds lat[{self.min_lat:.2f}, {self.max_lat:.2f}], lon[{self.min_lon:.2f}, {self.max_lon:.2f}] "
                    f"do not cover query window lat[{q_min_lat:.2f}, {q_max_lat:.2f}], lon[{q_min_lon:.2f}, {q_max_lon:.2f}]"
                )
            tol_sec = 86400.0  # 1-day discretization tolerance for daily-mean products
            if self.min_time.timestamp() > q_start_time.timestamp() + tol_sec or self.max_time.timestamp() < q_end_time.timestamp() - tol_sec:
                raise EnvironmentalCoverageError(
                    f"Dataset temporal bounds [{self.min_time.isoformat()}, {self.max_time.isoformat()}] "
                    f"do not cover query window [{q_start_time.isoformat()}, {q_end_time.isoformat()}]"
                )

    def interpolate(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> Tuple[float, float]:
        """
        Performs spatial bilinear interpolation and temporal linear interpolation
        for the given (latitude, longitude, timestamp).
        
        Returns:
            Tuple of (u_mps, v_mps).
            
        Raises:
            OutOfDomainError: if coordinates are outside spatial bounds.
            TemporalCoverageError: if timestamp is outside temporal bounds.
            EnvironmentalDataUnavailableError: if dataset is closed.
        """
        if not self._is_open or self._dataset is None:
            self.open_dataset()

        # 1. Normalize timestamp to UTC
        query_time = normalize_to_utc(timestamp)
        query_sec = datetime_to_seconds(query_time)

        # 2. Check temporal coverage
        min_sec = self.time_seconds[0]
        max_sec = self.time_seconds[-1]
        tol_sec = 1.0  # 1-second floating point tolerance

        if query_sec < min_sec - tol_sec or query_sec > max_sec + tol_sec:
            raise TemporalCoverageError(
                f"Query timestamp '{query_time.isoformat()}' is outside dataset temporal coverage: "
                f"[{self.min_time.isoformat()}, {self.max_time.isoformat()}]."
            )

        # 3. Normalize query longitude to dataset convention
        norm_lon = normalize_longitude(longitude, convention=self.lon_convention)

        # 4. Check spatial bounds
        tol_deg = 1e-6
        if (latitude < self.min_lat - tol_deg or latitude > self.max_lat + tol_deg or
                norm_lon < self.min_lon - tol_deg or norm_lon > self.max_lon + tol_deg):
            raise OutOfDomainError(
                f"Query coordinates (lat={latitude:.4f}, lon={longitude:.4f} -> normalized {norm_lon:.4f}) "
                f"are outside dataset spatial domain: lat[{self.min_lat:.4f}, {self.max_lat:.4f}], "
                f"lon[{self.min_lon:.4f}, {self.max_lon:.4f}]."
            )

        # 5. Spatial bounding indices
        lat_i0, lat_i1, t_lat = find_grid_bounding_indices(self.lats, latitude)
        lon_j0, lon_j1, t_lon = find_grid_bounding_indices(self.lons, norm_lon)

        # 6. Temporal bounding indices
        if len(self.time_seconds) == 1 or abs(min_sec - max_sec) < 1e-3:
            # Single timestamp in dataset
            t_k0, t_k1, w_time = 0, 0, 0.0
        else:
            t_k0, t_k1, w_time = find_grid_bounding_indices(self.time_seconds, query_sec)

        # 7. Extract data slices and perform 2D bilinear interpolation at t_k0 and t_k1
        u_val_k0 = self._bilinear_2d(self.resolved_u_var, t_k0, lat_i0, lat_i1, lon_j0, lon_j1, t_lat, t_lon)
        v_val_k0 = self._bilinear_2d(self.resolved_v_var, t_k0, lat_i0, lat_i1, lon_j0, lon_j1, t_lat, t_lon)

        if t_k0 == t_k1 or w_time == 0.0:
            u_final = u_val_k0
            v_final = v_val_k0
        else:
            u_val_k1 = self._bilinear_2d(self.resolved_u_var, t_k1, lat_i0, lat_i1, lon_j0, lon_j1, t_lat, t_lon)
            v_val_k1 = self._bilinear_2d(self.resolved_v_var, t_k1, lat_i0, lat_i1, lon_j0, lon_j1, t_lat, t_lon)
            # Linear temporal blending
            u_final = (1.0 - w_time) * u_val_k0 + w_time * u_val_k1
            v_final = (1.0 - w_time) * v_val_k0 + w_time * v_val_k1

        return float(u_final), float(v_final)

    def _bilinear_2d(
        self,
        var_name: str,
        t_idx: int,
        lat_i0: int,
        lat_i1: int,
        lon_j0: int,
        lon_j1: int,
        t_lat: float,
        t_lon: float
    ) -> float:
        """Extracts 4 grid corner values and evaluates 2D bilinear interpolation."""
        arr = self._cached_arrays.get(var_name)
        if arr is None:
            # Fallback if accessed before validate_dataset
            da = self._dataset[var_name]
            arr = self._extract_surface_slice(da)
            self._cached_arrays[var_name] = arr

        if arr.ndim == 3:
            v00 = float(arr[t_idx, lat_i0, lon_j0])
            v10 = float(arr[t_idx, lat_i1, lon_j0])
            v01 = float(arr[t_idx, lat_i0, lon_j1])
            v11 = float(arr[t_idx, lat_i1, lon_j1])
        elif arr.ndim == 2:
            v00 = float(arr[lat_i0, lon_j0])
            v10 = float(arr[lat_i1, lon_j0])
            v01 = float(arr[lat_i0, lon_j1])
            v11 = float(arr[lat_i1, lon_j1])
        else:
            raise InvalidDatasetError(f"Unsupported array dimension {arr.ndim} for variable '{var_name}'.")

        # Standard bilinear formulation
        interpolated = (
            (1.0 - t_lat) * (1.0 - t_lon) * v00 +
            t_lat * (1.0 - t_lon) * v10 +
            (1.0 - t_lat) * t_lon * v01 +
            t_lat * t_lon * v11
        )
        return float(interpolated)
