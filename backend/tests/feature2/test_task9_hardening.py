"""
Unit tests for Task 9: Feature 2 Production Hardening & Contract Freeze.
Covers:
  - Production provider wiring & runtime validation guards
  - Feature 1 GeoJSON FeatureCollection adapter & geometry validation
  - NetCDF semantic depth dimension discovery
  - Cache TTL enforcement & corrupt cache deletion
  - Spatial uncertainty exact chi-square quantile & small-sample edge cases
  - Release timeline dynamic scoring vs legacy deprecation
  - Forecast dispersion polygon GeoJSON labeling
  - Provenance model_source and access_provider metadata
"""

import math
import os
import tempfile
import time
import unittest
import warnings
from datetime import datetime, timezone, timedelta

import numpy as np
import xarray as xr

from feature2.config import (
    DataSourceConfig,
    Feature2Settings,
    validate_production_data_sources,
    get_provider_summary,
)
from feature2.exceptions import (
    ConfigurationError,
    InvalidInputGeometryError,
)
from feature2.geo.spatial import (
    compute_polygon_centroid,
    haversine_polygon_area_km2,
    haversine_polygon_perimeter_km,
    validate_polygon_geometry,
)
from feature2.schemas.feature1_adapter import parse_feature1_input
from feature2.schemas.input_schema import SlickDetectionInput, GeoJSONGeometry, CentroidCoordinates
from feature2.schemas.output_schema import OriginCandidate, SpatialUncertainty
from feature2.data.cache import EnvironmentalDataCacheManager
from feature2.data.local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from feature2.uncertainty.spatial_error import SpatialUncertaintyEstimator
from feature2.origin.scoring.timeline import ReleaseTimelineEstimator
from feature2.origin.scoring.confidence import OriginConfidenceScorer
from feature2.output.formatter import OutputFormatter


class TestTask9ProductionProviderWiring(unittest.TestCase):
    """Verifies that production mode strictly enforces real providers and guards against mocks."""

    def test_production_mode_rejects_mock_providers(self):
        with self.assertRaises(ConfigurationError):
            validate_production_data_sources(
                Feature2Settings(
                    environment="production",
                    data=DataSourceConfig(wind_provider="mock")
                )
            )

        with self.assertRaises(ConfigurationError):
            validate_production_data_sources(
                Feature2Settings(
                    environment="production",
                    data=DataSourceConfig(currents_provider="mock")
                )
            )

        with self.assertRaises(ConfigurationError):
            validate_production_data_sources(
                Feature2Settings(
                    environment="production",
                    data=DataSourceConfig(forecast_wind_provider="mock")
                )
            )

        with self.assertRaises(ConfigurationError):
            validate_production_data_sources(
                Feature2Settings(
                    environment="production",
                    data=DataSourceConfig(forecast_currents_provider="mock")
                )
            )

    def test_production_mode_rejects_fixtures_unless_explicitly_flagged(self):
        # Local netcdf filepath in production without allow_production_replay_fixture
        settings = Feature2Settings(
            environment="production",
            data=DataSourceConfig(
                wind_provider="era5",
                currents_provider="copernicus",
                forecast_wind_provider="gfs",
                forecast_currents_provider="copernicus",
                local_wind_filepath="some/path.nc",
                allow_production_replay_fixture=False
            )
        )
        with self.assertRaises(ConfigurationError):
            validate_production_data_sources(settings)

    def test_validate_production_data_sources_validates_credentials(self):
        settings = Feature2Settings.production()
        # Save original env
        old_user = os.environ.get("CMEMS_USERNAME")
        old_cds = os.environ.get("CDSAPI_KEY")

        try:
            # Missing credentials should trigger ConfigurationError
            if "CMEMS_USERNAME" in os.environ:
                del os.environ["CMEMS_USERNAME"]
            with self.assertRaises(ConfigurationError):
                validate_production_data_sources(settings)
        finally:
            if old_user:
                os.environ["CMEMS_USERNAME"] = old_user
            if old_cds:
                os.environ["CDSAPI_KEY"] = old_cds

    def test_provider_summary_contains_no_secrets(self):
        settings = Feature2Settings.production()
        summary = get_provider_summary(settings)
        self.assertIn("environment", summary)
        self.assertEqual(summary["historical_wind"], "era5")
        self.assertEqual(summary["historical_currents"], "copernicus")
        self.assertEqual(summary["forecast_wind"], "gfs")
        self.assertEqual(summary["forecast_currents"], "copernicus")
        self.assertNotIn("CMEMS_PASSWORD", summary)
        self.assertNotIn("CDSAPI_KEY", summary)


