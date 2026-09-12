"""
RFC 7946 GeoJSON builder for Feature 3 AIS trajectories, gap intervals, and closest approach markers.
"""

from typing import Any, Dict, List, Optional
from .schemas import AISRecord, RawEvidenceMetrics, TrajectorySegment


def build_vessel_trajectory_geojson(
    mmsi: str,
    valid_segments: List[TrajectorySegment],
    gap_segments: List[TrajectorySegment],
    evidence: RawEvidenceMetrics,
    color: str = "#2563EB",
) -> Dict[str, Any]:
    """
    Constructs an RFC 7946 GeoJSON FeatureCollection for a single vessel.
    Includes continuous track LineStrings, AIS gap LineStrings, closest approach Point,
    and interpolated origin position Point.
    """
    features: List[Dict[str, Any]] = []

    # 1. Continuous track segments
    for idx, seg in enumerate(valid_segments):
        if not seg.points or len(seg.points) < 2:
            continue
        coords = [[round(p.longitude, 6), round(p.latitude, 6)] for p in seg.points]
        features.append({
            "type": "Feature",
            "id": f"{mmsi}-track-{idx}",
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "properties": {
                "feature_type": "trajectory",
                "mmsi": mmsi,
                "segment_index": idx,
                "start_time": seg.start_time.isoformat(),
                "end_time": seg.end_time.isoformat(),
                "duration_minutes": seg.duration_minutes,
                "distance_km": seg.distance_km,
                "point_count": len(seg.points),
                "stroke_color": color,
            }
        })

    # 2. AIS Gap segments
    for idx, gap in enumerate(gap_segments):
        if not gap.start_position or not gap.end_position:
            continue
        gap_coords = [
            [round(gap.start_position.longitude, 6), round(gap.start_position.latitude, 6)],
            [round(gap.end_position.longitude, 6), round(gap.end_position.latitude, 6)],
        ]
        features.append({
            "type": "Feature",
            "id": f"{mmsi}-gap-{idx}",
            "geometry": {
                "type": "LineString",
                "coordinates": gap_coords,
            },
            "properties": {
                "feature_type": "ais_gap",
                "mmsi": mmsi,
                "gap_index": idx,
                "start_time": gap.start_time.isoformat(),
                "end_time": gap.end_time.isoformat(),
                "duration_minutes": gap.duration_minutes,
                "distance_km": gap.distance_km,
                "dash_array": "6, 6",
                "stroke_color": "#DC2626",  # Visual differentiation for missing telemetry
            }
        })

    # 3. Closest approach point
    if evidence.closest_approach_time is not None and evidence.closest_approach_distance_km < 9000:
        # Find position of closest approach (derived from trajectory)
        ca_pt = None
        for seg in valid_segments:
            for p in seg.points:
                if p.timestamp == evidence.closest_approach_time:
                    ca_pt = p
                    break
            if ca_pt:
                break

        if ca_pt:
            features.append({
                "type": "Feature",
                "id": f"{mmsi}-closest-approach",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(ca_pt.longitude, 6), round(ca_pt.latitude, 6)],
                },
                "properties": {
                    "feature_type": "closest_approach",
                    "mmsi": mmsi,
                    "distance_km": evidence.closest_approach_distance_km,
                    "timestamp": evidence.closest_approach_time.isoformat(),
                    "sog": evidence.sog_at_origin_kn,
                    "inside_uncertainty_zone": evidence.inside_uncertainty_zone,
                }
            })

    # 4. Interpolated origin position point
    if evidence.position_at_origin:
        lat = evidence.position_at_origin.get("latitude")
        lon = evidence.position_at_origin.get("longitude")
        if lat is not None and lon is not None:
            features.append({
                "type": "Feature",
                "id": f"{mmsi}-interpolated-origin",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 6), round(lat, 6)],
                },
                "properties": {
                    "feature_type": "interpolated_origin",
                    "mmsi": mmsi,
                    "sog": evidence.position_at_origin.get("sog"),
                    "exact": evidence.position_at_origin.get("exact", False),
                }
            })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def build_combined_feature3_geojson(
    vessel_geojsons: List[Dict[str, Any]],
    uncertainty_polygon_geojson: Optional[Dict[str, Any]] = None,
    reverse_drift_geojson: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combines all candidate vessels and Feature 2 context into a single map GeoJSON.
    """
    all_features: List[Dict[str, Any]] = []

    # Include uncertainty polygon if available
    if uncertainty_polygon_geojson:
        all_features.append({
            "type": "Feature",
            "id": "feature2-uncertainty-polygon",
            "geometry": uncertainty_polygon_geojson,
            "properties": {
                "feature_type": "uncertainty_polygon",
                "label": "Modeled Release Uncertainty Boundary",
            }
        })

    # Include reverse drift corridor if available
    if reverse_drift_geojson:
        all_features.append({
            "type": "Feature",
            "id": "feature2-reverse-drift-corridor",
            "geometry": reverse_drift_geojson,
            "properties": {
                "feature_type": "reverse_drift",
                "label": "Backward Hydrodynamic Drift Reconstruction",
            }
        })

    for v_geojson in vessel_geojsons:
        if v_geojson and "features" in v_geojson:
            all_features.extend(v_geojson["features"])

    return {
        "type": "FeatureCollection",
        "features": all_features,
    }
