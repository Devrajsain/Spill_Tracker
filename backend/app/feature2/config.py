"""
Configuration models and defaults for Feature 2.
Supports environment overrides, local dataset paths, variable mappings, and simulation physics parameters.
"""

import os
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field

from .exceptions import ConfigurationError
from .logging_config import logger
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class VariableMappingConfig(BaseModel):
    """Configurable NetCDF variable and coordinate names."""
    u_var: Optional[str] = Field(None, description="Variable name for U component.")
    v_var: Optional[str] = Field(None, description="Variable name for V component.")
    lat_var: Optional[str] = Field(None, description="Coordinate name for Latitude.")
    lon_var: Optional[str] = Field(None, description="Coordinate name for Longitude.")
    time_var: Optional[str] = Field(None, description="Coordinate name for Time.")


def get_configured_environment() -> str:
    """Returns runtime execution environment ('development', 'testing', 'production')."""
    return os.getenv("FEATURE2_ENVIRONMENT", "development").strip().lower()


class DataSourceConfig(BaseModel):
    """Configuration for environmental data sources (ocean currents and wind)."""
    currents_provider: Literal["mock", "local_netcdf", "hycom", "copernicus", "incois"] = Field(
        default_factory=lambda: "copernicus" if get_configured_environment() == "production" else os.getenv("FEATURE2_CURRENTS_PROVIDER", "mock"),
        description="Provider identifier for historical ocean current vector fields (u, v)."
    )
    wind_provider: Literal["mock", "local_netcdf", "gfs", "era5", "incois_wind"] = Field(
        default_factory=lambda: "era5" if get_configured_environment() == "production" else os.getenv("FEATURE2_WIND_PROVIDER", "mock"),
        description="Provider identifier for historical surface wind vector fields (u10, v10)."
    )
    forecast_currents_provider: Literal["mock", "local_netcdf", "copernicus"] = Field(
        default_factory=lambda: "copernicus" if get_configured_environment() == "production" else os.getenv("FEATURE2_FORECAST_CURRENTS_PROVIDER", "mock"),
        description="Provider identifier for operational forecast ocean currents (+0 to +48h)."
    )
    forecast_wind_provider: Literal["mock", "local_netcdf", "gfs"] = Field(
        default_factory=lambda: "gfs" if get_configured_environment() == "production" else os.getenv("FEATURE2_FORECAST_WIND_PROVIDER", "mock"),
        description="Provider identifier for operational forecast surface wind (+0 to +48h)."
    )
    local_currents_filepath: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for ocean currents when currents_provider is 'local_netcdf'."
    )
    local_wind_filepath: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for surface wind when wind_provider is 'local_netcdf'."
    )
    era5_data_path: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for ERA5 surface wind. Can also be set via ERA5_WIND_DATA_PATH env var."
    )
    copernicus_data_path: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for Copernicus currents. Can also be set via COPERNICUS_CURRENTS_DATA_PATH env var."
    )
    gfs_data_path: Optional[str] = Field(
        default=None,
        description="Path to local NetCDF file for GFS forecast wind. Can also be set via GFS_WIND_DATA_PATH env var."
    )
    copernicus_historical_dataset_id: str = Field(
        default="cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
        description="Copernicus Marine dataset ID for ocean analysis & forecast currents."
    )
    copernicus_forecast_dataset_id: str = Field(
        default="cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
        description="Copernicus Marine dataset ID for operational forecast currents."
    )
    copernicus_depth_level_m: float = Field(
        default=0.494,
        ge=0.0,
        description="Surface layer depth selection in meters for 2D horizontal transport."
    )
    enable_live_downloads: bool = Field(
        default=False,
        description="Whether to attempt live remote authenticated downloads when local data is absent."
    )
    currents_variable_mapping: VariableMappingConfig = Field(
        default_factory=VariableMappingConfig,
        description="Custom variable name mappings for local ocean currents NetCDF file."
    )
    wind_variable_mapping: VariableMappingConfig = Field(
        default_factory=VariableMappingConfig,
        description="Custom variable name mappings for local surface wind NetCDF file."
    )
    spatial_interpolation: Literal["bilinear"] = Field(
        default="bilinear",
        description="Spatial interpolation algorithm."
    )
    temporal_interpolation: Literal["linear"] = Field(
        default="linear",
        description="Temporal interpolation algorithm."
    )
    data_cache_dir: str = Field(
        default="./data_cache",
        description="Local directory path used for caching environmental datasets."
    )
    environmental_buffer_km: float = Field(
        default=50.0,
        ge=0.0,
        le=500.0,
        description="Spatial buffer padding in km applied to the Sentinel-1 footprint for environmental data querying."
    )
    timeout_seconds: int = Field(
        default=30,
        description="HTTP or service timeout for remote data fetching."
    )
    cache_ttl_hours: int = Field(
        default=24,
        description="Cache time-to-live for ingested meteorological / hydrodynamic grids."
    )
    cache_ttl_forecast_seconds: Optional[float] = Field(
        default=21600.0,
        ge=0.0,
        description="Deterministic cache TTL in seconds for operational forecast data (default 6h)."
    )
    cache_ttl_historical_seconds: Optional[float] = Field(
        default=None,
        description="Deterministic cache TTL in seconds for historical reanalysis data (None = indefinite)."
    )
    allow_production_replay_fixture: bool = Field(
        default=False,
        description="Explicit flag permitting local historical replay fixtures in non-standard evaluations."
    )


