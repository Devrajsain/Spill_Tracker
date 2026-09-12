"""
Deterministic, bounded, and explainable 5-factor and PS-143 scoring engines for Feature 3.
Implements non-accusatory evidence correlation ranking with explicit weight redistribution
when evidence dimensions are unavailable.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .schemas import (
    AISRecord,
    Feature2OriginContext,
    Feature3EngineConfig,
    RawEvidenceMetrics,
    ScoreBreakdown,
    TrajectorySegment,
)
from .spatial import (
    calculate_bearing,
    distance_to_uncertainty_zone_km,
    haversine_km,
    smallest_angle_difference,
)


def compute_origin_presence_score(
    closest_distance_km: float,
    time_offset_min: float,
    inside_uncertainty_zone: bool,
    config: Feature3EngineConfig,
) -> float:
    """
    Computes bounded Origin Presence score (0–100) using geodetic spatial decay and temporal decay.
    Vessels observed directly inside the uncertainty polygon receive high correlation.
    """
    # Spatial decay factor (e^-d/scale)
    # If inside uncertainty zone, spatial distance penalty is 0 -> spatial_factor = 1.0
    eff_distance = 0.0 if inside_uncertainty_zone else closest_distance_km
    spatial_factor = math.exp(-eff_distance / max(0.5, config.spatial_scale_km))

    # Temporal decay factor (e^-dt/scale)
    # If time offset is within release window (0 min offset), temporal_factor = 1.0
    temporal_factor = math.exp(-time_offset_min / max(5.0, config.temporal_scale_min))

    score = 100.0 * spatial_factor * temporal_factor

    # If vessel entered the uncertainty zone during/near the window, ensure high baseline
    if inside_uncertainty_zone:
        if time_offset_min <= 15.0:
            score = max(score, 90.0)
        elif time_offset_min <= 60.0:
            score = max(score, 75.0)

    return round(max(0.0, min(100.0, score)), 2)


def compute_behavior_anomaly_score(
    event_records: List[AISRecord],
    all_records: List[AISRecord],
    inside_zone: bool,
    min_distance_km: float,
) -> Tuple[float, Dict[str, Any], List[str]]:
    """
    Evaluates kinematic anomalies (speed reduction relative to vessel baseline, loitering, course change).
    If historical baseline is insufficient, emits BASELINE_INSUFFICIENT and applies a conservative heuristic
    without penalizing or fabricating baseline data.
    
    Returns:
      (score: float, metrics: Dict, flags: List[str])
    """
    flags: List[str] = []
    metrics: Dict[str, Any] = {
        "baseline_median_sog_kn": None,
        "event_median_sog_kn": None,
        "speed_reduction_ratio": None,
        "minimum_sog_kn": None,
        "course_change_degrees": None,
    }

    if not event_records:
        return 0.0, metrics, ["NO_EVENT_RECORDS"]

    # Extract observed speeds
    event_sogs = [r.sog for r in event_records if r.sog is not None and r.sog >= 0]
    all_sogs = [r.sog for r in all_records if r.sog is not None and r.sog >= 0]

    min_sog = min(event_sogs) if event_sogs else None
    metrics["minimum_sog_kn"] = round(min_sog, 1) if min_sog is not None else None

    # Compute course changes
    event_cogs = [r.cog for r in event_records if r.cog is not None and 0 <= r.cog <= 360]
    max_cog_change = 0.0
    if len(event_cogs) >= 2:
        for i in range(len(event_cogs) - 1):
            diff = smallest_angle_difference(event_cogs[i], event_cogs[i + 1])
            if diff > max_cog_change:
                max_cog_change = diff
    metrics["course_change_degrees"] = round(max_cog_change, 1) if event_cogs else None

    # Baseline evaluation: pre-event / non-event points (> 15 km from origin)
    baseline_records = [
        r for r in all_records 
        if r not in event_records and r.sog is not None and r.sog > 1.0
    ]
    
    has_sufficient_baseline = len(baseline_records) >= 3

    if has_sufficient_baseline:
        sorted_baseline = sorted(r.sog for r in baseline_records if r.sog is not None)
        baseline_median = sorted_baseline[len(sorted_baseline) // 2]
        metrics["baseline_median_sog_kn"] = round(baseline_median, 1)

        event_median = sorted(event_sogs)[len(event_sogs) // 2] if event_sogs else baseline_median
        metrics["event_median_sog_kn"] = round(event_median, 1)

        if baseline_median > 3.0:
            reduction_ratio = max(0.0, (baseline_median - event_median) / baseline_median)
            metrics["speed_reduction_ratio"] = round(reduction_ratio, 2)
        else:
            reduction_ratio = 0.0
            metrics["speed_reduction_ratio"] = 0.0

        # Score based on relative drop and course deviations
        speed_score = min(100.0, reduction_ratio * 100.0 * 1.3)
        cog_score = min(100.0, (max_cog_change / 90.0) * 80.0) if max_cog_change >= 30.0 else 0.0

        if reduction_ratio >= 0.4:
            flags.append("SPEED_REDUCTION_DETECTED")
        if max_cog_change >= 45.0:
            flags.append("COURSE_DEVIATION_NEAR_ORIGIN")

        raw_score = 0.70 * speed_score + 0.30 * cog_score
        # Proximity amplification if vessel performed maneuvers close to origin
        if min_distance_km <= 5.0 or inside_zone:
            if reduction_ratio >= 0.3:
                raw_score = max(raw_score, 70.0)
            if min_sog is not None and min_sog <= 3.0:
                raw_score = max(raw_score, 75.0)
                flags.append("LOITERING_SPEED_NEAR_ORIGIN")
    else:
        # Insufficient baseline: evaluate absolute kinematic metrics near event without claiming baseline certainty
        flags.append("BASELINE_INSUFFICIENT")
        event_median = sorted(event_sogs)[len(event_sogs) // 2] if event_sogs else 0.0
        metrics["event_median_sog_kn"] = round(event_median, 1)

        raw_score = 0.0
        # If speed is unusually low near origin (< 4 knots for commercial vessel)
        if min_sog is not None and min_sog <= 4.0 and (min_distance_km <= 8.0 or inside_zone):
            raw_score += 65.0
            flags.append("LOITERING_SPEED_NEAR_ORIGIN")
        elif event_median <= 6.0 and min_distance_km <= 10.0:
            raw_score += 45.0

        if max_cog_change >= 45.0:
            raw_score += 25.0
            flags.append("COURSE_DEVIATION_NEAR_ORIGIN")

    return round(max(0.0, min(100.0, raw_score)), 2), metrics, flags


def compute_dwell_time_score(
    dwell_inside_min: float,
    dwell_near_min: float,
    config: Feature3EngineConfig,
) -> float:
    """
    Calculates Dwell Time score (0–100) saturating at configurable threshold.
    """
    sat_min = max(10.0, config.dwell_saturation_minutes)
    # Inside zone is weighted 1.0, near zone is weighted 0.5
    effective_dwell = dwell_inside_min + (0.5 * dwell_near_min)
    ratio = min(1.0, effective_dwell / sat_min)
    score = 100.0 * ratio
    return round(score, 2)


def compute_ais_gap_score(
    gap_segments: List[TrajectorySegment],
    origin_lat: float,
    origin_lon: float,
    release_start: datetime,
    release_end: datetime,
    config: Feature3EngineConfig,
) -> Tuple[float, Dict[str, Any], List[str]]:
    """
    Evaluates AIS dark / gap segments. A gap is only relevant if it occurs close in space and time
    to the release event. Gaps far away in space or time contribute 0.
    """
    metrics: Dict[str, Any] = {
        "gap_duration_minutes": None,
        "gap_distance_to_origin_km": None,
        "gap_time_offset_minutes": None,
        "gap_relevance_score": 0.0,
    }
    flags: List[str] = []

    if not gap_segments:
        return 0.0, metrics, flags

    best_score = 0.0
    best_gap: Optional[TrajectorySegment] = None
    best_dist = 9999.0
    best_dt = 9999.0

    t_origin = release_start + (release_end - release_start) / 2

    for gap in gap_segments:
        gap_mid_time = gap.start_time + (gap.end_time - gap.start_time) / 2
        
        # Temporal offset to release window
        if release_start <= gap_mid_time <= release_end:
            dt_min = 0.0
        elif gap_mid_time < release_start:
            dt_min = (release_start - gap_mid_time).total_seconds() / 60.0
        else:
            dt_min = (gap_mid_time - release_end).total_seconds() / 60.0

        # Spatial midpoint distance to origin
        if gap.start_position and gap.end_position:
            mid_lat = (gap.start_position.latitude + gap.end_position.latitude) / 2
            mid_lon = (gap.start_position.longitude + gap.end_position.longitude) / 2
        elif gap.start_position:
            mid_lat, mid_lon = gap.start_position.latitude, gap.start_position.longitude
        else:
            continue

        dist_km = haversine_km(mid_lat, mid_lon, origin_lat, origin_lon)

        # Duration factor: saturates around 90 minutes
        duration_factor = min(1.0, gap.duration_minutes / 90.0)

        # Spatial decay: scale ~ 12 km
        spatial_decay = math.exp(-dist_km / 12.0)

        # Temporal decay: scale ~ 120 min
        temporal_decay = math.exp(-dt_min / 120.0)

        relevance = 100.0 * duration_factor * spatial_decay * temporal_decay

        if relevance > best_score:
            best_score = relevance
            best_gap = gap
            best_dist = dist_km
            best_dt = dt_min

    if best_gap and best_score > 5.0:
        metrics["gap_duration_minutes"] = round(best_gap.duration_minutes, 1)
        metrics["gap_distance_to_origin_km"] = round(best_dist, 2)
        metrics["gap_time_offset_minutes"] = round(best_dt, 1)
        metrics["gap_relevance_score"] = round(best_score, 1)

        if best_dist <= 10.0:
            flags.append("AIS_GAP_NEAR_ORIGIN")
        if best_score >= 35.0:
            flags.append("AIS_GAP_EVENT_RELEVANT")

    return round(max(0.0, min(100.0, best_score)), 2), metrics, flags


def compute_approach_departure_score(
    entry_bearing: Optional[float],
    exit_bearing: Optional[float],
    reverse_drift_geojson: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
    """
    Evaluates trajectory ingress/egress vector consistency with reverse drift.
    If reverse drift is unavailable, returns (None, metrics, ['REVERSE_DRIFT_UNAVAILABLE'])
    so the weight can be redistributed without penalizing the vessel.
    """
    metrics: Dict[str, Any] = {
        "approach_bearing_deg": round(entry_bearing, 1) if entry_bearing is not None else None,
        "departure_bearing_deg": round(exit_bearing, 1) if exit_bearing is not None else None,
        "reverse_drift_bearing_deg": None,
        "approach_alignment_deg": None,
        "departure_alignment_deg": None,
    }
    flags: List[str] = []

    if not reverse_drift_geojson or not reverse_drift_geojson.get("coordinates"):
        flags.append("REVERSE_DRIFT_UNAVAILABLE")
        return None, metrics, flags

    coords = reverse_drift_geojson["coordinates"]
    if len(coords) < 2:
        flags.append("REVERSE_DRIFT_UNAVAILABLE")
        return None, metrics, flags

    # Calculate tangent bearing of reverse drift at origin (first segment or overall)
    pt0_lon, pt0_lat = coords[0][0], coords[0][1]
    pt1_lon, pt1_lat = coords[1][0], coords[1][1]
    drift_bearing = calculate_bearing(pt0_lat, pt0_lon, pt1_lat, pt1_lon)
    metrics["reverse_drift_bearing_deg"] = round(drift_bearing, 1)

    alignments: List[float] = []

    if entry_bearing is not None:
        diff_entry = smallest_angle_difference(entry_bearing, drift_bearing)
        metrics["approach_alignment_deg"] = round(diff_entry, 1)
        alignments.append(100.0 * max(0.0, 1.0 - (diff_entry / 180.0)))

    if exit_bearing is not None:
        diff_exit = smallest_angle_difference(exit_bearing, drift_bearing)
        metrics["departure_alignment_deg"] = round(diff_exit, 1)
        alignments.append(100.0 * max(0.0, 1.0 - (diff_exit / 180.0)))

    if not alignments:
        return 50.0, metrics, flags  # Neutral fallback

    score = max(alignments)
    return round(max(0.0, min(100.0, score)), 2), metrics, flags


def calculate_composite_score(
    scores: Dict[str, Optional[float]],
    scoring_mode: str = "UNCERTAINTY_AWARE_5_FACTOR",
) -> Tuple[float, Dict[str, float]]:
    """
    Calculates final Composite Evidence Correlation Score (0–100) with deterministic weight redistribution.
    If an evidence dimension is None (e.g. reverse drift missing), its weight is redistributed
    proportionally among available dimensions so the vessel is not penalized for missing data.
    """
    if scoring_mode == "PS143_4_FACTOR":
        base_weights = {
            "proximity_ps143": 0.35,
            "trajectory_ps143": 0.35,
            "speed_ps143": 0.15,
            "dark_ps143": 0.15,
        }
    else:
        base_weights = {
            "origin_presence": 0.45,
            "behavior_anomaly": 0.20,
            "dwell_time": 0.15,
            "ais_gap": 0.10,
            "approach_departure": 0.10,
        }

    # Identify available factors
    available_keys = [k for k, w in base_weights.items() if scores.get(k) is not None]
    if not available_keys:
        return 0.0, {}

    total_available_weight = sum(base_weights[k] for k in available_keys)
    if total_available_weight <= 0:
        return 0.0, {}

    # Proportional weight redistribution
    applied_weights: Dict[str, float] = {}
    composite = 0.0

    for k in available_keys:
        reweighted = base_weights[k] / total_available_weight
        applied_weights[k] = round(reweighted, 4)
        score_val = scores[k]
        if score_val is not None:
            composite += reweighted * score_val

    composite_bounded = round(max(0.0, min(100.0, composite)), 1)
    return composite_bounded, applied_weights


def determine_risk_class(
    score: float,
    config: Feature3EngineConfig,
) -> str:
    """
    Deterministically maps composite Evidence Correlation Score to non-accusatory ranking categories.
    Categories: 'VERY HIGH', 'HIGH', 'MODERATE', 'LOW'.
    """
    if score >= config.threshold_very_high:
        return "VERY HIGH"
    elif score >= config.threshold_high:
        return "HIGH"
    elif score >= config.threshold_moderate:
        return "MODERATE"
    else:
        return "LOW"
