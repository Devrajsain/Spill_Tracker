from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import os

from app.db import get_db
from app.models.case import ForensicCase
from app.models.spill import SpillDetection
from app.models.vessel import VesselAttribution
from app.models.feature2_result import Feature2Result
from app.schemas.case import CaseResponse
from app.schemas.vessel import VesselResponse
from app.tasks.pipeline import execute_5step_pipeline
from app.config import settings

router = APIRouter(prefix="/cases", tags=["Cases"])


def _persist_vessel_records(db: Session, case_id: str, vessels: list):
    """Persists candidate vessels including Feature 3 multi-factor evidence fields."""
    for v in vessels:
        v_obj = VesselAttribution(
            id=f"{case_id}-{v['mmsi']}",
            case_id=case_id,
            mmsi=v["mmsi"],
            name=v["name"],
            type=v["type"],
            flag=v["flag"],
            overall_score=v["overall_score"],
            proximity_score=v["proximity_score"],
            trajectory_score=v["trajectory_score"],
            behavioral_score=v["behavioral_score"],
            warning_flags=v["warning_flags"],
            current_latitude=v["current_latitude"],
            current_longitude=v["current_longitude"],
            heading_deg=v["heading_deg"],
            speed_kts=v["speed_kts"],
            composite_score=v.get("composite_score", v["overall_score"]),
            risk_class=v.get("risk_class"),
            scoring_mode=v.get("scoring_mode", "UNCERTAINTY_AWARE_5_FACTOR"),
            origin_presence_score=v.get("origin_presence_score"),
            behavior_anomaly_score=v.get("behavior_anomaly_score"),
            dwell_time_score=v.get("dwell_time_score"),
            ais_gap_score=v.get("ais_gap_score"),
            approach_departure_score=v.get("approach_departure_score"),
            evidence_metrics=v.get("evidence_metrics"),
            quality_flags=v.get("quality_flags"),
            trajectory_geojson=v.get("trajectory_geojson"),
            explanation=v.get("explanation"),
        )
        db.add(v_obj)


def _persist_feature2_result(db: Session, case_id: str, summary: dict):
    """Extracts Feature 2 data from the pipeline summary and persists it."""
    f2 = summary.get("feature2", {})
    if not f2:
        return

    origin = f2.get("origin", {})
    forecast = f2.get("forecast", {})
    geojson = f2.get("geojson", {})

    f2_obj = Feature2Result(
        id=f"f2-{case_id}",
        case_id=case_id,
        status=f2.get("status", "SKIPPED"),
        processing_mode=f2.get("processing_mode", "mock"),
        origin_latitude=origin.get("origin_latitude"),
        origin_longitude=origin.get("origin_longitude"),
        origin_timestamp=origin.get("origin_timestamp"),
        origin_confidence_score=origin.get("origin_confidence_score"),
        origin_uncertainty_radius_km=origin.get("origin_uncertainty_radius_km"),
        release_window_start=origin.get("release_window_start"),
        release_window_end=origin.get("release_window_end"),
        forecast_json=forecast if forecast else None,
        geojson_feature_collection=geojson if geojson else None,
        error_message=f2.get("error"),
    )
    db.add(f2_obj)


