"""
Spatio-temporal geometry, geodetic distance, and spatial candidate filtering for Feature 3.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Point as ShapelyPoint, Polygon as ShapelyPolygon, LineString as ShapelyLineString, shape as shapely_shape
from shapely.ops import nearest_points

from .schemas import AISRecord, Feature2OriginContext, LatLon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two geographic coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    return 2.0 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the initial forward geodetic bearing from point 1 to point 2 in degrees (0–360).
    """
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlon = lon2_r - lon1_r

    y = math.sin(dlon) * math.cos(lat2_r)
    x = (math.cos(lat1_r) * math.sin(lat2_r) -
         math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon))
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def smallest_angle_difference(angle1: float, angle2: float) -> float:
    """Calculates smallest angular difference in degrees between two directions [0, 180]."""
    diff = abs(angle1 - angle2) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def point_to_segment_distance_km(
    p_lat: float, p_lon: float,
    a_lat: float, a_lon: float,
    b_lat: float, b_lon: float
) -> Tuple[float, float]:
    """
    Calculates minimum distance from a point P to a great-circle segment [A, B] in km.
    Returns (min_distance_km, projection_ratio_t) where t in [0, 1] is along segment AB.
    """
    d_a = haversine_km(p_lat, p_lon, a_lat, a_lon)
    d_b = haversine_km(p_lat, p_lon, b_lat, b_lon)
    d_ab = haversine_km(a_lat, a_lon, b_lat, b_lon)

    if d_ab < 1e-4:
        return d_a, 0.0

    # Planar approximation for local projection parameter t
    cos_lat = math.cos(math.radians((a_lat + b_lat + p_lat) / 3.0))
    dx = (b_lon - a_lon) * cos_lat
    dy = b_lat - a_lat
    
    px = (p_lon - a_lon) * cos_lat
    py = p_lat - a_lat
    
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return d_a, 0.0
        
    t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
    
    proj_lat = a_lat + t * (b_lat - a_lat)
    proj_lon = a_lon + t * (b_lon - a_lon)
    
    min_dist = haversine_km(p_lat, p_lon, proj_lat, proj_lon)
    return min_dist, t


def is_point_in_polygon(lat: float, lon: float, polygon_geojson: Optional[Dict[str, Any]]) -> bool:
    """Checks whether a lat/lon coordinate falls inside a GeoJSON Polygon / MultiPolygon."""
    if not polygon_geojson:
        return False
    try:
        poly = shapely_shape(polygon_geojson)
        pt = ShapelyPoint(lon, lat)  # Shapely coordinates are (x=lon, y=lat)
        return bool(poly.contains(pt))
    except Exception:
        return False


def distance_to_uncertainty_zone_km(
    lat: float,
    lon: float,
    origin_lat: float,
    origin_lon: float,
    uncertainty_radius_km: float,
    uncertainty_polygon_geojson: Optional[Dict[str, Any]] = None
) -> float:
    """
    Calculates shortest geodetic distance from a point to the Feature 2 uncertainty zone.
    Returns 0.0 if the point is inside the uncertainty polygon or within the uncertainty radius.
    """
    if uncertainty_polygon_geojson:
        try:
            poly = shapely_shape(uncertainty_polygon_geojson)
            pt = ShapelyPoint(lon, lat)
            if poly.contains(pt):
                return 0.0
            nearest_geom = nearest_points(poly, pt)[0]
            boundary_lon, boundary_lat = nearest_geom.x, nearest_geom.y
            return haversine_km(lat, lon, boundary_lat, boundary_lon)
        except Exception:
            pass

    dist_to_center = haversine_km(lat, lon, origin_lat, origin_lon)
    return max(0.0, dist_to_center - uncertainty_radius_km)


def point_to_linestring_distance_km(
    lat: float,
    lon: float,
    linestring_geojson: Optional[Dict[str, Any]]
) -> float:
    """
    Calculates minimum distance from a point to a GeoJSON LineString in kilometers.
    Used for reverse drift corridor proximity.
    """
    if not linestring_geojson or not linestring_geojson.get("coordinates"):
        return 9999.0

    coords = linestring_geojson["coordinates"]
    if len(coords) == 1:
        return haversine_km(lat, lon, coords[0][1], coords[0][0])

    min_dist = 9999.0
    for i in range(len(coords) - 1):
        a_lon, a_lat = coords[i][0], coords[i][1]
        b_lon, b_lat = coords[i + 1][0], coords[i + 1][1]
        d, _ = point_to_segment_distance_km(lat, lon, a_lat, a_lon, b_lat, b_lon)
        if d < min_dist:
            min_dist = d
    return min_dist
