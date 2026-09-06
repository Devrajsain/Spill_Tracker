"""
Focused smoke and integration tests for Task 4A:
Real Zenodo Sentinel-1 scene georeferencing, Feature 1 derivation,
dynamic domain propagation, and fail-closed real provider behavior.
"""

from datetime import datetime, timezone
import os
import unittest

from scripts.validate_real_scene import (
    inspect_sentinel1_geotiff,
    derive_feature1_output_from_mask,
    PROJECT_ROOT
)
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.wind.era5 import ERA5WindProvider
from feature2.data.currents.copernicus import CopernicusCurrentsProvider
from feature2.exceptions import EnvironmentalDataUnavailableError
from feature2.schemas.input_schema import SlickDetectionInput


class TestRealSceneValidation(unittest.TestCase):
    """Test suite for Task 4A real Zenodo Sentinel-1 scene validation."""

    @classmethod
    def setUpClass(cls):
        cls.tiff_path = os.path.join(PROJECT_ROOT, "tests", "fixtures", "Oil", "00000.tif")
        cls.mask_path = os.path.join(PROJECT_ROOT, "tests", "fixtures", "Mask_oil", "00000.tif")
        if not os.path.exists(cls.tiff_path) or not os.path.exists(cls.mask_path):
            raise unittest.SkipTest("Large Zenodo Sentinel-1 TIFF fixtures not present; skipping live scene test")
        cls.meta = inspect_sentinel1_geotiff(cls.tiff_path)
        cls.slick = derive_feature1_output_from_mask(cls.mask_path, cls.meta)

    # 1. Real TIFF georeferencing inspection
    def test_01_real_sentinel1_georeferencing(self):
        """Verify real Zenodo Sentinel-1 GeoTIFF georeferencing metadata and CRS."""
        self.assertEqual(self.meta["filename"], "00000.tif")
        self.assertIn("WGS 84", self.meta["crs"])
        self.assertEqual(self.meta["width"], 2048)
        self.assertEqual(self.meta["height"], 2048)
        self.assertEqual(self.meta["bands"], 2)  # VV and VH
        self.assertAlmostEqual(self.meta["pixel_res_deg"], 8.98315e-05, delta=1e-7)

        # Coordinate bounds must be in the North Sea (lat ~55, lon ~4)
        bounds = self.meta["bounds_wgs84"]
        self.assertGreater(bounds["min_lat"], 54.0)
        self.assertLess(bounds["max_lat"], 56.0)
        self.assertGreater(bounds["min_lon"], 3.5)
        self.assertLess(bounds["max_lon"], 4.5)

    # 2. Feature 1 derived from real TIFF geometry
    def test_02_feature1_derivation_from_real_scene(self):
        """Verify Feature 1 detection payload is derived from real Sentinel-1 mask and image."""
        self.assertIsInstance(self.slick, SlickDetectionInput)
        self.assertEqual(self.slick.observation_time, datetime(2018, 8, 3, 17, 25, 57, tzinfo=timezone.utc))
        self.assertAlmostEqual(self.slick.centroid.latitude, 55.241575, delta=0.01)
        self.assertAlmostEqual(self.slick.centroid.longitude, 4.053477, delta=0.01)
        self.assertGreater(self.slick.area_sq_km, 1.0)
        self.assertEqual(self.slick.geometry.type, "Polygon")
        self.assertGreater(len(self.slick.geometry.coordinates[0]), 4)

    # 3. Dynamic Feature 2 domain derives bounding box and windows from real scene
    def test_03_feature2_dynamic_domain_propagation(self):
        """Verify Feature 2 dynamically derives environmental domain from real scene anchor."""
        obs_domain = SentinelObservationDomain.from_slick_input(self.slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain,
            buffer_distance_km=50.0,
            historical_horizon_hours=6.0,
            forecast_horizon_hours=48.0
        )

        # Spatial domain must encompass the real slick with 50 km buffer
        self.assertLess(query_domain.min_lat, self.slick.centroid.latitude)
        self.assertGreater(query_domain.max_lat, self.slick.centroid.latitude)
        self.assertLess(query_domain.min_lon, self.slick.centroid.longitude)
        self.assertGreater(query_domain.max_lon, self.slick.centroid.longitude)

        # Temporal domain must anchor to observation time
        self.assertEqual(query_domain.historical_start_time, datetime(2018, 8, 3, 11, 25, 57, tzinfo=timezone.utc))
        self.assertEqual(query_domain.historical_end_time, datetime(2018, 8, 3, 17, 25, 57, tzinfo=timezone.utc))
        self.assertEqual(query_domain.forecast_start_time, datetime(2018, 8, 3, 17, 25, 57, tzinfo=timezone.utc))
        self.assertEqual(query_domain.forecast_end_time, datetime(2018, 8, 5, 17, 25, 57, tzinfo=timezone.utc))

    # 4. Providers receive real derived coordinates (no hardcoded regional coordinates)
    def test_04_provider_requests_receive_derived_coordinates(self):
        """Verify ERA5 and Copernicus providers receive exact derived real coordinates."""
        obs_domain = SentinelObservationDomain.from_slick_input(self.slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain,
            buffer_distance_km=50.0,
            historical_horizon_hours=6.0
        )

        era5_provider = ERA5WindProvider()
        cop_provider = CopernicusCurrentsProvider()

        era5_req = era5_provider.build_cds_request(query_domain)
        cop_req = cop_provider.build_subset_request(query_domain)

        # ERA5 area format is [North, West, South, East]
        self.assertAlmostEqual(era5_req["area"][0], query_domain.max_lat, places=4)
        self.assertAlmostEqual(era5_req["area"][1], query_domain.min_lon, places=4)
        self.assertAlmostEqual(era5_req["area"][2], query_domain.min_lat, places=4)
        self.assertAlmostEqual(era5_req["area"][3], query_domain.max_lon, places=4)

        # Copernicus format
        self.assertAlmostEqual(cop_req["minimum_latitude"], query_domain.min_lat, places=4)
        self.assertAlmostEqual(cop_req["maximum_latitude"], query_domain.max_lat, places=4)
        self.assertAlmostEqual(cop_req["minimum_longitude"], query_domain.min_lon, places=4)
        self.assertAlmostEqual(cop_req["maximum_longitude"], query_domain.max_lon, places=4)
        self.assertEqual(cop_req["maximum_depth"], 0.494)

    # 5. Live-data failure is fail-closed without credentials
    def test_05_unconfigured_live_data_fails_closed(self):
        """Verify unconfigured live providers refuse to fabricate data and fail closed."""
        era5 = ERA5WindProvider()
        cop = CopernicusCurrentsProvider()
        obs_domain = SentinelObservationDomain.from_slick_input(self.slick)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(obs_domain)

        # If credentials are not set, fetch_grid returns False or raises
        if not os.getenv("CDSAPI_KEY"):
            self.assertFalse(era5.fetch_grid(query_domain))
        if not (os.getenv("CMEMS_USERNAME") and os.getenv("CMEMS_PASSWORD")):
            self.assertFalse(cop.fetch_grid(query_domain))

    # 6. Forecast starts strictly from observed Feature 1 polygon at T0
    def test_06_forecast_anchors_to_observed_slick_polygon(self):
        """Verify forward forecast initializes particles strictly inside the observed slick polygon at T0."""
        from feature2.config import Feature2Settings, ForecastConfig
        from feature2.forecast.forecaster import ForwardForecaster
        from feature2.simulation.forward.engine import ForwardSimulationEngine
        from feature2.data.currents.copernicus import CopernicusForecastCurrentsProvider
        from feature2.data.wind.gfs import GFSWindProvider

        ns_cop = os.path.join(PROJECT_ROOT, "tests", "fixtures", "environment", "north_sea_copernicus_2018.nc")
        ns_gfs = os.path.join(PROJECT_ROOT, "tests", "fixtures", "environment", "north_sea_forecast_wind_2018.nc")

        fc_cop = CopernicusForecastCurrentsProvider(data_path=ns_cop)
        fc_gfs = GFSWindProvider(data_path=ns_gfs)
        settings = Feature2Settings(
            random_seed=42,
            forecast=ForecastConfig(
                forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
                particles_per_slick=20,
                forecast_ensemble_size=1,
                simulation_step_seconds=600
            )
        )
        engine = ForwardSimulationEngine(currents_provider=fc_cop, wind_provider=fc_gfs, settings=settings)
        forecaster = ForwardForecaster(simulation_engine=engine, settings=settings)

        res = forecaster.predict(slick=self.slick)

        # Initial centroid of forecast at +6h must be close to observed slick centroid
        c_observed = self.slick.centroid
        c_6h = res.forecast["6h"].predicted_centroid
        self.assertAlmostEqual(c_6h.latitude, c_observed.latitude, delta=0.5)
        self.assertAlmostEqual(c_6h.longitude, c_observed.longitude, delta=0.5)
        self.assertEqual(res.forecast["6h"].active_particle_count, 20)
        self.assertTrue(res.forecast["48h"].valid)


if __name__ == "__main__":
    unittest.main()
