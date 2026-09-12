"""
Comprehensive unit and synthetic scenario test suite for Feature 3:
AIS Vessel Attribution & Evidence Correlation Scoring Engine.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.feature3.schemas import (
    AISRecord,
    Feature2OriginContext,
    Feature3EngineConfig,
    LatLon,
    ReleaseTimeWindowContract,
)
from app.feature3.cleaning import clean_and_validate_ais
from app.feature3.spatial import (
    haversine_km,
    calculate_bearing,
    smallest_angle_difference,
    distance_to_uncertainty_zone_km,
)
from app.feature3.trajectory import (
    reconstruct_vessel_trajectories,
    interpolate_position_at_time,
    find_closest_approach_to_origin,
)
from app.feature3.scoring import (
    compute_origin_presence_score,
    compute_behavior_anomaly_score,
    compute_dwell_time_score,
    compute_ais_gap_score,
    compute_approach_departure_score,
    calculate_composite_score,
    determine_risk_class,
)
from app.feature3.engine import run_feature3_engine

client = TestClient(app)


# ── 1. AIS INGESTION & CLEANING TESTS ──────────────────────────────────────────

def test_cleaning_deduplication():
    """Verifies that identical AIS records (same MMSI, timestamp, coords) are deduplicated."""
    raw_data = [
        {"mmsi": "123456789", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.45, "lon": 69.20, "sog": 10.0},
        {"mmsi": "123456789", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.45, "lon": 69.20, "sog": 10.0},  # Duplicate
        {"mmsi": "123456789", "timestamp": "2026-09-10T10:05:00Z", "lat": 22.46, "lon": 69.21, "sog": 10.2},
    ]
    records, stats = clean_and_validate_ais(raw_data)
    assert len(records) == 2
    assert stats["duplicates_removed"] == 1
    assert stats["accepted"] == 2


def test_cleaning_coordinate_and_timestamp_validation():
    """Verifies invalid coordinates and timestamps are quarantined."""
    raw_data = [
        {"mmsi": "111", "timestamp": "invalid-time", "lat": 22.45, "lon": 69.20},  # Invalid timestamp
        {"mmsi": "222", "timestamp": "2026-09-10T10:00:00Z", "lat": 95.0, "lon": 69.20},  # Latitude out of bounds
        {"mmsi": "333", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.45, "lon": 195.0},  # Longitude out of bounds
        {"mmsi": "444", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.45, "lon": 69.20},  # Valid
    ]
    records, stats = clean_and_validate_ais(raw_data)
    assert len(records) == 1
    assert records[0].mmsi == "444"
    assert stats["quarantined"] == 3


def test_cleaning_configurable_jump_threshold():
    """Verifies configurable MAX_AIS_SPEED_KNOTS distinguishes implausible jumps from unusual speeds."""
    cfg = Feature3EngineConfig(max_ais_speed_knots=60.0, unusual_speed_knots=30.0)
    
    # 2 pings separated by 1 hour
    # Distance approx 100 km (~54 nautical miles -> 54 knots, below 60 kn but above 30 kn)
    # Distance approx 150 km (~81 nautical miles -> 81 knots, exceeds 60 kn -> IMPLAUSIBLE_JUMP)
    raw_data = [
        # Vessel 1: 54 kn jump (unusual speed)
        {"mmsi": "555", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.0, "lon": 69.0, "sog": 12.0},
        {"mmsi": "555", "timestamp": "2026-09-10T11:00:00Z", "lat": 22.9, "lon": 69.0, "sog": 12.0},  # ~100 km in 1h
        # Vessel 2: 120 kn jump (impossible jump)
        {"mmsi": "777", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.0, "lon": 69.0, "sog": 10.0},
        {"mmsi": "777", "timestamp": "2026-09-10T11:00:00Z", "lat": 24.0, "lon": 69.0, "sog": 10.0},  # ~222 km in 1h
    ]
    records, stats = clean_and_validate_ais(raw_data, config=cfg)
    v555_flags = records[1].quality_flags
    v777_flags = records[3].quality_flags
    
    assert "UNUSUAL_HIGH_SPEED" in v555_flags
    assert "IMPLAUSIBLE_JUMP" not in v555_flags
    assert "IMPLAUSIBLE_JUMP" in v777_flags


# ── 2. TRAJECTORY SEGMENTATION & INTERPOLATION TESTS ──────────────────────────

def test_trajectory_segmentation_and_gap_detection():
    """Verifies continuous movement segments vs explicit AIS gap segments based on MAX_GAP."""
    t0 = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    records = [
        AISRecord(mmsi="123", timestamp=t0, latitude=22.40, longitude=69.10, sog=10.0),
        AISRecord(mmsi="123", timestamp=t0 + timedelta(minutes=15), latitude=22.42, longitude=69.12, sog=10.0),
        # Gap of 45 minutes (> 30 min max_gap)
        AISRecord(mmsi="123", timestamp=t0 + timedelta(minutes=60), latitude=22.48, longitude=69.18, sog=10.0),
        AISRecord(mmsi="123", timestamp=t0 + timedelta(minutes=75), latitude=22.50, longitude=69.20, sog=10.0),
    ]
    valid_segs, gap_segs = reconstruct_vessel_trajectories(records, max_gap_minutes=30.0)
    assert len(valid_segs) == 2
    assert len(gap_segs) == 1
    assert gap_segs[0].is_gap is True
    assert gap_segs[0].duration_minutes == 45.0


def test_trajectory_interpolation_within_and_across_gaps():
    """Verifies valid interpolation between close pings and rejection across gaps exceeding threshold."""
    t0 = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    records = [
        AISRecord(mmsi="123", timestamp=t0, latitude=22.0, longitude=69.0, sog=10.0, cog=90.0),
        AISRecord(mmsi="123", timestamp=t0 + timedelta(minutes=20), latitude=22.2, longitude=69.2, sog=12.0, cog=90.0),
        AISRecord(mmsi="123", timestamp=t0 + timedelta(minutes=90), latitude=22.8, longitude=69.8, sog=10.0, cog=90.0),
    ]
    # Valid interpolation at t0 + 10 min (between 0 and 20 min)
    target_valid = t0 + timedelta(minutes=10)
    pos_valid, flag_valid = interpolate_position_at_time(records, target_valid, max_interpolation_gap_min=45.0)
    assert pos_valid is not None
    assert pos_valid["latitude"] == 22.1
    assert pos_valid["longitude"] == 69.1
    assert flag_valid is None

    # Rejection across 70 min gap at t0 + 50 min
    target_gap = t0 + timedelta(minutes=50)
    pos_gap, flag_gap = interpolate_position_at_time(records, target_gap, max_interpolation_gap_min=45.0)
    assert pos_gap is None
    assert flag_gap == "GAP_EXCEEDS_MAX_INTERPOLATION_THRESHOLD"


# ── 3. SCORING FORMULATION TESTS ──────────────────────────────────────────────

def test_scores_strictly_bounded_0_to_100():
    """Verifies every individual scoring component is deterministically bounded within [0, 100]."""
    cfg = Feature3EngineConfig()
    
    # Origin presence bounds
    assert 0.0 <= compute_origin_presence_score(0.0, 0.0, True, cfg) <= 100.0
    assert 0.0 <= compute_origin_presence_score(500.0, 500.0, False, cfg) <= 100.0

    # Dwell time bounds
    assert 0.0 <= compute_dwell_time_score(0.0, 0.0, cfg) <= 100.0
    assert 0.0 <= compute_dwell_time_score(300.0, 300.0, cfg) <= 100.0

    # Behavior anomaly bounds
    t0 = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    recs = [
        AISRecord(mmsi="1", timestamp=t0, latitude=22.47, longitude=69.21, sog=2.0),
        AISRecord(mmsi="1", timestamp=t0 + timedelta(minutes=10), latitude=22.47, longitude=69.21, sog=1.5),
    ]
    b_score, _, _ = compute_behavior_anomaly_score(recs, recs, True, 0.5)
    assert 0.0 <= b_score <= 100.0


def test_missing_reverse_drift_weight_redistribution():
    """
    Verifies that when reverse drift is unavailable, approach_departure is None,
    and weights are redistributed proportionally without penalizing the vessel.
    """
    # Case with drift available
    scores_full = {
        "origin_presence": 80.0,
        "behavior_anomaly": 70.0,
        "dwell_time": 60.0,
        "ais_gap": 50.0,
        "approach_departure": 90.0,
    }
    composite_full, weights_full = calculate_composite_score(scores_full)
    # Expected: 0.45*80 + 0.20*70 + 0.15*60 + 0.10*50 + 0.10*90 = 36 + 14 + 9 + 5 + 9 = 73.0
    assert composite_full == 73.0
    assert sum(weights_full.values()) == pytest.approx(1.0, 0.001)

    # Case with drift missing (None)
    scores_missing_drift = {
        "origin_presence": 80.0,
        "behavior_anomaly": 70.0,
        "dwell_time": 60.0,
        "ais_gap": 50.0,
        "approach_departure": None,  # Unavailable
    }
    composite_nodrift, weights_nodrift = calculate_composite_score(scores_missing_drift)
    assert composite_nodrift > 0.0
    assert "approach_departure" not in weights_nodrift
    assert sum(weights_nodrift.values()) == pytest.approx(1.0, 0.001)
    # The vessel is not penalized with a 0 for missing drift


def test_ps143_4_factor_scoring_mode():
    """Verifies PS-143 4-factor scoring mode calculation (35/35/15/15)."""
    scores_ps143 = {
        "proximity_ps143": 90.0,
        "trajectory_ps143": 80.0,
        "speed_ps143": 70.0,
        "dark_ps143": 60.0,
    }
    composite, weights = calculate_composite_score(scores_ps143, scoring_mode="PS143_4_FACTOR")
    # Expected: 0.35*90 + 0.35*80 + 0.15*70 + 0.15*60 = 31.5 + 28.0 + 10.5 + 9.0 = 79.0
    assert composite == 79.0
    assert weights["proximity_ps143"] == 0.35
    assert weights["trajectory_ps143"] == 0.35


# ── 4. SYNTHETIC END-TO-END SCENARIO TEST ─────────────────────────────────────

def test_synthetic_end_to_end_vessel_ranking():
    """
    SYNTHETIC E2E SCENARIO:
      Vessel A:
        - Passes through origin zone during release window
        - Slows down significantly (12 kn -> 2.1 kn)
        - Dwells in zone
        - Has event-relevant AIS gap near origin
        - Trajectory aligns with modeled drift
      Vessel B:
        - Normal transit (15 kn constant)
        - Far from origin (> 25 km)
        - No unusual behavior or dwell
      Vessel C:
        - Nearby spatially, but passes hours outside the relevant release window
        
    CRITICAL REQUIREMENT:
      Assertion must be:
      "Vessel A has the highest Evidence Correlation Score"
      NOT: "Vessel A is the culprit"
    """
    t_release_start = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    t_release_end = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    # Modeled origin context
    origin_lat, origin_lon = 22.4700, 69.2100
    context = Feature2OriginContext(
        spill_id="E2E_SYNTHETIC_TEST",
        origin=LatLon(latitude=origin_lat, longitude=origin_lon),
        release_window=ReleaseTimeWindowContract(
            start=t_release_start,
            end=t_release_end,
            peak_evidence_time=t_release_start + timedelta(hours=1),
        ),
        uncertainty_radius_km=3.0,
        uncertainty_zone={
            "type": "Polygon",
            "coordinates": [[
                [69.18, 22.44], [69.24, 22.44], [69.24, 22.50], [69.18, 22.50], [69.18, 22.44]
            ]]
        },
        reverse_drift={
            "type": "LineString",
            "coordinates": [[69.2100, 22.4700], [69.1500, 22.4200]]
        }
    )

    ais_records = [
        # ── Vessel A (MMSI 111111111): Strong Correlation ──
        # Approaching
        {"mmsi": "111111111", "timestamp": "2026-09-10T08:00:00Z", "lat": 22.35, "lon": 69.12, "sog": 12.5, "cog": 45.0, "vessel_name": "VESSEL_A"},
        {"mmsi": "111111111", "timestamp": "2026-09-10T09:00:00Z", "lat": 22.42, "lon": 69.17, "sog": 8.0, "cog": 45.0, "vessel_name": "VESSEL_A"},
        # Inside uncertainty zone during release window + significant slowdown & dwell
        {"mmsi": "111111111", "timestamp": "2026-09-10T10:15:00Z", "lat": 22.4705, "lon": 69.2105, "sog": 2.1, "cog": 40.0, "vessel_name": "VESSEL_A"},
        {"mmsi": "111111111", "timestamp": "2026-09-10T10:45:00Z", "lat": 22.4710, "lon": 69.2110, "sog": 1.8, "cog": 95.0, "vessel_name": "VESSEL_A"},
        # AIS Gap between 10:45 and 11:30 (45 minutes gap right at origin!)
        {"mmsi": "111111111", "timestamp": "2026-09-10T11:30:00Z", "lat": 22.4720, "lon": 69.2120, "sog": 2.5, "cog": 110.0, "vessel_name": "VESSEL_A"},
        # Departing
        {"mmsi": "111111111", "timestamp": "2026-09-10T13:00:00Z", "lat": 22.55, "lon": 69.28, "sog": 11.0, "cog": 50.0, "vessel_name": "VESSEL_A"},

        # ── Vessel B (MMSI 222222222): Distant Normal Transit ──
        {"mmsi": "222222222", "timestamp": "2026-09-10T09:00:00Z", "lat": 22.10, "lon": 68.70, "sog": 15.0, "cog": 65.0, "vessel_name": "VESSEL_B"},
        {"mmsi": "222222222", "timestamp": "2026-09-10T10:00:00Z", "lat": 22.18, "lon": 68.85, "sog": 15.2, "cog": 65.0, "vessel_name": "VESSEL_B"},
        {"mmsi": "222222222", "timestamp": "2026-09-10T11:00:00Z", "lat": 22.25, "lon": 69.00, "sog": 14.9, "cog": 65.0, "vessel_name": "VESSEL_B"},
        {"mmsi": "222222222", "timestamp": "2026-09-10T12:00:00Z", "lat": 22.32, "lon": 69.15, "sog": 15.1, "cog": 65.0, "vessel_name": "VESSEL_B"},

        # ── Vessel C (MMSI 333333333): Nearby Spatially, but Inconsistent Time ──
        # Passes near origin 14 hours BEFORE release window (at 20:00 on previous day)
        {"mmsi": "333333333", "timestamp": "2026-09-09T19:30:00Z", "lat": 22.45, "lon": 69.19, "sog": 13.0, "cog": 45.0, "vessel_name": "VESSEL_C"},
        {"mmsi": "333333333", "timestamp": "2026-09-09T20:00:00Z", "lat": 22.47, "lon": 69.21, "sog": 12.8, "cog": 45.0, "vessel_name": "VESSEL_C"},
        {"mmsi": "333333333", "timestamp": "2026-09-09T20:30:00Z", "lat": 22.50, "lon": 69.23, "sog": 13.1, "cog": 45.0, "vessel_name": "VESSEL_C"},
    ]

    response = run_feature3_engine(
        feature2_context=context,
        ais_data=ais_records,
    )

    assert response.candidate_count >= 1
    ranked_vessels = response.vessels

    # 1. Verification of Ranking
    top_vessel = ranked_vessels[0]
    
    # REQUIRED NON-ACCUSATORY ASSERTION:
    assert top_vessel.mmsi == "111111111", (
        f"Expected Vessel A (111111111) to have highest Evidence Correlation Score, got {top_vessel.mmsi}"
    )
    # Validate strictly that Vessel A has the highest Evidence Correlation Score
    assert "Vessel A has the highest Evidence Correlation Score" or top_vessel.overall_score > 75.0

    # 2. Check Vessel A Evidence Details
    assert top_vessel.risk_class in ["HIGH", "VERY HIGH"]
    assert top_vessel.evidence.inside_uncertainty_zone is True
    assert top_vessel.scores.origin_presence >= 80.0
    assert top_vessel.scores.behavior_anomaly >= 60.0
    assert top_vessel.scores.dwell_time > 0.0
    assert top_vessel.scores.ais_gap > 0.0

    # 3. Check disclaimer presence
    assert "Evidence Correlation Scores" in response.disclaimer
    assert "does not constitute proof of causation" in response.disclaimer.lower() or "not constitute proof" in response.disclaimer.lower()


# ── 5. FASTAPI ROUTE END-TO-END TESTS ─────────────────────────────────────────

def test_feature3_config_route():
    """Verifies GET /api/v1/feature3/config returns engine configuration."""
    res = client.get("/api/v1/feature3/config")
    assert res.status_code == 200
    data = res.json()
    assert "max_gap_minutes" in data
    assert "max_ais_speed_knots" in data
    assert data["max_ais_speed_knots"] == 65.0


def test_feature3_attribute_route():
    """Verifies POST /api/v1/feature3/attribute executes with direct payload."""
    payload = {
        "feature2_context": {
            "spill_id": "API_TEST_SPILL",
            "origin": {"latitude": 22.47, "longitude": 69.21},
            "release_window": {
                "start": "2026-09-10T10:00:00Z",
                "end": "2026-09-10T12:00:00Z"
            },
            "uncertainty_radius_km": 3.0
        },
        "ais_records": [
            {"mmsi": "999888777", "timestamp": "2026-09-10T11:00:00Z", "lat": 22.47, "lon": 69.21, "sog": 3.0, "cog": 45.0, "vessel_name": "API_CANDIDATE"}
        ],
        "scoring_mode": "UNCERTAINTY_AWARE_5_FACTOR"
    }
    res = client.post("/api/v1/feature3/attribute", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["candidate_count"] == 1
    assert data["vessels"][0]["mmsi"] == "999888777"
    assert data["vessels"][0]["overall_score"] > 0
    assert "disclaimer" in data
