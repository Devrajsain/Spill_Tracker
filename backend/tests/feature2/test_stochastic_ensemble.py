"""
Task 3B: Stochastic Diffusion & Ensemble Uncertainty Foundation Test Suite.
Verifies:
  1. Diffusion disabled reproduces exact Task 3A deterministic trajectory.
  2. Diffusion enabled with Kh = 0 reproduces Task 3A deterministic trajectory.
  3. Determinism: same seed + same inputs produces identical ensemble trajectories.
  4. Stochasticity: different seed + nonzero Kh produces different stochastic trajectories.
  5. Statistical physics sanity: Var(E) ≈ 2 * Kh * T and Var(N) ≈ 2 * Kh * T.
  6. Diffusion displacements are computed in physical meters, not degrees.
  7. Multi-member ensemble scaling (size = 1, 10, 50).
  8. Ensemble members and particle IDs remain distinguishable.
  9. Provider queries follow moving particles and independent simulation clock.
 10. Out-of-domain particles deactivate cleanly under diffusion without extrapolation.
 11. End-to-end integration from representative Feature 1 payload.
 12. Local metric spatial covariance and ensemble spread statistics.
 13. Numerical parameter validations (Kh >= 0, ensemble_size >= 1, dt > 0, duration >= 0).
"""

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, List, Optional
import unittest
import numpy as np

from feature2.config import Feature2Settings, DiffusionConfig, WindageConfig
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
    EnsembleSimulationResult,
    EnsembleStepStatistics,
)
from feature2.simulation.particles import ParticleManager
from feature2.simulation.forward.engine import (
    ForwardSimulationEngine,
    simulate_forward,
    simulate_ensemble,
)
from feature2.uncertainty.spatial_error import compute_ensemble_step_statistics
from feature2.exceptions import OutOfDomainError


