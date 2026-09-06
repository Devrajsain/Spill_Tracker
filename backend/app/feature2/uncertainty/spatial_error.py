"""
Spatial uncertainty quantification using empirical particle dispersion covariance.
Computes 95% confidence dispersion ellipses and GeoJSON boundary polygons dynamically
from particle ensembles, avoiding hardcoded uncertainty radii.
"""

import math
from typing import Any, List, Tuple
import numpy as np
from ..schemas.output_schema import SpatialUncertainty
from ..schemas.input_schema import GeoJSONGeometry
from ..geo.coordinates import meters_to_lat_deg, meters_to_lon_deg, EARTH_RADIUS_KM, haversine_distance_km


class SpatialUncertaintyEstimator:
    """Calculates dynamic spatial dispersion uncertainty from ensemble particle distributions."""

    @staticmethod
    def compute_dispersion_ellipse(
        particle_coords: List[Tuple[float, float]],
        confidence_level: float = 0.95
    ) -> SpatialUncertainty:
        """
        Calculates semi-major axis, semi-minor axis, orientation angle, and polygon
        from the spatial covariance matrix of particle positions (lat, lon).
        """
        if len(particle_coords) == 0:
            poly = GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]]
            )
            return SpatialUncertainty(
                semi_major_axis_km=0.0,
                semi_minor_axis_km=0.0,
                orientation_deg=0.0,
                uncertainty_polygon=poly
            )

        if len(particle_coords) == 1:
            mean_lat = particle_coords[0][0]
            mean_lon = particle_coords[0][1]
            poly = GeoJSONGeometry(
                type="Polygon",
                coordinates=[[[mean_lon, mean_lat], [mean_lon, mean_lat], [mean_lon, mean_lat], [mean_lon, mean_lat]]]
            )
            return SpatialUncertainty(
                semi_major_axis_km=0.0,
                semi_minor_axis_km=0.0,
                orientation_deg=0.0,
                uncertainty_polygon=poly
            )

        if len(particle_coords) == 2:
            pt1, pt2 = particle_coords[0], particle_coords[1]
            dist_km = haversine_distance_km(pt1[0], pt1[1], pt2[0], pt2[1])
            mean_lat = (pt1[0] + pt2[0]) / 2.0
            mean_lon = (pt1[1] + pt2[1]) / 2.0
            semi_major = max(dist_km / 2.0, 0.01)
            semi_minor = 0.01
            d_lat = pt2[0] - pt1[0]
            d_lon = (pt2[1] - pt1[1]) * math.cos(math.radians(mean_lat))
            angle_deg = float(math.degrees(math.atan2(d_lon, d_lat)) % 360.0)
            return SpatialUncertaintyEstimator.from_parameters(
                mean_lat=mean_lat,
                mean_lon=mean_lon,
                semi_major_km=round(semi_major, 3),
                semi_minor_km=round(semi_minor, 3),
                orientation_deg=round(angle_deg, 2)
            )

        lats = np.array([pt[0] for pt in particle_coords])
        lons = np.array([pt[1] for pt in particle_coords])

        mean_lat = float(np.mean(lats))
        mean_lon = float(np.mean(lons))

        # Convert degree offsets to approximate km displacements
        d_lat_km = (lats - mean_lat) * (math.pi / 180.0) * EARTH_RADIUS_KM
        cos_lat = max(math.cos(math.radians(mean_lat)), 1e-6)
        d_lon_km = (lons - mean_lon) * (math.pi / 180.0) * EARTH_RADIUS_KM * cos_lat

        pts_km = np.column_stack([d_lon_km, d_lat_km])
        cov = np.cov(pts_km, rowvar=False)

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Sort eigenvalues descending
        order = eigenvalues.argsort()[::-1]
        eigenvalues = np.maximum(eigenvalues[order], 1e-6)
        eigenvectors = eigenvectors[:, order]

        # Exact chi-square quantile for 2 DOF: chi2 = -2 * ln(1 - p)
        eff_conf = min(max(float(confidence_level), 0.01), 0.9999)
        chi2_val = -2.0 * math.log(1.0 - eff_conf)
        semi_major_km = float(math.sqrt(chi2_val * eigenvalues[0]))
        semi_minor_km = float(math.sqrt(chi2_val * eigenvalues[1]))

        # Orientation of the semi-major axis in degrees clockwise from North
        angle_rad = math.atan2(eigenvectors[0, 0], eigenvectors[1, 0])
        orientation_deg = float(math.degrees(angle_rad) % 360.0)

        # Generate ellipse boundary polygon points (36 vertices)
        ellipse_points: List[List[float]] = []
        num_vertices = 36
        for i in range(num_vertices + 1):
            theta = 2.0 * math.pi * i / num_vertices
            # Local coordinates in principal axes
            x_local = semi_major_km * math.cos(theta)
            y_local = semi_minor_km * math.sin(theta)

            # Rotate to geographic orientation
            x_rot = eigenvectors[0, 0] * x_local + eigenvectors[0, 1] * y_local
            y_rot = eigenvectors[1, 0] * x_local + eigenvectors[1, 1] * y_local

            # Convert back to lat/lon degrees
            pt_lat = mean_lat + meters_to_lat_deg(y_rot * 1000.0)
            pt_lon = mean_lon + meters_to_lon_deg(x_rot * 1000.0, mean_lat)
            ellipse_points.append([round(pt_lon, 6), round(pt_lat, 6)])

        polygon_geom = GeoJSONGeometry(
            type="Polygon",
            coordinates=[ellipse_points]
        )

        return SpatialUncertainty(
            semi_major_axis_km=round(semi_major_km, 3),
            semi_minor_axis_km=round(semi_minor_km, 3),
            orientation_deg=round(orientation_deg, 2),
            uncertainty_polygon=polygon_geom
        )

    @classmethod
    def from_parameters(
        cls,
        mean_lat: float,
        mean_lon: float,
        semi_major_km: float,
        semi_minor_km: float,
        orientation_deg: float = 0.0,
        num_vertices: int = 36,
    ) -> SpatialUncertainty:
        """
        Constructs a SpatialUncertainty object with a GeoJSON polygon from explicit axes.
        """
        ellipse_points: List[List[float]] = []
        angle_rad = math.radians(orientation_deg)
        cos_ang = math.cos(angle_rad)
        sin_ang = math.sin(angle_rad)

        for i in range(num_vertices + 1):
            theta = 2.0 * math.pi * i / num_vertices
            x_loc = semi_major_km * math.cos(theta)
            y_loc = semi_minor_km * math.sin(theta)

            x_rot = x_loc * cos_ang - y_loc * sin_ang
            y_rot = x_loc * sin_ang + y_loc * cos_ang

            pt_lat = mean_lat + meters_to_lat_deg(y_rot * 1000.0)
            pt_lon = mean_lon + meters_to_lon_deg(x_rot * 1000.0, mean_lat)
            ellipse_points.append([round(pt_lon, 6), round(pt_lat, 6)])

        polygon_geom = GeoJSONGeometry(
            type="Polygon",
            coordinates=[ellipse_points]
        )

        return SpatialUncertainty(
            semi_major_axis_km=round(max(semi_major_km, 0.001), 3),
            semi_minor_axis_km=round(max(semi_minor_km, 0.001), 3),
            orientation_deg=round(orientation_deg, 2),
            uncertainty_polygon=polygon_geom
        )


