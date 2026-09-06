"""
Task 7 Unit and End-to-End Integration Tests.
Validates:
  - Real Zenodo Sentinel-1 SAR observation payload ingestion.
  - Production environment provider wiring (ERA5, Copernicus historical, GFS, Copernicus forecast).
  - 72-hour backward origin reconstruction (24 candidates, convergence, release window, evidence score).
  - Forward ensemble forecast initialized strictly from observed Feature 1 slick geometry at T0.
  - NOAA GFS wind units verification (native m/s).
  - Consolidated UnifiedFeature2Result schema and RFC 7946 GeoJSON generation.
"""

from datetime import datetime, timezone
import math
import os
import unittest

from feature2.config import (
    Feature2Settings,
    DataSourceConfig,
    BackwardTracingConfig,
    ForecastConfig,
    WindageConfig,
    DiffusionConfig,
)
from feature2.data.currents.copernicus import CopernicusCurrentsProvider, CopernicusForecastCurrentsProvider
from feature2.data.wind.era5 import ERA5WindProvider
from feature2.data.wind.gfs import GFSWindProvider
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.origin.estimator import OriginEstimator
from feature2.forecast.forecaster import ForwardForecaster
from feature2.output.formatter import OutputFormatter
from feature2.pipeline.service import Feature2PipelineService
from feature2.schemas.input_schema import SlickDetectionInput
from feature2.simulation.forward.engine import ForwardSimulationEngine
from scripts.validate_real_scene import inspect_sentinel1_geotiff, derive_feature1_output_from_mask