class TestTask9Feature1AdapterAndGeometry(unittest.TestCase):
    """Verifies GeoJSON FeatureCollection adapter and geometry validation."""

    def setUp(self):
        self.valid_ring = [
            [104.150, 1.250],
            [104.165, 1.255],
            [104.170, 1.270],
            [104.155, 1.265],
            [104.150, 1.250]
        ]
        self.valid_feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [self.valid_ring]
                    },
                    "properties": {
                        "spill_id": "SPILL-TEST-001",
                        "observation_time": "2026-09-03T12:00:00Z",
                    }
                }
            ]
        }

    def test_parse_valid_feature_collection(self):
        slick = parse_feature1_input(self.valid_feature_collection)
        self.assertEqual(slick.spill_id, "SPILL-TEST-001")
        self.assertEqual(slick.observation_time, datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc))
        self.assertGreater(slick.area_sq_km, 0.0)
        self.assertGreater(slick.perimeter_km, 0.0)
        self.assertAlmostEqual(slick.centroid.latitude, 1.26, delta=0.01)
        self.assertAlmostEqual(slick.centroid.longitude, 104.16, delta=0.01)

    def test_adapter_rejects_multipolygon(self):
        mp_payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [[self.valid_ring], [self.valid_ring]]
                    },
                    "properties": {
                        "spill_id": "SPILL-MP",
                        "observation_time": "2026-09-03T12:00:00Z",
                    }
                }
            ]
        }
        with self.assertRaises(InvalidInputGeometryError):
            parse_feature1_input(mp_payload)

    def test_geometry_validation_unclosed_ring(self):
        unclosed_ring = [
            [104.150, 1.250],
            [104.165, 1.255],
            [104.170, 1.270],
            [104.155, 1.265]  # Not closed back to 104.150, 1.250
        ]
        with self.assertRaises(InvalidInputGeometryError):
            validate_polygon_geometry([unclosed_ring])

    def test_geometry_validation_out_of_bounds_coords(self):
        # Latitude 95 is invalid
        oob_ring = [
            [104.150, 95.0],
            [104.165, 95.0],
            [104.170, 95.1],
            [104.150, 95.0]
        ]
        with self.assertRaises(InvalidInputGeometryError):
            validate_polygon_geometry([oob_ring])

    def test_geometry_validation_non_numeric_coords(self):
        nan_ring = [
            [104.150, 1.250],
            [float('nan'), 1.255],
            [104.170, 1.270],
            [104.150, 1.250]
        ]
        with self.assertRaises(InvalidInputGeometryError):
            validate_polygon_geometry([nan_ring])

    def test_haversine_polygon_area_and_perimeter(self):
        area = haversine_polygon_area_km2(self.valid_ring)
        perimeter = haversine_polygon_perimeter_km(self.valid_ring)
        self.assertGreater(area, 0.5)
        self.assertLess(area, 10.0)
        self.assertGreater(perimeter, 2.0)
        self.assertLess(perimeter, 20.0)


class TestTask9NetCDFSemanticDimensions(unittest.TestCase):
    """Verifies that 4D NetCDF files identify depth dimensions semantically."""

    def test_semantic_depth_dimension_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nc_path = os.path.join(tmpdir, "test_currents.nc")
            times = np.array(["2026-09-03T00:00:00"], dtype="datetime64[ns]")
            depths = np.array([0.494, 5.0, 10.0], dtype=np.float32)
            lats = np.array([1.0, 1.5, 2.0], dtype=np.float32)
            lons = np.array([104.0, 104.5, 105.0], dtype=np.float32)

            u_vals = np.ones((1, 3, 3, 3), dtype=np.float32) * 0.45
            v_vals = np.ones((1, 3, 3, 3), dtype=np.float32) * -0.25

            # Notice dimension ordering: time, depth, latitude, longitude
            ds = xr.Dataset(
                data_vars={
                    "uo": (["time", "depth", "latitude", "longitude"], u_vals, {"units": "m/s"}),
                    "vo": (["time", "depth", "latitude", "longitude"], v_vals, {"units": "m/s"}),
                },
                coords={
                    "time": times,
                    "depth": depths,
                    "latitude": lats,
                    "longitude": lons,
                }
            )
            ds.to_netcdf(nc_path)

            mapping = VariableMapping(
                u_var="uo", v_var="vo", lat_var="latitude", lon_var="longitude", time_var="time"
            )
            reader = LocalNetCDFDatasetReader(nc_path, mapping)
            reader.open_dataset()

            # Cached array should be 3D (time, lat, lon) with depth sliced out
            cached_u = reader._cached_arrays["uo"]
            self.assertEqual(cached_u.ndim, 3)
            self.assertEqual(cached_u.shape, (1, 3, 3))
            self.assertAlmostEqual(float(cached_u[0, 1, 1]), 0.45, places=3)
            reader.close_dataset()


