from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.db import engine, Base, SessionLocal
from app.routers import cases, spills, vessels
from app.feature2.api.routes import router as feature2_router
from app.feature2.exceptions import EnvironmentalDataError
from app.models.case import ForensicCase
from app.models.spill import SpillDetection
from app.models.vessel import VesselAttribution
from app.tasks.pipeline import execute_5step_pipeline

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for AI-assisted Oil Spill Detection, Hydrodynamic Drift Modeling, and AIS Vessel Attribution for India's Maritime Waters.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Feature 2 environmental data exception handling
@app.exception_handler(EnvironmentalDataError)
async def environmental_data_error_handler(request: Request, exc: EnvironmentalDataError):
    return JSONResponse(
        status_code=422,
        content={
            "error": exc.__class__.__name__,
            "detail": str(exc),
        }
    )

# Include Routers
app.include_router(cases.router, prefix=settings.API_V1_STR)
app.include_router(spills.router, prefix=settings.API_V1_STR)
app.include_router(vessels.router, prefix=settings.API_V1_STR)
app.include_router(feature2_router)

@app.on_event("startup")
def startup_event():
    # Initialize DB tables
    Base.metadata.create_all(bind=engine)
    
    # Seed default case if DB is empty
    db = SessionLocal()
    try:
        existing = db.query(ForensicCase).filter(ForensicCase.id == "SLK-2291").first()
        if not existing:
            summary = execute_5step_pipeline(
                case_id="SLK-2291",
                image_path=None,
                csv_path=None,
                center_lat=22.47,
                center_lon=69.21
            )
            
            case_obj = ForensicCase(
                id="SLK-2291",
                name="Gulf of Kutch Maritime Disagree Incident",
                status="COMPLETED",
                location_name="Gulf of Kutch, Gujarat EEZ",
                center_latitude=22.47,
                center_longitude=69.21,
                summary_json=summary
            )
            db.add(case_obj)
            
            spill_info = summary["spill"]
            drift_info = summary["drift"]
            spill_obj = SpillDetection(
                id="spill-SLK-2291",
                case_id="SLK-2291",
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

            for v in summary["vessels"]:
                v_obj = VesselAttribution(
                    id=f"SLK-2291-{v['mmsi']}",
                    case_id="SLK-2291",
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
    finally:
        db.close()

@app.get("/")
def root():
    return {
        "system": "SlickTrace - Marine Oil Spill Detection & Vessel Attribution System",
        "status": "OPERATIONAL",
        "docs": "/docs",
        "version": "1.0.0"
    }
