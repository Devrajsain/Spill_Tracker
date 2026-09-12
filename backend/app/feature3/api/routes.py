"""
FastAPI route handlers for Feature 3 AIS Attribution.
"""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.case import ForensicCase
from app.models.feature2_result import Feature2Result
from app.models.spill import SpillDetection
from ..adapter import extract_feature2_context
from ..engine import run_feature3_engine
from ..schemas import (
    Feature2OriginContext,
    Feature3AttributionRequest,
    Feature3AttributionResponse,
    Feature3EngineConfig,
)

router = APIRouter(tags=["Feature 3 - AIS Attribution"])


@router.get("/config", response_model=Feature3EngineConfig)
def get_engine_config():
    """Returns default configurable hyperparameters for the Feature 3 attribution engine."""
    return Feature3EngineConfig()


@router.post("/attribute", response_model=Feature3AttributionResponse)
def execute_attribution(
    request: Feature3AttributionRequest,
    db: Session = Depends(get_db),
):
    """
    Executes Feature 3 AIS Vessel Attribution & Evidence Correlation Engine.
    Correlates AIS telemetry against Feature 2 origin/drift context.
    """
    f2_context = request.feature2_context
    case_obj: Optional[ForensicCase] = None

    # If case_id is specified, load context and/or CSV from database if not explicitly passed
    if request.case_id:
        case_obj = db.query(ForensicCase).filter(ForensicCase.id == request.case_id).first()
        if not case_obj:
            raise HTTPException(status_code=404, detail=f"Case {request.case_id} not found")

        if not f2_context:
            f2_res = db.query(Feature2Result).filter(Feature2Result.case_id == request.case_id).first()
            spill_rec = db.query(SpillDetection).filter(SpillDetection.case_id == request.case_id).first()

            if not f2_res and not (case_obj.summary_json and "drift" in case_obj.summary_json):
                raise HTTPException(
                    status_code=422,
                    detail=f"Case {request.case_id} has not completed Feature 2 origin tracing. Run Feature 2 first."
                )

            drift_dict = None
            if case_obj.summary_json and "drift" in case_obj.summary_json:
                drift_dict = case_obj.summary_json["drift"]

            spill_dict = None
            if spill_rec:
                spill_dict = {
                    "spill_latitude": spill_rec.origin_latitude,
                    "spill_longitude": spill_rec.origin_longitude,
                    "detection_timestamp": spill_rec.detection_timestamp,
                }

            try:
                f2_context = extract_feature2_context(
                    feature2_data=f2_res or (case_obj.summary_json.get("feature2", {}) if case_obj.summary_json else {}),
                    spill_data=spill_dict,
                    drift_data=drift_dict,
                    spill_id=request.case_id,
                )
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Failed to derive Feature 2 context: {exc}")

    if not f2_context:
        raise HTTPException(
            status_code=422,
            detail="Feature 2 origin context is required (pass 'feature2_context' or valid 'case_id')."
        )

    # Resolve AIS input source
    ais_source = None
    if request.ais_records:
        ais_source = request.ais_records
    elif request.ais_csv_content:
        ais_source = request.ais_csv_content
    elif case_obj and case_obj.csv_path and os.path.exists(case_obj.csv_path):
        ais_source = case_obj.csv_path

    if not ais_source:
        cfg = request.config or Feature3EngineConfig()
        if not cfg.allow_demo_fallback:
            raise HTTPException(
                status_code=422,
                detail="No AIS telemetry data provided. Real case analysis requires an uploaded AIS telemetry CSV or records."
            )

    try:
        response = run_feature3_engine(
            feature2_context=f2_context,
            ais_data=ais_source or "",
            config=request.config,
            scoring_mode=request.scoring_mode,
        )
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Feature 3 attribution failed: {exc}")
