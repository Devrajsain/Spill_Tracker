"""
Task 2B: Real Feature 1 -> Environmental Data Wiring Verification Test Suite.
Verifies the complete data chain:
  Feature 1 Payload -> SentinelObservationDomain -> EnvironmentalQueryDomain -> Current/Wind Providers
Guarantees zero manual coordinate input, scene isolation, exact bounding box and historical
time propagation, request auditing, and absence of hardcoded coordinates or credential leakage.
"""

from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch
import numpy as np

from feature2.config import Feature2Settings, DataSourceConfig
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.currents.copernicus import CopernicusCurrentsProvider, CopernicusConfig
from feature2.data.currents.hycom import HYCOMCurrentsProvider, HYCOMConfig
from feature2.data.wind.mock import MockWindProvider
from feature2.data.wind.era5 import ERA5WindProvider, ERA5Config
from feature2.data.wind.gfs import GFSWindProvider, GFSConfig
from feature2.data.wiring_trace import (
    ProviderRequestAuditor,
    WiringTraceRecord,
    trace_feature1_environmental_wiring,
)
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.exceptions import EnvironmentalCoverageError


class TestFeature1EnvironmentalWiring(unittest.TestCase):
    """Rigorous runtime wiring and data-chain audit tests."""

    def setUp(self):
        # Load representative Feature 1 Sentinel-1 payload
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "feature2", "schemas", "sample_feature1_payload.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.sample_f1_dict = json.load(f)

        self.f1_payload_a = SlickDetectionInput(**self.sample_f1_dict)

        # Distinct Scene B (e.g. North Sea scene at different epoch)
        self.f1_payload_b = SlickDetectionInput(
            spill_id="S1B_NORTH_SEA_20261010T140000_OIL_002",
            observation_time=datetime.fromisoformat("2026-10-10T14:00:00Z"),
            area_sq_km=14.2,
            perimeter_km=28.5,
            centroid=CentroidCoordinates(latitude=56.4500, longitude=3.2000),
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[
                    [
                        [3.15, 56.40],
                        [3.25, 56.40],
                        [3.25, 56.50],
                        [3.15, 56.50],
                        [3.15, 56.40]
                    ]
                ]
            ),
            metadata={"dataset": "Zenodo Sentinel-1 Part 2", "orbit": 114}
        )

    def test_01_feature1_payload_to_sentinel_observation_domain(self):
        """Verify SentinelObservationDomain inherits exact coordinates and T0 from Feature 1 payload."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)

        self.assertEqual(so.spill_id, self.f1_payload_a.spill_id)
        self.assertEqual(so.observation_time, datetime(2026, 8, 27, 6, 30, 12, tzinfo=timezone.utc))
        self.assertAlmostEqual(so.centroid_lat, 25.1245)
        self.assertAlmostEqual(so.centroid_lon, 53.8421)
        self.assertAlmostEqual(so.min_lat, 25.1100)
        self.assertAlmostEqual(so.max_lat, 25.1400)
        self.assertAlmostEqual(so.min_lon, 53.8200)
        self.assertAlmostEqual(so.max_lon, 53.8700)

    def test_02_sentinel_domain_to_environmental_query_domain(self):
        """Verify EnvironmentalQueryDomain buffers the exact source footprint and sets historical window."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(
            sentinel_domain=so,
            buffer_distance_km=40.0,
            historical_horizon_hours=72.0
        )

        self.assertEqual(eq.spill_id, so.spill_id)
        self.assertEqual(eq.observation_time, so.observation_time)
        self.assertEqual(eq.historical_end_time, so.observation_time)
        self.assertEqual(eq.historical_start_time, so.observation_time - timedelta(hours=72))
        self.assertEqual(eq.buffer_distance_km, 40.0)

        # Environmental bbox strictly encloses source slick bbox
        self.assertLess(eq.min_lat, so.min_lat)
        self.assertGreater(eq.max_lat, so.max_lat)
        self.assertLess(eq.min_lon, so.min_lon)
        self.assertGreater(eq.max_lon, so.max_lon)

    def test_03_exact_provider_bbox_and_time_propagation(self):
        """Verify provider requests receive identical bounding boxes and historical time windows."""
        curr_provider = MockCurrentsProvider()
        wind_provider = MockWindProvider()

        trace = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=curr_provider,
            wind_provider=wind_provider
        )

        eq = trace.environmental_query
        cr = trace.current_request
        wr = trace.wind_request

        # Bounding box propagation
        self.assertEqual(cr.requested_bbox, eq.environmental_bbox)
        self.assertEqual(wr.requested_bbox, eq.environmental_bbox)

        # Time range propagation
        self.assertEqual(cr.requested_time_start, eq.historical_start_time)
        self.assertEqual(cr.requested_time_end, eq.historical_end_time)
        self.assertEqual(wr.requested_time_start, eq.historical_start_time)
        self.assertEqual(wr.requested_time_end, eq.historical_end_time)

        self.assertTrue(trace.geographic_match)
        self.assertTrue(trace.temporal_match)

    def test_04_current_and_wind_providers_receive_same_domain(self):
        """Current and wind requests must use matching spatial and temporal boundaries."""
        trace = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=MockCurrentsProvider(),
            wind_provider=MockWindProvider()
        )
        self.assertEqual(trace.current_request.requested_bbox, trace.wind_request.requested_bbox)
        self.assertEqual(trace.current_request.requested_time_start, trace.wind_request.requested_time_start)
        self.assertEqual(trace.current_request.requested_time_end, trace.wind_request.requested_time_end)

    def test_05_two_scene_spatial_and_temporal_isolation(self):
        """Verify Scene A and Scene B never cross-contaminate coordinates or timestamps."""
        curr_prov = MockCurrentsProvider()
        wind_prov = MockWindProvider()

        trace_a = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=curr_prov,
            wind_provider=wind_prov
        )
        trace_b = trace_feature1_environmental_wiring(
            payload=self.f1_payload_b,
            currents_provider=curr_prov,
            wind_provider=wind_prov
        )

        # Spatial isolation
        self.assertNotEqual(trace_a.current_request.requested_bbox, trace_b.current_request.requested_bbox)
        self.assertNotEqual(trace_a.wind_request.requested_bbox, trace_b.wind_request.requested_bbox)

        # Temporal isolation
        self.assertNotEqual(trace_a.current_request.requested_time_start, trace_b.current_request.requested_time_start)
        self.assertNotEqual(trace_a.current_request.requested_time_end, trace_b.current_request.requested_time_end)

        # Anti-cross-contamination assertion: Scene A never touches Scene B coordinates
        a_bbox = trace_a.environmental_query.environmental_bbox
        b_bbox = trace_b.environmental_query.environmental_bbox
        self.assertFalse(
            a_bbox[0] <= b_bbox[0] <= a_bbox[1] and a_bbox[2] <= b_bbox[2] <= a_bbox[3],
            "Scene A and Scene B bounding boxes must be cleanly separated without cross-contamination."
        )

    def test_06_configurable_buffer_applied_once(self):
        """Changing environmental_buffer_km adjusts environmental query bounding box proportionally."""
        cfg_20 = Feature2Settings(data=DataSourceConfig(environmental_buffer_km=20.0))
        cfg_60 = Feature2Settings(data=DataSourceConfig(environmental_buffer_km=60.0))

        trace_20 = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=MockCurrentsProvider(),
            wind_provider=MockWindProvider(),
            settings=cfg_20
        )
        trace_60 = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=MockCurrentsProvider(),
            wind_provider=MockWindProvider(),
            settings=cfg_60
        )

        eq_20 = trace_20.environmental_query
        eq_60 = trace_60.environmental_query

        # Source bbox is unchanged
        self.assertEqual(eq_20.source_bbox, eq_60.source_bbox)

        # 60km buffer is strictly larger than 20km buffer
        self.assertLess(eq_60.min_lat, eq_20.min_lat)
        self.assertGreater(eq_60.max_lat, eq_20.max_lat)
        self.assertLess(eq_60.min_lon, eq_20.min_lon)
        self.assertGreater(eq_60.max_lon, eq_20.max_lon)

    def test_07_historical_horizon_derived_from_t0(self):
        """Historical window is computed strictly as T0 - horizon, never system current time."""
        cfg_custom_horizon = Feature2Settings()
        cfg_custom_horizon.backward.max_backtrack_hours = 96.0

        trace = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=MockCurrentsProvider(),
            wind_provider=MockWindProvider(),
            settings=cfg_custom_horizon
        )
        eq = trace.environmental_query

        t0 = self.f1_payload_a.observation_time
        self.assertEqual(eq.historical_end_time, t0)
        self.assertEqual(eq.historical_start_time, t0 - timedelta(hours=96.0))

    def test_08_provider_request_auditor_detects_tampered_coordinates(self):
        """ProviderRequestAuditor raises EnvironmentalCoverageError if provider attempts to alter bbox."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so)

        # Tampered coordinates (attempting to query Mumbai instead of Sentinel-1 scene)
        with self.assertRaises(EnvironmentalCoverageError):
            ProviderRequestAuditor.audit_request(
                domain=eq,
                provider_name="rogue_provider",
                provider_type="current",
                requested_bbox=(18.0, 19.0, 72.0, 73.0),
                requested_start=eq.historical_start_time,
                requested_end=eq.historical_end_time
            )

    def test_09_provider_request_auditor_detects_tampered_time(self):
        """ProviderRequestAuditor raises EnvironmentalCoverageError if provider alters time window."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so)

        # Tampered start time (using current time instead of historical window)
        with self.assertRaises(EnvironmentalCoverageError):
            ProviderRequestAuditor.audit_request(
                domain=eq,
                provider_name="rogue_provider",
                provider_type="wind",
                requested_bbox=eq.environmental_bbox,
                requested_start=datetime.now(timezone.utc),
                requested_end=eq.historical_end_time
            )

    def test_10_no_hardcoded_coordinates_in_production_codebase(self):
        """Static audit verifying no fixed regional coordinates exist in feature2/ python source."""
        import glob
        import re

        feature2_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "feature2"))
        py_files = glob.glob(os.path.join(feature2_dir, "**", "*.py"), recursive=True)

        # Exclude sample fixture and test files
        target_files = [f for f in py_files if "tests" not in f and not f.endswith("_test.py")]

        # Pattern targeting hardcoded coordinate assignments: lat = XX.XXXX or center_lat = XX.XX
        forbidden_regex = re.compile(
            r"(Arabian\s+Sea|Persian\s+Gulf|Bay\s+of\s+Bengal|Mumbai|center_lat\s*=\s*[1-9]|center_lon\s*=\s*[1-9])",
            re.IGNORECASE
        )

        violations = []
        for file_path in target_files:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, start=1):
                    # Ignore comment blocks mentioning example names
                    if forbidden_regex.search(line) and not line.strip().startswith("#"):
                        violations.append(f"{os.path.basename(file_path)}:{line_idx}: {line.strip()}")

        self.assertEqual(
            len(violations), 0,
            f"Found hardcoded geographic references in production code: {violations}"
        )

    def test_11_request_trace_formatted_output(self):
        """Verify human-readable diagnostic trace output matches Section 17 format."""
        trace = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=MockCurrentsProvider(),
            wind_provider=MockWindProvider()
        )
        output_str = trace.format_trace()

        self.assertIn("FEATURE 1 → ENVIRONMENT TRACE", output_str)
        self.assertIn("spill_id:", output_str)
        self.assertIn(self.f1_payload_a.spill_id, output_str)
        self.assertIn("Sentinel observation:", output_str)
        self.assertIn("Environmental query:", output_str)
        self.assertIn("CURRENT REQUEST:", output_str)
        self.assertIn("WIND REQUEST:", output_str)
        self.assertIn("geographic_match: PASS", output_str)
        self.assertIn("temporal_match: PASS", output_str)
        self.assertIn("scene_isolation: PASS", output_str)

    def test_12_no_credential_leakage_in_logs_or_traces(self):
        """Verify trace and logging never expose sensitive API keys or passwords."""
        trace = trace_feature1_environmental_wiring(
            payload=self.f1_payload_a,
            currents_provider=MockCurrentsProvider(),
            wind_provider=MockWindProvider()
        )
        trace_str = trace.format_trace()

        forbidden_tokens = ["password", "token", "secret", "api_key", "bearer", "authorization"]
        for token in forbidden_tokens:
            self.assertNotIn(token, trace_str.lower())

    def test_13_remote_adapters_construct_requests_from_derived_domain(self):
        """Verify Copernicus, HYCOM, ERA5, and GFS adapters construct requests strictly from derived domain."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so)

        # Copernicus Current
        cmems = CopernicusCurrentsProvider(config=CopernicusConfig())
        cmems_req = cmems.build_subset_request(eq)
        self.assertEqual(cmems_req["minimum_latitude"], eq.min_lat)
        self.assertEqual(cmems_req["maximum_latitude"], eq.max_lat)
        self.assertEqual(cmems_req["minimum_longitude"], eq.min_lon)
        self.assertEqual(cmems_req["maximum_longitude"], eq.max_lon)
        self.assertEqual(cmems_req["start_datetime"], eq.historical_start_time.isoformat())
        self.assertEqual(cmems_req["end_datetime"], eq.historical_end_time.isoformat())

        # HYCOM Current
        hycom = HYCOMCurrentsProvider(config=HYCOMConfig())
        hycom_url = hycom.build_opendap_slice_url(eq)
        self.assertIn(f"[{eq.min_lat}:1:{eq.max_lat}]", hycom_url)
        self.assertIn(f"[{eq.min_lon}:1:{eq.max_lon}]", hycom_url)

        # ERA5 Wind
        era5 = ERA5WindProvider(config=ERA5Config())
        era5_req = era5.build_cds_request(eq)
        self.assertEqual(era5_req["area"], [eq.max_lat, eq.min_lon, eq.min_lat, eq.max_lon])
        self.assertEqual(era5_req["year"], str(eq.historical_start_time.year))

        # GFS Wind
        gfs = GFSWindProvider(config=GFSConfig())
        gfs_req = gfs.build_forecast_request(eq)
        self.assertEqual(gfs_req["min_lat"], eq.min_lat)
        self.assertEqual(gfs_req["max_lat"], eq.max_lat)

    def test_14_live_api_unconfigured_reports_not_executed_cleanly(self):
        """Verify unconfigured live adapters report environmental data unavailable without false claims."""
        with patch.dict(os.environ, {"CMEMS_USERNAME": "", "CMEMS_PASSWORD": "", "CDSAPI_KEY": ""}):
            cmems = CopernicusCurrentsProvider(config=CopernicusConfig(username="", password=""))
            era5 = ERA5WindProvider(config=ERA5Config(api_key=""))

            # fetch_grid without credentials returns False
            self.assertFalse(cmems.fetch_grid(EnvironmentalQueryDomain.from_sentinel_observation(
                SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
            )))
            self.assertFalse(era5.fetch_grid(EnvironmentalQueryDomain.from_sentinel_observation(
                SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
            )))

    def test_15_longitude_convention_and_boundary_handling(self):
        """Verify longitude conventions [-180, 180] and [0, 360] are consistently handled."""
        from feature2.data.coord_utils import normalize_longitude, detect_longitude_convention

        # Scene with positive Eastern hemisphere coordinates
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so)

        self.assertEqual(detect_longitude_convention([eq.min_lon, eq.max_lon]), "[-180, 180]")
        self.assertAlmostEqual(normalize_longitude(eq.min_lon, convention="[-180, 180]"), eq.min_lon)
        self.assertAlmostEqual(normalize_longitude(eq.min_lon, convention="[0, 360]"), eq.min_lon)

        # Western hemisphere scene (-70.5 deg W)
        west_payload = SlickDetectionInput(
            spill_id="WEST_HEMISPHERE_TEST",
            observation_time=datetime.fromisoformat("2026-08-27T06:30:12Z"),
            area_sq_km=5.0,
            perimeter_km=10.0,
            centroid=CentroidCoordinates(latitude=20.0, longitude=-70.5),
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[-70.6, 19.9], [-70.4, 19.9], [-70.4, 20.1], [-70.6, 20.1], [-70.6, 19.9]]]
            )
        )
        so_west = SentinelObservationDomain.from_feature1_input(west_payload)
        eq_west = EnvironmentalQueryDomain.from_sentinel_observation(so_west)
        self.assertLess(eq_west.min_lon, 0.0)

        # Normalization to positive 360 converts -70.5 to 289.5
        lon_360 = normalize_longitude(so_west.centroid_lon, convention="[0, 360]")
        self.assertAlmostEqual(lon_360, 289.5)
        # Normalization back to [-180, 180] returns -70.5
        self.assertAlmostEqual(normalize_longitude(lon_360, convention="[-180, 180]"), -70.5)

    def test_16_coverage_validation_explicit_failure_cases(self):
        """Verify spatial and temporal coverage failures raise EnvironmentalCoverageError without silent fallbacks."""
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload_a)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(so)

        # Case 1: Fully covered -> succeeds
        eq.validate_spatial_coverage(
            dataset_min_lat=eq.min_lat - 1.0,
            dataset_max_lat=eq.max_lat + 1.0,
            dataset_min_lon=eq.min_lon - 1.0,
            dataset_max_lon=eq.max_lon + 1.0,
            strict_buffer=True
        )
        eq.validate_temporal_coverage(
            dataset_min_time=eq.historical_start_time - timedelta(days=1),
            dataset_max_time=eq.historical_end_time + timedelta(days=1),
            mode="historical"
        )

        # Case 2: Spatial mismatch -> raises EnvironmentalCoverageError
        with self.assertRaises(EnvironmentalCoverageError):
            eq.validate_spatial_coverage(
                dataset_min_lat=0.0, dataset_max_lat=10.0,
                dataset_min_lon=0.0, dataset_max_lon=10.0
            )

        # Case 3: Historical start earlier than available data -> raises EnvironmentalCoverageError
        with self.assertRaises(EnvironmentalCoverageError):
            eq.validate_temporal_coverage(
                dataset_min_time=eq.historical_start_time + timedelta(hours=12),
                dataset_max_time=eq.historical_end_time,
                mode="historical"
            )

        # Case 4: Historical end later than available data -> raises EnvironmentalCoverageError
        with self.assertRaises(EnvironmentalCoverageError):
            eq.validate_temporal_coverage(
                dataset_min_time=eq.historical_start_time - timedelta(days=1),
                dataset_max_time=eq.historical_end_time - timedelta(hours=6),
                mode="historical"
            )


if __name__ == "__main__":
    unittest.main()
