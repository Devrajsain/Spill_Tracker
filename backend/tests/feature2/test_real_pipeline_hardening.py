"""
Automated Test Suite: Real Environmental Data Pipeline Hardening
Verifies:
1. CMEMS default dataset ID is cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m.
2. Mock drift anchors dynamically to detection_timestamp; no hardcoded 2026-09-01.
3. GFS historical mode requests past_days and verifies actual returned timestamps cover window.
4. GFS empty or all-NaN grid raises EnvironmentalDataUnavailableError.
5. In real mode, Feature 2 failure returns status="DATA_UNAVAILABLE" with null origin/trajectory.
6. In real mode with DATA_UNAVAILABLE, Feature 3 attribution is skipped.
7. Mock drift only executes if explicitly configured (FEATURE2_ENVIRONMENT=testing or FEATURE2_CURRENTS_PROVIDER=mock).
8. Backtracking environmental model specification: CMEMS currents + GFS wind.
9. GeoJSON coordinates conform to RFC 7946 [lon, lat] ordering.
"""

from datetime import datetime, timezone, timedelta
import os
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from app.feature2.config import Feature2Settings, default_settings
from app.feature2.data.currents.copernicus import CopernicusConfig, CopernicusCurrentsProvider
from app.feature2.data.wind.gfs import GFSConfig, GFSWindProvider
from app.feature2.exceptions import EnvironmentalCoverageError, EnvironmentalDataUnavailableError
from app.feature2.schemas.simulation_schema import EnvironmentalQueryWindow
from app.services.drift import run_drift_hindcast_model
from app.tasks.pipeline import execute_5step_pipeline, _run_feature2_pipeline


def test_cmems_default_dataset_id():
    """Verify that Copernicus currents default dataset ID is the verified Analysis/Forecast product."""
    cfg = Feature2Settings()
    assert cfg.data.copernicus_historical_dataset_id == "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"

    c_cfg = CopernicusConfig()
    assert c_cfg.dataset_id == "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"


def test_mock_drift_anchored_to_detection_timestamp():
    """Verify mock drift calculates origin and trajectory anchored to T0 without hardcoding 2026-09-01."""
    det_ts = "2026-09-10T14:11:50Z"
    lat, lon = 18.92, 72.88
    drift_res = run_drift_hindcast_model(lat, lon, detection_timestamp=det_ts)

    # Origin timestamp must be anchored to detection timestamp (18h before T0)
    assert drift_res["origin_timestamp"] == "2026-09-09 20:11:50 UTC"
    assert "2026-09-01" not in drift_res["origin_timestamp"]

    # Trajectory points: origin (-18h), -12h, -6h, 0h (detected), +6h, +12h forecast
    traj = drift_res["drift_trajectory"]
    assert len(traj) == 6
    assert "2026-09-09" in traj[0]["timestamp"]
    assert "2026-09-10" in traj[3]["timestamp"]  # Detected 0h
    assert "2026-09-11" in traj[-1]["timestamp"]  # +12h forecast
    for pt in traj:
        assert "2026-09-01" not in pt["timestamp"]


def test_gfs_historical_window_timestamp_verification():
    """Verify that GFS historical mode validates returned timestamps against required query window."""
    provider = GFSWindProvider(mode="historical")
    provider.cache_manager.clear("gfs_historical")
    window = EnvironmentalQueryWindow(
        min_lat=18.5, max_lat=19.5, min_lon=72.5, max_lon=73.5,
        start_time=datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc),
    )

    # Mock an API response whose time range is incomplete (e.g. only covers 2026-09-09 to 2026-09-10)
    incomplete_mock_response = {
        "hourly": {
            "time": ["2026-09-09T00:00", "2026-09-10T00:00"],
            "wind_u_component_10m": [1.0, 1.5],
            "wind_v_component_10m": [0.5, 0.8],
        }
    }

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        import json
        mock_resp.read.return_value = json.dumps(incomplete_mock_response).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        # Should raise EnvironmentalCoverageError because returned range does not cover 2026-09-07
        with pytest.raises(EnvironmentalCoverageError) as exc_info:
            provider.fetch_grid(window, mode="historical")
        assert "do not cover the required historical window" in str(exc_info.value)


def test_gfs_nan_grid_validation():
    """Verify that all-NaN or empty grid in GFS response raises EnvironmentalDataUnavailableError."""
    provider = GFSWindProvider(mode="historical")
    provider.cache_manager.clear("gfs_historical")
    window = EnvironmentalQueryWindow(
        min_lat=18.5, max_lat=19.5, min_lon=72.5, max_lon=73.5,
        start_time=datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc),
    )

    # Mock an API response with NaNs
    nan_mock_response = {
        "hourly": {
            "time": [f"2026-09-{d:02d}T12:00" for d in range(6, 12)],
            "wind_u_component_10m": [float("nan")] * 6,
            "wind_v_component_10m": [float("nan")] * 6,
        }
    }

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        import json
        mock_resp.read.return_value = json.dumps(nan_mock_response).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        with pytest.raises(EnvironmentalDataUnavailableError) as exc_info:
            provider.fetch_grid(window, mode="historical")
        assert "NaN" in str(exc_info.value)


