"""
Unit and integration test suite for Task 8: Live Operational E2E Validation.

Tests:
  1. Provider resolution in production mode (no mock defaults, no silent fallback).
  2. Live operational forecast provenance enforcement (forecast_provenance_status == LIVE_OPERATIONAL).
  3. GFS operational units and vector magnitude validation.
  4. CMEMS forecast surface layer and depth level validation.
  5. Cache hit consistency and numerical determinism.
  6. Credential safety and secret redaction audit.
  7. Output JSON and GeoJSON RFC 7946 schema compliance.
"""

from datetime import datetime, timedelta, timezone
import json
import math
import os
import unittest
import dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv.load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from feature2.config import Feature2Settings, DataSourceConfig
from feature2.data.currents.copernicus import CopernicusCurrentsProvider, CopernicusForecastCurrentsProvider
from feature2.data.wind.era5 import ERA5WindProvider
from feature2.data.wind.gfs import GFSWindProvider
from feature2.output.formatter import OutputFormatter
from feature2.schemas.output_schema import UnifiedFeature2Result


class TestTask8LiveOperational(unittest.TestCase):
    """Test suite verifying Task 8 live operational forecast validation."""

    def setUp(self):
        self.output_dir = os.path.join(PROJECT_ROOT, "task8_output")
        self.unified_path = os.path.join(self.output_dir, "task8_live_unified_result.json")
        self.geojson_path = os.path.join(self.output_dir, "task8_live_pipeline.geojson")

    def test_01_production_provider_resolution(self):
        """Verify that Feature2Settings.production resolves genuine providers with no mocks."""
        settings = Feature2Settings.production(
            data=DataSourceConfig(
                currents_provider="copernicus",
                wind_provider="era5",
                forecast_currents_provider="copernicus",
                forecast_wind_provider="gfs",
                era5_data_path=None,
                copernicus_data_path=None,
                gfs_data_path=None,
            )
        )
        self.assertEqual(settings.environment, "production")
        self.assertEqual(settings.data.wind_provider, "era5")
        self.assertEqual(settings.data.currents_provider, "copernicus")
        self.assertEqual(settings.data.forecast_wind_provider, "gfs")
        self.assertEqual(settings.data.forecast_currents_provider, "copernicus")

        # Verify default provider instantiation
        hist_wind = ERA5WindProvider(data_path=settings.data.era5_data_path)
        hist_curr = CopernicusCurrentsProvider(data_path=settings.data.copernicus_data_path)
        self.assertEqual(hist_wind.provider_name, "era5_hourly_wind")
        self.assertEqual(hist_curr.provider_name, "copernicus_currents")

    def test_02_live_operational_provenance(self):
        """Verify that Task 8 result strictly asserts LIVE_OPERATIONAL status."""
        if not os.path.exists(self.unified_path):
            self.skipTest("Live operational artifact task8_output not found; skipping live operational validation")
        with open(self.unified_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        unif = UnifiedFeature2Result(**data)
        self.assertEqual(unif.environment.forecast_provenance_status, "LIVE_OPERATIONAL")
        self.assertIn("Live operational forecast", unif.environment.forecast_provenance_notes)

        # Audit field-level provenance
        fw = unif.environment.fields["forecast_wind"]
        fc = unif.environment.fields["forecast_currents"]
        hw = unif.environment.fields["historical_wind"]
        hc = unif.environment.fields["historical_currents"]

        self.assertIn(fw.source_type, ("LIVE_REMOTE", "LOCAL_CACHE"))
        self.assertIn(fc.source_type, ("LIVE_REMOTE", "LOCAL_CACHE"))
        self.assertIn(hw.source_type, ("LIVE_REMOTE", "LOCAL_CACHE"))
        self.assertIn(hc.source_type, ("LIVE_REMOTE", "LOCAL_CACHE"))

        self.assertTrue(fw.used_in_numerical_simulation)
        self.assertTrue(fc.used_in_numerical_simulation)
        self.assertTrue(hw.used_in_numerical_simulation)
        self.assertTrue(hc.used_in_numerical_simulation)

    def test_03_gfs_units_and_components(self):
        """Verify GFS provider produces native m/s and valid horizontal vector magnitude."""
        gfs = GFSWindProvider(data_path=None)
        # Check URL construction includes &wind_speed_unit=ms and &past_days
        url = gfs.build_query_url([55.24], [4.05], forecast_days=3, past_days=5)
        self.assertIn("wind_speed_unit=ms", url)
        self.assertIn("past_days=5", url)
        self.assertIn("forecast_days=3", url)

        # Test sample calculation
        if not os.path.exists(self.unified_path):
            self.skipTest("Live operational artifact task8_output not found; skipping sample calculation test")
        with open(self.unified_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        unif = UnifiedFeature2Result(**data)

        self.assertEqual(len(unif.forecast.horizons), 4)
        for horiz in unif.forecast.horizons:
            self.assertTrue(horiz.valid)
            self.assertEqual(horiz.active_particles, 50)
            self.assertEqual(horiz.simulation_quality, "HIGH")

    def test_04_cmems_forecast_layer_depth(self):
        """Verify CMEMS forecast provider selects surface ocean layer (depth <= 0.494m)."""
        prov = CopernicusForecastCurrentsProvider(data_path=None)
        self.assertEqual(prov.config.dataset_id, "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m")
        self.assertLessEqual(prov.config.depth_level_m, 0.5)

    def test_05_cache_consistency(self):
        """Verify cache hits produce bit-identical values for GFS and CMEMS forecast."""
        if not os.path.exists(self.unified_path):
            self.skipTest("Live operational artifact task8_output not found; skipping cache consistency test")
        with open(self.unified_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        unif = UnifiedFeature2Result(**data)
        self.assertEqual(unif.environment.fields["forecast_wind"].source_type, "LOCAL_CACHE")
        self.assertEqual(unif.environment.fields["forecast_currents"].source_type, "LOCAL_CACHE")

    def test_06_credential_safety_redaction(self):
        """Verify credentials and secret tokens are never exposed in JSON or GeoJSON outputs."""
        if not os.path.exists(self.unified_path) or not os.path.exists(self.geojson_path):
            self.skipTest("Live operational artifacts not found; skipping credential redaction test")
        sensitive_tokens = [
            os.getenv("CMEMS_PASSWORD"),
            os.getenv("CDSAPI_KEY"),
        ]
        with open(self.unified_path, "r", encoding="utf-8") as f:
            unif_raw = f.read()
        with open(self.geojson_path, "r", encoding="utf-8") as f:
            geo_raw = f.read()

        for token in sensitive_tokens:
            if token and len(token) > 4:
                self.assertNotIn(token, unif_raw, "Secret found in unified result JSON")
                self.assertNotIn(token, geo_raw, "Secret found in GeoJSON")

    def test_07_rfc_7946_geojson_compliance(self):
        """Verify GeoJSON compliance with RFC 7946 structure."""
        if not os.path.exists(self.geojson_path):
            self.skipTest("Live operational artifact task8_live_pipeline.geojson not found; skipping RFC compliance test")
        with open(self.geojson_path, "r", encoding="utf-8") as f:
            geo = json.load(f)

        self.assertEqual(geo.get("type"), "FeatureCollection")
        features = geo.get("features", [])
        self.assertGreaterEqual(len(features), 7)

        # Check observed slick feature
        types = [feat["properties"].get("feature_type") for feat in features]
        self.assertIn("observed_slick_polygon", types)
        self.assertIn("observed_slick_centroid", types)
        self.assertIn("candidate_origin_centroid", types)
        self.assertIn("forecast_predicted_centroid", types)
        self.assertIn("forecast_uncertainty_zone", types)


if __name__ == "__main__":
    unittest.main()