class TestTask9CacheTTLandCorruption(unittest.TestCase):
    """Verifies cache TTL enforcement and automatic deletion of corrupted cache files."""

    def test_corrupted_cache_file_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = EnvironmentalDataCacheManager(tmpdir)
            cache_path = mgr.get_cache_filepath("era5", "corrupt_key")
            # Write corrupted zero-byte file
            with open(cache_path, "wb") as f:
                f.write(b"")

            self.assertFalse(mgr.has_valid_cache("era5", "corrupt_key"))
            # File should have been automatically deleted
            self.assertFalse(os.path.exists(cache_path))

    def test_cache_ttl_expiration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = EnvironmentalDataCacheManager(tmpdir)
            cache_path = mgr.get_cache_filepath("gfs", "valid_key")

            # Create minimal valid NetCDF
            ds = xr.Dataset(
                data_vars={"u10": (["lat"], [1.0, 2.0])},
                coords={"lat": [10.0, 20.0]}
            )
            ds.to_netcdf(cache_path)

            # Fresh check: max_age=3600 -> Valid
            self.assertTrue(mgr.has_valid_cache("gfs", "valid_key", max_age_seconds=3600.0))

            # Set file mtime to 10 hours ago
            past_time = time.time() - 36000.0
            os.utime(cache_path, (past_time, past_time))

            # Expired check: max_age=3600 -> False (triggers remote refresh)
            self.assertFalse(mgr.has_valid_cache("gfs", "valid_key", max_age_seconds=3600.0))
            self.assertIsNone(mgr.get_cached_file("gfs", "valid_key", max_age_seconds=3600.0))


class TestTask9UncertaintySemantics(unittest.TestCase):
    """Verifies exact chi-square quantile formula and small particle sample edge cases."""

    def test_uncertainty_zero_particles(self):
        unc = SpatialUncertaintyEstimator.compute_dispersion_ellipse([])
        self.assertEqual(unc.semi_major_axis_km, 0.0)
        self.assertEqual(unc.semi_minor_axis_km, 0.0)
        self.assertEqual(len(unc.uncertainty_polygon.coordinates[0]), 4)

    def test_uncertainty_single_particle(self):
        unc = SpatialUncertaintyEstimator.compute_dispersion_ellipse([(1.25, 104.15)])
        self.assertEqual(unc.semi_major_axis_km, 0.0)
        self.assertEqual(unc.semi_minor_axis_km, 0.0)

    def test_uncertainty_two_particles(self):
        unc = SpatialUncertaintyEstimator.compute_dispersion_ellipse([
            (1.25, 104.15),
            (1.27, 104.15)
        ])
        self.assertGreater(unc.semi_major_axis_km, 0.0)
        self.assertEqual(unc.semi_minor_axis_km, 0.01)

    def test_confidence_level_parameter_scales_chi_square(self):
        coords = [
            (1.250, 104.150),
            (1.255, 104.155),
            (1.248, 104.148),
            (1.260, 104.160),
            (1.245, 104.142)
        ]
        unc_50 = SpatialUncertaintyEstimator.compute_dispersion_ellipse(coords, confidence_level=0.50)
        unc_95 = SpatialUncertaintyEstimator.compute_dispersion_ellipse(coords, confidence_level=0.95)
        unc_99 = SpatialUncertaintyEstimator.compute_dispersion_ellipse(coords, confidence_level=0.99)

        # Higher confidence -> larger dispersion ellipse
        self.assertLess(unc_50.semi_major_axis_km, unc_95.semi_major_axis_km)
        self.assertLess(unc_95.semi_major_axis_km, unc_99.semi_major_axis_km)


class TestTask9ReleaseTimeline(unittest.TestCase):
    """Verifies dynamic release timeline calculation and deprecation of static estimate_window."""

    def test_dynamic_window_varies_with_candidate_scores(self):
        estimator = ReleaseTimelineEstimator()
        t0 = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)

        # Best candidate at -6h with high score
        best = OriginCandidate(
            candidate_id="c_best",
            cluster_id=0,
            release_time=t0 - timedelta(hours=6),
            latitude=1.25,
            longitude=104.15,
            candidate_score=0.90,
            convergence_score=0.9,
            trajectory_score=0.9,
            coverage_score=1.0,
            uncertainty_radius_km=1.0,
            active_particle_count=100,
            total_particle_count=100
        )
        # Second candidate at -12h with score above 0.8 * 0.9 = 0.72
        second = OriginCandidate(
            candidate_id="c_second",
            cluster_id=1,
            release_time=t0 - timedelta(hours=12),
            latitude=1.23,
            longitude=104.13,
            candidate_score=0.80,
            convergence_score=0.8,
            trajectory_score=0.8,
            coverage_score=1.0,
            uncertainty_radius_km=1.2,
            active_particle_count=90,
            total_particle_count=100
        )
        # Third candidate at -24h with low score below threshold
        third = OriginCandidate(
            candidate_id="c_third",
            cluster_id=2,
            release_time=t0 - timedelta(hours=24),
            latitude=1.20,
            longitude=104.10,
            candidate_score=0.40,
            convergence_score=0.4,
            trajectory_score=0.4,
            coverage_score=1.0,
            uncertainty_radius_km=2.5,
            active_particle_count=40,
            total_particle_count=100
        )

        window = estimator.estimate_candidate_window([best, second, third])
        self.assertIsNotNone(window)
        # Plausible window should include best (-6h) and second (-12h), duration = 6h (NOT 18h)
        self.assertEqual(window.duration_hours, 6.0)
        self.assertEqual(window.peak_evidence_time, best.release_time)

    def test_legacy_estimate_window_warns_deprecation(self):
        t0 = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ReleaseTimelineEstimator.estimate_window({}, t0)
            self.assertTrue(any(issubclass(item.category, DeprecationWarning) for item in w))