class ZeroFlowCurrentProvider(HistoricalCurrentProvider):
    """Zero velocity current provider for pure diffusion verification."""

    def __init__(self):
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "zero_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        self.query_log.append((latitude, longitude, timestamp))
        return CurrentSample(
            u_current_mps=0.0,
            v_current_mps=0.0,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class UniformFlowCurrentProvider(HistoricalCurrentProvider):
    """Uniform current provider (u=0.5, v=0.2) for advection + diffusion tests."""

    def __init__(self, u: float = 0.5, v: float = 0.2):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "uniform_current_mock"

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


class BoundedDiffusionCurrentProvider(HistoricalCurrentProvider):
    """Current provider that throws OutOfDomainError outside a tight bounding box."""

    def __init__(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float):
        self.min_lat = min_lat
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.max_lon = max_lon

    @property
    def provider_name(self) -> str:
        return "bounded_diffusion_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        if not (self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon):
            raise OutOfDomainError(f"Coordinate ({latitude}, {longitude}) is outside data coverage.")
        return CurrentSample(
            u_current_mps=0.5,
            v_current_mps=0.5,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class TestStochasticDiffusionAndEnsemble(unittest.TestCase):
    """Verification suite for Task 3B."""

    def setUp(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "feature2", "schemas", "sample_feature1_payload.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.f1_payload = SlickDetectionInput(**json.load(f))

        self.t0 = datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc)

    def test_01_diffusion_disabled_reproduces_task3a(self):
        """TEST 1: diffusion_enabled = False must reproduce exact Task 3A deterministic trajectory."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = UniformFlowCurrentProvider(u=0.8, v=0.3)

        # Run with diffusion explicitly False
        res_no_diff = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr,
            diffusion_enabled=False
        )

        # Run with pure deterministic default
        res_deterministic = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr
        )

        states_a = res_no_diff.trajectories[0].states
        states_b = res_deterministic.trajectories[0].states
        self.assertEqual(len(states_a), len(states_b))

        for sa, sb in zip(states_a, states_b):
            self.assertEqual(sa.latitude, sb.latitude)
            self.assertEqual(sa.longitude, sb.longitude)
            self.assertEqual(sa.timestamp, sb.timestamp)

    def test_02_diffusion_enabled_with_zero_kh_reproduces_task3a(self):
        """TEST 2: diffusion_enabled = True with Kh = 0.0 must reproduce exact Task 3A trajectory."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = UniformFlowCurrentProvider(u=0.8, v=0.3)

        res_zero_kh = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=0.0
        )

        res_deterministic = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr
        )

        states_zero = res_zero_kh.trajectories[0].states
        states_det = res_deterministic.trajectories[0].states

        for sz, sd in zip(states_zero, states_det):
            self.assertEqual(sz.latitude, sd.latitude)
            self.assertEqual(sz.longitude, sd.longitude)

    def test_03_same_seed_produces_identical_ensemble_results(self):
        """TEST 3: Same seed + same inputs must produce identical ensemble trajectories."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = UniformFlowCurrentProvider(u=0.5, v=0.1)

        res1 = simulate_ensemble(
            source=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            ensemble_size=3,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=25.0,
            random_seed=42
        )

        res2 = simulate_ensemble(
            source=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            ensemble_size=3,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=25.0,
            random_seed=42
        )

        self.assertEqual(len(res1.trajectories), len(res2.trajectories))
        for t1, t2 in zip(res1.trajectories, res2.trajectories):
            self.assertEqual(t1.particle_id, t2.particle_id)
            for s1, s2 in zip(t1.states, t2.states):
                self.assertAlmostEqual(s1.latitude, s2.latitude, places=10)
                self.assertAlmostEqual(s1.longitude, s2.longitude, places=10)

    def test_04_different_seed_produces_different_stochastic_trajectories(self):
        """TEST 4: Different seeds with nonzero Kh must produce different stochastic trajectories."""
        p_init = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr = UniformFlowCurrentProvider(u=0.5, v=0.1)

        res_seed_a = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=50.0,
            random_seed=101
        )

        res_seed_b = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=50.0,
            random_seed=202
        )

        final_a = res_seed_a.trajectories[0].states[-1]
        final_b = res_seed_b.trajectories[0].states[-1]

        # Different stochastic realizations should produce different endpoints
        self.assertNotEqual(final_a.latitude, final_b.latitude)
        self.assertNotEqual(final_a.longitude, final_b.longitude)

    def test_05_statistical_diffusion_sanity_einstein_relation(self):
        """
        TEST 5: Statistical diffusion sanity test.
        Zero current and zero wind.
        For total time T = 1800 s, Kh = 10.0 m^2/s:
          Expected theoretical variance: Var(E) = Var(N) = 2 * Kh * T = 2 * 10 * 1800 = 36,000 m^2.
        Verify empirical variance across 600 particles matches theoretical within 25% statistical tolerance.
        """
        num_particles = 600
        kh = 10.0
        duration = 1800.0
        dt = 300.0

        init_particles = [
            Particle(particle_id=f"p_{i:04d}", latitude=0.0, longitude=0.0, timestamp=self.t0, active=True)
            for i in range(num_particles)
        ]
        zero_curr = ZeroFlowCurrentProvider()

        result = simulate_forward(
            initial_particles=init_particles,
            start_time=self.t0,
            duration_seconds=duration,
            dt_seconds=dt,
            current_provider=zero_curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=kh,
            random_seed=98765
        )

        final_stats = result.step_statistics[-1]
        var_e = final_stats.variance_east_m2
        var_n = final_stats.variance_north_m2

        expected_var = 2.0 * kh * duration  # 36,000 m^2
        # Statistical tolerance (central limit theorem on 600 sample variance: ~20-25%)
        self.assertAlmostEqual(var_e, expected_var, delta=expected_var * 0.25)
        self.assertAlmostEqual(var_n, expected_var, delta=expected_var * 0.25)

    def test_06_diffusion_displacement_calculated_in_meters_not_degrees(self):
        """
        TEST 6: Verify diffusion displacement is evaluated in physical meters.
        At latitude 60°N, 1 degree longitude is half the metric distance of 1 degree longitude at Equator.
        Eastward physical variance in meters must remain invariant to latitude.
        """
        kh = 20.0
        dt = 600.0
        duration = 600.0
        n_p = 400

        # Run at Equator (lat 0.0)
        p_eq = [Particle(particle_id=f"eq_{i}", latitude=0.0, longitude=0.0, timestamp=self.t0) for i in range(n_p)]
        res_eq = simulate_forward(
            initial_particles=p_eq,
            start_time=self.t0,
            duration_seconds=duration,
            dt_seconds=dt,
            current_provider=ZeroFlowCurrentProvider(),
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=kh,
            random_seed=123
        )

        # Run at 60°N
        p_60 = [Particle(particle_id=f"n60_{i}", latitude=60.0, longitude=0.0, timestamp=self.t0) for i in range(n_p)]
        res_60 = simulate_forward(
            initial_particles=p_60,
            start_time=self.t0,
            duration_seconds=duration,
            dt_seconds=dt,
            current_provider=ZeroFlowCurrentProvider(),
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=kh,
            random_seed=123
        )

        var_e_eq = res_eq.step_statistics[-1].variance_east_m2
        var_e_60 = res_60.step_statistics[-1].variance_east_m2

        expected_var = 2.0 * kh * duration  # 24,000 m^2
        # Both must produce ~24,000 m^2 in local metric coordinates
        self.assertAlmostEqual(var_e_eq, expected_var, delta=expected_var * 0.30)
        self.assertAlmostEqual(var_e_60, expected_var, delta=expected_var * 0.30)

        # But in raw angular degrees, the 60°N spread should be roughly double that of the Equator
        deg_spread_eq = np.std([s.states[-1].longitude for s in res_eq.trajectories])
        deg_spread_60 = np.std([s.states[-1].longitude for s in res_60.trajectories])
        self.assertGreater(deg_spread_60, deg_spread_eq * 1.5)

    def test_07_ensemble_size_scaling(self):
        """TEST 7: Verify ensemble_size = 1, 5, 10 produces the correct number of ensemble realizations."""
        curr = UniformFlowCurrentProvider()

        for size in [1, 5, 10]:
            res = simulate_ensemble(
                source=self.f1_payload,
                start_time=self.t0,
                duration_seconds=1200.0,
                dt_seconds=600.0,
                ensemble_size=size,
                particles_per_member=5,
                current_provider=curr,
                random_seed=42
            )
            self.assertEqual(res.ensemble_size, size)
            self.assertEqual(res.particles_per_member, 5)
            self.assertEqual(res.total_trajectories_count, size * 5)
            self.assertEqual(len(res.trajectories), size * 5)

    def test_08_ensemble_members_remain_distinguishable(self):
        """TEST 8: Verify ensemble members have distinct ensemble_member_id and globally unique particle IDs."""
        curr = UniformFlowCurrentProvider()
        res = simulate_ensemble(
            source=self.f1_payload,
            start_time=self.t0,
            duration_seconds=1200.0,
            dt_seconds=600.0,
            ensemble_size=4,
            particles_per_member=6,
            current_provider=curr,
            random_seed=55
        )

        member_ids = set()
        particle_ids = set()
        for traj in res.trajectories:
            member_ids.add(traj.ensemble_member_id)
            self.assertNotIn(traj.particle_id, particle_ids)
            particle_ids.add(traj.particle_id)
            for state in traj.states:
                self.assertEqual(state.ensemble_member_id, traj.ensemble_member_id)

        self.assertEqual(member_ids, {0, 1, 2, 3})
        self.assertEqual(len(particle_ids), 24)

    def test_09_provider_query_tracks_moving_particles_and_clock(self):
        """TEST 9: Verify environmental provider queries follow particle positions and advancing simulation clock."""
        p_init = [Particle(particle_id="p_0001", latitude=24.5, longitude=54.1, timestamp=self.t0, active=True)]
        curr = UniformFlowCurrentProvider(u=2.0, v=1.0)

        logged = []

        def callback(p: Particle, u: float, v: float, t: datetime):
            logged.append((p.latitude, p.longitude, t))

        simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=1800.0,
            dt_seconds=600.0,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=10.0,
            random_seed=42,
            step_callback=callback
        )

        self.assertEqual(len(logged), 3)
        self.assertEqual(logged[0][2], self.t0)
        self.assertEqual(logged[1][2], self.t0 + timedelta(seconds=600))
        self.assertEqual(logged[2][2], self.t0 + timedelta(seconds=1200))

        # Spatial positions must change continuously
        self.assertNotEqual(logged[0][0], logged[1][0])
        self.assertNotEqual(logged[1][0], logged[2][0])

    def test_10_out_of_domain_particles_deactivate_cleanly(self):
        """TEST 10: Particles leaving coverage are deactivated without silent extrapolation."""
        bounded_curr = BoundedDiffusionCurrentProvider(
            min_lat=24.0, max_lat=25.02, min_lon=53.0, max_lon=54.0
        )
        p_init = [Particle(particle_id="p_0001", latitude=25.015, longitude=53.5, timestamp=self.t0, active=True)]

        # Northward drift (v=0.1 m/s) + diffusion will cross 25.02
        res = simulate_forward(
            initial_particles=p_init,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=300.0,
            current_provider=bounded_curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=15.0,
            random_seed=42
        )

        final_state = res.trajectories[0].states[-1]
        self.assertFalse(final_state.is_active)

    def test_11_real_feature1_domain_integration(self):
        """TEST 11: End-to-end integration from representative Feature 1 payload without hardcoded coordinates."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so, buffer_distance_km=40.0)

        curr = MockCurrentsProvider()
        wind = MockWindProvider()

        res = simulate_ensemble(
            source=so,
            start_time=so.observation_time,
            duration_seconds=7200.0,  # 2 hours
            dt_seconds=1800.0,
            ensemble_size=3,
            particles_per_member=10,
            current_provider=curr,
            wind_provider=wind,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=15.0,
            random_seed=888,
            query_domain=eq
        )

        self.assertEqual(res.ensemble_size, 3)
        self.assertEqual(res.total_trajectories_count, 30)
        self.assertEqual(len(res.step_statistics), 5)  # T0 + 4 steps

        for stat in res.step_statistics:
            self.assertTrue(np.isfinite(stat.mean_latitude))
            self.assertTrue(np.isfinite(stat.mean_longitude))
            self.assertGreaterEqual(stat.spread_radius_m, 0.0)

    def test_12_ensemble_statistics_content_and_covariance_structure(self):
        """TEST 12: Verify step statistics 2x2 covariance matrix is symmetric, finite, and derived from members."""
        curr = UniformFlowCurrentProvider(u=0.2, v=0.2)
        res = simulate_ensemble(
            source=self.f1_payload,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=1200.0,
            ensemble_size=5,
            particles_per_member=8,
            current_provider=curr,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=30.0,
            random_seed=42
        )

        for stat in res.step_statistics:
            cov = stat.covariance_matrix_m2
            self.assertEqual(len(cov), 2)
            self.assertEqual(len(cov[0]), 2)
            self.assertEqual(len(cov[1]), 2)

            # Symmetry: cov_EN == cov_NE
            self.assertAlmostEqual(cov[0][1], cov[1][0], places=6)
            # Diagonal variances >= 0
            self.assertGreaterEqual(cov[0][0], 0.0)
            self.assertGreaterEqual(cov[1][1], 0.0)

            # Finite checks
            self.assertTrue(np.isfinite(stat.variance_east_m2))
            self.assertTrue(np.isfinite(stat.variance_north_m2))
            self.assertTrue(np.isfinite(stat.covariance_en_m2))
            self.assertTrue(np.isfinite(stat.spread_radius_m))

    def test_13_input_validations(self):
        """TEST 13: Numerical validation for ensemble_size < 1, dt <= 0, duration < 0, Kh < 0."""
        curr = UniformFlowCurrentProvider()

        # ensemble_size < 1
        with self.assertRaises(ValueError):
            simulate_ensemble(source=self.f1_payload, ensemble_size=0, current_provider=curr)

        # dt <= 0
        with self.assertRaises(ValueError):
            simulate_ensemble(source=self.f1_payload, dt_seconds=0.0, current_provider=curr)

        # duration < 0
        with self.assertRaises(ValueError):
            simulate_ensemble(source=self.f1_payload, duration_seconds=-100.0, current_provider=curr)

        # Kh < 0
        with self.assertRaises(ValueError):
            simulate_ensemble(
                source=self.f1_payload,
                diffusion_coefficient_m2_s=-5.0,
                current_provider=curr
            )


if __name__ == "__main__":
    unittest.main()
