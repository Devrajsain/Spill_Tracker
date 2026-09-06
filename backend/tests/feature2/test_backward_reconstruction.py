"""
Task 3C: Backward / Inverse Particle Reconstruction Foundation Test Suite.
Verifies:
  1. Reverse-time clock progression (T0, T0 - dt, T0 - 2dt, ...).
  2. Controlled forward -> backward synthetic known-source validation (non-circular).
  3. Source reconstruction haversine error metrics.
  4. Candidate release time generation (T0 - 3h, T0 - 6h, ..., in UTC).
  5. Reverse-time environmental provider querying at particle's actual locations and times.
  6. Multi-scene geographic and temporal isolation (Scene A vs Scene B).
  7. Out-of-coverage deactivation behavior without silent extrapolation.
  8. Zero backward duration edge case (duration = 0s).
  9. Non-divisible backward duration remainder stepping (e.g., 1000s with dt=300s).
 10. Windage combination in reverse time.
 11. Multi-horizon candidate evaluation utility.
 12. Input validations (dt <= 0, duration < 0, horizon <= 0, interval <= 0).
"""

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, List
import unittest
import numpy as np

from feature2.config import Feature2Settings, WindageConfig, BackwardTracingConfig
from feature2.data.base import (
    HistoricalCurrentProvider,
    HistoricalWindProvider,
    CurrentSample,
    WindSample,
)
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.geo.coordinates import haversine_distance_km
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.schemas.simulation_schema import (
    Particle,
    ForwardSimulationResult,
    BackwardSimulationResult,
    BackwardCandidateEvaluationResult,
)
from feature2.simulation.particles import ParticleManager
from feature2.simulation.forward.engine import simulate_forward
from feature2.simulation.backward.engine import (
    BackwardSimulationEngine,
    simulate_backward,
    generate_candidate_release_times,
    evaluate_backward_candidates,
)
from feature2.exceptions import OutOfDomainError


