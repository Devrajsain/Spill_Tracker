"""
Comprehensive test suite for Real Environmental Data Integration (Task 4).
Tests:
  1. Real ERA5 historical wind provider (NetCDF ingestion, interpolation, units, coverage errors, provenance).
  2. Real Copernicus Marine currents provider (surface layer depth selection, uo/vo mapping, units, coverage errors, provenance).
  3. Real NOAA GFS operational forecast wind provider (operational lead times +0 to +48h, interpolation, coverage errors).
  4. Environmental data cache manager (deterministic keys, domain isolation, atomic saves, integrity checks).
  5. Multi-scene spatial and temporal isolation (Scene A Arabian Gulf vs Scene B South Pacific).
  6. Coordinate and dateline conventions (descending latitudes, [0, 360] longitudes).
  7. End-to-end backward origin estimation consuming real environmental providers.
  8. End-to-end forward slick forecasting consuming real environmental providers.
  9. Safe live smoke testing (skips cleanly when credentials absent).
"""

from datetime import datetime, timedelta, timezone
import os
import shutil
import tempfile
import unittest
import numpy as np

from feature2.config import Feature2Settings, BackwardTracingConfig, ForecastConfig
from feature2.data.base import CurrentSample, WindSample
from feature2.data.cache import EnvironmentalDataCacheManager, generate_cache_key
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.copernicus import (
    CopernicusConfig,
    CopernicusCurrentsProvider,
    CopernicusForecastCurrentsProvider,
)
from feature2.data.wind.era5 import ERA5Config, ERA5WindProvider
from feature2.data.wind.gfs import GFSConfig, GFSWindProvider
from feature2.exceptions import (
    EnvironmentalCoverageError,
    EnvironmentalDataUnavailableError,
    OutOfDomainError,
    TemporalCoverageError,
)
from feature2.forecast.forecaster import ForwardForecaster
from feature2.origin.estimator import OriginEstimator
from feature2.pipeline.service import Feature2PipelineService
from feature2.schemas.input_schema import CentroidCoordinates, GeoJSONGeometry, SlickDetectionInput
from feature2.schemas.simulation_schema import EnvironmentalQueryWindow
from feature2.simulation.forward.engine import ForwardSimulationEngine
from tests.feature2.fixtures.environment.create_fixtures import generate_all_fixtures, FIXTURES_DIR


