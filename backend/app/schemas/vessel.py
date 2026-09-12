from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

class VesselResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    mmsi: str
    name: str
    type: str
    flag: str
    overall_score: float
    proximity_score: float
    trajectory_score: float
    behavioral_score: float
    warning_flags: List[str]
    current_latitude: float
    current_longitude: float
    heading_deg: float
    speed_kts: str

    # Feature 3 extended fields (optional for backward compatibility)
    composite_score: Optional[float] = None
    risk_class: Optional[str] = None
    scoring_mode: Optional[str] = None
    origin_presence_score: Optional[float] = None
    behavior_anomaly_score: Optional[float] = None
    dwell_time_score: Optional[float] = None
    ais_gap_score: Optional[float] = None
    approach_departure_score: Optional[float] = None
    evidence_metrics: Optional[Dict[str, Any]] = None
    quality_flags: Optional[List[str]] = None
    trajectory_geojson: Optional[Dict[str, Any]] = None
    explanation: Optional[str] = None
    created_at: Optional[datetime] = None
