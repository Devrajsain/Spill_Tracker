"""
Feature 1 SAR Slick Detection Input Adapter (Task 9).
Provides dual-mode input parsing for:
1. Canonical internal Feature 1 flattened schema (SlickDetectionInput).
2. Standard RFC 7946 GeoJSON FeatureCollection payloads.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Union
from pydantic import ValidationError

from ..exceptions import InvalidInputGeometryError
from ..geo.spatial import (
    compute_polygon_centroid,
    validate_polygon_geometry,
    haversine_polygon_area_km2,
    haversine_polygon_perimeter_km,
)
from .input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry


def parse_feature1_input(
    payload: Union[SlickDetectionInput, Dict[str, Any]]
) -> SlickDetectionInput:
    """
    Parses and normalizes input payload from Feature 1.
    Accepts:
    - Existing SlickDetectionInput instance
    - Flattened internal dictionary matching SlickDetectionInput
    - Standard GeoJSON FeatureCollection containing a SAR slick Polygon Feature

    Returns:
        Canonical, fully validated SlickDetectionInput model.

    Raises:
        InvalidInputGeometryError: on malformed, unclosed, out-of-bounds, or MultiPolygon geometry.
        ValueError: on missing mandatory properties (spill_id, observation_time) or malformed payload.
    """
    if isinstance(payload, SlickDetectionInput):
        if payload.geometry.type == "MultiPolygon":
            raise InvalidInputGeometryError(
                "MultiPolygon geometry is not currently supported; Feature 1 input geometry must be 'Polygon'."
            )
        # Validate coordinates
        validate_polygon_geometry(payload.geometry.coordinates)
        return payload

    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported payload type: {type(payload)}. Expected dict or SlickDetectionInput.")

    # Detect GeoJSON FeatureCollection
    if payload.get("type") == "FeatureCollection":
        return _parse_geojson_feature_collection(payload)

    # Detect GeoJSON single Feature
    if payload.get("type") == "Feature":
        return _parse_single_geojson_feature(payload)

    # Internal flattened dictionary
    return _parse_flattened_dict(payload)


def _parse_geojson_feature_collection(collection: Dict[str, Any]) -> SlickDetectionInput:
    """Extracts and validates slick detection from a GeoJSON FeatureCollection."""
    features = collection.get("features")
    if not isinstance(features, list) or len(features) == 0:
        raise ValueError("GeoJSON FeatureCollection must contain a non-empty 'features' list.")

    # Find the primary polygon feature
    slick_feature: Optional[Dict[str, Any]] = None
    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry")
        if isinstance(geom, dict):
            geom_type = geom.get("type")
            if geom_type in ("Polygon", "MultiPolygon"):
                slick_feature = feat
                break

    if slick_feature is None:
        # Fall back to first feature if present
        first = features[0]
        if isinstance(first, dict):
            slick_feature = first
        else:
            raise ValueError("FeatureCollection does not contain any valid Feature objects.")

    return _parse_single_geojson_feature(slick_feature)


def _parse_single_geojson_feature(feature: Dict[str, Any]) -> SlickDetectionInput:
    """Parses an individual GeoJSON Feature into a canonical SlickDetectionInput."""
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        raise InvalidInputGeometryError("Feature is missing a valid 'geometry' object.")

    geom_type = geom.get("type")
    if geom_type == "MultiPolygon":
        raise InvalidInputGeometryError(
            "MultiPolygon geometry is not currently supported; Feature 1 input geometry must be 'Polygon'."
        )
    if geom_type != "Polygon":
        raise InvalidInputGeometryError(
            f"Unsupported geometry type '{geom_type}'. Feature 1 input geometry must be 'Polygon'."
        )

    raw_coords = geom.get("coordinates")
    validated_coords = validate_polygon_geometry(raw_coords)

    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        props = {}

    # 1. spill_id
    spill_id = (
        props.get("spill_id") or
        props.get("id") or
        feature.get("id") or
        props.get("name")
    )
    if not spill_id or not str(spill_id).strip():
        raise ValueError("Feature properties must contain a valid, non-empty 'spill_id'.")
    spill_id = str(spill_id).strip()

    # 2. observation_time
    obs_time_raw = (
        props.get("observation_time") or
        props.get("timestamp") or
        props.get("time") or
        props.get("datetime") or
        props.get("acquisition_time")
    )
    if not obs_time_raw:
        raise ValueError("Feature properties must contain a valid 'observation_time' timestamp.")

    if isinstance(obs_time_raw, datetime):
        obs_time = obs_time_raw if obs_time_raw.tzinfo else obs_time_raw.replace(tzinfo=timezone.utc)
    else:
        try:
            obs_time = datetime.fromisoformat(str(obs_time_raw).replace("Z", "+00:00"))
        except Exception as err:
            raise ValueError(f"Invalid observation_time format '{obs_time_raw}': {err}") from err

    # 3. Centroid (derive if absent)
    centroid_prop = props.get("centroid")
    if isinstance(centroid_prop, dict) and "latitude" in centroid_prop and "longitude" in centroid_prop:
        c_lat = float(centroid_prop["latitude"])
        c_lon = float(centroid_prop["longitude"])
    elif isinstance(centroid_prop, (list, tuple)) and len(centroid_prop) >= 2:
        # Check if [lon, lat] or [lat, lon]
        c_lon = float(centroid_prop[0])
        c_lat = float(centroid_prop[1])
    else:
        c_lat, c_lon = compute_polygon_centroid(validated_coords[0])

    centroid = CentroidCoordinates(
        latitude=round(c_lat, 6),
        longitude=round(c_lon, 6)
    )

    # 4. Area (derive if absent)
    area_val = props.get("area_sq_km") or props.get("area_km2") or props.get("area")
    if area_val is not None:
        try:
            area_km2 = float(area_val)
        except (ValueError, TypeError):
            area_km2 = 0.0
    else:
        area_km2 = 0.0

    if area_km2 <= 0.0:
        area_km2 = haversine_polygon_area_km2(validated_coords[0])
    if area_km2 <= 0.0:
        area_km2 = 0.01  # Nominal fallback for tiny sub-resolution features

    # 5. Perimeter (derive if absent)
    perim_val = props.get("perimeter_km") or props.get("perimeter")
    if perim_val is not None:
        try:
            perim_km = float(perim_val)
        except (ValueError, TypeError):
            perim_km = 0.0
    else:
        perim_km = 0.0

    if perim_km <= 0.0:
        perim_km = haversine_polygon_perimeter_km(validated_coords[0])
    if perim_km <= 0.0:
        perim_km = 0.1

    geometry = GeoJSONGeometry(
        type="Polygon",
        coordinates=validated_coords
    )

    metadata = {k: v for k, v in props.items() if k not in ("spill_id", "observation_time", "centroid", "area_sq_km", "area_km2", "perimeter_km")}

    return SlickDetectionInput(
        spill_id=spill_id,
        observation_time=obs_time,
        area_sq_km=round(area_km2, 4),
        perimeter_km=round(perim_km, 4),
        centroid=centroid,
        geometry=geometry,
        metadata=metadata
    )


def _parse_flattened_dict(payload: Dict[str, Any]) -> SlickDetectionInput:
    """Parses internal flattened dictionary."""
    geom = payload.get("geometry")
    if isinstance(geom, dict):
        if geom.get("type") == "MultiPolygon":
            raise InvalidInputGeometryError(
                "MultiPolygon geometry is not currently supported; Feature 1 input geometry must be 'Polygon'."
            )
        if geom.get("coordinates"):
            validate_polygon_geometry(geom["coordinates"])

    try:
        return SlickDetectionInput(**payload)
    except ValidationError as e:
        raise ValueError(f"Invalid Feature 1 input schema: {e}") from e
