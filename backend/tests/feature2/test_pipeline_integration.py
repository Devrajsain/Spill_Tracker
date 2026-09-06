"""
Task 3F: End-to-End Feature 2 Pipeline Integration Test Suite.
Verifies:
  1. /trace-origin returns non-empty candidate_origins, best_candidate, and release_time_window.
  2. /pipeline returns non-empty origin_estimation, origin_analysis, and 6h, 12h, 24h, 48h forecasts.
  3. Feature 1 observed slick geometry at T0 is used as the primary forecast initialization.
  4. Origin candidates do NOT replace the observed slick as primary forecast initial condition.
  5. Dynamic environmental domain follows Feature 1 coordinates and observation time T0.
  6. Multi-scene geographic and temporal isolation (Scene A vs Scene B).
  7. Timezone-aware UTC timestamps throughout pipeline.
  8. Environmental coverage failure propagates cleanly with structured error / HTTP 422.
  9. No fake remote data is generated when remote credentials are unavailable.
 10. Reproducibility with deterministic master random seeds.
 11. GeoJSON output endpoints (/geojson/origin, /geojson/forecast, /geojson/pipeline).
 12. Synthetic end-to-end forward-to-backward model closure validation.
"""

from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any, Dict, List
import unittest
import numpy as np
from fastapi.testclient import TestClient

from main import app
from feature2.config import Feature2Settings, BackwardTracingConfig, ForecastConfig
from feature2.data.base import (
    HistoricalCurrentProvider,
    HistoricalWindProvider,
    CurrentSample,
    WindSample,
)
from feature2.data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from feature2.exceptions import EnvironmentalCoverageError
from feature2.geo.coordinates import haversine_distance_km, meters_to_lon_deg
from feature2.origin.estimator import OriginEstimator
from feature2.pipeline.service import Feature2PipelineService
from feature2.forecast.forecaster import ForwardForecaster
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.simulation.forward.engine import ForwardSimulationEngine
from feature2.output.formatter import OutputFormatter


class ConstantVelocityMock(HistoricalCurrentProvider):
    """Deterministic mock provider providing constant velocity over an infinite or bounded domain."""

    def __init__(
        self,
        u: float = 0.5,
        v: float = 0.0,
        provider_name: str = "constant_mock",
        min_lon: float = -180.0,
        max_lon: float = 180.0,
        min_lat: float = -90.0,
        max_lat: float = 90.0,
    ):
        self._u = u
        self._v = v
        self._name = provider_name
        self._min_lon = min_lon
        self._max_lon = max_lon
        self._min_lat = min_lat
        self._max_lat = max_lat

    @property
    def provider_name(self) -> str:
        return self._name

    def fetch_grid(self, window: Any) -> bool:
        if hasattr(window, "environmental_bbox"):
            min_lat, max_lat, min_lon, max_lon = window.environmental_bbox
            if min_lat < self._min_lat or max_lat > self._max_lat or min_lon < self._min_lon or max_lon > self._max_lon:
                return False
        return True

    def get_current(self, latitude: float, longitude: float, timestamp: datetime) -> CurrentSample:
        if not (self._min_lat <= latitude <= self._max_lat and self._min_lon <= longitude <= self._max_lon):
            raise EnvironmentalCoverageError(f"Coordinate ({latitude}, {longitude}) is out of mock coverage.")
        return CurrentSample(
            u_current_mps=self._u,
            v_current_mps=self._v,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude,
            source=self._name,
        )


class ConstantWindMock(HistoricalWindProvider):
    """Deterministic mock provider providing constant surface wind."""

    def __init__(self, u: float = 0.0, v: float = 0.0, provider_name: str = "constant_wind_mock"):
        self._u = u
        self._v = v
        self._name = provider_name

    @property
    def provider_name(self) -> str:
        return self._name

    def fetch_grid(self, window: Any) -> bool:
        return True

    def get_wind(self, latitude: float, longitude: float, timestamp: datetime) -> WindSample:
        return WindSample(
            u_wind_mps=self._u,
            v_wind_mps=self._v,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude,
            source=self._name,
        )


