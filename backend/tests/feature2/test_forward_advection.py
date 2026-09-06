"""
Task 3A: Forward Particle Advection Engine Test Suite.
Verifies:
  1. Deterministic particle initialization from Feature 1 spill polygon
  2. First-order Euler advection with exact geodesic conversion (dx/dt = u, dy/dt = v)
  3. Continuous simulation clock advancement (provider_time == particle.timestamp)
  4. Explicit windage combination (u_eff = u_curr + leeway * u_wind)
  5. Multi-particle isolation and trajectory completeness
  6. Out-of-coverage deactivation semantics (no silent clamping)
  7. Input validation (dt <= 0, duration < 0, empty particle sets)
  8. End-to-end integration from Feature 1 Sentinel-1 payload
"""

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, List, Optional
import unittest
import numpy as np

from feature2.config import Feature2Settings, WindageConfig
from feature2.data.base import (
    EnvironmentalDataProvider,
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
from feature2.schemas.simulation_schema import Particle, ForwardSimulationResult
from feature2.simulation.particles import ParticleManager
from feature2.simulation.forward.engine import ForwardSimulationEngine, simulate_forward
from feature2.exceptions import EnvironmentalCoverageError, OutOfDomainError


class ConstantCurrentProvider(HistoricalCurrentProvider):
    """Deterministic mock ocean current provider with constant (u, v) across space and time."""

    def __init__(self, u: float = 1.0, v: float = 0.0):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "constant_current_mock"

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


class ConstantWindProvider(HistoricalWindProvider):
    """Deterministic mock surface wind provider with constant (u, v) across space and time."""

    def __init__(self, u: float = 2.0, v: float = 0.0):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "constant_wind_mock"

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


class BoundedMockCurrentProvider(HistoricalCurrentProvider):
    """Mock current provider that raises OutOfDomainError outside a specified bounding box."""

    def __init__(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float):
        self.min_lat = min_lat
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.max_lon = max_lon

    @property
    def provider_name(self) -> str:
        return "bounded_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        if not (self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon):
            raise OutOfDomainError(f"Coordinate ({latitude}, {longitude}) is outside bounded coverage.")
        return CurrentSample(
            u_current_mps=1.0,
            v_current_mps=0.0,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class TestForwardParticleAdvection(unittest.TestCase):
    """Unit and integration test cases for Task 3A."""

    def setUp(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "feature2", "schemas", "sample_feature1_payload.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.f1_payload = SlickDetectionInput(**json.load(f))

        self.t0 = datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc)

    def test_01_particle_initialization_from_spill_polygon(self):
        """Verify particles are initialized inside the Feature 1 polygon boundary."""
        particles = ParticleManager.seed_particles(self.f1_payload, num_particles=20, random_seed=42)

        self.assertEqual(len(particles), 20)
        # Unique IDs
        ids = [p.particle_id for p in particles]
        self.assertEqual(len(set(ids)), 20)

        # All particles start at T0
        for p in particles:
            self.assertEqual(p.timestamp, self.f1_payload.observation_time)
            self.assertTrue(p.active)
            self.assertEqual(p.age_seconds, 0.0)
            # Spatially inside source bounding box
            self.assertTrue(25.11 <= p.latitude <= 25.14)
            self.assertTrue(53.82 <= p.longitude <= 53.87)

    def test_02_deterministic_particle_initialization(self):
        """Identical seed and payload produce exact same initial positions."""
        particles_1 = ParticleManager.seed_particles(self.f1_payload, num_particles=30, random_seed=99)
        particles_2 = ParticleManager.seed_particles(self.f1_payload, num_particles=30, random_seed=99)

        for p1, p2 in zip(particles_1, particles_2):
            self.assertEqual(p1.particle_id, p2.particle_id)
            self.assertAlmostEqual(p1.latitude, p2.latitude, places=7)
            self.assertAlmostEqual(p1.longitude, p2.longitude, places=7)

    def test_03_geographic_movement_conversion(self):
        """
        Section 18 Geo Test Case:
        u = 1.0 m/s, v = 0.0 m/s, duration = 3600 s.
        Expected eastward displacement ≈ 3600 meters.
        """
        init_p = [Particle(particle_id="p_0001", latitude=0.0, longitude=0.0, timestamp=self.t0, active=True)]
        curr_prov = ConstantCurrentProvider(u=1.0, v=0.0)

        result = simulate_forward(
            initial_particles=init_p,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=600.0,
            current_provider=curr_prov,
            windage_fraction=0.0
        )

        final_state = result.trajectories[0].states[-1]
        self.assertEqual(final_state.latitude, 0.0)

        # Great-circle distance between (0.0, 0.0) and (0.0, final_lon)
        dist_km = haversine_distance_km(0.0, 0.0, final_state.latitude, final_state.longitude)
        dist_meters = dist_km * 1000.0

        # Expected displacement: 3600 meters within numerical tolerance (< 0.1%)
        self.assertAlmostEqual(dist_meters, 3600.0, delta=3.0)

    def test_04_timestamp_progression(self):
        """
        Section 19 Time Test Case:
        T0 = known UTC, dt = 1h (3600s), duration = 3h (10800s).
        Expected timestamps: T0, T0 + 1h, T0 + 2h, T0 + 3h.
        """
        init_p = [Particle(particle_id="p_0001", latitude=10.0, longitude=50.0, timestamp=self.t0, active=True)]
        curr_prov = ConstantCurrentProvider(u=0.5, v=0.5)

        result = simulate_forward(
            initial_particles=init_p,
            start_time=self.t0,
            duration_seconds=10800.0,
            dt_seconds=3600.0,
            current_provider=curr_prov,
            windage_fraction=0.0
        )

        states = result.trajectories[0].states
        self.assertEqual(len(states), 4)

        expected_times = [
            self.t0,
            self.t0 + timedelta(hours=1),
            self.t0 + timedelta(hours=2),
            self.t0 + timedelta(hours=3),
        ]
        for state, exp_time in zip(states, expected_times):
            self.assertEqual(state.timestamp, exp_time)

    def test_05_windage_combination(self):
        """
        Section 20 Windage Test Case:
        Current: u = 1.0 m/s, v = 0.0
        Wind: u = 2.0 m/s, v = 0.0
        windage_fraction = 0.1
        Expected u_effective = 1.0 + 0.1 * 2.0 = 1.2 m/s.
        Over 3600s, total eastward displacement ≈ 4320 meters.
        """
        init_p = [Particle(particle_id="p_0001", latitude=0.0, longitude=0.0, timestamp=self.t0, active=True)]
        curr_prov = ConstantCurrentProvider(u=1.0, v=0.0)
        wind_prov = ConstantWindProvider(u=2.0, v=0.0)

        # Custom settings with 0 deg deflection
        cfg = Feature2Settings(windage=WindageConfig(leeway_factor=0.1, deflection_angle_deg=0.0))

        result = simulate_forward(
            initial_particles=init_p,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=3600.0,
            current_provider=curr_prov,
            wind_provider=wind_prov,
            windage_fraction=0.1,
            config=cfg
        )

        final_state = result.trajectories[0].states[-1]
        dist_km = haversine_distance_km(0.0, 0.0, final_state.latitude, final_state.longitude)
        dist_meters = dist_km * 1000.0

        # Expected: 1.2 m/s * 3600s = 4320 meters
        self.assertAlmostEqual(dist_meters, 4320.0, delta=4.0)

    def test_06_deterministic_simulation(self):
        """Section 21 Determinism Test: identical runs produce identical trajectories."""
        particles = ParticleManager.seed_particles(self.f1_payload, num_particles=15, random_seed=77)
        curr_prov = MockCurrentsProvider(const_u=0.3, const_v=0.1)
        wind_prov = MockWindProvider(const_u=5.0, const_v=2.0)

        res_a = simulate_forward(
            initial_particles=particles,
            start_time=self.t0,
            duration_seconds=7200.0,
            dt_seconds=1800.0,
            current_provider=curr_prov,
            wind_provider=wind_prov
        )
        res_b = simulate_forward(
            initial_particles=particles,
            start_time=self.t0,
            duration_seconds=7200.0,
            dt_seconds=1800.0,
            current_provider=curr_prov,
            wind_provider=wind_prov
        )

        for traj_a, traj_b in zip(res_a.trajectories, res_b.trajectories):
            self.assertEqual(traj_a.particle_id, traj_b.particle_id)
            for sa, sb in zip(traj_a.states, traj_b.states):
                self.assertAlmostEqual(sa.latitude, sb.latitude, places=8)
                self.assertAlmostEqual(sa.longitude, sb.longitude, places=8)
                self.assertEqual(sa.timestamp, sb.timestamp)

    def test_07_multi_particle_isolation_and_completeness(self):
        """Section 22: multiple particles maintain unique IDs and separate trajectory state histories."""
        particles = ParticleManager.seed_particles(self.f1_payload, num_particles=10, random_seed=123)
        curr_prov = ConstantCurrentProvider(u=0.2, v=0.1)

        result = simulate_forward(
            initial_particles=particles,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=1200.0,
            current_provider=curr_prov,
            windage_fraction=0.0
        )

        self.assertEqual(len(result.trajectories), 10)
        seen_ids = set()
        for traj in result.trajectories:
            self.assertNotIn(traj.particle_id, seen_ids)
            seen_ids.add(traj.particle_id)
            # 3600s / 1200s = 3 steps -> 4 states (T0, T0+1200, T0+2400, T0+3600)
            self.assertEqual(len(traj.states), 4)

    def test_08_real_feature1_domain_integration(self):
        """Section 23: end-to-end integration starting from real Feature 1 Sentinel-1 payload."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so, buffer_distance_km=50.0)

        particles = ParticleManager.seed_particles(so, num_particles=12, random_seed=42)
        curr_prov = MockCurrentsProvider()
        wind_prov = MockWindProvider()

        result = simulate_forward(
            initial_particles=particles,
            start_time=so.observation_time,
            duration_seconds=21600.0,  # 6 hours
            dt_seconds=3600.0,
            current_provider=curr_prov,
            wind_provider=wind_prov,
            query_domain=eq
        )

        self.assertEqual(result.start_time, so.observation_time)
        self.assertEqual(result.end_time, so.observation_time + timedelta(hours=6))
        self.assertEqual(result.particle_count, 12)
        for traj in result.trajectories:
            self.assertEqual(len(traj.states), 7)  # T0 + 6 steps

    def test_09_provider_queries_follow_moving_particle_position_and_clock(self):
        """Section 24: provider queries track the moving particle coordinates and advancing clock."""
        init_p = [Particle(particle_id="p_0001", latitude=24.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr_prov = ConstantCurrentProvider(u=10.0, v=0.0)  # fast velocity to ensure noticeable motion

        logged_queries = []

        def trace_callback(p: Particle, u: float, v: float, t: datetime):
            logged_queries.append((p.latitude, p.longitude, t))

        simulate_forward(
            initial_particles=init_p,
            start_time=self.t0,
            duration_seconds=3600.0,
            dt_seconds=1200.0,
            current_provider=curr_prov,
            step_callback=trace_callback,
            windage_fraction=0.0
        )

        # 3 query steps at t = 0, 1200, 2400
        self.assertEqual(len(logged_queries), 3)

        # Longitude must strictly increase across queries
        self.assertLess(logged_queries[0][1], logged_queries[1][1])
        self.assertLess(logged_queries[1][1], logged_queries[2][1])

        # Timestamps must strictly increase
        self.assertEqual(logged_queries[0][2], self.t0)
        self.assertEqual(logged_queries[1][2], self.t0 + timedelta(seconds=1200))
        self.assertEqual(logged_queries[2][2], self.t0 + timedelta(seconds=2400))

    def test_10_out_of_domain_behavior_deactivates_particle(self):
        """Section 25: particle moving outside available dataset coverage is deactivated without crashing or clamping."""
        # Grid bounded between lat[24.0, 26.0], lon[54.0, 54.02]
        bounded_prov = BoundedMockCurrentProvider(min_lat=24.0, max_lat=26.0, min_lon=54.0, max_lon=54.02)
        init_p = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.015, timestamp=self.t0, active=True)]

        # Move fast eastward (10 m/s) -> will breach 54.02 within a few steps
        result = simulate_forward(
            initial_particles=init_p,
            start_time=self.t0,
            duration_seconds=7200.0,
            dt_seconds=600.0,
            current_provider=bounded_prov,
            windage_fraction=0.0
        )

        traj = result.trajectories[0]
        final_state = traj.states[-1]
        # Particle must be deactivated
        self.assertFalse(final_state.is_active)
        # Position should NOT be silently clamped to 54.02
        self.assertNotEqual(final_state.longitude, 54.02)

    def test_11_invalid_input_validations(self):
        """Section 26: explicit errors on invalid timestep, negative duration, or missing provider."""
        init_p = [Particle(particle_id="p_0001", latitude=25.0, longitude=54.0, timestamp=self.t0, active=True)]
        curr_prov = ConstantCurrentProvider()

        # dt <= 0
        with self.assertRaises(ValueError):
            simulate_forward(init_p, start_time=self.t0, dt_seconds=0.0, current_provider=curr_prov)

        with self.assertRaises(ValueError):
            simulate_forward(init_p, start_time=self.t0, dt_seconds=-60.0, current_provider=curr_prov)

        # duration < 0
        with self.assertRaises(ValueError):
            simulate_forward(init_p, start_time=self.t0, duration_seconds=-10.0, current_provider=curr_prov)

        # empty particles
        with self.assertRaises(ValueError):
            simulate_forward([], start_time=self.t0, current_provider=curr_prov)

        # missing current provider
        with self.assertRaises(ValueError):
            simulate_forward(init_p, start_time=self.t0, current_provider=None)

    def test_12_forecast_horizons_support(self):
        """Section 16: supports standard Feature 2 forecast lead times (6h, 12h, 24h, 48h)."""
        init_p = [Particle(particle_id="p_0001", latitude=20.0, longitude=60.0, timestamp=self.t0, active=True)]
        curr_prov = ConstantCurrentProvider(u=0.1, v=0.1)

        for hours in [6, 12, 24, 48]:
            res = simulate_forward(
                initial_particles=init_p,
                start_time=self.t0,
                duration_seconds=hours * 3600.0,
                dt_seconds=3600.0,
                current_provider=curr_prov,
                windage_fraction=0.0
            )
            self.assertEqual(res.end_time, self.t0 + timedelta(hours=hours))
            self.assertEqual(len(res.trajectories[0].states), hours + 1)


if __name__ == "__main__":
    unittest.main()
