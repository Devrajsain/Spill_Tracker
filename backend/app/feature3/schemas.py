"""
Schemas and data contracts for Feature 3: AIS Vessel Attribution & Evidence Correlation Engine.
Adheres strictly to non-accusatory evidence ranking semantics and uncertainty-aware contracts.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LatLon(BaseModel):
    """Latitude and Longitude coordinates in decimal degrees."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")


class ReleaseTimeWindowContract(BaseModel):
    """Estimated candidate release time window with start and end bounds."""
    start: datetime = Field(..., description="Earliest plausible release time boundary (UTC).")
    end: datetime = Field(..., description="Latest plausible release time boundary (UTC).")
    peak_evidence_time: Optional[datetime] = Field(None, description="Timestamp exhibiting peak evidence if computed.")

    @property
    def midpoint(self) -> datetime:
        """Calculates T_origin as the temporal midpoint of the window."""
        delta = self.end - self.start
        return self.start + (delta / 2)


class Feature2OriginContext(BaseModel):
    """
    Clean internal contract representing Feature 2 output ingested by Feature 3.
    Decoupled from internal physics classes.
    """
    spill_id: str = Field(default="SPILL_EVENT", description="Identifier for the spill event")
    origin: LatLon = Field(..., description="Estimated origin centroid coordinates")
    release_window: ReleaseTimeWindowContract = Field(..., description="Estimated candidate release time window")
    uncertainty_radius_km: float = Field(default=3.0, ge=0.0, description="Spatial uncertainty dispersion radius in km")
    uncertainty_zone: Optional[Dict[str, Any]] = Field(default=None, description="GeoJSON Polygon/MultiPolygon of spatial uncertainty boundary")
    reverse_drift: Optional[Dict[str, Any]] = Field(default=None, description="GeoJSON LineString/time series of backward drift trajectory")
    feature2_quality: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metocean and simulation quality flags")

    @property
    def t_origin(self) -> datetime:
        """Returns peak evidence time if present, otherwise midpoint of release window."""
        if self.release_window.peak_evidence_time:
            return self.release_window.peak_evidence_time
        return self.release_window.midpoint


class AISRecord(BaseModel):
    """Standardized single AIS telemetry observation."""
    mmsi: str = Field(..., description="Maritime Mobile Service Identity (9-digit identifier)")
    timestamp: datetime = Field(..., description="Observation timestamp in UTC")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    sog: Optional[float] = Field(None, ge=0.0, le=102.2, description="Speed Over Ground in knots")
    cog: Optional[float] = Field(None, ge=0.0, le=360.0, description="Course Over Ground in degrees")
    vessel_name: Optional[str] = Field(None, description="Vessel display name")
    vessel_type: Optional[str] = Field(None, description="Vessel category / shiptype")
    flag: Optional[str] = Field(None, description="Vessel flag state / country")
    quality_flags: List[str] = Field(default_factory=list, description="Quality and validation flags")


class TrajectorySegment(BaseModel):
    """Time-valid continuous trajectory segment or explicit AIS gap."""
    mmsi: str
    start_time: datetime
    end_time: datetime
    points: List[AISRecord] = Field(default_factory=list)
    is_gap: bool = Field(default=False, description="True if segment represents an AIS silence interval > MAX_GAP")
    duration_minutes: float = Field(default=0.0)
    distance_km: float = Field(default=0.0)
    start_position: Optional[LatLon] = None
    end_position: Optional[LatLon] = None


