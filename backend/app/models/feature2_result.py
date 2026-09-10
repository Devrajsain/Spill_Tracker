from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON, Text
from datetime import datetime
from app.db import Base


class Feature2Result(Base):
    __tablename__ = "feature2_results"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, unique=True)

    # Origin Tracing Results
    origin_latitude = Column(Float, nullable=True)
    origin_longitude = Column(Float, nullable=True)
    origin_timestamp = Column(String, nullable=True)
    origin_confidence_score = Column(Float, nullable=True)
    origin_uncertainty_radius_km = Column(Float, nullable=True)

    # Release Time Window
    release_window_start = Column(String, nullable=True)
    release_window_end = Column(String, nullable=True)

    # Forward Forecast Results (JSON blob: {6h: {...}, 12h: {...}, 24h: {...}, 48h: {...}})
    forecast_json = Column(JSON, nullable=True)

    # Full Feature 2 Pipeline Response (complete audit trail)
    pipeline_response_json = Column(JSON, nullable=True)

    # GeoJSON FeatureCollection for map rendering (origin + forecast combined)
    geojson_feature_collection = Column(JSON, nullable=True)

    # Processing metadata
    status = Column(String, default="PENDING")  # PENDING, COMPLETED, FAILED, SKIPPED
    error_message = Column(Text, nullable=True)
    processing_mode = Column(String, default="mock")  # mock, live

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
