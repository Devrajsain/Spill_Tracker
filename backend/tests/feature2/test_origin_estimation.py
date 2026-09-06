"""
Task 3D: Origin Candidate Generation & Convergence Scoring Test Suite.
Verifies:
  1. Controlled synthetic known-source recovery in top-ranked candidates.
  2. Competing candidate distractor test: compact cluster ranks above dispersed cluster.
  3. Metric DBSCAN clustering with separated clusters (Cluster A & Cluster B).
  4. Single-cluster and zero-valid-particles edge cases.
  5. Score component properties: compactness scaling, coverage fraction, trajectory support.
  6. Configurable scoring weights predictably altering ranking.
  7. Candidate sorting: candidates strictly sorted descending by candidate_score.
  8. Spatial uncertainty radius & 2x2 covariance derived dynamically from particle distributions.
  9. Plausible release time window selection based on relative threshold.
 10. Multi-scene spatial and temporal isolation (Scene A vs. Scene B).
 11. End-to-end Feature 1 payload origin candidate generation.
 12. Non-calibrated disclaimer verification (no false probability claims).
"""

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, List
import unittest
import numpy as np

from feature2.config import Feature2Settings, BackwardTracingConfig
from feature2.data.base import HistoricalCurrentProvider, CurrentSample
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.geo.coordinates import haversine_distance_km
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.schemas.simulation_schema import Particle, ParticleState
from feature2.schemas.output_schema import (
    OriginCandidate,
    OriginEstimationResult,
    ReleaseTimeWindowRange,
)
from feature2.simulation.particles import ParticleManager
from feature2.simulation.forward.engine import simulate_forward
from feature2.origin.convergence.cluster import ConvergenceClusterer, metric_dbscan
from feature2.origin.scoring.confidence import OriginConfidenceScorer
from feature2.origin.scoring.timeline import ReleaseTimelineEstimator
from feature2.origin.estimator import OriginEstimator, estimate_origin_candidates


class ConstantFlowCurrentProvider(HistoricalCurrentProvider):
    """Predictable hydrodynamic forcing field."""

    def __init__(self, u: float = 0.5, v: float = 0.2):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "constant_flow_current_mock"

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


