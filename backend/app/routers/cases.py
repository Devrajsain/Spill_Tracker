from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import os

from app.db import get_db
from app.models.case import ForensicCase
from app.models.spill import SpillDetection
from app.models.vessel import VesselAttribution
from app.schemas.case import CaseResponse
from app.tasks.pipeline import execute_5step_pipeline
from app.config import settings

router = APIRouter(prefix="/cases", tags=["Cases"])

@router.post("/", response_model=CaseResponse)
async def create_case(
    name: str = Form(...),
    location_name: str = Form(...),
    center_latitude: float = Form(...),
    center_longitude: float = Form(...),
    image_file: Optional[UploadFile] = File(None),
    csv_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    case_id = f"SLK-{uuid.uuid4().hex[:4].upper()}"
    
    image_path = None
    csv_path = None
    
    if image_file:
        image_path = os.path.join(settings.UPLOAD_DIR, f"{case_id}_{image_file.filename}")
        with open(image_path, "wb") as f:
            f.write(await image_file.read())
            
    if csv_file:
        csv_path = os.path.join(settings.UPLOAD_DIR, f"{case_id}_{csv_file.filename}")
        with open(csv_path, "wb") as f:
            f.write(await csv_file.read())

    # Run Analysis Pipeline synchronously for API response
    summary = execute_5step_pipeline(case_id, image_path, csv_path, center_latitude, center_longitude)

    case_obj = ForensicCase(
        id=case_id,
        name=name,
        status="COMPLETED",
        location_name=location_name,
        center_latitude=center_latitude,
        center_longitude=center_longitude,
        image_path=image_path,
        csv_path=csv_path,
        summary_json=summary
    )
    
    db.add(case_obj)

    # Save Spill DB Entry
    spill_info = summary["spill"]
    drift_info = summary["drift"]
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
        polygon_geojson=spill_info["polygon_geojson"],
        origin_latitude=drift_info["origin_latitude"],
        origin_longitude=drift_info["origin_longitude"],
        origin_timestamp=drift_info["origin_timestamp"],
        drift_trajectory_json=drift_info["drift_trajectory"]
    )
    db.add(spill_obj)

    # Save Vessel DB Entries
    for v in summary["vessels"]:
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
            speed_kts=v["speed_kts"]
        )
        db.add(v_obj)

    db.commit()
    db.refresh(case_obj)
    return case_obj

@router.get("/", response_model=List[CaseResponse])
def list_cases(db: Session = Depends(get_db)):
    return db.query(ForensicCase).all()

@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case_obj = db.query(ForensicCase).filter(ForensicCase.id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")
    return case_obj
