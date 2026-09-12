"""
Clean adapter layer transforming Feature 2 outputs into the Feature 3 Feature2OriginContext contract.
Prevents tight coupling to internal simulation physics classes.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Union
import dateutil.parser

from .schemas import Feature2OriginContext, LatLon, ReleaseTimeWindowContract


def _parse_utc(ts_val: Any) -> Optional[datetime]:
    if ts_val is None:
        return None
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=timezone.utc)
        return ts_val.astimezone(timezone.utc)
    s = str(ts_val).strip()
    if not s:
        return None
    try:
        dt = dateutil.parser.parse(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def extract_feature2_context(
    feature2_data: Union[Feature2OriginContext, Dict[str, Any], Any],
    spill_data: Optional[Dict[str, Any]] = None,
    drift_data: Optional[Dict[str, Any]] = None,
    spill_id: str = "SPILL_EVENT",
) -> Feature2OriginContext:
    """
    Constructs a validated Feature2OriginContext from Feature 2 pipeline output,
    database record, or dictionary payload.
    """
    if isinstance(feature2_data, Feature2OriginContext):
        return feature2_data

    # If dict representation of Feature2OriginContext
    if isinstance(feature2_data, dict) and "origin" in feature2_data and "release_window" in feature2_data:
        try:
            return Feature2OriginContext(**feature2_data)
        except Exception:
            pass

    # Extract origin coordinates
    lat = None
    lon = None
    radius_km = 3.0
    start_dt = None
    end_dt = None
    peak_dt = None
    uncertainty_polygon = None
    reverse_drift = None
    quality = {}

    # Check if feature2_data is an object or dict
    f2_dict = {}
    if hasattr(feature2_data, "__dict__"):
        f2_dict = {k: v for k, v in feature2_data.__dict__.items() if not k.startswith("_")}
    elif isinstance(feature2_data, dict):
        f2_dict = feature2_data

    origin_sub = f2_dict.get("origin") or {}

    lat = (
        origin_sub.get("origin_latitude") or
        origin_sub.get("latitude") or
        f2_dict.get("origin_latitude") or
        (drift_data.get("origin_latitude") if drift_data else None)
    )
    lon = (
        origin_sub.get("origin_longitude") or
        origin_sub.get("longitude") or
        f2_dict.get("origin_longitude") or
        (drift_data.get("origin_longitude") if drift_data else None)
    )

    if lat is None or lon is None:
        raise ValueError("Cannot extract origin coordinates from Feature 2 output.")

    radius_km = (
        origin_sub.get("origin_uncertainty_radius_km") or
        origin_sub.get("uncertainty_radius_km") or
        f2_dict.get("origin_uncertainty_radius_km") or
        3.0
    )

    # Release window
    raw_start = (
        origin_sub.get("release_window_start") or
        f2_dict.get("release_window_start") or
        origin_sub.get("origin_timestamp") or
        f2_dict.get("origin_timestamp") or
        (drift_data.get("origin_timestamp") if drift_data else None)
    )
    raw_end = (
        origin_sub.get("release_window_end") or
        f2_dict.get("release_window_end") or
        (spill_data.get("detection_timestamp") if spill_data else None) or
        raw_start
    )
    raw_peak = origin_sub.get("origin_timestamp") or f2_dict.get("origin_timestamp")

    start_dt = _parse_utc(raw_start)
    end_dt = _parse_utc(raw_end)
    peak_dt = _parse_utc(raw_peak)

    # Default fallback if timestamps are somehow missing
    now_utc = datetime.now(timezone.utc)
    if start_dt is None and end_dt is None:
        start_dt = now_utc - timedelta(hours=6)
        end_dt = now_utc
    elif start_dt is None and end_dt is not None:
        start_dt = end_dt - timedelta(hours=6)
    elif end_dt is None and start_dt is not None:
        end_dt = start_dt + timedelta(hours=6)

    # Reverse drift LineString derivation
    # If explicit reverse_drift was provided
    if "reverse_drift" in f2_dict and f2_dict["reverse_drift"]:
        reverse_drift = f2_dict["reverse_drift"]
    elif drift_data and drift_data.get("drift_trajectory"):
        # Use drift trajectory as corridor
        traj = drift_data["drift_trajectory"]
        coords = [[round(p["lon"], 6), round(p["lat"], 6)] for p in traj if "lon" in p and "lat" in p]
        if len(coords) >= 2:
            reverse_drift = {"type": "LineString", "coordinates": coords}
    elif spill_data and spill_data.get("spill_latitude") and spill_data.get("spill_longitude"):
        # Connecting detected slick centroid at T0 back to origin centroid at T_origin
        spill_lat = float(spill_data["spill_latitude"])
        spill_lon = float(spill_data["spill_longitude"])
        reverse_drift = {
            "type": "LineString",
            "coordinates": [
                [round(lon, 6), round(lat, 6)],
                [round(spill_lon, 6), round(spill_lat, 6)],
            ]
        }

    # Uncertainty polygon derivation
    if "uncertainty_zone" in f2_dict and f2_dict["uncertainty_zone"]:
        uncertainty_polygon = f2_dict["uncertainty_zone"]
    elif f2_dict.get("geojson_feature_collection"):
        fc = f2_dict["geojson_feature_collection"]
        for feat in fc.get("features", []):
            if feat.get("properties", {}).get("type") == "uncertainty_polygon" or feat.get("geometry", {}).get("type") == "Polygon":
                uncertainty_polygon = feat.get("geometry")
                break

    return Feature2OriginContext(
        spill_id=spill_id,
        origin=LatLon(latitude=float(lat), longitude=float(lon)),
        release_window=ReleaseTimeWindowContract(
            start=start_dt,
            end=end_dt,
            peak_evidence_time=peak_dt,
        ),
        uncertainty_radius_km=float(radius_km),
        uncertainty_zone=uncertainty_polygon,
        reverse_drift=reverse_drift,
        feature2_quality=quality,
    )
