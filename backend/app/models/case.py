from sqlalchemy import Column, String, Float, DateTime, Text, JSON
from datetime import datetime
from app.db import Base

class ForensicCase(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="PENDING") # PENDING, PROCESSING, COMPLETED, FAILED
    location_name = Column(String, nullable=False)
    center_latitude = Column(Float, nullable=False)
    center_longitude = Column(Float, nullable=False)
    
    # Upload File Paths
    image_path = Column(String, nullable=True)
    csv_path = Column(String, nullable=True)

    # Diagnostic Summary (JSON object containing spill, drift, & top vessel results)
    summary_json = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