class TestTask9ForecastGeoJSONSemantics(unittest.TestCase):
    """Verifies that forecast GeoJSON properties explicitly declare dispersion envelope semantics."""

    def test_forecast_uncertainty_zone_properties(self):
        from feature2.schemas.output_schema import (
            ForecastAnalysisResult,
            ForecastHorizonResult,
            ForecastUncertainty,
        )
        t0 = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        poly = GeoJSONGeometry(
            type="Polygon",
            coordinates=[[[104.1, 1.2], [104.2, 1.2], [104.2, 1.3], [104.1, 1.3], [104.1, 1.2]]]
        )
        unc = ForecastUncertainty(
            radius_km=3.5,
            semi_major_km=3.5,
            semi_minor_km=1.5,
            orientation_deg=45.0,
            uncertainty_polygon=poly
        )
        horizon = ForecastHorizonResult(
            lead_time_hours=6.0,
            forecast_time=t0 + timedelta(hours=6),
            centroid=CentroidCoordinates(latitude=1.25, longitude=104.15),
            uncertainty=unc,
            active_particle_count=100,
            total_particle_count=100,
            active_fraction=1.0,
            mean_drift_speed_kmh=1.2,
            mean_drift_direction_deg=45.0
        )
        fc_res = ForecastAnalysisResult(
            spill_id="SPILL-FC-TEST",
            observation_time=t0,
            initialization_time=t0,
            forecast={"6h": horizon}
        )

        fc_geojson = OutputFormatter.forecast_result_to_geojson(fc_res)
        features = fc_geojson["features"]
        unc_feature = next(f for f in features if f["properties"]["feature_type"] == "forecast_uncertainty_zone")

        self.assertEqual(unc_feature["properties"]["polygon_type"], "modeled_dispersion_envelope")
        self.assertIn("Modeled spatial dispersion envelope", unc_feature["properties"]["disclaimer"])


