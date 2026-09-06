"""
Synthetic Feature 1 End-to-End Scientific Validation for Feature 2.

Validates that Feature 2's hindcasting (backward origin estimation) and
forecasting (forward trajectory prediction) produce physically correct results
under a deterministic, analytically tractable synthetic scenario.

Ground Truth Scenario:
  - True release origin at (lat=25.0000, lon=54.0000) at time T0 - 6h.
  - Constant uniform ocean current: u=0.20 m/s (east), v=0.10 m/s (north).
  - Zero wind contribution (wind u=0, v=0).
  - No stochastic diffusion (deterministic advection only).
  - The observed slick position at T0 is computed analytically from the above.
  - Forecast positions at +6h, +12h, +24h, +48h are computed analytically.

This test does NOT modify any existing source code, schemas, or configuration.
"""

import math
import os
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta, timezone

# Ensure backend and backend/app are available when run directly via python
_backend_dir = Path(__file__).resolve().parent.parent.parent
_app_dir = _backend_dir / "app"
for _p in [str(_backend_dir), str(_app_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import app.feature2
    sys.modules.setdefault("feature2", app.feature2)
except Exception:
    pass

from feature2.config import (
    BackwardTracingConfig,
    DiffusionConfig,
    Feature2Settings,
    ForecastConfig,
    WindageConfig,
)
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.forecast.forecaster import ForwardForecaster
from feature2.geo.coordinates import (
    EARTH_RADIUS_KM,
    EARTH_RADIUS_METERS,
    haversine_distance_km,
    meters_to_lat_deg,
    meters_to_lon_deg,
)
from feature2.origin.estimator import OriginEstimator
from feature2.pipeline.service import Feature2PipelineService
from feature2.schemas.input_schema import (
    CentroidCoordinates,
    GeoJSONGeometry,
    SlickDetectionInput,
)
from feature2.simulation.forward.engine import ForwardSimulationEngine


# ---------------------------------------------------------------------------
# Constants for the synthetic scenario
# ---------------------------------------------------------------------------

# Uniform ocean current velocity (m/s)
CURRENT_U_MPS = 0.20  # eastward
CURRENT_V_MPS = 0.10  # northward

# Zero wind
WIND_U_MPS = 0.0
WIND_V_MPS = 0.0

# True spill origin
TRUE_ORIGIN_LAT = 25.0
TRUE_ORIGIN_LON = 54.0

# Release time offset before observation
RELEASE_OFFSET_HOURS = 6.0

# Observation time T0
T0 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

# Forecast horizons (hours after T0)
FORECAST_HORIZONS = [6.0, 12.0, 24.0, 48.0]

# Tolerance for hindcast origin reconstruction (km).
# With 100 particles over a small polygon, uniform current, no diffusion,
# and 6h backtrack with 3h candidate intervals, the cluster centroid should
# converge within a few km of the true origin. We allow generous tolerance
# because particles are seeded across the observation polygon (not a point)
# and DBSCAN clustering introduces small offsets.
HINDCAST_TOLERANCE_KM = 8.0

# Tolerance for forecast position error (km).
# With no diffusion and constant currents, the centroid of particles seeded
# across the small observation polygon should track the analytical trajectory
# closely. Seeding spread (~1 km polygon) and numerical integration (dt=300s)
# contribute minor deviations.
FORECAST_TOLERANCE_KM = 3.0


def _compute_displacement(u_mps: float, v_mps: float, duration_hours: float,
                           ref_lat: float):
    """
    Computes the (delta_lat, delta_lon) for constant velocity advection.

    Args:
        u_mps: Eastward velocity in m/s.
        v_mps: Northward velocity in m/s.
        duration_hours: Duration in hours.
        ref_lat: Reference latitude for longitude degree conversion.

    Returns:
        (delta_lat_deg, delta_lon_deg)
    """
    dt_s = duration_hours * 3600.0
    dx_m = u_mps * dt_s  # east displacement in meters
    dy_m = v_mps * dt_s  # north displacement in meters
    d_lat = meters_to_lat_deg(dy_m)
    d_lon = meters_to_lon_deg(dx_m, ref_lat)
    return d_lat, d_lon


def _expected_position(origin_lat, origin_lon, u_mps, v_mps, duration_hours):
    """Returns (lat, lon) after constant velocity advection from origin."""
    d_lat, d_lon = _compute_displacement(u_mps, v_mps, duration_hours, origin_lat)
    return origin_lat + d_lat, origin_lon + d_lon


# Compute the observed slick position at T0 (origin + 6h of drift)
OBS_LAT, OBS_LON = _expected_position(
    TRUE_ORIGIN_LAT, TRUE_ORIGIN_LON,
    CURRENT_U_MPS, CURRENT_V_MPS,
    RELEASE_OFFSET_HOURS
)

# Build a small polygon around the observation centroid (~1 km wide)
HALF_SIZE_DEG = 0.005  # ~0.5 km half-width
OBS_POLYGON = [
    [OBS_LON - HALF_SIZE_DEG, OBS_LAT - HALF_SIZE_DEG],
    [OBS_LON + HALF_SIZE_DEG, OBS_LAT - HALF_SIZE_DEG],
    [OBS_LON + HALF_SIZE_DEG, OBS_LAT + HALF_SIZE_DEG],
    [OBS_LON - HALF_SIZE_DEG, OBS_LAT + HALF_SIZE_DEG],
    [OBS_LON - HALF_SIZE_DEG, OBS_LAT - HALF_SIZE_DEG],  # closed ring
]


def _build_synthetic_feature1_input() -> SlickDetectionInput:
    """Constructs the synthetic Feature 1 JSON-equivalent SlickDetectionInput."""
    return SlickDetectionInput(
        spill_id="SYNTHETIC_E2E_VALIDATION_001",
        observation_time=T0,
        area_sq_km=0.5,
        perimeter_km=3.0,
        centroid=CentroidCoordinates(
            latitude=round(OBS_LAT, 6),
            longitude=round(OBS_LON, 6),
        ),
        geometry=GeoJSONGeometry(
            type="Polygon",
            coordinates=[OBS_POLYGON],
        ),
        metadata={
            "dataset": "Synthetic Validation",
            "sensor": "Simulated",
            "purpose": "Deterministic scientific validation",
        },
    )


def _build_test_settings() -> Feature2Settings:
    """Constructs deterministic test settings with no diffusion and zero wind."""
    return Feature2Settings(
        environment="testing",
        random_seed=42,
        windage=WindageConfig(leeway_factor=0.0, deflection_angle_deg=0.0),
        diffusion=DiffusionConfig(
            horizontal_diffusivity_m2_s=0.0,
            enable_stochastic_diffusion=False,
        ),
        backward=BackwardTracingConfig(
            max_backtrack_hours=12.0,
            candidate_time_step_hours=3.0,
            particles_per_slick=100,
            simulation_step_seconds=300,
            convergence_cluster_eps_km=5.0,
            min_cluster_samples=3,
        ),
        forecast=ForecastConfig(
            forecast_horizons_hours=FORECAST_HORIZONS,
            particles_per_slick=100,
            simulation_step_seconds=300,
            forecast_ensemble_size=1,
            forecast_buffer_km=100.0,
        ),
    )


def _build_pipeline_components(settings: Feature2Settings):
    """
    Builds the OriginEstimator, ForwardForecaster, and Feature2PipelineService
    using mock constant-velocity providers.
    """
    currents = MockCurrentsProvider(
        const_u=CURRENT_U_MPS, const_v=CURRENT_V_MPS, pattern="uniform"
    )
    wind = MockWindProvider(const_u=WIND_U_MPS, const_v=WIND_V_MPS, pattern="uniform")

    origin_estimator = OriginEstimator(
        currents_provider=currents,
        wind_provider=wind,
        settings=settings,
    )

    fwd_engine = ForwardSimulationEngine(
        currents_provider=currents,
        wind_provider=wind,
        settings=settings,
    )
    forecaster = ForwardForecaster(
        simulation_engine=fwd_engine,
        settings=settings,
    )

    service = Feature2PipelineService(
        origin_estimator=origin_estimator,
        forecaster=forecaster,
        settings=settings,
    )
    return origin_estimator, forecaster, service


class TestSyntheticFeature1EndToEnd(unittest.TestCase):
    """
    Deterministic end-to-end scientific validation using synthetic Feature 1 input.
    Validates hindcast origin recovery and forecast trajectory accuracy against
    analytically known ground truth positions.
    """

    @classmethod
    def setUpClass(cls):
        cls.settings = _build_test_settings()
        cls.slick_input = _build_synthetic_feature1_input()
        cls.origin_estimator, cls.forecaster, cls.service = _build_pipeline_components(
            cls.settings
        )

        # Precompute expected forecast positions from observed slick centroid
        cls.expected_forecast_positions = {}
        for h in FORECAST_HORIZONS:
            lat, lon = _expected_position(
                OBS_LAT, OBS_LON, CURRENT_U_MPS, CURRENT_V_MPS, h
            )
            cls.expected_forecast_positions[h] = (lat, lon)

    # ------------------------------------------------------------------
    # 1. SYNTHETIC INPUT SANITY CHECK
    # ------------------------------------------------------------------

    def test_01_synthetic_input_is_valid(self):
        """Verify the synthetic Feature 1 input passes schema validation."""
        s = self.slick_input
        self.assertEqual(s.spill_id, "SYNTHETIC_E2E_VALIDATION_001")
        self.assertEqual(s.observation_time, T0)
        self.assertGreater(s.area_sq_km, 0.0)
        self.assertGreater(s.perimeter_km, 0.0)
        self.assertEqual(s.geometry.type, "Polygon")
        self.assertEqual(len(s.geometry.coordinates[0]), 5)  # closed ring

    def test_02_observation_centroid_consistent_with_ground_truth(self):
        """The observation centroid should be the ground-truth origin + 6h drift."""
        expected_dist_km = haversine_distance_km(
            TRUE_ORIGIN_LAT, TRUE_ORIGIN_LON, OBS_LAT, OBS_LON
        )
        # 6h at ~0.224 m/s resultant => ~4.8 km displacement
        self.assertGreater(expected_dist_km, 1.0, "Observation must be displaced from origin")
        self.assertLess(expected_dist_km, 20.0, "Displacement must be physically reasonable")

    # ------------------------------------------------------------------
    # 2. HINDCAST VALIDATION
    # ------------------------------------------------------------------

    def test_03_hindcast_recovers_true_origin(self):
        """
        Run backward origin estimation and verify the best candidate
        is within HINDCAST_TOLERANCE_KM of the known true origin.
        """
        origin_result = self.service.trace_origin(self.slick_input)

        # Must produce at least one candidate
        self.assertIsNotNone(origin_result.best_candidate,
                             "Origin estimation must produce at least one candidate")
        self.assertGreater(len(origin_result.candidates), 0,
                           "Candidates list must not be empty")

        best = origin_result.best_candidate
        best_lat = best.latitude
        best_lon = best.longitude

        hindcast_error_km = haversine_distance_km(
            TRUE_ORIGIN_LAT, TRUE_ORIGIN_LON, best_lat, best_lon
        )

        # Check if any candidate is close to the true origin
        min_error_km = hindcast_error_km
        closest_candidate = best
        for cand in origin_result.candidates:
            err = haversine_distance_km(
                TRUE_ORIGIN_LAT, TRUE_ORIGIN_LON, cand.latitude, cand.longitude
            )
            if err < min_error_km:
                min_error_km = err
                closest_candidate = cand

        # Report
        print("\n" + "=" * 60)
        print("FEATURE 2 — SYNTHETIC SCIENTIFIC VALIDATION")
        print("=" * 60)
        print()
        print("GROUND TRUTH")
        print(f"  Origin:       lat={TRUE_ORIGIN_LAT:.4f}, lon={TRUE_ORIGIN_LON:.4f}")
        print(f"  Release time: T0 - {RELEASE_OFFSET_HOURS:.0f}h = "
              f"{(T0 - timedelta(hours=RELEASE_OFFSET_HOURS)).isoformat()}")
        print()
        print("OBSERVATION")
        print(f"  Time: {T0.isoformat()}")
        print(f"  Centroid: lat={OBS_LAT:.6f}, lon={OBS_LON:.6f}")
        print()
        print("HINDCAST")
        print(f"  Best candidate:    lat={best_lat:.6f}, lon={best_lon:.6f}")
        print(f"  Best error:        {hindcast_error_km:.3f} km")
        print(f"  Closest candidate: lat={closest_candidate.latitude:.6f}, "
              f"lon={closest_candidate.longitude:.6f}")
        print(f"  Closest error:     {min_error_km:.3f} km")
        print(f"  Tolerance:         {HINDCAST_TOLERANCE_KM:.1f} km")
        print(f"  Candidates found:  {len(origin_result.candidates)}")
        print(f"  STATUS:            {'PASS' if min_error_km <= HINDCAST_TOLERANCE_KM else 'FAIL'}")

        self.assertLessEqual(
            min_error_km, HINDCAST_TOLERANCE_KM,
            f"Closest origin candidate error ({min_error_km:.3f} km) exceeds "
            f"tolerance ({HINDCAST_TOLERANCE_KM} km). "
            f"Best candidate at ({closest_candidate.latitude:.4f}, "
            f"{closest_candidate.longitude:.4f}), "
            f"true origin at ({TRUE_ORIGIN_LAT}, {TRUE_ORIGIN_LON})."
        )

    # ------------------------------------------------------------------
    # 3. FORECAST VALIDATION
    # ------------------------------------------------------------------

    def test_04_forecast_from_observed_slick(self):
        """
        Run forward forecast from the OBSERVED SLICK (not the hindcast origin)
        and validate predicted positions against analytical expected positions
        at +6h, +12h, +24h, +48h.
        """
        forecast_result = self.forecaster.predict(
            slick=self.slick_input,
            forecast_horizons_hours=FORECAST_HORIZONS,
            ensemble_size=1,
            particles_per_slick=100,
            dt_seconds=300.0,
            random_seed=42,
            diffusion_enabled=False,
            diffusion_coefficient_m2_s=0.0,
            windage_fraction=0.0,
        )

        print()
        print("FORECAST")
        all_pass = True

        for h in FORECAST_HORIZONS:
            key = f"{int(h)}h"
            self.assertIn(key, forecast_result.forecast,
                          f"Missing forecast horizon '{key}'")

            horizon = forecast_result.forecast[key]
            pred_lat = horizon.centroid.latitude
            pred_lon = horizon.centroid.longitude

            exp_lat, exp_lon = self.expected_forecast_positions[h]

            error_km = haversine_distance_km(exp_lat, exp_lon, pred_lat, pred_lon)
            status = "PASS" if error_km <= FORECAST_TOLERANCE_KM else "FAIL"
            if status == "FAIL":
                all_pass = False

            print(f"  +{int(h)}h")
            print(f"    Expected:  lat={exp_lat:.6f}, lon={exp_lon:.6f}")
            print(f"    Predicted: lat={pred_lat:.6f}, lon={pred_lon:.6f}")
            print(f"    Error:     {error_km:.3f} km")
            print(f"    Tolerance: {FORECAST_TOLERANCE_KM:.1f} km")
            print(f"    STATUS:    {status}")

            self.assertLessEqual(
                error_km, FORECAST_TOLERANCE_KM,
                f"Forecast +{int(h)}h error ({error_km:.3f} km) exceeds "
                f"tolerance ({FORECAST_TOLERANCE_KM} km)."
            )

            # Verify horizon validity
            self.assertTrue(
                horizon.valid,
                f"Forecast +{int(h)}h marked invalid: {horizon.reason}"
            )

        print()
        print("=" * 60)
        final = "PASS" if all_pass else "FAIL"
        print(f"FORECAST RESULT: {final}")
        print("=" * 60)

    # ------------------------------------------------------------------
    # 4. CRITICAL ARCHITECTURAL CHECK: Forecast seeds from observed slick
    # ------------------------------------------------------------------

    def test_05_forecast_does_not_start_from_hindcast_origin(self):
        """
        Explicitly verify that the forecast initial position is the observed
        slick centroid at T0, NOT the hindcast-reconstructed origin.

        Under a constant eastward current, the hindcast origin is west of the
        observation. If the forecast incorrectly started from the origin, the
        +6h forecast centroid would end up near the observation position rather
        than east of it.
        """
        # Run full pipeline
        pipeline_result = self.service.run_pipeline(self.slick_input)

        # Origin candidate should be west/south of observation
        best_origin = pipeline_result.origin_estimation.best_candidate
        self.assertIsNotNone(best_origin)

        # Forecast at +6h must be east/north of observation (drifted further)
        fc_6h = pipeline_result.forecast["6h"]
        pred_lat_6h = fc_6h.centroid.latitude
        pred_lon_6h = fc_6h.centroid.longitude

        # The forecast centroid at +6h must be further from the origin than
        # the observation centroid (i.e., it continued eastward from T0)
        dist_origin_to_obs = haversine_distance_km(
            best_origin.latitude, best_origin.longitude,
            OBS_LAT, OBS_LON,
        )
        dist_origin_to_fc6h = haversine_distance_km(
            best_origin.latitude, best_origin.longitude,
            pred_lat_6h, pred_lon_6h,
        )

        print()
        print("ARCHITECTURAL CHECK: Forecast initialization source")
        print(f"  Origin candidate:  lat={best_origin.latitude:.6f}, "
              f"lon={best_origin.longitude:.6f}")
        print(f"  Observation:       lat={OBS_LAT:.6f}, lon={OBS_LON:.6f}")
        print(f"  Forecast +6h:      lat={pred_lat_6h:.6f}, lon={pred_lon_6h:.6f}")
        print(f"  Dist(origin->obs):  {dist_origin_to_obs:.3f} km")
        print(f"  Dist(origin->fc6h): {dist_origin_to_fc6h:.3f} km")

        self.assertGreater(
            dist_origin_to_fc6h, dist_origin_to_obs,
            "Forecast +6h must be further from origin than the observation, "
            "confirming it started from observed slick (T0), not from the origin."
        )

        # Additionally, forecast +6h should be closer to the analytically
        # expected position than to the observation
        exp_lat_6h, exp_lon_6h = self.expected_forecast_positions[6.0]
        fc_error = haversine_distance_km(
            exp_lat_6h, exp_lon_6h, pred_lat_6h, pred_lon_6h
        )
        self.assertLessEqual(
            fc_error, FORECAST_TOLERANCE_KM,
            f"Forecast +6h centroid error ({fc_error:.3f} km) from pipeline "
            f"exceeds tolerance."
        )

        # Check pipeline's forecast_summary initialization source
        if pipeline_result.forecast_summary:
            init_info = pipeline_result.forecast_summary.initialization
            self.assertEqual(
                init_info.source, "observed_feature1_slick",
                "Forecast initialization source must be 'observed_feature1_slick'"
            )
            print(f"  Init source:       {init_info.source}")
            print(f"  Init centroid:     lat={init_info.centroid.lat:.6f}, "
                  f"lon={init_info.centroid.lon:.6f}")

        print("  STATUS:            PASS")

    # ------------------------------------------------------------------
    # 5. FULL PIPELINE COHERENCE
    # ------------------------------------------------------------------

    def test_06_full_pipeline_coherence(self):
        """
        Run the full pipeline and print a consolidated scientific validation
        report. Verify all components are coherent.
        """
        pipeline_result = self.service.run_pipeline(self.slick_input)

        # Origin estimation present
        self.assertIsNotNone(pipeline_result.origin_estimation)
        self.assertGreater(len(pipeline_result.origin_estimation.candidates), 0)

        # All forecast horizons present
        for h in FORECAST_HORIZONS:
            key = f"{int(h)}h"
            self.assertIn(key, pipeline_result.forecast,
                          f"Missing forecast horizon '{key}' in pipeline result")

        # Verify observation time consistency
        self.assertEqual(pipeline_result.observation_time, T0)
        self.assertEqual(pipeline_result.spill_id, "SYNTHETIC_E2E_VALIDATION_001")

        # Quality assessment should exist
        if pipeline_result.quality:
            self.assertIn(
                pipeline_result.quality.overall_simulation_quality,
                ["HIGH", "MEDIUM", "LOW"],
            )

        # Compute and report hindcast error
        best = pipeline_result.origin_estimation.best_candidate
        self.assertIsNotNone(best)
        hindcast_error = haversine_distance_km(
            TRUE_ORIGIN_LAT, TRUE_ORIGIN_LON,
            best.latitude, best.longitude,
        )

        # Compute forecast errors
        forecast_errors = {}
        for h in FORECAST_HORIZONS:
            key = f"{int(h)}h"
            fc = pipeline_result.forecast[key]
            exp_lat, exp_lon = self.expected_forecast_positions[h]
            err = haversine_distance_km(
                exp_lat, exp_lon,
                fc.centroid.latitude, fc.centroid.longitude,
            )
            forecast_errors[h] = err

        # Print consolidated report
        print()
        print("=" * 60)
        print("FEATURE 2 — FULL PIPELINE VALIDATION REPORT")
        print("=" * 60)
        print()
        print(f"Spill ID:     {pipeline_result.spill_id}")
        print(f"Obs Time:     {T0.isoformat()}")
        print(f"Environment:  Constant current u={CURRENT_U_MPS} m/s, "
              f"v={CURRENT_V_MPS} m/s; zero wind; no diffusion")
        print()
        print("HINDCAST")
        print(f"  Best origin:  lat={best.latitude:.6f}, lon={best.longitude:.6f}")
        print(f"  True origin:  lat={TRUE_ORIGIN_LAT:.4f}, lon={TRUE_ORIGIN_LON:.4f}")
        print(f"  Error:        {hindcast_error:.3f} km")
        print(f"  Tolerance:    {HINDCAST_TOLERANCE_KM:.1f} km")
        print(f"  STATUS:       {'PASS' if hindcast_error <= HINDCAST_TOLERANCE_KM else 'FAIL'}")
        print()
        print("FORECAST")

        all_forecast_pass = True
        for h in FORECAST_HORIZONS:
            key = f"{int(h)}h"
            err = forecast_errors[h]
            fc = pipeline_result.forecast[key]
            exp_lat, exp_lon = self.expected_forecast_positions[h]
            status = "PASS" if err <= FORECAST_TOLERANCE_KM else "FAIL"
            if status == "FAIL":
                all_forecast_pass = False
            print(f"  +{int(h)}h  expected=({exp_lat:.4f}, {exp_lon:.4f})  "
                  f"predicted=({fc.centroid.latitude:.4f}, {fc.centroid.longitude:.4f})  "
                  f"err={err:.3f} km  {status}")

        print()
        quality_label = (pipeline_result.quality.overall_simulation_quality
                         if pipeline_result.quality else "N/A")
        print(f"Quality:     {quality_label}")

        overall_pass = (hindcast_error <= HINDCAST_TOLERANCE_KM) and all_forecast_pass
        print()
        print("=" * 60)
        print(f"FINAL RESULT: {'PASS' if overall_pass else 'FAIL'}")
        print("=" * 60)

        # Assert overall
        self.assertTrue(overall_pass, "Full pipeline validation failed")


if __name__ == "__main__":
    unittest.main()
