from pydantic import BaseModel
from typing import List

class VesselResponse(BaseModel):
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

    class Config:
        from_attributes = True