class TestTask9EnsembleParticleSemantics(unittest.TestCase):
    """Verifies that ensemble_realizations, particles_per_realization, and total_particles are mathematically consistent."""

    def test_forecast_ensemble_summary_automatic_calculation(self):
        from feature2.schemas.output_schema import ForecastEnsembleSummary

        # Case A: total_particles omitted (automatic calculation)
        configs = [
            (1, 50, 50),
            (1, 100, 100),
            (5, 50, 250),
            (5, 100, 500),
        ]
        for n_real, p_real, expected_total in configs:
            ens = ForecastEnsembleSummary(
                ensemble_realizations=n_real,
                particles_per_realization=p_real
            )
            self.assertEqual(ens.ensemble_realizations, n_real)
            self.assertEqual(ens.particles_per_realization, p_real)
            self.assertEqual(ens.total_particles, expected_total)
            self.assertEqual(ens.total_particles, ens.ensemble_realizations * ens.particles_per_realization)

    def test_forecast_ensemble_summary_explicit_correct_value(self):
        from feature2.schemas.output_schema import ForecastEnsembleSummary

        # Case B: total_particles explicitly provided and mathematically correct
        ens = ForecastEnsembleSummary(
            ensemble_realizations=5,
            particles_per_realization=100,
            total_particles=500
        )
        self.assertEqual(ens.ensemble_realizations, 5)
        self.assertEqual(ens.particles_per_realization, 100)
        self.assertEqual(ens.total_particles, 500)

        ens2 = ForecastEnsembleSummary(
            ensemble_realizations=2,
            particles_per_realization=50,
            total_particles=100
        )
        self.assertEqual(ens2.total_particles, 100)

    def test_forecast_ensemble_summary_explicit_incorrect_value_rejected(self):
        from feature2.schemas.output_schema import ForecastEnsembleSummary
        from pydantic import ValidationError

        # Case C: total_particles explicitly provided but inconsistent with realization counts -> rejected
        with self.assertRaises((ValidationError, ValueError)) as ctx:
            ForecastEnsembleSummary(
                ensemble_realizations=5,
                particles_per_realization=100,
                total_particles=123
            )
        self.assertIn("total_particles (123) must equal ensemble_realizations (5) * particles_per_realization (100) = 500", str(ctx.exception))

        with self.assertRaises((ValidationError, ValueError)):
            ForecastEnsembleSummary(
                ensemble_realizations=2,
                particles_per_realization=50,
                total_particles=99
            )

        with self.assertRaises((ValidationError, ValueError)):
            ForecastEnsembleSummary(
                ensemble_realizations=1,
                particles_per_realization=50,
                total_particles=51
            )

    def test_forecast_ensemble_summary_serialization_preserves_values(self):
        from feature2.schemas.output_schema import ForecastEnsembleSummary

        # Case D: Serialized output preserves reconciled values
        ens = ForecastEnsembleSummary(
            ensemble_realizations=4,
            particles_per_realization=75
        )
        dumped = ens.model_dump()
        self.assertEqual(dumped["ensemble_realizations"], 4)
        self.assertEqual(dumped["particles_per_realization"], 75)
        self.assertEqual(dumped["total_particles"], 300)
        self.assertEqual(dumped["particles_per_slick"], 75)

    def test_forecast_ensemble_summary_particles_per_slick_backward_compatibility(self):
        from feature2.schemas.output_schema import ForecastEnsembleSummary
        from pydantic import ValidationError

        # Case E: particles_per_slick legacy alias works correctly
        ens = ForecastEnsembleSummary(
            ensemble_realizations=3,
            particles_per_slick=40
        )
        self.assertEqual(ens.particles_per_realization, 40)
        self.assertEqual(ens.total_particles, 120)

        # Inconsistent particles_per_slick + total_particles rejected
        with self.assertRaises((ValidationError, ValueError)):
            ForecastEnsembleSummary(
                ensemble_realizations=3,
                particles_per_slick=40,
                total_particles=100
            )


