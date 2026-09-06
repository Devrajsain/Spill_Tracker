"""
Spatial algorithms for polygon operations and Lagrangian particle seeding.
"""

import math
from typing import Any, List, Tuple, Optional, Union
import numpy as np
from ..exceptions import InvalidInputGeometryError
from .coordinates import EARTH_RADIUS_KM, haversine_distance_km


def is_point_in_polygon(x: float, y: float, polygon_ring: List[List[float]]) -> bool:
    """
    Standard ray-casting algorithm to test whether a point (x, y) = (lon, lat)
    is inside a 2D closed polygon ring.
    polygon_ring is a list of [lon, lat] pairs.
    """
    inside = False
    n = len(polygon_ring)
    if n < 3:
        return False

    j = n - 1
    for i in range(n):
        xi, yi = polygon_ring[i][0], polygon_ring[i][1]
        xj, yj = polygon_ring[j][0], polygon_ring[j][1]

        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i

    return inside


def compute_polygon_centroid(coordinates: List[List[float]]) -> Tuple[float, float]:
    """
    Computes arithmetic mean centroid (lat, lon) from a ring of [lon, lat] coordinates.
    """
    if not coordinates:
        return 0.0, 0.0
    lons = [pt[0] for pt in coordinates]
    lats = [pt[1] for pt in coordinates]
    return float(np.mean(lats)), float(np.mean(lons))


def sample_particles_in_polygon(
    polygon_coords: List[List[float]],
    num_particles: int = 500,
    random_seed: Optional[int] = None
) -> List[Tuple[float, float]]:
    """
    Seeds `num_particles` uniformly across the interior of the given polygon
    using bounding-box rejection sampling.
    Returns list of (lat, lon) tuples.
    """
    rng = np.random.RandomState(random_seed) if random_seed is not None else np.random

    lons = [p[0] for p in polygon_coords]
    lats = [p[1] for p in polygon_coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    sampled: List[Tuple[float, float]] = []
    max_attempts = num_particles * 50
    attempts = 0

    while len(sampled) < num_particles and attempts < max_attempts:
        batch_size = max((num_particles - len(sampled)) * 3, 50)
        cand_lons = rng.uniform(min_lon, max_lon, batch_size)
        cand_lats = rng.uniform(min_lat, max_lat, batch_size)

        for lon, lat in zip(cand_lons, cand_lats):
            if is_point_in_polygon(lon, lat, polygon_coords):
                sampled.append((float(lat), float(lon)))
                if len(sampled) >= num_particles:
                    break
        attempts += batch_size

    # Fallback if sampling fails (e.g. self-intersecting or degenerate polygon): place at centroid
    if len(sampled) < num_particles:
        c_lat, c_lon = compute_polygon_centroid(polygon_coords)
        while len(sampled) < num_particles:
            sampled.append((c_lat, c_lon))

    return sampled


def validate_polygon_geometry(coordinates: Any) -> List[List[List[float]]]:
    """
    Strictly validates GeoJSON Polygon coordinates structure:
    - Coordinates must be a list containing at least one linear ring.
    - Outer ring must have >= 4 coordinates (at least 3 distinct vertices + 1 closing vertex).
    - Coordinates must be finite numbers in correct GeoJSON [longitude, latitude] order.
    - Longitude must be in [-180.0, 180.0] (or [0.0, 360.0]).
    - Latitude must be in [-90.0, 90.0].
    - Linear ring must be closed (first coordinate equals last coordinate).

    Returns:
        Validated nested coordinate list.

    Raises:
        InvalidInputGeometryError: if any validation condition fails.
    """
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) == 0:
        raise InvalidInputGeometryError("Polygon coordinates must be a non-empty list of linear rings.")

    outer_ring = coordinates[0]
    if not isinstance(outer_ring, (list, tuple)) or len(outer_ring) < 4:
        raise InvalidInputGeometryError(
            f"Polygon exterior linear ring must contain at least 4 coordinates (got {len(outer_ring) if isinstance(outer_ring, (list, tuple)) else 0})."
        )

    validated_ring: List[List[float]] = []
    for idx, pt in enumerate(outer_ring):
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            raise InvalidInputGeometryError(f"Coordinate at vertex {idx} must be a pair [lon, lat].")

        try:
            lon = float(pt[0])
            lat = float(pt[1])
        except (ValueError, TypeError) as e:
            raise InvalidInputGeometryError(f"Coordinate vertex {idx} contains non-numeric value: {pt}") from e

        if not math.isfinite(lon) or not math.isfinite(lat):
            raise InvalidInputGeometryError(f"Coordinate vertex {idx} contains non-finite value: [{lon}, {lat}].")

        # GeoJSON coordinate order: [longitude, latitude]
        if lat < -90.0 or lat > 90.0:
            raise InvalidInputGeometryError(
                f"Latitude {lat} at vertex {idx} is outside valid range [-90, 90]. "
                "Ensure coordinates follow standard GeoJSON [longitude, latitude] order."
            )
        if lon < -180.0 or lon > 360.0:
            raise InvalidInputGeometryError(
                f"Longitude {lon} at vertex {idx} is outside valid range [-180, 180] / [0, 360]."
            )

        validated_ring.append([lon, lat])

    # Check closure (first point equals last point)
    first_pt = validated_ring[0]
    last_pt = validated_ring[-1]
    if abs(first_pt[0] - last_pt[0]) > 1e-6 or abs(first_pt[1] - last_pt[1]) > 1e-6:
        raise InvalidInputGeometryError(
            f"Polygon linear ring is not closed: first vertex [{first_pt[0]}, {first_pt[1]}] "
            f"does not match last vertex [{last_pt[0]}, {last_pt[1]}]."
        )

    # Check at least 3 distinct vertices
    distinct_pts = set((round(p[0], 7), round(p[1], 7)) for p in validated_ring[:-1])
    if len(distinct_pts) < 3:
        raise InvalidInputGeometryError(
            f"Polygon linear ring must contain at least 3 distinct vertices (found {len(distinct_pts)})."
        )

    return [validated_ring]


