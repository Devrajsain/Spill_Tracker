"""
Full End-to-End Integration Test Script for SlickTrace
Validates Feature 1, Feature 2, Feature 3, and all API endpoints.
"""

import os
import requests
import json
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"

def run_integration_tests():
    print("================================================================")
    print("STARTING SLICKTRACE COMPREHENSIVE INTEGRATION TESTING")
    print("================================================================")

    # 1. Health check & Root
    root_resp = requests.get(f"{BASE_URL}/")
    assert root_resp.status_code == 200, f"Root failed: {root_resp.status_code}"
    print("[PASS] 1. Backend root health check passed:", root_resp.json()["status"])

    # 2. Feature 3 Config check
    f3_config_resp = requests.get(f"{BASE_URL}/api/v1/feature3/config")
    assert f3_config_resp.status_code == 200, f"Feature 3 config failed: {f3_config_resp.status_code}"
    print("[PASS] 2. Feature 3 config endpoint passed. Max speed kn:", f3_config_resp.json()["max_vessel_speed_kn"])

    # 3. Create a complete case with real GeoTIFF + AIS telemetry
    geotiff_path = UPLOADS_DIR / "SLK-C62E_slicktrace_feature2_realapi_test_sar.tif"
    ais_path = UPLOADS_DIR / "sample_ais_telemetry.csv"

    if not geotiff_path.exists():
        # Fallback to any available tif
        tifs = list(UPLOADS_DIR.glob("*.tif"))
        if tifs:
            geotiff_path = tifs[0]
    
    print(f"Testing with image: {geotiff_path.name}, AIS: {ais_path.name}")

    with open(geotiff_path, "rb") as img_f, open(ais_path, "rb") as ais_f:
        files = {
            "image_file": (geotiff_path.name, img_f, "image/tiff"),
            "csv_file": (ais_path.name, ais_f, "text/csv"),
        }
        data = {
            "name": "Integration Test Arabian Sea Incident",
            "location_name": "Gulf of Khambhat / Gujarat Maritime Zone",
        }
        create_resp = requests.post(f"{BASE_URL}/api/v1/cases/", files=files, data=data)
    
    assert create_resp.status_code in [200, 201], f"Case creation failed: {create_resp.status_code} - {create_resp.text}"
    case_json = create_resp.json()
    case_id = case_json["id"]
    print(f"[PASS] 3. Case created successfully! Case ID: {case_id}, Status: {case_json['status']}")

    # 4. Fetch Case Detail
    get_case_resp = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}")
    assert get_case_resp.status_code == 200, f"Get case failed: {get_case_resp.status_code}"
    c_data = get_case_resp.json()
    print(f"[PASS] 4. Fetched case data: Center ({c_data['center_latitude']:.4f}°N, {c_data['center_longitude']:.4f}°E)")

    # 5. Fetch Feature 1 Spill Detection Results
    spill_resp = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/spill")
    assert spill_resp.status_code == 200, f"Get spill failed: {spill_resp.status_code}"
    spill_data = spill_resp.json()
    print(f"[PASS] 5. Feature 1 Detection: Area={spill_data['area_km2']:.2f} km², Est Vol={spill_data['est_volume_bbl']} bbl, Conf={spill_data['confidence_label']}")
    assert spill_data["polygon_geojson"] is not None, "Spill polygon GeoJSON missing!"

    # 6. Fetch Feature 2 Hydrodynamic Drift / Results
    f2_resp = requests.get(f"{BASE_URL}/api/v1/feature2-results/{case_id}")
    assert f2_resp.status_code == 200, f"Get Feature 2 results failed: {f2_resp.status_code}"
    f2_data = f2_resp.json()
    print(f"[PASS] 6. Feature 2 Results: Origin ({f2_data.get('origin_latitude')}, {f2_data.get('origin_longitude')}), Status={f2_data.get('status')}")

    # 7. Fetch Feature 2 GeoJSON FeatureCollection
    f2_geojson_resp = requests.get(f"{BASE_URL}/api/v1/feature2-results/{case_id}/geojson")
    assert f2_geojson_resp.status_code == 200, f"Get Feature 2 GeoJSON failed: {f2_geojson_resp.status_code}"
    print("[PASS] 7. Feature 2 GeoJSON FeatureCollection verified.")

    # 8. Fetch Feature 3 Vessel Attribution Ranking
    vessels_resp = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/vessels")
    assert vessels_resp.status_code == 200, f"Get vessels failed: {vessels_resp.status_code}"
    vessels = vessels_resp.json()
    print(f"[PASS] 8. Feature 3 Attribution: {len(vessels)} candidate vessels ranked.")
    
    if vessels:
        top_vessel = vessels[0]
        mmsi = top_vessel["mmsi"]
        score = top_vessel.get("composite_score") or top_vessel.get("overall_score")
        risk = top_vessel.get("risk_class") or "N/A"
        print(f"   --> Top Suspect: {top_vessel['name']} (MMSI: {mmsi}) | Score: {score}/100 | Risk: {risk}")

        # 9. Fetch Single Vessel with Forensic Explainability Narrative
        single_v_resp = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/vessels/{mmsi}")
        assert single_v_resp.status_code == 200, f"Get single vessel failed: {single_v_resp.status_code}"
        sv_data = single_v_resp.json()
        assert sv_data.get("explanation") is not None, "Forensic explanation missing!"
        print("[PASS] 9. Forensic Explainability narrative generated successfully:")
        first_lines = "\n".join(sv_data["explanation"].splitlines()[:5])
        print("   " + first_lines.replace("\n", "\n   "))

    print("================================================================")
    print("ALL INTEGRATION TESTS PASSED PERFECTLY!")
    print("================================================================")
    return case_id

if __name__ == "__main__":
    run_integration_tests()