class ScoreBreakdown(BaseModel):
    """
    Normalized evidence scores (0–100) across all evaluated evidence dimensions.
    Fields may be None if underlying evidence was genuinely unavailable (e.g. reverse drift missing).
    """
    origin_presence: float = Field(..., ge=0.0, le=100.0, description="Spatial and temporal origin zone overlap score (0-100)")
    behavior_anomaly: float = Field(..., ge=0.0, le=100.0, description="Speed reduction and course change anomaly score (0-100)")
    dwell_time: float = Field(..., ge=0.0, le=100.0, description="Duration spent inside/near origin uncertainty zone (0-100)")
    ais_gap: float = Field(..., ge=0.0, le=100.0, description="Event-specific AIS transponder gap score (0-100)")
    approach_departure: Optional[float] = Field(
        None, ge=0.0, le=100.0,
        description="Ingress/egress vector plausibility and drift context (0-100). None if reverse drift is unavailable."
    )

    # Weights actually applied to compute composite score after redistributing missing evidence weights
    applied_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Effective weights applied after handling missing evidence (sum to 1.0)"
    )

    # Legacy/Baseline PS-143 4-factor scores if calculated
    proximity_ps143: Optional[float] = Field(None, ge=0.0, le=100.0)
    trajectory_ps143: Optional[float] = Field(None, ge=0.0, le=100.0)
    speed_ps143: Optional[float] = Field(None, ge=0.0, le=100.0)
    dark_ps143: Optional[float] = Field(None, ge=0.0, le=100.0)


class RawEvidenceMetrics(BaseModel):
    """Auditable raw physical and kinematics evidence metrics."""
    closest_approach_distance_km: float = Field(..., description="Minimum geodetic distance to origin centroid in km")
    closest_approach_time: Optional[datetime] = Field(None, description="Timestamp of closest approach")
    time_offset_minutes: float = Field(..., description="Temporal difference from T_origin or release window boundary in minutes")
    inside_uncertainty_zone: bool = Field(default=False, description="Whether vessel entered the Feature 2 spatial uncertainty polygon")
    position_at_origin: Optional[Dict[str, float]] = Field(None, description="Interpolated lat/lon position at T_origin if valid")
    sog_at_origin_kn: Optional[float] = Field(None, description="SOG at closest approach or T_origin in knots")
    baseline_median_sog_kn: Optional[float] = Field(None, description="Pre-event / outer-transit median SOG in knots")
    event_median_sog_kn: Optional[float] = Field(None, description="Median SOG near origin in knots")
    speed_reduction_ratio: Optional[float] = Field(None, description="Relative speed reduction (0.0 to 1.0)")
    minimum_sog_kn: Optional[float] = Field(None, description="Minimum SOG observed near event in knots")
    course_change_degrees: Optional[float] = Field(None, description="Maximum course deviation observed near origin")
    dwell_minutes_inside_zone: float = Field(default=0.0, description="Minutes spent inside spatial uncertainty zone")
    dwell_minutes_near_zone: float = Field(default=0.0, description="Minutes spent within 1.5x uncertainty radius")
    gap_duration_minutes: Optional[float] = Field(None, description="Duration of longest relevant AIS gap in minutes")
    gap_distance_to_origin_km: Optional[float] = Field(None, description="Distance from gap midpoint to origin centroid")
    gap_time_offset_minutes: Optional[float] = Field(None, description="Time offset of gap midpoint from T_origin")
    gap_relevance_score: Optional[float] = Field(None, description="Computed relevance of the gap to the spill event (0-100)")
    approach_bearing_deg: Optional[float] = Field(None, description="Vessel entry bearing into origin area")
    departure_bearing_deg: Optional[float] = Field(None, description="Vessel exit bearing from origin area")
    reverse_drift_bearing_deg: Optional[float] = Field(None, description="Reverse drift tangent bearing at event time")
    approach_alignment_deg: Optional[float] = Field(None, description="Angular alignment difference for approach")
    departure_alignment_deg: Optional[float] = Field(None, description="Angular alignment difference for departure")


