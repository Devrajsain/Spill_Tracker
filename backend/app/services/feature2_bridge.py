"""
Feature 1 to Feature 2 Bridge Service.

Translates Feature 1 SAR oil spill detection outputs into the canonical
RFC 7946 GeoJSON FeatureCollection format required by Feature 2
(backward origin tracing and forward trajectory forecasting).

Mapping Specification:
  Feature 1: case_id / spill identifier -> Feature 2: properties.spill_id
  Feature 1: detection_timestamp        -> Feature 2: properties.observation_time (normalized to ISO-8601 with tz)
  Feature 1: polygon_geojson            -> Feature 2: geometry
  Feature 1: center_lat / center_lon    -> Feature 2: properties.centroid.latitude / longitude
  Feature 1: area_km2                   -> Feature 2: properties.area_sq_km
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Union
from dateutil import parser as dateutil_parser


def normalize_detection_timestamp(timestamp_input: Union[str, datetime]) -> str:
    """
    Normalizes Feature 1 detection timestamp to strict ISO-8601 with explicit UTC timezone offset.

    Examples:
        '2026-09-02 04:18:00 UTC' -> '2026-09-02T04:18:00+00:00'
        '2026-09-02T04:18:00Z'     -> '2026-09-02T04:18:00+00:00'
        '2026-09-02 04:18:00'      -> '2026-09-02T04:18:00+00:00'
        datetime(2026, 9, 2, 4, 18)-> '2026-09-02T04:18:00+00:00'
    """
    if isinstance(timestamp_input, datetime):
        dt = timestamp_input
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()

    if not isinstance(timestamp_input, str):
        raise ValueError(f"Unsupported timestamp type: {type(timestamp_input)}. Expected str or datetime.")

    cleaned = timestamp_input.strip()
    if not cleaned:
        raise ValueError("Empty timestamp provided.")

    # Match common Feature 1 pattern: 'YYYY-MM-DD HH:MM:SS UTC'
    utc_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*UTC$", re.IGNORECASE)
    match = utc_pattern.match(cleaned)
    if match:
        iso_str = f"{match.group(1)}T{match.group(2)}+00:00"
        return iso_str

    # General parsing with dateutil
    try:
        dt = dateutil_parser.parse(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    except Exception as exc:
        raise ValueError(f"Unable to parse timestamp '{timestamp_input}' into ISO-8601: {exc}") from exc


def calculate_polygon_centroid(coordinates: List[List[List[float]]]) -> Dict[str, float]:
    """Calculates geographic centroid (lat, lon) from polygon outer ring coordinates [[lon, lat], ...]."""
    if not coordinates or not coordinates[0]:
        raise ValueError("Invalid polygon coordinates for centroid calculation.")

    ring = coordinates[0]
    # If closed polygon, ignore identical last vertex in arithmetic mean
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not pts:
        pts = ring

    avg_lon = sum(p[0] for p in pts) / len(pts)
    avg_lat = sum(p[1] for p in pts) / len(pts)
    return {"latitude": round(avg_lat, 6), "longitude": round(avg_lon, 6)}


def feature1_to_feature2_geojson(
    detection_output: Dict[str, Any],
    case_id: Optional[str] = None,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Converts Feature 1 detection output into Feature 2 GeoJSON FeatureCollection format.

    Args:
        detection_output: Output dictionary from Feature 1 detection service or database record.
        case_id: Optional case identifier or spill id.
        center_lat: Optional center latitude override.
        center_lon: Optional center longitude override.

    Returns:
        RFC 7946 compliant GeoJSON FeatureCollection ready for Feature 2 consumption.
    """
    # 1. Resolve spill identifier
    spill_id = (
        case_id or
        detection_output.get("case_id") or
        detection_output.get("spill_id") or
        detection_output.get("id") or
        "spill-unknown"
    )

    # 2. Resolve & normalize observation timestamp
    raw_timestamp = (
        detection_output.get("detection_timestamp") or
        detection_output.get("observation_time") or
        detection_output.get("timestamp") or
        detection_output.get("origin_timestamp")
    )
    if not raw_timestamp:
        raise ValueError("Feature 1 detection output must contain a detection_timestamp.")
    observation_time_iso = normalize_detection_timestamp(raw_timestamp)

    # 3. Resolve geometry
    geometry = detection_output.get("polygon_geojson") or detection_output.get("geometry")
    if not geometry or not isinstance(geometry, dict):
        raise ValueError("Feature 1 detection output must contain a valid polygon_geojson dictionary.")

    # 4. Resolve centroid
    if detection_output.get("spill_latitude") is not None and detection_output.get("spill_longitude") is not None:
        centroid = {
            "latitude": float(detection_output["spill_latitude"]),
            "longitude": float(detection_output["spill_longitude"]),
        }
    elif center_lat is not None and center_lon is not None:
        centroid = {"latitude": float(center_lat), "longitude": float(center_lon)}
    elif "center_latitude" in detection_output and "center_longitude" in detection_output:
        centroid = {
            "latitude": float(detection_output["center_latitude"]),
            "longitude": float(detection_output["center_longitude"]),
        }
    elif "centroid" in detection_output and isinstance(detection_output["centroid"], dict):
        c = detection_output["centroid"]
        lat = c.get("latitude", c.get("lat"))
        lon = c.get("longitude", c.get("lon"))
        centroid = {"latitude": float(lat), "longitude": float(lon)}
    elif geometry.get("type") == "Polygon" and geometry.get("coordinates"):
        centroid = calculate_polygon_centroid(geometry["coordinates"])
    else:
        raise ValueError("Cannot derive centroid coordinates for Feature 2 from detection output.")

    # 5. Resolve surface area
    area_sq_km = (
        detection_output.get("area_km2") or
        detection_output.get("area_sq_km") or
        0.0
    )

    # 6. Assemble properties preserving metadata
    perimeter_km = (
        detection_output.get("perimeter_km") or
        0.0
    )

    properties: Dict[str, Any] = {
        "spill_id": str(spill_id),
        "observation_time": observation_time_iso,
        "centroid": centroid,
        "area_sq_km": float(area_sq_km),
        "perimeter_km": float(perimeter_km),
    }

    # Pass through additional detection metadata if available
    for key in (
        "confidence_score",
        "confidence_label",
        "length_km",
        "width_km",
        "est_volume_bbl",
        "satellite_source",
    ):
        if key in detection_output:
            properties[key] = detection_output[key]

    feature = {
        "type": "Feature",
        "id": str(spill_id),
        "geometry": geometry,
        "properties": properties,
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
    }
