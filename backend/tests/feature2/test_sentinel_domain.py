"""
Unit tests for Sentinel-1 driven environmental domain derivation and coverage validation (Task 2A).
Verifies that Feature 2 dynamically adapts its spatial and temporal environmental query domains
to any arbitrary Sentinel-1 observation scene from the Zenodo dataset without hardcoded coordinates.
"""

from datetime import datetime, timedelta, timezone
import unittest

from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.exceptions import EnvironmentalCoverageError, InvalidInputGeometryError


class TestSentinelDomainDerivation(unittest.TestCase):
    """Tests for extracting SentinelObservationDomain from Feature 1 and deriving EnvironmentalQueryDomain."""

    def setUp(self):
        # Scene A: Synthetic Sentinel-1 observation (e.g. Arabian Sea)
        self.scene_a_payload = SlickDetectionInput(
            spill_id="S1A_SCENE_001",
            observation_time=datetime.fromisoformat("2026-08-27T06:30:00Z"),
            area_sq_km=8.5,
            perimeter_km=18.2,
            centroid=CentroidCoordinates(latitude=24.8192, longitude=54.1204),
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[
                    [
                        [54.10, 24.80],
                        [54.15, 24.80],
                        [54.15, 24.85],
                        [54.10, 24.85],
                        [54.10, 24.80]
                    ]
                ]
            ),
            metadata={"satellite": "Sentinel-1A", "polarization": "VV", "scene_id": "S1A_IW_GRDH_1SDV_20260827T063000"}
        )

        # Scene B: Completely different Sentinel-1 observation (e.g. Bay of Bengal or North Sea)
        self.scene_b_payload = SlickDetectionInput(
            spill_id="S1B_SCENE_002",
            observation_time=datetime.fromisoformat("2026-07-15T18:45:00Z"),
            area_sq_km=12.1,
            perimeter_km=22.0,
            centroid=CentroidCoordinates(latitude=15.2500, longitude=82.5000),
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[
                    [
                        [82.40, 15.20],
                        [82.60, 15.20],
                        [82.60, 15.30],
                        [82.40, 15.30],
                        [82.40, 15.20]
                    ]
                ]
            ),
            metadata={"satellite": "Sentinel-1B", "polarization": "VH"}
        )

    def test_sentinel_observation_domain_creation(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)

        self.assertEqual(domain_a.spill_id, "S1A_SCENE_001")
        self.assertEqual(domain_a.observation_time, datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc))
        self.assertAlmostEqual(domain_a.centroid_lat, 24.8192)
        self.assertAlmostEqual(domain_a.centroid_lon, 54.1204)
        self.assertAlmostEqual(domain_a.min_lat, 24.80)
        self.assertAlmostEqual(domain_a.max_lat, 24.85)
        self.assertAlmostEqual(domain_a.min_lon, 54.10)
        self.assertAlmostEqual(domain_a.max_lon, 54.15)

    def test_environmental_query_domain_derivation_and_buffering(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)
        env_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            sentinel_domain=domain_a,
            buffer_distance_km=50.0,
            historical_horizon_hours=72.0,
            forecast_horizon_hours=48.0
        )

        # Buffer must expand spatial bounds
        self.assertLess(env_domain.min_lat, domain_a.min_lat)
        self.assertGreater(env_domain.max_lat, domain_a.max_lat)
        self.assertLess(env_domain.min_lon, domain_a.min_lon)
        self.assertGreater(env_domain.max_lon, domain_a.max_lon)
        self.assertEqual(env_domain.buffer_distance_km, 50.0)

        # Historical time window [T0 - 72h, T0]
        self.assertEqual(env_domain.historical_end_time, domain_a.observation_time)
        self.assertEqual(
            env_domain.historical_start_time,
            domain_a.observation_time - timedelta(hours=72)
        )

        # Forecast time window [T0, T0 + 48h]
        self.assertEqual(env_domain.forecast_start_time, domain_a.observation_time)
        self.assertEqual(
            env_domain.forecast_end_time,
            domain_a.observation_time + timedelta(hours=48)
        )

    def test_configurable_buffer_distance(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)
        env_domain_10km = EnvironmentalQueryDomain.from_sentinel_observation(
            sentinel_domain=domain_a,
            buffer_distance_km=10.0
        )
        env_domain_100km = EnvironmentalQueryDomain.from_sentinel_observation(
            sentinel_domain=domain_a,
            buffer_distance_km=100.0
        )

        # 100km buffer should have strictly larger bounding box than 10km buffer
        self.assertLess(env_domain_100km.min_lat, env_domain_10km.min_lat)
        self.assertGreater(env_domain_100km.max_lat, env_domain_10km.max_lat)
        self.assertLess(env_domain_100km.min_lon, env_domain_10km.min_lon)
        self.assertGreater(env_domain_100km.max_lon, env_domain_10km.max_lon)

    def test_multiple_distinct_sentinel_scenes_produce_distinct_domains(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)
        domain_b = SentinelObservationDomain.from_feature1_input(self.scene_b_payload)

        env_a = EnvironmentalQueryDomain.from_sentinel_observation(domain_a)
        env_b = EnvironmentalQueryDomain.from_sentinel_observation(domain_b)

        # Ensure spatial domains are completely distinct
        self.assertNotEqual(env_a.source_bbox, env_b.source_bbox)
        self.assertNotEqual(env_a.environmental_bbox, env_b.environmental_bbox)
        self.assertNotEqual(env_a.observation_time, env_b.observation_time)
        self.assertNotEqual(env_a.historical_start_time, env_b.historical_start_time)

    def test_spatial_coverage_validation_success_and_failure(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)
        env_domain = EnvironmentalQueryDomain.from_sentinel_observation(domain_a, buffer_distance_km=20.0)

        # Dataset that properly encompasses Scene A
        env_domain.validate_spatial_coverage(
            dataset_min_lat=24.0,
            dataset_max_lat=26.0,
            dataset_min_lon=53.0,
            dataset_max_lon=56.0,
            strict_buffer=True
        )

        # Dataset that fails to cover Scene A (e.g. wrong region in Indian Ocean)
        with self.assertRaises(EnvironmentalCoverageError):
            env_domain.validate_spatial_coverage(
                dataset_min_lat=10.0,
                dataset_max_lat=15.0,
                dataset_min_lon=70.0,
                dataset_max_lon=75.0,
                strict_buffer=False
            )

    def test_temporal_coverage_validation_success_and_failure(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)
        env_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            domain_a,
            historical_horizon_hours=72.0
        )

        # Dataset covering 2026-08-20 to 2026-08-28 (encompasses historical search window)
        env_domain.validate_temporal_coverage(
            dataset_min_time=datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc),
            dataset_max_time=datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc),
            mode="historical"
        )

        # Dataset that is only available at T0 (fails historical window requirement)
        with self.assertRaises(EnvironmentalCoverageError):
            env_domain.validate_temporal_coverage(
                dataset_min_time=datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc),
                dataset_max_time=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
                mode="historical"
            )

    def test_providers_accept_derived_environmental_domain(self):
        domain_a = SentinelObservationDomain.from_feature1_input(self.scene_a_payload)
        env_domain = EnvironmentalQueryDomain.from_sentinel_observation(domain_a)

        curr_provider = MockCurrentsProvider()
        wind_provider = MockWindProvider()

        # Both providers accept the derived query domain
        self.assertTrue(curr_provider.fetch_grid(env_domain))
        self.assertTrue(wind_provider.fetch_grid(env_domain))


if __name__ == "__main__":
    unittest.main()
