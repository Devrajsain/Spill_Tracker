from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON
from app.db import Base

class SpillDetection(Base):
    __tablename__ = "spills"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    
    confidence_score = Column(Float, nullable=False) # e.g. 0.942
    confidence_label = Column(String, nullable=False) # HIGH CONFIDENCE, MEDIUM CONFIDENCE
    area_km2 = Column(Float, nullable=False)
    length_km = Column(Float, nullable=False)
    width_km = Column(Float, nullable=False)
    est_volume_bbl = Column(Float, nullable=False)
    
    detection_timestamp = Column(String, nullable=False)
    satellite_source = Column(String, nullable=False) # Sentinel-1A (IW / VV)
    
    # GeoJSON Polygon geometry coordinates
    polygon_geojson = Column(JSON, nullable=False)
    
    # Hydrodynamic Drift Hindcast Result
    origin_latitude = Column(Float, nullable=False)
    origin_longitude = Column(Float, nullable=False)
    origin_timestamp = Column(String, nullable=False)
    drift_trajectory_json = Column(JSON, nullable=False) # list of trajectory points
