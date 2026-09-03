from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.models.vessel import VesselAttribution
from app.schemas.vessel import VesselResponse

router = APIRouter(prefix="/vessels", tags=["Vessels"])

@router.get("/", response_model=List[VesselResponse])
def list_vessels(db: Session = Depends(get_db)):
    return db.query(VesselAttribution).all()

@router.get("/{mmsi}", response_model=List[VesselResponse])
def get_vessel_tracks(mmsi: str, db: Session = Depends(get_db)):
    vessels = db.query(VesselAttribution).filter(VesselAttribution.mmsi == mmsi).all()
    if not vessels:
        raise HTTPException(status_code=404, detail="No vessel records found for specified MMSI")
    return vessels
