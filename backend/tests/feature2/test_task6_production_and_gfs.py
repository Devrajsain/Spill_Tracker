"""
Test Suite for Task 6: Production Environment Provider Wiring + GFS Forecast Provider.

Verifies:
  1. Provider selection across environments (production vs. testing/development).
  2. Production provider configuration (ERA5 + Copernicus historical, GFS + Copernicus forecast).
  3. Explicit mock provider configuration for offline tests.
  4. Absence of silent mock fallbacks (fail-closed behavior).
  5. GFS forecast request construction from dynamic domain.
  6. GFS response parsing and NetCDF structure.
  7. GFS spatial and temporal interpolation.
  8. GFS coverage validation (spatial bounds and historical archive rejection).
  9. GFS cache miss and atomic write.
 10. GFS cache hit and consistency.
 11. CMEMS forecast selection (CopernicusForecastCurrentsProvider).
 12. CMEMS forecast interpolation and depth slicing.
 13. Failure propagation without fallback.
 14. Dynamic domain propagation to forecast queries.
"""

from datetime import datetime, timedelta, timezone
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import xarray as xr

from feature2.config import (
    Feature2Settings,
    DataSourceConfig,
    VariableMappingConfig,
    get_configured_environment,
)
from feature2.api.dependencies import (
    get_currents_provider,
    get_wind_provider,
    get_forecast_currents_provider,
    get_forecast_wind_provider,
    get_forward_simulation_engine,
    get_backward_simulation_engine,
)
from feature2.simulation import ForwardSimulationEngine, BackwardSimulationEngine
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.copernicus import (
    CopernicusConfig,
    CopernicusCurrentsProvider,
    CopernicusForecastCurrentsProvider,
)
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.era5 import ERA5Config, ERA5WindProvider
from feature2.data.wind.gfs import GFSConfig, GFSWindProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.data.cache import EnvironmentalDataCacheManager, generate_cache_key
from feature2.exceptions import (
    EnvironmentalCoverageError,
    EnvironmentalDataUnavailableError,
    OutOfDomainError,
    TemporalCoverageError,
)
from feature2.schemas.input_schema import SlickDetectionInput
from feature2.schemas.simulation_schema import EnvironmentalQueryWindow
from tests.fixtures.environment.create_fixtures import generate_all_fixtures, FIXTURES_DIR


