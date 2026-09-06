"""
Relative evidence / confidence scoring for candidate origin clusters (Task 3D / Task 9).
Active scoring components:
  1. Convergence / compactness score (S_conv): spatial compactness of backward particle ensemble.
  2. Trajectory consistency score (S_traj): particle continuity and valid advection history.
  3. Coverage score (S_cov): fraction of particles remaining within environmental dataset boundaries.

DEFERRED / FUTURE NON-ACTIVE EXTENSIONS:
  The following factors are NOT modeled and are NOT part of candidate scoring:
  - Infrastructure proximity (offshore platforms, wells, pipelines, terminals)
  - AIS shipping traffic / vessel tracking density
  - Coastline beaching / shoreline interaction
  - Bathymetry / shallow-water bottom friction

Adheres strictly to the scientific principle:
Confidence score reflects model evidence and trajectory support,
NOT a calibrated frequentist or Bayesian probability.
"""

from typing import Any, Dict, Optional
from ...config import BackwardTracingConfig, default_settings


class OriginConfidenceScorer:
    """
    Computes normalized relative evidence scores [0.0, 1.0] evaluating how strongly
    backward trajectory convergence, continuity, and environmental coverage support
    a candidate origin region.
    """

    def __init__(self, config: Optional[BackwardTracingConfig] = None):
        self.config = config or default_settings.backward

    def compute_convergence_score(
        self,
        spread_radius_km: float,
        scale_km: Optional[float] = None,
    ) -> float:
        """
        Calculates spatial convergence score:
        S_conv = 1.0 / (1.0 + spread_radius_km / scale_km)
        Compact cloud -> score near 1.0; dispersed cloud -> lower score.
        """
        eff_scale = scale_km if scale_km is not None else self.config.convergence_scale_km
        if eff_scale <= 0.0:
            eff_scale = 5.0

        score = 1.0 / (1.0 + max(spread_radius_km, 0.0) / eff_scale)
        return float(min(max(score, 0.0), 1.0))

    def compute_trajectory_score(
        self,
        active_particle_count: int,
        total_particle_count: int,
        cluster_fraction: float = 1.0,
    ) -> float:
        """
        Calculates trajectory consistency and cluster support score.
        Evaluates the proportion of particles maintaining coherent valid trajectories.
        """
        if total_particle_count <= 0:
            return 0.0
        active_ratio = min(max(active_particle_count / float(total_particle_count), 0.0), 1.0)
        eff_cluster = min(max(cluster_fraction, 0.0), 1.0)
        return float(active_ratio * eff_cluster)

    def compute_coverage_score(
        self,
        active_particle_count: int,
        total_particle_count: int,
    ) -> float:
        """
        Calculates environmental data coverage score:
        S_coverage = active_particle_count / total_particle_count.
        Measures the fraction of particles remaining within environmental dataset boundaries.
        """
        if total_particle_count <= 0:
            return 0.0
        return float(min(max(active_particle_count / float(total_particle_count), 0.0), 1.0))

    def calculate_candidate_score(
        self,
        convergence_score: float,
        trajectory_score: float,
        coverage_score: float,
        weight_convergence: Optional[float] = None,
        weight_trajectory: Optional[float] = None,
        weight_coverage: Optional[float] = None,
    ) -> float:
        """
        Combines evidence components into a unified weighted candidate score.
        Score = (w_conv * S_conv + w_traj * S_traj + w_cov * S_cov) / sum(weights)
        """
        w_conv = weight_convergence if weight_convergence is not None else self.config.weight_convergence
        w_traj = weight_trajectory if weight_trajectory is not None else self.config.weight_trajectory
        w_cov = weight_coverage if weight_coverage is not None else self.config.weight_coverage

        total_weight = w_conv + w_traj + w_cov
        if total_weight <= 0.0:
            total_weight = 1.0

        score = (w_conv * convergence_score + w_traj * trajectory_score + w_cov * coverage_score) / total_weight
        return float(min(max(score, 0.0), 1.0))

    @staticmethod
    def calculate_score(
        particle_support_ratio: float,
        spatial_compactness_score: float,
        environmental_consistency: float,
    ) -> float:
        """Compatibility method for legacy signatures."""
        score = (
            0.50 * particle_support_ratio +
            0.30 * spatial_compactness_score +
            0.20 * environmental_consistency
        )
        return float(min(max(score, 0.0), 1.0))
