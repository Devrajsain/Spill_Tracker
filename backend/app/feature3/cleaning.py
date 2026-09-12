"""
Robust AIS ingestion, validation, and cleaning pipeline.
Normalizes columns, UTC timestamps, validates coordinate bounds, and annotates quality flags.
"""

import io
import csv
import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import dateutil.parser
import pandas as pd

from .schemas import AISRecord, Feature3EngineConfig, LatLon

logger = logging.getLogger(__name__)

# Default kinematic upper bound for plausible commercial vessel speed in knots
# Typical displacement tankers cruise at 10-16 kn, fast cargo at 20-25 kn. Speeds above 65 kn
# (approx 120 km/h) are physically impossible for commercial marine traffic and represent GPS/AIS transmission jumps.
DEFAULT_MAX_AIS_SPEED_KNOTS = 65.0
DEFAULT_UNUSUAL_SPEED_KNOTS = 35.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two geographic coordinates in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    return 2.0 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def parse_utc_timestamp(val: Any) -> Optional[datetime]:
    """Parses diverse timestamp formats into a UTC-aware datetime object."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        # Check if epoch timestamp in seconds or milliseconds
        if val > 1e11:
            val = val / 1000.0
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    
    val_str = str(val).strip()
    if not val_str:
        return None
    try:
        dt = dateutil.parser.parse(val_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def clean_and_validate_ais(
    source: Union[str, bytes, pd.DataFrame, List[Dict[str, Any]]],
    config: Optional[Feature3EngineConfig] = None,
) -> Tuple[List[AISRecord], Dict[str, Any]]:
    """
    Ingests and cleans raw AIS data from CSV filepath, CSV string/bytes, DataFrame, or dict list.
    
    Returns:
      (cleaned_sorted_records: List[AISRecord], audit_stats: Dict[str, Any])
    """
    max_speed_threshold = config.max_ais_speed_knots if config else DEFAULT_MAX_AIS_SPEED_KNOTS
    unusual_speed_threshold = config.unusual_speed_knots if config else DEFAULT_UNUSUAL_SPEED_KNOTS

    raw_records: List[Dict[str, Any]] = []

    # Handle various source formats
    if isinstance(source, pd.DataFrame):
        raw_records = source.to_dict(orient="records")
    elif isinstance(source, list):
        raw_records = source
    elif isinstance(source, (str, bytes)):
        if isinstance(source, bytes):
            source = source.decode("utf-8-sig", errors="replace")
        
        # Check if source is a file path
        if "\n" not in source and len(source) < 1000 and source.endswith(".csv"):
            import os
            if os.path.exists(source):
                with open(source, mode="r", encoding="utf-8-sig", errors="replace") as f:
                    source = f.read()

        # Parse CSV text
        reader = csv.DictReader(io.StringIO(source))
        raw_records = list(reader)

    if not raw_records:
        return [], {"total_raw": 0, "accepted": 0, "quarantined": 0, "duplicates_removed": 0}

    # Standardize column names
    cleaned_records: List[AISRecord] = []
    quarantined_count = 0
    duplicates_count = 0
    seen_keys = set()

    for row in raw_records:
        # Standardize dictionary keys to lowercase trimmed
        norm_row = {str(k).lower().strip(): v for k, v in row.items() if k is not None}

        # Extract MMSI
        mmsi_val = (norm_row.get("mmsi") or norm_row.get("vessel_mmsi") or 
                    norm_row.get("vesselid") or norm_row.get("user_id"))
        if not mmsi_val:
            quarantined_count += 1
            continue
        mmsi = str(mmsi_val).strip()
        if not mmsi or mmsi == "0" or mmsi.lower() == "nan":
            quarantined_count += 1
            continue

        # Extract timestamp
        time_val = (norm_row.get("timestamp") or norm_row.get("time") or 
                    norm_row.get("datetime") or norm_row.get("basedatetime") or
                    norm_row.get("date_time_utc"))
        ts = parse_utc_timestamp(time_val)
        if ts is None:
            quarantined_count += 1
            continue

        # Extract Latitude & Longitude
        lat_val = (norm_row.get("lat") or norm_row.get("latitude") or 
                   norm_row.get("y") or norm_row.get("lat_deg"))
        lon_val = (norm_row.get("lon") or norm_row.get("longitude") or 
                   norm_row.get("lng") or norm_row.get("x") or norm_row.get("lon_deg"))

        try:
            lat = float(lat_val)
            lon = float(lon_val)
        except (ValueError, TypeError):
            quarantined_count += 1
            continue

        quality_flags = []

        # Validate coordinate boundaries
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            quarantined_count += 1
            continue

        if lat == 0.0 and lon == 0.0:
            quality_flags.append("NULL_ISLAND_COORDINATE")

        # Deduplication check: (MMSI, timestamp, rounded lat, rounded lon)
        dedup_key = (mmsi, ts.isoformat(), round(lat, 5), round(lon, 5))
        if dedup_key in seen_keys:
            duplicates_count += 1
            continue
        seen_keys.add(dedup_key)

        # Extract SOG (Speed Over Ground)
        sog_raw = (norm_row.get("sog") or norm_row.get("speed") or 
                   norm_row.get("speed_knots") or norm_row.get("speed_over_ground"))
        sog: Optional[float] = None
        if sog_raw is not None and str(sog_raw).strip() != "":
            try:
                sog = float(sog_raw)
                if sog < 0.0 or sog > 102.2:
                    quality_flags.append("INVALID_SOG_RANGE")
                    sog = max(0.0, min(102.2, sog))
            except (ValueError, TypeError):
                quality_flags.append("UNPARSEABLE_SOG")

        # Extract COG (Course Over Ground)
        cog_raw = (norm_row.get("cog") or norm_row.get("course") or 
                   norm_row.get("heading") or norm_row.get("heading_deg") or
                   norm_row.get("course_over_ground"))
        cog: Optional[float] = None
        if cog_raw is not None and str(cog_raw).strip() != "":
            try:
                cog = float(cog_raw)
                if cog < 0.0 or cog > 360.0:
                    quality_flags.append("INVALID_COG_RANGE")
                    cog = cog % 360.0
            except (ValueError, TypeError):
                quality_flags.append("UNPARSEABLE_COG")

        # Metadata
        name = (norm_row.get("vessel_name") or norm_row.get("name") or 
                norm_row.get("shipname") or norm_row.get("vesselname"))
        v_name = str(name).strip() if name else None

        vtype = (norm_row.get("vessel_type") or norm_row.get("type") or 
                 norm_row.get("shiptype") or norm_row.get("shiptype_text"))
        v_type = str(vtype).strip() if vtype else None

        flag = (norm_row.get("flag") or norm_row.get("country") or 
                norm_row.get("flagstate") or norm_row.get("flag_country"))
        v_flag = str(flag).strip() if flag else None

        cleaned_records.append(AISRecord(
            mmsi=mmsi,
            timestamp=ts,
            latitude=lat,
            longitude=lon,
            sog=sog,
            cog=cog,
            vessel_name=v_name,
            vessel_type=v_type,
            flag=v_flag,
            quality_flags=quality_flags,
        ))

    # Sort records deterministically by MMSI then timestamp
    cleaned_records.sort(key=lambda r: (r.mmsi, r.timestamp))

    # Second pass: detect kinematic jumps between consecutive pings per vessel
    jump_flagged_count = 0
    unusual_speed_count = 0
    records_by_mmsi: Dict[str, List[AISRecord]] = {}
    for r in cleaned_records:
        records_by_mmsi.setdefault(r.mmsi, []).append(r)

    # Deterministic vessel iteration
    validated_records: List[AISRecord] = []
    for mmsi in sorted(records_by_mmsi.keys()):
        mmsi_pts = records_by_mmsi[mmsi]
        for i in range(len(mmsi_pts)):
            pt = mmsi_pts[i]
            if i > 0:
                prev_pt = mmsi_pts[i - 1]
                dt_hours = (pt.timestamp - prev_pt.timestamp).total_seconds() / 3600.0
                if dt_hours > 0:
                    dist_km = _haversine_km(prev_pt.latitude, prev_pt.longitude, pt.latitude, pt.longitude)
                    speed_knots = (dist_km / 1.852) / dt_hours
                    if speed_knots > max_speed_threshold:
                        pt.quality_flags.append("IMPLAUSIBLE_JUMP")
                        jump_flagged_count += 1
                    elif speed_knots > unusual_speed_threshold:
                        pt.quality_flags.append("UNUSUAL_HIGH_SPEED")
                        unusual_speed_count += 1
            validated_records.append(pt)

    audit_stats = {
        "total_raw": len(raw_records),
        "accepted": len(validated_records),
        "quarantined": quarantined_count,
        "duplicates_removed": duplicates_count,
        "jump_flags": jump_flagged_count,
        "unusual_speed_flags": unusual_speed_count,
        "unique_mmsi_count": len(records_by_mmsi),
    }

    return validated_records, audit_stats