class TestRealEnvironmentalData(unittest.TestCase):
    """Test suite for Task 4 Real Environmental Data Integration."""

    @classmethod
    def setUpClass(cls):
        """Ensure all synthetic NetCDF test fixtures are generated."""
        cls.fixture_paths = generate_all_fixtures(FIXTURES_DIR)
        cls.era5_nc = cls.fixture_paths["era5"]
        cls.copernicus_nc = cls.fixture_paths["copernicus"]
        cls.gfs_nc = cls.fixture_paths["gfs"]
        cls.descending_lat_nc = cls.fixture_paths["descending_lat"]
        cls.lon360_nc = cls.fixture_paths["lon360"]

        # Base Feature 1 test payload in Arabian Gulf (lat 25.0, lon 54.0)
        cls.f1_payload_gulf = {
            "spill_id": "SAR_SPILL_ARABIAN_GULF_001",
            "observation_time": "2026-08-27T06:00:00Z",
            "area_sq_km": 1.2,
            "perimeter_km": 4.5,
            "centroid": {"latitude": 25.0, "longitude": 54.0},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[53.98, 24.98], [54.02, 24.98], [54.02, 25.02], [53.98, 25.02], [53.98, 24.98]]
                ]
            }
        }

    def setUp(self):
        self.test_cache_dir = tempfile.mkdtemp(prefix="feat2_cache_test_")
        self.cache_mgr = EnvironmentalDataCacheManager(cache_root_dir=self.test_cache_dir)

    def tearDown(self):
        shutil.rmtree(self.test_cache_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. ERA5 Historical Wind Provider Tests
    # --------------------------------------------------------------------------

    def test_era5_exact_analytical_retrieval(self):
        """Verify ERA5 provider retrieves exact known analytical values at grid nodes."""
        provider = ERA5WindProvider(data_path=self.era5_nc)
        
        # Grid node: lat=25.0 (idx 2), lon=54.0 (idx 2), time=2026-08-27T00:00:00Z (t_idx 0)
        # Analytical formula:
        # u10 = 5.0 + 0.1*(25.0 - 24.0) + 0.05*(54.0 - 53.0) + 0.1*0 = 5.15 m/s
        # v10 = 2.0 + 0.05*(25.0 - 24.0) - 0.02*(54.0 - 53.0) - 0.05*0 = 2.03 m/s
        t_query = datetime(2026, 8, 27, 0, 0, 0, tzinfo=timezone.utc)
        sample = provider.get_wind(latitude=25.0, longitude=54.0, timestamp=t_query)

        self.assertIsInstance(sample, WindSample)
        self.assertAlmostEqual(sample.u_wind_mps, 5.15, places=3)
        self.assertAlmostEqual(sample.v_wind_mps, 2.03, places=3)
        self.assertEqual(sample.timestamp, t_query)
        self.assertEqual(sample.quality_flag, 1)

    def test_era5_spatial_bilinear_interpolation(self):
        """Verify ERA5 spatial bilinear interpolation at an intermediate off-grid coordinate."""
        provider = ERA5WindProvider(data_path=self.era5_nc)
        
        # Intermediate: lat=24.25, lon=53.25, time t_idx=0
        # u10 = 5.0 + 0.1*(24.25 - 24) + 0.05*(53.25 - 53) = 5.0 + 0.025 + 0.0125 = 5.0375 m/s
        # v10 = 2.0 + 0.05*(24.25 - 24) - 0.02*(53.25 - 53) = 2.0 + 0.0125 - 0.0050 = 2.0075 m/s
        t_query = datetime(2026, 8, 27, 0, 0, 0, tzinfo=timezone.utc)
        sample = provider.get_wind(latitude=24.25, longitude=53.25, timestamp=t_query)

        self.assertAlmostEqual(sample.u_wind_mps, 5.0375, places=3)
        self.assertAlmostEqual(sample.v_wind_mps, 2.0075, places=3)

    def test_era5_temporal_linear_interpolation(self):
        """Verify ERA5 temporal linear interpolation at intermediate UTC timestamp."""
        provider = ERA5WindProvider(data_path=self.era5_nc)
        
        # lat=25.0, lon=54.0 at t = 1.5 hours (halfway between t_idx 0 [0h] and t_idx 1 [3h])
        # u10(t=0) = 5.15, u10(t=3h) = 5.25 -> midpoint = 5.20 m/s
        # v10(t=0) = 2.03, v10(t=3h) = 1.98 -> midpoint = 2.005 m/s
        t_mid = datetime(2026, 8, 27, 1, 30, 0, tzinfo=timezone.utc)
        sample = provider.get_wind(latitude=25.0, longitude=54.0, timestamp=t_mid)

        self.assertAlmostEqual(sample.u_wind_mps, 5.20, places=3)
        self.assertAlmostEqual(sample.v_wind_mps, 2.005, places=3)

    def test_era5_coverage_error_boundary_enforcement(self):
        """Verify ERA5 raises EnvironmentalCoverageError outside spatial and temporal domain."""
        provider = ERA5WindProvider(data_path=self.era5_nc)
        t_valid = datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc)

        # Latitude out of bounds (coverage is [24.0, 26.0])
        with self.assertRaises(OutOfDomainError):
            provider.get_wind(latitude=23.5, longitude=54.0, timestamp=t_valid)
        with self.assertRaises(OutOfDomainError):
            provider.get_wind(latitude=26.5, longitude=54.0, timestamp=t_valid)

        # Longitude out of bounds (coverage is [53.0, 55.0])
        with self.assertRaises(OutOfDomainError):
            provider.get_wind(latitude=25.0, longitude=52.5, timestamp=t_valid)
        with self.assertRaises(OutOfDomainError):
            provider.get_wind(latitude=25.0, longitude=55.5, timestamp=t_valid)

        # Timestamp before coverage (coverage is [00:00, 12:00])
        with self.assertRaises(TemporalCoverageError):
            provider.get_wind(latitude=25.0, longitude=54.0, timestamp=datetime(2026, 8, 26, 23, 0, 0, tzinfo=timezone.utc))

        # Timestamp after coverage
        with self.assertRaises(TemporalCoverageError):
            provider.get_wind(latitude=25.0, longitude=54.0, timestamp=datetime(2026, 8, 27, 13, 0, 0, tzinfo=timezone.utc))

    def test_era5_descending_latitude_support(self):
        """Verify ERA5 descending latitude convention [North to South] is correctly handled."""
        provider = ERA5WindProvider(data_path=self.descending_lat_nc)
        t_valid = datetime(2026, 8, 27, 3, 0, 0, tzinfo=timezone.utc)
        sample = provider.get_wind(latitude=25.2, longitude=54.2, timestamp=t_valid)
        self.assertAlmostEqual(sample.u_wind_mps, 6.0, places=2)
        self.assertAlmostEqual(sample.v_wind_mps, 3.0, places=2)

    def test_era5_provenance_metadata(self):
        """Verify ERA5 provenance dictionary contains source, product, units, and bounds."""
        provider = ERA5WindProvider(data_path=self.era5_nc)
        prov = provider.provenance
        self.assertEqual(prov["source"], "ECMWF ERA5")
        self.assertEqual(prov["mode"], "historical")
        self.assertEqual(prov["units"], "m/s")
        self.assertEqual(prov["source_type"], "local_netcdf")
        self.assertEqual(prov["spatial_domain"]["min_lat"], 24.0)
        self.assertEqual(prov["spatial_domain"]["max_lat"], 26.0)

    # --------------------------------------------------------------------------
    # 2. Copernicus Marine Current Provider Tests
    # --------------------------------------------------------------------------

    def test_copernicus_surface_layer_depth_selection(self):
        """Verify Copernicus provider explicitly selects surface layer depth (0.494m)."""
        cfg = CopernicusConfig(depth_level_m=0.494)
        provider = CopernicusCurrentsProvider(config=cfg, data_path=self.copernicus_nc)
        
        # Grid node at lat=25.0, lon=54.0, t=2026-08-26T00:00:00Z (t_idx 0)
        # Analytical formula:
        # uo = 0.3 + 0.02*(25.0 - 24.0) + 0.01*(54.0 - 53.0) + 0.02*0 = 0.33 m/s
        # vo = 0.1 + 0.01*(25.0 - 24.0) - 0.01*(54.0 - 53.0) - 0.01*0 = 0.10 m/s
        t_query = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)
        sample = provider.get_current(latitude=25.0, longitude=54.0, timestamp=t_query)

        self.assertIsInstance(sample, CurrentSample)
        self.assertAlmostEqual(sample.u_current_mps, 0.33, places=3)
        self.assertAlmostEqual(sample.v_current_mps, 0.10, places=3)
        self.assertEqual(provider.provenance["selected_depth_m"], 0.494)

    def test_copernicus_spatial_and_temporal_interpolation(self):
        """Verify Copernicus 2D bilinear spatial + linear temporal interpolation."""
        provider = CopernicusCurrentsProvider(data_path=self.copernicus_nc)
        
        # At lat=24.5, lon=53.5, time t=6h (midway between 0h and 12h)
        # uo(0h) = 0.3 + 0.02(0.5) + 0.01(0.5) = 0.315
        # uo(12h) = 0.315 + 0.02 = 0.335 -> midpoint = 0.325 m/s
        t_mid = datetime(2026, 8, 26, 6, 0, 0, tzinfo=timezone.utc)
        sample = provider.get_current(latitude=24.5, longitude=53.5, timestamp=t_mid)

        self.assertAlmostEqual(sample.u_current_mps, 0.325, places=3)

    def test_copernicus_lon360_coordinate_convention(self):
        """Verify Copernicus provider correctly handles [0, 360] longitude datasets."""
        # Fixture has lon [282.0, 284.0] and lat [-13.0, -11.0]
        provider = CopernicusCurrentsProvider(data_path=self.lon360_nc)
        t_valid = datetime(2026, 8, 27, 3, 0, 0, tzinfo=timezone.utc)
        
        # Querying with standard WGS84 Western hemisphere longitude: -77.0 deg -> maps to 283.0 deg
        sample = provider.get_current(latitude=-12.0, longitude=-77.0, timestamp=t_valid)
        self.assertAlmostEqual(sample.u_current_mps, 2.5, places=2)
        self.assertAlmostEqual(sample.v_current_mps, -1.0, places=2)

    def test_copernicus_coverage_boundary_errors(self):
        """Verify Copernicus coverage errors are raised without silent fallbacks."""
        provider = CopernicusCurrentsProvider(data_path=self.copernicus_nc)
        t_valid = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(OutOfDomainError):
            provider.get_current(latitude=27.0, longitude=54.0, timestamp=t_valid)
        with self.assertRaises(TemporalCoverageError):
            provider.get_current(latitude=25.0, longitude=54.0, timestamp=datetime(2026, 8, 31, 0, 0, 0, tzinfo=timezone.utc))

    # --------------------------------------------------------------------------
    # 3. NOAA GFS Operational Forecast Wind Provider Tests
    # --------------------------------------------------------------------------

    def test_gfs_forecast_horizons_up_to_48h(self):
        """Verify GFS forecast provider covers operational lead times from +0h up to +48h."""
        provider = GFSWindProvider(data_path=self.gfs_nc)
        t0 = datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc)

        # Check at +0h, +12h, +24h, +48h
        for h in [0, 12, 24, 48]:
            t_fc = t0 + timedelta(hours=h)
            sample = provider.get_wind(latitude=25.0, longitude=54.0, timestamp=t_fc)
            self.assertIsInstance(sample, WindSample)
            self.assertGreater(sample.u_wind_mps, 0.0)

        # Query beyond +48h must fail with TemporalCoverageError
        with self.assertRaises(TemporalCoverageError):
            provider.get_wind(latitude=25.0, longitude=54.0, timestamp=t0 + timedelta(hours=50))

    def test_gfs_forecast_provenance(self):
        """Verify GFS forecast provenance tracks forecast mode and product."""
        provider = GFSWindProvider(data_path=self.gfs_nc)
        prov = provider.provenance
        self.assertEqual(prov["source"], "NOAA GFS")
        self.assertEqual(prov["mode"], "forecast")
        self.assertEqual(prov["units"], "m/s")

    # --------------------------------------------------------------------------
    # 4. Cache & Download Architecture Tests
    # --------------------------------------------------------------------------

    def test_cache_key_deterministic_and_domain_isolated(self):
        """Verify cache keys are deterministic and isolated between different geographic scenes."""
        key_gulf = generate_cache_key(
            provider_name="era5",
            dataset_id="single-levels",
            variables=["u10", "v10"],
            min_lat=24.0, max_lat=26.0, min_lon=53.0, max_lon=55.0,
            start_time_iso="2026-08-27T00:00:00Z",
            end_time_iso="2026-08-27T12:00:00Z",
        )
        key_gulf_dup = generate_cache_key(
            provider_name="era5",
            dataset_id="single-levels",
            variables=["u10", "v10"],
            min_lat=24.0, max_lat=26.0, min_lon=53.0, max_lon=55.0,
            start_time_iso="2026-08-27T00:00:00Z",
            end_time_iso="2026-08-27T12:00:00Z",
        )
        key_peru = generate_cache_key(
            provider_name="era5",
            dataset_id="single-levels",
            variables=["u10", "v10"],
            min_lat=-13.0, max_lat=-11.0, min_lon=-78.0, max_lon=-76.0,
            start_time_iso="2026-08-27T00:00:00Z",
            end_time_iso="2026-08-27T12:00:00Z",
        )

        self.assertEqual(key_gulf, key_gulf_dup, "Identical query parameters must generate identical cache key")
        self.assertNotEqual(key_gulf, key_peru, "Distinct geographic scenes must have distinct cache keys")

    def test_cache_atomic_save_and_recovery(self):
        """Verify atomic_save writes valid files and handles interrupted/failed writes cleanly."""
        key = "test_atomic_key"

        def _valid_writer(tmp_path: str):
            shutil.copyfile(self.era5_nc, tmp_path)

        cached_path = self.cache_mgr.atomic_save("era5", key, _valid_writer)
        self.assertTrue(os.path.exists(cached_path))
        self.assertTrue(self.cache_mgr.has_valid_cache("era5", key))

        # Test broken writer: temp file removed on failure, destination untouched
        def _failing_writer(tmp_path: str):
            with open(tmp_path, "w") as f:
                f.write("corrupted non-netcdf")

        with self.assertRaises(Exception):
            self.cache_mgr.atomic_save("era5", "broken_key", _failing_writer)

        self.assertFalse(self.cache_mgr.has_valid_cache("era5", "broken_key"))

    # --------------------------------------------------------------------------
    # 5. Dynamic Domain + Real Providers Wiring
    # --------------------------------------------------------------------------

    def test_dynamic_domain_derivation_from_feature1_payload(self):
        """Verify dynamic domain derives bounding box and time windows directly from Feature 1."""
        slick = SlickDetectionInput(**self.f1_payload_gulf)
        obs_domain = SentinelObservationDomain.from_slick_input(slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain,
            buffer_distance_km=40.0,
            historical_horizon_hours=6.0,
            forecast_horizon_hours=24.0
        )

        self.assertAlmostEqual(obs_domain.centroid_lat, 25.0, delta=0.01)
        self.assertAlmostEqual(obs_domain.centroid_lon, 54.0, delta=0.01)
        self.assertEqual(query_domain.historical_start_time, datetime(2026, 8, 27, 0, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(query_domain.historical_end_time, datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc))

        # Providers can successfully fetch_grid for this query domain
        era5_provider = ERA5WindProvider(data_path=self.era5_nc)
        cop_provider = CopernicusCurrentsProvider(data_path=self.copernicus_nc)

        self.assertTrue(era5_provider.fetch_grid(query_domain))
        self.assertTrue(cop_provider.fetch_grid(query_domain))

    # --------------------------------------------------------------------------
    # 6. Backward Reconstruction with Real Providers
    # --------------------------------------------------------------------------

    def test_backward_origin_estimation_with_real_providers(self):
        """Verify OriginEstimator executes backward reconstruction using real ERA5 and Copernicus providers."""
        era5 = ERA5WindProvider(data_path=self.era5_nc)
        cop = CopernicusCurrentsProvider(data_path=self.copernicus_nc)
        settings = Feature2Settings(
            random_seed=42,
            backward=BackwardTracingConfig(
                max_backtrack_hours=6.0,
                candidate_time_step_hours=3.0,
                particles_per_slick=40,
                simulation_step_seconds=300
            )
        )
        origin_est = OriginEstimator(currents_provider=cop, wind_provider=era5, settings=settings)
        slick = SlickDetectionInput(**self.f1_payload_gulf)

        result = origin_est.estimate_origins(
            source=slick,
            observation_time=slick.observation_time,
            spill_id=slick.spill_id,
            max_backtrack_hours=6.0,
            candidate_interval_hours=3.0,
            dt_seconds=300.0,
            windage_fraction=0.03
        )

        self.assertGreater(len(result.candidates), 0, "OriginEstimator must produce real origin candidates")
        self.assertIsNotNone(result.best_candidate)
        self.assertIsNotNone(result.release_time_window)
        # Verify candidate location is in the vicinity of the Arabian Gulf
        self.assertAlmostEqual(result.best_candidate.latitude, 25.0, delta=1.0)
        self.assertAlmostEqual(result.best_candidate.longitude, 54.0, delta=1.0)

    # --------------------------------------------------------------------------
    # 7. Forward Slick Forecasting with Real Providers
    # --------------------------------------------------------------------------

    def test_forward_forecasting_with_real_providers(self):
        """Verify ForwardForecaster executes forward advection using real Copernicus and GFS providers."""
        cop_fc = CopernicusForecastCurrentsProvider(data_path=self.copernicus_nc)
        gfs_fc = GFSWindProvider(data_path=self.gfs_nc)
        settings = Feature2Settings(
            random_seed=42,
            forecast=ForecastConfig(
                forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
                particles_per_slick=40,
                forecast_ensemble_size=1,
                simulation_step_seconds=600
            )
        )
        engine_fwd = ForwardSimulationEngine(currents_provider=cop_fc, wind_provider=gfs_fc, settings=settings)
        forecaster = ForwardForecaster(simulation_engine=engine_fwd, settings=settings)

        slick = SlickDetectionInput(**self.f1_payload_gulf)
        forecast_result = forecaster.predict(slick=slick)

        self.assertIn("6h", forecast_result.forecast)
        self.assertIn("12h", forecast_result.forecast)
        self.assertIn("24h", forecast_result.forecast)
        self.assertIn("48h", forecast_result.forecast)

        # Verify predicted centroid drifts continuously forward from observed slick (25.0, 54.0)
        fc_48h = forecast_result.forecast["48h"]
        self.assertTrue(fc_48h.valid)
        self.assertGreater(fc_48h.predicted_centroid.latitude, 24.5)
        self.assertGreater(fc_48h.predicted_centroid.longitude, 53.5)

    # --------------------------------------------------------------------------
    # 8. Unauthenticated Remote Download Graceful Failure (No Fake Data)
    # --------------------------------------------------------------------------

    def test_unauthenticated_providers_raise_structured_error(self):
        """Verify providers without credentials raise EnvironmentalDataUnavailableError instead of fake data."""
        # Provider with non-existent data path and no credentials
        unconfigured_era5 = ERA5WindProvider(
            config=ERA5Config(data_path="/non/existent/era5.nc", api_key=None)
        )
        unconfigured_cop = CopernicusCurrentsProvider(
            config=CopernicusConfig(data_path="/non/existent/cop.nc", username=None, password=None)
        )

        with self.assertRaises(EnvironmentalDataUnavailableError):
            unconfigured_era5.get_wind(25.0, 54.0, datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc))

        with self.assertRaises(EnvironmentalDataUnavailableError):
            unconfigured_cop.get_current(25.0, 54.0, datetime(2026, 8, 27, 6, 0, 0, tzinfo=timezone.utc))

    # --------------------------------------------------------------------------
    # 9. Live Remote Smoke Tests (Opt-In with Credentials)
    # --------------------------------------------------------------------------

    @unittest.skipUnless(
        os.getenv("CMEMS_USERNAME") and os.getenv("CMEMS_PASSWORD"),
        "LIVE CMEMS credentials required via CMEMS_USERNAME / CMEMS_PASSWORD."
    )
    def test_live_copernicus_smoke(self):
        """Live smoke test for Copernicus Marine Data Store download (skipped by default)."""
        provider = CopernicusCurrentsProvider()
        window = EnvironmentalQueryWindow(
            min_lat=55.0,
            max_lat=55.5,
            min_lon=3.75,
            max_lon=4.25,
            start_time=datetime(2018, 8, 3, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2018, 8, 4, 12, 0, 0, tzinfo=timezone.utc),
        )
        success = provider.fetch_grid(window)
        self.assertTrue(success)

    @unittest.skipUnless(
        os.getenv("CDSAPI_KEY"),
        "LIVE CDS credentials required via CDSAPI_KEY."
    )
    def test_live_era5_smoke(self):
        """Live smoke test for CDS ERA5 download (skipped by default)."""
        provider = ERA5WindProvider()
        window = EnvironmentalQueryWindow(
            min_lat=55.0,
            max_lat=55.5,
            min_lon=3.75,
            max_lon=4.25,
            start_time=datetime(2018, 8, 3, 16, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2018, 8, 3, 18, 0, 0, tzinfo=timezone.utc),
        )
        success = provider.fetch_grid(window)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
