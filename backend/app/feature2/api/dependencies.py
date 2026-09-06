"""
FastAPI dependency injection providers for Feature 2.
"""

from ..config import Feature2Settings, default_settings, validate_production_data_sources
from ..exceptions import ConfigurationError
from ..data.base import EnvironmentalDataProvider
from ..data.currents.mock import MockCurrentsProvider
from ..data.currents.local import LocalCurrentsProvider
from ..data.currents.copernicus import CopernicusCurrentsProvider, CopernicusForecastCurrentsProvider, CopernicusConfig
from ..data.currents.hycom import HYCOMCurrentsProvider
from ..data.wind.mock import MockWindProvider
from ..data.wind.local import LocalWindProvider
from ..data.wind.gfs import GFSWindProvider, GFSConfig
from ..data.wind.era5 import ERA5WindProvider, ERA5Config
from ..data.local_netcdf import VariableMapping
from ..simulation.forward.engine import ForwardSimulationEngine
from ..simulation.backward.engine import BackwardSimulationEngine
from ..origin.estimator import OriginEstimator
from ..forecast.forecaster import ForwardForecaster
from ..pipeline.service import Feature2PipelineService


def get_settings() -> Feature2Settings:
    """Returns application configuration settings."""
    return default_settings


def get_currents_provider(settings: Feature2Settings = default_settings) -> EnvironmentalDataProvider:
    """Returns configured ocean currents data provider."""
    provider_type = settings.data.currents_provider
    if provider_type == "local_netcdf" and settings.data.local_currents_filepath:
        mapping = VariableMapping(
            u_var=settings.data.currents_variable_mapping.u_var,
            v_var=settings.data.currents_variable_mapping.v_var,
            lat_var=settings.data.currents_variable_mapping.lat_var,
            lon_var=settings.data.currents_variable_mapping.lon_var,
            time_var=settings.data.currents_variable_mapping.time_var,
        )
        return LocalCurrentsProvider(
            filepath=settings.data.local_currents_filepath,
            variable_mapping=mapping
        )
    elif provider_type == "copernicus":
        copernicus_cfg = CopernicusConfig(
            dataset_id=settings.data.copernicus_historical_dataset_id,
            depth_level_m=settings.data.copernicus_depth_level_m,
            cache_dir=settings.data.data_cache_dir,
            data_path=settings.data.copernicus_data_path,
        )
        return CopernicusCurrentsProvider(
            config=copernicus_cfg,
            data_path=settings.data.copernicus_data_path,
        )
    elif provider_type == "hycom":
        return HYCOMCurrentsProvider()
    else:
        return MockCurrentsProvider()


def get_forecast_currents_provider(settings: Feature2Settings = default_settings) -> EnvironmentalDataProvider:
    """Returns configured forecast ocean currents data provider (+0 to +48h)."""
    provider_type = getattr(settings.data, "forecast_currents_provider", None) or (
        "copernicus" if settings.environment == "production" else settings.data.currents_provider
    )
    if provider_type == "copernicus":
        copernicus_cfg = CopernicusConfig(
            dataset_id=settings.data.copernicus_forecast_dataset_id,
            depth_level_m=settings.data.copernicus_depth_level_m,
            cache_dir=settings.data.data_cache_dir,
            data_path=settings.data.copernicus_data_path,
        )
        return CopernicusForecastCurrentsProvider(
            config=copernicus_cfg,
            data_path=settings.data.copernicus_data_path,
            settings=settings,
        )
    elif provider_type == "local_netcdf" and settings.data.local_currents_filepath:
        mapping = VariableMapping(
            u_var=settings.data.currents_variable_mapping.u_var,
            v_var=settings.data.currents_variable_mapping.v_var,
            lat_var=settings.data.currents_variable_mapping.lat_var,
            lon_var=settings.data.currents_variable_mapping.lon_var,
            time_var=settings.data.currents_variable_mapping.time_var,
        )
        return LocalCurrentsProvider(
            filepath=settings.data.local_currents_filepath,
            variable_mapping=mapping
        )
    elif provider_type == "mock":
        return MockCurrentsProvider()
    return get_currents_provider(settings)


