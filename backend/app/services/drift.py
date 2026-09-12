from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import pandas as pd


def run_drift_hindcast_model(
    center_lat: float,
    center_lon: float,
    detection_timestamp: Optional[Union[str, datetime]] = None,
    backtrack_hours: float = 18.0,
):
    """
    Wraps the MetOcean hydrodynamic ocean current & wind drift hindcasting engine (testing/mock fallback).
    Calculates origin coordinates and future trajectory forecast dynamically anchored to observation time T0.
    """
    # Reverse backtrack vector (-18h) using 0.82 m/s surface current at 214°
    origin_lat = center_lat - 0.09
    origin_lon = center_lon - 0.26

    # Resolve observation timestamp T0 dynamically - never use hardcoded dates
    if detection_timestamp is not None:
        try:
            if isinstance(detection_timestamp, datetime):
                t0 = detection_timestamp.astimezone(timezone.utc) if detection_timestamp.tzinfo else detection_timestamp.replace(tzinfo=timezone.utc)
            else:
                ts_clean = str(detection_timestamp).replace(" UTC", "").strip()
                t0 = pd.to_datetime(ts_clean).tz_localize("UTC") if pd.to_datetime(ts_clean).tzinfo is None else pd.to_datetime(ts_clean).tz_convert("UTC")
                t0 = t0.to_pydatetime()
        except Exception:
            t0 = datetime.now(timezone.utc)
    else:
        t0 = datetime.now(timezone.utc)

    origin_dt = t0 - timedelta(hours=backtrack_hours)
    origin_timestamp = origin_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    drift_trajectory = [
        {"time": f"-{int(backtrack_hours)}h origin", "lat": origin_lat, "lon": origin_lon, "timestamp": origin_dt.isoformat()},
        {"time": "-12h backtrack", "lat": center_lat - 0.06, "lon": center_lon - 0.19, "timestamp": (t0 - timedelta(hours=12)).isoformat()},
        {"time": "-6h backtrack", "lat": center_lat - 0.03, "lon": center_lon - 0.11, "timestamp": (t0 - timedelta(hours=6)).isoformat()},
        {"time": "detected (0h)", "lat": center_lat, "lon": center_lon, "timestamp": t0.isoformat()},
        {"time": "+6h forecast", "lat": center_lat + 0.03, "lon": center_lon + 0.11, "timestamp": (t0 + timedelta(hours=6)).isoformat()},
        {"time": "+12h forecast", "lat": center_lat + 0.06, "lon": center_lon + 0.22, "timestamp": (t0 + timedelta(hours=12)).isoformat()}
    ]

    return {
        "origin_latitude": origin_lat,
        "origin_longitude": origin_lon,
        "origin_timestamp": origin_timestamp,
        "drift_trajectory": drift_trajectory
    }
