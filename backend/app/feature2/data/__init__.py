"""
Environmental data acquisition and interpolation layer for ocean currents and surface winds.
"""

from .base import (
    CurrentSample,
    WindSample,
    VectorFieldSample,
    EnvironmentalDataProvider,
    HistoricalCurrentProvider,
    HistoricalWindProvider,
    ForecastCurrentProvider,
    ForecastWindProvider,
)
from .domain import (
    SentinelObservationDomain,
    EnvironmentalQueryDomain,
    extract_query_bounds,
)
from .wiring_trace import (
    ProviderRequestRecord,
    WiringTraceRecord,
    ProviderRequestAuditor,
    trace_feature1_environmental_wiring,
)
from .local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from .time_utils import normalize_to_utc, datetime_to_seconds, seconds_to_datetime
from .coord_utils import normalize_longitude, detect_longitude_convention, find_grid_bounding_indices

__all__ = [
    "CurrentSample",
    "WindSample",
    "VectorFieldSample",
    "EnvironmentalDataProvider",
    "HistoricalCurrentProvider",
    "HistoricalWindProvider",
    "ForecastCurrentProvider",
    "ForecastWindProvider",
    "SentinelObservationDomain",
    "EnvironmentalQueryDomain",
    "extract_query_bounds",
    "ProviderRequestRecord",
    "WiringTraceRecord",
    "ProviderRequestAuditor",
    "trace_feature1_environmental_wiring",
    "LocalNetCDFDatasetReader",
    "VariableMapping",
    "normalize_to_utc",
    "datetime_to_seconds",
    "seconds_to_datetime",
    "normalize_longitude",
    "detect_longitude_convention",
    "find_grid_bounding_indices",
]
