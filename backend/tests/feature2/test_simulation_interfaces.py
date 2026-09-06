"""
Unit tests for simulation components, advection leeway combination, and diffusion.
"""

from datetime import datetime
import unittest
import numpy as np
from feature2.config import WindageConfig, DiffusionConfig
from feature2.data.base import VectorFieldSample
from feature2.simulation.advection import AdvectionCalculator
from feature2.simulation.diffusion import TurbulentDiffusion
from feature2.simulation.particles import ParticleManager
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry


class TestSimulationComponents(unittest.TestCase):

    def test_advection_leeway_calculation(self):
        windage_cfg = WindageConfig(leeway_factor=0.03, deflection_angle_deg=0.0)
        advection = AdvectionCalculator(windage_cfg)

        curr = VectorFieldSample(u=0.5, v=0.2, valid_time=datetime.utcnow())
        wind = VectorFieldSample(u=10.0, v=0.0, valid_time=datetime.utcnow())

        adv_vec = advection.compute_velocity(curr, wind)
        # u_total = 0.5 + 0.03 * 10.0 = 0.8 m/s
        self.assertAlmostEqual(adv_vec.u_total_ms, 0.8, places=3)
        self.assertAlmostEqual(adv_vec.v_total_ms, 0.2, places=3)

    def test_turbulent_diffusion_deterministic_seed(self):
        diff_cfg = DiffusionConfig(horizontal_diffusivity_m2_s=10.0, enable_stochastic_diffusion=True)
        diffusion = TurbulentDiffusion(diff_cfg)

        rng = np.random.RandomState(42)
        dx, dy = diffusion.random_displacement_meters(dt_seconds=600.0, num_particles=100, rng=rng)

        self.assertEqual(len(dx), 100)
        self.assertEqual(len(dy), 100)
        # Verify non-zero variance
        self.assertGreater(np.var(dx), 0.0)

    def test_particle_seeding_from_slick(self):
        slick = SlickDetectionInput(
            spill_id="TEST-001",
            observation_time=datetime.utcnow(),
            area_sq_km=2.0,
            perimeter_km=6.0,
            centroid=CentroidCoordinates(latitude=18.5, longitude=72.5),
            geometry=GeoJSONGeometry(
                type="Polygon",
                coordinates=[
                    [[72.0, 18.0], [73.0, 18.0], [73.0, 19.0], [72.0, 19.0], [72.0, 18.0]]
                ]
            )
        )
        ensemble = ParticleManager.seed_from_slick(slick, num_particles=30, random_seed=42)
        self.assertEqual(len(ensemble.particles), 30)
        self.assertEqual(len(ensemble.active_coordinates()), 30)


if __name__ == "__main__":
    unittest.main()
