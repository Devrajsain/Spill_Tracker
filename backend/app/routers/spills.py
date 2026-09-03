from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.models.spill import SpillDetection
from app.schemas.spill import SpillResponse

router = APIRouter(prefix="/spills", tags=["Spills"])

@router.get("/", response_model=List[SpillResponse])
def list_spills(db: Session = Depends(get_db)):
    return db.query(SpillDetection).all()

@router.get("/{spill_id}", response_model=SpillResponse)
def get_spill(spill_id: str, db: Session = Depends(get_db)):
    spill = db.query(SpillDetection).filter(SpillDetection.id == spill_id).first()
    if not spill:
        raise HTTPException(status_code=404, detail="Spill record not found")
    return spill
