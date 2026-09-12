"""
AIS Vessel Attribution Service for Spill Tracker.
Integrates Feature 3 multi-factor evidence correlation engine with Feature 2 drift context.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union

from app.feature3.adapter import extract_feature2_context
from app.feature3.engine import run_feature3_engine
from app.feature3.schemas import (
    Feature2OriginContext,
    Feature3EngineConfig,
    LatLon,
    ReleaseTimeWindowContract,
    VesselAttributionResult,
)

logger = logging.getLogger(__name__)


def run_vessel_attribution_model(
    csv_path: Optional[str] = None,
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    feature2_context: Optional[Feature2OriginContext] = None,
    feature2_result: Optional[Any] = None,
    spill_detection: Optional[Any] = None,
    config: Optional[Feature3EngineConfig] = None,
    scoring_mode: Optional[str] = None,
    allow_demo_fallback: bool = False,
) -> List[Dict[str, Any]]:
    """
    Executes Feature 3 AIS Vessel Attribution and returns serialized candidate vessel records.
    
    SAFETY NOTICE:
      If csv_path is missing or not found, this function returns [] unless allow_demo_fallback
      is explicitly set to True (for demo/test cases only). It will NEVER silently substitute
      sample data during real case analysis.
    """
    cfg = config or Feature3EngineConfig()
    cfg.allow_demo_fallback = allow_demo_fallback

    # Resolve AIS telemetry file
    effective_csv = csv_path
    if not effective_csv or not os.path.exists(effective_csv):
        if allow_demo_fallback:
            from app.config import settings
            sample_csv = os.path.join(settings.UPLOAD_DIR, "sample_ais_telemetry.csv")
            if os.path.exists(sample_csv):
                logger.info(f"Using explicit demo AIS dataset: {sample_csv}")
                effective_csv = sample_csv
            else:
                logger.warning("No AIS telemetry provided and demo sample not found.")
                return []
        else:
            logger.info("No AIS telemetry file uploaded for this case. Attribution skipped.")
            return []

    # Resolve Feature 2 Origin Context
    effective_context = feature2_context
    if not effective_context:
        if feature2_result:
            effective_context = extract_feature2_context(
                feature2_data=feature2_result,
                spill_data=spill_detection,
            )
        elif origin_lat is not None and origin_lon is not None:
            now_utc = datetime.now(timezone.utc)
            effective_context = Feature2OriginContext(
                spill_id="PIPELINE_SPILL",
                origin=LatLon(latitude=origin_lat, longitude=origin_lon),
                release_window=ReleaseTimeWindowContract(
                    start=now_utc - timedelta(hours=6),
                    end=now_utc,
                ),
                uncertainty_radius_km=3.0,
            )
        else:
            logger.warning("Insufficient Feature 2 context to perform vessel attribution.")
            return []

    # Execute Feature 3 Engine
    try:
        response = run_feature3_engine(
            feature2_context=effective_context,
            ais_data=effective_csv,
            config=cfg,
            scoring_mode=scoring_mode,
        )
    except Exception as exc:
        logger.error(f"Feature 3 attribution engine failed: {exc}", exc_info=True)
        return []

    # Serialize results to match database & API models
    serialized_vessels: List[Dict[str, Any]] = []
    for v in response.vessels:
        # Convert Pydantic datetime objects in evidence to iso strings
        evidence_dict = v.evidence.model_dump()
        if evidence_dict.get("closest_approach_time"):
            if isinstance(evidence_dict["closest_approach_time"], datetime):
                evidence_dict["closest_approach_time"] = evidence_dict["closest_approach_time"].isoformat()

        serialized_vessels.append({
            "id": v.id,
            "mmsi": v.mmsi,
            "name": v.name,
            "type": v.type,
            "flag": v.flag,
            "overall_score": v.overall_score,
            "proximity_score": round(v.scores.origin_presence, 1),
            "trajectory_score": round(v.scores.approach_departure if v.scores.approach_departure is not None else v.scores.origin_presence, 1),
            "behavioral_score": round(v.scores.behavior_anomaly, 1),
            "warning_flags": v.warning_flags,
            "current_latitude": v.current_latitude,
            "current_longitude": v.current_longitude,
            "heading_deg": v.heading_deg,
            "speed_kts": v.speed_kts,
            # Extended Feature 3 fields
            "composite_score": v.overall_score,
            "risk_class": v.risk_class,
            "scoring_mode": v.scoring_mode,
            "origin_presence_score": round(v.scores.origin_presence, 1),
            "behavior_anomaly_score": round(v.scores.behavior_anomaly, 1),
            "dwell_time_score": round(v.scores.dwell_time, 1),
            "ais_gap_score": round(v.scores.ais_gap, 1),
            "approach_departure_score": round(v.scores.approach_departure, 1) if v.scores.approach_departure is not None else None,
            "evidence_metrics": evidence_dict,
            "quality_flags": v.quality_flags,
            "trajectory_geojson": v.trajectory_geojson,
            "explanation": v.explanation,
        })

    return serialized_vessels