def haversine_polygon_area_km2(polygon_coords: List[List[float]]) -> float:
    """
    Computes the surface area in square kilometers of a spherical polygon ring
    given in [longitude, latitude] coordinates using Girard's theorem / Green's theorem on sphere.
    """
    if len(polygon_coords) < 4:
        return 0.0

    n = len(polygon_coords)
    # Convert lon/lat to radians
    coords_rad = [(math.radians(pt[0]), math.radians(pt[1])) for pt in polygon_coords]

    total_sum = 0.0
    for i in range(n - 1):
        lon1, lat1 = coords_rad[i]
        lon2, lat2 = coords_rad[i + 1]
        total_sum += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))

    area_km2 = abs(total_sum * (EARTH_RADIUS_KM ** 2) / 2.0)
    # Cap area to realistic slick bounds if numerical wrap
    if area_km2 > 4.0 * math.pi * (EARTH_RADIUS_KM ** 2):
        area_km2 = 0.0
    return round(float(area_km2), 4)


def haversine_polygon_perimeter_km(polygon_coords: List[List[float]]) -> float:
    """
    Computes the perimeter length in kilometers of a closed polygon ring
    given in [longitude, latitude] coordinates.
    """
    if len(polygon_coords) < 2:
        return 0.0

    total_dist = 0.0
    for i in range(len(polygon_coords) - 1):
        lon1, lat1 = polygon_coords[i][0], polygon_coords[i][1]
        lon2, lat2 = polygon_coords[i + 1][0], polygon_coords[i + 1][1]
        total_dist += haversine_distance_km(lat1, lon1, lat2, lon2)

    return round(float(total_dist), 4)