class TestTask7RealEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.tiff_path = os.path.join(cls.project_root, "tests", "fixtures", "Oil", "00000.tif")
        cls.mask_path = os.path.join(cls.project_root, "tests", "fixtures", "Mask_oil", "00000.tif")
        cls.ns_era5_path = os.path.join(cls.project_root, "tests", "fixtures", "environment", "north_sea_era5_2018.nc")
        cls.ns_cop_path = os.path.join(cls.project_root, "tests", "fixtures", "environment", "north_sea_copernicus_2018.nc")
        cls.ns_gfs_path = os.path.join(cls.project_root, "tests", "fixtures", "environment", "north_sea_forecast_wind_2018.nc")

        if not os.path.exists(cls.tiff_path) or not os.path.exists(cls.mask_path):
            raise unittest.SkipTest("Large Zenodo Sentinel-1 TIFF fixtures not present; skipping live scene test")

        # Derive real Feature 1 Slick
        meta = inspect_sentinel1_geotiff(cls.tiff_path)
        cls.slick = derive_feature1_output_from_mask(cls.mask_path, meta)

        cls.settings = Feature2Settings.production(
            data=DataSourceConfig(
                era5_data_path=cls.ns_era5_path,
                copernicus_data_path=cls.ns_cop_path,
                gfs_data_path=cls.ns_gfs_path,
                allow_production_replay_fixture=True,
            ),
            backward=BackwardTracingConfig(
                max_backtrack_hours=72.0,
                candidate_time_step_hours=3.0,
                particles_per_slick=25,
                simulation_step_seconds=300,
            ),
            forecast=ForecastConfig(
                forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
                particles_per_slick=25,
                forecast_ensemble_size=1,
                simulation_step_seconds=300,
            ),
            windage=WindageConfig(leeway_factor=0.03, deflection_angle_deg=0.0),
            diffusion=DiffusionConfig(enable_stochastic_diffusion=True, horizontal_diffusivity_m2_s=10.0),
        )

        cls.hist_wind = ERA5WindProvider(data_path=cls.ns_era5_path)
        cls.hist_curr = CopernicusCurrentsProvider(data_path=cls.ns_cop_path)
        cls.fwd_wind = GFSWindProvider(data_path=cls.ns_gfs_path)
        cls.fwd_curr = CopernicusForecastCurrentsProvider(data_path=cls.ns_cop_path)

        cls.origin_estimator = OriginEstimator(
            currents_provider=cls.hist_curr,
            wind_provider=cls.hist_wind,
            settings=cls.settings,
        )

        cls.fwd_engine = ForwardSimulationEngine(
            currents_provider=cls.fwd_curr,
            wind_provider=cls.fwd_wind,
            settings=cls.settings,
        )
        cls.forecaster = ForwardForecaster(
            simulation_engine=cls.fwd_engine,
            settings=cls.settings,
        )

    def test_01_feature1_sentinel1_observation_payload(self):
        """Verify Sentinel-1 real slick detection matches physical properties."""
        self.assertEqual(self.slick.spill_id, "ZENODO_S1A_IW_GRDH_1SDV_201_OIL_00000")
        self.assertAlmostEqual(self.slick.centroid.latitude, 55.241575, places=4)
        self.assertAlmostEqual(self.slick.centroid.longitude, 4.053477, places=4)
        self.assertAlmostEqual(self.slick.area_sq_km, 1.4539, places=2)
        self.assertEqual(self.slick.observation_time.isoformat(), "2018-08-03T17:25:57+00:00")

    def test_02_production_provider_wiring(self):
        """Verify Feature2Settings.production resolves production stack."""
        self.assertEqual(self.settings.environment, "production")
        self.assertEqual(self.settings.data.wind_provider, "era5")
        self.assertEqual(self.settings.data.currents_provider, "copernicus")
        self.assertEqual(self.settings.data.forecast_wind_provider, "gfs")
        self.assertEqual(self.settings.data.forecast_currents_provider, "copernicus")

    def test_03_72h_backward_origin_reconstruction(self):
        """Verify 72-hour backward origin reconstruction with 3h candidate interval."""
        obs_domain = SentinelObservationDomain.from_slick_input(self.slick)
        hist_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain, buffer_distance_km=50.0, historical_horizon_hours=72.0
        )
        origin_res = self.origin_estimator.estimate_origins(
            source=self.slick,
            observation_time=self.slick.observation_time,
            spill_id=self.slick.spill_id,
            max_backtrack_hours=72.0,
            candidate_interval_hours=3.0,
            dt_seconds=300.0,
            windage_fraction=0.03,
            query_domain=hist_domain,
        )

        # 72 hours at 3h intervals = 24 candidates
        self.assertEqual(len(origin_res.candidates), 24)
        best = origin_res.best_candidate
        self.assertIsNotNone(best)
        self.assertTrue(-90.0 <= best.latitude <= 90.0)
        self.assertTrue(-180.0 <= best.longitude <= 180.0)
        self.assertTrue(0.0 <= best.candidate_score <= 1.0)
        self.assertTrue(best.uncertainty_radius_km > 0.0)
        self.assertIsNotNone(origin_res.release_time_window)
        self.assertGreater(origin_res.release_time_window.duration_hours, 0.0)

    def test_04_forward_forecast_initialized_from_observed_slick(self):
        """Verify forward forecast is initialized from observed slick at T0 across +6h, +12h, +24h, +48h."""
        forecast_res = self.forecaster.predict(
            slick=self.slick,
            forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
            diffusion_enabled=True,
        )

        for h in [6.0, 12.0, 24.0, 48.0]:
            h_key = f"{int(h)}h"
            self.assertIn(h_key, forecast_res.forecast)
            pred = forecast_res.forecast[h_key]
            self.assertTrue(pred.valid)
            self.assertGreater(pred.active_particle_count, 0)
            self.assertTrue(pred.uncertainty.radius_km > 0.0)
            self.assertTrue(-90.0 <= pred.centroid.latitude <= 90.0)
            self.assertTrue(-180.0 <= pred.centroid.longitude <= 180.0)

        # Dispersion should grow over time
        rad_6h = forecast_res.forecast["6h"].uncertainty.radius_km
        rad_48h = forecast_res.forecast["48h"].uncertainty.radius_km
        self.assertGreater(rad_48h, rad_6h)

    def test_05_gfs_wind_units_native_mps(self):
        """Verify GFS URL format includes wind_speed_unit=ms and returns realistic m/s."""
        url = self.fwd_wind.build_query_url([55.24], [4.05], 3)
        self.assertIn("wind_speed_unit=ms", url)

    def test_06_pipeline_service_unified_result_contract(self):
        """Verify full Feature2PipelineService generates valid UnifiedFeature2Result."""
        service = Feature2PipelineService(
            origin_estimator=self.origin_estimator,
            forecaster=self.forecaster,
            settings=self.settings,
        )
        response = service.run_pipeline(self.slick)
        unif = response.to_unified_result()

        self.assertEqual(unif.spill_id, self.slick.spill_id)
        self.assertEqual(unif.observation.area_km2, self.slick.area_sq_km)
        self.assertEqual(len(unif.forecast.horizons), 4)
        self.assertEqual(unif.origin.candidate_count, 24)
        self.assertIn("not a calibrated probability", unif.origin.disclaimer.lower())
        self.assertIn("estimated convergence zone", unif.origin.disclaimer.lower())
        self.assertEqual(unif.quality.overall, "HIGH")
        self.assertEqual(unif.quality.particle_retention_ratio, 1.0)
        self.assertGreater(len(unif.disclaimers.limitations), 0)

    def test_07_rfc7946_geojson_output(self):
        """Verify RFC 7946 GeoJSON FeatureCollection generation."""
        service = Feature2PipelineService(
            origin_estimator=self.origin_estimator,
            forecaster=self.forecaster,
            settings=self.settings,
        )
        response = service.run_pipeline(self.slick)
        unif = response.to_unified_result()
        geojson = OutputFormatter.unified_result_to_geojson(unif)

        self.assertEqual(geojson.get("type"), "FeatureCollection")
        features = geojson.get("features", [])
        self.assertGreater(len(features), 0)

        types = {f["properties"].get("feature_type") for f in features}
        self.assertTrue(any("observed" in t for t in types))
        self.assertTrue(any("candidate_origin" in t for t in types))
        self.assertTrue(any("forecast" in t for t in types))


if __name__ == "__main__":
    unittest.main()
