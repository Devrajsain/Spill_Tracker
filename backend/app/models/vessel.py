from sqlalchemy import Column, String, Float, ForeignKey, JSON
from app.db import Base

class VesselAttribution(Base):
    __tablename__ = "vessels"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    
    mmsi = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False) # Oil Tanker, Container Cargo, etc.
    flag = Column(String, nullable=False)
    
    overall_score = Column(Float, nullable=False) # 0 to 100
    proximity_score = Column(Float, nullable=False)
    trajectory_score = Column(Float, nullable=False)
    behavioral_score = Column(Float, nullable=False)
    
    warning_flags = Column(JSON, nullable=False) # list of string flags
    current_latitude = Column(Float, nullable=False)
    current_longitude = Column(Float, nullable=False)
    heading_deg = Column(Float, nullable=False)
    speed_kts = Column(String, nullable=False)
