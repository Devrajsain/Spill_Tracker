from pydantic import BaseModel
from typing import Optional, Any, List
from datetime import datetime

class CaseCreate(BaseModel):
    name: str
    location_name: str
    center_latitude: float
    center_longitude: float

class CaseResponse(BaseModel):
    id: str
    name: str
    status: str
    location_name: str
    center_latitude: float
    center_longitude: float
    summary_json: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True