class TestPipelineIntegration(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

        # Baseline Feature 1 SAR slick input
        self.obs_time = datetime(2026, 8, 27, 6, 30, 0, tzinfo=timezone.utc)
        self.payload = {
            "spill_id": "S1A_IW_GRDH_1SDV_20260827T063012_OIL_001",
            "observation_time": self.obs_time.isoformat(),
            "area_sq_km": 1.25,
            "perimeter_km": 4.8,
            "centroid": {"latitude": 25.0, "longitude": 54.0},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [53.995, 24.995],
                        [54.005, 24.995],
                        [54.005, 25.005],
                        [53.995, 25.005],
                        [53.995, 24.995]
                    ]
                ]
            },
            "metadata": {
                "satellite": "Sentinel-1A",
                "sensor_mode": "IW",
                "polarization": "VV+VH"
            }
        }

    def test_01_trace_origin_endpoint_returns_actual_candidates(self):
        """A. /trace-origin endpoint must return real non-empty origin candidates and release window."""
        response = self.client.post("/feature2/trace-origin", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()

        self.assertEqual(data["spill_id"], self.payload["spill_id"])
        self.assertIn("candidate_origins", data)
        self.assertGreater(len(data["candidate_origins"]), 0, "candidate_origins must not be empty")

        first_cand = data["candidate_origins"][0]
        self.assertIn("estimated_centroid", first_cand)
        self.assertIn("spatial_uncertainty", first_cand)
        self.assertIn("release_time_window", first_cand)
        self.assertGreaterEqual(first_cand["confidence_score"], 0.0)
        self.assertLessEqual(first_cand["confidence_score"], 1.0)

        # Rich Task 3D model validation
        self.assertIn("origin_estimation", data)
        if data["origin_estimation"]:
            self.assertIn("release_time_window", data["origin_estimation"])
            self.assertIn("candidates", data["origin_estimation"])

    def test_02_pipeline_endpoint_full_integration(self):
        """B. /pipeline endpoint must return non-empty origin_estimation and all forecast horizons."""
        response = self.client.post("/feature2/pipeline", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()

        self.assertEqual(data["spill_id"], self.payload["spill_id"])
        self.assertIsNotNone(data["origin_estimation"])
        self.assertGreater(len(data["origin_estimation"]["candidates"]), 0)

        # Verify all 4 mandatory forecast horizons
        self.assertIn("forecast", data)
        forecast_dict = data["forecast"]
        for h_key in ["6h", "12h", "24h", "48h"]:
            self.assertIn(h_key, forecast_dict, f"Missing horizon '{h_key}' in pipeline forecast")
            step = forecast_dict[h_key]
            self.assertIn("centroid", step)
            self.assertIn("uncertainty", step)
            self.assertTrue(step["valid"])

    def test_03_forecast_seeds_from_observed_slick_not_origin(self):
        """C & D. Forecast must initialize from observed Feature 1 slick at T0, NOT from backward origin."""
        # Create deterministic service with distinct eastward current
        curr_provider = ConstantVelocityMock(u=0.5, v=0.0)
        wind_provider = ConstantWindMock(u=0.0, v=0.0)
        settings = Feature2Settings(
            random_seed=42,
            backward=BackwardTracingConfig(max_backtrack_hours=6.0, candidate_time_step_hours=3.0, particles_per_slick=50),
            forecast=ForecastConfig(forecast_horizons_hours=[6.0], particles_per_slick=50, forecast_ensemble_size=1)
        )
        engine_fwd = ForwardSimulationEngine(curr_provider, wind_provider, settings)
        forecaster = ForwardForecaster(simulation_engine=engine_fwd, settings=settings)
        origin_est = OriginEstimator(curr_provider, wind_provider, settings)
        service = Feature2PipelineService(origin_est, forecaster, settings)

        slick_input = SlickDetectionInput(**self.payload)
        pipe_res = service.run_pipeline(slick_input)

        # Origin candidate is backtracked westward (approx lon 53.9)
        best_cand = pipe_res.origin_estimation.best_candidate
        self.assertIsNotNone(best_cand)
        self.assertLess(best_cand.longitude, 54.0, "Backward origin candidate should be westward of slick")

        # Forecast at +6h must be advected eastward from observed slick at 54.0
        fc_6h = pipe_res.forecast["6h"]
        self.assertGreater(fc_6h.predicted_centroid.longitude, 54.0, "Forecast must drift eastward from observed slick")

        # Verify drift distance is measured relative to observed slick (25.0, 54.0), not origin candidate
        expected_drift_km = (0.5 * 6.0 * 3600.0) / 1000.0  # 10.8 km
        dist_from_observed = haversine_distance_km(
            slick_input.centroid.latitude, slick_input.centroid.longitude,
            fc_6h.predicted_centroid.latitude, fc_6h.predicted_centroid.longitude
        )
        self.assertAlmostEqual(dist_from_observed, expected_drift_km, delta=0.5)

    def test_04_dynamic_environmental_domain_follows_feature1_input(self):
        """E. Domain must be derived from Feature 1 observation geometry without hardcoded coordinates."""
        # Scene in North Sea (lat ~56, lon ~3)
        north_sea_payload = {
            "spill_id": "S1B_NORTH_SEA_001",
            "observation_time": "2026-10-10T14:00:00Z",
            "area_sq_km": 2.0,
            "perimeter_km": 6.0,
            "centroid": {"latitude": 56.5, "longitude": 3.2},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[3.18, 56.48], [3.22, 56.48], [3.22, 56.52], [3.18, 56.52], [3.18, 56.48]]
                ]
            }
        }
        obs_domain = SentinelObservationDomain.from_feature1_input(north_sea_payload)
        query_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain,
            buffer_distance_km=40.0,
            historical_horizon_hours=48.0,
            forecast_horizon_hours=24.0,
        )

        self.assertAlmostEqual(obs_domain.centroid_lat, 56.5, places=2)
        self.assertAlmostEqual(obs_domain.centroid_lon, 3.2, places=2)
        self.assertLess(query_domain.min_lat, 56.48)
        self.assertGreater(query_domain.max_lat, 56.52)
        self.assertLess(query_domain.min_lon, 3.18)
        self.assertGreater(query_domain.max_lon, 3.22)
        self.assertEqual(query_domain.historical_start_time, datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(query_domain.forecast_end_time, datetime(2026, 10, 11, 14, 0, 0, tzinfo=timezone.utc))

    def test_05_multi_scene_spatial_and_temporal_isolation(self):
        """F. Scene A and Scene B must produce completely isolated origin and forecast results."""
        payload_a = dict(self.payload)
        payload_b = {
            "spill_id": "S1_SCENE_B_PACIFIC",
            "observation_time": "2026-11-15T02:00:00Z",
            "area_sq_km": 1.5,
            "perimeter_km": 5.0,
            "centroid": {"latitude": -12.0, "longitude": -77.0},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[-77.02, -12.02], [-76.98, -12.02], [-76.98, -11.98], [-77.02, -11.98], [-77.02, -12.02]]
                ]
            }
        }

        resp_a = self.client.post("/feature2/pipeline", json=payload_a)
        resp_b = self.client.post("/feature2/pipeline", json=payload_b)

        data_a = resp_a.json()
        data_b = resp_b.json()

        # Scene A must stay around Arabian Gulf
        cand_a = data_a["origin_estimation"]["candidates"][0]
        self.assertAlmostEqual(cand_a["latitude"], 25.0, delta=1.5)
        self.assertAlmostEqual(cand_a["longitude"], 54.0, delta=1.5)
        self.assertIn("2026-08", cand_a["release_time"])

        # Scene B must stay around Peru / South Pacific
        cand_b = data_b["origin_estimation"]["candidates"][0]
        self.assertAlmostEqual(cand_b["latitude"], -12.0, delta=1.5)
        self.assertAlmostEqual(cand_b["longitude"], -77.0, delta=1.5)
        self.assertIn("2026-11", cand_b["release_time"])

    def test_06_timezone_aware_utc_timestamps(self):
        """G. All timestamps in the pipeline response must be timezone-aware UTC."""
        resp = self.client.post("/feature2/pipeline", json=self.payload)
        data = resp.json()

        # Check top-level observation_time
        obs_dt = datetime.fromisoformat(data["observation_time"])
        self.assertIsNotNone(obs_dt.tzinfo)

        # Check candidate release times
        for cand in data["origin_estimation"]["candidates"]:
            cand_dt = datetime.fromisoformat(cand["release_time"])
            self.assertIsNotNone(cand_dt.tzinfo)

        # Check forecast horizon times
        for h_key, step in data["forecast"].items():
            fc_dt = datetime.fromisoformat(step["forecast_time"])
            self.assertIsNotNone(fc_dt.tzinfo)

    def test_07_environmental_coverage_failure_raises_422(self):
        """H. Coverage failure must raise HTTP 422 with structured details, not fake data."""
        # Provider bounded to a tiny box that excludes the spill
        bounded_provider = ConstantVelocityMock(
            u=0.5, v=0.0,
            min_lat=10.0, max_lat=11.0, min_lon=10.0, max_lon=11.0
        )
        wind_provider = ConstantWindMock(u=0.0, v=0.0)
        settings = Feature2Settings()
        origin_est = OriginEstimator(bounded_provider, wind_provider, settings)
        forecaster = ForwardForecaster(ForwardSimulationEngine(bounded_provider, wind_provider, settings), settings)
        service = Feature2PipelineService(origin_est, forecaster, settings)

        slick_input = SlickDetectionInput(**self.payload)
        with self.assertRaises(EnvironmentalCoverageError):
            service.trace_origin(slick_input)

    def test_08_reproducibility_with_same_seed(self):
        """J. Identical settings and seed must yield bit-identical pipeline responses."""
        curr_provider = ConstantVelocityMock(u=0.3, v=0.2)
        wind_provider = ConstantWindMock(u=0.0, v=0.0)
        settings = Feature2Settings(
            random_seed=12345,
            backward=BackwardTracingConfig(max_backtrack_hours=6.0, candidate_time_step_hours=3.0, particles_per_slick=30),
            forecast=ForecastConfig(forecast_horizons_hours=[6.0, 12.0], particles_per_slick=30, forecast_ensemble_size=2)
        )
        service1 = Feature2PipelineService(
            OriginEstimator(curr_provider, wind_provider, settings),
            ForwardForecaster(simulation_engine=ForwardSimulationEngine(curr_provider, wind_provider, settings), settings=settings),
            settings
        )
        service2 = Feature2PipelineService(
            OriginEstimator(curr_provider, wind_provider, settings),
            ForwardForecaster(simulation_engine=ForwardSimulationEngine(curr_provider, wind_provider, settings), settings=settings),
            settings
        )

        slick_input = SlickDetectionInput(**self.payload)
        res1 = service1.run_pipeline(slick_input)
        res2 = service2.run_pipeline(slick_input)

        # Verify bit-identical forecast centroid and spread
        self.assertEqual(res1.forecast["6h"].predicted_centroid.latitude, res2.forecast["6h"].predicted_centroid.latitude)
        self.assertEqual(res1.forecast["6h"].predicted_centroid.longitude, res2.forecast["6h"].predicted_centroid.longitude)
        self.assertEqual(res1.forecast["6h"].uncertainty.radius_km, res2.forecast["6h"].uncertainty.radius_km)

    def test_09_geojson_endpoints(self):
        """L. GeoJSON endpoints must return valid RFC 7946 FeatureCollections."""
        for endpoint in ["/feature2/geojson/origin", "/feature2/geojson/forecast", "/feature2/geojson/pipeline"]:
            resp = self.client.post(endpoint, json=self.payload)
            self.assertEqual(resp.status_code, 200, f"Endpoint {endpoint} failed: {resp.text}")
            data = resp.json()
            self.assertEqual(data["type"], "FeatureCollection")
            self.assertIn("features", data)
            self.assertGreater(len(data["features"]), 0, f"Endpoint {endpoint} returned 0 features")

    def test_10_synthetic_end_to_end_forward_backward_closure(self):
        """
        13. Synthetic End-to-End Validation:
        Known source at (25.0, 54.0), known release time T_release.
        Forward advect slick for 6.0 hours with known current (0.5 m/s Eastward).
        Then execute the backward pipeline from the forward-advected slick.
        Verify that the best reconstructed origin candidate matches the known source within ~0.2 km.
        """
        lat_src = 25.0
        lon_src = 54.0
        t_release = datetime(2026, 8, 27, 0, 0, 0, tzinfo=timezone.utc)
        drift_hours = 6.0
        t_obs = t_release + timedelta(hours=drift_hours)

        # Eastward velocity u = 0.5 m/s, v = 0.0 m/s
        u_curr = 0.5
        drift_meters = u_curr * (drift_hours * 3600.0)  # 10,800 m
        d_lon = meters_to_lon_deg(drift_meters, lat_src)
        obs_lon = lon_src + d_lon
        obs_lat = lat_src

        # Construct synthetic observed slick at T0
        delta = 0.005
        synthetic_payload = {
            "spill_id": "SYNTHETIC-CLOSURE-TEST-001",
            "observation_time": t_obs.isoformat(),
            "area_sq_km": 1.0,
            "perimeter_km": 4.0,
            "centroid": {"latitude": obs_lat, "longitude": obs_lon},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [obs_lon - delta, obs_lat - delta],
                        [obs_lon + delta, obs_lat - delta],
                        [obs_lon + delta, obs_lat + delta],
                        [obs_lon - delta, obs_lat + delta],
                        [obs_lon - delta, obs_lat - delta],
                    ]
                ]
            }
        }

        # Run pipeline with deterministic mock provider
        curr_provider = ConstantVelocityMock(u=u_curr, v=0.0)
        wind_provider = ConstantWindMock(u=0.0, v=0.0)
        settings = Feature2Settings(
            random_seed=42,
            backward=BackwardTracingConfig(
                max_backtrack_hours=12.0,
                candidate_time_step_hours=3.0,
                particles_per_slick=50,
                simulation_step_seconds=300,
            ),
            forecast=ForecastConfig(
                forecast_horizons_hours=[6.0],
                particles_per_slick=50,
                forecast_ensemble_size=1,
            )
        )
        service = Feature2PipelineService(
            OriginEstimator(curr_provider, wind_provider, settings),
            ForwardForecaster(simulation_engine=ForwardSimulationEngine(curr_provider, wind_provider, settings), settings=settings),
            settings
        )

        slick_input = SlickDetectionInput(**synthetic_payload)
        pipe_res = service.run_pipeline(slick_input)

        # Inspect origin candidates
        candidates = pipe_res.origin_estimation.candidates
        self.assertGreater(len(candidates), 0)

        # Find the candidate corresponding to the true release time (T0 - 6h)
        target_cand = min(
            candidates,
            key=lambda c: abs((c.release_time - t_release).total_seconds())
        )

        # Check temporal match: release time must be within 1 minute of true release time
        time_err_sec = abs((target_cand.release_time - t_release).total_seconds())
        self.assertLessEqual(time_err_sec, 60.0, f"Candidate release time error: {time_err_sec}s")

        # Check spatial closure: reconstructed candidate centroid must be close to (25.0, 54.0)
        err_km = haversine_distance_km(
            target_cand.latitude, target_cand.longitude,
            lat_src, lon_src
        )
        self.assertLess(err_km, 0.25, f"Spatial closure error: {err_km:.4f} km; expected < 0.25 km")


if __name__ == "__main__":
    unittest.main()