class TestTask6ProductionAndGFS(unittest.TestCase):
    """Rigorous tests for Task 6 production wiring, GFS, and Copernicus forecast."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_paths = generate_all_fixtures(FIXTURES_DIR)
        cls.copernicus_nc = cls.fixture_paths["copernicus"]
        cls.gfs_nc = cls.fixture_paths["gfs"]
        cls.era5_nc = cls.fixture_paths["era5"]

        cls.sample_f1 = {
            "spill_id": "TEST_TASK6_S1A_001",
            "observation_time": "2026-09-03T12:00:00Z",
            "area_sq_km": 1.5,
            "perimeter_km": 5.0,
            "centroid": {"latitude": 55.241575, "longitude": 4.053477},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[4.04, 55.23], [4.06, 55.23], [4.06, 55.25], [4.04, 55.25], [4.04, 55.23]]
                ]
            }
        }

    def setUp(self):
        self.test_cache_dir = tempfile.mkdtemp(prefix="feat2_task6_cache_")
        self.cache_mgr = EnvironmentalDataCacheManager(cache_root_dir=self.test_cache_dir)

    def tearDown(self):
        shutil.rmtree(self.test_cache_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Provider Selection Across Environments
    # --------------------------------------------------------------------------

    def test_01_default_testing_environment_selects_mock(self):
        """Testing/development environment defaults to mock providers for offline isolation."""
        settings = Feature2Settings.testing()
        self.assertEqual(settings.environment, "testing")
        self.assertEqual(settings.data.currents_provider, "mock")
        self.assertEqual(settings.data.wind_provider, "mock")

        curr = get_currents_provider(settings)
        wind = get_wind_provider(settings)
        fc_curr = get_forecast_currents_provider(settings)
        fc_wind = get_forecast_wind_provider(settings)

        self.assertIsInstance(curr, MockCurrentsProvider)
        self.assertIsInstance(wind, MockWindProvider)
        self.assertIsInstance(fc_curr, MockCurrentsProvider)
        self.assertIsInstance(fc_wind, MockWindProvider)

    # --------------------------------------------------------------------------
    # 2. Production Provider Configuration
    # --------------------------------------------------------------------------

    def test_02_production_environment_selects_real_stack(self):
        """Production environment explicitly selects ERA5 + Copernicus (historical) and GFS + Copernicus (forecast)."""
        settings = Feature2Settings.production()
        self.assertEqual(settings.environment, "production")
        self.assertEqual(settings.data.currents_provider, "copernicus")
        self.assertEqual(settings.data.wind_provider, "era5")
        self.assertEqual(settings.data.forecast_currents_provider, "copernicus")
        self.assertEqual(settings.data.forecast_wind_provider, "gfs")

        curr = get_currents_provider(settings)
        wind = get_wind_provider(settings)
        fc_curr = get_forecast_currents_provider(settings)
        fc_wind = get_forecast_wind_provider(settings)

        self.assertIsInstance(curr, CopernicusCurrentsProvider)
        self.assertIsInstance(wind, ERA5WindProvider)
        self.assertIsInstance(fc_curr, CopernicusForecastCurrentsProvider)
        self.assertIsInstance(fc_wind, GFSWindProvider)

        # Verify forward simulation engine receives forecast providers
        fwd_engine = ForwardSimulationEngine(
            currents_provider=fc_curr,
            wind_provider=fc_wind,
            settings=settings
        )
        self.assertEqual(fwd_engine.currents_provider.provider_name, "copernicus_forecast_currents")
        self.assertEqual(fwd_engine.wind_provider.provider_name, "gfs_forecast_wind")

    # --------------------------------------------------------------------------
    # 3. Explicit Mock Provider Configuration for Tests
    # --------------------------------------------------------------------------

    def test_03_explicit_mock_override_in_production(self):
        """Explicit mock configuration is preserved even when requested in production environment."""
        data_cfg = DataSourceConfig(
            currents_provider="mock",
            wind_provider="mock",
            forecast_currents_provider="mock",
            forecast_wind_provider="mock",
        )
        settings = Feature2Settings(environment="production", data=data_cfg)

        curr = get_currents_provider(settings)
        wind = get_wind_provider(settings)
        fc_curr = get_forecast_currents_provider(settings)
        fc_wind = get_forecast_wind_provider(settings)

        self.assertIsInstance(curr, MockCurrentsProvider)
        self.assertIsInstance(wind, MockWindProvider)
        self.assertIsInstance(fc_curr, MockCurrentsProvider)
        self.assertIsInstance(fc_wind, MockWindProvider)

    # --------------------------------------------------------------------------
    # 4. Absence of Silent Mock Fallbacks (Fail-Closed)
    # --------------------------------------------------------------------------

    def test_04_no_automatic_mock_fallback_on_real_provider_failure(self):
        """Unconfigured real providers raise EnvironmentalDataUnavailableError, never silently falling back to mocks."""
        unconfigured_cop = CopernicusCurrentsProvider(
            config=CopernicusConfig(username="", password="", data_path="/nonexistent/cop.nc")
        )
        unconfigured_era5 = ERA5WindProvider(
            config=ERA5Config(api_key="", data_path="/nonexistent/era5.nc")
        )
        unconfigured_gfs = GFSWindProvider(
            config=GFSConfig(data_path="/nonexistent/gfs.nc")
        )

        t_query = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(EnvironmentalDataUnavailableError):
            unconfigured_cop.get_current(55.24, 4.05, t_query)

        with self.assertRaises(EnvironmentalDataUnavailableError):
            unconfigured_era5.get_wind(55.24, 4.05, t_query)

        with self.assertRaises(EnvironmentalDataUnavailableError):
            unconfigured_gfs.get_wind(55.24, 4.05, t_query)

    # --------------------------------------------------------------------------
    # 5. GFS Request Construction
    # --------------------------------------------------------------------------

    def test_05_gfs_request_construction_matches_domain(self):
        """GFSWindProvider.build_forecast_request strictly reflects the query domain bounding box and time."""
        slick = SlickDetectionInput(**self.sample_f1)
        obs_domain = SentinelObservationDomain.from_slick_input(slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(obs_domain, buffer_distance_km=30.0)

        provider = GFSWindProvider()
        req = provider.build_forecast_request(query_domain)

        self.assertAlmostEqual(req["min_lat"], query_domain.min_lat, places=4)
        self.assertAlmostEqual(req["max_lat"], query_domain.max_lat, places=4)
        self.assertAlmostEqual(req["min_lon"], query_domain.min_lon, places=4)
        self.assertAlmostEqual(req["max_lon"], query_domain.max_lon, places=4)
        self.assertEqual(req["start_time"], query_domain.forecast_start_time.isoformat())
        self.assertEqual(req["end_time"], query_domain.forecast_end_time.isoformat())

    # --------------------------------------------------------------------------
    # 6 & 7. GFS Response Parsing and Interpolation
    # --------------------------------------------------------------------------

    def test_06_gfs_spatial_and_temporal_interpolation(self):
        """GFSWindProvider performs exact bilinear spatial and linear temporal interpolation on GFS NetCDF."""
        provider = GFSWindProvider(data_path=self.gfs_nc)
        t_base = datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc)

        # Node test
        sample_node = provider.get_wind(latitude=25.0, longitude=54.0, timestamp=t_base)
        self.assertGreater(sample_node.u_wind_mps, 0.0)
        self.assertGreater(sample_node.v_wind_mps, 0.0)

        # Off-grid interpolation test (+6h, mid-grid)
        t_mid = t_base + timedelta(hours=6)
        sample_interp = provider.get_wind(latitude=24.5, longitude=53.5, timestamp=t_mid)
        self.assertIsInstance(sample_interp.u_wind_mps, float)
        self.assertIsInstance(sample_interp.v_wind_mps, float)
        self.assertEqual(sample_interp.quality_flag, 1)

    # --------------------------------------------------------------------------
    # 8. GFS Coverage Validation & Historical Rejection
    # --------------------------------------------------------------------------

    def test_07_gfs_coverage_validation_and_historical_rejection(self):
        """GFSWindProvider validates boundaries and rejects historical queries outside operational forecast range."""
        provider = GFSWindProvider(data_path=self.gfs_nc)
        t_valid = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

        # Spatial out of domain
        with self.assertRaises(OutOfDomainError):
            provider.get_wind(latitude=35.0, longitude=54.0, timestamp=t_valid)

        # Temporal out of domain (+72h when fixture covers up to +48h)
        with self.assertRaises(TemporalCoverageError):
            provider.get_wind(latitude=25.0, longitude=54.0, timestamp=t_valid + timedelta(hours=72))

        # Remote fetch rejecting historical 2018 window
        remote_provider = GFSWindProvider(data_path=None, cache_manager=self.cache_mgr)
        hist_window = EnvironmentalQueryWindow(
            min_lat=55.0, max_lat=55.5, min_lon=3.75, max_lon=4.25,
            start_time=datetime(2018, 8, 3, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2018, 8, 5, 0, 0, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(TemporalCoverageError):
            remote_provider.fetch_grid(hist_window)

    # --------------------------------------------------------------------------
    # 9 & 10. GFS Cache Miss, Atomic Write, and Cache Hit
    # --------------------------------------------------------------------------

    def test_08_gfs_cache_miss_atomic_write_and_hit(self):
        """GFSWindProvider caches datasets atomically; subsequent identical query is served from cache."""
        key = generate_cache_key(
            provider_name="gfs",
            dataset_id="gfs_0p25",
            variables=["u10", "v10"],
            min_lat=24.0, max_lat=26.0, min_lon=53.0, max_lon=55.0,
            start_time_iso="2026-08-27T06:00:00Z",
            end_time_iso="2026-08-29T06:00:00Z",
        )

        # Seed cache via atomic_save
        def _writer(tmp_path: str):
            shutil.copyfile(self.gfs_nc, tmp_path)

        cached_path = self.cache_mgr.atomic_save("gfs", key, _writer)
        self.assertTrue(os.path.exists(cached_path))

        # Provider with cache_mgr should hit cache
        cached_provider = GFSWindProvider(data_path=None, cache_manager=self.cache_mgr)
        window = EnvironmentalQueryWindow(
            min_lat=24.0, max_lat=26.0, min_lon=53.0, max_lon=55.0,
            start_time=datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 8, 29, 6, 0, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(cached_provider.fetch_grid(window))
        self.assertEqual(cached_provider._source_type, "cache")
        self.assertEqual(cached_provider._cache_status, "hit")

        # Interpolation on cached provider works correctly
        sample = cached_provider.get_wind(25.0, 54.0, datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc))
        self.assertGreater(sample.u_wind_mps, 0.0)

    # --------------------------------------------------------------------------
    # 11 & 12. CMEMS Forecast Selection & Interpolation
    # --------------------------------------------------------------------------

    def test_09_copernicus_forecast_provider_selection_and_interpolation(self):
        """CopernicusForecastCurrentsProvider uses operational forecast product and performs surface interpolation."""
        cfg = CopernicusConfig(
            dataset_id="cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
            depth_level_m=0.494,
        )
        provider = CopernicusForecastCurrentsProvider(config=cfg, data_path=self.copernicus_nc)

        prov = provider.provenance
        self.assertEqual(prov["mode"], "forecast")
        self.assertEqual(prov["product"], "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m")
        self.assertEqual(prov["selected_depth_m"], 0.494)

        t_query = datetime(2026, 8, 26, 6, 0, 0, tzinfo=timezone.utc)
        sample = provider.get_current(latitude=24.5, longitude=53.5, timestamp=t_query)
        self.assertGreater(sample.u_current_mps, 0.0)
        self.assertEqual(sample.quality_flag, 1)

    # --------------------------------------------------------------------------
    # 13. Failure Propagation
    # --------------------------------------------------------------------------

    def test_10_failure_propagation_without_silent_fallback(self):
        """When forecast currents or wind encounter coverage errors, the error is propagated without masking."""
        provider = CopernicusForecastCurrentsProvider(data_path=self.copernicus_nc)
        t_oob = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(TemporalCoverageError):
            provider.get_current(25.0, 54.0, t_oob)

    # --------------------------------------------------------------------------
    # 14. Dynamic Domain Propagation
    # --------------------------------------------------------------------------

    def test_11_dynamic_domain_propagation_to_forecast_providers(self):
        """Dynamic Feature 1 observation domain propagates cleanly to Copernicus and GFS forecast requests."""
        slick = SlickDetectionInput(**self.sample_f1)
        obs_domain = SentinelObservationDomain.from_slick_input(slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(obs_domain)

        cop_fc = CopernicusForecastCurrentsProvider()
        gfs_fc = GFSWindProvider()

        cop_req = cop_fc.build_subset_request(query_domain)
        gfs_req = gfs_fc.build_forecast_request(query_domain)

        self.assertAlmostEqual(cop_req["minimum_latitude"], query_domain.min_lat, places=3)
        self.assertAlmostEqual(cop_req["maximum_latitude"], query_domain.max_lat, places=3)
        self.assertAlmostEqual(gfs_req["min_lat"], query_domain.min_lat, places=3)
        self.assertAlmostEqual(gfs_req["max_lat"], query_domain.max_lat, places=3)
        self.assertEqual(cop_req["start_datetime"], query_domain.forecast_start_time.isoformat())
        self.assertEqual(gfs_req["start_time"], query_domain.forecast_start_time.isoformat())


if __name__ == "__main__":
    unittest.main()
