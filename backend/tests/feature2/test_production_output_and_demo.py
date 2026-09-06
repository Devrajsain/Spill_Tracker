"""
Task 5 Test Suite: Production-ready output contract, auditability, GeoJSON properties,
provenance, quality assessment, and deterministic offline demo validation.
"""

from datetime import datetime, timedelta, timezone
import os
import unittest

from feature2.config import Feature2Settings, BackwardTracingConfig, ForecastConfig, default_settings
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.wind.era5 import ERA5WindProvider
from feature2.data.currents.copernicus import CopernicusCurrentsProvider, CopernicusForecastCurrentsProvider
from feature2.data.wind.gfs import GFSWindProvider
from feature2.forecast.forecaster import ForwardForecaster
from feature2.origin.estimator import OriginEstimator
from feature2.output.formatter import OutputFormatter
from feature2.pipeline.demo import run_offline_demo, load_demo_slick_input, create_demo_pipeline_service
from feature2.pipeline.service import Feature2PipelineService
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.schemas.output_schema import (
    UnifiedFeature2Result,
    Feature2PipelineResponse,
    ObservationOutputSummary,
    OriginOutputSummary,
    ForecastOutputSummary,
    QualityAssessmentSummary,
    ReproducibilitySummary,
)
from scripts.validate_real_scene import PROJECT_ROOT


