import time
from app.services.detection import run_spill_detection_model
from app.services.drift import run_drift_hindcast_model
from app.services.attribution import run_vessel_attribution_model

def execute_5step_pipeline(case_id: str, image_path: str, csv_path: str, center_lat: float, center_lon: float):
    """
    Executes the 5-step forensic analysis pipeline:
    1. Upload evidence ingestion
    2. AI satellite boundary segmentation
    3. MetOcean hydrodynamic drift hindcasting
    4. AIS vessel spatio-temporal attribution
    5. Final case summary compilation
    """
    # Step 2: Satellite Detection
    spill_res = run_spill_detection_model(image_path, center_lat, center_lon)
    
    # Step 3: Drift Hindcasting
    drift_res = run_drift_hindcast_model(center_lat, center_lon)
    
    # Step 4: AIS Vessel Attribution
    vessels_res = run_vessel_attribution_model(csv_path, drift_res["origin_latitude"], drift_res["origin_longitude"])
    
    # Step 5: Summary Package
    summary = {
        "case_id": case_id,
        "status": "COMPLETED",
        "spill": spill_res,
        "drift": drift_res,
        "vessels": vessels_res,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }
    
    return summary