class VesselAttributionResult(BaseModel):
    """Complete explainable evidence attribution record for a single candidate vessel."""
    id: str = Field(..., description="Unique result identifier (e.g. v-123456789)")
    mmsi: str = Field(..., description="Vessel MMSI")
    name: str = Field(..., description="Vessel display name")
    type: str = Field(..., description="Vessel type category")
    flag: str = Field(..., description="Vessel flag country")
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Composite Evidence Correlation Score (0–100)")
    risk_class: str = Field(..., description="Deterministic ranking category: 'VERY HIGH', 'HIGH', 'MODERATE', or 'LOW'")
    scoring_mode: str = Field(default="UNCERTAINTY_AWARE_5_FACTOR", description="Scoring formula applied")
    scores: ScoreBreakdown
    evidence: RawEvidenceMetrics
    warning_flags: List[str] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)
    explanation: str = Field(..., description="Comprehensive explainability forensic narrative")
    current_latitude: float
    current_longitude: float
    heading_deg: float
    speed_kts: str
    trajectory_geojson: Optional[Dict[str, Any]] = None


class Feature3EngineConfig(BaseModel):
    """Configurable hyperparameters for the Feature 3 engine."""
    max_gap_minutes: float = Field(default=30.0, ge=5.0, description="Max time gap for continuous trajectory segments")
    max_interpolation_gap_minutes: float = Field(default=45.0, ge=5.0, description="Max gap allowable for time interpolation at T_origin")
    time_padding_before_hours: float = Field(default=4.0, ge=0.5, description="Time window padding before release start")
    time_padding_after_hours: float = Field(default=4.0, ge=0.5, description="Time window padding after release end")
    search_radius_km: float = Field(default=25.0, ge=1.0, description="Outer spatial candidate search radius around origin")
    spatial_scale_km: float = Field(default=6.0, ge=0.5, description="Exponential spatial decay scaling factor")
    temporal_scale_min: float = Field(default=60.0, ge=5.0, description="Exponential temporal decay scaling factor")
    dwell_saturation_minutes: float = Field(default=60.0, ge=10.0, description="Dwell time duration producing 100% dwell score")
    scoring_mode: str = Field(default="UNCERTAINTY_AWARE_5_FACTOR", description="'UNCERTAINTY_AWARE_5_FACTOR' or 'PS143_4_FACTOR'")

    # Configurable AIS jump and speed thresholds
    max_ais_speed_knots: float = Field(
        default=65.0, ge=20.0,
        description="Kinematic threshold in knots above which consecutive pings represent an IMPLAUSIBLE_JUMP"
    )
    unusual_speed_knots: float = Field(
        default=35.0, ge=15.0,
        description="Speed threshold in knots flagged as UNUSUAL_HIGH_SPEED without invalidating"
    )

    # Risk category score thresholds
    threshold_very_high: float = Field(default=80.0)
    threshold_high: float = Field(default=60.0)
    threshold_moderate: float = Field(default=30.0)

    # Safety flag: never allow silent demo fallback in real pipeline runs
    allow_demo_fallback: bool = Field(
        default=False,
        description="If False, missing real AIS data returns an explicit error/validation state, never silent demo substitution."
    )


class Feature3AttributionRequest(BaseModel):
    """Request payload for executing Feature 3 AIS Vessel Attribution."""
    case_id: Optional[str] = None
    feature2_context: Optional[Feature2OriginContext] = None
    ais_csv_content: Optional[str] = None
    ais_records: Optional[List[Dict[str, Any]]] = None
    scoring_mode: Optional[str] = "UNCERTAINTY_AWARE_5_FACTOR"
    config: Optional[Feature3EngineConfig] = None


class Feature3AttributionResponse(BaseModel):
    """Top-level API response from Feature 3."""
    spill_id: str
    scoring_mode: str
    candidate_count: int
    vessels: List[VesselAttributionResult] = Field(default_factory=list)
    geojson: Dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = Field(
        default="Evidence Correlation Scores (0–100) are deterministic multi-factor ranking metrics. They do not constitute proof of causation, vessel culpability, or legal responsibility.",
        description="Mandatory scientific and legal interpretation notice"
    )
