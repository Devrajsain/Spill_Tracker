"""
Core Feature 3 AIS Attribution & Evidence Correlation Scoring Engine.
Orchestrates AIS cleaning, trajectory reconstruction, spatial candidate extraction,
deterministic multi-factor scoring, GeoJSON compilation, and forensic explainability.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import logging
import pandas as pd

from .cleaning import clean_and_validate_ais
from .explainability import generate_forensic_explanation
from .geojson_builder import build_combined_feature3_geojson, build_vessel_trajectory_geojson
from .schemas import (
    AISRecord,
    Feature2OriginContext,
    Feature3AttributionResponse,
    Feature3EngineConfig,
    LatLon,
    RawEvidenceMetrics,
    ReleaseTimeWindowContract,
    ScoreBreakdown,
    TrajectorySegment,
    VesselAttributionResult,
)
from .scoring import (
    calculate_composite_score,
    compute_ais_gap_score,
    compute_approach_departure_score,
    compute_behavior_anomaly_score,
    compute_dwell_time_score,
    compute_origin_presence_score,
    determine_risk_class,
)
from .spatial import (
    calculate_bearing,
    distance_to_uncertainty_zone_km,
    haversine_km,
    is_point_in_polygon,
    point_to_linestring_distance_km,
)
from .trajectory import (
    find_closest_approach_to_origin,
    interpolate_position_at_time,
    reconstruct_vessel_trajectories,
)

logger = logging.getLogger(__name__)

# Distinct categorical palette for vessel trajectory tracks (avoiding red/green which imply guilt/innocence)
_TRACK_PALETTE = [
    "#2563EB",  # Vibrant Royal Blue
    "#7C3AED",  # Deep Violet
    "#0D9488",  # Teal
    "#D97706",  # Amber/Ochre
    "#4F46E5",  # Indigo
    "#0284C7",  # Sky Blue
    "#9333EA",  # Purple
    "#059669",  # Emerald
    "#EA580C",  # Burnt Orange
    "#64748B",  # Slate
]


def run_feature3_engine(
    feature2_context: Feature2OriginContext,
    ais_data: Union[str, bytes, pd.DataFrame, List[Dict[str, Any]]],
    config: Optional[Feature3EngineConfig] = None,
    scoring_mode: Optional[str] = None,
) -> Feature3AttributionResponse:
    """
    Executes complete, deterministic Feature 3 vessel attribution workflow.
    """
    cfg = config or Feature3EngineConfig()
    mode = scoring_mode or cfg.scoring_mode

    # 1. Clean and validate AIS records
    records, audit_stats = clean_and_validate_ais(ais_data, config=cfg)
    if not records:
        return Feature3AttributionResponse(
            spill_id=feature2_context.spill_id,
            scoring_mode=mode,
            candidate_count=0,
            vessels=[],
            geojson={"type": "FeatureCollection", "features": []},
        )

    # 2. Time Window Definition
    t_start = feature2_context.release_window.start
    t_end = feature2_context.release_window.end
    t_origin = feature2_context.t_origin

    t_filter_start = t_start - timedelta(hours=cfg.time_padding_before_hours)
    t_filter_end = t_end + timedelta(hours=cfg.time_padding_after_hours)

    origin_lat = feature2_context.origin.latitude
    origin_lon = feature2_context.origin.longitude
    uncertainty_km = feature2_context.uncertainty_radius_km
    uncertainty_polygon = feature2_context.uncertainty_zone
    reverse_drift = feature2_context.reverse_drift

    # 3. Group records by MMSI
    records_by_mmsi: Dict[str, List[AISRecord]] = {}
    for r in records:
        records_by_mmsi.setdefault(r.mmsi, []).append(r)

    candidate_results: List[VesselAttributionResult] = []
    vessel_geojsons: List[Dict[str, Any]] = []

    sorted_mmsis = sorted(records_by_mmsi.keys())

    for idx, mmsi in enumerate(sorted_mmsis):
        all_vessel_records = records_by_mmsi[mmsi]
        all_vessel_records.sort(key=lambda r: r.timestamp)

        # Reconstruct continuous segments and gaps across the vessel's track
        valid_segs, gap_segs = reconstruct_vessel_trajectories(
            all_vessel_records,
            max_gap_minutes=cfg.max_gap_minutes,
        )

        # Extract records within the padded temporal observation window
        event_window_records = [
            r for r in all_vessel_records 
            if t_filter_start <= r.timestamp <= t_filter_end
        ]

        # Calculate closest approach
        ca_data = find_closest_approach_to_origin(
            all_vessel_records,
            origin_lat,
            origin_lon,
        )
        min_dist_km = ca_data["distance_km"]
        ca_time = ca_data["time"]

        # Check for presence inside uncertainty polygon or within uncertainty radius
        inside_zone = False
        dwell_inside_min = 0.0
        dwell_near_min = 0.0

        for seg in valid_segs:
            for p in seg.points:
                dist_zone = distance_to_uncertainty_zone_km(
                    p.latitude, p.longitude,
                    origin_lat, origin_lon,
                    uncertainty_km,
                    uncertainty_polygon,
                )
                if dist_zone <= 0.001 or is_point_in_polygon(p.latitude, p.longitude, uncertainty_polygon):
                    inside_zone = True

        # Calculate dwell minutes (time duration between points inside or near zone)
        for seg in valid_segs:
            for i in range(len(seg.points) - 1):
                p1 = seg.points[i]
                p2 = seg.points[i + 1]
                dt = (p2.timestamp - p1.timestamp).total_seconds() / 60.0
                if dt <= cfg.max_gap_minutes:
                    d1 = distance_to_uncertainty_zone_km(p1.latitude, p1.longitude, origin_lat, origin_lon, uncertainty_km, uncertainty_polygon)
                    d2 = distance_to_uncertainty_zone_km(p2.latitude, p2.longitude, origin_lat, origin_lon, uncertainty_km, uncertainty_polygon)
                    avg_d = (d1 + d2) / 2.0
                    if avg_d <= 0.001:
                        dwell_inside_min += dt
                    elif avg_d <= (1.5 * uncertainty_km):
                        dwell_near_min += dt

        # Check for relevant AIS gaps near origin
        has_relevant_gap = False
        for gap in gap_segs:
            if gap.start_position:
                gap_dist = haversine_km(gap.start_position.latitude, gap.start_position.longitude, origin_lat, origin_lon)
                if gap_dist <= (uncertainty_km + 15.0):
                    has_relevant_gap = True
                    break

        # Check reverse drift corridor proximity
        min_dist_to_drift = 9999.0
        if reverse_drift:
            for p in all_vessel_records:
                d_drift = point_to_linestring_distance_km(p.latitude, p.longitude, reverse_drift)
                if d_drift < min_dist_to_drift:
                    min_dist_to_drift = d_drift

        # Spatial & temporal candidate filtering criteria:
        # Include if:
        #  1) observed inside uncertainty zone, OR
        #  2) closest approach <= search_radius_km, OR
        #  3) relevant AIS gap near origin, OR
        #  4) track passes within 10 km of reverse drift corridor
        is_candidate = (
            inside_zone or
            min_dist_km <= cfg.search_radius_km or
            has_relevant_gap or
            (reverse_drift is not None and min_dist_to_drift <= 10.0)
        )

        if not is_candidate:
            continue

        # Compute temporal difference from release window
        if ca_time:
            if t_start <= ca_time <= t_end:
                time_offset_min = 0.0
            elif ca_time < t_start:
                time_offset_min = (t_start - ca_time).total_seconds() / 60.0
            else:
                time_offset_min = (ca_time - t_end).total_seconds() / 60.0
        else:
            time_offset_min = 9999.0

        # Interpolate vessel position at T_origin
        interp_pos, interp_flag = interpolate_position_at_time(
            all_vessel_records,
            t_origin,
            max_interpolation_gap_min=cfg.max_interpolation_gap_minutes,
        )

        # Warning & Quality flags
        warning_flags: List[str] = []
        quality_flags: List[str] = []

        if interp_flag:
            quality_flags.append(f"INTERPOLATION_{interp_flag}")

        # Ingress / Egress bearings
        entry_bearing = None
        exit_bearing = None
        if len(all_vessel_records) >= 2:
            entry_bearing = calculate_bearing(
                all_vessel_records[0].latitude, all_vessel_records[0].longitude,
                all_vessel_records[1].latitude, all_vessel_records[1].longitude,
            )
            exit_bearing = calculate_bearing(
                all_vessel_records[-2].latitude, all_vessel_records[-2].longitude,
                all_vessel_records[-1].latitude, all_vessel_records[-1].longitude,
            )

        # Compute Individual Scores
        # 1. Origin Presence Score (0–100)
        origin_score = compute_origin_presence_score(
            closest_distance_km=min_dist_km,
            time_offset_min=time_offset_min,
            inside_uncertainty_zone=inside_zone,
            config=cfg,
        )

        # 2. Behavior Anomaly Score (0–100)
        behavior_score, behavior_metrics, behavior_flags = compute_behavior_anomaly_score(
            event_records=event_window_records,
            all_records=all_vessel_records,
            inside_zone=inside_zone,
            min_distance_km=min_dist_km,
        )
        warning_flags.extend(behavior_flags)

        # 3. Dwell Time Score (0–100)
        dwell_score = compute_dwell_time_score(
            dwell_inside_min=dwell_inside_min,
            dwell_near_min=dwell_near_min,
            config=cfg,
        )

        # 4. AIS Gap Score (0–100)
        gap_score, gap_metrics, gap_flags = compute_ais_gap_score(
            gap_segments=gap_segs,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            release_start=t_start,
            release_end=t_end,
            config=cfg,
        )
        warning_flags.extend(gap_flags)

        # 5. Approach / Departure Alignment Score (0–100 or None if reverse drift unavailable)
        drift_score, drift_metrics, drift_flags = compute_approach_departure_score(
            entry_bearing=entry_bearing,
            exit_bearing=exit_bearing,
            reverse_drift_geojson=reverse_drift,
        )
        quality_flags.extend(drift_flags)

        # PS-143 Alternative Sub-scores
        prox_ps143 = compute_origin_presence_score(min_dist_km, 0.0, inside_zone, cfg)
        traj_ps143 = drift_score if drift_score is not None else prox_ps143
        speed_ps143 = behavior_score
        dark_ps143 = gap_score

        scores_dict = {
            "origin_presence": origin_score,
            "behavior_anomaly": behavior_score,
            "dwell_time": dwell_score,
            "ais_gap": gap_score,
            "approach_departure": drift_score,
            "proximity_ps143": prox_ps143,
            "trajectory_ps143": traj_ps143,
            "speed_ps143": speed_ps143,
            "dark_ps143": dark_ps143,
        }

        # Calculate composite score with dynamic weight redistribution
        composite_score, applied_weights = calculate_composite_score(scores_dict, scoring_mode=mode)
        risk_class = determine_risk_class(composite_score, cfg)

        score_breakdown = ScoreBreakdown(
            origin_presence=origin_score,
            behavior_anomaly=behavior_score,
            dwell_time=dwell_score,
            ais_gap=gap_score,
            approach_departure=drift_score,
            applied_weights=applied_weights,
            proximity_ps143=prox_ps143,
            trajectory_ps143=traj_ps143,
            speed_ps143=speed_ps143,
            dark_ps143=dark_ps143,
        )

        raw_evidence = RawEvidenceMetrics(
            closest_approach_distance_km=min_dist_km,
            closest_approach_time=ca_time,
            time_offset_minutes=round(time_offset_min, 1),
            inside_uncertainty_zone=inside_zone,
            position_at_origin=interp_pos,
            sog_at_origin_kn=ca_data.get("sog"),
            baseline_median_sog_kn=behavior_metrics.get("baseline_median_sog_kn"),
            event_median_sog_kn=behavior_metrics.get("event_median_sog_kn"),
            speed_reduction_ratio=behavior_metrics.get("speed_reduction_ratio"),
            minimum_sog_kn=behavior_metrics.get("minimum_sog_kn"),
            course_change_degrees=behavior_metrics.get("course_change_degrees"),
            dwell_minutes_inside_zone=round(dwell_inside_min, 1),
            dwell_minutes_near_zone=round(dwell_near_min, 1),
            gap_duration_minutes=gap_metrics.get("gap_duration_minutes"),
            gap_distance_to_origin_km=gap_metrics.get("gap_distance_to_origin_km"),
            gap_time_offset_minutes=gap_metrics.get("gap_time_offset_minutes"),
            gap_relevance_score=gap_metrics.get("gap_relevance_score"),
            approach_bearing_deg=drift_metrics.get("approach_bearing_deg"),
            departure_bearing_deg=drift_metrics.get("departure_bearing_deg"),
            reverse_drift_bearing_deg=drift_metrics.get("reverse_drift_bearing_deg"),
            approach_alignment_deg=drift_metrics.get("approach_alignment_deg"),
            departure_alignment_deg=drift_metrics.get("departure_alignment_deg"),
        )

        # Vessel Metadata
        v_name = all_vessel_records[0].vessel_name or f"Vessel {mmsi}"
        v_type = all_vessel_records[0].vessel_type or "Commercial Cargo/Tanker"
        v_flag = all_vessel_records[0].flag or "International"

        last_pt = all_vessel_records[-1]

        # Assign harmonious categorical track color
        v_color = _TRACK_PALETTE[idx % len(_TRACK_PALETTE)]

        # Generate GeoJSON for this vessel
        v_geojson = build_vessel_trajectory_geojson(
            mmsi=mmsi,
            valid_segments=valid_segs,
            gap_segments=gap_segs,
            evidence=raw_evidence,
            color=v_color,
        )
        vessel_geojsons.append(v_geojson)

        # Generate Natural Language Forensic Explanation
        explanation = generate_forensic_explanation(
            mmsi=mmsi,
            vessel_name=v_name,
            overall_score=composite_score,
            risk_class=risk_class,
            scores=score_breakdown,
            evidence=raw_evidence,
            warning_flags=sorted(list(set(warning_flags))),
            quality_flags=sorted(list(set(quality_flags))),
            scoring_mode=mode,
        )

        candidate_results.append(VesselAttributionResult(
            id=f"v-{mmsi}",
            mmsi=mmsi,
            name=v_name,
            type=v_type,
            flag=v_flag,
            overall_score=composite_score,
            risk_class=risk_class,
            scoring_mode=mode,
            scores=score_breakdown,
            evidence=raw_evidence,
            warning_flags=sorted(list(set(warning_flags))),
            quality_flags=sorted(list(set(quality_flags))),
            explanation=explanation,
            current_latitude=round(last_pt.latitude, 6),
            current_longitude=round(last_pt.longitude, 6),
            heading_deg=round(last_pt.cog or 0.0, 1),
            speed_kts=f"{round(last_pt.sog or 0.0, 1)} kts",
            trajectory_geojson=v_geojson,
        ))

    # Deterministic sorting:
    # 1. overall_score descending
    # 2. closest approach distance ascending
    # 3. mmsi ascending
    candidate_results.sort(
        key=lambda v: (
            -round(v.overall_score, 2),
            round(v.evidence.closest_approach_distance_km, 3),
            v.mmsi,
        )
    )

    # Combined map GeoJSON
    combined_geojson = build_combined_feature3_geojson(
        vessel_geojsons=vessel_geojsons,
        uncertainty_polygon_geojson=uncertainty_polygon,
        reverse_drift_geojson=reverse_drift,
    )

    return Feature3AttributionResponse(
        spill_id=feature2_context.spill_id,
        scoring_mode=mode,
        candidate_count=len(candidate_results),
        vessels=candidate_results,
        geojson=combined_geojson,
    )
