"""
Environmental Data Layer Contracts and Abstract Interfaces.
Defines data structures for ocean currents and surface wind samples in SI units (m/s, degrees, UTC),
and establishes separate provider hierarchies for historical reanalysis vs future forecast data.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import NamedTuple, Optional, Union
from pydantic import BaseModel, Field
from ..schemas.simulation_schema import EnvironmentalQueryWindow
from .time_utils import normalize_to_utc


class VectorFieldSample(BaseModel):
    """
    Generic vector field velocity sample (backward-compatible).
    """
    u: float = Field(..., description="Eastward velocity component in m/s.")
    v: float = Field(..., description="Northward velocity component in m/s.")
    valid_time: datetime = Field(..., description="Timezone-aware UTC timestamp.")
    latitude: float = Field(default=0.0, description="Sample latitude in decimal degrees.")
    longitude: float = Field(default=0.0, description="Sample longitude in decimal degrees.")
    quality_flag: int = Field(default=1, description="Data quality flag (1=valid).")

    @property
    def u_current_mps(self) -> float:
        return self.u

    @property
    def v_current_mps(self) -> float:
        return self.v

    @property
    def u_wind_mps(self) -> float:
        return self.u

    @property
    def v_wind_mps(self) -> float:
        return self.v

    @property
    def timestamp(self) -> datetime:
        return self.valid_time


class CurrentSample(BaseModel):
    """
    Standardized ocean current velocity sample.
    
    Attributes:
        u_current_mps: Eastward water velocity component in meters per second (m/s).
                       Positive = Eastward, Negative = Westward.
        v_current_mps: Northward water velocity component in meters per second (m/s).
                       Positive = Northward, Negative = Southward.
        latitude: Latitude of sample in decimal degrees North [-90.0, 90.0].
        longitude: Longitude of sample in decimal degrees East [-180.0, 180.0] or [0.0, 360.0].
        timestamp: Timezone-aware UTC observation timestamp.
        quality_flag: Data quality indicator (1 = valid, 0 = degraded/missing).
    """
    u_current_mps: float = Field(..., description="Eastward current velocity component in m/s.")
    v_current_mps: float = Field(..., description="Northward current velocity component in m/s.")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Sample latitude in decimal degrees.")
    longitude: float = Field(..., description="Sample longitude in decimal degrees.")
    timestamp: datetime = Field(..., description="Timezone-aware UTC timestamp.")
    quality_flag: int = Field(default=1, description="Data quality flag (1=valid).")

    @property
    def u(self) -> float:
        """Alias for eastward velocity (m/s)."""
        return self.u_current_mps

    @property
    def v(self) -> float:
        """Alias for northward velocity (m/s)."""
        return self.v_current_mps

    @property
    def valid_time(self) -> datetime:
        """Alias for timestamp."""
        return self.timestamp


class WindSample(BaseModel):
    """
    Standardized 10-meter atmospheric surface wind velocity sample.
    
    Attributes:
        u_wind_mps: 10m Eastward wind velocity component in meters per second (m/s).
                    Positive = Eastward (blowing towards East), Negative = Westward.
        v_wind_mps: 10m Northward wind velocity component in meters per second (m/s).
                    Positive = Northward (blowing towards North), Negative = Southward.
        latitude: Latitude of sample in decimal degrees North [-90.0, 90.0].
        longitude: Longitude of sample in decimal degrees East [-180.0, 180.0] or [0.0, 360.0].
        timestamp: Timezone-aware UTC observation timestamp.
        quality_flag: Data quality indicator (1 = valid, 0 = degraded/missing).
    """
    u_wind_mps: float = Field(..., description="Eastward 10m wind velocity component in m/s.")
    v_wind_mps: float = Field(..., description="Northward 10m wind velocity component in m/s.")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Sample latitude in decimal degrees.")
    longitude: float = Field(..., description="Sample longitude in decimal degrees.")
    timestamp: datetime = Field(..., description="Timezone-aware UTC timestamp.")
    quality_flag: int = Field(default=1, description="Data quality flag (1=valid).")

    @property
    def u(self) -> float:
        """Alias for eastward wind velocity (m/s)."""
        return self.u_wind_mps

    @property
    def v(self) -> float:
        """Alias for northward wind velocity (m/s)."""
        return self.v_wind_mps

    @property
    def valid_time(self) -> datetime:
        """Alias for timestamp."""
        return self.timestamp


class EnvironmentalDataProvider(ABC):
    """
    Root abstract interface for hydrodynamic and meteorological data providers.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier of the data provider."""
        pass

    @property
    @abstractmethod
    def data_category(self) -> str:
        """Data category: 'historical' or 'forecast'."""
        pass

    @property
    @abstractmethod
    def field_type(self) -> str:
        """Physical field type: 'ocean_currents' or 'surface_wind'."""
        pass

    @abstractmethod
    def fetch_grid(self, window: EnvironmentalQueryWindow) -> bool:
        """
        Prepares or caches the gridded vector field for the requested spacetime bounding box.
        """
        pass

    @abstractmethod
    def sample_vector(
        self,
        lat: float,
        lon: float,
        timestamp: Union[datetime, str]
    ) -> Optional[Union[CurrentSample, WindSample, VectorFieldSample]]:
        """
        Samples the interpolated vector velocity at a specific lat, lon, and UTC timestamp.
        """
        pass


class HistoricalCurrentProvider(EnvironmentalDataProvider):
    """
    Abstract interface for historical / hindcast ocean current providers
    (e.g., Copernicus Marine, HYCOM Reanalysis, Local NetCDF).
    """

    @property
    def data_category(self) -> str:
        return "historical"

    @property
    def field_type(self) -> str:
        return "ocean_currents"

    @abstractmethod
    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        """
        Interpolates the ocean current vector (u_current_mps, v_current_mps) at target location & UTC time.
        """
        pass

    def sample_vector(
        self,
        lat: float,
        lon: float,
        timestamp: Union[datetime, str]
    ) -> Optional[CurrentSample]:
        """Backward-compatible sampling method."""
        return self.get_current(latitude=lat, longitude=lon, timestamp=timestamp)


class HistoricalWindProvider(EnvironmentalDataProvider):
    """
    Abstract interface for historical surface wind providers (e.g., ERA5 Reanalysis, Local NetCDF).
    """

    @property
    def data_category(self) -> str:
        return "historical"

    @property
    def field_type(self) -> str:
        return "surface_wind"

    @abstractmethod
    def get_wind(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> WindSample:
        """
        Interpolates the 10m surface wind vector (u_wind_mps, v_wind_mps) at target location & UTC time.
        """
        pass

    def sample_vector(
        self,
        lat: float,
        lon: float,
        timestamp: Union[datetime, str]
    ) -> Optional[WindSample]:
        """Backward-compatible sampling method."""
        return self.get_wind(latitude=lat, longitude=lon, timestamp=timestamp)


class ForecastCurrentProvider(EnvironmentalDataProvider):
    """
    Abstract interface for operational forecast ocean current providers (e.g., Copernicus Forecast, HYCOM Forecast).
    """

    @property
    def data_category(self) -> str:
        return "forecast"

    @property
    def field_type(self) -> str:
        return "ocean_currents"

    @abstractmethod
    def get_current(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> CurrentSample:
        """
        Interpolates forecast ocean current vector (u_current_mps, v_current_mps) at target location & UTC time.
        """
        pass

    def sample_vector(
        self,
        lat: float,
        lon: float,
        timestamp: Union[datetime, str]
    ) -> Optional[CurrentSample]:
        return self.get_current(latitude=lat, longitude=lon, timestamp=timestamp)


class ForecastWindProvider(EnvironmentalDataProvider):
    """
    Abstract interface for numerical weather prediction forecast wind providers (e.g., NOAA GFS, ECMWF IFS).
    """

    @property
    def data_category(self) -> str:
        return "forecast"

    @property
    def field_type(self) -> str:
        return "surface_wind"

    @abstractmethod
    def get_wind(
        self,
        latitude: float,
        longitude: float,
        timestamp: Union[datetime, str]
    ) -> WindSample:
        """
        Interpolates forecast 10m surface wind vector (u_wind_mps, v_wind_mps) at target location & UTC time.
        """
        pass

    def sample_vector(
        self,
        lat: float,
        lon: float,
        timestamp: Union[datetime, str]
    ) -> Optional[WindSample]:
        return self.get_wind(latitude=lat, longitude=lon, timestamp=timestamp)
