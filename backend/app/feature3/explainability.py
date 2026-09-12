"""
Forensic explainability narrative generator for Feature 3.
Transforms raw kinematic metrics, scores, and quality flags into structured, auditable natural language.
"""

from typing import List
from .schemas import RawEvidenceMetrics, ScoreBreakdown


def generate_forensic_explanation(
    mmsi: str,
    vessel_name: str,
    overall_score: float,
    risk_class: str,
    scores: ScoreBreakdown,
    evidence: RawEvidenceMetrics,
    warning_flags: List[str],
    quality_flags: List[str],
    scoring_mode: str,
) -> str:
    """
    Constructs a deterministic, auditable markdown explanation for a candidate vessel.
    Adheres strictly to non-accusatory terminology.
    """
    lines = [
        f"### Forensic Evidence Audit: {vessel_name} (MMSI: {mmsi})",
        f"**Evidence Correlation Score:** {overall_score}/100 — **Classification:** {risk_class}",
        f"**Scoring Formulation:** {scoring_mode}",
        "",
        "#### 1. Origin-Zone Spatio-Temporal Correlation",
        f"- Score: {scores.origin_presence}/100",
        f"- Closest Approach Distance: {evidence.closest_approach_distance_km:.2f} km to estimated spill origin",
        f"- Temporal Offset: {evidence.time_offset_minutes:.1f} minutes from candidate release window",
        f"- Uncertainty Zone Entry: {'YES (Observed inside modeled boundary)' if evidence.inside_uncertainty_zone else 'NO (Outside modeled boundary)'}",
    ]

    if evidence.position_at_origin:
        lines.append(
            f"- Position at T_origin: {evidence.position_at_origin.get('latitude', 0):.4f}°N, "
            f"{evidence.position_at_origin.get('longitude', 0):.4f}°E (SOG: {evidence.position_at_origin.get('sog', 0)} kn)"
        )

    lines.extend([
        "",
        "#### 2. Kinematic & Behavioral Evidence",
        f"- Score: {scores.behavior_anomaly}/100",
    ])
    if evidence.baseline_median_sog_kn is not None:
        lines.append(f"- Baseline Median SOG: {evidence.baseline_median_sog_kn} kn")
        lines.append(f"- Event Area Median SOG: {evidence.event_median_sog_kn} kn")
        if evidence.speed_reduction_ratio is not None and evidence.speed_reduction_ratio > 0.05:
            lines.append(f"- Observed Speed Reduction: {evidence.speed_reduction_ratio * 100:.1f}% drop relative to baseline")
    else:
        lines.append(f"- Event Area Median SOG: {evidence.event_median_sog_kn or 'N/A'} kn (baseline insufficient)")

    if evidence.minimum_sog_kn is not None:
        lines.append(f"- Minimum Observed SOG: {evidence.minimum_sog_kn} kn")
    if evidence.course_change_degrees is not None:
        lines.append(f"- Maximum Course Deviation: {evidence.course_change_degrees:.1f}°")

    lines.extend([
        "",
        "#### 3. Dwell Duration Evidence",
        f"- Score: {scores.dwell_time}/100",
        f"- Time Spent Inside Uncertainty Boundary: {evidence.dwell_minutes_inside_zone:.1f} minutes",
        f"- Time Spent in Immediate Vicinity (<=1.5x radius): {evidence.dwell_minutes_near_zone:.1f} minutes",
        "",
        "#### 4. AIS Telemetry Gap Evidence",
        f"- Score: {scores.ais_gap}/100",
    ])

    if evidence.gap_duration_minutes is not None and evidence.gap_duration_minutes > 0:
        lines.append(f"- Most Relevant AIS Gap Duration: {evidence.gap_duration_minutes:.1f} minutes")
        lines.append(f"- Gap Midpoint Distance to Origin: {evidence.gap_distance_to_origin_km:.2f} km")
        lines.append(f"- Gap Time Offset from Release Window: {evidence.gap_time_offset_minutes:.1f} minutes")
        lines.append(f"- Gap Relevance Metric: {evidence.gap_relevance_score:.1f}/100")
    else:
        lines.append("- No event-relevant AIS transponder silence intervals detected (continuous telemetry).")

    lines.extend([
        "",
        "#### 5. Trajectory & Drift Vector Consistency",
    ])
    if scores.approach_departure is not None:
        lines.append(f"- Score: {scores.approach_departure}/100")
        if evidence.approach_bearing_deg is not None:
            lines.append(f"- Approach Bearing: {evidence.approach_bearing_deg:.1f}°")
        if evidence.departure_bearing_deg is not None:
            lines.append(f"- Departure Bearing: {evidence.departure_bearing_deg:.1f}°")
        if evidence.reverse_drift_bearing_deg is not None:
            lines.append(f"- Modeled Reverse Drift Tangent: {evidence.reverse_drift_bearing_deg:.1f}°")
        if evidence.approach_alignment_deg is not None:
            lines.append(f"- Ingress Alignment Difference: {evidence.approach_alignment_deg:.1f}°")
    else:
        lines.append("- Score: N/A (Reverse hydrodynamic drift trajectory unavailable; weight redistributed proportionally without penalty)")

    # Data Quality and Flags
    lines.extend([
        "",
        "#### 6. Data Quality & Audit Flags",
        f"- Warning Flags: {', '.join(warning_flags) if warning_flags else 'None'}",
        f"- Quality & Provenance Flags: {', '.join(quality_flags) if quality_flags else 'NOMINAL_QUALITY'}",
        f"- Applied Weights: {scores.applied_weights}",
        "",
        "#### 7. Interpretation",
    ])

    if overall_score >= 80.0:
        lines.append(
            "The vessel demonstrates very high multi-dimensional correlation with the estimated release window, "
            "spatial origin zone, and observed kinematic behavior."
        )
    elif overall_score >= 60.0:
        lines.append(
            "The vessel demonstrates substantial correlation with the estimated origin region and release timing."
        )
    elif overall_score >= 30.0:
        lines.append(
            "The vessel shows moderate spatial or temporal proximity to the event, with limited behavioral anomalies."
        )
    else:
        lines.append(
            "The vessel exhibits low correlation with the modeled spill event."
        )

    lines.extend([
        "",
        "> **Scientific & Legal Notice**: Evidence Correlation Scores (0–100) are deterministic multi-factor ranking metrics. "
        "They do not constitute proof of causation, vessel culpability, or legal responsibility."
    ])

    return "\n".join(lines)
