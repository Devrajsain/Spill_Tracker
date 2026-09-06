"""
Unit tests for Feature 2 configuration system.
"""

import unittest
from feature2.config import Feature2Settings, WindageConfig, DiffusionConfig, BackwardTracingConfig, ForecastConfig


class TestFeature2Config(unittest.TestCase):

    def test_default_configuration_bounds(self):
        settings = Feature2Settings()

        # Backward search horizon defaults
        self.assertEqual(settings.backward.max_backtrack_hours, 72.0)
        self.assertEqual(settings.backward.candidate_time_step_hours, 3.0)
        self.assertGreater(settings.backward.particles_per_slick, 0)
        self.assertEqual(settings.backward.simulation_step_seconds, 600)

        # Forecast horizons
        self.assertEqual(settings.forecast.forecast_horizons_hours, [6.0, 12.0, 24.0, 48.0])

        # Windage parameters
        self.assertGreaterEqual(settings.windage.leeway_factor, 0.0)
        self.assertLessEqual(settings.windage.leeway_factor, 0.10)
        self.assertEqual(settings.windage.deflection_angle_deg, 0.0)

        # Diffusion parameters
        self.assertTrue(settings.diffusion.enable_stochastic_diffusion)
        self.assertEqual(settings.diffusion.horizontal_diffusivity_m2_s, 10.0)

        # Reproducible random seed
        self.assertEqual(settings.random_seed, 42)

    def test_custom_overrides(self):
        custom = Feature2Settings(
            random_seed=999,
            windage=WindageConfig(leeway_factor=0.035, deflection_angle_deg=5.0),
            diffusion=DiffusionConfig(horizontal_diffusivity_m2_s=25.0),
            backward=BackwardTracingConfig(max_backtrack_hours=48.0, candidate_time_step_hours=2.0)
        )
        self.assertEqual(custom.random_seed, 999)
        self.assertEqual(custom.windage.leeway_factor, 0.035)
        self.assertEqual(custom.windage.deflection_angle_deg, 5.0)
        self.assertEqual(custom.diffusion.horizontal_diffusivity_m2_s, 25.0)
        self.assertEqual(custom.backward.max_backtrack_hours, 48.0)


if __name__ == "__main__":
    unittest.main()
