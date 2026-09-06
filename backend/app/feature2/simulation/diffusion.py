"""
Turbulent random walk horizontal diffusion model (Task 3B).
Implements horizontal isotropic Fickian diffusion:
  sigma = sqrt(2 * Kh * dt)
  dE ~ Normal(0, sigma) [meters]
  dN ~ Normal(0, sigma) [meters]
Calculates stochastic displacements in metric horizontal coordinates using an explicit RNG.
"""

import math
from typing import Optional, Tuple, Union
import numpy as np
from ..config import DiffusionConfig


class TurbulentDiffusion:
    """Computes stochastic horizontal dispersion displacements for Lagrangian particles."""

    def __init__(self, config: Optional[DiffusionConfig] = None):
        self.config = config or DiffusionConfig()

    @property
    def diffusivity(self) -> float:
        return self.config.horizontal_diffusivity_m2_s

    @property
    def is_enabled(self) -> bool:
        return self.config.enable_stochastic_diffusion and (self.config.horizontal_diffusivity_m2_s > 0.0)

    def compute_sigma(self, dt_seconds: float) -> float:
        """
        Calculates standard deviation of Gaussian displacement per axis:
        sigma = sqrt(2 * Kh * dt)
        """
        if not self.is_enabled or dt_seconds <= 0.0:
            return 0.0
        return math.sqrt(2.0 * self.config.horizontal_diffusivity_m2_s * dt_seconds)

    def random_displacement_single(
        self,
        dt_seconds: float,
        rng: Optional[Union[np.random.Generator, np.random.RandomState]] = None
    ) -> Tuple[float, float]:
        """
        Generates single particle stochastic horizontal displacement (dE, dN) in meters.
        """
        sigma = self.compute_sigma(dt_seconds)
        if sigma <= 0.0:
            return 0.0, 0.0

        if rng is not None:
            if isinstance(rng, np.random.Generator):
                dE = float(rng.normal(0.0, sigma))
                dN = float(rng.normal(0.0, sigma))
            else:
                dE = float(rng.normal(0.0, sigma))
                dN = float(rng.normal(0.0, sigma))
        else:
            # Fallback to local default generator
            local_rng = np.random.default_rng()
            dE = float(local_rng.normal(0.0, sigma))
            dN = float(local_rng.normal(0.0, sigma))

        return dE, dN

    def random_displacement_meters(
        self,
        dt_seconds: float,
        num_particles: int,
        rng: Optional[Union[np.random.Generator, np.random.RandomState]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates Brownian displacement vectors for an ensemble of particles.
        Returns:
            (dE, dN) arrays of displacements in meters.
        """
        if num_particles <= 0 or not self.is_enabled or dt_seconds <= 0.0:
            return np.zeros(num_particles), np.zeros(num_particles)

        sigma = self.compute_sigma(dt_seconds)
        if sigma <= 0.0:
            return np.zeros(num_particles), np.zeros(num_particles)

        if rng is not None:
            if isinstance(rng, np.random.Generator):
                dE = rng.normal(0.0, sigma, num_particles)
                dN = rng.normal(0.0, sigma, num_particles)
            else:
                dE = rng.normal(0.0, sigma, num_particles)
                dN = rng.normal(0.0, sigma, num_particles)
        else:
            local_rng = np.random.default_rng()
            dE = local_rng.normal(0.0, sigma, num_particles)
            dN = local_rng.normal(0.0, sigma, num_particles)

        return dE, dN