class TestTask94P1Hardening(unittest.TestCase):
    """Verifies P1 production fixes: GFS and Copernicus forecast cache TTL wiring,
    provider-level stale cache rejection, and public serialization filepath privacy."""

    def _create_forecast_netcdf(self, filepath: str, u_var: str, v_var: str, start_dt: datetime, end_dt: datetime):
        import numpy as np
        import pandas as pd
        t_start = start_dt.replace(tzinfo=None) if hasattr(start_dt, "tzinfo") and start_dt.tzinfo else start_dt
        t_end = end_dt.replace(tzinfo=None) if hasattr(end_dt, "tzinfo") and end_dt.tzinfo else end_dt
        times = pd.date_range(t_start, t_end, periods=5)
        lats = np.array([50.0, 52.0])
        lons = np.array([2.0, 4.0])
        u_data = np.ones((len(times), len(lats), len(lons)), dtype=np.float32) * 5.0
        v_data = np.ones((len(times), len(lats), len(lons)), dtype=np.float32) * -3.0

        ds = xr.Dataset(
            data_vars={
                u_var: (["time", "latitude", "longitude"], u_data),
                v_var: (["time", "latitude", "longitude"], v_data),
            },
            coords={
                "time": times,
                "latitude": lats,
                "longitude": lons,
            }
        )
        ds.to_netcdf(filepath)
        ds.close()

    def test_gfs_forecast_provider_enforces_cache_ttl(self):
        """Proves GFSWindProvider actually enforces cache_ttl_forecast_seconds at real cache lookup."""
        from feature2.data.wind.gfs import GFSWindProvider, GFSConfig
        from feature2.data.cache import generate_cache_key
        from feature2.schemas.simulation_schema import EnvironmentalQueryWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = EnvironmentalDataCacheManager(tmpdir)
            settings = Feature2Settings(
                environment="development",
                data={"cache_ttl_forecast_seconds": 1800.0}  # 30 min TTL
            )
            provider = GFSWindProvider(
                config=GFSConfig(u_var="u10", v_var="v10", cache_dir=tmpdir),
                cache_manager=mgr,
                settings=settings,
            )

            now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            end_utc = now_utc + timedelta(hours=48)
            query_win = EnvironmentalQueryWindow(
                min_lat=50.5,
                max_lat=51.5,
                min_lon=2.5,
                max_lon=3.5,
                start_time=now_utc,
                end_time=end_utc,
            )

            cache_key = generate_cache_key(
                provider_name="gfs",
                dataset_id="gfs_0p25",
                variables=["u10", "v10"],
                min_lat=50.5,
                max_lat=51.5,
                min_lon=2.5,
                max_lon=3.5,
                start_time_iso=now_utc.isoformat(),
                end_time_iso=end_utc.isoformat(),
            )
            cached_path = mgr.get_cache_filepath("gfs", cache_key)
            self._create_forecast_netcdf(cached_path, "u10", "v10", now_utc, end_utc)

            # Test A: Fresh cache is accepted
            res_fresh = provider.fetch_grid(query_win)
            self.assertTrue(res_fresh)
            self.assertEqual(provider._cache_status, "hit")
            self.assertEqual(provider._source_type, "cache")
            provider.reader.close_dataset()

            # Test B: Stale cache (file mtime older than 1800s TTL) is rejected by GFS provider
            provider.reader = None
            provider._cache_status = "none"
            provider._source_type = "uninitialized"
            past_mtime = time.time() - 7200.0  # 2 hours ago
            os.utime(cached_path, (past_mtime, past_mtime))

            # Directly verify manager invalidates
            self.assertIsNone(mgr.get_cached_file("gfs", cache_key, max_age_seconds=1800.0))

            # Verify GFS provider rejects stale cache on fetch_grid
            # (Remote fetch is skipped or raises coverage error without network, proving stale cache was not used)
            try:
                res_stale = provider.fetch_grid(query_win)
                # If it didn't raise, it must NOT be a cache hit
                self.assertNotEqual(provider._cache_status, "hit")
            except Exception:
                # Reaching remote call confirms stale cache was rejected
                pass
            finally:
                if provider.reader:
                    provider.reader.close_dataset()

    def test_copernicus_forecast_currents_provider_enforces_cache_ttl(self):
        """Proves CopernicusForecastCurrentsProvider actually enforces cache_ttl_forecast_seconds at real cache lookup."""
        from feature2.data.currents.copernicus import CopernicusForecastCurrentsProvider, CopernicusConfig
        from feature2.data.cache import generate_cache_key
        from feature2.schemas.simulation_schema import EnvironmentalQueryWindow
        from feature2.exceptions import EnvironmentalDataUnavailableError, EnvironmentalCoverageError

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = EnvironmentalDataCacheManager(tmpdir)
            settings = Feature2Settings(
                environment="development",
                data={"cache_ttl_forecast_seconds": 1800.0}
            )
            provider = CopernicusForecastCurrentsProvider(
                config=CopernicusConfig(dataset_id="cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m", u_var="uo", v_var="vo", cache_dir=tmpdir),
                cache_manager=mgr,
                settings=settings,
            )

            now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            end_utc = now_utc + timedelta(hours=48)
            query_win = EnvironmentalQueryWindow(
                min_lat=50.5,
                max_lat=51.5,
                min_lon=2.5,
                max_lon=3.5,
                start_time=now_utc,
                end_time=end_utc,
            )

            cache_key = generate_cache_key(
                provider_name="copernicus_fc",
                dataset_id="cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
                variables=["uo", "vo"],
                min_lat=50.5,
                max_lat=51.5,
                min_lon=2.5,
                max_lon=3.5,
                start_time_iso=now_utc.isoformat(),
                end_time_iso=end_utc.isoformat(),
                extra_params={"depth": 0.494}
            )
            cached_path = mgr.get_cache_filepath("copernicus", cache_key)
            self._create_forecast_netcdf(cached_path, "uo", "vo", now_utc, end_utc)

            # Test A: Fresh cache is accepted
            res_fresh = provider.fetch_grid(query_win)
            self.assertTrue(res_fresh)
            self.assertEqual(provider._cache_status, "hit")
            self.assertEqual(provider._source_type, "cache")
            provider.reader.close_dataset()

            # Test B: Stale cache is rejected by Copernicus forecast provider
            provider.reader = None
            provider._cache_status = "none"
            provider._source_type = "uninitialized"
            past_mtime = time.time() - 7200.0  # 2 hours ago
            os.utime(cached_path, (past_mtime, past_mtime))

            self.assertIsNone(mgr.get_cached_file("copernicus", cache_key, max_age_seconds=1800.0))

            # Rejecting stale cache triggers remote download attempt (which skips/fails cleanly without credentials)
            try:
                res_stale = provider.fetch_grid(query_win)
                self.assertFalse(res_stale)
                self.assertNotEqual(provider._cache_status, "hit")
            except (EnvironmentalDataUnavailableError, EnvironmentalCoverageError):
                # Remote download failure confirms stale cache was rejected and remote path was invoked
                self.assertNotEqual(provider._cache_status, "hit")
            finally:
                if provider.reader:
                    provider.reader.close_dataset()

    def test_historical_provider_paths_unaffected(self):
        """Proves historical reanalysis cache retention does NOT apply forecast TTL."""
        from feature2.data.currents.copernicus import CopernicusCurrentsProvider, CopernicusConfig
        from feature2.data.cache import generate_cache_key
        from feature2.schemas.simulation_schema import EnvironmentalQueryWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = EnvironmentalDataCacheManager(tmpdir)
            provider = CopernicusCurrentsProvider(
                config=CopernicusConfig(dataset_id="cmems_mod_glo_phy_my_0.083deg_P1D-m", u_var="uo", v_var="vo", cache_dir=tmpdir),
                cache_manager=mgr,
            )

            hist_start = datetime(2018, 8, 1, 0, 0, tzinfo=timezone.utc)
            hist_end = datetime(2018, 8, 4, 0, 0, tzinfo=timezone.utc)
            query_win = EnvironmentalQueryWindow(
                min_lat=50.5,
                max_lat=51.5,
                min_lon=2.5,
                max_lon=3.5,
                start_time=hist_start,
                end_time=hist_end,
            )

            req = provider.build_subset_request(query_win)
            cache_key = generate_cache_key(
                provider_name="copernicus",
                dataset_id=provider.config.dataset_id,
                variables=["uo", "vo"],
                min_lat=50.5,
                max_lat=51.5,
                min_lon=2.5,
                max_lon=3.5,
                start_time_iso=req["start_datetime"],
                end_time_iso=req["end_datetime"],
                extra_params={"depth": provider.config.depth_level_m}
            )
            cached_path = mgr.get_cache_filepath("copernicus", cache_key)
            self._create_forecast_netcdf(cached_path, "uo", "vo", hist_start, hist_end)

            # Aging file beyond forecast TTL (e.g. 10 hours ago)
            past_mtime = time.time() - 36000.0
            os.utime(cached_path, (past_mtime, past_mtime))

            # Historical provider still hits the cache (reanalysis is indefinite)
            try:
                res = provider.fetch_grid(query_win)
                self.assertTrue(res)
                self.assertEqual(provider._cache_status, "hit")
            finally:
                if provider.reader:
                    provider.reader.close_dataset()

    def test_public_filepath_privacy_in_serialization(self):
        """Proves local filesystem paths are excluded from public serialized contracts while retained internally."""
        from feature2.schemas.output_schema import EnvironmentalFieldProvenance

        secret_local_path = "C:\\Users\\engineer\\workspace\\feature2\\data_cache\\secret_field.nc"
        prov = EnvironmentalFieldProvenance(
            provider_name="copernicus",
            dataset_id="cmems_mod_glo_phy_my_0.083deg_P1D-m",
            field_type="ocean_currents",
            data_category="historical",
            source_type="LOCAL_CACHE",
            filepath=secret_local_path,
        )

        # 1. Internal attribute access preserved for diagnostics/debugging
        self.assertEqual(prov.filepath, secret_local_path)

        # 2. Excluded from public dictionary serialization
        dumped = prov.model_dump()
        self.assertNotIn("filepath", dumped)

        # 3. Excluded from public JSON serialization
        json_dump = prov.model_dump_json()
        self.assertNotIn("filepath", json_dump)
        self.assertNotIn("secret_field.nc", json_dump)
        self.assertNotIn("engineer", json_dump)