class WindageConfig(BaseModel):
    """Windage / leeway parameters for surface slick advection."""
    leeway_factor: float = Field(
        default=0.03,
        ge=0.0,
        le=0.10,
        description="Fraction of wind speed transferred to surface slick (typically 0.02 - 0.04)."
    )
    deflection_angle_deg: float = Field(
        default=0.0,
        ge=-45.0,
        le=45.0,
        description="Coriolis wind deflection angle relative to downwind direction in degrees."
    )


class DiffusionConfig(BaseModel):
    """Horizontal turbulent diffusion parameters for stochastic particle spreading."""
    horizontal_diffusivity_m2_s: float = Field(
        default=10.0,
        ge=0.0,
        le=1000.0,
        description="Horizontal diffusion coefficient Kh in m^2/s for random walk dispersion."
    )
    enable_stochastic_diffusion: bool = Field(
        default=True,
        description="Whether to apply stochastic Brownian motion / random walk increments."
    )
    ensemble_size: int = Field(
        default=1,
        ge=1,
        le=1000,
        description="Number of independent stochastic ensemble realizations."
    )
    random_seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducible stochastic diffusion."
    )

    @property
    def diffusion_coefficient_m2_s(self) -> float:
        return self.horizontal_diffusivity_m2_s

    @property
    def diffusion_enabled(self) -> bool:
        return self.enable_stochastic_diffusion

    @classmethod
    def from_params(
        cls,
        diffusion_enabled: Optional[bool] = None,
        diffusion_coefficient_m2_s: Optional[float] = None,
        ensemble_size: Optional[int] = None,
        random_seed: Optional[int] = None,
    ) -> "DiffusionConfig":
        return cls(
            horizontal_diffusivity_m2_s=diffusion_coefficient_m2_s if diffusion_coefficient_m2_s is not None else 10.0,
            enable_stochastic_diffusion=diffusion_enabled if diffusion_enabled is not None else True,
            ensemble_size=ensemble_size if ensemble_size is not None else 1,
            random_seed=random_seed
        )


class BackwardTracingConfig(BaseModel):
    """Configuration for inverse / backward origin reconstruction."""
    max_backtrack_hours: float = Field(
        default=72.0,
        gt=0.0,
        le=168.0,
        description="Maximum historical window in hours to search backward from observation time T0."
    )
    candidate_time_step_hours: float = Field(
        default=3.0,
        gt=0.0,
        le=24.0,
        description="Interval between discrete candidate release timestamps tested in the search window."
    )
    particles_per_slick: int = Field(
        default=100,
        ge=10,
        le=10000,
        description="Number of discrete Lagrangian particles seeded over the observed SAR slick polygon."
    )
    simulation_step_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Numerical integration time step dt in seconds (e.g. 600s = 10 min)."
    )
    convergence_cluster_eps_km: float = Field(
        default=2.0,
        gt=0.0,
        description="DBSCAN or spatial clustering epsilon in km for identifying dense candidate origin regions."
    )
    min_cluster_samples: int = Field(
        default=5,
        ge=2,
        description="Minimum particle density to register a candidate origin cluster."
    )
    weight_convergence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Weight assigned to spatial compactness/convergence in candidate scoring."
    )
    weight_trajectory: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Weight assigned to trajectory continuity in candidate scoring."
    )
    weight_coverage: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Weight assigned to environmental data coverage in candidate scoring."
    )
    convergence_scale_km: float = Field(
        default=5.0,
        gt=0.0,
        description="Normalization scale in km for the convergence score S_conv = 1 / (1 + spread / scale)."
    )
    relative_score_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Relative score fraction of the best candidate to define the plausible release window."
    )
    merge_radius_km: float = Field(
        default=0.5,
        ge=0.0,
        description="Maximum spatial distance in km to merge duplicate candidates across similar release times."
    )
    merge_time_hours: float = Field(
        default=0.5,
        ge=0.0,
        description="Maximum temporal interval in hours to merge duplicate candidates."
    )


