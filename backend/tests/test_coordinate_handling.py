"""
Comprehensive tests for Geographic Coordinate Handling (Feature 1 -> Feature 2).

Verifies the 6 required test scenarios:
  TEST 1: GeoTIFF with valid geospatial metadata -> auto-extract real lat/lon -> Feature 2
  TEST 2: JPG -> no fake coords -> manual coords input & validation -> Feature 2
  TEST 3: PNG -> same flow as JPG
  TEST 4: Invalid coordinates -> validation error (422), Feature 2 NOT called
  TEST 5: TIFF without geospatial metadata -> detected as TIFF, no valid metadata, manual prompt
  TEST 6: Regression test -> existing detection and Feature 2 pipeline work as before
"""

import os
import tempfile
import pytest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import rasterio
from rasterio.transform import from_bounds

from app.main import app
from app.services.geotiff import inspect_image_geospatial, pixel_to_wgs84
from app.services.detection import run_spill_detection_model
from app.tasks.pipeline import execute_5step_pipeline

client = TestClient(app)


@pytest.fixture
def sample_geotiff():
    """Creates a temporary valid GeoTIFF with EPSG:4326 geospatial metadata and a dark slick."""
    # Extent around Gujarat / Gulf of Kutch: lon 69.1 to 69.3, lat 22.4 to 22.6
    min_lon, min_lat, max_lon, max_lat = 69.10, 22.40, 69.30, 22.60
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, 200, 200)

    # Base sea background (lighter ~180)
    arr = np.full((1, 200, 200), 180, dtype=np.uint8)
    # Dark slick anomaly around pixel (100, 100)
    arr[0, 80:120, 80:120] = 30

    fd, path = tempfile.mkstemp(suffix=".tif")
    os.close(fd)

    with rasterio.open(
        path,
        'w',
        driver='GTiff',
        height=200,
        width=200,
        count=1,
        dtype=arr.dtype,
        crs='EPSG:4326',
        transform=transform
    ) as dst:
        dst.write(arr)

    yield path

    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_non_geo_tiff():
    """Creates a temporary TIFF file without any CRS or geotransform metadata."""
    arr = np.full((200, 200), 180, dtype=np.uint8)
    arr[80:120, 80:120] = 30
    img = Image.fromarray(arr)

    fd, path = tempfile.mkstemp(suffix=".tif")
    os.close(fd)
    img.save(path, format="TIFF")

    yield path

    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_jpg():
    """Creates a temporary JPG file."""
    arr = np.full((200, 200), 180, dtype=np.uint8)
    arr[80:120, 80:120] = 30
    img = Image.fromarray(arr)

    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img.save(path, format="JPEG")

    yield path

    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_png():
    """Creates a temporary PNG file."""
    arr = np.full((200, 200), 180, dtype=np.uint8)
    arr[80:120, 80:120] = 30
    img = Image.fromarray(arr)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path, format="PNG")

    yield path

    if os.path.exists(path):
        os.remove(path)


# ── TEST 1: GeoTIFF with valid metadata ────────────────────────────────────────

def test_1_geotiff_valid_metadata(sample_geotiff):
    """
    TEST 1: Upload GeoTIFF
      -> Feature 1 runs normally
      -> Geospatial metadata detected
      -> Spill location converted to real lat/lon
      -> Coordinates displayed / returned
      -> Feature 2 receives coordinates
    """
    # 1. Verify metadata inspection detects GeoTIFF
    meta = inspect_image_geospatial(sample_geotiff)
    assert meta["is_geotiff"] is True
    assert meta["has_crs"] is True
    assert "4326" in meta["crs"]

    # 2. Run Feature 1 detection
    spill = run_spill_detection_model(sample_geotiff)
    assert spill["geospatial_metadata_detected"] is True
    assert spill["geospatial_source"] == "geotiff"
    assert spill["spill_latitude"] is not None
    assert spill["spill_longitude"] is not None

    # Verify extracted coordinate is within bounds (approx center 22.5, 69.2)
    assert 22.4 <= spill["spill_latitude"] <= 22.6
    assert 69.1 <= spill["spill_longitude"] <= 69.3
    assert spill["polygon_geojson"] is not None

    # 3. Test end-to-end pipeline execution with GeoTIFF
    summary = execute_5step_pipeline(
        case_id="TEST-GEOTIFF-1",
        image_path=sample_geotiff,
        csv_path=None,
        center_lat=None,
        center_lon=None
    )
    assert summary["status"] == "COMPLETED"
    assert summary["spill"]["geospatial_metadata_detected"] is True
    assert summary["drift"] is not None
    # Feature 2 / drift received real coordinates
    assert summary["drift"]["origin_latitude"] is not None
    assert summary["drift"]["origin_longitude"] is not None


# ── TEST 2: JPG image ──────────────────────────────────────────────────────────