def compute_ensemble_step_statistics(
    timestamp: Any,
    particles: List[Any],
    earth_radius_m: float = 6371008.8
) -> Any:
    """
    Computes ensemble-derived spatial dispersion spread and 2x2 covariance in local horizontal meters.
    Covariance matrix is defined in physical meter offsets:
      [[var_E, cov_EN],
       [cov_EN, var_N]]
    Note: Represents empirical ensemble dispersion, NOT a calibrated frequentist probability.
    """
    from ..schemas.simulation_schema import EnsembleStepStatistics

    # Filter active particles
    active_particles = [
        p for p in particles
        if getattr(p, "is_active", getattr(p, "active", True)) and not getattr(p, "beached", False)
    ]

    if not active_particles:
        return EnsembleStepStatistics(
            timestamp=timestamp,
            active_particle_count=0,
            mean_latitude=0.0,
            mean_longitude=0.0,
            variance_east_m2=0.0,
            variance_north_m2=0.0,
            covariance_en_m2=0.0,
            covariance_matrix_m2=[[0.0, 0.0], [0.0, 0.0]],
            spread_radius_m=0.0
        )

    lats = np.array([p.latitude for p in active_particles], dtype=float)
    lons = np.array([p.longitude for p in active_particles], dtype=float)

    mean_lat = float(np.mean(lats))
    mean_lon = float(np.mean(lons))

    if len(active_particles) < 2:
        return EnsembleStepStatistics(
            timestamp=timestamp,
            active_particle_count=1,
            mean_latitude=mean_lat,
            mean_longitude=mean_lon,
            variance_east_m2=0.0,
            variance_north_m2=0.0,
            covariance_en_m2=0.0,
            covariance_matrix_m2=[[0.0, 0.0], [0.0, 0.0]],
            spread_radius_m=0.0
        )

    # Convert angular offsets to local metric East and North displacements
    mean_lat_rad = math.radians(mean_lat)
    cos_lat = max(math.cos(mean_lat_rad), 1e-6)

    # dE in meters, dN in meters
    dE = (lons - mean_lon) * (math.pi / 180.0) * earth_radius_m * cos_lat
    dN = (lats - mean_lat) * (math.pi / 180.0) * earth_radius_m

    pts_m = np.column_stack([dE, dN])
    cov_matrix = np.cov(pts_m, rowvar=False)

    var_e = float(cov_matrix[0, 0])
    var_n = float(cov_matrix[1, 1])
    cov_en = float(cov_matrix[0, 1])
    spread_r = float(math.sqrt(max(var_e + var_n, 0.0)))

    return EnsembleStepStatistics(
        timestamp=timestamp,
        active_particle_count=len(active_particles),
        mean_latitude=mean_lat,
        mean_longitude=mean_lon,
        variance_east_m2=var_e,
        variance_north_m2=var_n,
        covariance_en_m2=cov_en,
        covariance_matrix_m2=[
            [var_e, cov_en],
            [cov_en, var_n]
        ],
        spread_radius_m=spread_r
    )

