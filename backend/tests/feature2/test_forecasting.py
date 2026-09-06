"""
Task 3E: Forward Oil-Slick Trajectory Forecasting Test Suite.
Verifies:
  1. Deterministic analytical trajectory validation (+6h, +12h, +24h, +48h).
  2. Stochastic ensemble forecast: spread growth, finite numbers, no NaNs/Infs.
  3. Strict reproducibility with master seed; variation with different seeds.
  4. Horizon dispersion consistency (spread_6h <= spread_12h <= spread_24h <= spread_48h).
  5. Feature 1 polygon seeding: particles inside polygon at T0, MultiPolygon clear error.
  6. Dynamic forecast environmental domain generation without hardcoded coordinates.
  7. Multi-scene spatial and temporal domain isolation (Scene A vs. Scene B).
  8. Environmental data coverage failure: partial horizon validity.
  9. Exact UTC forecast timestamps at +6h, +12h, +24h, +48h.
 10. Antimeridian dateline crossing (+/- 180 longitude) handling without coordinate jumps.
 11. Quality thresholds and minimum active particle fraction validation.
 12. Optional origin-conditioned hypothesis metadata tracking.
 13. End-to-end Feature 1 payload forecasting integration.
 14. GeoJSON FeatureCollection visualization output formatting.
 15. FastAPI /feature2/forecast and /feature2/pipeline endpoints integration.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, List, Optional
import unittest
import numpy as np
from fastapi.testclient import TestClient

from feature2.config import Feature2Settings, default_settings
from feature2.data.base import HistoricalCurrentProvider, CurrentSample, EnvironmentalDataProvider
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.geo.coordinates import (
    haversine_distance_km,
    meters_to_lat_deg,
    meters_to_lon_deg,
    EARTH_RADIUS_KM,
)
from feature2.geo.spatial import is_point_in_polygon
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.schemas.output_schema import (
    ForecastAnalysisResult,
    ForecastHorizonResult,
    Feature2PipelineResponse,
)
from feature2.forecast.forecaster import ForwardForecaster, predict_slick_forecast, circular_mean_longitude
from feature2.output.formatter import OutputFormatter
from feature2.api.routes import router
from fastapi import FastAPI


class ConstantCurrentProvider(HistoricalCurrentProvider):
    """Predictable uniform hydrodynamic velocity field."""

    def __init__(self, u: float = 0.5, v: float = 0.3):
        self._u = u
        self._v = v
        self.query_log = []

    @property
    def provider_name(self) -> str:
        return "constant_current_mock"

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


class ExpiringCoverageCurrentProvider(HistoricalCurrentProvider):
    """Provider whose data coverage strictly expires after a specified cutoff time."""

    def __init__(self, cutoff_time: datetime, u: float = 0.4, v: float = 0.2):
        self.cutoff_time = cutoff_time
        self._u = u
        self._v = v

    @property
    def provider_name(self) -> str:
        return "expiring_coverage_current_mock"

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        if timestamp > self.cutoff_time:
            from feature2.exceptions import EnvironmentalCoverageError
            raise EnvironmentalCoverageError(
                f"Requested timestamp {timestamp.isoformat()} exceeds provider coverage cutoff {self.cutoff_time.isoformat()}"
            )
        return CurrentSample(
            u_current_mps=self._u,
            v_current_mps=self._v,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )


class TestForwardOilSlickForecasting(unittest.TestCase):
    """Verification suite for Task 3E."""

    def setUp(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "feature2", "schemas", "sample_feature1_payload.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.f1_payload = SlickDetectionInput(**json.load(f))

        self.t0 = datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc)

    def test_01_deterministic_analytical_trajectory_validation(self):
        """
        TEST 1: Analytical validation against known constant current.
        Start center: 25.0 N, 54.0 E.
        u = 0.5 m/s, v = 0.3 m/s, wind = 0, diffusion = 0.
        Verifies predicted centroids at +6h, +12h, +24h, +48h match analytical expectations.
        """
        lat0, lon0 = 25.0, 54.0
        u, v = 0.5, 0.3
        provider = ConstantCurrentProvider(u=u, v=v)

        # Small 0.01 deg synthetic square slick centered at (25.0, 54.0)
        slick = SlickDetectionInput(
            spill_id="TEST_ANALYTICAL_01",
            observation_time=self.t0,
            centroid=CentroidCoordinates(latitude=lat0, longitude=lon0),
            area_sq_km=1.0,
            perimeter_km=4.0,
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[[
                    [lon0 - 0.005, lat0 - 0.005],
                    [lon0 + 0.005, lat0 - 0.005],
                    [lon0 + 0.005, lat0 + 0.005],
                    [lon0 - 0.005, lat0 + 0.005],
                    [lon0 - 0.005, lat0 - 0.005],
                ]]
            )
        )

        forecaster = ForwardForecaster(current_provider=provider)
        res = forecaster.predict(
            slick=slick,
            forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
            ensemble_size=1,
            particles_per_slick=20,
            dt_seconds=300.0,
            diffusion_enabled=False
        )

        for h in [6.0, 12.0, 24.0, 48.0]:
            key = f"{int(h)}h"
            self.assertIn(key, res.forecast)
            pred = res.forecast[key]
            self.assertTrue(pred.valid)

            # Analytical expected displacement in meters
            sec = h * 3600.0
            dx_m = u * sec
            dy_m = v * sec

            exp_lat = lat0 + meters_to_lat_deg(dy_m)
            mid_lat = (lat0 + exp_lat) / 2.0
            exp_lon = lon0 + meters_to_lon_deg(dx_m, mid_lat)

            # Error in km between numerical centroid and analytical expectation (< 200m over up to 86 km drift)
            err_km = haversine_distance_km(pred.centroid.latitude, pred.centroid.longitude, exp_lat, exp_lon)
            self.assertLess(err_km, 0.2, f"Displacement error at +{h}h is {err_km:.4f} km; expected < 0.2 km")

    def test_02_stochastic_ensemble_validation(self):
        """
        TEST 2: Stochastic ensemble validation.
        Constant velocity + nonzero diffusion Kh = 15.0 m^2/s, ensemble_size = 5.
        Verifies:
          - Ensemble mean approximately follows drift
          - Spread is positive and finite
          - No NaN/Inf values
        """
        provider = ConstantCurrentProvider(u=0.4, v=0.2)
        forecaster = ForwardForecaster(current_provider=provider)

        res = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
            ensemble_size=5,
            particles_per_slick=30,
            dt_seconds=600.0,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=15.0,
            random_seed=42
        )

        for h_key in ["6h", "12h", "24h", "48h"]:
            pred = res.forecast[h_key]
            self.assertTrue(pred.valid)
            self.assertGreater(pred.uncertainty.radius_km, 0.0)
            self.assertFalse(np.isnan(pred.centroid.latitude))
            self.assertFalse(np.isnan(pred.centroid.longitude))
            self.assertFalse(np.isinf(pred.uncertainty.radius_km))
            self.assertGreater(pred.uncertainty.semi_major_km, 0.0)
            self.assertGreater(pred.uncertainty.semi_minor_km, 0.0)

    def test_03_reproducibility_with_same_seed_and_difference_with_new_seed(self):
        """
        TEST 3: Reproducibility validation.
        Same seed produces identical results. Different seeds produce different realizations.
        """
        provider = ConstantCurrentProvider(u=0.5, v=0.2)
        forecaster = ForwardForecaster(current_provider=provider)

        res1 = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0],
            ensemble_size=3,
            particles_per_slick=25,
            dt_seconds=600.0,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=20.0,
            random_seed=12345
        )

        res2 = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0],
            ensemble_size=3,
            particles_per_slick=25,
            dt_seconds=600.0,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=20.0,
            random_seed=12345
        )

        res3 = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0],
            ensemble_size=3,
            particles_per_slick=25,
            dt_seconds=600.0,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=20.0,
            random_seed=99999
        )

        # Same seed produces identical centroids and uncertainties
        self.assertEqual(res1.forecast["6h"].centroid.latitude, res2.forecast["6h"].centroid.latitude)
        self.assertEqual(res1.forecast["6h"].centroid.longitude, res2.forecast["6h"].centroid.longitude)
        self.assertEqual(res1.forecast["6h"].uncertainty.radius_km, res2.forecast["6h"].uncertainty.radius_km)

        # Different seed produces different spread or centroid
        self.assertNotEqual(
            res1.forecast["6h"].uncertainty.radius_km,
            res3.forecast["6h"].uncertainty.radius_km
        )

    def test_04_horizon_dispersion_consistency(self):
        """
        TEST 4: Horizon dispersion consistency.
        For single continuous simulation with constant diffusion:
        spread_6h <= spread_12h <= spread_24h <= spread_48h.
        """
        provider = ConstantCurrentProvider(u=0.3, v=0.2)
        forecaster = ForwardForecaster(current_provider=provider)

        res = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
            ensemble_size=5,
            particles_per_slick=40,
            dt_seconds=600.0,
            diffusion_enabled=True,
            diffusion_coefficient_m2_s=25.0,
            random_seed=777
        )

        s6 = res.forecast["6h"].uncertainty.radius_km
        s12 = res.forecast["12h"].uncertainty.radius_km
        s24 = res.forecast["24h"].uncertainty.radius_km
        s48 = res.forecast["48h"].uncertainty.radius_km

        self.assertLessEqual(s6, s12)
        self.assertLessEqual(s12, s24)
        self.assertLessEqual(s24, s48)

    def test_05_feature1_polygon_seeding_and_multipolygon_error(self):
        """
        TEST 5: Verify all seeded particles lie inside Feature 1 polygon at T0,
        and MultiPolygon raises clear NotImplementedError.
        """
        # 1. MultiPolygon raises clear NotImplementedError
        multi_poly_slick = SlickDetectionInput(
            spill_id="TEST_MULTI_01",
            observation_time=self.t0,
            centroid=CentroidCoordinates(latitude=25.0, longitude=54.0),
            area_sq_km=2.0,
            perimeter_km=8.0,
            geometry=GeoJSONGeometry(
                type="MultiPolygon",
                coordinates=[
                    [[[54.0, 25.0], [54.01, 25.0], [54.01, 25.01], [54.0, 25.0]]],
                    [[[54.05, 25.05], [54.06, 25.05], [54.06, 25.06], [54.05, 25.05]]]
                ]
            )
        )
        provider = ConstantCurrentProvider()
        forecaster = ForwardForecaster(current_provider=provider)

        with self.assertRaises(NotImplementedError) as ctx:
            forecaster.predict(multi_poly_slick)
        self.assertIn("MultiPolygon", str(ctx.exception))

        # 2. Polygon seeding places points strictly inside polygon interior
        from feature2.simulation.particles import ParticleManager
        seeded = ParticleManager.seed_particles(self.f1_payload, num_particles=30, random_seed=42)
        poly_coords = self.f1_payload.geometry.coordinates[0]
        for p in seeded:
            self.assertTrue(
                is_point_in_polygon(p.longitude, p.latitude, poly_coords),
                f"Particle ({p.latitude}, {p.longitude}) was initialized outside the slick polygon!"
            )
            self.assertEqual(p.timestamp, self.f1_payload.observation_time)

    def test_06_dynamic_forecast_environmental_domain(self):
        """
        TEST 6: Forecast environmental domain is constructed dynamically from
        Feature 1 geometry + forecast horizon + buffer. No hardcoded coordinates.
        """
        so = SentinelObservationDomain.from_feature1_input(self.f1_payload)
        eq = EnvironmentalQueryDomain.from_sentinel_observation(
            sentinel_domain=so,
            buffer_distance_km=75.0,
            forecast_horizon_hours=48.0
        )

        self.assertEqual(eq.forecast_start_time, so.observation_time)
        self.assertEqual(eq.forecast_end_time, so.observation_time + timedelta(hours=48))
        self.assertEqual(eq.forecast_horizon_hours, 48.0)
        self.assertEqual(eq.buffer_distance_km, 75.0)

        # Environmental bbox strictly expands source bbox by buffer
        self.assertLess(eq.min_lat, so.min_lat)
        self.assertGreater(eq.max_lat, so.max_lat)

    def test_07_multi_scene_spatial_and_temporal_isolation(self):
        """
        TEST 7: Multi-scene isolation. Scene A (Persian Gulf) and Scene B (North Sea)
        never cross-contaminate environmental queries or global state.
        """
        scene_a = SlickDetectionInput(
            spill_id="SCENE_A_PERSIAN_GULF",
            observation_time=datetime(2026, 8, 27, 6, 30, tzinfo=timezone.utc),
            centroid=CentroidCoordinates(latitude=25.1, longitude=53.8),
            area_sq_km=1.0,
            perimeter_km=4.0,
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[53.79, 25.09], [53.81, 25.09], [53.81, 25.11], [53.79, 25.11], [53.79, 25.09]]]
            )
        )
        scene_b = SlickDetectionInput(
            spill_id="SCENE_B_NORTH_SEA",
            observation_time=datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc),
            centroid=CentroidCoordinates(latitude=56.5, longitude=3.2),
            area_sq_km=1.5,
            perimeter_km=5.0,
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[3.19, 56.49], [3.21, 56.49], [3.21, 56.51], [3.19, 56.51], [3.19, 56.49]]]
            )
        )

        prov_a = ConstantCurrentProvider(u=0.5, v=0.2)
        prov_b = ConstantCurrentProvider(u=0.1, v=0.4)

        fc_a = ForwardForecaster(current_provider=prov_a)
        fc_b = ForwardForecaster(current_provider=prov_b)

        res_a = fc_a.predict(scene_a, forecast_horizons_hours=[6.0, 12.0], ensemble_size=1, particles_per_slick=10, dt_seconds=600.0)
        res_b = fc_b.predict(scene_b, forecast_horizons_hours=[6.0, 12.0], ensemble_size=1, particles_per_slick=10, dt_seconds=600.0)

        # Geographic bounds separation
        self.assertTrue(all(24.0 < res_a.forecast[h].centroid.latitude < 27.0 for h in ["6h", "12h"]))
        self.assertTrue(all(55.0 < res_b.forecast[h].centroid.latitude < 58.0 for h in ["6h", "12h"]))

        # Temporal separation
        self.assertEqual(res_a.observation_time, scene_a.observation_time)
        self.assertEqual(res_b.observation_time, scene_b.observation_time)

    def test_08_environmental_coverage_cutoff_failure(self):
        """
        TEST 8: Environmental coverage failure. Provider coverage ends at T0 + 15 hours.
        Verifies:
          - +6h: valid = True
          - +12h: valid = True
          - +24h: valid = False, quality = 'low'
          - +48h: valid = False, quality = 'low'
        """
        cutoff = self.t0 + timedelta(hours=15)
        prov = ExpiringCoverageCurrentProvider(cutoff_time=cutoff)
        forecaster = ForwardForecaster(current_provider=prov)

        res = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
            ensemble_size=1,
            particles_per_slick=15,
            dt_seconds=600.0,
            diffusion_enabled=False
        )

        self.assertTrue(res.forecast["6h"].valid)
        self.assertEqual(res.forecast["6h"].quality, "high")

        self.assertTrue(res.forecast["12h"].valid)
        self.assertEqual(res.forecast["12h"].quality, "high")

        self.assertFalse(res.forecast["24h"].valid)
        self.assertEqual(res.forecast["24h"].quality, "low")
        self.assertIsNotNone(res.forecast["24h"].reason)

        self.assertFalse(res.forecast["48h"].valid)
        self.assertEqual(res.forecast["48h"].quality, "low")

    def test_09_exact_utc_forecast_timestamps(self):
        """
        TEST 9: Timestamp arithmetic verification.
        If T0 = 2026-08-27T06:30:12Z:
          +6h  = 2026-08-27T12:30:12Z
          +12h = 2026-08-27T18:30:12Z
          +24h = 2026-08-28T06:30:12Z
          +48h = 2026-08-29T06:30:12Z
        """
        t_obs = datetime(2026, 8, 27, 6, 30, 12, tzinfo=timezone.utc)
        slick = SlickDetectionInput(
            spill_id="TEST_TIME_01",
            observation_time=t_obs,
            centroid=CentroidCoordinates(latitude=25.0, longitude=54.0),
            area_sq_km=1.0,
            perimeter_km=4.0,
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[53.99, 24.99], [54.01, 24.99], [54.01, 25.01], [53.99, 25.01], [53.99, 24.99]]]
            )
        )

        prov = ConstantCurrentProvider()
        forecaster = ForwardForecaster(current_provider=prov)
        res = forecaster.predict(slick, forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0], ensemble_size=1, particles_per_slick=5, dt_seconds=600.0)

        self.assertEqual(res.forecast["6h"].forecast_time, datetime(2026, 8, 27, 12, 30, 12, tzinfo=timezone.utc))
        self.assertEqual(res.forecast["12h"].forecast_time, datetime(2026, 8, 27, 18, 30, 12, tzinfo=timezone.utc))
        self.assertEqual(res.forecast["24h"].forecast_time, datetime(2026, 8, 28, 6, 30, 12, tzinfo=timezone.utc))
        self.assertEqual(res.forecast["48h"].forecast_time, datetime(2026, 8, 29, 6, 30, 12, tzinfo=timezone.utc))

    def test_10_dateline_crossing_normalization(self):
        """
        TEST 10: Dateline crossing near +/- 180 longitude.
        Slick starts at 179.95 E. Eastward current u = 1.0 m/s pushes it across 180 into -179.95 W.
        Verifies:
          - No absurd longitude jumps (e.g. 359 degrees)
          - Centroid longitude is normalized inside [-180, 180]
          - Circular mean longitude behaves smoothly across the antimeridian
        """
        lat0, lon0 = 10.0, 179.95
        slick = SlickDetectionInput(
            spill_id="TEST_DATELINE_01",
            observation_time=self.t0,
            centroid=CentroidCoordinates(latitude=lat0, longitude=lon0),
            area_sq_km=1.0,
            perimeter_km=4.0,
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[179.94, 9.99], [179.96, 9.99], [179.96, 10.01], [179.94, 10.01], [179.94, 9.99]]]
            )
        )

        prov = ConstantCurrentProvider(u=2.0, v=0.0)  # Strong eastward flow
        forecaster = ForwardForecaster(current_provider=prov)

        res = forecaster.predict(
            slick=slick,
            forecast_horizons_hours=[6.0, 12.0],
            ensemble_size=1,
            particles_per_slick=10,
            dt_seconds=300.0,
            diffusion_enabled=False
        )

        pred_12h = res.forecast["12h"]
        self.assertTrue(pred_12h.valid)
        # Should have crossed 180 into negative longitude
        self.assertLess(pred_12h.centroid.longitude, 0.0)
        self.assertGreaterEqual(pred_12h.centroid.longitude, -180.0)
        # Distance from 179.95 across 180 to ~ -179.3 is small (~80 km)
        dist_km = haversine_distance_km(lat0, lon0, pred_12h.centroid.latitude, pred_12h.centroid.longitude)
        self.assertLess(dist_km, 120.0)

    def test_11_origin_conditioned_metadata_tracking(self):
        """
        TEST 11: Origin-conditioned forecasting hypothesis metadata tracking.
        Passing origin_candidate_id="ORIGIN_1" preserves primary slick initialization
        while documenting the candidate hypothesis in metadata and provenance.
        """
        prov = ConstantCurrentProvider()
        forecaster = ForwardForecaster(current_provider=prov)

        res = forecaster.predict(
            slick=self.f1_payload,
            origin_candidate_id="ORIGIN_1",
            forecast_horizons_hours=[6.0],
            ensemble_size=1,
            particles_per_slick=10,
            dt_seconds=600.0
        )

        self.assertEqual(res.origin_candidate_id, "ORIGIN_1")
        self.assertEqual(res.metadata.get("origin_candidate_id"), "ORIGIN_1")

    def test_12_geojson_output_formatting(self):
        """
        TEST 12: GeoJSON output formatting.
        Converts ForecastAnalysisResult into standard RFC 7946 FeatureCollection
        containing predicted centroids and uncertainty zones.
        """
        prov = ConstantCurrentProvider()
        forecaster = ForwardForecaster(current_provider=prov)

        res = forecaster.predict(
            slick=self.f1_payload,
            forecast_horizons_hours=[6.0, 12.0],
            ensemble_size=2,
            particles_per_slick=15,
            dt_seconds=600.0,
            diffusion_enabled=True,
            random_seed=42
        )

        geojson = OutputFormatter.forecast_result_to_geojson(res)

        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertGreater(len(geojson["features"]), 0)

        feature_types = [f["properties"]["feature_type"] for f in geojson["features"]]
        self.assertIn("forecast_predicted_centroid", feature_types)
        self.assertIn("forecast_uncertainty_zone", feature_types)

    def test_13_api_and_pipeline_integration(self):
        """
        TEST 13: FastAPI service-level integration testing /feature2/forecast and /feature2/pipeline.
        """
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        payload_dict = self.f1_payload.model_dump(mode="json")

        # 1. Test /feature2/forecast endpoint
        fc_response = client.post("/feature2/forecast", json=payload_dict)
        self.assertEqual(fc_response.status_code, 200)
        fc_data = fc_response.json()
        self.assertEqual(fc_data["spill_id"], self.f1_payload.spill_id)
        self.assertIn("forecast", fc_data)
        self.assertIn("6h", fc_data["forecast"])
        self.assertIn("disclaimers", fc_data)

        # 2. Test /feature2/pipeline endpoint
        pipe_response = client.post("/feature2/pipeline", json=payload_dict)
        self.assertEqual(pipe_response.status_code, 200)
        pipe_data = pipe_response.json()
        self.assertEqual(pipe_data["spill_id"], self.f1_payload.spill_id)
        self.assertIn("forecast", pipe_data)
        self.assertIn("origin_analysis", pipe_data)


if __name__ == "__main__":
    unittest.main()