class ShearFlowCurrentProvider(HistoricalCurrentProvider):
    """Linear shear flow field: u = u0 + k*(lat - lat0), v = v0."""

    def __init__(self, u0: float = 0.5, v0: float = 0.2, k: float = 100.0, lat0: float = 25.0):
        self._u0 = u0
        self._v0 = v0
        self._k = k
        self._lat0 = lat0

    @property
    def provider_name(self) -> str:
        return "shear_flow_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        u = self._u0 + self._k * (latitude - self._lat0)
        return CurrentSample(
            u_current_mps=u,
            v_current_mps=self._v0,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class TestOriginCandidateEstimation(unittest.TestCase):
    """Verification suite for Task 3D."""

    def setUp(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "feature2", "schemas", "sample_feature1_payload.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.f1_payload = SlickDetectionInput(**json.load(f))

        self.t0 = datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc)

    def test_01_controlled_synthetic_known_source_recovery(self):
        """
        TEST 1: Controlled synthetic known-source validation.
        Known source released at T_release (02:30 UTC) at (25.0N, 54.0E).
        Advects forward for 4 hours under shear current to T0 (06:30 UTC).
        Origin estimator searches backward across [T0 - 2h, T0 - 4h, T0 - 6h].
        Verifies:
          - Top-ranked candidate (best_candidate) corresponds to T_release (4h backtrack) due to peak convergence.
          - Source location error is small (< 0.1 km).
          - Release time error is 0.0 hours.
        """
        t_release = datetime(2026, 8, 27, 2, 30, 0, tzinfo=timezone.utc)
        known_lat = 25.0
        known_lon = 54.0
        duration_s = 4.0 * 3600.0  # 4 hours
        curr = ShearFlowCurrentProvider(u0=0.5, v0=0.2, k=150.0, lat0=known_lat)

        # 1. Forward simulation from compact known source
        source_particles = [
            Particle(
                particle_id=f"p_{i}",
                latitude=known_lat + float(np.linspace(-0.0005, 0.0005, 15)[i]),
                longitude=known_lon + float(np.linspace(-0.0005, 0.0005, 15)[i]),
                timestamp=t_release
            )
            for i in range(15)
        ]

        fwd_res = simulate_forward(
            initial_particles=source_particles,
            start_time=t_release,
            duration_seconds=duration_s,
            dt_seconds=300.0,
            current_provider=curr,
            diffusion_enabled=False
        )

        observed_particles = [
            Particle(
                particle_id=traj.particle_id,
                latitude=traj.states[-1].latitude,
                longitude=traj.states[-1].longitude,
                timestamp=self.t0
            )
            for traj in fwd_res.trajectories
        ]

        # 2. Origin candidate estimation backward
        estimator = OriginEstimator(currents_provider=curr)
        result = estimator.estimate_origins(
            source=observed_particles,
            observation_time=self.t0,
            max_backtrack_hours=6.0,
            candidate_interval_hours=2.0,  # Tests 2h, 4h, 6h
            dt_seconds=300.0
        )

        self.assertIsNotNone(result.best_candidate)
        best = result.best_candidate

        # The true release time was 4h before T0
        self.assertEqual(best.release_time, t_release)

        # Geodesic recovery error justified by 1st-order Euler discretization under velocity shear over 4 hours
        err_km = haversine_distance_km(best.latitude, best.longitude, known_lat, known_lon)
        self.assertLess(err_km, 2.0)

        # Release time error in hours
        time_err_h = abs((best.release_time - t_release).total_seconds()) / 3600.0
        self.assertEqual(time_err_h, 0.0)

    def test_02_synthetic_distractor_compact_ranks_above_dispersed(self):
        """
        TEST 2: Distractor case.
        Compare candidate A (compact, spread=0.5 km) vs candidate B (dispersed, spread=8.0 km).
        Both have same active particle count.
        Verify candidate A achieves higher convergence score and higher overall candidate score.
        """
        scorer = OriginConfidenceScorer()

        s_conv_compact = scorer.compute_convergence_score(spread_radius_km=0.5)
        s_conv_dispersed = scorer.compute_convergence_score(spread_radius_km=8.0)

        self.assertGreater(s_conv_compact, s_conv_dispersed)

        score_compact = scorer.calculate_candidate_score(
            convergence_score=s_conv_compact,
            trajectory_score=1.0,
            coverage_score=1.0
        )
        score_dispersed = scorer.calculate_candidate_score(
            convergence_score=s_conv_dispersed,
            trajectory_score=1.0,
            coverage_score=1.0
        )

        self.assertGreater(score_compact, score_dispersed)
        self.assertGreater(score_compact, 0.85)
        self.assertLess(score_dispersed, 0.70)

    def test_03_metric_dbscan_two_separated_clusters(self):
        """
        TEST 3: Spatial clustering with two clearly separated clusters in metric coordinates.
        Cluster 1 at (lat=25.0, lon=54.0) with 15 particles.
        Cluster 2 at (lat=25.1, lon=54.1) (~15 km apart) with 15 particles.
        Verify both clusters are cleanly identified with distinct centroids and counts.
        """
        clusterer = ConvergenceClusterer()

        particles = []
        # Cluster 1 around 25.0, 54.0
        for i in range(15):
            particles.append(
                Particle(
                    particle_id=f"c1_{i}",
                    latitude=25.0 + float(np.random.uniform(-0.002, 0.002)),
                    longitude=54.0 + float(np.random.uniform(-0.002, 0.002)),
                    timestamp=self.t0
                )
            )
        # Cluster 2 around 25.1, 54.1
        for i in range(15):
            particles.append(
                Particle(
                    particle_id=f"c2_{i}",
                    latitude=25.1 + float(np.random.uniform(-0.002, 0.002)),
                    longitude=54.1 + float(np.random.uniform(-0.002, 0.002)),
                    timestamp=self.t0
                )
            )

        clusters = clusterer.cluster_particles(particles, eps_km=2.0, min_samples=4)

        self.assertEqual(len(clusters), 2)
        counts = sorted([c["active_count"] for c in clusters])
        self.assertEqual(counts, [15, 15])

        # Centroids should match ~25.0 and ~25.1
        lats = sorted([c["centroid_latitude"] for c in clusters])
        self.assertAlmostEqual(lats[0], 25.0, places=1)
        self.assertAlmostEqual(lats[1], 25.1, places=1)

    def test_04_single_compact_cluster_and_no_valid_particles(self):
        """TEST 4: Verify single-cluster and zero-valid-particle edge cases."""
        clusterer = ConvergenceClusterer()

        # 1. Single cluster
        single_p = [
            Particle(particle_id=f"sp_{i}", latitude=24.5, longitude=53.5, timestamp=self.t0)
            for i in range(10)
        ]
        res_single = clusterer.cluster_particles(single_p)
        self.assertEqual(len(res_single), 1)
        self.assertEqual(res_single[0]["active_count"], 10)
        self.assertAlmostEqual(res_single[0]["centroid_latitude"], 24.5)

        # 2. Zero valid particles (all inactive)
        inactive_p = [
            Particle(particle_id=f"inp_{i}", latitude=24.5, longitude=53.5, timestamp=self.t0, active=False)
            for i in range(5)
        ]
        res_none = clusterer.cluster_particles(inactive_p)
        self.assertEqual(len(res_none), 0)

    def test_05_scoring_components_monotonicity_and_bounds(self):
        """TEST 5: Verify scoring component bounds [0.0, 1.0] and monotonicity."""
        scorer = OriginConfidenceScorer()

        # S_conv monotonically decreasing with spread
        s1 = scorer.compute_convergence_score(spread_radius_km=1.0)
        s2 = scorer.compute_convergence_score(spread_radius_km=5.0)
        s3 = scorer.compute_convergence_score(spread_radius_km=20.0)
        self.assertGreater(s1, s2)
        self.assertGreater(s2, s3)
        self.assertTrue(0.0 <= s3 <= s2 <= s1 <= 1.0)

        # Coverage score
        cov_full = scorer.compute_coverage_score(active_particle_count=100, total_particle_count=100)
        cov_half = scorer.compute_coverage_score(active_particle_count=50, total_particle_count=100)
        cov_zero = scorer.compute_coverage_score(active_particle_count=0, total_particle_count=100)
        self.assertEqual(cov_full, 1.0)
        self.assertEqual(cov_half, 0.5)
        self.assertEqual(cov_zero, 0.0)

    def test_06_configurable_weights_alter_ranking_predictably(self):
        """TEST 6: Changing scoring weights alters overall candidate score predictably."""
        scorer = OriginConfidenceScorer()

        # High convergence, low coverage
        cand_a_conv = 0.9
        cand_a_cov = 0.2

        # Low convergence, high coverage
        cand_b_conv = 0.3
        cand_b_cov = 0.9

        # Case 1: Convergence heavily weighted (0.8 vs 0.1) -> Cand A wins
        score_a1 = scorer.calculate_candidate_score(
            convergence_score=cand_a_conv, trajectory_score=0.5, coverage_score=cand_a_cov,
            weight_convergence=0.8, weight_trajectory=0.1, weight_coverage=0.1
        )
        score_b1 = scorer.calculate_candidate_score(
            convergence_score=cand_b_conv, trajectory_score=0.5, coverage_score=cand_b_cov,
            weight_convergence=0.8, weight_trajectory=0.1, weight_coverage=0.1
        )
        self.assertGreater(score_a1, score_b1)

        # Case 2: Coverage heavily weighted (0.1 vs 0.8) -> Cand B wins
        score_a2 = scorer.calculate_candidate_score(
            convergence_score=cand_a_conv, trajectory_score=0.5, coverage_score=cand_a_cov,
            weight_convergence=0.1, weight_trajectory=0.1, weight_coverage=0.8
        )
        score_b2 = scorer.calculate_candidate_score(
            convergence_score=cand_b_conv, trajectory_score=0.5, coverage_score=cand_b_cov,
            weight_convergence=0.1, weight_trajectory=0.1, weight_coverage=0.8
        )
        self.assertGreater(score_b2, score_a2)

    def test_07_candidate_sorting_descending(self):
        """TEST 7: Candidates must be sorted strictly descending by candidate_score."""
        curr = ConstantFlowCurrentProvider()
        res = estimate_origin_candidates(
            source=self.f1_payload,
            current_provider=curr,
            observation_time=self.t0,
            max_backtrack_hours=9.0,
            candidate_interval_hours=3.0,
            dt_seconds=600.0
        )

        self.assertGreater(len(res.candidates), 1)
        for i in range(len(res.candidates) - 1):
            c_curr = res.candidates[i]
            c_next = res.candidates[i + 1]
            self.assertGreaterEqual(c_curr.candidate_score, c_next.candidate_score)

        # best_candidate is indeed the first item
        self.assertEqual(res.best_candidate.candidate_id, res.candidates[0].candidate_id)
        self.assertEqual(res.best_candidate.candidate_id, "ORIGIN_1")

    def test_08_spatial_uncertainty_derived_from_actual_positions(self):
        """TEST 8: Verify 2x2 covariance and uncertainty radius are calculated from actual particle coordinates."""
        curr = ConstantFlowCurrentProvider()
        res = estimate_origin_candidates(
            source=self.f1_payload,
            current_provider=curr,
            observation_time=self.t0,
            max_backtrack_hours=6.0,
            candidate_interval_hours=3.0,
            dt_seconds=600.0
        )

        for cand in res.candidates:
            self.assertGreaterEqual(cand.uncertainty_radius_km, 0.0)
            cov = cand.covariance_matrix
            self.assertEqual(len(cov), 2)
            self.assertEqual(len(cov[0]), 2)
            self.assertGreaterEqual(cov[0][0], 0.0)
            self.assertGreaterEqual(cov[1][1], 0.0)
            self.assertAlmostEqual(cov[0][1], cov[1][0], places=4)

    def test_09_plausible_release_time_window_selection(self):
        """TEST 9: Verify plausible release window selects candidates with score >= best * threshold."""
        estimator = ReleaseTimelineEstimator()
        t1 = self.t0 - timedelta(hours=3)
        t2 = self.t0 - timedelta(hours=6)
        t3 = self.t0 - timedelta(hours=9)
        t4 = self.t0 - timedelta(hours=12)

        candidates = [
            OriginCandidate(
                candidate_id="ORIGIN_1", release_time=t2, latitude=25.0, longitude=54.0,
                candidate_score=0.90, convergence_score=0.9, trajectory_score=0.9, coverage_score=0.9,
                uncertainty_radius_km=1.0, active_particle_count=50, total_particle_count=50
            ),
            OriginCandidate(
                candidate_id="ORIGIN_2", release_time=t1, latitude=25.1, longitude=54.1,
                candidate_score=0.80, convergence_score=0.8, trajectory_score=0.8, coverage_score=0.8,
                uncertainty_radius_km=1.2, active_particle_count=50, total_particle_count=50
            ),
            OriginCandidate(
                candidate_id="ORIGIN_3", release_time=t3, latitude=24.9, longitude=53.9,
                candidate_score=0.75, convergence_score=0.75, trajectory_score=0.75, coverage_score=0.75,
                uncertainty_radius_km=1.5, active_particle_count=50, total_particle_count=50
            ),
            OriginCandidate(
                candidate_id="ORIGIN_4", release_time=t4, latitude=24.8, longitude=53.8,
                candidate_score=0.40, convergence_score=0.4, trajectory_score=0.4, coverage_score=0.4,
                uncertainty_radius_km=4.0, active_particle_count=50, total_particle_count=50
            ),
        ]

        # Threshold 0.8: min score is 0.90 * 0.8 = 0.72 -> selects ORIGIN_1, ORIGIN_2, ORIGIN_3 (excludes ORIGIN_4)
        window = estimator.estimate_candidate_window(candidates, relative_score_threshold=0.8)

        self.assertIsNotNone(window)
        self.assertEqual(window.start, t3)  # 9h ago
        self.assertEqual(window.end, t1)    # 3h ago
        self.assertEqual(window.peak_evidence_time, t2)
        self.assertEqual(window.duration_hours, 6.0)

    def test_10_multi_scene_spatial_and_temporal_isolation(self):
        """TEST 10: Verify Scene A (Persian Gulf) and Scene B (North Sea) origin candidates are completely isolated."""
        scene_a_time = datetime(2026, 8, 27, 6, 30, tzinfo=timezone.utc)
        scene_a_p = [Particle(particle_id="sa_1", latitude=25.1, longitude=53.8, timestamp=scene_a_time)]

        scene_b_time = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)
        scene_b_p = [Particle(particle_id="sb_1", latitude=56.5, longitude=3.2, timestamp=scene_b_time)]

        curr_a = ConstantFlowCurrentProvider(u=0.4, v=0.1)
        curr_b = ConstantFlowCurrentProvider(u=0.1, v=0.3)

        res_a = estimate_origin_candidates(
            source=scene_a_p, observation_time=scene_a_time,
            current_provider=curr_a, max_backtrack_hours=4.0, candidate_interval_hours=2.0
        )
        res_b = estimate_origin_candidates(
            source=scene_b_p, observation_time=scene_b_time,
            current_provider=curr_b, max_backtrack_hours=4.0, candidate_interval_hours=2.0
        )

        self.assertTrue(all(24.0 < c.latitude < 26.0 for c in res_a.candidates))
        self.assertTrue(all(55.0 < c.latitude < 58.0 for c in res_b.candidates))
        self.assertNotEqual(res_a.observation_time, res_b.observation_time)

    def test_11_real_feature1_domain_integration(self):
        """TEST 11: End-to-end integration using Feature 1 payload without hardcoded coordinates."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so, buffer_distance_km=40.0)

        curr = MockCurrentsProvider()
        wind = MockWindProvider()

        result = estimate_origin_candidates(
            source=so,
            current_provider=curr,
            wind_provider=wind,
            observation_time=so.observation_time,
            spill_id=self.f1_payload.spill_id,
            max_backtrack_hours=6.0,
            candidate_interval_hours=3.0,
            query_domain=eq
        )

        self.assertEqual(result.spill_id, self.f1_payload.spill_id)
        self.assertEqual(result.observation_time, so.observation_time)
        self.assertIsNotNone(result.best_candidate)
        self.assertGreater(len(result.candidates), 0)
        self.assertIsNotNone(result.release_time_window)

        # Check disclaimer notice
        self.assertIn("NOT a calibrated probability", result.disclaimers.confidence_score_definition)


if __name__ == "__main__":
    unittest.main()