class TestProductionOutputAndDemo(unittest.TestCase):
    """Test suite for Task 5 production output contract, provenance, and demo validation."""

    @classmethod
    def setUpClass(cls):
        cls.project_root = PROJECT_ROOT
        cls.slick = load_demo_slick_input(cls.project_root)
        cls.service = create_demo_pipeline_service(cls.project_root, random_seed=42)
        cls.pipeline_response = cls.service.run_pipeline(cls.slick)
        cls.unified_result = cls.pipeline_response.to_unified_result()

    # 1. Unified Output Schema Structure
    def test_01_unified_output_schema_structure(self):
        """Verify unified Feature 2 output conforms to the complete contract structure."""
        self.assertIsInstance(self.unified_result, UnifiedFeature2Result)
        self.assertEqual(self.unified_result.feature2_version, "1.0.0")
        self.assertEqual(self.unified_result.spill_id, self.slick.spill_id)

        # Check sub-models exist
        self.assertIsInstance(self.unified_result.observation, ObservationOutputSummary)
        self.assertIsInstance(self.unified_result.origin, OriginOutputSummary)
        self.assertIsInstance(self.unified_result.forecast, ForecastOutputSummary)
        self.assertIsInstance(self.unified_result.quality, QualityAssessmentSummary)
        self.assertIsInstance(self.unified_result.reproducibility, ReproducibilitySummary)

    # 2. Origin Semantics (evidence_score, not probability)
    def test_02_origin_semantics_and_disclaimers(self):
        """Verify origin result uses evidence_score, not probability, and includes scientific disclaimer."""
        origin = self.unified_result.origin
        self.assertIsNotNone(origin.best_candidate)
        self.assertGreaterEqual(origin.best_candidate.evidence_score, 0.0)
        self.assertLessEqual(origin.best_candidate.evidence_score, 1.0)
        self.assertEqual(origin.evidence_score, origin.best_candidate.evidence_score)

        # Confirm disclaimer explicitly denies calibrated probability
        disclaimer = origin.disclaimer
        self.assertIn("normalized evidence/confidence metric", disclaimer)
        self.assertIn("not a calibrated probability", disclaimer)
        self.assertIn("not a confirmed spill source", disclaimer)

    # 3. 72h Production Origin Horizon Preserved
    def test_03_72h_production_horizon_preserved(self):
        """Verify production configuration preserves 72h historical search horizon and 3h candidate interval."""
        self.assertEqual(default_settings.backward.max_backtrack_hours, 72.0)
        self.assertEqual(default_settings.backward.candidate_time_step_hours, 3.0)
        self.assertEqual(self.unified_result.origin.search_horizon_hours, 72.0)

        # Verify historical window spans exactly 72 hours
        hist_win = self.unified_result.environment.historical_window
        duration_h = (hist_win.end - hist_win.start).total_seconds() / 3600.0
        self.assertAlmostEqual(duration_h, 72.0, delta=0.01)

    # 4. Release-Time Window Single Source of Truth
    def test_04_release_time_window_single_source_of_truth(self):
        """Verify release-time window originates directly from the origin estimator."""
        rel_win = self.unified_result.origin.release_time_window
        self.assertIsNotNone(rel_win.start)
        self.assertIsNotNone(rel_win.end)
        self.assertLessEqual(rel_win.start, rel_win.end)
        # Matches the underlying pipeline response release window
        self.assertEqual(rel_win.start, self.pipeline_response.origin_estimation.release_time_window.start)
        self.assertEqual(rel_win.end, self.pipeline_response.origin_estimation.release_time_window.end)

    # 5. Forecast Initialization from Observed Feature 1 Slick at T0
    def test_05_forecast_initialization_from_observed_slick(self):
        """Verify forecast initialization anchor is strictly observed Feature 1 slick at T0."""
        init = self.unified_result.forecast.initialization
        self.assertEqual(init.source, "observed_feature1_slick")
        self.assertEqual(init.time, self.unified_result.observation.observation_time)
        self.assertAlmostEqual(init.centroid.lat, self.slick.centroid.latitude, delta=1e-4)
        self.assertAlmostEqual(init.centroid.lon, self.slick.centroid.longitude, delta=1e-4)
        self.assertIn("observed Feature 1 slick at T0", init.notes)
        self.assertIn("not used as the forecast initialization", init.notes)

    # 6. Exact +6h, +12h, +24h, +48h Checkpoints in Forecast
    def test_06_forecast_checkpoints_horizons(self):
        """Verify unified forecast output contains exactly +6h, +12h, +24h, and +48h horizons."""
        horizons = self.unified_result.forecast.horizons
        self.assertEqual(len(horizons), 4)

        lead_times = [h.horizon_hours for h in horizons]
        self.assertEqual(lead_times, [6.0, 12.0, 24.0, 48.0])

        obs_time = self.unified_result.observation.observation_time
        for h in horizons:
            expected_time = obs_time + timedelta(hours=h.horizon_hours)
            self.assertEqual(h.timestamp, expected_time)
            self.assertGreater(h.active_particles, 0)
            self.assertGreater(h.spread_radius_km, 0.0)
            self.assertIn(h.quality, ["HIGH", "MEDIUM", "LOW"])

    # 7. Environmental Provider Provenance for All 4 Providers
    def test_07_environmental_provenance_metadata(self):
        """Verify all 4 environmental providers expose comprehensive dataset provenance."""
        prov = self.unified_result.environment.providers
        self.assertIn("historical_wind", prov)
        self.assertIn("historical_currents", prov)
        self.assertIn("forecast_wind", prov)
        self.assertIn("forecast_currents", prov)

        for p_key in ["historical_wind", "historical_currents", "forecast_wind", "forecast_currents"]:
            meta = prov[p_key]
            self.assertIn("source", meta)
            self.assertIn("product", meta)
            self.assertIn("variables", meta)
            self.assertIn("units", meta)
            self.assertIn("mode", meta)
            self.assertIn("source_type", meta)
            self.assertIn("cache_status", meta)

    # 8. Deterministic Quality Flags
    def test_08_quality_flags_deterministic_rules(self):
        """Verify quality flags follow documented deterministic rules."""
        q = self.unified_result.quality
        self.assertIn(q.overall, ["HIGH", "MEDIUM", "LOW"])
        self.assertTrue(q.historical_data_complete)
        self.assertTrue(q.forecast_data_complete)
        self.assertGreaterEqual(q.particle_retention_ratio, 0.0)
        self.assertLessEqual(q.particle_retention_ratio, 1.0)
        self.assertIsInstance(q.coverage_warnings, list)

        # High quality if retention >= 80% and 0 critical warnings
        if q.particle_retention_ratio >= 0.8 and len(q.coverage_warnings) == 0:
            self.assertEqual(q.overall, "HIGH")

    # 9. Reproducibility Metadata and Hash
    def test_09_reproducibility_metadata_and_hash(self):
        """Verify configuration hash is deterministic, reproducible, and sensitive to parameter changes."""
        r = self.unified_result.reproducibility
        self.assertEqual(r.random_seed, 42)
        self.assertGreater(len(r.configuration_hash), 8)

        # Deterministic consistency: identical settings produce identical hash
        settings_a = Feature2Settings(random_seed=42)
        settings_b = Feature2Settings(random_seed=42)
        self.assertEqual(settings_a.get_reproducibility_hash(), settings_b.get_reproducibility_hash())

        # Sensitivity: altered physics parameter produces different hash
        settings_c = Feature2Settings(random_seed=999)
        self.assertNotEqual(settings_a.get_reproducibility_hash(), settings_c.get_reproducibility_hash())

    # 10. GeoJSON Properties and Formatting
    def test_10_geojson_output_properties(self):
        """Verify GeoJSON FeatureCollection outputs contain required properties."""
        # A. Observed Slick GeoJSON
        obs_gj = OutputFormatter.observed_slick_to_geojson(self.slick)
        self.assertEqual(obs_gj["type"], "FeatureCollection")
        self.assertGreaterEqual(len(obs_gj["features"]), 1)
        f0 = obs_gj["features"][0]
        self.assertEqual(f0["properties"]["spill_id"], self.slick.spill_id)
        self.assertIn("area_km2", f0["properties"])

        # B. Unified Result GeoJSON
        unified_gj = OutputFormatter.unified_result_to_geojson(self.unified_result)
        self.assertEqual(unified_gj["type"], "FeatureCollection")
        self.assertGreater(len(unified_gj["features"]), 5)

        feature_types = [f["properties"]["feature_type"] for f in unified_gj["features"]]
        self.assertIn("observed_slick_polygon", feature_types)
        self.assertIn("candidate_origin_centroid", feature_types)
        self.assertIn("forecast_predicted_centroid", feature_types)

        # Check candidate origin properties
        orig_f = next(f for f in unified_gj["features"] if f["properties"]["feature_type"] == "candidate_origin_centroid")
        self.assertIn("evidence_score", orig_f["properties"])
        self.assertIn("release_window_start", orig_f["properties"])
        self.assertIn("release_window_end", orig_f["properties"])

        # Check forecast centroid properties
        fc_f = next(f for f in unified_gj["features"] if f["properties"]["feature_type"] == "forecast_predicted_centroid")
        self.assertIn("horizon_hours", fc_f["properties"])
        self.assertIn("forecast_timestamp", fc_f["properties"])
        self.assertIn("spread_radius_km", fc_f["properties"])

    # 11. Offline Deterministic Demo Execution
    def test_11_offline_deterministic_demo_execution(self):
        """Verify run_offline_demo executes cleanly without external credentials and writes artifacts."""
        out_dir = os.path.join(self.project_root, "demo_output")
        res, gj = run_offline_demo(project_root=self.project_root, output_dir=out_dir, random_seed=42)

        self.assertIsInstance(res, UnifiedFeature2Result)
        self.assertEqual(gj["type"], "FeatureCollection")
        self.assertTrue(os.path.exists(os.path.join(out_dir, "demo_unified_result.json")))
        self.assertTrue(os.path.exists(os.path.join(out_dir, "demo_pipeline.geojson")))

    # 12. Fail-Closed Live Mode Without Credentials
    def test_12_live_mode_fails_closed(self):
        """Verify unconfigured live remote providers refuse to fabricate data and fail closed."""
        unconfigured_era5 = ERA5WindProvider()
        unconfigured_cop = CopernicusCurrentsProvider()
        obs_domain = SentinelObservationDomain.from_slick_input(self.slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(obs_domain)

        if not os.getenv("CDSAPI_KEY"):
            self.assertFalse(unconfigured_era5.fetch_grid(query_domain))
        if not (os.getenv("CMEMS_USERNAME") and os.getenv("CMEMS_PASSWORD")):
            self.assertFalse(unconfigured_cop.fetch_grid(query_domain))

    # 13. End-to-End Golden Integration Test
    def test_13_end_to_end_golden_test(self):
        """Golden integration test verifying all unified sections, coordinate consistency, and horizons."""
        res = self.unified_result

        # 1. Observation
        self.assertAlmostEqual(res.observation.centroid.lat, 55.241575, delta=0.01)
        self.assertAlmostEqual(res.observation.centroid.lon, 4.053477, delta=0.01)
        self.assertGreater(res.observation.area_km2, 1.0)

        # 2. Dynamic Domain
        d = res.environment.domain
        self.assertLess(d.bbox.min_lat, res.observation.centroid.lat)
        self.assertGreater(d.bbox.max_lat, res.observation.centroid.lat)
        self.assertLess(d.bbox.min_lon, res.observation.centroid.lon)
        self.assertGreater(d.bbox.max_lon, res.observation.centroid.lon)

        # 3. Origin Candidate
        self.assertIsNotNone(res.origin.best_candidate)
        bc = res.origin.best_candidate
        self.assertGreater(bc.evidence_score, 0.0)
        self.assertLessEqual(bc.evidence_score, 1.0)
        self.assertGreater(bc.uncertainty.spread_radius_km, 0.0)

        # 4. Forecast Checkpoints (+6h, +12h, +24h, +48h)
        self.assertEqual(len(res.forecast.horizons), 4)
        for h in res.forecast.horizons:
            self.assertTrue(h.valid)
            self.assertGreater(h.active_particles, 0)
            self.assertGreater(h.spread_radius_km, 0.0)

        # 5. Provenance & Reproducibility
        self.assertEqual(len(res.environment.providers), 4)
        self.assertEqual(res.reproducibility.feature2_version, "1.0.0")
        self.assertEqual(res.quality.overall, "HIGH")


if __name__ == "__main__":
    unittest.main()