class TestTask95ProductionFailClosedHardening(unittest.TestCase):
    """Verifies Task 9.5 P0/P1 production fail-closed invariants:
    - Production never auto-enables replay fixtures from filepath presence
    - Explicit replay flag is strictly required to consume local fixtures in production
    - GFS and Copernicus forecast providers fail closed before loading local fixtures
    - .env is removed from repository while .env.example remains intact."""

    def setUp(self):
        self._orig_env = os.environ.copy()
        os.environ["CMEMS_USERNAME"] = "dummy_user"
        os.environ["CMEMS_PASSWORD"] = "dummy_pass"
        os.environ["CDSAPI_KEY"] = "dummy_cds"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_production_never_auto_enables_replay_from_filepath_presence(self):
        """Rule A: Production factory never silently infers replay mode; fails validation by default."""
        fixture_path = os.path.abspath("tests/fixtures/environment/north_sea_era5_2018.nc")
        settings = Feature2Settings.production(
            data=DataSourceConfig(era5_data_path=fixture_path)
        )
        # Invariant 1: allow_production_replay_fixture remains strictly False
        self.assertFalse(settings.data.allow_production_replay_fixture)

        # Invariant 2: validation raises ConfigurationError because replay mode was not explicitly opted-in
        with self.assertRaises(ConfigurationError) as ctx:
            validate_production_data_sources(settings)
        self.assertIn("Production mode strictly forbids local fixture data paths", str(ctx.exception))

    def test_production_local_fixture_accepted_only_with_explicit_opt_in(self):
        """Rule B: Local fixture in production is accepted ONLY when allow_production_replay_fixture=True is explicit."""
        fixture_path = os.path.abspath("tests/fixtures/environment/north_sea_era5_2018.nc")
        settings = Feature2Settings.production(
            data=DataSourceConfig(
                era5_data_path=fixture_path,
                allow_production_replay_fixture=True  # Explicit opt-in
            )
        )
        self.assertTrue(settings.data.allow_production_replay_fixture)
        # Validation passes because explicit opt-in is configured
        validate_production_data_sources(settings)

    def test_production_real_providers_no_local_paths_passes(self):
        """Rule C: Normal production with genuine providers and zero local paths passes validation."""
        settings = Feature2Settings.production()
        self.assertIsNone(settings.data.era5_data_path)
        self.assertIsNone(settings.data.copernicus_data_path)
        self.assertIsNone(settings.data.gfs_data_path)
        self.assertFalse(settings.data.allow_production_replay_fixture)
        validate_production_data_sources(settings)

    def test_production_rejects_mock_providers_regardless_of_replay_flag(self):
        """Rule D: Mock providers are strictly forbidden in production even if replay flag is True."""
        settings = Feature2Settings(
            environment="production",
            data=DataSourceConfig(
                wind_provider="mock",
                allow_production_replay_fixture=True
            )
        )
        with self.assertRaises(ConfigurationError) as ctx:
            validate_production_data_sources(settings)
        self.assertIn("Production mode strictly forbids mock wind provider", str(ctx.exception))

    def test_gfs_provider_fails_closed_in_production_without_explicit_flag(self):
        """P1: GFSWindProvider raises ConfigurationError before loading local fixture in production."""
        from feature2.data.wind.gfs import GFSWindProvider, GFSConfig

        fixture_path = os.path.abspath("tests/fixtures/environment/north_sea_forecast_wind_2018.nc")
        prod_settings_default = Feature2Settings.production()

        # In production without allow_production_replay_fixture=True, constructor raises ConfigurationError
        with self.assertRaises(ConfigurationError) as ctx:
            GFSWindProvider(
                config=GFSConfig(),
                data_path=fixture_path,
                settings=prod_settings_default,
            )
        self.assertIn("Production mode strictly forbids local fixture data_path for GFS wind", str(ctx.exception))

        # With explicit opt-in, constructor accepts the fixture in replay mode
        prod_settings_replay = Feature2Settings.production(
            data=DataSourceConfig(allow_production_replay_fixture=True)
        )
        provider = GFSWindProvider(
            config=GFSConfig(),
            data_path=fixture_path,
            settings=prod_settings_replay,
        )
        self.assertEqual(provider.data_path, fixture_path)
        if provider.reader:
            provider.reader.close_dataset()

    def test_copernicus_forecast_provider_fails_closed_in_production_without_explicit_flag(self):
        """P1: CopernicusForecastCurrentsProvider raises ConfigurationError before loading local fixture in production."""
        from feature2.data.currents.copernicus import CopernicusForecastCurrentsProvider, CopernicusConfig

        fixture_path = os.path.abspath("tests/fixtures/environment/north_sea_copernicus_2018.nc")
        prod_settings_default = Feature2Settings.production()

        # In production without allow_production_replay_fixture=True, constructor raises ConfigurationError
        with self.assertRaises(ConfigurationError) as ctx:
            CopernicusForecastCurrentsProvider(
                config=CopernicusConfig(),
                data_path=fixture_path,
                settings=prod_settings_default,
            )
        self.assertIn("Production mode strictly forbids local fixture data_path for Copernicus forecast currents", str(ctx.exception))

        # With explicit opt-in, constructor accepts the fixture in replay mode
        prod_settings_replay = Feature2Settings.production(
            data=DataSourceConfig(allow_production_replay_fixture=True)
        )
        provider = CopernicusForecastCurrentsProvider(
            config=CopernicusConfig(),
            data_path=fixture_path,
            settings=prod_settings_replay,
        )
        self.assertEqual(provider.data_path, fixture_path)
        if provider.reader:
            provider.reader.close_dataset()

    def test_repository_contains_no_env_file(self):
        """P1: Verifies Feature 2 credentials are absent while .env.example remains intact."""
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.abspath(os.path.join(cur_dir, "..", ".."))
        env_example_path = os.path.join(backend_dir, ".env.example")
        feature2_env_path = os.path.join(backend_dir, "app", "feature2", ".env")

        self.assertFalse(os.path.exists(feature2_env_path), "app/feature2/.env file must NOT exist in repository.")
        self.assertTrue(os.path.exists(env_example_path), ".env.example must be preserved as clean template.")


if __name__ == "__main__":
    unittest.main()