class RecordingHistoricalCurrentProvider(HistoricalCurrentProvider):
    """Logs every query with (lat, lon, timestamp) and returns constant velocity."""

    def __init__(self, u: float = 0.5, v: float = 0.2):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "recording_historical_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        self.query_log.append((latitude, longitude, timestamp))
        return CurrentSample(
            u_current_mps=self._u,
            v_current_mps=self._v,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class RecordingHistoricalWindProvider(HistoricalWindProvider):
    """Logs wind queries and returns constant wind velocity."""

    def __init__(self, u: float = 2.0, v: float = 1.0):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "recording_historical_wind_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_wind(self, latitude: float, longitude: float, timestamp: datetime) -> WindSample:
        self.query_log.append((latitude, longitude, timestamp))
        return WindSample(
            u_wind_mps=self._u,
            v_wind_mps=self._v,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class BoundedHistoricalCurrentProvider(HistoricalCurrentProvider):
    """Historical current provider that enforces a strict geographic bounding box."""

    def __init__(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float):
        self.min_lat = min_lat
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.max_lon = max_lon

    @property
    def provider_name(self) -> str:
        return "bounded_historical_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        if not (self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon):
            raise OutOfDomainError(f"Coordinate ({latitude}, {longitude}) is outside data coverage.")
        return CurrentSample(
            u_current_mps=0.4,
            v_current_mps=0.4,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class TestBackwardParticleReconstruction(unittest.TestCase):
    """Verification suite for Task 3C."""

    def setUp(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "feature2", "schemas", "sample_feature1_payload.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.f1_payload = SlickDetectionInput(**json.load(f))

        self.t0 = datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc)

    def test_01_reverse_time_clock_progression(self):
        """TEST 1: Verify backward timestamps decrease as T0, T0 - dt, T0 - 2dt, ..."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = RecordingHistoricalCurrentProvider(u=0.5, v=0.2)

        res = simulate_backward(
            initial_particles=p_init,
            observation_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=1200.0,
            current_provider=curr
        )

        states = res.trajectories[0].states
        self.assertEqual(len(states), 4)  # T0, T0 - 20m, T0 - 40m, T0 - 60m

        expected_timestamps = [
            self.t0,
            self.t0 - timedelta(seconds=1200),
            self.t0 - timedelta(seconds=2400),
            self.t0 - timedelta(seconds=3600),
        ]

        for s, exp_t in zip(states, expected_timestamps):
            self.assertEqual(s.timestamp, exp_t)

    def test_02_controlled_synthetic_known_source_recovery(self):
        """
        TEST 2 & TEST 3: Controlled synthetic forward -> backward known-source validation.
        Known source at (lat=25.0, lon=54.0) released at T_release.
        Moves forward for 2 hours under constant current u=0.5 m/s, v=0.3 m/s.
        Synthetic observed slick at T0 is then reconstructed backward for 2 hours.
        Reconstructed centroid must match the known source within numerical discretization tolerance (< 0.05 km).
        """
        t_release = datetime(2026, 8, 27, 4, 30, 0, tzinfo=timezone.utc)
        t_obs = self.t0  # 2 hours later
        known_source_lat = 25.0
        known_source_lon = 54.0
        duration_s = 7200.0  # 2 hours
        dt_s = 300.0

        known_source_particles = [
            Particle(
                particle_id=f"src_{i}",
                latitude=known_source_lat,
                longitude=known_source_lon,
                timestamp=t_release,
                active=True
            )
            for i in range(10)
        ]

        curr = RecordingHistoricalCurrentProvider(u=0.5, v=0.3)

        # 1. Forward simulation: T_release -> T_obs
        forward_res = simulate_forward(
            initial_particles=known_source_particles,
            start_time=t_release,
            duration_seconds=duration_s,
            dt_seconds=dt_s,
            current_provider=curr,
            diffusion_enabled=False
        )

        # Observed particles at T_obs
        observed_particles = [
            Particle(
                particle_id=traj.particle_id,
                latitude=traj.states[-1].latitude,
                longitude=traj.states[-1].longitude,
                timestamp=t_obs,
                active=True
            )
            for traj in forward_res.trajectories
        ]

        # 2. Backward reconstruction: T_obs -> T_release
        backward_res = simulate_backward(
            initial_particles=observed_particles,
            observation_time=t_obs,
            duration_seconds=duration_s,
            dt_seconds=dt_s,
            current_provider=curr
        )

        reconstructed_lat = backward_res.reconstructed_centroid_latitude
        reconstructed_lon = backward_res.reconstructed_centroid_longitude

        # Compute geodesic reconstruction error in km
        source_error_km = haversine_distance_km(
            reconstructed_lat, reconstructed_lon,
            known_source_lat, known_source_lon
        )

        # Geodesic difference should be negligible (< 50 meters = 0.05 km)
        self.assertLess(source_error_km, 0.05)
        self.assertAlmostEqual(reconstructed_lat, known_source_lat, places=4)
        self.assertAlmostEqual(reconstructed_lon, known_source_lon, places=4)

    def test_03_candidate_release_times_generation(self):
        """TEST 4: Verify discrete candidate release times are in UTC and spaced accurately."""
        horizon_h = 12.0
        interval_h = 3.0
        candidates = generate_candidate_release_times(
            observation_time=self.t0,
            horizon_hours=horizon_h,
            interval_hours=interval_h
        )

        self.assertEqual(len(candidates), 4)
        expected = [
            self.t0 - timedelta(hours=3),
            self.t0 - timedelta(hours=6),
            self.t0 - timedelta(hours=9),
            self.t0 - timedelta(hours=12),
        ]
        self.assertEqual(candidates, expected)
        for c in candidates:
            self.assertEqual(c.tzinfo, timezone.utc)

    def test_04_provider_queries_follow_moving_particle_in_reverse_time(self):
        """TEST 5: Verify historical provider queries use moving particle coordinates and historical clock."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = RecordingHistoricalCurrentProvider(u=1.0, v=0.5)

        logged = []

        def callback(p: Particle, u: float, v: float, t: datetime):
            logged.append((p.latitude, p.longitude, t))

        simulate_backward(
            initial_particles=p_init,
            observation_time=self.t0,
            duration_seconds=1800.0,
            dt_seconds=600.0,
            current_provider=curr,
            step_callback=callback
        )

        self.assertEqual(len(logged), 3)
        self.assertEqual(logged[0][2], self.t0)
        self.assertEqual(logged[1][2], self.t0 - timedelta(seconds=600))
        self.assertEqual(logged[2][2], self.t0 - timedelta(seconds=1200))

        # Backward coordinates must shift south-west (opposite to u=1.0, v=0.5)
        self.assertGreater(logged[0][0], logged[1][0])
        self.assertGreater(logged[1][0], logged[2][0])
        self.assertGreater(logged[0][1], logged[1][1])
        self.assertGreater(logged[1][1], logged[2][1])

    def test_05_multi_scene_spatial_and_temporal_isolation(self):
        """TEST 6: Verify Scene A (Persian Gulf) and Scene B (North Sea) are completely isolated."""
        scene_a_time = datetime(2026, 8, 27, 6, 30, tzinfo=timezone.utc)
        scene_a_p = [Particle(particle_id="sa_1", latitude=25.1, longitude=53.8, timestamp=scene_a_time)]

        scene_b_time = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)
        scene_b_p = [Particle(particle_id="sb_1", latitude=56.5, longitude=3.2, timestamp=scene_b_time)]

        curr_a = RecordingHistoricalCurrentProvider(u=0.5, v=0.0)
        curr_b = RecordingHistoricalCurrentProvider(u=0.2, v=0.1)

        res_a = simulate_backward(
            initial_particles=scene_a_p,
            observation_time=scene_a_time,
            duration_seconds=3600.0,
            dt_seconds=1800.0,
            current_provider=curr_a
        )

        res_b = simulate_backward(
            initial_particles=scene_b_p,
            observation_time=scene_b_time,
            duration_seconds=3600.0,
            dt_seconds=1800.0,
            current_provider=curr_b
        )

        # Scene A checks
        self.assertAlmostEqual(res_a.observation_time.timestamp(), scene_a_time.timestamp())
        self.assertAlmostEqual(res_a.reconstructed_centroid_latitude, 25.1, places=1)

        # Scene B checks
        self.assertAlmostEqual(res_b.observation_time.timestamp(), scene_b_time.timestamp())
        self.assertAlmostEqual(res_b.reconstructed_centroid_latitude, 56.5, places=1)

        # Confirm query logs are mutually exclusive
        lats_a = [q[0] for q in curr_a.query_log]
        lats_b = [q[0] for q in curr_b.query_log]
        self.assertTrue(all(24.0 < lat < 26.0 for lat in lats_a))
        self.assertTrue(all(55.0 < lat < 58.0 for lat in lats_b))

    def test_06_out_of_coverage_deactivation(self):
        """TEST 7: Verify particles leaving historical data coverage deactivate without extrapolation."""
        # Bounded box: lat [24.99, 25.02]
        bounded = BoundedHistoricalCurrentProvider(min_lat=24.99, max_lat=25.02, min_lon=53.0, max_lon=55.0)
        # Starting at 25.00. Current v=0.4 m/s -> backward moving south (v_back = -0.4 m/s)
        # In 3600s: displacement ~ -1440m -> lat shifts by ~ -0.013 deg -> crosses 24.99
        p_init = [Particle(particle_id="p_0001", latitude=25.00, longitude=54.0, timestamp=self.t0, active=True)]

        res = simulate_backward(
            initial_particles=p_init,
            observation_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=bounded
        )

        final_state = res.trajectories[0].states[-1]
        self.assertFalse(final_state.is_active)
        self.assertEqual(res.active_particle_count, 0)

    def test_07_zero_backward_duration(self):
        """TEST 8: duration = 0 returns initial state at T0 with 0 advection steps."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = RecordingHistoricalCurrentProvider()

        res = simulate_backward(
            initial_particles=p_init,
            observation_time=self.t0,
            duration_seconds=0.0,
            dt_seconds=600.0,
            current_provider=curr
        )

        self.assertEqual(len(res.trajectories[0].states), 1)
        self.assertEqual(res.trajectories[0].states[0].timestamp, self.t0)
        self.assertEqual(res.trajectories[0].states[0].latitude, 25.0)
        self.assertEqual(len(curr.query_log), 0)

    def test_08_non_divisible_backward_duration(self):
        """TEST 9: duration = 1000s with dt = 300s handles final 100s remainder step."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = RecordingHistoricalCurrentProvider(u=1.0, v=0.0)

        res = simulate_backward(
            initial_particles=p_init,
            observation_time=self.t0,
            duration_seconds=1000.0,
            dt_seconds=300.0,
            current_provider=curr
        )

        states = res.trajectories[0].states
        self.assertEqual(len(states), 5)  # T0, T0-300, T0-600, T0-900, T0-1000
        self.assertEqual(states[-1].timestamp, self.t0 - timedelta(seconds=1000))

    def test_09_windage_combination_in_reverse_time(self):
        """TEST 10: Verify current + leeway * windage correctly moves opposite to combined vector."""
        p_init = [Particle(particle_id="p_0001", latitude=0.0, longitude=0.0, timestamp=self.t0, active=True)]
        curr = RecordingHistoricalCurrentProvider(u=1.0, v=0.0)
        wind = RecordingHistoricalWindProvider(u=2.0, v=0.0)

        # Leeway 0.1 -> u_eff = 1.0 + 0.1 * 2.0 = 1.2 m/s eastward
        # In reverse time for 3600s: moves westward by 1.2 * 3600 = 4320 meters
        res = simulate_backward(
            initial_particles=p_init,
            observation_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=3600.0,
            current_provider=curr,
            wind_provider=wind,
            windage_fraction=0.1
        )

        final_state = res.trajectories[0].states[-1]
        dist_m = haversine_distance_km(0.0, 0.0, final_state.latitude, final_state.longitude) * 1000.0
        self.assertAlmostEqual(dist_m, 4320.0, delta=5.0)
        self.assertLess(final_state.longitude, 0.0)  # Westward

    def test_10_multi_horizon_candidate_evaluation(self):
        """TEST 11: Verify evaluate_backward_candidates produces structured candidates."""
        curr = RecordingHistoricalCurrentProvider(u=0.3, v=0.2)
        res = evaluate_backward_candidates(
            source=self.f1_payload,
            observation_time=self.t0,
            max_backtrack_hours=6.0,
            candidate_interval_hours=2.0,
            dt_seconds=1200.0,
            current_provider=curr
        )

        self.assertEqual(res.candidate_count, 3)  # T0 - 2h, T0 - 4h, T0 - 6h
        self.assertEqual(len(res.candidates), 3)

        cands = res.candidates
        self.assertEqual(cands[0].candidate_release_time, self.t0 - timedelta(hours=2))
        self.assertEqual(cands[1].candidate_release_time, self.t0 - timedelta(hours=4))
        self.assertEqual(cands[2].candidate_release_time, self.t0 - timedelta(hours=6))

        for c in cands:
            self.assertTrue(np.isfinite(c.reconstructed_centroid_latitude))
            self.assertTrue(np.isfinite(c.reconstructed_centroid_longitude))
            self.assertGreater(c.active_particle_count, 0)
            self.assertGreaterEqual(c.spatial_spread_radius_m, 0.0)

    def test_11_input_validations(self):
        """TEST 12: Input validations for dt <= 0, duration < 0, horizon <= 0, interval <= 0."""
        curr = RecordingHistoricalCurrentProvider()

        # dt <= 0
        with self.assertRaises(ValueError):
            simulate_backward(initial_particles=self.f1_payload, dt_seconds=0.0, current_provider=curr)

        # duration < 0
        with self.assertRaises(ValueError):
            simulate_backward(initial_particles=self.f1_payload, duration_seconds=-50.0, current_provider=curr)

        # candidate horizon <= 0
        with self.assertRaises(ValueError):
            generate_candidate_release_times(observation_time=self.t0, horizon_hours=0.0)

        # candidate interval <= 0
        with self.assertRaises(ValueError):
            generate_candidate_release_times(observation_time=self.t0, interval_hours=-2.0)


if __name__ == "__main__":
    unittest.main()
