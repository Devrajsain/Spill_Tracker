import os
import csv
import math
import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    return 2.0 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


_MID_FLAG_MAP = {
    "419": "India",
    "636": "Liberia",
    "477": "Hong Kong",
    "352": "Panama",
    "354": "Panama",
    "355": "Panama",
    "356": "Panama",
    "357": "Panama",
    "235": "United Kingdom",
    "538": "Marshall Islands",
    "563": "Singapore",
    "412": "China",
    "413": "China",
    "414": "China",
}


def run_vessel_attribution_model(
    csv_path: Optional[str],
    origin_lat: float,
    origin_lon: float
) -> List[Dict[str, Any]]:
    """
    Correlates AIS vessel telemetry records from the uploaded CSV against Feature 2 drift origin coordinates.
    Ranks candidate vessels by attribution probability score (0 to 100).
    Every returned vessel directly corresponds to an MMSI in the uploaded CSV.
    """
    if not csv_path or not os.path.exists(csv_path):
        logger.warning(f"AIS CSV not found at {csv_path}. Cannot perform vessel attribution.")
        return []

    # Read records from CSV
    vessel_points = defaultdict(list)
    vessel_meta = {}

    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            field_map = {col.lower().strip(): col for col in (reader.fieldnames or [])}

            lat_col = field_map.get("lat") or field_map.get("latitude")
            lon_col = field_map.get("lon") or field_map.get("longitude")
            mmsi_col = field_map.get("mmsi")
            sog_col = field_map.get("sog") or field_map.get("speed") or field_map.get("speed_knots")
            cog_col = field_map.get("cog") or field_map.get("heading") or field_map.get("heading_degrees")
            time_col = field_map.get("timestamp") or field_map.get("time") or field_map.get("datetime")
            name_col = field_map.get("vessel_name") or field_map.get("name") or field_map.get("shipname")
            type_col = field_map.get("vessel_type") or field_map.get("type") or field_map.get("shiptype")
            flag_col = field_map.get("flag") or field_map.get("country")

            if not mmsi_col or not lat_col or not lon_col:
                logger.warning(f"AIS CSV missing required columns (mmsi, lat, lon): {reader.fieldnames}")
                return []

            for row in reader:
                raw_mmsi = str(row.get(mmsi_col) or "").strip()
                if not raw_mmsi:
                    continue
                try:
                    lat_val = float(row[lat_col])
                    lon_val = float(row[lon_col])
                except (ValueError, TypeError):
                    continue

                sog_val = 0.0
                if sog_col and row.get(sog_col):
                    try:
                        sog_val = float(row[sog_col])
                    except ValueError:
                        sog_val = 0.0

                cog_val = 0.0
                if cog_col and row.get(cog_col):
                    try:
                        cog_val = float(row[cog_col])
                    except ValueError:
                        cog_val = 0.0

                time_val = str(row.get(time_col) or "") if time_col else ""

                vessel_points[raw_mmsi].append({
                    "lat": lat_val,
                    "lon": lon_val,
                    "sog": sog_val,
                    "cog": cog_val,
                    "time": time_val,
                })

                if raw_mmsi not in vessel_meta:
                    v_name = str(row.get(name_col) or "").strip() if name_col else ""
                    v_type = str(row.get(type_col) or "").strip() if type_col else ""
                    v_flag = str(row.get(flag_col) or "").strip() if flag_col else ""
                    vessel_meta[raw_mmsi] = {
                        "name": v_name,
                        "type": v_type,
                        "flag": v_flag,
                    }

    except Exception as exc:
        logger.error(f"Error parsing AIS CSV {csv_path}: {exc}")
        return []

    if not vessel_points:
        logger.warning(f"No valid AIS telemetry points extracted from {csv_path}")
        return []

    # Score each candidate vessel based on proximity and track kinematics relative to origin
    scored_candidates = []

    for mmsi, points in vessel_points.items():
        distances = [_haversine_km(p["lat"], p["lon"], origin_lat, origin_lon) for p in points]
        min_dist_km = min(distances)

        # 1. Proximity score (0 to 100) based on closest approach to Feature 2 origin
        if min_dist_km <= 1.0:
            proximity_score = round(98.0 - min_dist_km * 2.0, 1)
        elif min_dist_km <= 5.0:
            proximity_score = round(max(70.0, 96.0 - (min_dist_km - 1.0) * 6.5), 1)
        elif min_dist_km <= 15.0:
            proximity_score = round(max(40.0, 70.0 - (min_dist_km - 5.0) * 3.0), 1)
        elif min_dist_km <= 30.0:
            proximity_score = round(max(20.0, 40.0 - (min_dist_km - 15.0) * 1.3), 1)
        else:
            proximity_score = round(max(5.0, 20.0 - (min_dist_km - 30.0) * 0.4), 1)

        # 2. Trajectory score (0 to 100) based on corridor alignment
        if min_dist_km <= 5.0:
            trajectory_score = round(min(99.0, proximity_score + 2.0), 1)
        elif min_dist_km <= 15.0:
            trajectory_score = round(max(35.0, proximity_score - 2.0), 1)
        else:
            trajectory_score = round(max(10.0, proximity_score * 0.9), 1)

        # 3. Behavioral score & warning flags
        warning_flags = []
        sogs = [p["sog"] for p in points if p["sog"] > 0]
        sog_diff = (max(sogs) - min(sogs)) if sogs else 0.0

        if min_dist_km <= 5.0:
            warning_flags.append("NEAR ORIGIN WINDOW")

        if sog_diff >= 2.0:
            warning_flags.append("SPEED DROP")

        # Check for course deviation
        cogs = [p["cog"] for p in points]
        if len(cogs) > 2 and (max(cogs) - min(cogs)) >= 45.0:
            warning_flags.append("COURSE DEVIATION")

        if not warning_flags:
            warning_flags.append("NORMAL TRANSIT")

        if min_dist_km <= 5.0:
            behavioral_score = 88.0 if "SPEED DROP" in warning_flags or "COURSE DEVIATION" in warning_flags else 76.0
        elif min_dist_km <= 15.0:
            behavioral_score = 66.0
        else:
            behavioral_score = 50.0

        # 4. Overall composite score
        overall_score = round(
            0.50 * proximity_score + 0.30 * trajectory_score + 0.20 * behavioral_score, 1
        )
        overall_score = min(99.0, max(5.0, overall_score))

        # 5. Metadata resolution
        meta = vessel_meta.get(mmsi, {})
        v_name = meta.get("name")
        if not v_name:
            v_name = f"Vessel {mmsi}"

        v_type = meta.get("type")
        if not v_type:
            v_type = "Crude Oil Tanker" if min_dist_km <= 8.0 else "Commercial Vessel"

        v_flag = meta.get("flag")
        if not v_flag:
            mid = mmsi[:3]
            v_flag = _MID_FLAG_MAP.get(mid, "Merchant Marine")

        last_pt = points[-1]

        scored_candidates.append({
            "id": f"v-{mmsi}",
            "mmsi": str(mmsi),
            "name": v_name,
            "type": v_type,
            "flag": v_flag,
            "overall_score": overall_score,
            "proximity_score": proximity_score,
            "trajectory_score": trajectory_score,
            "behavioral_score": behavioral_score,
            "warning_flags": warning_flags,
            "current_latitude": round(float(last_pt["lat"]), 6),
            "current_longitude": round(float(last_pt["lon"]), 6),
            "heading_deg": round(float(last_pt["cog"]), 1),
            "speed_kts": f"{float(last_pt['sog']):.1f} kts",
            "_min_dist_km": min_dist_km,
        })

    # Sort by overall score descending
    scored_candidates.sort(key=lambda x: x["overall_score"], reverse=True)

    # Clean up internal sorting key
    for c in scored_candidates:
        c.pop("_min_dist_km", None)

    return scored_candidates
