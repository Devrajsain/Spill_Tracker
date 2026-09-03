from pydantic import BaseModel
from typing import List, Any

class SpillResponse(BaseModel):
    id: str
    case_id: str
    confidence_score: float
    confidence_label: str
    area_km2: float
    length_km: float
    width_km: float
    est_volume_bbl: float
    detection_timestamp: str
    satellite_source: str
    polygon_geojson: Any
    origin_latitude: float
    origin_longitude: float
    origin_timestamp: str
    drift_trajectory_json: Any

    class Config:
        from_attributes = True
