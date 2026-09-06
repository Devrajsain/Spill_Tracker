"""
Spatial convergence clustering for backtracked Lagrangian trajectory endpoints (Task 3D).
Performs DBSCAN-style clustering in local physical meter coordinates:
  - Euclidean metric in meters
  - Configurable epsilon (km -> m)
  - Configurable min_samples
  - Zero degree-space distortion
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from ...schemas.simulation_schema import Particle, ParticleState, ParticleEnsemble
from ...config import BackwardTracingConfig, default_settings
from ...geo.coordinates import (
    EARTH_RADIUS_KM,
    meters_to_lat_deg,
    meters_to_lon_deg,
)


def metric_dbscan(
    points_meters: np.ndarray,
    eps_meters: float,
    min_samples: int = 3,
) -> np.ndarray:
    """
    Pure NumPy DBSCAN clustering on 2D coordinates in physical meters.
    Returns:
        labels: 1D array of cluster indices (0, 1, ...) or -1 for noise.
    """
    n_points = len(points_meters)
    if n_points == 0:
        return np.array([], dtype=int)

    # Compute pairwise Euclidean distance matrix in meters
    diff = points_meters[:, np.newaxis, :] - points_meters[np.newaxis, :, :]
    dist_matrix = np.sqrt(np.sum(diff**2, axis=-1))

    labels = np.full(n_points, -1, dtype=int)
    cluster_id = 0

    # Core point identification
    neighbors = [np.where(dist_matrix[i] <= eps_meters)[0] for i in range(n_points)]
    visited = np.zeros(n_points, dtype=bool)

    for i in range(n_points):
        if visited[i]:
            continue
        visited[i] = True

        if len(neighbors[i]) < min_samples:
            continue

        # Start new cluster
        labels[i] = cluster_id
        seed_queue = list(neighbors[i])

        q_idx = 0
        while q_idx < len(seed_queue):
            nb_idx = seed_queue[q_idx]
            q_idx += 1

            if not visited[nb_idx]:
                visited[nb_idx] = True
                if len(neighbors[nb_idx]) >= min_samples:
                    for item in neighbors[nb_idx]:
                        if item not in seed_queue:
                            seed_queue.append(item)

            if labels[nb_idx] == -1:
                labels[nb_idx] = cluster_id

        cluster_id += 1

    return labels


class ConvergenceClusterer:
    """
    Identifies high-density convergence regions from backward-tracked particle ensembles.
    Projects angular coordinates to local tangent horizontal meters and clusters via metric DBSCAN.
    """

    def __init__(self, config: Optional[BackwardTracingConfig] = None):
        self.config = config or default_settings.backward

    def cluster_particles(
        self,
        particles: List[Union[Particle, ParticleState]],
        earth_radius_m: float = 6371008.8,
        eps_km: Optional[float] = None,
        min_samples: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Clusters a set of reconstructed particle states at a candidate release timestamp.

        Args:
            particles: List of Particle or ParticleState objects at candidate release time.
            earth_radius_m: WGS84 mean radius.
            eps_km: Clustering neighborhood radius in km (defaults to config).
            min_samples: Minimum cluster points (defaults to config).

        Returns:
            List of cluster dictionaries containing centroids, metric spread, and covariance.
        """
        active_particles = [
            p for p in particles
            if getattr(p, "is_active", getattr(p, "active", True)) and not getattr(p, "beached", False)
        ]

        if not active_particles:
            return []

        lats = np.array([p.latitude for p in active_particles], dtype=float)
        lons = np.array([p.longitude for p in active_particles], dtype=float)

        mean_lat = float(np.mean(lats))
        mean_lon = float(np.mean(lons))

        # Single particle edge case
        if len(active_particles) == 1:
            return [{
                "cluster_id": 0,
                "particle_indices": [0],
                "centroid_latitude": lats[0],
                "centroid_longitude": lons[0],
                "active_count": 1,
                "cluster_fraction": 1.0,
                "variance_east_m2": 0.0,
                "variance_north_m2": 0.0,
                "covariance_en_m2": 0.0,
                "covariance_matrix_m2": [[0.0, 0.0], [0.0, 0.0]],
                "spread_radius_m": 0.0,
                "uncertainty_radius_km": 0.0,
                "semi_major_axis_km": 0.0,
                "semi_minor_axis_km": 0.0,
                "orientation_deg": 0.0,
            }]

        # Convert angular positions to local horizontal metric displacements (dE, dN)
        mean_lat_rad = math.radians(mean_lat)
        cos_lat = max(math.cos(mean_lat_rad), 1e-6)

        dE = (lons - mean_lon) * (math.pi / 180.0) * earth_radius_m * cos_lat
        dN = (lats - mean_lat) * (math.pi / 180.0) * earth_radius_m
        pts_m = np.column_stack([dE, dN])

        effective_eps_km = eps_km if eps_km is not None else self.config.convergence_cluster_eps_km
        effective_eps_m = effective_eps_km * 1000.0
        effective_min_samples = min_samples if min_samples is not None else self.config.min_cluster_samples

        labels = metric_dbscan(
            points_meters=pts_m,
            eps_meters=effective_eps_m,
            min_samples=effective_min_samples
        )

        unique_labels = [lbl for lbl in np.unique(labels) if lbl != -1]

        # If all particles are labeled as noise (or no clusters formed), fallback to single cluster
        if len(unique_labels) == 0:
            unique_labels = [0]
            labels = np.zeros(len(active_particles), dtype=int)

        clusters: List[Dict[str, Any]] = []

        for cid in sorted(unique_labels):
            indices = np.where(labels == cid)[0]
            c_lats = lats[indices]
            c_lons = lons[indices]
            c_pts_m = pts_m[indices]

            c_centroid_lat = float(np.mean(c_lats))
            c_centroid_lon = float(np.mean(c_lons))
            c_fraction = len(indices) / float(len(active_particles))

            if len(indices) > 1:
                # Recenter cluster points to cluster centroid
                c_mean_lat_rad = math.radians(c_centroid_lat)
                c_cos_lat = max(math.cos(c_mean_lat_rad), 1e-6)
                c_dE = (c_lons - c_centroid_lon) * (math.pi / 180.0) * earth_radius_m * c_cos_lat
                c_dN = (c_lats - c_centroid_lat) * (math.pi / 180.0) * earth_radius_m
                c_local_pts_m = np.column_stack([c_dE, c_dN])

                cov_matrix = np.cov(c_local_pts_m, rowvar=False)
                var_e = float(cov_matrix[0, 0])
                var_n = float(cov_matrix[1, 1])
                cov_en = float(cov_matrix[0, 1])
                spread_r_m = float(math.sqrt(max(var_e + var_n, 0.0)))

                # Eigenvalues for dispersion ellipse
                eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
                order = eigenvalues.argsort()[::-1]
                eigenvalues = np.maximum(eigenvalues[order], 1e-6)
                eigenvectors = eigenvectors[:, order]

                # 95% scale factor (~sqrt(5.991))
                semi_major_km = float(math.sqrt(5.991 * eigenvalues[0]) / 1000.0)
                semi_minor_km = float(math.sqrt(5.991 * eigenvalues[1]) / 1000.0)
                angle_rad = math.atan2(eigenvectors[0, 0], eigenvectors[1, 0])
                orientation_deg = float(math.degrees(angle_rad) % 360.0)
            else:
                var_e = 0.0
                var_n = 0.0
                cov_en = 0.0
                spread_r_m = 0.0
                semi_major_km = 0.0
                semi_minor_km = 0.0
                orientation_deg = 0.0

            clusters.append({
                "cluster_id": int(cid),
                "particle_indices": indices.tolist(),
                "centroid_latitude": c_centroid_lat,
                "centroid_longitude": c_centroid_lon,
                "active_count": len(indices),
                "cluster_fraction": c_fraction,
                "variance_east_m2": var_e,
                "variance_north_m2": var_n,
                "covariance_en_m2": cov_en,
                "covariance_matrix_m2": [
                    [var_e, cov_en],
                    [cov_en, var_n]
                ],
                "spread_radius_m": spread_r_m,
                "uncertainty_radius_km": round(spread_r_m / 1000.0, 3),
                "semi_major_axis_km": round(semi_major_km, 3),
                "semi_minor_axis_km": round(semi_minor_km, 3),
                "orientation_deg": round(orientation_deg, 2),
            })

        return clusters

    def identify_clusters(
        self,
        candidate_ensembles: List[ParticleEnsemble]
    ) -> List[Dict[str, Any]]:
        """Compatibility method for ParticleEnsemble input lists."""
        all_clusters = []
        for ensemble in candidate_ensembles:
            cls_list = self.cluster_particles(ensemble.particles)
            for c in cls_list:
                c["timestamp"] = ensemble.timestamp
                all_clusters.append(c)
        return all_clusters