def test_2_jpg_handling(sample_jpg):
    """
    TEST 2: Upload JPG
      -> Feature 1 runs normally
      -> Latitude/longitude input appears (status: AWAITING_COORDINATES)
      -> No fake coordinates calculated
      -> User enters coordinates
      -> Validation passes
      -> Feature 2 receives user coordinates
    """
    # 1. Feature 1 without coordinates does NOT fabricate coordinates
    spill = run_spill_detection_model(sample_jpg, center_lat=None, center_lon=None)
    assert spill["geospatial_metadata_detected"] is False
    assert spill["requires_coordinates"] is True
    assert spill["spill_latitude"] is None
    assert spill["spill_longitude"] is None
    assert "not contain reliable geospatial coordinates" in spill["message"]

    # 2. Case creation without coordinates sets AWAITING_COORDINATES; Feature 2 is paused
    with open(sample_jpg, "rb") as f:
        response = client.post(
            "/api/v1/cases/",
            data={"name": "Test JPG Case", "location_name": "Test Offshore"},
            files={"image_file": ("test.jpg", f, "image/jpeg")}
        )
    assert response.status_code == 200
    case_data = response.json()
    assert case_data["status"] == "AWAITING_COORDINATES"
    case_id = case_data["id"]

    # 3. User enters valid coordinates to continue to Feature 2
    user_lat, user_lon = 19.40, 71.33
    cont_res = client.post(
        f"/api/v1/cases/{case_id}/continue-feature2",
        data={"latitude": user_lat, "longitude": user_lon}
    )
    assert cont_res.status_code == 200
    updated_case = cont_res.json()
    assert updated_case["status"] == "COMPLETED"
    assert updated_case["center_latitude"] == user_lat
    assert updated_case["center_longitude"] == user_lon
    # Feature 2 ran and produced drift results
    assert updated_case["summary_json"]["drift"] is not None
    assert updated_case["summary_json"]["drift"]["origin_latitude"] is not None


# ── TEST 3: PNG image ──────────────────────────────────────────────────────────

def test_3_png_handling(sample_png):
    """
    TEST 3: Upload PNG
      -> Same expected behavior as JPG
      -> No fake coordinates
      -> Coordinates entered and validated
      -> Feature 2 receives user coordinates
    """
    spill = run_spill_detection_model(sample_png, center_lat=None, center_lon=None)
    assert spill["geospatial_metadata_detected"] is False
    assert spill["requires_coordinates"] is True
    assert spill["spill_latitude"] is None
    assert spill["spill_longitude"] is None

    with open(sample_png, "rb") as f:
        res = client.post(
            "/api/v1/cases/",
            data={"name": "Test PNG Case", "location_name": "Chennai Port"},
            files={"image_file": ("test.png", f, "image/png")}
        )
    assert res.status_code == 200
    case_id = res.json()["id"]

    cont_res = client.post(
        f"/api/v1/cases/{case_id}/continue-feature2",
        data={"latitude": 13.23, "longitude": 80.33}
    )
    assert cont_res.status_code == 200
    assert cont_res.json()["status"] == "COMPLETED"
    assert cont_res.json()["center_latitude"] == 13.23
    assert cont_res.json()["center_longitude"] == 80.33


# ── TEST 4: Invalid coordinates ───────────────────────────────────────────────

def test_4_invalid_coordinates(sample_jpg):
    """
    TEST 4: Invalid coordinates (e.g. Latitude = 120, Longitude = 200)
      -> Validation error (422)
      -> Feature 2 is NOT called
    """
    # Test invalid on create_case
    with open(sample_jpg, "rb") as f:
        res = client.post(
            "/api/v1/cases/",
            data={
                "name": "Invalid Case",
                "location_name": "Invalid Zone",
                "center_latitude": 120.0,
                "center_longitude": 200.0,
            },
            files={"image_file": ("test.jpg", f, "image/jpeg")}
        )
    assert res.status_code == 422
    assert "Invalid latitude/longitude" in res.text

    # Test invalid on continue-feature2
    with open(sample_jpg, "rb") as f:
        create_res = client.post(
            "/api/v1/cases/",
            data={"name": "Case Awaiting", "location_name": "Area"},
            files={"image_file": ("test.jpg", f, "image/jpeg")}
        )
    case_id = create_res.json()["id"]

    cont_res = client.post(
        f"/api/v1/cases/{case_id}/continue-feature2",
        data={"latitude": -100.0, "longitude": 50.0}
    )
    assert cont_res.status_code == 422
    assert "Invalid latitude/longitude" in cont_res.text

    # Verify in Python pipeline directly that ValueError is raised
    with pytest.raises(ValueError, match="Invalid latitude/longitude"):
        execute_5step_pipeline("INVALID-ID", sample_jpg, None, center_lat=120.0, center_lon=200.0)


# ── TEST 5: TIFF without geospatial metadata ───────────────────────────────────

def test_5_tiff_without_geospatial_metadata(sample_non_geo_tiff):
    """
    TEST 5: TIFF detected without valid geospatial metadata
      -> Detected as TIFF
      -> has_crs is False
      -> No fake coordinates invented
      -> Manual latitude/longitude input prompt appears
    """
    meta = inspect_image_geospatial(sample_non_geo_tiff)
    assert meta["is_geotiff"] is True
    assert meta["has_crs"] is False
    assert meta["crs"] is None

    spill = run_spill_detection_model(sample_non_geo_tiff, center_lat=None, center_lon=None)
    assert spill["geospatial_metadata_detected"] is False
    assert spill["spill_latitude"] is None
    assert spill["spill_longitude"] is None
    assert spill["requires_coordinates"] is True
    assert "⚠ This TIFF does not contain valid geospatial metadata" in spill["message"]


# ── TEST 6: Regression test ────────────────────────────────────────────────────

def test_6_regression_existing_functionality():
    """
    TEST 6: Regression test
      -> Verify existing preset pipeline (e.g. SLK-2291 with valid coords) still runs cleanly
      -> Feature 1 detection works
      -> Feature 2 drift and AIS vessel attribution work
    """
    summary = execute_5step_pipeline(
        case_id="REGRESSION-TEST",
        image_path=None,
        csv_path=None,
        center_lat=22.47,
        center_lon=69.21
    )
    assert summary["status"] == "COMPLETED"
    assert summary["spill"] is not None
    assert summary["spill"]["confidence_score"] > 0
    assert summary["drift"] is not None
    assert summary["drift"]["origin_latitude"] is not None
    assert summary["feature2"] is not None
    assert len(summary["vessels"]) > 0