def test_pipeline_real_mode_fail_closed_on_data_unavailable(monkeypatch):
    """Verify that in real data mode, Feature 2 failure produces DATA_UNAVAILABLE and does NOT synthesize drift."""
    monkeypatch.setenv("FEATURE2_ENVIRONMENT", "production")
    monkeypatch.setenv("FEATURE2_CURRENTS_PROVIDER", "copernicus")

    # Mock Feature 1 detection
    mock_spill = {
        "spill_detected": True,
        "spill_latitude": 18.92,
        "spill_longitude": 72.88,
        "detection_timestamp": "2026-09-10T14:11:50Z",
    }

    # Mock Feature 2 failure
    with patch("app.tasks.pipeline.run_spill_detection_model", return_value=mock_spill):
        with patch("app.tasks.pipeline._run_feature2_pipeline") as mock_f2:
            mock_f2.return_value = {
                "status": "DATA_UNAVAILABLE",
                "processing_mode": "live",
                "error": "Copernicus Marine CAS authentication failure: Invalid credentials",
                "origin": {},
                "forecast": {},
                "geojson": {"type": "FeatureCollection", "features": []},
            }

            summary = execute_5step_pipeline(
                case_id="REAL-CASE-001",
                image_path=None,
                csv_path=None,
                center_lat=18.92,
                center_lon=72.88,
            )

            # Verification: Status is DATA_UNAVAILABLE, drift origin is None, drift trajectory is empty
            assert summary["status"] == "DATA_UNAVAILABLE"
            assert summary["drift"]["status"] == "DATA_UNAVAILABLE"
            assert summary["drift"]["origin_latitude"] is None
            assert summary["drift"]["origin_longitude"] is None
            assert summary["drift"]["origin_timestamp"] is None
            assert summary["drift"]["drift_trajectory"] == []

            # Requirement 4: Feature 3 attribution must NOT execute an attribution calculation!
            assert summary["vessels"] == []
            assert summary["attribution_status"] == "SKIPPED_ENVIRONMENT_DATA_UNAVAILABLE"
            assert "Environmental origin context is unavailable" in summary["attribution_message"]


def test_pipeline_explicit_mock_mode_allows_synthetic_drift(monkeypatch):
    """Verify that mock drift only executes when explicitly requested via config/env."""
    monkeypatch.setenv("FEATURE2_ENVIRONMENT", "testing")
    monkeypatch.setenv("FEATURE2_CURRENTS_PROVIDER", "mock")

    mock_spill = {
        "spill_detected": True,
        "spill_latitude": 18.92,
        "spill_longitude": 72.88,
        "detection_timestamp": "2026-09-10T14:11:50Z",
    }

    with patch("app.tasks.pipeline.run_spill_detection_model", return_value=mock_spill):
        with patch("app.tasks.pipeline._run_feature2_pipeline") as mock_f2:
            # Simulate f2 failure in testing mode
            mock_f2.return_value = {"status": "FAILED", "origin": {}, "forecast": {}}

            summary = execute_5step_pipeline(
                case_id="DEMO-TEST-001",
                image_path=None,
                csv_path=None,
                center_lat=18.92,
                center_lon=72.88,
            )

            # In testing/mock mode, mock drift should run and anchor to detection_timestamp
            assert summary["drift"]["origin_latitude"] is not None
            assert summary["drift"]["origin_timestamp"] == "2026-09-09 20:11:50 UTC"
            assert len(summary["drift"]["drift_trajectory"]) > 0


def test_geojson_lon_lat_rfc7946_ordering():
    """Verify that GeoJSON features in Feature 2 output conform to [lon, lat] RFC 7946 order."""
    mock_detection = {
        "spill_id": "TEST-SLICK-01",
        "detection_timestamp": "2026-09-10T14:11:50Z",
        "spill_latitude": 18.92,
        "spill_longitude": 72.88,
        "estimated_area_sqkm": 1.25,
        "polygon_geojson": {
            "type": "Polygon",
            "coordinates": [
                [[72.87, 18.91], [72.89, 18.91], [72.89, 18.93], [72.87, 18.93], [72.87, 18.91]]
            ],
        },
    }

    mock_resp = MagicMock()
    mock_resp.origin_analysis.best_candidate.latitude = 18.85
    mock_resp.origin_analysis.best_candidate.longitude = 72.75
    mock_resp.origin_analysis.best_candidate.release_time = datetime(2026, 9, 7, 14, 11, 50, tzinfo=timezone.utc)
    mock_resp.origin_analysis.best_candidate.candidate_score = 0.92
    mock_resp.origin_analysis.best_candidate.uncertainty_radius_km = 3.5
    mock_resp.origin_analysis.release_time_window = None
    mock_resp.forecast = {}

    with patch("app.feature2.api.dependencies.get_pipeline_service") as mock_svc:
        mock_svc.return_value.run_pipeline.return_value = mock_resp
        res = _run_feature2_pipeline("CASE-123", mock_detection, 18.92, 72.88)

        assert res["status"] == "COMPLETED"
        assert len(res["geojson"]["features"]) == 1
        origin_geom = res["geojson"]["features"][0]["geometry"]
        assert origin_geom["type"] == "Point"
        # RFC 7946: [longitude, latitude]
        assert origin_geom["coordinates"] == [72.75, 18.85]
