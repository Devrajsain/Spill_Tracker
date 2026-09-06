"""
Coordinate conversion and geodesic calculation helpers.
"""

import math
from typing import Tuple, List

# Earth parameters (WGS84 approx mean radius)
EARTH_RADIUS_METERS = 6371008.8
EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two points in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def meters_to_lat_deg(delta_y_meters: float) -> float:
    """Converts a north-south displacement in meters to delta latitude degrees."""
    return delta_y_meters / (EARTH_RADIUS_METERS * (math.pi / 180.0))


def meters_to_lon_deg(delta_x_meters: float, at_latitude: float) -> float:
    """Converts an east-west displacement in meters to delta longitude degrees at a given latitude."""
    lat_rad = math.radians(at_latitude)
    cos_lat = max(math.cos(lat_rad), 1e-6)
    return delta_x_meters / (EARTH_RADIUS_METERS * cos_lat * (math.pi / 180.0))


def lat_lon_to_meters(d_lat: float, d_lon: float, at_latitude: float) -> Tuple[float, float]:
    """Converts delta lat/lon in degrees to approximate delta meters (dx, dy)."""
    lat_rad = math.radians(at_latitude)
    cos_lat = max(math.cos(lat_rad), 1e-6)
    dy = d_lat * (EARTH_RADIUS_METERS * (math.pi / 180.0))
    dx = d_lon * (EARTH_RADIUS_METERS * cos_lat * (math.pi / 180.0))
    return dx, dy


def compute_bounding_box(coords: List[Tuple[float, float]], buffer_km: float = 0.0) -> Tuple[float, float, float, float]:
    """
    Computes (min_lat, max_lat, min_lon, max_lon) for a list of (lat, lon) coordinates,
    with an optional buffer padding in km.
    """
    if not coords:
        return 0.0, 0.0, 0.0, 0.0

    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    if buffer_km > 0:
        d_lat = meters_to_lat_deg(buffer_km * 1000.0)
        mean_lat = (min_lat + max_lat) / 2.0
        d_lon = meters_to_lon_deg(buffer_km * 1000.0, mean_lat)
        min_lat -= d_lat
        max_lat += d_lat
        min_lon -= d_lon
        max_lon += d_lon

    return min_lat, max_lat, min_lon, max_lon