@router.post("/", response_model=CaseResponse)
async def create_case(
    name: str = Form(...),
    location_name: str = Form(...),
    center_latitude: Optional[float] = Form(None),
    center_longitude: Optional[float] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    csv_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    # Validate coordinates if passed
    if center_latitude is not None or center_longitude is not None:
        if (
            center_latitude is None or center_longitude is None or
            not (-90.0 <= center_latitude <= 90.0 and -180.0 <= center_longitude <= 180.0)
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid latitude/longitude. Please enter valid geographic coordinates."
            )

    case_id = f"SLK-{uuid.uuid4().hex[:4].upper()}"
    
    image_path = None
    csv_path = None
    
    if image_file:
        image_path = os.path.join(settings.UPLOAD_DIR, f"{case_id}_{image_file.filename}")
        with open(image_path, "wb") as f:
            f.write(await image_file.read())
    else:
        sample_img = os.path.join(settings.UPLOAD_DIR, "sample_sar_slick.png")
        if os.path.exists(sample_img):
            image_path = sample_img
            
    if csv_file:
        csv_path = os.path.join(settings.UPLOAD_DIR, f"{case_id}_{csv_file.filename}")
        with open(csv_path, "wb") as f:
            f.write(await csv_file.read())
    else:
        sample_csv = os.path.join(settings.UPLOAD_DIR, "sample_ais_telemetry.csv")
        if os.path.exists(sample_csv):
            csv_path = sample_csv

    # Run Analysis Pipeline
    try:
        summary = execute_5step_pipeline(case_id, image_path, csv_path, center_latitude, center_longitude)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    status = summary.get("status", "COMPLETED")
    spill_info = summary.get("spill", {})
    drift_info = summary.get("drift")

    # Determine stored center coordinates: prefer real GeoTIFF detected coordinates
    stored_lat = spill_info.get("spill_latitude")
    if stored_lat is None:
        stored_lat = center_latitude if center_latitude is not None else 0.0

    stored_lon = spill_info.get("spill_longitude")
    if stored_lon is None:
        stored_lon = center_longitude if center_longitude is not None else 0.0

    # Refine location_name if generic or default
    if not location_name or location_name in ["Operational Area", "Operational Maritime Area"]:
        name_lower = (name or "").lower()
        fn_lower = (image_file.filename if image_file else "").lower()
        if "kutch" in name_lower or "kutch" in fn_lower:
            location_name = "Gulf of Kutch, Gujarat EEZ"
        elif 22.0 <= float(stored_lat) <= 23.5 and 68.0 <= float(stored_lon) <= 71.0:
            location_name = "Gulf of Kutch, Gujarat EEZ"

    case_obj = ForensicCase(
        id=case_id,
        name=name,
        status=status,
        location_name=location_name,
        center_latitude=float(stored_lat),
        center_longitude=float(stored_lon),
        image_path=image_path,
        csv_path=csv_path,
        summary_json=summary
    )
    
    db.add(case_obj)

    # Save Spill DB Entry if complete
    if status == "COMPLETED" and drift_info:
        spill_obj = SpillDetection(
            id=f"spill-{case_id}",
            case_id=case_id,
            confidence_score=spill_info["confidence_score"],
            confidence_label=spill_info["confidence_label"],
            area_km2=spill_info["area_km2"],
            length_km=spill_info["length_km"],
            width_km=spill_info["width_km"],
            est_volume_bbl=spill_info["est_volume_bbl"],
            detection_timestamp=spill_info["detection_timestamp"],
            satellite_source=spill_info["satellite_source"],
            polygon_geojson=spill_info.get("polygon_geojson") or {},
            origin_latitude=drift_info["origin_latitude"],
            origin_longitude=drift_info["origin_longitude"],
            origin_timestamp=drift_info["origin_timestamp"],
            drift_trajectory_json=drift_info["drift_trajectory"]
        )
        db.add(spill_obj)

        # Save Vessel DB Entries
        _persist_vessel_records(db, case_id, summary.get("vessels", []))

        # Save Feature 2 Results
        _persist_feature2_result(db, case_id, summary)

    db.commit()
    db.refresh(case_obj)
    return case_obj


@router.post("/{case_id}/continue-feature2", response_model=CaseResponse)
async def continue_feature2(
    case_id: str,
    latitude: float = Form(...),
    longitude: float = Form(...),
    db: Session = Depends(get_db)
):
    """
    Continues pipeline execution into Feature 2 using user-entered coordinates
    for cases where the image lacks valid geospatial metadata (JPG/PNG or unreferenced TIFF).
    """
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        raise HTTPException(
            status_code=422,
            detail="Invalid latitude/longitude. Please enter valid geographic coordinates."
        )

    case_obj = db.query(ForensicCase).filter(ForensicCase.id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    try:
        summary = execute_5step_pipeline(
            case_id,
            case_obj.image_path,
            case_obj.csv_path,
            center_lat=latitude,
            center_lon=longitude
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    case_obj.center_latitude = latitude
    case_obj.center_longitude = longitude
    case_obj.status = "COMPLETED"
    case_obj.summary_json = summary

    spill_info = summary.get("spill", {})
    drift_info = summary.get("drift")

    # Update or create SpillDetection
    spill_obj = db.query(SpillDetection).filter(SpillDetection.case_id == case_id).first()
    if not spill_obj:
        spill_obj = SpillDetection(
            id=f"spill-{case_id}",
            case_id=case_id,
            confidence_score=spill_info["confidence_score"],
            confidence_label=spill_info["confidence_label"],
            area_km2=spill_info["area_km2"],
            length_km=spill_info["length_km"],
            width_km=spill_info["width_km"],
            est_volume_bbl=spill_info["est_volume_bbl"],
            detection_timestamp=spill_info["detection_timestamp"],
            satellite_source=spill_info["satellite_source"],
            polygon_geojson=spill_info.get("polygon_geojson") or {},
            origin_latitude=drift_info["origin_latitude"] if drift_info else latitude,
            origin_longitude=drift_info["origin_longitude"] if drift_info else longitude,
            origin_timestamp=drift_info["origin_timestamp"] if drift_info else "",
            drift_trajectory_json=drift_info["drift_trajectory"] if drift_info else []
        )
        db.add(spill_obj)
    else:
        spill_obj.confidence_score = spill_info["confidence_score"]
        spill_obj.confidence_label = spill_info["confidence_label"]
        spill_obj.area_km2 = spill_info["area_km2"]
        spill_obj.length_km = spill_info["length_km"]
        spill_obj.width_km = spill_info["width_km"]
        spill_obj.est_volume_bbl = spill_info["est_volume_bbl"]
        spill_obj.detection_timestamp = spill_info["detection_timestamp"]
        spill_obj.satellite_source = spill_info["satellite_source"]
        spill_obj.polygon_geojson = spill_info.get("polygon_geojson") or {}
        if drift_info:
            spill_obj.origin_latitude = drift_info["origin_latitude"]
            spill_obj.origin_longitude = drift_info["origin_longitude"]
            spill_obj.origin_timestamp = drift_info["origin_timestamp"]
            spill_obj.drift_trajectory_json = drift_info["drift_trajectory"]

    # Re-save Vessel entries
    db.query(VesselAttribution).filter(VesselAttribution.case_id == case_id).delete()
    _persist_vessel_records(db, case_id, summary.get("vessels", []))

    # Re-save Feature 2 entries
    db.query(Feature2Result).filter(Feature2Result.case_id == case_id).delete()
    _persist_feature2_result(db, case_id, summary)

    db.commit()
    db.refresh(case_obj)
    return case_obj

@router.get("/", response_model=List[CaseResponse])
def list_cases(db: Session = Depends(get_db)):
    return db.query(ForensicCase).order_by(ForensicCase.created_at.desc()).all()

@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case_obj = db.query(ForensicCase).filter(ForensicCase.id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")
    return case_obj

@router.get("/{case_id}/spill")
def get_case_spill(case_id: str, db: Session = Depends(get_db)):
    """Returns the spill detection data for a specific case."""
    spill = db.query(SpillDetection).filter(SpillDetection.case_id == case_id).first()
    if not spill:
        raise HTTPException(status_code=404, detail="Spill record not found for this case")
    return spill

@router.get("/{case_id}/vessels", response_model=List[VesselResponse])
def get_case_vessels(
    case_id: str,
    sort: Optional[str] = Query("score", description="Sort field: 'score' (default) or 'mmsi'"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Max vessels to return"),
    db: Session = Depends(get_db)
):
    """Returns ranked vessel attribution records for a specific case with deterministic sorting."""
    query = db.query(VesselAttribution).filter(VesselAttribution.case_id == case_id)
    if sort == "mmsi":
        query = query.order_by(VesselAttribution.mmsi.asc())
    else:
        query = query.order_by(VesselAttribution.overall_score.desc(), VesselAttribution.mmsi.asc())

    if limit:
        query = query.limit(limit)

    return query.all()


@router.get("/{case_id}/vessels/{mmsi}", response_model=VesselResponse)
def get_case_vessel_by_mmsi(
    case_id: str,
    mmsi: str,
    db: Session = Depends(get_db)
):
    """Returns a single vessel attribution record including full forensic explanation and evidence metrics."""
    vessel = db.query(VesselAttribution).filter(
        VesselAttribution.case_id == case_id,
        VesselAttribution.mmsi == mmsi
    ).first()
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel with MMSI {mmsi} not found for case {case_id}")
    return vessel

@router.get("/{case_id}/feature2")
def get_case_feature2(case_id: str, db: Session = Depends(get_db)):
    """Returns the Feature 2 results for a specific case."""
    result = db.query(Feature2Result).filter(Feature2Result.case_id == case_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="No Feature 2 results for this case")
    return result


@router.delete("/{case_id}")
def delete_case(case_id: str, db: Session = Depends(get_db)):
    """Deletes a case and all associated spill, vessel, and Feature 2 records."""
    case_obj = db.query(ForensicCase).filter(ForensicCase.id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Clean up uploaded files if case-specific
    for file_path in [case_obj.image_path, case_obj.csv_path]:
        if file_path and os.path.exists(file_path) and "sample_" not in os.path.basename(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    # Cascading deletion
    db.query(SpillDetection).filter(SpillDetection.case_id == case_id).delete()
    db.query(VesselAttribution).filter(VesselAttribution.case_id == case_id).delete()
    db.query(Feature2Result).filter(Feature2Result.case_id == case_id).delete()
    db.delete(case_obj)
    db.commit()

    return {"message": f"Case {case_id} and all related records deleted successfully", "id": case_id}

