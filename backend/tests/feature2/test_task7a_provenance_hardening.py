"""
Task 7A Regression Tests: Hardened Provenance, Honest Data Categorization,
Simulation Quality Semantics, and Non-Probabilistic Origin Scoring.
"""

from datetime import datetime, timezone
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
from feature2.exceptions import TemporalCoverageError
from feature2.origin.estimator import OriginEstimator
from feature2.forecast.forecaster import ForwardForecaster
from feature2.pipeline.service import Feature2PipelineService
from feature2.schemas.simulation_schema import EnvironmentalQueryWindow
from feature2.simulation.forward.engine import ForwardSimulationEngine
from scripts.validate_real_scene import inspect_sentinel1_geotiff, derive_feature1_output_from_mask


class TestTask7AProvenanceHardening(unittest.TestCase):
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
                particles_per_slick=20,
                simulation_step_seconds=300,
            ),
            forecast=ForecastConfig(
                forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
                particles_per_slick=20,
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
        cls.service = Feature2PipelineService(
            origin_estimator=cls.origin_estimator,
            forecaster=cls.forecaster,
            settings=cls.settings,
        )
        cls.pipeline_response = cls.service.run_pipeline(cls.slick)
        cls.unif = cls.pipeline_response.to_unified_result()

    def test_01_historical_forecast_provenance_is_not_labeled_live_operational(self):
        """Rule 1: Historical forecast provenance must NOT be labeled LIVE_OPERATIONAL when using fixtures."""
        status = self.unif.environment.forecast_provenance_status
        self.assertNotEqual(
            status,
            "LIVE_OPERATIONAL",
            "Violation: 2018 historical replay forecast was falsely labeled as LIVE_OPERATIONAL.",
        )
        self.assertEqual(status, "HISTORICAL_REPLAY_FIXTURE")
        self.assertIn("Historical replay forecast", self.unif.environment.forecast_provenance_notes)
        self.assertIn("current operational GFS does not archive the 2018 forecast cycle", self.unif.environment.forecast_provenance_notes)

    def test_02_operational_gfs_rejects_historical_2018_query(self):
        """Rule 2: Operational GFS remote endpoint must raise TemporalCoverageError for historical 2018 queries."""
        remote_gfs = GFSWindProvider(data_path=None)
        historical_window = EnvironmentalQueryWindow(
            min_lat=55.0,
            max_lat=55.5,
            min_lon=3.75,
            max_lon=4.25,
            start_time=datetime(2018, 8, 3, 17, 25, tzinfo=timezone.utc),
            end_time=datetime(2018, 8, 5, 17, 25, tzinfo=timezone.utc),
        )
        with self.assertRaises(TemporalCoverageError):
            remote_gfs.fetch_grid(historical_window)

    def test_03_local_fixture_usage_is_explicit_in_provenance(self):
        """Rule 3: Local fixture usage must be explicitly classified as LOCAL_TEST_FIXTURE."""
        fields = self.unif.environment.fields
        self.assertIn("forecast_wind", fields)
        self.assertIn("forecast_currents", fields)

        self.assertEqual(fields["forecast_wind"].source_type, "LOCAL_TEST_FIXTURE")
        self.assertEqual(fields["forecast_currents"].source_type, "LOCAL_TEST_FIXTURE")
        self.assertTrue(fields["forecast_wind"].used_in_numerical_simulation)
        self.assertTrue(fields["forecast_currents"].used_in_numerical_simulation)
        self.assertTrue(os.path.isabs(fields["forecast_wind"].filepath))
        self.assertTrue(os.path.isabs(fields["forecast_currents"].filepath))

    def test_04_forecast_quality_is_simulation_integrity_not_accuracy(self):
        """Rule 4: HIGH quality rating must be documented as numerical simulation integrity, NOT forecast accuracy."""
        quality = self.unif.quality
        self.assertEqual(quality.quality_metric_type, "numerical_simulation_integrity")
        self.assertEqual(quality.overall_simulation_quality, "HIGH")
        self.assertEqual(quality.overall, "HIGH")
        self.assertIn("NOT an empirical forecast accuracy estimate", quality.accuracy_notice)

        for h in self.unif.forecast.horizons:
            self.assertEqual(h.simulation_quality, "HIGH")

    def test_05_evidence_score_is_not_exposed_as_probability(self):
        """Rule 5: Origin candidate scores must be labeled as evidence_score and disclaimers must forbid probability interpretation."""
        best_c = self.unif.origin.best_candidate
        self.assertIsNotNone(best_c)
        self.assertTrue(hasattr(best_c, "evidence_score"))
        self.assertFalse(hasattr(best_c, "probability"))

        disclaimer = self.unif.origin.disclaimer.lower()
        self.assertIn("not a calibrated probability", disclaimer)
        self.assertIn("estimated convergence zone", disclaimer)

    def test_06_ensemble_is_classified_as_stochastic_realization(self):
        """Rule 6: Single-realization ensemble must be classified as stochastic particle realization, not probabilistic."""
        ensemble = self.unif.forecast.ensemble
        self.assertIsNotNone(ensemble)
        self.assertEqual(ensemble.ensemble_classification, "stochastic_particle_realization")
        self.assertIn("not a calibrated statistical confidence interval", ensemble.dispersion_interpretation.lower())

    def test_07_release_window_semantics(self):
        """Rule 7: Candidate release window is computed dynamically with 3h candidate intervals."""
        window = self.unif.origin.release_time_window
        self.assertIsNotNone(window)
        self.assertGreater(window.duration_hours, 0.0)

        # Verify candidate spacing across unique release times
        unique_times = sorted(list({c.release_time_utc for c in self.unif.origin.candidates}))
        self.assertEqual(len(unique_times), 24)
        for i in range(len(unique_times) - 1):
            diff_h = abs((unique_times[i + 1] - unique_times[i]).total_seconds()) / 3600.0
            self.assertAlmostEqual(diff_h, 3.0, places=3, msg=f"Candidate times not exactly 3h apart: {diff_h}h")


if __name__ == "__main__":
    unittest.main()
