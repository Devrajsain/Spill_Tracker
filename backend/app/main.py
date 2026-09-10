from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.db import engine, Base
from app.routers import cases, spills, vessels
from app.routers.feature2_results import router as feature2_results_router
from app.feature2.api.routes import router as feature2_router
from app.feature2.exceptions import EnvironmentalDataError
import os
import logging

logger = logging.getLogger(__name__)

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
        status_code=503,
        content={"detail": f"Environmental data unavailable: {exc}"}
    )

# Routers
app.include_router(cases.router, prefix="/api/v1")
app.include_router(spills.router, prefix="/api/v1")
app.include_router(vessels.router, prefix="/api/v1")
app.include_router(feature2_results_router, prefix="/api/v1")
app.include_router(feature2_router, prefix="/api/v1/feature2")

# Static mounting for uploads & outputs
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

@app.on_event("startup")
def startup_event():
    # Initialize DB tables (including Feature2Result)
    Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {
        "system": "SlickTrace - Marine Oil Spill Detection & Vessel Attribution System",
        "status": "OPERATIONAL",
        "docs": "/docs",
        "version": "1.0.0"
    }
