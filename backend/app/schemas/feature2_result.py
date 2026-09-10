from pydantic import BaseModel
from typing import Optional, Any, List, Dict
from datetime import datetime


class ForecastHorizonResponse(BaseModel):
    horizon_label: str  # "6h", "12h", "24h", "48h"
    lead_time_hours: float
    timestamp: Optional[str] = None
    centroid_latitude: Optional[float] = None
    centroid_longitude: Optional[float] = None
    spread_radius_km: Optional[float] = None
    active_particles: Optional[int] = None
    quality: Optional[str] = None  # HIGH, MEDIUM, LOW, DEGRADED
    valid: bool = True


class OriginResponse(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[str] = None
    confidence_score: Optional[float] = None
    uncertainty_radius_km: Optional[float] = None
    release_window_start: Optional[str] = None
    release_window_end: Optional[str] = None


class Feature2ResultResponse(BaseModel):
    id: str
    case_id: str
    status: str
    processing_mode: str

    # Origin
    origin_latitude: Optional[float] = None
    origin_longitude: Optional[float] = None
    origin_timestamp: Optional[str] = None
    origin_confidence_score: Optional[float] = None
    origin_uncertainty_radius_km: Optional[float] = None
    release_window_start: Optional[str] = None
    release_window_end: Optional[str] = None

    # Forecast
    forecast_json: Optional[Any] = None

    # GeoJSON for map
    geojson_feature_collection: Optional[Any] = None

    # Full pipeline response
    pipeline_response_json: Optional[Any] = None

    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Feature2GeoJSONResponse(BaseModel):
    """Simplified GeoJSON response for map rendering."""
    case_id: str
    origin: Optional[OriginResponse] = None
    forecast_horizons: Optional[List[ForecastHorizonResponse]] = None
    drift_trajectory: Optional[List[Dict[str, Any]]] = None
    geojson: Optional[Any] = None