def get_wind_provider(settings: Feature2Settings = default_settings) -> EnvironmentalDataProvider:
    """Returns configured surface wind data provider."""
    provider_type = settings.data.wind_provider
    if provider_type == "local_netcdf" and settings.data.local_wind_filepath:
        mapping = VariableMapping(
            u_var=settings.data.wind_variable_mapping.u_var,
            v_var=settings.data.wind_variable_mapping.v_var,
            lat_var=settings.data.wind_variable_mapping.lat_var,
            lon_var=settings.data.wind_variable_mapping.lon_var,
            time_var=settings.data.wind_variable_mapping.time_var,
        )
        return LocalWindProvider(
            filepath=settings.data.local_wind_filepath,
            variable_mapping=mapping
        )
    elif provider_type == "era5":
        era5_cfg = ERA5Config(
            data_path=settings.data.era5_data_path,
            cache_dir=settings.data.data_cache_dir,
        )
        return ERA5WindProvider(
            config=era5_cfg,
            data_path=settings.data.era5_data_path,
        )
    elif provider_type == "gfs":
        gfs_cfg = GFSConfig(
            data_path=settings.data.gfs_data_path,
            cache_dir=settings.data.data_cache_dir,
        )
        return GFSWindProvider(
            config=gfs_cfg,
            data_path=settings.data.gfs_data_path,
        )
    else:
        return MockWindProvider()


def get_forecast_wind_provider(settings: Feature2Settings = default_settings) -> EnvironmentalDataProvider:
    """Returns configured forecast surface wind data provider (+0 to +48h)."""
    provider_type = getattr(settings.data, "forecast_wind_provider", None) or (
        "gfs" if settings.environment == "production" else settings.data.wind_provider
    )
    if provider_type == "gfs":
        gfs_cfg = GFSConfig(
            data_path=settings.data.gfs_data_path,
            cache_dir=settings.data.data_cache_dir,
        )
        return GFSWindProvider(
            config=gfs_cfg,
            data_path=settings.data.gfs_data_path,
            settings=settings,
        )
    elif provider_type == "local_netcdf" and settings.data.local_wind_filepath:
        mapping = VariableMapping(
            u_var=settings.data.wind_variable_mapping.u_var,
            v_var=settings.data.wind_variable_mapping.v_var,
            lat_var=settings.data.wind_variable_mapping.lat_var,
            lon_var=settings.data.wind_variable_mapping.lon_var,
            time_var=settings.data.wind_variable_mapping.time_var,
        )
        return LocalWindProvider(
            filepath=settings.data.local_wind_filepath,
            variable_mapping=mapping
        )
    elif provider_type == "mock":
        return MockWindProvider()
    return get_wind_provider(settings)


def get_forward_simulation_engine() -> ForwardSimulationEngine:
    """Returns forward simulation engine."""
    settings = get_settings()
    return ForwardSimulationEngine(
        currents_provider=get_forecast_currents_provider(settings),
        wind_provider=get_forecast_wind_provider(settings),
        settings=settings
    )


def get_backward_simulation_engine() -> BackwardSimulationEngine:
    """Returns backward simulation engine."""
    settings = get_settings()
    return BackwardSimulationEngine(
        currents_provider=get_currents_provider(settings),
        wind_provider=get_wind_provider(settings),
        settings=settings
    )


def get_origin_estimator() -> OriginEstimator:
    """Returns origin candidate estimation engine."""
    settings = get_settings()
    return OriginEstimator(
        currents_provider=get_currents_provider(settings),
        wind_provider=get_wind_provider(settings),
        settings=settings
    )


def get_forecaster() -> ForwardForecaster:
    """Returns forecaster coordinator."""
    return ForwardForecaster(
        simulation_engine=get_forward_simulation_engine(),
        settings=get_settings()
    )


def get_pipeline_service() -> Feature2PipelineService:
    """Returns consolidated Feature 2 pipeline service."""
    settings = get_settings()
    validate_production_data_sources(settings)
    return Feature2PipelineService(
        origin_estimator=get_origin_estimator(),
        forecaster=get_forecaster(),
        settings=settings
    )