class ForecastConfig(BaseModel):
    """Configuration for forward slick trajectory forecasting."""
    forecast_horizons_hours: List[float] = Field(
        default=[6.0, 12.0, 24.0, 48.0],
        description="Target forecast lead times relative to observation time T0."
    )
    particles_per_slick: int = Field(
        default=100,
        ge=10,
        le=10000,
        description="Number of particles seeded for forward Lagrangian advection."
    )
    simulation_step_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Forward simulation integration time step dt in seconds."
    )
    forecast_buffer_km: float = Field(
        default=60.0,
        gt=0.0,
        description="Spatial safety buffer in km for dynamic forecast environmental domain."
    )
    forecast_ensemble_size: int = Field(
        default=1,
        ge=1,
        description="Number of stochastic ensemble realizations for forward uncertainty."
    )
    minimum_active_fraction: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum active particle fraction required for a forecast horizon to be valid."
    )
    quality_threshold_high: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Active particle fraction threshold for high quality rating."
    )
    quality_threshold_medium: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Active particle fraction threshold for medium quality rating."
    )


class Feature2Settings(BaseModel):
    """Master configuration for Feature 2 module."""
    environment: str = Field(
        default="development",
        description="Execution environment ('development', 'testing', 'production')."
    )
    random_seed: Optional[int] = Field(
        default=42,
        description="Random seed for deterministic, reproducible simulation runs in tests/evals."
    )
    data: DataSourceConfig = Field(default_factory=DataSourceConfig)
    windage: WindageConfig = Field(default_factory=WindageConfig)
    diffusion: DiffusionConfig = Field(default_factory=DiffusionConfig)
    backward: BackwardTracingConfig = Field(default_factory=BackwardTracingConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    log_level: str = Field(default="INFO", description="Logging level.")

    def model_post_init(self, __context: Any) -> None:
        """If environment is production and data was not explicitly overridden, upgrade default mock providers to real production providers."""
        if self.environment == "production":
            if "data" not in self.model_fields_set:
                self.data.currents_provider = "copernicus"
                self.data.wind_provider = "era5"
                self.data.forecast_currents_provider = "copernicus"
                self.data.forecast_wind_provider = "gfs"
            else:
                if "currents_provider" not in self.data.model_fields_set and self.data.currents_provider == "mock":
                    self.data.currents_provider = "copernicus"
                if "wind_provider" not in self.data.model_fields_set and self.data.wind_provider == "mock":
                    self.data.wind_provider = "era5"
                if "forecast_currents_provider" not in self.data.model_fields_set and self.data.forecast_currents_provider == "mock":
                    self.data.forecast_currents_provider = "copernicus"
                if "forecast_wind_provider" not in self.data.model_fields_set and self.data.forecast_wind_provider == "mock":
                    self.data.forecast_wind_provider = "gfs"

    @classmethod
    def production(cls, **kwargs: Any) -> "Feature2Settings":
        """Factory for production settings with ERA5, Copernicus, and GFS providers."""
        data = kwargs.pop("data", None)
        if data is None:
            data = DataSourceConfig(
                currents_provider="copernicus",
                wind_provider="era5",
                forecast_currents_provider="copernicus",
                forecast_wind_provider="gfs",
            )
        else:
            if data.currents_provider == "mock" and "currents_provider" not in data.model_fields_set:
                data.currents_provider = "copernicus"
            if data.wind_provider == "mock" and "wind_provider" not in data.model_fields_set:
                data.wind_provider = "era5"
            if data.forecast_currents_provider == "mock" and "forecast_currents_provider" not in data.model_fields_set:
                data.forecast_currents_provider = "copernicus"
            if data.forecast_wind_provider == "mock" and "forecast_wind_provider" not in data.model_fields_set:
                data.forecast_wind_provider = "gfs"
        return cls(environment="production", data=data, **kwargs)

    @classmethod
    def testing(cls, **kwargs: Any) -> "Feature2Settings":
        """Factory for offline test settings with mock or synthetic providers."""
        return cls(environment="testing", **kwargs)

    def get_reproducibility_hash(self) -> str:
        """
        Computes a deterministic, reproducible SHA-256 configuration hash.
        Includes only physics, numerical, and ensemble configuration parameters.
        Excludes execution environment, paths, timestamps, secrets, and credentials.
        """
        import hashlib
        import json
        payload = {
            "random_seed": self.random_seed,
            "windage": {
                "leeway_factor": self.windage.leeway_factor,
                "deflection_angle_deg": self.windage.deflection_angle_deg,
            },
            "diffusion": {
                "enable": self.diffusion.enable_stochastic_diffusion,
                "diffusivity_m2_s": self.diffusion.horizontal_diffusivity_m2_s,
            },
            "backward": {
                "max_backtrack_hours": self.backward.max_backtrack_hours,
                "candidate_time_step_hours": self.backward.candidate_time_step_hours,
                "particles_per_slick": self.backward.particles_per_slick,
                "simulation_step_seconds": self.backward.simulation_step_seconds,
            },
            "forecast": {
                "forecast_horizons_hours": self.forecast.forecast_horizons_hours,
                "particles_per_slick": self.forecast.particles_per_slick,
                "forecast_ensemble_size": self.forecast.forecast_ensemble_size,
                "simulation_step_seconds": self.forecast.simulation_step_seconds,
            }
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()[:16]


# Global default settings instance anchored to configured environment
default_settings = Feature2Settings(environment=get_configured_environment())


def validate_production_data_sources(settings: Feature2Settings) -> None:
    """
    Strictly validates that production environment uses genuine real providers
    (ERA5, Copernicus Marine, NOAA GFS) and does not utilize mock or local fixtures.
    Verifies required production credentials exist in the environment.

    Raises:
        ConfigurationError: if mock providers, unauthorized fixtures, or missing credentials are detected.
    """
    if settings.environment != "production":
        return

    data = settings.data

    # 1. Historical Wind
    if data.wind_provider == "mock":
        raise ConfigurationError("Production mode strictly forbids mock wind provider. Historical wind must be 'era5'.")
    if data.wind_provider != "era5":
        raise ConfigurationError(f"Unsupported historical wind provider '{data.wind_provider}' in production mode. Must be 'era5'.")

    # 2. Historical Currents
    if data.currents_provider == "mock":
        raise ConfigurationError("Production mode strictly forbids mock currents provider. Historical currents must be 'copernicus'.")
    if data.currents_provider != "copernicus":
        raise ConfigurationError(f"Unsupported historical currents provider '{data.currents_provider}' in production mode. Must be 'copernicus'.")

    # 3. Forecast Wind
    if data.forecast_wind_provider == "mock":
        raise ConfigurationError("Production mode strictly forbids mock forecast wind provider. Forecast wind must be 'gfs'.")
    if data.forecast_wind_provider != "gfs":
        raise ConfigurationError(f"Unsupported forecast wind provider '{data.forecast_wind_provider}' in production mode. Must be 'gfs'.")

    # 4. Forecast Currents
    if data.forecast_currents_provider == "mock":
        raise ConfigurationError("Production mode strictly forbids mock forecast currents provider. Forecast currents must be 'copernicus'.")
    if data.forecast_currents_provider != "copernicus":
        raise ConfigurationError(f"Unsupported forecast currents provider '{data.forecast_currents_provider}' in production mode. Must be 'copernicus'.")

    # 5. Local Fixtures check
    if not data.allow_production_replay_fixture:
        if data.local_currents_filepath or data.local_wind_filepath:
            raise ConfigurationError(
                "Production mode strictly forbids local fixture filepaths (local_currents_filepath, local_wind_filepath)."
            )
        if data.era5_data_path or data.copernicus_data_path or data.gfs_data_path:
            raise ConfigurationError(
                "Production mode strictly forbids local fixture data paths (era5_data_path, copernicus_data_path, gfs_data_path) "
                "unless explicitly running with allow_production_replay_fixture=True."
            )
    else:
        logger.warning(
            "NON-STANDARD PRODUCTION MODE: allow_production_replay_fixture=True. "
            "Running in explicit historical replay/evaluation mode, NOT live operational production."
        )

    # 6. Credentials check (required for live production, bypassed only in explicit local replay fixture mode)
    if not data.allow_production_replay_fixture:
        cmems_user = os.getenv("CMEMS_USERNAME")
        cmems_pass = os.getenv("CMEMS_PASSWORD")
        cds_key = os.getenv("CDSAPI_KEY")

        if not cmems_user or not cmems_pass:
            raise ConfigurationError("Production mode requires CMEMS credentials (CMEMS_USERNAME, CMEMS_PASSWORD) in environment.")
        if not cds_key:
            raise ConfigurationError("Production mode requires Copernicus CDS API key (CDSAPI_KEY) in environment.")


def get_provider_summary(settings: Feature2Settings) -> dict:
    """
    Returns a concise, safe summary of configured environmental providers without exposing secrets.
    """
    return {
        "environment": settings.environment,
        "historical_wind": settings.data.wind_provider,
        "historical_currents": settings.data.currents_provider,
        "forecast_wind": settings.data.forecast_wind_provider,
        "forecast_currents": settings.data.forecast_currents_provider,
        "cache_dir": settings.data.data_cache_dir,
        "allow_production_replay_fixture": settings.data.allow_production_replay_fixture,
    }
