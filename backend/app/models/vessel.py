from datetime import datetime
from sqlalchemy import Column, String, Float, ForeignKey, JSON, Text, DateTime
from app.db import Base

class VesselAttribution(Base):
    __tablename__ = "vessels"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    
    mmsi = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False) # Oil Tanker, Container Cargo, etc.
    flag = Column(String, nullable=False)
    
    overall_score = Column(Float, nullable=False) # 0 to 100 Evidence Correlation Score
    proximity_score = Column(Float, nullable=False)
    trajectory_score = Column(Float, nullable=False)
    behavioral_score = Column(Float, nullable=False)
    
    warning_flags = Column(JSON, nullable=False) # list of string flags
    current_latitude = Column(Float, nullable=False)
    current_longitude = Column(Float, nullable=False)
    heading_deg = Column(Float, nullable=False)
    speed_kts = Column(String, nullable=False)

    # Feature 3 - Extended Multi-Factor Evidence Scoring fields
    composite_score = Column(Float, nullable=True)
    risk_class = Column(String, nullable=True) # VERY HIGH, HIGH, MODERATE, LOW
    scoring_mode = Column(String, default="UNCERTAINTY_AWARE_5_FACTOR", nullable=True)

    origin_presence_score = Column(Float, nullable=True)
    behavior_anomaly_score = Column(Float, nullable=True)
    dwell_time_score = Column(Float, nullable=True)
    ais_gap_score = Column(Float, nullable=True)
    approach_departure_score = Column(Float, nullable=True)

    evidence_metrics = Column(JSON, nullable=True)
    quality_flags = Column(JSON, nullable=True)
    trajectory_geojson = Column(JSON, nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
