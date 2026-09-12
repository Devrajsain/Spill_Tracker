"""
Vessel trajectory reconstruction, segment builder, AIS gap detector, and time-aware interpolator.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from .schemas import AISRecord, LatLon, TrajectorySegment
from .spatial import haversine_km, point_to_segment_distance_km


def reconstruct_vessel_trajectories(
    records: List[AISRecord],
    max_gap_minutes: float = 30.0
) -> Tuple[List[TrajectorySegment], List[TrajectorySegment]]:
    """
    Groups chronologically sorted AIS records into time-valid continuous segments and explicit AIS gaps.
    
    Returns:
      (valid_segments: List[TrajectorySegment], gap_segments: List[TrajectorySegment])
    """
    if not records:
        return [], []

    valid_segments: List[TrajectorySegment] = []
    gap_segments: List[TrajectorySegment] = []

    current_points: List[AISRecord] = [records[0]]

    for i in range(1, len(records)):
        prev_r = records[i - 1]
        curr_r = records[i]

        dt_min = (curr_r.timestamp - prev_r.timestamp).total_seconds() / 60.0

        if dt_min <= max_gap_minutes:
            # Continuous movement within threshold
            current_points.append(curr_r)
        else:
            # Finalize existing continuous segment
            if current_points:
                seg_dist = 0.0
                for k in range(1, len(current_points)):
                    seg_dist += haversine_km(
                        current_points[k - 1].latitude, current_points[k - 1].longitude,
                        current_points[k].latitude, current_points[k].longitude
                    )
                duration_m = (current_points[-1].timestamp - current_points[0].timestamp).total_seconds() / 60.0
                valid_segments.append(TrajectorySegment(
                    mmsi=records[0].mmsi,
                    start_time=current_points[0].timestamp,
                    end_time=current_points[-1].timestamp,
                    points=current_points,
                    is_gap=False,
                    duration_minutes=duration_m,
                    distance_km=round(seg_dist, 3),
                    start_position=LatLon(latitude=current_points[0].latitude, longitude=current_points[0].longitude),
                    end_position=LatLon(latitude=current_points[-1].latitude, longitude=current_points[-1].longitude),
                ))

            # Record explicit AIS Gap
            gap_dist = haversine_km(prev_r.latitude, prev_r.longitude, curr_r.latitude, curr_r.longitude)
            gap_segments.append(TrajectorySegment(
                mmsi=records[0].mmsi,
                start_time=prev_r.timestamp,
                end_time=curr_r.timestamp,
                points=[],
                is_gap=True,
                duration_minutes=round(dt_min, 1),
                distance_km=round(gap_dist, 3),
                start_position=LatLon(latitude=prev_r.latitude, longitude=prev_r.longitude),
                end_position=LatLon(latitude=curr_r.latitude, longitude=curr_r.longitude),
            ))

            current_points = [curr_r]

    # Finalize trailing segment
    if current_points:
        seg_dist = 0.0
        for k in range(1, len(current_points)):
            seg_dist += haversine_km(
                current_points[k - 1].latitude, current_points[k - 1].longitude,
                current_points[k].latitude, current_points[k].longitude
            )
        duration_m = (current_points[-1].timestamp - current_points[0].timestamp).total_seconds() / 60.0
        valid_segments.append(TrajectorySegment(
            mmsi=records[0].mmsi,
            start_time=current_points[0].timestamp,
            end_time=current_points[-1].timestamp,
            points=current_points,
            is_gap=False,
            duration_minutes=duration_m,
            distance_km=round(seg_dist, 3),
            start_position=LatLon(latitude=current_points[0].latitude, longitude=current_points[0].longitude),
            end_position=LatLon(latitude=current_points[-1].latitude, longitude=current_points[-1].longitude),
        ))

    return valid_segments, gap_segments


def interpolate_position_at_time(
    records: List[AISRecord],
    target_time: datetime,
    max_interpolation_gap_min: float = 45.0
) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
    """
    Interpolates vessel position, SOG, and COG at target_time if surrounded by time-valid observations.
    
    Returns:
      (interpolated_dict: Optional[Dict], reason_flag: Optional[str])
    """
    if len(records) == 0:
        return None, "NO_RECORDS"

    # Exact match check
    for r in records:
        if abs((r.timestamp - target_time).total_seconds()) < 30.0:
            return {
                "latitude": r.latitude,
                "longitude": r.longitude,
                "sog": r.sog or 0.0,
                "cog": r.cog or 0.0,
                "exact": True,
            }, None

    # Search for bracketing observations
    prev_r: Optional[AISRecord] = None
    next_r: Optional[AISRecord] = None

    for i in range(len(records) - 1):
        if records[i].timestamp <= target_time <= records[i + 1].timestamp:
            prev_r = records[i]
            next_r = records[i + 1]
            break

    if not prev_r or not next_r:
        if target_time < records[0].timestamp:
            return None, "TARGET_TIME_BEFORE_TRACK"
        else:
            return None, "TARGET_TIME_AFTER_TRACK"

    dt_bracket_min = (next_r.timestamp - prev_r.timestamp).total_seconds() / 60.0
    if dt_bracket_min > max_interpolation_gap_min:
        return None, "GAP_EXCEEDS_MAX_INTERPOLATION_THRESHOLD"

    # Linear time interpolation along geodetic line
    t = (target_time - prev_r.timestamp).total_seconds() / (next_r.timestamp - prev_r.timestamp).total_seconds()
    interp_lat = prev_r.latitude + t * (next_r.latitude - prev_r.latitude)
    interp_lon = prev_r.longitude + t * (next_r.longitude - prev_r.longitude)
    
    sog_prev = prev_r.sog if prev_r.sog is not None else 0.0
    sog_next = next_r.sog if next_r.sog is not None else 0.0
    interp_sog = sog_prev + t * (sog_next - sog_prev)

    cog_prev = prev_r.cog if prev_r.cog is not None else 0.0
    cog_next = next_r.cog if next_r.cog is not None else 0.0
    interp_cog = cog_prev + t * (cog_next - cog_prev)

    return {
        "latitude": round(interp_lat, 6),
        "longitude": round(interp_lon, 6),
        "sog": round(interp_sog, 1),
        "cog": round(interp_cog, 1),
        "exact": False,
    }, None


def find_closest_approach_to_origin(
    records: List[AISRecord],
    origin_lat: float,
    origin_lon: float
) -> Dict[str, Any]:
    """
    Finds the closest approach distance, time, and kinematics to origin coordinates.
    Considers both discrete AIS points and continuous segments between consecutive points.
    """
    if not records:
        return {
            "distance_km": 9999.0,
            "time": None,
            "lat": 0.0,
            "lon": 0.0,
            "sog": 0.0,
        }

    min_dist = 9999.0
    closest_time = records[0].timestamp
    closest_lat = records[0].latitude
    closest_lon = records[0].longitude
    closest_sog = records[0].sog or 0.0

    for i in range(len(records)):
        curr_r = records[i]
        d = haversine_km(curr_r.latitude, curr_r.longitude, origin_lat, origin_lon)
        if d < min_dist:
            min_dist = d
            closest_time = curr_r.timestamp
            closest_lat = curr_r.latitude
            closest_lon = curr_r.longitude
            closest_sog = curr_r.sog or 0.0

        # Also test segment projection if consecutive points are within reasonable gap (< 60 min)
        if i > 0:
            prev_r = records[i - 1]
            dt_min = (curr_r.timestamp - prev_r.timestamp).total_seconds() / 60.0
            if dt_min <= 60.0:
                seg_d, t = point_to_segment_distance_km(
                    origin_lat, origin_lon,
                    prev_r.latitude, prev_r.longitude,
                    curr_r.latitude, curr_r.longitude
                )
                if seg_d < min_dist:
                    min_dist = seg_d
                    # Estimate approximate time along segment
                    closest_time = prev_r.timestamp + (curr_r.timestamp - prev_r.timestamp) * t
                    closest_lat = prev_r.latitude + t * (curr_r.latitude - prev_r.latitude)
                    closest_lon = prev_r.longitude + t * (curr_r.longitude - prev_r.longitude)
                    s_prev = prev_r.sog or 0.0
                    s_curr = curr_r.sog or 0.0
                    closest_sog = s_prev + t * (s_curr - s_prev)

    return {
        "distance_km": round(min_dist, 3),
        "time": closest_time,
        "lat": round(closest_lat, 6),
        "lon": round(closest_lon, 6),
        "sog": round(closest_sog, 1),
    }
