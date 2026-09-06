"""
Geographic and spatial calculation utilities for Feature 2.
"""

from .coordinates import (
    haversine_distance_km,
    meters_to_lat_deg,
    meters_to_lon_deg,
    lat_lon_to_meters,
    compute_bounding_box,
)
from .spatial import (
    is_point_in_polygon,
    sample_particles_in_polygon,
    compute_polygon_centroid,
)

__all__ = [
    "haversine_distance_km",
    "meters_to_lat_deg",
    "meters_to_lon_deg",
    "lat_lon_to_meters",
    "compute_bounding_box",
    "is_point_in_polygon",
    "sample_particles_in_polygon",
    "compute_polygon_centroid",
]
